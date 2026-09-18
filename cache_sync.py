"""
ZenStock Cache Synchronization Manager
Handles updating local cache files and automatically syncing them to GitHub/Render.
"""

import os
import sys
import json
import time
import pickle
import subprocess
import datetime
from concurrent.futures import ThreadPoolExecutor
import yfinance as yf
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PRIME_TICKERS_FILE = os.path.join(BASE_DIR, "tse_prime_tickers.json")
FUNDAMENTALS_CACHE_FILE = os.path.join(BASE_DIR, "tse_fundamentals_cache.json")
PRICE_CACHE_FILE = os.path.join(BASE_DIR, "screener_price_cache.pkl")

def sync_cache_to_render(files=None, commit_msg=None):
    """
    Commit and push specified cache files to GitHub.
    Render detects the commit on main and automatically deploys the updated cache.
    """
    if files is None:
        files = ["tse_fundamentals_cache.json", "screener_price_cache.pkl", "static/sniper_matrix.json"]
    
    jst = datetime.timezone(datetime.timedelta(hours=9))
    now_str = datetime.datetime.now(jst).strftime("%Y-%m-%d %H:%M")
    if not commit_msg:
        commit_msg = f"Auto-sync updated cache to Render [{now_str}]"

    try:
        # 1. Filter existing files
        valid_files = [f for f in files if os.path.exists(os.path.join(BASE_DIR, f))]
        if not valid_files:
            return False, "コミット対象のキャッシュファイルが見つかりません。"

        # 2. Git Add
        cmd_add = ["git", "add"] + valid_files
        subprocess.run(cmd_add, cwd=BASE_DIR, check=True, capture_output=True)

        # 3. Check if there are any staged changes
        cmd_diff = ["git", "diff", "--staged", "--name-only"]
        res_diff = subprocess.run(cmd_diff, cwd=BASE_DIR, check=True, capture_output=True, text=True)
        if not res_diff.stdout.strip():
            print("ℹ️ [SYNC] No changes detected in cache files. Everything is already up-to-date.")
            return True, "キャッシュに変更はありません（すでに最新です）。"

        # 4. Git Commit
        cmd_commit = ["git", "commit", "-m", commit_msg]
        subprocess.run(cmd_commit, cwd=BASE_DIR, check=True, capture_output=True)

        # 5. Git Push with large buffer
        subprocess.run(["git", "config", "http.postBuffer", "524288000"], cwd=BASE_DIR, check=True, capture_output=True)
        cmd_push = ["git", "push", "origin", "main"]
        res_push = subprocess.run(cmd_push, cwd=BASE_DIR, check=True, capture_output=True, text=True)
        
        print(f"🚀 [SYNC] Successfully pushed cache to GitHub! Render is auto-deploying...")
        return True, f"GitHubへプッシュ完了！Render本番サーバーが自動更新されます（{now_str}）"

    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
        print(f"❌ [SYNC ERROR] Git operation failed: {err_msg}")
        return False, f"Git同期エラー: {err_msg}"
    except Exception as ex:
        print(f"❌ [SYNC ERROR] {ex}")
        return False, f"同期エラー: {str(ex)}"

def refresh_sniper_price_cache(pbr_max=1.0, max_workers=20, sync_to_render=True, progress_callback=None):
    """
    Download latest 2-year prices for candidate stocks, save to screener_price_cache.pkl,
    and optionally push to Render.
    """
    print("🔄 [CACHE REFRESH] Starting Prime stock price cache update...", flush=True)
    t0 = time.time()
    
    # 1. Load Tickers & Fundamentals
    tickers = []
    if os.path.exists(PRIME_TICKERS_FILE):
        with open(PRIME_TICKERS_FILE, "r", encoding="utf-8") as f:
            prime_dict = json.load(f)
            tickers = [t for t in prime_dict.keys() if t != "8303.T"]
            
    fund_cache = {}
    if os.path.exists(FUNDAMENTALS_CACHE_FILE):
        with open(FUNDAMENTALS_CACHE_FILE, "r", encoding="utf-8") as f:
            fund_cache = json.load(f).get("data", {})
            
    jp_names = {}
    if os.path.exists(PRIME_TICKERS_FILE):
        try:
            with open(PRIME_TICKERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                for k, v in data.items():
                    if isinstance(v, dict) and "name" in v:
                        jp_names[k] = v["name"]
                        jp_names[k.replace(".T", "")] = v["name"]
        except Exception:
            pass

    # 2. Filter candidates
    target_tickers = []
    for t in tickers:
        fc = fund_cache.get(t, {})
        pbr = fc.get('pbr')
        bps = fc.get('bps')
        if pbr is not None:
            if float(pbr) < pbr_max:
                target_tickers.append(t)
        elif bps is not None and float(bps) > 0:
            target_tickers.append(t)
        else:
            target_tickers.append(t)
            
    total = len(target_tickers)
    print(f"📥 Downloading latest 2-year history for {total} stocks (workers: {max_workers})...")
    
    stock_data = {}
    stock_info = {}
    completed = 0
    
    def fetch_stock(ticker):
        try:
            t = yf.Ticker(ticker)
            df = t.history(period="2y")
            if df is not None and not df.empty and len(df) >= 120:
                close = df['Close'].dropna()
                c_last = float(close.iloc[-1])
                c_data = fund_cache.get(ticker, {})
                bps = c_data.get('bps')
                pbr = c_data.get('pbr')
                jp_name = jp_names.get(ticker) or jp_names.get(ticker.replace('.T', ''))
                name = jp_name if jp_name else c_data.get('name', ticker)
                sector = c_data.get('sector', '')
                
                bps_f = float(bps) if bps else None
                pbr_f = float(pbr) if pbr else None
                if (bps_f is None or bps_f <= 0) and pbr_f and pbr_f > 0:
                    bps_f = c_last / pbr_f
                calc_pbr = (c_last / bps_f) if (bps_f and bps_f > 0) else pbr_f
                
                return ticker, {
                    'close': close,
                    'last_price': c_last,
                    'pbr': calc_pbr,
                    'bps': bps_f,
                    'name': name,
                    'sector': sector
                }
        except Exception:
            pass
        return ticker, None

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = executor.map(fetch_stock, target_tickers)
        for ticker, data in results:
            completed += 1
            if progress_callback:
                progress_callback(completed, total)
            if data is not None:
                stock_data[ticker] = data['close']
                stock_info[ticker] = data

    # 3. Save to disk cache
    if len(stock_data) >= 30:
        with open(PRICE_CACHE_FILE, "wb") as f:
            pickle.dump({'data': stock_data, 'info': stock_info}, f)
        elapsed = time.time() - t0
        print(f"💾 Saved {len(stock_data)} stocks to {PRICE_CACHE_FILE} in {elapsed:.1f}s!")
        
        # 4. Auto sync to Render
        if sync_to_render:
            ok, msg = sync_cache_to_render(files=["screener_price_cache.pkl"])
            return ok, f"株価キャッシュ更新完了（{len(stock_data)}社）！{msg}"
        return True, f"株価キャッシュ更新完了（{len(stock_data)}社、所要時間 {elapsed:.1f}秒）"
    else:
        return False, "取得できた銘柄数が不足しています。"

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--sync-only":
        ok, msg = sync_cache_to_render()
        print(msg)
    else:
        ok, msg = refresh_sniper_price_cache(sync_to_render=True)
        print(msg)
