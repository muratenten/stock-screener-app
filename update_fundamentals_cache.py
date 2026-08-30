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

def fetch_japanese_stock_indicators_kabutan(code):
    try:
        import urllib.request
        from bs4 import BeautifulSoup
        url = f"https://kabutan.jp/stock/?code={code}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'})
        html = urllib.request.urlopen(req, timeout=4).read().decode('utf-8')
        soup = BeautifulSoup(html, 'html.parser')
        box = soup.find('div', id='stockinfo_i3')
        if not box:
            return {}
        thead = box.find('thead')
        tbody = box.find('tbody')
        if not thead or not tbody:
            return {}
        ths = [th.text.strip() for th in thead.find_all('th')]
        tds = [td.text.strip() for td in tbody.find_all('td')]
        
        def clean_num(s):
            if not s or s in ('－', '---'):
                return None
            s = s.replace('倍', '').replace('％', '').replace('%', '').replace(',', '').strip()
            try:
                return float(s)
            except Exception:
                return None

        res = {}
        for h, d in zip(ths, tds):
            if 'PER' in h:
                res['per'] = clean_num(d)
            elif 'PBR' in h:
                res['pbr'] = clean_num(d)
            elif '利回り' in h:
                res['dividend_yield'] = clean_num(d)
            elif '信用倍率' in h:
                res['margin_ratio'] = clean_num(d)
        return res
    except Exception:
        return {}

def extract_single_fundamental(ticker, ticker_meta=None):
    try:
        t = yf.Ticker(ticker)
        info = t.info
        if not info:
            return None

        trailing_eps = safe_float(info.get('trailingEps'))
        forward_eps = safe_float(info.get('forwardEps'))
        eps = trailing_eps if trailing_eps is not None else forward_eps
        
        # Accurate dividend per share with cross-validation
        dr = safe_float(info.get('dividendRate'))
        tdr = safe_float(info.get('trailingAnnualDividendRate'))
        tdy = safe_float(info.get('trailingAnnualDividendYield'))
        cur_p = safe_float(info.get('currentPrice') or info.get('previousClose') or info.get('regularMarketPrice'))
        
        dps = None
        if cur_p is not None and cur_p > 0:
            y_dr = (dr / cur_p * 100.0) if (dr is not None and dr > 0) else None
            y_tdr = (tdr / cur_p * 100.0) if (tdr is not None and tdr > 0) else None
            tdy_pct = (tdy * 100.0) if (tdy is not None and tdy > 0) else None
            
            if y_dr is not None and y_tdr is not None:
                if (y_dr > 6.0 and y_dr > y_tdr * 1.5) or (dr > tdr * 2.0 and y_dr > 5.0):
                    dps = tdr
                else:
                    dps = dr
            elif y_dr is not None:
                dps = dr
            elif y_tdr is not None:
                dps = tdr
            elif tdy_pct is not None:
                dps = (tdy_pct / 100.0) * cur_p
            elif info.get('dividendYield') is not None:
                raw_dy = safe_float(info.get('dividendYield'))
                if raw_dy is not None:
                    dy_pct = raw_dy * 100.0 if raw_dy < 0.20 else raw_dy
                    dps = (dy_pct / 100.0) * cur_p
        elif dr is not None:
            dps = dr
        elif tdr is not None:
            dps = tdr
            
        # 🇯🇵 If Japanese stock, consult Kabutan consensus for official 1-share dividend
        if ticker.endswith('.T'):
            code = ticker.split('.')[0]
            kab_ind = fetch_japanese_stock_indicators_kabutan(code)
            if kab_ind.get('dividend_yield') is not None and cur_p is not None and cur_p > 0:
                dps = (kab_ind['dividend_yield'] / 100.0) * cur_p
        
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
