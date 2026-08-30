import json
import time
import os
import datetime
import concurrent.futures
import yfinance as yf

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tse_fundamentals_cache.json")
PRIME_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tse_prime_tickers.json")
GROWTH_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tse_growth_tickers.json")

def safe_float(val):
    if val is None:
        return None
    try:
        if isinstance(val, str):
            val = val.replace(',', '').replace('%', '').strip()
            if val in ('---', ''):
                return None
        return float(val)
    except Exception:
        return None

def extract_single_fundamental(ticker, ticker_meta=None):
    try:
        t = yf.Ticker(ticker)
        info = t.info
        if not info:
            return None

        trailing_eps = safe_float(info.get('trailingEps'))
        forward_eps = safe_float(info.get('forwardEps'))
        eps = trailing_eps if trailing_eps is not None else forward_eps
        
        bps = safe_float(info.get('bookValue'))
        
        dps = safe_float(info.get('dividendRate')) or safe_float(info.get('trailingAnnualDividendRate'))
        if dps is None or dps == 0:
            raw_dy = safe_float(info.get('dividendYield')) or safe_float(info.get('trailingAnnualDividendYield'))
            cur_p = safe_float(info.get('currentPrice') or info.get('previousClose') or info.get('regularMarketPrice'))
            if raw_dy is not None and cur_p is not None and cur_p > 0:
                if raw_dy < 0.20:
                    dps = raw_dy * cur_p
                else:
                    dps = (raw_dy / 100.0) * cur_p
        
        roe = safe_float(info.get('returnOnEquity'))
        if roe is not None and abs(roe) < 1.0:
            roe = roe * 100.0
            
        op_margin = safe_float(info.get('operatingMargins'))
        if op_margin is not None and abs(op_margin) < 1.0:
            op_margin = op_margin * 100.0
            
        net_income = safe_float(info.get('netIncome') or info.get('netIncomeToCommon'))
        total_cash = safe_float(info.get('totalCash'))
        total_debt = safe_float(info.get('totalDebt'))
        de_ratio = safe_float(info.get('debtToEquity'))
        
        rev_growth = safe_float(info.get('revenueGrowth'))
        if rev_growth is not None and abs(rev_growth) <= 10.0:
            rev_growth = rev_growth * 100.0
            
        eps_growth = safe_float(info.get('earningsGrowth') or info.get('earningsQuarterlyGrowth'))
        if eps_growth is not None and abs(eps_growth) <= 10.0:
            eps_growth = eps_growth * 100.0
            
        meta = ticker_meta or {}
        return {
            'ticker': ticker,
            'name': info.get('longName') or info.get('shortName') or meta.get('name', ticker),
            'eps': eps,
            'bps': bps,
            'dps': dps,
            'roe': roe,
            'op_margin': op_margin,
            'net_income': net_income,
            'total_cash': total_cash,
            'total_debt': total_debt,
            'debt_to_equity': de_ratio,
            'rev_growth': rev_growth,
            'eps_growth': eps_growth,
            'sector': info.get('sector') or meta.get('sector', ''),
            'industry': info.get('industry', ''),
            'market_cap': safe_float(info.get('marketCap'))
        }
    except Exception:
        return None

def build_fundamentals_cache(tickers_dict=None, max_workers=25, progress_callback=None):
    if tickers_dict is None:
        tickers_dict = {}
        if os.path.exists(PRIME_FILE):
            with open(PRIME_FILE, 'r', encoding='utf-8') as f:
                tickers_dict.update(json.load(f))
        if os.path.exists(GROWTH_FILE):
            with open(GROWTH_FILE, 'r', encoding='utf-8') as f:
                tickers_dict.update(json.load(f))
                
    total = len(tickers_dict)
    print(f"Starting fundamentals cache build for {total} tickers...")
    
    # Load existing cache to preserve items if API fails
    existing_data = {}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                existing_payload = json.load(f)
                existing_data = existing_payload.get('data', {})
        except Exception:
            existing_data = {}

    fresh_data = dict(existing_data)
    completed = 0
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_ticker = {
            executor.submit(extract_single_fundamental, ticker, meta): ticker 
            for ticker, meta in tickers_dict.items()
        }
        for future in concurrent.futures.as_completed(future_to_ticker):
            ticker = future_to_ticker[future]
            try:
                res = future.result()
                if res and (res.get('eps') is not None or res.get('bps') is not None):
                    fresh_data[ticker] = res
            except Exception:
                pass
            completed += 1
            if progress_callback:
                progress_callback(completed, total)
            if completed % 100 == 0 or completed == total:
                print(f"Progress: {completed}/{total} ({completed/total*100:.1f}%)")

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "metadata": {
            "last_updated": now_str,
            "total_tickers": len(fresh_data),
            "version": "1.0"
        },
        "data": fresh_data
    }
    
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        
    print(f"Saved {len(fresh_data)} ticker snapshots to {CACHE_FILE} at {now_str}!")
    return payload

if __name__ == "__main__":
    build_fundamentals_cache()
