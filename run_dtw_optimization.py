"""
Comprehensive Backtest & Grid-Search Simulation for DTW Optimization.
Evaluates:
  - Methods: Traditional Pearson vs DTW (w=3, w=5, w=8)
  - Match Windows: 35d, 50d, 65d
  - Holding Periods: 10d, 15d, 20d
  - Return Thresholds: +5.0%, +7.0%, +8.0%
  - Real TSE Prime Price Cache (~650 PBR<1.0 stocks, 1,221 trading days)
  - Evaluates Win Rate, Profit Factor, Signal Frequency, and Zero-Hit Ratio
"""

import os
import sys
import time
import pickle
import json
import numpy as np
import pandas as pd
from concurrent.futures import ProcessPoolExecutor

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)
import dtw_engine

CACHE_FILE = os.path.join(BASE_DIR, "screener_price_cache.pkl")
REPORT_OUTPUT = os.path.join(BASE_DIR, "dtw_optimization_results.json")

def load_data():
    if not os.path.exists(CACHE_FILE):
        raise FileNotFoundError(f"{CACHE_FILE} not found")
    with open(CACHE_FILE, "rb") as f:
        cached = pickle.load(f)
    return cached["data"], cached["dates"]

def run_simulation():
    print("🚀 [START] Loading price data...")
    stock_data, dates = load_data()
    tickers = list(stock_data.keys())
    print(f"Loaded {len(tickers)} stocks over {len(dates)} trading days.")
    
    # We sample every 10 trading days over the last 3 years (approx 750 trading days)
    # to evaluate realistic walk-forward screening dates without lookahead bias
    total_dates = len(dates)
    test_step = 12  # every ~2.5 weeks
    test_indices = list(range(total_dates - 600, total_dates - 25, test_step))
    print(f"Evaluation over {len(test_indices)} historical screening test points.")

    grid_configs = [
        # (Method, window_radius, match_days, hold_days, thresh)
        # Baseline: Traditional
        ("Traditional (Fixed)", 0, 50, 15, 8.0),
        ("Traditional (Fixed)", 0, 50, 15, 5.0),
        ("Traditional (Fixed)", 0, 35, 10, 5.0),
        # DTW-3 (Tight elastic)
        ("DTW (w=3)", 3, 50, 15, 8.0),
        ("DTW (w=3)", 3, 50, 15, 5.0),
        ("DTW (w=3)", 3, 35, 10, 5.0),
        # DTW-5 (Balanced standard)
        ("DTW (w=5)", 5, 50, 15, 8.0),
        ("DTW (w=5)", 5, 50, 15, 5.0),
        ("DTW (w=5)", 5, 35, 10, 5.0),
        ("DTW (w=5)", 5, 35, 15, 5.0),
        ("DTW (w=5)", 5, 50, 20, 7.0),
        ("DTW (w=5)", 5, 65, 20, 7.0),
        # DTW-8 (Wide elastic)
        ("DTW (w=8)", 8, 50, 15, 8.0),
        ("DTW (w=8)", 8, 50, 15, 5.0),
        ("DTW (w=8)", 8, 35, 10, 5.0),
    ]

    results = []

    for method, w_rad, n_match, future_day, thresh in grid_configs:
        t0 = time.time()
        trades = []
        zero_hit_count = 0
        
        for t_idx in test_indices:
            hits_on_date = 0
            for ticker in tickers:
                close = stock_data[ticker]
                if len(close) <= t_idx:
                    continue
                c_slice = close[:t_idx]
                total_len = len(c_slice)
                if total_len < n_match + 150:
                    continue
                    
                # 1. 200d trend filter
                if total_len >= 200:
                    sma200 = float(np.mean(c_slice[-200:]))
                    sma25 = float(np.mean(c_slice[-25:]))
                    cur_p = float(c_slice[-1])
                    if cur_p < sma200 or cur_p > sma200 * 1.25 or cur_p < sma25 * 0.96:
                        continue
                        
                target_pat = c_slice[-n_match:]
                t_mean = float(np.mean(target_pat))
                t_std = float(np.std(target_pat))
                if t_std < 1e-6:
                    continue
                t_norm = ((target_pat - t_mean) / t_std).astype(np.float32)
                
                search_end = total_len - n_match - future_day - 5
                if search_end < n_match + 20:
                    continue
                past_data = c_slice[:search_end]
                windows = np.lib.stride_tricks.sliding_window_view(past_data, window_shape=n_match)
                w_means = np.mean(windows, axis=1, keepdims=True)
                w_stds = np.std(windows, axis=1, keepdims=True)
                valid = (w_stds[:, 0] > 1e-6)
                if not np.any(valid):
                    continue
                    
                windows_norm = np.zeros_like(windows, dtype=np.float32)
                windows_norm[valid] = (windows[valid] - w_means[valid]) / w_stds[valid]
                
                # Compute distance / similarity
                if method.startswith("Traditional"):
                    dots = np.dot(windows_norm, t_norm) / n_match
                    dots[~valid] = -1.0
                    sorted_indices = np.argsort(dots)[::-1]
                    sim_filter = (dots > 0.45)
                else:
                    # DTW distance (lower is more similar)
                    # Use coarse dot-product pre-filter for top 50 windows, then exact DTW
                    dots = np.dot(windows_norm, t_norm) / n_match
                    top_candidates = np.argsort(dots)[::-1][:60]
                    cand_windows = windows_norm[top_candidates]
                    
                    dtw_dists = dtw_engine.compute_fast_dtw_distances(t_norm, cand_windows, window_radius=w_rad)
                    dtw_sorted = np.argsort(dtw_dists)
                    sorted_indices = [top_candidates[i] for i in dtw_sorted]
                    # Score metric: converted distance
                    sim_filter = np.ones(len(sorted_indices), dtype=bool)

                chosen = []
                min_dist = max(15, n_match // 2)
                for idx in sorted_indices:
                    if all(abs(idx - c) >= min_dist for c in chosen):
                        chosen.append(idx)
                        if len(chosen) == 5:
                            break
                            
                if len(chosen) >= 4:
                    p_rets = []
                    for c_idx in chosen:
                        p_end = c_idx + n_match - 1
                        p_fut = p_end + future_day
                        if p_fut < len(c_slice):
                            r = (c_slice[p_fut] - c_slice[p_end]) / c_slice[p_end] * 100.0
                            p_rets.append(r)
                    if len(p_rets) >= 4:
                        win_c = sum(1 for r in p_rets if r > 0.0)
                        win_r = (win_c / len(p_rets)) * 100.0
                        avg_r = float(np.mean(p_rets))
                        min_r = min(p_rets)
                        req_avg = max(5.0, thresh * 0.7)
                        
                        if win_r >= 80.0 and avg_r >= req_avg and min_r >= -4.5:
                            # Candidate triggered entry!
                            # Now evaluate ACTUAL forward return from t_idx to t_idx + future_day with -4.5% stop-loss
                            entry_p = float(c_slice[-1])
                            future_slice = close[t_idx : min(len(close), t_idx + future_day + 1)]
                            if len(future_slice) >= future_day:
                                # Track daily price during holding period for stop-loss
                                trade_ret = 0.0
                                stopped = False
                                for day_p in future_slice[1:]:
                                    d_ret = (day_p - entry_p) / entry_p * 100.0
                                    if d_ret <= -4.5:
                                        trade_ret = -4.5
                                        stopped = True
                                        break
                                if not stopped:
                                    trade_ret = (future_slice[-1] - entry_p) / entry_p * 100.0
                                    
                                trades.append(trade_ret)
                                hits_on_date += 1
                                
            if hits_on_date == 0:
                zero_hit_count += 1
                
        # Aggregate statistics
        total_trades = len(trades)
        zero_hit_rate = (zero_hit_count / len(test_indices)) * 100.0
        
        if total_trades > 0:
            wins = [r for r in trades if r > 0.0]
            losses = [r for r in trades if r <= 0.0]
            win_rate = (len(wins) / total_trades) * 100.0
            avg_return = float(np.mean(trades))
            
            gross_win = sum(wins) if wins else 0.0
            gross_loss = abs(sum(losses)) if losses else 1e-6
            profit_factor = gross_win / gross_loss if gross_loss > 0 else 99.0
            max_loss = min(trades) if trades else 0.0
        else:
            win_rate = 0.0
            avg_return = 0.0
            profit_factor = 0.0
            max_loss = 0.0
            
        dur = time.time() - t0
        summary_item = {
            "method": method,
            "window_radius": w_rad,
            "match_days": n_match,
            "hold_days": future_day,
            "thresh": thresh,
            "total_trades": total_trades,
            "win_rate": round(win_rate, 2),
            "avg_return": round(avg_return, 2),
            "profit_factor": round(profit_factor, 2),
            "zero_hit_rate": round(zero_hit_rate, 1),
            "max_loss": round(max_loss, 2),
            "calc_time_sec": round(dur, 2)
        }
        results.append(summary_item)
        print(f"[{method} {n_match}d/{future_day}d/+{thresh}%] Trades={total_trades}, WinRate={win_rate:.1f}%, AvgRet={avg_return:+.2f}%, PF={profit_factor:.2f}, ZeroHit={zero_hit_rate:.1f}%, Time={dur:.1f}s")

    with open(REPORT_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n✅ All simulations finished! Results saved to {REPORT_OUTPUT}")

if __name__ == "__main__":
    run_simulation()
