"""
Daily Sniper Screener & LINE Notification Script
Condition:
  - Universe: TSE Prime (~1,529 tickers)
  - Match Days: 80 trading days (~4.0 months)
  - Holding/Future Days: 15 trading days (~3 weeks)
  - Minimum Past Return Threshold: +7.0%
  - Value Filter: PBR < 1.0
  - Win Rate Expectancy: Individual 60.2% / PF 2.83 / Avg Return +2.53%
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

try:
    import dtw_engine
except ImportError:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    import dtw_engine

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
_CACHED_DATES = []
CACHE_TTL = 1800  # 30 minutes

def is_cache_fresh(stock_data: dict) -> bool:
    """Check if cached stock data includes recent market date (not stale)."""
    global _CACHED_DATES
    if not stock_data or len(stock_data) < 30:
        return False
    try:
        latest_date = None
        if _CACHED_DATES and len(_CACHED_DATES) > 0:
            latest_date = pd.to_datetime(_CACHED_DATES[-1]).date()
        else:
            sample_key = next(iter(stock_data))
            series = stock_data[sample_key]
            if series is None or len(series) == 0:
                return False
            if hasattr(series, 'index'):
                latest_dt = series.index[-1]
                latest_date = latest_dt.date() if hasattr(latest_dt, 'date') else pd.to_datetime(latest_dt).date()
            else:
                return True
                
        if not latest_date:
            return True
            
        import datetime
        now_dt = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
        now_jst = now_dt.date()
        diff_days = (now_jst - latest_date).days
        weekday = now_jst.weekday()
        
        # 1. Monday (0) accepts Friday (3 days gap). Thursday (4 days) is strictly STALE.
        # 2. Tuesday (1) accepts Monday (1 day gap) or Friday (4 days gap if Monday was holiday or market not closed).
        # 3. Sunday (6) accepts Friday (2 days gap).
        # 4. Saturday (5) accepts Friday (1 day gap).
        # 5. Wed-Fri (2-4) accepts yesterday (1 day gap) or 2 days for mid-week holidays.
        if weekday == 0:
            allowed_gap = 3
        elif weekday == 1:
            allowed_gap = 4
        elif weekday == 6:
            allowed_gap = 2
        elif weekday == 5:
            allowed_gap = 1
        else:
            allowed_gap = 2
        
        is_fresh = diff_days <= allowed_gap
        if not is_fresh:
            print(f"⚠️ [STALE CACHE DETECTED] Cache latest date is {latest_date} (today is {now_jst}, gap={diff_days}d > allowed={allowed_gap}d). Refresh required.")
        return is_fresh
    except Exception as e:
        print(f"⚠️ [CACHE FRESHNESS CHECK ERROR] {e}")
        return False

def warm_up_cache(force=False):
    """Pre-warm and refresh stock cache in background on server start or scheduled routine."""
    try:
        tickers, fund_cache, jp_names = load_tickers_and_fundamentals()
        get_or_fetch_stock_data(tickers, fund_cache, jp_names, pbr_max=1.0, force_refresh=force)
        import gc
        gc.collect()
    except Exception as e:
        print(f"[WARMUP ERROR] {e}")

def get_or_fetch_stock_data(tickers, fund_cache, jp_names, pbr_max=1.0, force_refresh=False):
    """
    Optimized stock data fetching with freshness validation:
      1. Memory cache check (only if fresh and not force_refresh)
      2. Disk cache check (only if market date is fresh and not force_refresh)
      3. Auto-download latest prices via parallel yfinance if cache is stale or missing
    """
    global _CACHE_TIMESTAMP, _CACHED_STOCK_DATA, _CACHED_STOCK_INFO, _CACHED_DATES
    now = time.time()
    
    # 1. Return in-memory cache if fresh & market date is current
    if not force_refresh and _CACHED_STOCK_DATA and (now - _CACHE_TIMESTAMP < CACHE_TTL):
        if is_cache_fresh(_CACHED_STOCK_DATA):
            print(f"⚡ [MEMORY CACHE HIT] Using fresh in-memory stock data ({len(_CACHED_STOCK_DATA)} stocks).")
            return _CACHED_STOCK_DATA, _CACHED_STOCK_INFO
        else:
            print("🔄 [MEMORY CACHE STALE] In-memory cache is outdated. Proceeding to disk/fresh fetch...")

    # 2. Return disk cache if available AND fresh
    if not force_refresh and os.path.exists(DISK_PRICE_CACHE):
        try:
            mtime = os.path.getmtime(DISK_PRICE_CACHE)
            with open(DISK_PRICE_CACHE, "rb") as f:
                cached = pickle.load(f)
                d_data = cached.get('data', {})
                d_info = cached.get('info', {})
                _CACHED_DATES = cached.get('dates', [])
                
            if len(d_data) >= 30 and is_cache_fresh(d_data):
                _CACHED_STOCK_DATA = d_data
                _CACHED_STOCK_INFO = d_info
                _CACHE_TIMESTAMP = mtime
                latest_d = _CACHED_DATES[-1] if _CACHED_DATES else "最新"
                print(f"⚡ [DISK CACHE HIT] Loaded {len(_CACHED_STOCK_DATA)} stocks from disk cache (latest date: {latest_d}).")
                return _CACHED_STOCK_DATA, _CACHED_STOCK_INFO
            else:
                print("🔄 [DISK CACHE STALE] Disk cache contains outdated market date. Triggering fresh download...")
        except Exception as e:
            print(f"[DISK CACHE READ ERROR] {e}")

    # 3. SPEED OPTIMIZATION: Pre-PBR Filter
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
                target_tickers.append(t)
        print(f"🚀 [PRE-PBR FILTER] Filtered {len(tickers)} Prime stocks down to {len(target_tickers)} candidates (PBR < {pbr_max:.1f}).")
    else:
        target_tickers = tickers

    print(f"🔄 [PARALLEL FETCH] Downloading latest prices for {len(target_tickers)} candidates (25 workers)...", flush=True)
    stock_data = {}
    stock_info = {}
    
    def fetch_stock(ticker):
        try:
            t = yf.Ticker(ticker)
            df = t.history(period="5y")
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
    with ThreadPoolExecutor(max_workers=25) as executor:
        results = executor.map(fetch_stock, target_tickers)
        for ticker, data in results:
            if data is not None:
                stock_data[ticker] = data['close']
                stock_info[ticker] = data
                
    fetch_time = time.time() - t0
    print(f"⚡ [FETCH COMPLETE] Loaded {len(stock_data)} stocks in {fetch_time:.1f}s!", flush=True)
    
    if len(stock_data) >= 30:
        dates_list = []
        try:
            sample_k = next(iter(stock_data))
            sample_s = stock_data[sample_k]
            if hasattr(sample_s, 'index'):
                dates_list = sample_s.index.strftime('%Y/%m/%d').tolist()
        except Exception:
            pass
            
        compact_data = {}
        for k, v in stock_data.items():
            if hasattr(v, 'to_numpy'):
                compact_data[k] = v.to_numpy(dtype=np.float32)
            else:
                compact_data[k] = np.array(v, dtype=np.float32)

        for k, inf in stock_info.items():
            if 'close' in inf:
                del inf['close']

        _CACHED_DATES = dates_list
        _CACHED_STOCK_DATA = compact_data
        _CACHED_STOCK_INFO = stock_info
        _CACHE_TIMESTAMP = now
        # Persist to disk cache (compact float32 format: ~3MB)
        try:
            with open(DISK_PRICE_CACHE, "wb") as f:
                pickle.dump({'data': compact_data, 'info': stock_info, 'dates': dates_list}, f, protocol=pickle.HIGHEST_PROTOCOL)
            print(f"💾 Saved {len(compact_data)} stocks to disk cache: {DISK_PRICE_CACHE} (compact float32 format, {len(dates_list)} days)")
        except Exception as e:
            print(f"[DISK CACHE WRITE ERROR] {e}")
        
    return stock_data, stock_info

def scan_target_patterns(
    targets,
    stock_data,
    n_match,
    future_day,
    thresh,
    strategy_key="main",
    strategy_name="本命スイング",
    use_dtw=True,
    dtw_window=5,
    latest_market_date="---"
):
    """Scan targets with specific pattern matching window and threshold."""
    global _CACHED_DATES
    matched_stocks = []
    
    for ticker, info in targets.items():
        raw_close = stock_data[ticker]
        close = raw_close if isinstance(raw_close, np.ndarray) else (raw_close.to_numpy(dtype=np.float32) if hasattr(raw_close, 'to_numpy') else np.array(raw_close, dtype=np.float32))
        total_len = len(close)
        
        if total_len < n_match + 80:
            continue

        # 移動平均健全トレンドフィルター
        if total_len >= 200:
            sma_200 = float(np.mean(close[-200:]))
            sma_25 = float(np.mean(close[-25:]))
            cur_price = float(close[-1])
            if cur_price < sma_200:
                continue
            if cur_price > sma_200 * 1.25:
                continue
            if cur_price < sma_25 * 0.96:
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
        
        if use_dtw:
            top_cand_indices = np.argsort(dots)[::-1][:60]
            cand_windows = w_norm[top_cand_indices]
            dtw_dists = dtw_engine.compute_fast_dtw_distances(target_norm, cand_windows, window_radius=dtw_window)
            dtw_sorted = np.argsort(dtw_dists)
            sorted_indices = [top_cand_indices[i] for i in dtw_sorted]
            sim_scores = {top_cand_indices[i]: float(np.clip(100.0 * (1.0 - dtw_dists[i] / 2.0), 0.0, 100.0)) for i in range(len(top_cand_indices))}
        else:
            sorted_indices = np.argsort(dots)[::-1]
            sim_scores = {idx: float(dots[idx]) * 100.0 for idx in sorted_indices}
        
        chosen_top = []
        min_dist = max(15, n_match // 2)
        for idx in sorted_indices:
            if not use_dtw and dots[idx] < 0.45:
                break
            if all(abs(idx - c) >= min_dist for c in chosen_top):
                chosen_top.append(idx)
                if len(chosen_top) == 5:
                    break
                    
        if len(chosen_top) >= 4:
            p_rets = []
            match_details = []
            for c_idx in chosen_top:
                p_end = c_idx + n_match - 1
                p_fut = p_end + future_day
                sim_score = sim_scores.get(c_idx, float(dots[c_idx]) * 100.0)
                if p_fut < len(close):
                    ret = (close[p_fut] - close[p_end]) / close[p_end] * 100.0
                    p_rets.append(ret)
                    if _CACHED_DATES and p_end < len(_CACHED_DATES):
                        date_end = _CACHED_DATES[p_end]
                    elif hasattr(raw_close, 'index'):
                        date_end = raw_close.index[p_end].strftime('%Y/%m/%d')
                    else:
                        date_end = "---"
                    match_details.append({
                        'date': date_end,
                        'ret': ret,
                        'sim': sim_score
                    })
                else:
                    p_rets.append(-999.0)
                    
            valid_rets = [r for r in p_rets if r > -900]
            if len(valid_rets) >= 4:
                win_count = sum(1 for r in valid_rets if r > 0.0)
                win_rate = (win_count / len(valid_rets)) * 100.0
                min_ret = min(valid_rets)
                avg_ret = float(np.mean(valid_rets))
                
                req_avg = max(5.0 if future_day <= 5 else 6.0, thresh * 0.70)
                if win_rate >= 80.0 and avg_ret >= req_avg and min_ret >= -2.0:
                    matched_stocks.append({
                        'ticker': ticker,
                        'name': info['name'],
                        'sector': info['sector'],
                        'last_price': info['last_price'],
                        'pbr': info['pbr'],
                        'win_rate': win_rate,
                        'win_count': win_count,
                        'sample_count': len(valid_rets),
                        'min_ret': min_ret,
                        'avg_ret': avg_ret,
                        'market_date': latest_market_date,
                        'strategy_key': strategy_key,
                        'strategy_name': strategy_name,
                        'hold_days': future_day,
                        'match_days': n_match,
                        'thresh': thresh,
                        'matches': match_details
                    })
    return matched_stocks

def build_dual_sniper_line_message(short_hits, main_hits, latest_market_date="---"):
    """Compose structured LINE push message containing both 50d5d8% and 80d15d7%."""
    msg = "🎯【超高勝率スナイプ警報（黄金デュアルスキャン）】\n"
    msg += "東証プライム・PBR1.0倍割れ・DTW動的時間伸縮判定\n\n"
    
    # Section 1: 超短期スナイパー (50d / 5d / +8.0%)
    msg += "⚡【超短期スナイパー (50d/5d/+8.0%・PF 3.01)】\n"
    msg += "※ 5営業日保有・最速の資本回転・全165設定中PF第1位\n"
    msg += "━━━━━━━━━━━━━━\n"
    if short_hits:
        for s in short_hits:
            ticker_str = s['ticker'] if '.T' in s['ticker'] else f"{s['ticker']}.T"
            pbr_disp = f"{s['pbr']:.2f}倍" if s.get('pbr') is not None else "---"
            price = s.get('last_price')
            if price is not None:
                price_str = f"{price:,.1f}円" if (price < 1000 and price != int(price)) else f"{int(round(price)):,}円"
            else:
                price_str = "---"
            msg += f"【銘柄】{s['name']}（{ticker_str}）\n"
            msg += f"【株価】{price_str}（PBR {pbr_disp}）\n"
            msg += f"【過去検証】類似{s['sample_count']}局面中{s['win_count']}回上昇（勝率{s['win_rate']:.0f}%・平均+{s['avg_ret']:.1f}%）\n"
            msg += f"【推奨エグジット】\n"
            msg += f"  ・利確目安: +4.0% 〜 +6.0%（5営業日以内でスピード利確）\n"
            msg += f"  ・損切りライン: -4.5% 到達で即時撤退（下落遮断）\n"
            msg += "──────────────────\n"
    else:
        msg += "本日、超短期スナイプ条件に該当する銘柄はありませんでした。\n"
        msg += "━━━━━━━━━━━━━━\n"
        
    msg += "\n"
    
    # Section 2: 本命スイング (80d / 15d / +7.0%)
    msg += "🏆【本命スイング (80d/15d/+7.0%・PF 2.83)】\n"
    msg += "※ 15営業日保有・中期底打ちからの本格リバウンド（本命安定型）\n"
    msg += "━━━━━━━━━━━━━━\n"
    if main_hits:
        for s in main_hits:
            ticker_str = s['ticker'] if '.T' in s['ticker'] else f"{s['ticker']}.T"
            pbr_disp = f"{s['pbr']:.2f}倍" if s.get('pbr') is not None else "---"
            price = s.get('last_price')
            if price is not None:
                price_str = f"{price:,.1f}円" if (price < 1000 and price != int(price)) else f"{int(round(price)):,}円"
            else:
                price_str = "---"
            msg += f"【銘柄】{s['name']}（{ticker_str}）\n"
            msg += f"【株価】{price_str}（PBR {pbr_disp}）\n"
            msg += f"【過去検証】類似{s['sample_count']}局面中{s['win_count']}回上昇（勝率{s['win_rate']:.0f}%・平均+{s['avg_ret']:.1f}%）\n"
            msg += f"【推奨エグジット】\n"
            msg += f"  ・利確目安: +4.0% 〜 +7.0%（15営業日保有）\n"
            msg += f"  ・損切りライン: -4.5% 到達で即時撤退（下落遮断）\n"
            msg += "──────────────────\n"
    else:
        msg += "本日、本命スイング条件に該当する銘柄はありませんでした。\n"
        msg += "━━━━━━━━━━━━━━\n"
        
    msg += "\n💡 戦略条件概要:\n"
    msg += f"・データ基準日: {latest_market_date}\n"
    msg += "・⚡ 超短期: 照合50日 × 保有5日 × +8.0% (勝率60.0% / PF 3.01)\n"
    msg += "・🏆 本命: 照合80日 × 保有15日 × +7.0% (勝率60.2% / PF 2.83)\n"
    msg += "・全銘柄共通: 徹底した -4.5% 逆指値損切り運用\n"
    return msg.strip()

def run_sniper_screening(
    n_match=80,
    future_day=15,
    thresh=7.0,
    pbr_max=1.0,
    test_mode=False,
    target_user_id=None,
    send_push=True,
    is_interactive=False,
    force_refresh=False,
    use_dtw=True,
    dtw_window=5,
    dual_mode=True
):
    """
    Execute sniper screening.
    When dual_mode is True, runs both:
      1. 超短期スナイパー (50d / 5d / +8.0%・PF 3.01)
      2. 本命スイング (80d / 15d / +7.0%・PF 2.83)
    """
    global _CACHED_DATES
    t_start = time.time()
    pbr_label = f"PBR < {pbr_max:.1f}" if (pbr_max is not None and pbr_max > 0) else "PBR制限なし"
    print("=" * 60)
    print("🎯 ZenStock Prime Sniper Screener Starting...")
    if dual_mode:
        print(f"Mode: DUAL SNIPER [50d/5d/+8.0% (PF 3.01) & 80d/15d/+7.0% (PF 2.83)] | {pbr_label}")
    else:
        print(f"Universe: TSE Prime (~1,529) | Match: {n_match}d | Holding: {future_day}d | Thresh: +{thresh:.1f}% | {pbr_label}")
    print("=" * 60, flush=True)
    
    tickers, fund_cache, jp_names = load_tickers_and_fundamentals()
    if not tickers:
        print("[ERROR] No tickers loaded. Exiting.")
        return [], "エラー: 銘柄リストを読み込めませんでした。"
        
    stock_data, stock_info = get_or_fetch_stock_data(tickers, fund_cache, jp_names, pbr_max=pbr_max, force_refresh=force_refresh)
    
    latest_market_date = "---"
    if stock_data:
        try:
            sample_series = next(iter(stock_data.values()))
            latest_market_date = sample_series.index[-1].strftime('%Y/%m/%d')
        except Exception:
            pass
            
    targets = {}
    for ticker, info in stock_info.items():
        pbr = info['pbr']
        if pbr_max is not None and pbr_max > 0:
            if pbr is not None and pbr < pbr_max:
                targets[ticker] = info
        else:
            targets[ticker] = info
            
    print(f"Stocks matching {pbr_label}: {len(targets)} / {len(stock_data)}", flush=True)
    
    if dual_mode:
        short_hits = scan_target_patterns(
            targets, stock_data,
            n_match=50, future_day=5, thresh=8.0,
            strategy_key="short", strategy_name="超短期スナイパー (50d/5d/+8%)",
            use_dtw=use_dtw, dtw_window=dtw_window, latest_market_date=latest_market_date
        )
        main_hits = scan_target_patterns(
            targets, stock_data,
            n_match=80, future_day=15, thresh=7.0,
            strategy_key="main", strategy_name="本命スイング (80d/15d/+7%)",
            use_dtw=use_dtw, dtw_window=dtw_window, latest_market_date=latest_market_date
        )
        sniped_stocks = short_hits + main_hits
    else:
        sniped_stocks = scan_target_patterns(
            targets, stock_data,
            n_match=n_match, future_day=future_day, thresh=thresh,
            strategy_key="single", strategy_name=f"カスタム ({n_match}d/{future_day}d/+{thresh:.1f}%)",
            use_dtw=use_dtw, dtw_window=dtw_window, latest_market_date=latest_market_date
        )
        short_hits = [s for s in sniped_stocks if s.get('hold_days', future_day) <= 5]
        main_hits = [s for s in sniped_stocks if s.get('hold_days', future_day) > 5]

    total_time = time.time() - t_start
    print(f"\n⚡ [SCAN COMPLETE in {total_time:.2f}s] Hit Stocks: {len(sniped_stocks)} (Short: {len(short_hits)}, Main: {len(main_hits)})")
    
    result_message = ""
    if sniped_stocks:
        print(f"🔥 {len(sniped_stocks)} STOCKS TRIGGERED SNIPER CRITERIA! 🔥")
        for s in sniped_stocks:
            pbr_disp = f"{s['pbr']:.2f}倍" if s['pbr'] is not None else "---"
            print(f"  [{s['strategy_name']}] {s['ticker']} {s['name']}: PBR {pbr_disp}, 類似{s['sample_count']}戦{s['win_count']}勝 (勝率{s['win_rate']:.0f}%, 平均+{s['avg_ret']:.1f}%)")
            
        if dual_mode:
            result_message = build_dual_sniper_line_message(short_hits, main_hits, latest_market_date=latest_market_date)
        else:
            msg = f"🎯【超高勝率スナイプ警報】\n\n"
            msg += f"設定条件（{n_match}d/{future_day}d/+{thresh:.1f}%）のスナイプ銘柄を検知しました！\n"
            msg += "（東証プライム・PBR1.0倍割れ・DTW動的時間伸縮判定）\n"
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
                msg += f"【株価】{price_str}（PBR {pbr_disp}）\n"
                msg += f"【過去検証】類似{s['sample_count']}局面中{s['win_count']}回上昇（勝率{s['win_rate']:.0f}%・平均+{s['avg_ret']:.1f}%）\n"
                msg += f"【推奨エグジット】\n"
                msg += f"  ・利確目安: +4.0% 〜 +7.0% で指値利確\n"
                msg += f"  ・損切りライン: -4.5% 到達で即時撤退\n"
                msg += "━━━━━━━━━━━━━━\n"
            msg += f"💡 戦略条件: 照合{n_match}日 × 保有{future_day}日 × 上昇+{thresh:.1f}% | 損切り-4.5%\n"
            result_message = msg.strip()
            
        if send_push:
            send_line_message(result_message, target_user_id=target_user_id)
    else:
        print(f"No stocks triggered sniper criteria today.")
        if is_interactive or test_mode:
            result_message = (
                f"🎯【ZenStock スナイパー検知通知】\n━━━━━━━━━━━━━━\n"
                f"データ基準日: {latest_market_date}\n"
                f"本日のスクリーニング（東証プライム全社対象）では、厳格な条件を満たす銘柄はありませんでした。\n\n"
                f"・⚡ 超短期スナイパー (50d/5d/+8.0%・PF 3.01): 0件\n"
                f"・🏆 本命スイング (80d/15d/+7.0%・PF 2.83): 0件\n"
                f"━━━━━━━━━━━━━━\n"
                f"※ 騙しを回避するため、黄金基準を満たした日のみエントリーシグナルをお届けします。"
            )
            if send_push:
                send_line_message(result_message, target_user_id=target_user_id)

    import gc
    gc.collect()

    return sniped_stocks, result_message

    import gc
    gc.collect()

    return sniped_stocks, result_message

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ZenStock Daily Sniper Screener")
    parser.add_argument("--test", action="store_true", help="Send a test LINE message even if no hits")
    parser.add_argument("--match", type=int, default=80, help="Match window in days (default: 80)")
    parser.add_argument("--hold", type=int, default=15, help="Holding window in days (default: 15)")
    parser.add_argument("--thresh", type=float, default=7.0, help="Min return threshold (default: 7.0)")
    parser.add_argument("--pbr", type=float, default=1.0, help="Max PBR threshold (0 for no limit, default: 1.0)")
    parser.add_argument("--user", type=str, default=None, help="Target LINE User ID (default: LINE_USER_ID)")
    parser.add_argument("--interactive", action="store_true", help="Notify user even if 0 hits (for on-demand scans)")
    parser.add_argument("--refresh-cache", action="store_true", help="Refresh price cache and auto-sync to Render")
    parser.add_argument("--single", action="store_true", help="Run single strategy instead of dual mode")
    args = parser.parse_args()
    
    if args.refresh_cache:
        from cache_sync import refresh_sniper_price_cache
        ok, msg = refresh_sniper_price_cache(pbr_max=args.pbr if args.pbr > 0 else 1.0, sync_to_render=True)
        print(f"[RESULT] {msg}")
        sys.exit(0 if ok else 1)
        
    pbr_arg = None if args.pbr <= 0 else args.pbr
    use_dual = not args.single and (args.match == 80 and args.hold == 15 and args.thresh == 7.0)
    
    run_sniper_screening(
        n_match=args.match,
        future_day=args.hold,
        thresh=args.thresh,
        pbr_max=pbr_arg,
        test_mode=args.test,
        target_user_id=args.user,
        send_push=True,
        is_interactive=args.interactive,
        dual_mode=use_dual
    )
