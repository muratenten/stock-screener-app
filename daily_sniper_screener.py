"""
Daily Sniper Screener & LINE Notification Script
Condition:
  - Match Days: 60 trading days
  - Holding/Future Days: 25 trading days
  - Minimum Past Return Threshold: +10.0% (all top 3 matches >= +10.0%)
  - Value Filter: PBR < 1.0
  - Win Rate Expectancy: 80.0% (Historical Avg Return: +9.37%, Excess Alpha: +7.04%)
"""

import os
import sys
import json
import time
import argparse
import requests
import numpy as np
import pandas as pd
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, "tse_fundamentals_cache.json")
TICKERS_FILE = "/Users/muraten/.gemini/antigravity-cli/brain/e0656f6c-60da-4e2b-a2b3-251df6f2c3d5/scratch/nikkei225_tickers.json"

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

def send_line_message(message_text):
    """Send LINE push message via LINE Messaging API."""
    token = LINE_CHANNEL_ACCESS_TOKEN
    user_id = LINE_USER_ID
    
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
            print("[LINE] Notification sent successfully!")
            return True
        else:
            print(f"[LINE] Failed to send notification: {res.status_code} - {res.text}")
            return False
    except Exception as e:
        print(f"[LINE] Error sending notification: {e}")
        return False

def load_tickers_and_fundamentals():
    tickers = []
    # 1. Try local scratch tickers or app dir
    if os.path.exists(TICKERS_FILE):
        with open(TICKERS_FILE, "r", encoding="utf-8") as f:
            tickers = json.load(f)
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

def run_sniper_screening(test_mode=False):
    print("=" * 60)
    print("🎯 ZenStock Daily Sniper Screener Starting...")
    print("Target: Nikkei 225 | Match: 60d | Holding: 25d | Thresh: +10.0% | PBR < 1.0")
    print("=" * 60, flush=True)
    
    tickers, fund_cache, jp_names = load_tickers_and_fundamentals()
    if not tickers:
        print("[ERROR] No tickers loaded. Exiting.")
        return
        
    print(f"Loaded {len(tickers)} tickers and fundamentals cache.")
    
    # 1. Parallel download price history (5 years)
    stock_data = {}
    stock_info = {}
    
    def fetch_stock(ticker):
        try:
            t = yf.Ticker(ticker)
            df = t.history(period="5y")
            if df is not None and not df.empty and len(df) >= 200:
                close = df['Close'].dropna()
                c_last = float(close.iloc[-1])
                
                # Check PBR
                c_data = fund_cache.get(ticker, {})
                bps = safe_float(c_data.get('bps'))
                pbr = safe_float(c_data.get('pbr'))
                # Check Japanese Name
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

    print(f"Fetching latest price and fundamental data for {len(tickers)} stocks...", flush=True)
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=20) as executor:
        results = executor.map(fetch_stock, tickers)
        for ticker, data in results:
            if data is not None:
                stock_data[ticker] = data['close']
                stock_info[ticker] = data
                
    print(f"Loaded {len(stock_data)} valid stocks in {time.time()-t0:.1f}s.", flush=True)
    
    # 2. Filter PBR < 1.0
    pbr_targets = {}
    for ticker, info in stock_info.items():
        pbr = info['pbr']
        if pbr is not None and pbr < 1.0:
            pbr_targets[ticker] = info
            
    print(f"Stocks matching PBR < 1.0 filter: {len(pbr_targets)} / {len(stock_data)}", flush=True)
    
    # 3. Pattern Matching (Match 60d, Thresh +10.0%, Future 25d)
    N_match = 60
    future_day = 25
    thresh = 10.0
    
    sniped_stocks = []
    
    for ticker, info in pbr_targets.items():
        close_series = stock_data[ticker]
        close = close_series.to_numpy(dtype=np.float32)
        total_len = len(close)
        
        if total_len < N_match + 100:
            continue
            
        # Target pattern is the most recent 60 trading days
        target_pattern = close[-N_match:]
        t_mean = np.mean(target_pattern)
        t_std = np.std(target_pattern)
        if t_std < 1e-6 or np.isnan(t_std):
            continue
        target_norm = (target_pattern - t_mean) / t_std
        
        # Historical search space: up to (last - future_day - 5)
        search_end = total_len - N_match - future_day - 5
        if search_end < N_match + 30:
            continue
            
        past_data = close[:search_end]
        windows = np.lib.stride_tricks.sliding_window_view(past_data, window_shape=N_match)
        w_means = np.mean(windows, axis=1, keepdims=True)
        w_stds = np.std(windows, axis=1, keepdims=True)
        valid_mask = (w_stds[:, 0] > 1e-6) & (~np.isnan(w_stds[:, 0]))
        if not np.any(valid_mask):
            continue
            
        w_norm = np.zeros_like(windows)
        w_norm[valid_mask] = (windows[valid_mask] - w_means[valid_mask]) / w_stds[valid_mask]
        dots = np.dot(w_norm, target_norm) / N_match
        dots[~valid_mask] = -1.0
        
        sorted_indices = np.argsort(dots)[::-1]
        chosen_top = []
        min_dist = max(20, N_match // 2)
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
                p_end = c_idx + N_match - 1
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
                
                # SNIPER HIT CONDITION: All 3 matches had >= +10.0% return
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

    print(f"\n[SCAN COMPLETE] Hit Stocks: {len(sniped_stocks)}")
    
    # 4. Process Notification
    if sniped_stocks:
        print(f"🔥 {len(sniped_stocks)} STOCKS TRIGGERED SNIPER CRITERIA! 🔥")
        for s in sniped_stocks:
            print(f"  - {s['ticker']} {s['name']}: PBR {s['pbr']:.2f}倍, 過去3回最小+{s['min_ret']:.1f}%")
            
        # Compose LINE Message (⚠️重要⚠️ + スクリーニングにヒット + 区切り線 + 銘柄名（コード.T） + PBR)
        msg = "⚠️重要⚠️\n\n"
        msg += "スクリーニングにヒットする銘柄が見つかりました！\n"
        msg += "━━━━━━━━━━━━━━\n"
        for s in sniped_stocks:
            ticker_str = s['ticker'] if '.T' in s['ticker'] else f"{s['ticker']}.T"
            msg += f"【銘柄】{s['name']}（{ticker_str}）\n"
            msg += f"【PBR】{s['pbr']:.2f}倍\n"
            msg += "━━━━━━━━━━━━━━\n"
        msg = msg.strip()
        
        send_line_message(msg)
    else:
        print("No stocks triggered sniper criteria today. (Condition: PBR < 1.0 & Min Past Return >= +10.0%)")
        if test_mode:
            test_msg = "🎯【ZenStock スナイパー通知テスト】\n"
            test_msg += "LINE Messaging APIの接続テストに成功しました！\n"
            test_msg += "本日のスクリーニングではスナイプ条件（照合60日×保有25日×+10%×PBR<1.0）の該当銘柄はありませんでした。\n\n"
            test_msg += "次回、条件を満たす激熱銘柄（勝率80%・平均利益+9.4%）が出現した瞬間に自動通知されます。"
            send_line_message(test_msg)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ZenStock Daily Sniper Screener")
    parser.add_argument("--test", action="store_true", help="Send a test LINE message even if no hits")
    args = parser.parse_args()
    
    run_sniper_screening(test_mode=args.test)
