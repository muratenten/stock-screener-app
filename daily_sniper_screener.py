"""
Daily Sniper Screener & LINE Notification Script
Condition:
  - Universe: TSE Prime (~1,529 tickers)
  - Match Days: 50 trading days (~2.5 months)
  - Holding/Future Days: 15 trading days (~3 weeks, ratio 30%)
  - Minimum Past Return Threshold: +8.0% (all top 3 matches >= +8.0%)
  - Value Filter: PBR < 1.0
  - Win Rate Expectancy: Individual 72.65% / Basket 70.49% (Excess Alpha: +1.99%, Avg Return: +4.28%, Annualized ROI: +65.2%/yr)
"""

import os
import sys
import json
import time
import pickle
import argparse
import requests
import numpy as np
import pandas as pd
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, "tse_fundamentals_cache.json")
PRIME_TICKERS_FILE = os.path.join(BASE_DIR, "tse_prime_tickers.json")
DISK_PRICE_CACHE = os.path.join(BASE_DIR, "screener_price_cache.pkl")
DISK_CACHE_TTL = 86400 * 3  # 3 days disk cache

# LINE Credentials (from env vars or default)
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get(
    "LINE_CHANNEL_ACCESS_TOKEN",
    "+0Ql7i4RQPQM6mDsg1H679hpdIDWRU9clQ3q4XoR9Mgz3es3mhsQJOJNQKHVhVHwO4OmUeQnYxw7cCkXrqzETunIi+VrDX8P19aoBnefzQVKaBSuKDp9kb8rj+QT3rdI4VX7UjaL+K+0NfKW1FWgwQdB04t89/1O/w1cDnyilFU="
)
LINE_USER_ID = os.environ.get(
    "LINE_USER_ID",
    "U808d7431c75b1a6dded4e6be45447e27"
)

def safe_float(val):
    if val is None or pd.isna(val):
        return None
    try:
        if isinstance(val, str):
            val = val.replace(',', '').replace('%', '').replace('％', '').replace('倍', '').replace('円', '').strip()
            if val in ('---', '－', 'None', '', 'N/A'):
                return None
        return float(val)
    except (ValueError, TypeError):
        return None

def send_line_message(message_text, target_user_id=None):
    """Send LINE push message via LINE Messaging API."""
    token = LINE_CHANNEL_ACCESS_TOKEN
    user_id = target_user_id or LINE_USER_ID
    
    if not token or not user_id:
        print("[LINE] LINE_CHANNEL_ACCESS_TOKEN or LINE_USER_ID not set. Skipping push notification.")
        print(f"[LINE Message Preview]:\n{message_text}")
        return False
        
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    payload = {
        "to": user_id,
        "messages": [
            {
                "type": "text",
                "text": message_text
            }
        ]
    }
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=15)
        if res.status_code == 200:
            print(f"[LINE] Notification sent successfully to {user_id}!")
            return True
        else:
            print(f"[LINE] Failed to send notification: {res.status_code} - {res.text}")
            return False
    except Exception as e:
        print(f"[LINE] Error sending notification: {e}")
        return False

def load_tickers_and_fundamentals():
    """Load Prime tickers and fundamentals cache with name mappings."""
    tickers = []
    # 1. TSE Prime Tickers
    if os.path.exists(PRIME_TICKERS_FILE):
        with open(PRIME_TICKERS_FILE, "r", encoding="utf-8") as f:
            prime_dict = json.load(f)
            tickers = [t for t in prime_dict.keys() if t != "8303.T"]
    elif os.path.exists(os.path.join(BASE_DIR, "nikkei225_tickers.json")):
        with open(os.path.join(BASE_DIR, "nikkei225_tickers.json"), "r", encoding="utf-8") as f:
            tickers = json.load(f)
            
    # 2. Fundamentals Cache
    fund_cache = {}
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            fund_cache = json.load(f).get("data", {})
            
    # 3. Japanese Ticker Names Mapping
    jp_names = {}
    for fn in ["tse_prime_tickers.json", "tse_all_tickers.json"]:
        path = os.path.join(BASE_DIR, fn)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for k, v in data.items():
                        if isinstance(v, dict) and "name" in v:
                            jp_names[k] = v["name"]
                            jp_names[k.replace(".T", "")] = v["name"]
            except Exception:
                pass
                
    return tickers, fund_cache, jp_names

# In-memory Price Cache (30 minutes TTL)
_CACHE_TIMESTAMP = 0
_CACHED_STOCK_DATA = {}
_CACHED_STOCK_INFO = {}
CACHE_TTL = 1800  # 30 minutes

def warm_up_cache():
    """Pre-warm stock cache in background on server start."""
    try:
        tickers, fund_cache, jp_names = load_tickers_and_fundamentals()
        get_or_fetch_stock_data(tickers, fund_cache, jp_names, pbr_max=1.0)
        import gc
        gc.collect()
    except Exception as e:
        print(f"[WARMUP ERROR] {e}")

def get_or_fetch_stock_data(tickers, fund_cache, jp_names, pbr_max=1.0):
    """
    Optimized stock data fetching:
      1. Memory cache check (0s)
      2. Disk cache check (0.01s)
      3. Pre-PBR filtering: only download stocks that could qualify for PBR < pbr_max (reducing 1,500 to ~500)
      4. Parallel download with 20 workers
    """
    global _CACHE_TIMESTAMP, _CACHED_STOCK_DATA, _CACHED_STOCK_INFO
    now = time.time()
    
    # 1. Return in-memory cache if fresh
    if _CACHED_STOCK_DATA and (now - _CACHE_TIMESTAMP < CACHE_TTL):
        print(f"⚡ [MEMORY CACHE HIT] Using in-memory stock data ({len(_CACHED_STOCK_DATA)} stocks, age {int(now - _CACHE_TIMESTAMP)}s).")
        return _CACHED_STOCK_DATA, _CACHED_STOCK_INFO

    # 2. Return disk cache if available
    if os.path.exists(DISK_PRICE_CACHE):
        try:
            mtime = os.path.getmtime(DISK_PRICE_CACHE)
            with open(DISK_PRICE_CACHE, "rb") as f:
                cached = pickle.load(f)
                _CACHED_STOCK_DATA = cached['data']
                _CACHED_STOCK_INFO = cached['info']
                _CACHE_TIMESTAMP = mtime
            print(f"⚡ [DISK CACHE HIT] Loaded {len(_CACHED_STOCK_DATA)} stocks from {DISK_PRICE_CACHE} (age {int(now - mtime)}s).")
            if len(_CACHED_STOCK_DATA) >= 30:
                # Return immediately for instant zero-wait execution
                return _CACHED_STOCK_DATA, _CACHED_STOCK_INFO
        except Exception as e:
            print(f"[DISK CACHE READ ERROR] {e}")

    # 3. SPEED OPTIMIZATION: Pre-PBR Filter
    # Filter out stocks that definitely have PBR >= pbr_max in fundamentals cache
    target_tickers = []
    if pbr_max is not None and pbr_max > 0:
        for t in tickers:
            fc = fund_cache.get(t, {})
            pbr = safe_float(fc.get('pbr'))
            bps = safe_float(fc.get('bps'))
            if pbr is not None:
                if pbr < pbr_max:
                    target_tickers.append(t)
            elif bps is not None and bps > 0:
                target_tickers.append(t)
            else:
                # Include tickers without fundamental info to avoid missing candidates
                target_tickers.append(t)
        print(f"🚀 [PRE-PBR FILTER] Filtered {len(tickers)} Prime stocks down to {len(target_tickers)} candidates (PBR < {pbr_max:.1f}).")
    else:
        target_tickers = tickers

    print(f"🔄 [PARALLEL FETCH] Downloading latest 2-year prices for {len(target_tickers)} candidates (20 workers)...", flush=True)
    stock_data = {}
    stock_info = {}
    
    def fetch_stock(ticker):
        try:
            t = yf.Ticker(ticker)
            df = t.history(period="2y")
            if df is not None and not df.empty and len(df) >= 120:
                close = df['Close'].dropna()
                c_last = float(close.iloc[-1])
                
                # Check PBR
                c_data = fund_cache.get(ticker, {})
                bps = safe_float(c_data.get('bps'))
                pbr = safe_float(c_data.get('pbr'))
                jp_name = jp_names.get(ticker) or jp_names.get(ticker.replace('.T', ''))
                name = jp_name if jp_name else c_data.get('name', ticker)
                sector = c_data.get('sector', '')
                
                if (bps is None or bps <= 0) and pbr and pbr > 0:
                    bps = c_last / pbr
                    
                calc_pbr = (c_last / bps) if (bps and bps > 0) else pbr
                
                return ticker, {
                    'close': close,
                    'last_price': c_last,
                    'pbr': calc_pbr,
                    'bps': bps,
                    'name': name,
                    'sector': sector
                }
        except Exception:
            pass
        return ticker, None

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=20) as executor:
        results = executor.map(fetch_stock, target_tickers)
        for ticker, data in results:
            if data is not None:
                stock_data[ticker] = data['close']
                stock_info[ticker] = data
                
    fetch_time = time.time() - t0
    print(f"⚡ [FETCH COMPLETE] Loaded {len(stock_data)} stocks in {fetch_time:.1f}s!", flush=True)
    
    if len(stock_data) >= 30:
        _CACHED_STOCK_DATA = stock_data
        _CACHED_STOCK_INFO = stock_info
        _CACHE_TIMESTAMP = now
        # Persist to disk cache
        try:
            with open(DISK_PRICE_CACHE, "wb") as f:
                pickle.dump({'data': stock_data, 'info': stock_info}, f)
            print(f"💾 Saved {len(stock_data)} stocks to disk cache: {DISK_PRICE_CACHE}")
        except Exception as e:
            print(f"[DISK CACHE WRITE ERROR] {e}")
        
    return stock_data, stock_info

def run_sniper_screening(
    n_match=50,
    future_day=15,
    thresh=8.0,
    pbr_max=1.0,
    test_mode=False,
    target_user_id=None,
    send_push=True,
    is_interactive=False
):
    """
    Execute sniper screening:
      - Default: 50d match x 15d future x +8.0% thresh x PBR < 1.0
      - Historical Stats: Individual Win Rate 72.65%, Basket Win Rate 70.49%, Alpha +1.99%, Avg Return +4.28%
    """
    t_start = time.time()
    pbr_label = f"PBR < {pbr_max:.1f}" if (pbr_max is not None and pbr_max > 0) else "PBR制限なし"
    print("=" * 60)
    print("🎯 ZenStock Prime Sniper Screener Starting...")
    print(f"Universe: TSE Prime (~1,529) | Match: {n_match}d | Holding: {future_day}d | Thresh: +{thresh:.1f}% | {pbr_label}")
    print("=" * 60, flush=True)
    
    tickers, fund_cache, jp_names = load_tickers_and_fundamentals()
    if not tickers:
        print("[ERROR] No tickers loaded. Exiting.")
        return [], "エラー: 銘柄リストを読み込めませんでした。"
        
    # 1. Fetch or get cached stock data with pre-PBR filtering
    stock_data, stock_info = get_or_fetch_stock_data(tickers, fund_cache, jp_names, pbr_max=pbr_max)
    
    # 2. Strict PBR verification with current price
    targets = {}
    for ticker, info in stock_info.items():
        pbr = info['pbr']
        if pbr_max is not None and pbr_max > 0:
            if pbr is not None and pbr < pbr_max:
                targets[ticker] = info
        else:
            targets[ticker] = info
            
    print(f"Stocks matching {pbr_label}: {len(targets)} / {len(stock_data)}", flush=True)
    
    # 3. High-Speed Pattern Matching (NumPy vector ops)
    sniped_stocks = []
    
    for ticker, info in targets.items():
        close_series = stock_data[ticker]
        close = close_series.to_numpy(dtype=np.float32)
        total_len = len(close)
        
        if total_len < n_match + 80:
            continue
            
        target_pattern = close[-n_match:]
        t_mean = np.mean(target_pattern)
        t_std = np.std(target_pattern)
        if t_std < 1e-6 or np.isnan(t_std):
            continue
        target_norm = (target_pattern - t_mean) / t_std
        
        search_end = total_len - n_match - future_day - 5
        if search_end < n_match + 20:
            continue
            
        past_data = close[:search_end]
        windows = np.lib.stride_tricks.sliding_window_view(past_data, window_shape=n_match)
        w_means = np.mean(windows, axis=1, keepdims=True)
        w_stds = np.std(windows, axis=1, keepdims=True)
        valid_mask = (w_stds[:, 0] > 1e-6) & (~np.isnan(w_stds[:, 0]))
        if not np.any(valid_mask):
            continue
            
        w_norm = np.zeros_like(windows)
        w_norm[valid_mask] = (windows[valid_mask] - w_means[valid_mask]) / w_stds[valid_mask]
        dots = np.dot(w_norm, target_norm) / n_match
        dots[~valid_mask] = -1.0
        
        sorted_indices = np.argsort(dots)[::-1]
        chosen_top = []
        min_dist = max(20, n_match // 2)
        for idx in sorted_indices:
            if dots[idx] < 0.5:
                break
            if all(abs(idx - c) >= min_dist for c in chosen_top):
                chosen_top.append(idx)
                if len(chosen_top) == 3:
                    break
                    
        if len(chosen_top) == 3:
            p_rets = []
            match_details = []
            for c_idx in chosen_top:
                p_end = c_idx + n_match - 1
                p_fut = p_end + future_day
                sim_score = float(dots[c_idx]) * 100.0
                if p_fut < len(close):
                    ret = (close[p_fut] - close[p_end]) / close[p_end] * 100.0
                    p_rets.append(ret)
                    date_end = close_series.index[p_end].strftime('%Y/%m/%d')
                    match_details.append({
                        'date': date_end,
                        'ret': ret,
                        'sim': sim_score
                    })
                else:
                    p_rets.append(-999.0)
                    
            if len(p_rets) == 3 and all(r > -900 for r in p_rets):
                min_ret = min(p_rets)
                avg_ret = float(np.mean(p_rets))
                
                # SNIPER HIT CONDITION: All 3 matches had >= thresh return
                if min_ret >= thresh:
                    sniped_stocks.append({
                        'ticker': ticker,
                        'name': info['name'],
                        'sector': info['sector'],
                        'last_price': info['last_price'],
                        'pbr': info['pbr'],
                        'min_ret': min_ret,
                        'avg_ret': avg_ret,
                        'matches': match_details
                    })

    total_time = time.time() - t_start
    print(f"\n⚡ [SCAN COMPLETE in {total_time:.2f}s] Hit Stocks: {len(sniped_stocks)}")
    
    # 4. Process Notification
    result_message = ""
    if sniped_stocks:
        print(f"🔥 {len(sniped_stocks)} STOCKS TRIGGERED SNIPER CRITERIA! 🔥")
        for s in sniped_stocks:
            pbr_disp = f"{s['pbr']:.2f}倍" if s['pbr'] is not None else "---"
            print(f"  - {s['ticker']} {s['name']}: PBR {pbr_disp}, 過去3回最小+{s['min_ret']:.1f}%")
            
        # Compose LINE Message
        msg = "【重要】\n\n"
        msg += "スクリーニングにヒットする銘柄が見つかりました！\n"
        msg += "（東証プライム全域・勝率72.7%スナイパー条件）\n"
        msg += "━━━━━━━━━━━━━━\n"
        for s in sniped_stocks:
            ticker_str = s['ticker'] if '.T' in s['ticker'] else f"{s['ticker']}.T"
            pbr_disp = f"{s['pbr']:.2f}倍" if s['pbr'] is not None else "---"
            price = s.get('last_price')
            if price is not None:
                price_str = f"{price:,.1f}円" if (price < 1000 and price != int(price)) else f"{int(round(price)):,}円"
            else:
                price_str = "---"
            msg += f"【銘柄】{s['name']}（{ticker_str}）\n"
            msg += f"【株価】{price_str}\n"
            msg += f"【PBR】{pbr_disp}\n"
            msg += f"【過去3回上昇】最小+{s['min_ret']:.1f}%（平均+{s['avg_ret']:.1f}%）\n"
            msg += "━━━━━━━━━━━━━━\n"
        msg += f"💡 戦略条件:\n"
        msg += f"・照合期間: {n_match}日（約2.5ヶ月）\n"
        msg += f"・保有期間: {future_day}日（約3週間）\n"
        msg += f"・過去5年実績: 個別勝率72.7% / バスケ70.5% / 超過α+1.99% / 利益+4.28%\n"
        result_message = msg.strip()
        
        if send_push:
            send_line_message(result_message, target_user_id=target_user_id)
    else:
        print(f"No stocks triggered sniper criteria today. (Condition: {pbr_label} & Min Past Return >= +{thresh:.1f}%)")
        if is_interactive:
            result_message = f"【ZenStock スキャナー結果】\n━━━━━━━━━━━━━━\n"
            result_message += f"設定条件:\n"
            result_message += f"・照合期間: {n_match}日（約2.5ヶ月）\n"
            result_message += f"・保有期間: {future_day}日（約3週間）\n"
            result_message += f"・上昇閾値: +{thresh:.1f}%\n"
            result_message += f"・PBR条件: {pbr_label}\n"
            result_message += f"・過去5年実績: 個別勝率72.7% / 超過α+1.99%\n"
            result_message += "━━━━━━━━━━━━━━\n"
            result_message += "本日、上記条件に合致する銘柄はありませんでした。"
            if send_push:
                send_line_message(result_message, target_user_id=target_user_id)
        elif test_mode:
            result_message = "🎯【ZenStock プライムスナイパー通知テスト】\n"
            result_message += "LINE Messaging APIの接続テストに成功しました！\n"
            result_message += f"本日のスクリーニング（東証プライム全社・照合{n_match}日×保有{future_day}日×+{thresh:.1f}%×{pbr_label}）では該当銘柄はありませんでした。\n\n"
            result_message += "次回、条件を満たす勝率72.7%の神シグナル銘柄が出現した瞬間に自動通知されます。"
            if send_push:
                send_line_message(result_message, target_user_id=target_user_id)

    import gc
    gc.collect()

    return sniped_stocks, result_message

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ZenStock Daily Sniper Screener")
    parser.add_argument("--test", action="store_true", help="Send a test LINE message even if no hits")
    parser.add_argument("--match", type=int, default=50, help="Match window in days (default: 50)")
    parser.add_argument("--hold", type=int, default=15, help="Holding window in days (default: 15)")
    parser.add_argument("--thresh", type=float, default=8.0, help="Min return threshold (default: 8.0)")
    parser.add_argument("--pbr", type=float, default=1.0, help="Max PBR threshold (0 for no limit, default: 1.0)")
    parser.add_argument("--user", type=str, default=None, help="Target LINE User ID (default: LINE_USER_ID)")
    parser.add_argument("--interactive", action="store_true", help="Notify user even if 0 hits (for on-demand scans)")
    args = parser.parse_args()
    
    pbr_arg = None if args.pbr <= 0 else args.pbr
    run_sniper_screening(
        n_match=args.match,
        future_day=args.hold,
        thresh=args.thresh,
        pbr_max=pbr_arg,
        test_mode=args.test,
        target_user_id=args.user,
        send_push=True,
        is_interactive=args.interactive
    )
