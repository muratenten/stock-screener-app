import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime
import urllib.request
import urllib.parse
import json
import os
from tickers import JP_TICKERS, US_TICKERS

# Page config
st.set_page_config(
    page_title="Rising Stock Screener | 株価上昇シグナル選定ツール",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inject premium custom CSS for clean white base layout
st.markdown("""
<style>
    /* Styling headers and blocks */
    .title-container {
        background: linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%);
        border-radius: 12px;
        padding: 25px;
        margin-bottom: 25px;
        border: 1px solid #cbd5e1;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
    }
    .title-text {
        font-family: 'Outfit', sans-serif;
        color: #1e3a8a;
        font-weight: 800;
        font-size: 2.5rem;
        margin: 0;
    }
    .subtitle-text {
        color: #475569;
        font-size: 1.1rem;
        margin-top: 10px;
        margin-bottom: 0;
    }
    .card {
        background: #ffffff;
        border-radius: 10px;
        padding: 20px;
        border: 1px solid #e2e8f0;
        margin-bottom: 20px;
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05), 0 2px 4px -1px rgba(0,0,0,0.03);
        color: #1e293b;
    }
    .metric-title {
        color: #64748b;
        font-size: 0.85rem;
        margin-bottom: 5px;
    }
    .metric-value {
        font-size: 1.5rem;
        font-weight: bold;
        color: #0f172a;
    }
    .metric-accent {
        color: #16a34a;
    }
</style>
""", unsafe_allow_html=True)

# Helper function to check if a ticker is a US stock
def is_us_stock(ticker):
    if not ticker:
        return False
    return not ticker.endswith(".T") and not ticker.isdigit()

# Helper function to get USD/JPY exchange rate
@st.cache_data(ttl=3600)
def get_usdjpy_rate():
    try:
        rate_ticker = yf.Ticker("JPY=X")
        df = rate_ticker.history(period="1d")
        if not df.empty:
            rate = float(df['Close'].iloc[-1])
            return rate
    except Exception:
        pass
    return 155.0

# Helper function to format price
def format_price(price, ticker=None):
    if price is None or pd.isna(price):
        return "N/A"
    if ticker and is_us_stock(ticker):
        return f"${price:,.2f}"
    return f"¥{int(price):,}"

# Helper function to format large currency figures
def format_large_jpy(val, ticker=None):
    if val is None or pd.isna(val):
        return "N/A"
    if ticker and is_us_stock(ticker):
        abs_val = abs(val)
        if abs_val >= 10**12:
            return f"${val / 10**12:.2f}兆ドル"
        elif abs_val >= 10**8:
            return f"${val / 10**8:.1f}億ドル"
        else:
            return f"${val:,.2f}"
    else:
        abs_val = abs(val)
        if abs_val >= 10**12:
            return f"¥{val / 10**12:.2f}兆円"
        elif abs_val >= 10**8:
            return f"¥{val / 10**8:.1f}億円"
        else:
            return f"¥{int(val):,}円"

# Helper functions for Technical Indicators
def calculate_rsi(series, period=14):
    if len(series) < period:
        return pd.Series(np.nan, index=series.index)
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period-1, adjust=False).mean()
    avg_loss = loss.ewm(com=period-1, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_macd(series, fast=12, slow=26, signal=9):
    if len(series) < slow:
        return pd.Series(np.nan, index=series.index), pd.Series(np.nan, index=series.index), pd.Series(np.nan, index=series.index)
    exp1 = series.ewm(span=fast, adjust=False).mean()
    exp2 = series.ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    macd_signal = macd.ewm(span=signal, adjust=False).mean()
    macd_hist = macd - macd_signal
    return macd, macd_signal, macd_hist

def calculate_bollinger_bands(series, period=20, std_dev=2):
    if len(series) < period:
        return pd.Series(np.nan, index=series.index), pd.Series(np.nan, index=series.index), pd.Series(np.nan, index=series.index)
    rolling_mean = series.rolling(window=period).mean()
    rolling_std = series.rolling(window=period).std()
    upper_band = rolling_mean + (rolling_std * std_dev)
    lower_band = rolling_mean - (rolling_std * std_dev)
    return upper_band, rolling_mean, lower_band

# Helper for Dialog Popup
@st.dialog("🎉 仮想購入（デモトレード登録）完了", width="medium")
def show_purchase_success_dialog(name, ticker, qty, price, total_cost):
    st.markdown(f"""
    ### **{name} ({ticker})** の購入が完了しました！
    
    仮想シミュレーションの保有ポートフォリオに正常に追加されました。
    
    <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 15px; margin-top: 15px; margin-bottom: 20px; color: #1e293b;">
        <!-- 購入銘柄 -->
        <div style="display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 1px solid #e2e8f0; padding: 10px 0;">
            <span style="color: #64748b; font-weight: bold; min-width: 100px; flex-shrink: 0; text-align: left;">購入銘柄</span>
            <span style="text-align: right; font-weight: bold; color: #0f172a; word-break: break-all; margin-left: 10px;">{name} ({ticker})</span>
        </div>
        <!-- 購入株数 -->
        <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #e2e8f0; padding: 10px 0;">
            <span style="color: #64748b; min-width: 100px; flex-shrink: 0; text-align: left;">購入株数</span>
            <span style="text-align: right; font-weight: bold; color: #0f172a;">{qty:,} 株</span>
        </div>
        <!-- 平均取得単価 -->
        <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #e2e8f0; padding: 10px 0;">
            <span style="color: #64748b; min-width: 100px; flex-shrink: 0; text-align: left;">平均取得単価</span>
            <span style="text-align: right; font-weight: bold; color: #16a34a;">{format_price(price, ticker)}</span>
        </div>
        <!-- 概算投資金額 -->
        <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px 0;">
            <span style="color: #64748b; font-weight: bold; min-width: 100px; flex-shrink: 0; text-align: left;">概算投資金額</span>
            <span style="text-align: right; font-weight: bold; color: #2563eb; font-size: 1.2rem;">{format_price(total_cost, ticker)}</span>
        </div>
    </div>
    
    ※ 「仮想シミュレーション（デモトレード）」タブを開くと、現在の評価損益やパフォーマンス推移が確認できます。
    """, unsafe_allow_html=True)
    if st.button("確認して閉じる", type="primary", use_container_width=True, key="dlg_confirm_close_btn"):
        st.rerun()

# Helper for Sell Dialog Popup
@st.dialog("🎉 仮想売却完了", width="medium")
def show_sell_success_dialog(name, ticker, qty, price, total_return, realized_pl):
    pl_color = "#16a34a" if realized_pl >= 0 else "#dc2626"
    pl_sign = "+" if realized_pl >= 0 else ""
    rate = get_usdjpy_rate() if is_us_stock(ticker) else 1.0
    
    if is_us_stock(ticker):
        price_str = format_price(price, ticker)
        total_return_str = f"{format_price(total_return, ticker)} (¥{int(total_return * rate):,})"
        realized_pl_str = f"{pl_sign}{format_price(realized_pl, ticker)} ({pl_sign}¥{int(realized_pl * rate):,})"
    else:
        price_str = format_price(price, ticker)
        total_return_str = format_price(total_return, ticker)
        realized_pl_str = f"{pl_sign}{format_price(realized_pl, ticker)}"

    st.markdown(f"""
    ### **{name} ({ticker})** の売却が完了しました！
    
    仮想シミュレーションの保有ポートフォリオから正常に売却されました。
    
    <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 15px; margin-top: 15px; margin-bottom: 20px; color: #1e293b;">
        <!-- 売却銘柄 -->
        <div style="display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 1px solid #e2e8f0; padding: 10px 0;">
            <span style="color: #64748b; font-weight: bold; min-width: 100px; flex-shrink: 0; text-align: left;">売却銘柄</span>
            <span style="text-align: right; font-weight: bold; color: #0f172a; word-break: break-all; margin-left: 10px;">{name} ({ticker})</span>
        </div>
        <!-- 売却株数 -->
        <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #e2e8f0; padding: 10px 0;">
            <span style="color: #64748b; min-width: 100px; flex-shrink: 0; text-align: left;">売却株数</span>
            <span style="text-align: right; font-weight: bold; color: #0f172a;">{qty:,} 株</span>
        </div>
        <!-- 売却単価 -->
        <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #e2e8f0; padding: 10px 0;">
            <span style="color: #64748b; min-width: 100px; flex-shrink: 0; text-align: left;">売却単価</span>
            <span style="text-align: right; font-weight: bold; color: #0f172a;">{price_str}</span>
        </div>
        <!-- 売却受取金額 -->
        <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #e2e8f0; padding: 10px 0;">
            <span style="color: #64748b; min-width: 100px; flex-shrink: 0; text-align: left;">売却受取金額</span>
            <span style="text-align: right; font-weight: bold; color: #2563eb;">{total_return_str}</span>
        </div>
        <!-- 確定実現損益 -->
        <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px 0;">
            <span style="color: #64748b; font-weight: bold; min-width: 100px; flex-shrink: 0; text-align: left;">確定実現損益</span>
            <span style="text-align: right; font-weight: bold; color: {pl_color}; font-size: 1.2rem;">{realized_pl_str}</span>
        </div>
    </div>
    
    ※ ポートフォリオの「確定取引（仮想売却）履歴一覧」にて履歴が確認できます。
    """, unsafe_allow_html=True)
    if st.button("確認して閉じる", type="primary", use_container_width=True, key="dlg_sell_confirm_close_btn"):
        st.rerun()

def patch_history_with_fast_info(ticker, df):
    if df.empty:
        return df
    # Check if the last row has NaN for Close (typical yfinance weekend bug for JPY stocks)
    last_idx = df.index[-1]
    if pd.isna(df.loc[last_idx, 'Close']):
        try:
            tk = yf.Ticker(ticker)
            f_info = tk.fast_info
            last_price = f_info.get('lastPrice')
            if last_price is not None and not pd.isna(last_price):
                df.loc[last_idx, 'Close'] = last_price
                if 'Open' in df.columns and f_info.get('open') is not None:
                    df.loc[last_idx, 'Open'] = f_info.get('open')
                if 'High' in df.columns and f_info.get('dayHigh') is not None:
                    df.loc[last_idx, 'High'] = f_info.get('dayHigh')
                if 'Low' in df.columns and f_info.get('dayLow') is not None:
                    df.loc[last_idx, 'Low'] = f_info.get('dayLow')
                if 'Volume' in df.columns and f_info.get('lastVolume') is not None:
                    df.loc[last_idx, 'Volume'] = f_info.get('lastVolume')
        except Exception:
            pass
    return df

def z_normalize(seq):
    arr = np.array(seq)
    std = np.std(arr)
    if std == 0:
        return np.zeros_like(arr)
    return (arr - np.mean(arr)) / std

def localize_timestamp(ts, tz):
    ts_pd = pd.to_datetime(ts)
    if tz is not None:
        if ts_pd.tz is None:
            return ts_pd.tz_localize(tz)
        else:
            return ts_pd.tz_convert(tz)
    else:
        if ts_pd.tz is not None:
            return ts_pd.tz_localize(None)
        return ts_pd

@st.cache_data(ttl=86400)
def get_stock_5y_history(ticker):
    try:
        tk = yf.Ticker(ticker)
        df_5y = tk.history(period="5y")
        df_5y = patch_history_with_fast_info(ticker, df_5y)
        return df_5y
    except Exception:
        return pd.DataFrame()

def create_pattern_overlay_chart(target_prices, matches_data, N, ticker=None):
    fig = go.Figure()
    
    symbol = "$" if ticker and is_us_stock(ticker) else "¥"
    fmt = ".2f" if ticker and is_us_stock(ticker) else ".0f"
    unit = "ドル" if ticker and is_us_stock(ticker) else "円"
    
    # Target pattern
    fig.add_trace(go.Scatter(
        x=list(range(N)),
        y=target_prices,
        mode='lines+markers',
        name='基準パターン (指定範囲)',
        line=dict(color='#1e3a8a', width=4),
        marker=dict(size=6),
        hovertemplate=f"日目: %{{x}}<br>株価: {symbol}%{{y:,{fmt}}}<extra></extra>"
    ))
    
    colors = ['#eab308', '#10b981', '#f97316']
    t0 = target_prices[0] if target_prices[0] != 0 else 1
    
    for idx, m in enumerate(matches_data):
        all_prices = m['all_prices']
        a0 = all_prices[0] if all_prices[0] != 0 else 1
        scale_factor = t0 / a0
        scaled_prices = all_prices * scale_factor
        
        period_str = f"{m['start_date'].strftime('%Y-%m-%d')} 〜 {m['end_date'].strftime('%Y-%m-%d')}"
        
        fig.add_trace(go.Scatter(
            x=list(range(len(all_prices))),
            y=scaled_prices,
            mode='lines',
            name=f"類似{idx+1}位 ({m['similarity']:.1f}%): {period_str}",
            line=dict(color=colors[idx % len(colors)], width=2, dash='solid' if idx == 0 else 'dash'),
            hovertemplate=f"日目: %{{x}}<br>株価 (スケール後): {symbol}%{{y:,{fmt}}}<extra></extra>"
        ))
        
    fig.add_vline(
        x=N-1, 
        line_width=1.5, 
        line_dash="dash", 
        line_color="#dc2626", 
        annotation_text="パターン終了点", 
        annotation_position="top left"
    )
    
    fig.update_layout(
        title="類似パターンの株価値動き重ね合わせ (現在値基準でスケール調整)",
        xaxis_title="経過営業日 (日)",
        yaxis_title=f"株価 ({unit})",
        template="plotly_white",
        height=450,
        margin=dict(l=10, r=10, t=50, b=50),
        legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5)
    )
    return fig

def create_selection_chart(df, ticker, name, start_date, end_date):
    fig = go.Figure()
    
    symbol = "$" if is_us_stock(ticker) else "¥"
    fmt = ".2f" if is_us_stock(ticker) else ".0f"
    unit = "ドル" if is_us_stock(ticker) else "円"
    
    # Plot Close price
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['Close'],
        mode='lines',
        name='株価 (終値)',
        line=dict(color='#2563eb', width=2),
        hovertemplate=f"日付: %{{x|%Y-%m-%d}}<br>株価: {symbol}%{{y:,{fmt}}}<extra></extra>"
    ))
    
    # 1. Draw static vertical lines and shaded rect for current state
    fig.add_vline(x=start_date, line_width=2, line_dash="solid", line_color="#ef4444")
    fig.add_vline(x=end_date, line_width=2, line_dash="solid", line_color="#ef4444")
    fig.add_vrect(
        x0=start_date,
        x1=end_date,
        fillcolor="#ef4444",
        opacity=0.12,
        layer="below",
        line_width=0
    )
    
    fig.update_layout(
        title=f"{name} ({ticker}) - パターン範囲選択（ドラッグして期間を調整）",
        xaxis_title="日付",
        yaxis_title=f"株価 ({unit})",
        template="plotly_white",
        height=320,
        margin=dict(l=10, r=10, t=40, b=10),
        showlegend=False,
        # 2. Style the active Box Select shape to match our red selection theme
        activeshape=dict(
            fillcolor="#ef4444",
            opacity=0.12
        ),
        uirevision="constant" # Prevent zoom/selection from resetting on rerun
    )
    return fig

# Cached function for downloading batch histories
@st.cache_data(ttl=3600)
def batch_download_histories(tickers_list, period="1y"):
    if not tickers_list:
        return {}
    try:
        data = yf.download(tickers_list, period=period, progress=False)
    except Exception as e:
        st.error(f"データのダウンロード中にエラーが発生しました: {e}")
        return {}
    
    histories = {}
    if len(tickers_list) == 1:
        ticker = tickers_list[0]
        if isinstance(data.columns, pd.MultiIndex):
            df = pd.DataFrame({
                'Open': data['Open'][ticker],
                'High': data['High'][ticker],
                'Low': data['Low'][ticker],
                'Close': data['Close'][ticker],
                'Volume': data['Volume'][ticker]
            })
        else:
            df = data.copy()
        df = patch_history_with_fast_info(ticker, df)
        df = df.dropna(subset=['Close'])
        histories[ticker] = df
    else:
        for ticker in tickers_list:
            try:
                if ticker in data['Close'].columns:
                    df = pd.DataFrame({
                        'Open': data['Open'][ticker],
                        'High': data['High'][ticker],
                        'Low': data['Low'][ticker],
                        'Close': data['Close'][ticker],
                        'Volume': data['Volume'][ticker]
                    })
                    df = patch_history_with_fast_info(ticker, df)
                    df = df.dropna(subset=['Close'])
                    if not df.empty:
                        histories[ticker] = df
            except Exception:
                continue
    return histories

# Cached function for downloading ticker fundamental info
@st.cache_data(ttl=86400)
def get_ticker_info(ticker):
    try:
        t = yf.Ticker(ticker)
        raw_info = t.info
        
        # Extract net income keys
        net_income = raw_info.get('netIncome') or raw_info.get('netIncomeToCommon')
        op_margin = raw_info.get('operatingMargins')
        total_cash = raw_info.get('totalCash')
        total_debt = raw_info.get('totalDebt')
        debt_equity = raw_info.get('debtToEquity')
        
        needed = {
            'longName': raw_info.get('longName'),
            'shortName': raw_info.get('shortName'),
            'trailingPE': raw_info.get('trailingPE') or raw_info.get('forwardPE'),
            'priceToBook': raw_info.get('priceToBook'),
            'returnOnEquity': raw_info.get('returnOnEquity'),
            'dividendYield': raw_info.get('dividendYield'),
            'marketCap': raw_info.get('marketCap'),
            'fiftyTwoWeekHigh': raw_info.get('fiftyTwoWeekHigh'),
            'fiftyTwoWeekLow': raw_info.get('fiftyTwoWeekLow'),
            'sector': raw_info.get('sector'),
            'industry': raw_info.get('industry'),
            'longBusinessSummary': raw_info.get('longBusinessSummary'),
            'netIncome': net_income,
            'opMargin': op_margin,
            'totalCash': total_cash,
            'totalDebt': total_debt,
            'debtToEquity': debt_equity
        }
        
        # Adjust ROE (fraction to % value)
        if needed['returnOnEquity'] is not None:
            if abs(needed['returnOnEquity']) < 1.0:
                needed['returnOnEquity'] *= 100
                
        # Adjust dividendYield (handle 0.15 threshold to resolve yfinance formatting inconsistency)
        if needed['dividendYield'] is not None:
            if needed['dividendYield'] < 0.15:
                needed['dividendYield'] *= 100
                
        # Adjust opMargin (fraction to % value)
        if needed['opMargin'] is not None:
            if abs(needed['opMargin']) < 1.0:
                needed['opMargin'] *= 100
                
        return needed
    except Exception:
        return {}

# Dynamic Index constituent fetcher (Scraping from Wikipedia)
@st.cache_data(ttl=86400)
def fetch_nikkei225_tickers():
    try:
        from bs4 import BeautifulSoup
        url = "https://ja.wikipedia.org/wiki/" + urllib.parse.quote("日経平均株価")
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        html_bytes = urllib.request.urlopen(req).read()
        html_str = html_bytes.decode('utf-8')
        soup = BeautifulSoup(html_str, 'html.parser')
        
        components = {}
        current_sector = "不明"
        
        for element in soup.find_all(['h3', 'h4', 'table']):
            if element.name in ['h3', 'h4']:
                text = element.text.strip()
                if '[' in text:
                    text = text.split('[')[0].strip()
                if '（' in text:
                    text = text.split('（')[0].strip()
                if '(' in text:
                    text = text.split('(')[0].strip()
                current_sector = text
            elif element.name == 'table':
                headers = [th.text.strip() for th in element.find_all('th')]
                if '証券コード' in headers and '銘柄' in headers:
                    rows = element.find_all('tr')[1:]
                    for row in rows:
                        cols = row.find_all('td')
                        if len(cols) >= 2:
                            code_text = cols[0].text.strip()
                            name_text = cols[1].text.strip()
                            if len(code_text) == 4 and code_text.isalnum():
                                ticker = f"{code_text}.T"
                                
                                # Inherit hand-curated tags from JP_TICKERS if available
                                inherited_tags = []
                                if ticker in JP_TICKERS:
                                    inherited_tags = JP_TICKERS[ticker].get("tags", [])
                                
                                tags = list(set(["日経225", current_sector] + inherited_tags))
                                components[ticker] = {"name": name_text, "tags": tags}
                                
        if components:
            return components
    except Exception as e:
        st.sidebar.warning(f"日経225の動的取得に失敗しました。ローカルデータを使用します。: {e}")
    return JP_TICKERS

# Build indicator scoring logic
def evaluate_stock(ticker, df, info=None):
    if df.empty or len(df) < 75:
        return None
        
    close = df['Close']
    volume = df['Volume']
    
    df['SMA5'] = close.rolling(window=5).mean()
    df['SMA25'] = close.rolling(window=25).mean()
    df['SMA75'] = close.rolling(window=75).mean()
    df['RSI'] = calculate_rsi(close)
    macd, macd_signal, macd_hist = calculate_macd(close)
    df['MACD'] = macd
    df['MACD_Signal'] = macd_signal
    df['MACD_Hist'] = macd_hist
    upper, middle, lower = calculate_bollinger_bands(close)
    df['BB_Upper'] = upper
    df['BB_Middle'] = middle
    df['BB_Lower'] = lower
    
    # --- 1. テクニカルスコアリング（3点満点に縮小） ---
    
    # (a) トレンド調和 (中長期上昇トレンド)
    # 現在値 > 25日線 > 75日線
    t_uptrend = close.iloc[-1] > df['SMA25'].iloc[-1] and df['SMA25'].iloc[-1] > df['SMA75'].iloc[-1]
    
    # (b) トレンド転換シグナル (GC または MACDクロス同期)
    golden_cross = False
    for i in range(-5, 0):
        if abs(i) < len(df):
            if df['SMA25'].iloc[i] > df['SMA75'].iloc[i] and df['SMA25'].iloc[i-1] <= df['SMA75'].iloc[i-1]:
                golden_cross = True
                break
    macd_cross = False
    for i in range(-5, 0):
        if abs(i) < len(df):
            if df['MACD'].iloc[i] > df['MACD_Signal'].iloc[i] and df['MACD'].iloc[i-1] <= df['MACD_Signal'].iloc[i-1]:
                macd_cross = True
                break
    t_trend_reversal = golden_cross or macd_cross
    
    # (c) 機関投資家の流入 (Volume Surge)
    vol_5d = volume.iloc[-5:].mean() if len(volume) >= 5 else 0
    vol_25d = volume.iloc[-25:].mean() if len(volume) >= 25 else 1
    t_volume_surge = vol_5d >= (vol_25d * 1.2) if vol_25d > 0 else False
    
    tech_score = sum([t_uptrend, t_trend_reversal, t_volume_surge])
    
    rsi_val = df['RSI'].iloc[-1]
    bb_lower_val = df['BB_Lower'].iloc[-1]
    bb_upper_val = df['BB_Upper'].iloc[-1]
    
    rsi_oversold = rsi_val < 30
    rsi_overbought = rsi_val > 70
    bb_rebound = close.iloc[-1] <= bb_lower_val
    bb_upper_breakout = close.iloc[-1] >= bb_upper_val
    
    signals = {
        'perfect_order': t_uptrend,
        'trend_reversal': t_trend_reversal,
        'volume_surge': t_volume_surge,
        'golden_cross': golden_cross,
        'rsi_oversold': rsi_oversold,
        'rsi_overbought': rsi_overbought,
        'macd_cross': macd_cross,
        'bb_rebound': bb_rebound,
        'bb_upper_breakout': bb_upper_breakout,
        'uptrend': t_uptrend
    }
    
    if info is None:
        return {
            'df': df,
            'tech_score': tech_score,
            'signals': signals,
            'metrics': {
                'price': close.iloc[-1],
                'change_pct': ((close.iloc[-1] - close.iloc[-2]) / close.iloc[-2]) * 100 if len(close) > 1 else 0.0,
                'vol_surge_ratio': vol_5d / vol_25d if vol_25d > 0 else 1.0
            }
        }
        
    # --- 2. ファンダメンタルズスコアリング（7点満点に拡張） ---
    per = info.get('trailingPE')
    pbr = info.get('priceToBook')
    roe = info.get('returnOnEquity')
    div_yield = info.get('dividendYield')
    net_inc = info.get('netIncome')
    op_margin = info.get('opMargin')
    de_ratio = info.get('debtToEquity')
    
    # (a) 資本効率 (ROE >= 10%)
    f_roe = roe is not None and roe >= 10.0
    
    # (b) 本業の収益力 (営業利益率 >= 8%)
    f_op_margin = op_margin is not None and op_margin >= 8.0
    
    # (c) 利益の質 (当期純利益が純黒字であること)
    f_profitable = net_inc is not None and net_inc > 0
    
    # (d) 利益面での割安性 (PER < 15倍)
    f_per = per is not None and per < 15.0
    
    # (e) 資産面での割安性・東証改革期待 (PBR < 1.0倍)
    f_pbr = pbr is not None and pbr < 1.0
    
    # (f) 財務健全性 (D/E比率 < 100% または 実質無借金)
    f_solvency = de_ratio is not None and de_ratio < 100.0
    if de_ratio is None:
        cash_val = info.get('totalCash') or 0
        debt_val = info.get('totalDebt') or 0
        f_solvency = cash_val >= debt_val
        
    # (g) 還元・インカム (配当利回り >= 3%)
    f_dividend = div_yield is not None and div_yield >= 3.0
    
    fund_score = sum([f_roe, f_op_margin, f_profitable, f_per, f_pbr, f_solvency, f_dividend])
    
    metrics = {
        'price': close.iloc[-1],
        'change_pct': ((close.iloc[-1] - close.iloc[-2]) / close.iloc[-2]) * 100 if len(close) > 1 else 0.0,
        'per': per,
        'pbr': pbr,
        'roe': roe,
        'dividend_yield': div_yield,
        'market_cap': info.get('marketCap'),
        'name': info.get('longName') or info.get('shortName') or ticker,
        'net_income': net_inc,
        'op_margin': op_margin,
        'total_cash': info.get('totalCash'),
        'total_debt': info.get('totalDebt'),
        'debt_equity': de_ratio,
        'vol_surge_ratio': vol_5d / vol_25d if vol_25d > 0 else 1.0
    }
    
    return {
        'df': df,
        'tech_score': tech_score,
        'fund_score': fund_score,
        'total_score': tech_score + fund_score,
        'signals': signals,
        'metrics': metrics,
        'info_raw': info
    }

# Dynamic text generation for recommendation
def generate_recommendation_text(ticker, name, tech_score, fund_score, signals, metrics):
    text = f"### **{name} ({ticker})** のAIスクリーニングレポート\n\n"
    
    total_score = tech_score + fund_score
    max_score = 10
    
    if total_score >= 8:
        rating = "**非常に強い上昇期待 (推奨)**"
    elif total_score >= 6:
        rating = "**上昇期待シグナル (買い推奨)**"
    elif total_score >= 4:
        rating = "**中立・監視対象**"
    else:
        rating = "**買いシグナル弱 / 調整局面**"
        
    text += f"**総合判定**: {rating} (総合スコア: **{total_score}/{max_score}** | テクニカル: {tech_score}/3, ファンダ: {fund_score}/7)\n\n"
    
    text += "#### テクニカル分析の所見\n"
    tech_bullets = []
    if signals.get('perfect_order'):
        tech_bullets.append("- **堅調な上昇トレンド**: 5日・25日・75日移動平均線が順並びの上昇トレンドを形成中。買い優勢の強いトレンドモメンタムを維持しています。")
    if signals.get('trend_reversal'):
        tech_bullets.append("- **トレンド転換シグナル**: 25日線と75日線のゴールデンクロス、またはMACDゴールデンクロスが発生。下落トレンドからの底打ち反転を示唆する強い兆候です。")
    if signals.get('volume_surge'):
        tech_bullets.append("- **大口資金流入 (出来高急増)**: 直近の平均出来高が過去平均の1.2倍以上に急増。機関投資家や大口投資家が本格的な買いを入れた本物のシグナルと判断されます。")
        
    if not tech_bullets:
        tech_bullets.append("- テクニカル面で特定の強い買いシグナルは点灯していません。")
    text += "\n".join(tech_bullets) + "\n\n"
    
    text += "#### ファンダメンタルズ分析の所見\n"
    fund_bullets = []
    
    pbr = metrics.get('pbr')
    per = metrics.get('per')
    roe = metrics.get('roe')
    div = metrics.get('dividend_yield')
    op_margin = metrics.get('op_margin')
    net_income = metrics.get('net_income')
    de_ratio = metrics.get('debt_equity')
    
    if roe is not None and roe >= 10.0:
        fund_bullets.append(f"- **高資本効率 (ROE: {roe:.1f}%)**: 自己資本に対して効率的に利益を稼ぎ出す優良経営です。(基準値: ROE 10%以上)")
    if op_margin is not None and op_margin >= 8.0:
        fund_bullets.append(f"- **高い本業の収益力 (営業利益率: {op_margin:.1f}%)**: 売上から本業の儲けを効率的に残せる強固なビジネスモデルです。(基準値: 営業利益率 8%以上)")
    if net_income is not None and net_income > 0:
        fund_bullets.append(f"- **当期純利益 黒字**: 直近利益が黒字であり、財務的な安定性と投資信頼性が保証されています。")
    if per is not None and per < 15.0:
        fund_bullets.append(f"- **利益面での割安性 (PER: {per:.1f}倍)**: 企業の稼ぐ力に対して現在の株価は割安に置かれており、水準訂正の余地があります。(基準値: PER 15倍未満)")
    if pbr is not None and pbr < 1.0:
        fund_bullets.append(f"- **資産面での割安性 (PBR: {pbr:.2f}倍)**: 解散価値とされるPBR1.0倍を下回っており、東証の資本効率改善要求に伴う株価対策（増配・自社株買い等）が強く期待される水準です。(基準値: PBR 1.0倍未満)")
    if de_ratio is not None and de_ratio < 100.0:
        fund_bullets.append(f"- **強固な財務健全性 (D/E比率: {de_ratio:.1f}%)**: 有利子負債が自己資本の範囲内であり、金利上昇局面でも影響を受けにくい健全な財務体質です。(基準値: D/E比率 100%未満)")
    elif de_ratio is None:
        total_cash = metrics.get('total_cash') or 0
        total_debt = metrics.get('total_debt') or 0
        if total_cash >= total_debt and total_cash > 0:
            fund_bullets.append(f"- **実質無借金経営**: 手元現預金が有利子負債を上回っており、財務的な倒産リスクが極めて低く、現金を有効活用した事業投資や株主還元余力が豊富です。")
    if div is not None and div >= 3.0:
        fund_bullets.append(f"- **高配当インカム (配当利回り: {div:.2f}%)**: 年利3%を超える配当があり、株価の下値支持力になると同時に、長期保有の強い味方です。(基準値: 配当利回り 3.0%以上)")
        
    if not fund_bullets:
        fund_bullets.append("- ファンダメンタルズ面で割安または超高収益に該当する特定指標はありません。")
    text += "\n".join(fund_bullets) + "\n\n"
    
    text += "#### 投資戦略アドバイス\n"
    if total_score >= 8:
        text += "ファンダメンタルズの盤石さとテクニカルの上昇モメンタムが極めて高水準で一致した、プロも注目する投資機会です。中長期の資産形成の核として、自信を持ってエントリーできる水準です。"
    elif total_score >= 6:
        text += "良好な企業価値と上昇トレンドが調和しています。ファンダメンタルズが下値を支えるため、リスクリワード比が良く、押し目買い（下がった局面での購入）や順張りエントリーに適しています。"
    elif total_score >= 4:
        if tech_score >= 2:
            text += "短期的な値動き（モメンタム）が先行しています。ファンダメンタルズの裏付けはやや薄いため、トレンドの終わり（25日線下抜け等）で早めに手仕舞う順張りトレードが推奨されます。"
        elif fund_score >= 4:
            text += "業績や財務健全性が極めて優良なバリュー銘柄です。目先のトレンドはやや弱いか横ばいですが、下値不安が極めて低いため、中長期的な観点から押し目でコツコツと仕込んでいくのに適しています。"
        else:
            text += "一部の買い材料が点灯していますが、モメンタム・ファンダメンタルズ共に決定打に欠けます。業界全体のトレンドや地合いの動向も見極めつつ、監視リストに入れてタイミングを待つのが無難です。"
    else:
        text += "現在の上昇確度は低めです。焦って購入せず、よりスコアの高い他の推奨銘柄を選択するか、チャートの本格的なボトムアウトを確認するまで様子見を推奨します。"
        
    return text

# Generate IR and Catalyst scenario analysis
def generate_ir_catalysts(ticker, tags, info):
    summary = info.get('longBusinessSummary') or ""
    sector = info.get('sector') or "未分類"
    industry = info.get('industry') or "未分類"
    
    # Determine sector name in Japanese
    sector_ja = {
        "Technology": "テクノロジー・情報技術",
        "Financial Services": "金融サービス",
        "Industrials": "資本財・重工業",
        "Consumer Cyclical": "一般消費財",
        "Healthcare": "ヘルスケア・バイオ",
        "Communication Services": "コミュニケーション・通信",
        "Consumer Defensive": "生活必需品",
        "Basic Materials": "素材・化学",
        "Real Estate": "不動産",
        "Energy": "エネルギー",
        "Utilities": "公益事業"
    }.get(sector, sector)
    
    text = f"### ビジネスモデルとカタリスト（株価上昇材料）分析\n\n"
    text += f"**セクター**: `{sector_ja}` | **業界**: `{industry}`\n\n"
    
    # 1. Business Description Summary
    text += "#### 企業の主要事業活動\n"
    if summary:
        text += f"> {summary[:600]}...\n\n"
        text += "*※Yahoo Financeより自動取得した事業サマリー（原文）を表示しています。*\n\n"
    else:
        text += "事業活動の詳細概要は取得できませんでした。（カスタム銘柄の場合は財務情報の取得が制限されることがあります）\n\n"
        
    # 2. Upcoming IR & Catalyst Scenarios based on tags
    text += "#### 期待される今後の株価上昇材料 (カタリスト)\n"
    
    catalysts = []
    
    # Space Tag
    if "宇宙" in tags or any(x in sector or x in industry for x in ["Space", "Aerospace", "Defense", "防衛", "航空宇宙"]):
        catalysts.extend([
            "**宇宙開発・打上げ成功IR**: 自社人工衛星や顧客衛星の打上げスケジュール・打上げ成否に関する公式アナウンス。ミッションの成功は直接的な収益化や技術実証となり、最も強力な買い材料になります。",
            "**防衛省・JAXA等からの政府受注**: 政府が推進する宇宙技術戦略基金などの開発補助金の採択、または防衛関連での大型契約受注IRが株価急騰の最大のトリガーです。",
            "**月面探査プロジェクトの進捗**: 月面データビジネスや着陸船の着陸予定、各種パートナーシップ企業の開示など、宇宙ビジネスの実現性に直結するアップデート。"
        ])
        
    # AI / Semi Tag
    if "AI" in tags or "半導体" in tags or any(x in sector or x in industry for x in ["Technology", "Semiconductor", "Software", "ソフトウェア"]):
        catalysts.extend([
            "**次世代AIサーバー / SoCの出荷 / テープアウト**: 最先端AIチップ（NVIDIA製等）の安定確保やデータセンターの拡張IR、カスタムSoC（ソシオネクスト等）の開発進捗（テープアウト完了）に関する発表。",
            "**グローバルAIリーダー（NVIDIA等）の決算**: AI・半導体セクターは連動性が非常に高いため、米NVIDIA等の決算内容や将来の設備投資計画（CapEx）に関するカンファレンスコール自体が、自社株の強力なカタリストになります。",
            "**政府による国内製造支援・助成金**: データセンター整備費用への政府補助金の採択、経産省による半導体技術支援プロジェクトへの参画認定IR。"
        ])
        
    # High Volatility / growth tag
    if "急騰期待" in tags:
        catalysts.extend([
            "**業績ガイダンスの上方修正（サプライズ）**: 急成長株において、四半期決算で通期予想を上方修正したり、市場のコンセンサス予想を大幅に超える進捗率を見せた際の決算IRは、ストップ高を誘発しやすくなります。",
            "**業界巨人・グローバル企業との業務資本提携**: 認知度や資本力に劣る新興ベンチャーが、NTTやトヨタ等の国内大手、あるいは海外メガテック企業とのシステム連携や共同出資を発表した際の株価インパクトは絶大です。",
            "**株式分割・株主優待制度の新設**: 個人投資家の売買活発度が高いため、最低投資金額を引き下げる株式分割や、魅力的な優待の新設IRは、需給関係を急激に好転させます。"
        ])
        
    # PBR < 1
    pbr = info.get('priceToBook')
    if pbr is not None and pbr < 1.0:
        catalysts.extend([
            "**東証PBR改革要求への対応策の開示**: 「資本コストや株価を意識した経営の具体策」に関するIR発表。これが中長期的に最も評価されるカタリストです。",
            "**自社株買い・配当性向の引き上げ（増配）**: 企業内に蓄積されたキャッシュを株主に還元する、数百万株規模の自社株買いや特別配当の決定IR。",
            "**MBO（経営陣による自社買収）またはTOB**: 割安すぎる評価に甘んじている優良企業が、非公開化を選択するMBOや親会社による子会社化を発表する動き。提示されるプレミアム価格まで一気に上昇します。"
        ])
        
    # General default if no specific catalysts match
    if not catalysts:
        catalysts.extend([
            "**四半期決算時の利益進捗（コンセンサス上振れ）**: 定期決算における、市場予想を上回るポジティブサプライズの発表。",
            "**新規プロダクトのローンチ・主要アップデート**: 既存顧客へのアップセルにつながる新機能や、新規市場への進出ロードマップの公表。"
        ])
        
    for c in catalysts:
        text += f"- {c}\n\n"
        
    # 3. Next Earnings Info
    text += "#### 次回決算・IR予定におけるリスク管理\n"
    text += "グロース企業やテーマ株において、**決算発表日は最も株価が激しく動く「両刃の剣」**です。\n"
    text += "- ポジティブなIRが出ても「材料出尽くし」として一時的に売られるケースがあるため、決算発表前の過度な買い煽り局面でのエントリーは避け、発表後の反応を確認する『決算またぎの回避』も有効な手段です。\n"
    text += "- 反対に、期待値が低い割安バリュー株は、僅かな上方修正や株主還元IRだけで株価が大きく跳ね上がります。"
    
    return text

# Create Plotly interactive chart
def create_chart(df, ticker, name):
    fig = make_subplots(
        rows=3, cols=1, 
        shared_xaxes=True, 
        vertical_spacing=0.08, # Spacing increased to prevent subplot titles overlapping
        row_width=[0.2, 0.2, 0.6],
        subplot_titles=("株価 / 移動平均線 / ボリンジャーバンド (-2σから+2σ)", "RSI (相対力指数 - 30/70基準線)", "MACD / シグナル線")
    )
    
    # Row 1: Candlestick
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df['Open'],
            high=df['High'],
            low=df['Low'],
            close=df['Close'],
            name="ローソク足",
            increasing_line_color='#16a34a', # clean green
            decreasing_line_color='#dc2626'  # clean red
        ),
        row=1, col=1
    )
    
    # Row 1: Moving Averages (high visibility on white background)
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA5'], name='5日線', line=dict(color='#d97706', width=1.2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA25'], name='25日線', line=dict(color='#2563eb', width=1.5)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA75'], name='75日線', line=dict(color='#7c3aed', width=1.5)), row=1, col=1)
    
    # Row 1: Bollinger Bands
    fig.add_trace(go.Scatter(x=df.index, y=df['BB_Upper'], name='BB上限 (+2σ)', line=dict(color='rgba(100,116,139,0.3)', width=1, dash='dash')), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=df['BB_Lower'], name='BB下限 (-2σ)', 
        line=dict(color='rgba(100,116,139,0.3)', width=1, dash='dash'),
        fill='tonexty', fillcolor='rgba(37, 99, 235, 0.03)'
    ), row=1, col=1)
    
    # Row 2: RSI
    fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], name='RSI (14)', line=dict(color='#ea580c', width=1.5)), row=2, col=1)
    fig.add_shape(type="line", x0=df.index[0], y0=30, x1=df.index[-1], y1=30, line=dict(color="#dc2626", width=1, dash="dash"), row=2, col=1)
    fig.add_shape(type="line", x0=df.index[0], y0=70, x1=df.index[-1], y1=70, line=dict(color="#16a34a", width=1, dash="dash"), row=2, col=1)
    fig.update_yaxes(range=[10, 90], row=2, col=1)
    
    # Row 3: MACD
    fig.add_trace(go.Scatter(x=df.index, y=df['MACD'], name='MACD', line=dict(color='#2563eb', width=1.5)), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MACD_Signal'], name='シグナル', line=dict(color='#ea580c', width=1.5)), row=3, col=1)
    
    # MACD Hist bars
    hist_colors = ['#16a34a' if val >= 0 else '#dc2626' for val in df['MACD_Hist']]
    fig.add_trace(go.Bar(x=df.index, y=df['MACD_Hist'], name='ヒストグラム', marker_color=hist_colors, opacity=0.5), row=3, col=1)
    
    # Formatting layout
    fig.update_layout(
        xaxis_rangeslider_visible=False,
        height=750,
        template="plotly_white", # White template for clean charting
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=10, r=120, t=35, b=10),
        legend=dict(
            orientation="v",
            yanchor="top",
            y=1.0,
            xanchor="left",
            x=1.02
        )
    )
    
    # Clean grids
    fig.update_yaxes(gridcolor='#f1f5f9', zerolinecolor='#cbd5e1')
    fig.update_xaxes(gridcolor='#f1f5f9')
    
    return fig

def fetch_historical_google_news(query, start_date, end_date):
    import urllib.request
    import urllib.parse
    import re
    import html
    
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')
    
    # Clean query (remove parts in parenthesis)
    search_query = f"{query.split('(')[0].split('（')[0].strip()} after:{start_str} before:{end_str}"
    encoded_query = urllib.parse.quote(search_query)
    
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ja&gl=JP&ceid=JP:ja"
    
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=4) as response:
            xml_data = response.read().decode('utf-8', errors='ignore')
            
        items = re.findall(r'<item>(.*?)</item>', xml_data, re.DOTALL)
        results = []
        for item in items[:5]: # Take top 5 news items
            title_m = re.search(r'<title>(.*?)</title>', item)
            pub_date_m = re.search(r'<pubDate>(.*?)</pubDate>', item)
            link_m = re.search(r'<link>(.*?)</link>', item)
            
            if title_m:
                title = html.unescape(title_m.group(1))
                parts = title.split(" - ")
                if len(parts) > 1:
                    title_clean = " - ".join(parts[:-1])
                    source = parts[-1]
                else:
                    title_clean = title
                    source = ""
                    
                pub_date_str = pub_date_m.group(1) if pub_date_m else ""
                try:
                    date_parts = pub_date_str.split(" ")
                    if len(date_parts) >= 4:
                        day = date_parts[1]
                        month_str = date_parts[2]
                        year_str = date_parts[3]
                        months = {"Jan":"01", "Feb":"02", "Mar":"03", "Apr":"04", "May":"05", "Jun":"06",
                                  "Jul":"07", "Aug":"08", "Sep":"09", "Oct":"10", "Nov":"11", "Dec":"12"}
                        month_num = months.get(month_str[:3], "01")
                        readable_date = f"{year_str}/{month_num}/{day.zfill(2)}"
                    else:
                        readable_date = pub_date_str
                except:
                    readable_date = pub_date_str
                    
                link = link_m.group(1) if link_m else ""
                results.append({"title": title_clean, "date": readable_date, "link": link, "source": source})
        return results
    except Exception as e:
        return []

def fetch_all_historical_news_in_parallel(name, matches_data):
    from concurrent.futures import ThreadPoolExecutor
    
    def fetch_one(m):
        m['news'] = fetch_historical_google_news(name, m['start_date'], m['end_date'])
        
    try:
        with ThreadPoolExecutor(max_workers=len(matches_data)) as executor:
            executor.map(fetch_one, matches_data)
    except Exception as e:
        for m in matches_data:
            if 'news' not in m:
                m['news'] = []

def generate_similar_pattern_explanation(ticker, name, m, N):
    start_dt = m['start_date']
    end_dt = m['end_date']
    similarity = m['similarity']
    all_prices = m['all_prices']
    
    price_at_end = all_prices[N-1]
    price_after = all_prices[-1]
    ret = (price_after - price_at_end) / price_at_end * 100
    
    year = start_dt.year
    month = start_dt.month
    
    # 1. Identify general macro event
    macro_title = "グローバル市場の調整局面"
    macro_desc = "この時期、特に目立った局所的イベントはありませんでしたが、金利動向や市場センチメントの推移に応じて価格形成が行われていました。"
    
    if year == 2018:
        macro_title = "米中貿易摩擦の激化と世界的な景気減速懸念"
        macro_desc = "トランプ大統領（当時）による対中関税発動などから米中対立が深刻化し、世界的にハイテク株や輸出株を中心に株価のボラティリティ（値幅）が激しく高まりました。日本市場も新興株を中心に売り優勢となりました。"
    elif year == 2019:
        if month >= 8 or month <= 11:
            macro_title = "消費税増税（10%へ）と駆け込み需要の反動減"
            macro_desc = "10月の消費税増税前後の時期です。駆け込み需要による小売業の一時的活況とその後の反動減、さらに世界的な米中交渉の行方に神経質な相場展開が続き、内需・ディフェンシブ株が二極化しました。"
        else:
            macro_title = "世界的な金融緩和の推進局面"
            macro_desc = "米FRBが予防的利下げを開始し、日米欧の金融緩和姿勢が改めて材料視されました。半導体セクターの底入れ期待が浮上し、グロース株に買い戻しが入る土台ができました。"
    elif year == 2020:
        if month <= 4:
            macro_title = "新型コロナウイルス（コロナショック）による世界同時暴落"
            macro_desc = "世界的な感染爆発により景気シャットダウン懸念が台頭し、日経平均は一時16,000円台へ急落。市場からリスクマネーが急速に引き揚げられ、全業種がセクターを問わずパニック売りに見舞われました。"
        else:
            macro_title = "コロナ後金融緩和による大規模流動性相場"
            macro_desc = "各国中銀による未曾有の資金供給（ゼロ金利、量的緩和）とテレワーク普及等の「巣ごもり需要」を背景に、IT・通信、DX関連、半導体株などの特定テーマ株が歴史的な急騰劇を演じました。"
    elif year == 2021:
        macro_title = "経済再開（リオープン）期待と金融引き締め懸念の台頭"
        macro_desc = "新型コロナワクチンの本格的普及により、それまで売り込まれていた旅行・空運やバリュー株（鉄鋼・銀行等）に資金が還流する一方、景気回復に伴うインフレ懸念が徐々に市場へ台頭し始めた過渡期です。"
    elif year == 2022:
        if month <= 4:
            macro_title = "ロシア・ウクライナ軍事衝突の勃発と資源価格の暴騰"
            macro_desc = "ロシアによるウクライナ侵攻が開始され、原油や天然ガス、穀物などの資源原材料価格が一段と急騰。コストプッシュ型のインフレ懸念が急激に広がり、グローバル株価は大幅な下落圧力に晒されました。"
        else:
            macro_title = "米FRBの利上げ開始と激しい日米金利差拡大・大幅な円安"
            macro_desc = "インフレ抑制のため米FRBが急速な大幅利上げを開始。日銀の緩和継続姿勢との乖離から、為替は一時1ドル150円台に迫る歴史的な円安が進行し、輸出企業と輸入企業の損益格差が際立ちました。"
    elif year == 2023:
        macro_title = "東証のPBR1倍割れ改善要求とウォーレン・バフェット効果"
        macro_desc = "東京証券取引所による「資本効率・株価意識の経営要求」がサプライズとなり、バリュー株（低PBR株）への見直し買いが活発化。バフェット氏の日本株買い増し報道も加わり、海外機関投資家の巨額マネーが日本株を押し上げました。"
    elif year == 2024:
        if month <= 3:
            macro_title = "日経平均史上最高値更新（4万円突破）とマイナス金利解除"
            macro_desc = "日本企業の業績好調と円安を追い風に、日経平均株価がバブル期の史上最高値を34年ぶりに更新し初の4万円台に到達。日銀がマイナス金利解除を決定し、金利のある世界への転換点が意識されました。"
        elif month >= 7 and month <= 9:
            macro_title = "日銀追加利上げと円高進行、歴史的ボラティリティ上昇（株価大震災）"
            macro_desc = "日銀の追加利上げと米景気後退懸念が重なり、為替が急激に円高方向へ転換。円キャリートレードの巻き戻しから、日経平均は史上最大（-4,451円）の暴落を記録し、その後に急反発する記録的ボラティリティ相場となりました。"
        else:
            macro_title = "新NISA開始と新政権発足に伴う国内株の再評価相場"
            macro_desc = "新NISA制度のスタートにより個人マネーが流入し、自社株買いや増配などの株主還元強化を続ける日本企業が選別される相場環境となりました。政権交代や衆院選などの政治イベントにも値動きが敏感に反応しました。"
    elif year >= 2025:
        macro_title = "金利上昇局面におけるクオリティ株・バリュー株優位の展開"
        macro_desc = "国内の徐々な利上げ観測の強まりから、銀行株や手元資金の厚いキャッシュリッチ企業が堅調に推移する一方、高PBR・無配グロー株などのバリュエーション調整が継続する選別的な相場展開となりました。"

    # 2. Resolve tags
    tags = []
    if ticker in JP_TICKERS:
        tags = JP_TICKERS[ticker].get("tags", [])
    else:
        # Check by code pattern or name
        code = ticker.split(".")[0]
        if code.isdigit():
            code_num = int(code)
            if code_num in [8035, 6857, 6526, 6723, 7735]:
                tags = ["半導体", "電気機器"]
            elif code_num in [7011, 7012, 7013]:
                tags = ["宇宙", "防衛", "機械"]
            elif code_num in [8058, 8031, 8001, 8002]:
                tags = ["商社", "卸売業"]
            elif code_num in [8306, 8316, 8411]:
                tags = ["銀行業", "金融"]
            elif 8300 <= code_num <= 8400 or 8500 <= code_num <= 8599:
                tags = ["銀行業", "金融"]
            elif code_num in [9101, 9104, 9107]:
                tags = ["海運業"]
            elif code_num in [7203, 7267, 7201]:
                tags = ["自動車", "輸送用機器"]
            elif 7200 <= code_num <= 7299:
                tags = ["自動車", "輸送用機器"]
            elif code_num in [8801, 8802]:
                tags = ["不動産業"]
            elif code_num in [9020, 9022]:
                tags = ["陸運業"]
            elif code_num in [9432, 9433, 9984]:
                tags = ["情報通信"]
        
        if not tags:
            if any(k in name for k in ["半導体", "デバイス", "エレクトロン", "アドバンテスト"]):
                tags = ["半導体"]
            elif any(k in name for k in ["宇宙", "重工", "防衛", "航空"]):
                tags = ["宇宙", "防衛"]
            elif any(k in name for k in ["銀行", "フィナンシャル", "信託"]):
                tags = ["銀行業"]
            elif any(k in name for k in ["商社", "物産", "商事"]):
                tags = ["商社"]
            elif any(k in name for k in ["海運", "郵船", "汽船"]):
                tags = ["海運業"]
            elif any(k in name for k in ["自動車", "タイヤ"]):
                tags = ["自動車"]

    # 3. Identify company-specific event (based on ticker and year)
    corp_event = ""
    
    # Specific Ticker Matches
    if ticker == "9984.T":
        if year == 2018:
            corp_event = "10兆円規模の「ソフトバンク・ビジョン・ファンド(SVF)」が本格稼働し、UberやDidi等の海外IT企業への巨額投資が連日報じられました。ファンドとしての性格が強まるなか、株価のボラティリティが大きく高まりました。"
        elif year == 2019:
            corp_event = "投資先の米WeWorkの上場延期と経営難を受け、数千億円規模の評価損を計上する事態となりました。ファンドビジネスの評価モデルに対する市場の不信感が強まり、株価は低迷を余儀なくされました。"
        elif year == 2020:
            if month <= 4:
                corp_event = "コロナショックの直撃により一時株価は半減近くなりましたが、直後に孫正義社長が「4.5兆円の資産売却プログラム」および「2.5兆円の巨額自社株買い」を発表。これが猛烈な買い戻しを呼び込み、株価急回復の起点となりました。"
            else:
                corp_event = "アリババ株式の売却などによる手元資金確保と、2.5兆円の自己株取得が進行し、需給が圧倒的に改善。コロナ禍でのナスダック上場ハイテク株の急騰も手伝い、SBGの純資産価値（NAV）は急増、株価も右肩上がりを続けました。"
        elif year == 2021:
            corp_event = "中国政府によるIT大手（アリババや滴滴など）への規制強化が直撃し、保有資産の評価額が急激に目減りしました。これによりビジョン・ファンドは大きな評価損を被り、株価は調整局面へと移行しました。"
        elif year == 2022:
            corp_event = "米FRBの利上げに伴う世界的なハイテク株（グロース株）の下落により、SVFの保有する公開・未公開株が軒並み急落。過去最大の純損失を計上するなか、投資方針を極めて保守的な「守り」に変更しました。"
        elif year == 2023:
            corp_event = "9月に傘下の英半導体設計大手「Arm」のナスダック上場を成功させ、数兆円規模の含み資産価値が表面化しました。AI半導体需要の拡大も手伝い、オフェンスへの再転換期待から株価は底打ちしました。"
        elif year >= 2024:
            corp_event = "子会社であるArmの株価が生成AIブームで数倍に急騰。SBGの保有資産（NAV）が大幅に向上し、孫社長の「ASI（人工超知能）」構想に基づくAI・データセンター向け超大型投資計画が材料視され、数年ぶりの高値圏を推移しました。"
            
    elif ticker == "7203.T":
        if year == 2020:
            corp_event = "新型コロナによるサプライチェーンの寸断や世界的な新車需要の一時蒸発で工場稼働停止が相次ぎました。しかし秋以降は北米・中国市場での急激な需要回復を捉え、高い危機管理能力によるV字回復を遂げました。"
        elif year == 2021:
            corp_event = "世界的な車載半導体不足による世界規模での減産が繰り返され、生産がボトルネックとなりました。一方でドル円相場が円安基調に転じたことで為替差益が下値を強力に支えました。"
        elif year == 2022:
            corp_event = "歴史的な円安進行（115円から一時150円台へ）により、輸出利益の円建て評価が爆発的に急増。原材料やエネルギーコストの急騰を上回る為替メリットを計上し、バリュー株の代表格として底堅く推移しました。"
        elif year == 2023:
            corp_event = "年末にかけてグループ会社（ダイハツ、豊田自動織機）の品質認証不正問題が相次いで表面化し、一時売りを浴びました。しかし、世界的なEV（電気自動車）需要の失速に伴い、トヨタのハイブリッド車（HEV）の高い利益率と実用性が世界的に見直され、販売は絶好調となりました。"
        elif year >= 2024:
            corp_event = "安全性不正問題の立ち入り検査などが懸念されたものの、ドル円が155円台の歴史的円安水準で推移し、期中決算では日本企業初の「営業利益5兆円」を達成。大規模な自社株買い（最大1兆円）の実行もあり、最高値を大きく更新しました。"

    elif ticker == "3778.T":
        if year <= 2022:
            corp_event = "一般的なクラウド関連株・データセンター運営企業として、市場平均と連動した地味な値動きが続いていました。"
        elif year == 2023:
            corp_event = "経済産業省から「生成AI開発支援のためのスパコン整備事業者」として正式に選定され、政府からの巨額の助成金とGPU調達の優位性が判明。生成AI国策銘柄の筆頭として、個人投資家の投機的な買いが集中し株価は大化けを開始しました。"
        elif year >= 2024:
            corp_event = "NVIDIA製GPUの本格稼働とAI開発需要の拡大により、営業利益の劇的な急増見通しを発表。投資マネーの流入が止まらず、連日株価は乱高下を繰り返し、新興市場きってのスター株として値動きが激化しました。"

    elif ticker == "9348.T":
        if year == 2023:
            corp_event = "4月に民間月面探査プログラム「HAKUTO-R」Mission 1の月面着陸に挑みました。上場直後ということもあり期待値が極限まで高まりましたが、着陸直前に高度誤認により着陸未達（衝突）となり、株価は大きく失望売りに押されました。"
        elif year >= 2024:
            corp_event = "Mission 2および米NASA関連の月面物資輸送プロジェクトの進捗、民間宇宙投資拡大のテーマが繰り返し囃され、宇宙ベンチャー特有の将来期待に基づくボラティリティの非常に高い展開が継続しました。"

    elif ticker == "5595.T":
        if year >= 2023:
            corp_event = "小型SAR衛星の打ち上げ成功、政府やJAXAからの大型プロジェクトの受注発表が頻繁に行われました。国策の防衛・宇宙関連の急騰銘柄として、短期投機資金の出入りによる非常に激しい値動きとなりました。"

    # VTuber Sector Matches (Cover, ANYCOLOR)
    elif "VTuber" in tags:
        if year == 2022:
            corp_event = f"にじさんじを運営するANYCOLORの新規上場を契機に、「VTuberセクター」の営業利益率30％を超える圧倒的な収益モデルが市場に周知され、セクター全体に莫大なプレミアムが乗る『VTuber熱狂相場』が起きた時期です。"
        elif year == 2023:
            corp_event = f"カバー（5253.T）の3月新規上場、および hololive の海外ライブイベントのソールドアウト、新規3Dスタジオ設立による中長期成長ポテンシャルが意識され、国内新興株の中心的存在として物色されました。"
        elif year >= 2024:
            corp_event = f"事業成長自体は高い伸びを維持したものの、グロース株全体のバリュエーション調整や大株主の売却懸念が上値を抑えました。一方でANYCOLORの大規模自社株買いや、カバーのグローバル進出の継続が確認され、業績実態に伴う底固さも見せました。"

    # Sector General Matches
    if not corp_event:
        if "半導体" in tags:
            if year == 2018:
                corp_event = f"スマートフォンの成長鈍化や暗号資産マイニング需要の急減による「シリコンサイクル下落局面」が直撃し、{name} などの半導体セクターの業績悪化懸念が強まり、厳しい調整局面でした。"
            elif year == 2019:
                corp_event = f"米中貿易摩擦の警戒感があったものの、5G導入に向けたデータセンター投資などの先行き期待から半導体セクターが底打ちし、先行投資の動きから株価が徐々に上向いた過渡期です。"
            elif year in [2020, 2021]:
                corp_event = f"コロナ禍によるテレワークの世界的な浸透、クラウド需要拡大に伴うサーバー投資、ゲーム機の品薄が重なり、深刻な「半導体不足」が到来。{name} の工場稼働率は限界まで高まり、空前の受注・業績好調から株価は急騰サイクルを描きました。"
            elif year == 2022:
                corp_event = f"世界的なインフレ抑制に向けた米FRBの大幅利上げが引き金となり、高PEグロース株としてのバリュエーション調整が発生。PC・スマホ需要急冷によるメモリ余剰からシリコンサイクルは下降へ向かい、株価は大きく下落しました。"
            elif year == 2023:
                corp_event = f"5月に米エヌビディア（NVDA）が示した驚異的な業績見通しを機に「生成AIバブル」が本格化。AIサーバー用デバイスや次世代メモリ（HBM）検査向けの需要が殺到し、{name} を含む半導体・電子部品株に世界的な投資マネーが流れ込みました。"
            elif year >= 2024:
                corp_event = f"TSMC熊本工場の稼働など国内半導体再興テーマで年初に急騰したのち、夏場にかけて米国の対中半導体輸出規制強化、円高への巻き戻し、および米AI関連株の反落から、歴史的レベルの急落と乱高下が発生した局面です。"

        elif "宇宙" in tags or "防衛" in tags:
            if year <= 2021:
                corp_event = f"防衛・宇宙関連のビジネスは公共セクターへの依存度が高く、安定しているものの成長期待は低めに見積もられており、{name} の株価はディフェンシブな横ばい推移が中心でした。"
            elif year == 2022:
                corp_event = f"2月のロシア・ウクライナ戦争勃発により防衛環境が一変。日本政府が防衛費の倍増方針（GDP比2%へ）を打ち出し、防衛省向け大型契約（スタンドオフミサイル等）の主契約者である重工セクターを中心に国策銘柄としての大相場が始まりました。"
            elif year == 2023:
                corp_event = f"防衛省との大型契約締結（数百億円〜数千億円）のニュースが相次ぎ、かつJAXA新型ロケット「H3」開発への進捗・成否が注目され、日本の防衛・宇宙の基幹企業として株価は継続的な上昇トレンドを形成しました。"
            elif year >= 2024:
                corp_event = f"H3ロケット2号機・3号機の連続打上げ成功や防衛予算執行の具体化が進み、重工業・宇宙関連セクターは業績への寄与度が高まりました。海外投資家によるインバウンド買いの対象にもなり、株価はバブル期以来の高値を更新する活況を呈しました。"

        elif "商社" in tags:
            if year == 2020:
                corp_event = "8月に米バークシャー・ハサウェイ（ウォーレン・バフェット率いる）が日本の大手商社株を5%ずつ取得したと発表し衝撃が走りました。万年割安・低PBRに放置されていた商社株のグローバルな評価訂正のスタート地点です。"
            elif year in [2021, 2022]:
                corp_event = "経済活動の再開とウクライナ危機に伴い、原油、LNG、石炭、鉄鉱石などの資源価格が歴史的な高値に急騰。商社各社が持つ資源権益からの純利益が爆発的に拡大し、史上最高益更新と増配が株価を大きく押し上げました。"
            elif year == 2023:
                corp_event = "4月にバフェット氏が来日し、商社株の保有比率を引き上げたと表明。これが引き金となり、割安でキャッシュフローの潤沢な日本株バリューセクター全体に海外マネーが殺到。商社株はそのシンボルとして急激な右肩上がりを記録しました。"
            elif year >= 2024:
                corp_event = "大規模な株式分割や積極的な株主還元策（自社株買いや増配）の継続が好感され、資源価格の一服にかかわらず株価は高値圏での推移となりました。日本のデフレ脱却とバリュー株優位の象徴的なセクターとして買いが続きました。"

        elif "銀行業" in tags or "金融" in tags:
            if year <= 2021:
                corp_event = "日銀による長年のマイナス金利政策により、国内での貸出金利マージン（利ざや）が極端に低迷。「収益の伸びない万年低PBRバリュー株」として株価は冷遇され、割安放置が続いていました。"
            elif year == 2022:
                corp_event = "米FRBの利上げ加速に伴う金利上昇を受け、日本でも長期金利が上昇。12月に日銀がYCC（イールドカーブ・コントロール）の変動幅拡大を発表したことで、「金利上昇＝銀行の収益改善」という大転換シナリオが意識され、株価は強気トレンドへ入りました。"
            elif year == 2023:
                corp_event = "3月に米国でのSVB（シリコンバレーバンク）破綻を機に、世界的な金融システム不安が連鎖し銀行セクターは急落に見舞われました。しかし、日銀がYCC上限の1%への修正を行うなど国内金利上昇圧力が続き、下半期には再び高値へ急騰しました。"
            elif year >= 2024:
                corp_event = "3月に日銀がマイナス金利を解除し、金利上昇による預貸金利ざやの拡大期待が現実のものとなりました。メガバンクによる過去最高益と増配の発表、持ち合い株式売却を伴う強力な株主還元姿勢がバリュー株人気の中心として株価を大きく押し上げました。"

        elif "自動車" in tags:
            if year == 2020:
                corp_event = f"新型コロナの世界的な流行により自動車生産および新車販売が一時壊滅的打撃を受けました。しかし後半にかけての需要リバウンドが極めて急激で、業績はV字回復を見せました。"
            elif year == 2021:
                corp_event = f"自動車向け半導体の世界的な枯渇や、サプライチェーンの混乱による「強制的な減産」が重荷となりました。一方、海外の中古車価格高騰などの需要過熱が価格交渉力を生み、実質の収益力は維持されました。"
            elif year == 2022:
                corp_event = f"インフレによる部品や輸送費のコスト増を、急激な円安（1ドル115円から150円へ）による為替換算メリットが補い、結果的に業績が大幅に押し上げられ、バリュー株として底堅く展開となりました。"
            elif year == 2023:
                corp_event = f"車載半導体不足が解消し減産からの生産挽回が本格化。EVの普及スピード減速から、日本メーカーの強みであるハイブリッド車（HEV）の実用性と収益力がグローバルで脚光を浴び、自動車株は軒並み好業績を記録しました。"
            elif year >= 2024:
                corp_event = f"一部メーカーでの認証テスト不正などのスキャンダルによる国内一時稼働停止が株価にブレーキをかけましたが、150円台の超円安基調と好調な北米販売が貢献し、強力な自社株買い発表も手伝い、業績水準に対する割安感から買い直されました。"

        elif "海運業" in tags:
            if year in [2020, 2021]:
                corp_event = "コロナ禍の物流混乱と欧米の巣ごもり消費爆発が重なり、コンテナ船運賃が歴史的暴騰（コンテナバブル）を記録。海運会社の純利益が十数倍に跳ね上がり、配当利回り15〜20%という前代未聞の超高配当相場となり急上昇しました。"
            elif year == 2022:
                corp_event = "コンテナ運賃価格の天井打ちと景気後退への懸念からボラティリティが極限まで高まり、配当の権利落ち前後で凄まじい乱高下を演じるなど、国内屈指のハイベータ株として個人投資家の主戦場となりました。"
            elif year == 2023:
                corp_event = "運賃は正常化しましたが、紅海における地政学的危機による喜望峰迂回ルートへの切り替えが発生し運賃コストが高止まり。さらに東証のPBR改善要請に応える強力な増配や自社株買いが発表され、高配当ディフェンシブ株として再評価されました。"
            elif year >= 2024:
                corp_event = "地政学不安の長期化に伴うコンテナ運賃再騰に加え、自社株買いや増配等の積極的な還元策が評価され、下落シナリオを裏切り再び高値更新を果たすなど、業績と需給が強い状況が維持されました。"

        else:
            # Fallback based on years
            if year == 2018:
                corp_event = f"この期間、世界的な貿易対立による業績悪化懸念から {name} も売り優勢となり、市場平均と連動する形で株価の下押し圧力がかかっていました。"
            elif year == 2020:
                if month <= 4:
                    corp_event = f"新型コロナの世界的な感染拡大に伴うコロナショックが直撃し、{name} の株価も業績やセクターにかかわらずパニック的な売りを浴びました。"
                else:
                    corp_event = f"コロナショック後の金融緩和マネー流入により株価は急回復。実態経済の冷え込みとは裏腹に、過剰流動性相場による株価押し上げメリットを享受した時期です。"
            elif year == 2022:
                corp_event = f"米FRBの利上げに伴うグローバルな株主バリュエーション調整（特にマルチプルの低下）や、為替相場の激しい乱高下が {name} の上値を抑えていました。"
            elif year == 2023:
                corp_event = f"東京証券取引所によるPBR改善要求や、日本市場への海外マネー再流入という市場構造のポジティブな変化のなかで、{name} に対しても資本効率の観点から見直し買いが入りました。"
            elif year >= 2024:
                corp_event = f"日本企業の好業績やデフレ脱却期待という大局的な好材料と、日銀の金融政策決定や為替の円高転換という個別材料が交錯し、ボラティリティが高いなかでも {name} の個別ファンダメンタルズが選別された相場環境でした。"
            else:
                corp_event = f"この時期、{name} のセクター特性に応じた個別の需給変化や季節要因が株価形成の主因となっていました。"

    # Build explaining paragraph
    direction = "上昇" if ret >= 0 else "下落"
    ret_style = f"color: {'#16a34a' if ret >= 0 else '#dc2626'}; font-weight: bold;"
    
    # Render real-time Google News if available
    news_items = m.get('news', [])
    news_html = ""
    if news_items:
        for item in news_items:
            source_badge = f"""<span style="background-color: #e2e8f0; color: #475569; font-size: 0.72rem; padding: 2px 6px; border-radius: 4px; margin-left: 6px; font-weight: 500; display: inline-block; vertical-align: middle;">{item['source']}</span>""" if item['source'] else ""
            news_html += f"""
            <li style="margin-bottom: 6px; list-style-type: square; margin-left: 15px;">
                <span style="color: #64748b; font-size: 0.85rem; font-family: monospace; margin-right: 6px;">[{item['date']}]</span>
                <a href="{item['link']}" target="_blank" style="color: #2563eb; text-decoration: none; font-weight: 500; font-size: 0.88rem; border-bottom: 1px dashed #93c5fd;">{item['title']}</a>
                {source_badge}
            </li>
            """
    else:
        news_html = """
        <li style="margin-bottom: 6px; list-style-type: none; margin-left: 0px; color: #64748b; font-size: 0.88rem;">
            ℹ️ 当時のニュース履歴を取得できませんでした（期間外、またはインデックス未登録）。
        </li>
        """

    explanation = f"""
    <div style="background-color: #f8fafc; border-radius: 8px; padding: 16px; border-left: 4px solid {'#16a34a' if ret >= 0 else '#dc2626'}; margin-bottom: 12px; border-top: 1px solid #e2e8f0; border-right: 1px solid #e2e8f0; border-bottom: 1px solid #e2e8f0;">
        <div style="display: flex; justify-content: space-between; font-weight: bold; margin-bottom: 8px;">
            <span style="font-size: 0.95rem; color: #1e293b;">🕒 類似期間: {start_dt.strftime('%Y-%m-%d')} 〜 {end_dt.strftime('%Y-%m-%d')} (類似度: {similarity:.1f}%)</span>
            <span style="font-size: 1rem; {ret_style}">その後の20営業日の動向: {ret:+.2f}% ({direction})</span>
        </div>
        <div style="font-size: 0.9rem; color: #334155; line-height: 1.6; margin-bottom: 8px;">
            <strong>【当時の主要な時事・市況イベント】：{macro_title}</strong><br/>
            {macro_desc}
        </div>
        <div style="font-size: 0.9rem; color: #334155; line-height: 1.6; border-top: 1px dashed #cbd5e1; padding-top: 8px; margin-bottom: 8px;">
            <strong>📰 当時（同日〜同月内）に報道された主要ニュース（リアルタイム取得）</strong>:<br/>
            <ul style="margin: 6px 0 0 0; padding-left: 5px; line-height: 1.5;">
                {news_html}
            </ul>
        </div>
        <div style="font-size: 0.9rem; color: #1e3a8a; line-height: 1.6; border-top: 1px dashed #cbd5e1; padding-top: 8px; background-color: #f0f5ff; padding: 8px; border-radius: 6px; margin-top: 8px;">
            <strong>🏢 当時の {name} に関係した主要出来事・材料（専門分析）</strong>:<br/>
            {corp_event}
        </div>
    </div>
    """
    return "\n".join([line.strip() for line in explanation.split("\n")])

def generate_final_pattern_implication(name, matches_data, avg_ret):
    avg_color = "#16a34a" if avg_ret >= 0 else "#dc2626"
    avg_sign = "+" if avg_ret >= 0 else ""
    direction_text = "上昇する傾向" if avg_ret >= 0 else "下落（または調整）する傾向"
    
    up_count = 0
    for m in matches_data:
        N = len(m['all_prices']) - 20
        price_at_end = m['all_prices'][N-1]
        price_after = m['all_prices'][-1]
        if price_after >= price_at_end:
            up_count += 1
            
    win_rate = (up_count / len(matches_data)) * 100
    
    if win_rate >= 66:
        strategy = f"過去の類似局面では高い確率で株価が上昇しており、現在の値動きパターンからも**強い順張り（押し目買い・買い追随）**の優位性が期待されます。"
    elif win_rate <= 33:
        strategy = f"過去の類似局面では下落・調整傾向が高く、現在の株価の動きにおいても天井圏での反落や、ブレイク失敗に伴う急落リスクが懸念されます。**利益確定の検討や、押し目を引き付けての慎重なエントリー**が推奨されます。"
    else:
        strategy = f"過去の類似局面における上昇率は二極化しており、方向感は中立です。チャート形状単体でのエントリー判断は避け、直近の出来高やファンダメンタルズの動向、決算発表スケジュール等を併せて考慮すべき局面です。"

    text = f"""
    <div style="background-color: #f8fafc; border-left: 5px solid {avg_color}; border-radius: 8px; padding: 20px; margin-top: 20px; box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05); border-top: 1px solid #e2e8f0; border-right: 1px solid #e2e8f0; border-bottom: 1px solid #e2e8f0;">
        <h5 style="margin: 0 0 10px 0; color: #1e293b; font-size: 1.05rem;">💡 歴史的パターンから導かれる総合考察</h5>
        <div style="font-size: 0.95rem; color: #334155; line-height: 1.6; margin-bottom: 12px;">
            過去5年間のデータから抽出された類似パターン上位3例において、形状終了から20営業日後の平均騰落率は 
            <strong style="color: {avg_color}; font-size: 1.2rem;">{avg_sign}{avg_ret:.2f}%</strong> となり、
            過去の統計上は<strong>{direction_text}</strong>が見られます。（3回中 {up_count} 回で上昇）
        </div>
        <div style="font-size: 0.92rem; color: #475569; line-height: 1.6; border-top: 1px dashed #cbd5e1; padding-top: 12px;">
            <strong>🎯 推奨される投資戦略のアプローチ：</strong><br/>
            {strategy}
        </div>
    </div>
    """
    return "\n".join([line.strip() for line in text.split("\n")])

def render_detail_dashboard(selected_ticker, selected_name, raw_analysis, key_suffix=""):
    # Get owned stock details for the dashboard
    portfolio = load_portfolio()
    owned_rec = next((r for r in portfolio.get("purchase_records", []) if r["ticker"] == selected_ticker), None)
    if owned_rec:
        qty_str = f"{int(owned_rec['quantity']):,}株" if not is_us_stock(selected_ticker) else f"{owned_rec['quantity']:,.2f}株" if int(owned_rec['quantity']) != owned_rec['quantity'] else f"{int(owned_rec['quantity']):,}株"
        owned_text = f"保有中: {qty_str}"
        owned_sub = f"取得単価: {format_price(owned_rec['purchase_price'], selected_ticker)}"
        owned_color = "#16a34a" # Green
    else:
        owned_text = "未保有"
        owned_sub = "シミュレーション未登録"
        owned_color = "#64748b" # Grey

    metrics = raw_analysis['metrics']

    # Layout for detailed metrics and Watchlist add/remove button
    watchlist = load_watchlist()
    is_favorite = selected_ticker in watchlist
    
    wl_col1, wl_col2 = st.columns([3.8, 1.2])
    with wl_col1:
        st.markdown(f"#### {selected_name} ({selected_ticker}) の分析ダッシュボード")
    with wl_col2:
        if is_favorite:
            if st.button("⭐ お気に入り解除", key=f"fav_btn_{selected_ticker}{key_suffix}", use_container_width=True):
                del watchlist[selected_ticker]
                save_watchlist(watchlist)
                st.rerun()
        else:
            if st.button("☆ お気に入り追加", key=f"fav_btn_{selected_ticker}{key_suffix}", use_container_width=True):
                watchlist[selected_ticker] = selected_name
                save_watchlist(watchlist)
                st.rerun()

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        st.markdown(f"""<div class="card">
             <div class="metric-title">現在株価</div>
             <div class="metric-value metric-accent">{format_price(metrics['price'], selected_ticker)}</div>
         </div>""", unsafe_allow_html=True)
    with col2:
        st.markdown(f"""<div class="card">
             <div class="metric-title">前日比</div>
             <div class="metric-value" style="color: {'#16a34a' if metrics['change_pct'] >= 0 else '#dc2626'}">{metrics['change_pct']:.2f}%</div>
         </div>""", unsafe_allow_html=True)
    with col3:
        st.markdown(f"""<div class="card">
             <div class="metric-title">PER (倍)</div>
             <div class="metric-value">{f"{metrics['per']:.1f}" if metrics['per'] is not None else "N/A"}</div>
         </div>""", unsafe_allow_html=True)
    with col4:
        st.markdown(f"""<div class="card">
             <div class="metric-title">PBR (倍)</div>
             <div class="metric-value">{f"{metrics['pbr']:.2f}" if metrics['pbr'] is not None else "N/A"}</div>
         </div>""", unsafe_allow_html=True)
    with col5:
        st.markdown(f"""<div class="card">
             <div class="metric-title">配当利回り</div>
             <div class="metric-value">{f"{metrics['dividend_yield']:.2f}%" if metrics['dividend_yield'] is not None else "N/A"}</div>
         </div>""", unsafe_allow_html=True)
    with col6:
        st.markdown(f"""<div class="card" style="border-left: 4px solid {owned_color};">
             <div class="metric-title">保有状況</div>
             <div class="metric-value" style="color: {owned_color};">{owned_text}</div>
             <div style="font-size: 0.8rem; color: #64748b; margin-top: 2px;">{owned_sub}</div>
         </div>""", unsafe_allow_html=True)
    
    # CSS styling to stretch st.segmented_control to full width and make buttons equal width
    st.markdown("""
    <style>
    div[data-testid="stSegmentedControl"] {
        width: 100% !important;
    }
    div[data-testid="stSegmentedControl"] > div {
        display: flex !important;
        width: 100% !important;
        flex-direction: row !important;
        gap: 8px !important;
    }
    div[data-testid="stSegmentedControl"] button {
        flex: 1 1 0% !important;
        text-align: center !important;
        font-size: 0.95rem !important;
        padding: 10px 16px !important;
        white-space: nowrap !important;
        font-weight: 600 !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # Use st.segmented_control to completely avoid tab reset on rerun
    tab_options = [
        "📈 チャート・指標", 
        "💡 事業カタリスト",
        "📊 財務データ分析",
        "🔍 類似パターン検索"
    ]
    selected_tab = st.segmented_control(
        "詳細分析メニュー",
        options=tab_options,
        default=tab_options[0],
        key=f"det_tab_select_{selected_ticker}{key_suffix}",
        label_visibility="collapsed"
    )
    if not selected_tab:
        selected_tab = tab_options[0]
    
    if selected_tab == "📈 チャート・指標":
        # Display chart and report vertically for better readability
        fig = create_chart(raw_analysis['df'], selected_ticker, selected_name)
        st.plotly_chart(fig, use_container_width=True)
        
        report_md = generate_recommendation_text(
            ticker=selected_ticker,
            name=selected_name,
            tech_score=raw_analysis['tech_score'],
            fund_score=raw_analysis['fund_score'],
            signals=raw_analysis['signals'],
            metrics=raw_analysis['metrics']
        )
        st.markdown(f'<div class="card" style="padding: 25px; margin-top: 15px;">{report_md}</div>', unsafe_allow_html=True)
            
    elif selected_tab == "💡 事業カタリスト":
        # Business & IR analysis
        ir_md = generate_ir_catalysts(
            ticker=selected_ticker,
            tags=raw_analysis.get('tags', []),
            info=raw_analysis.get('info_raw', {})
        )
        st.markdown(f'<div class="card" style="padding: 25px; max-height: 720px; overflow-y: auto;">{ir_md}</div>', unsafe_allow_html=True)
        
    elif selected_tab == "📊 財務データ分析":
        # Fundamental details formatted vertically
        st.markdown("### 財政状態と詳細財務データ")
        
        net_inc = metrics.get('net_income')
        op_m = metrics.get('op_margin')
        cash = metrics.get('total_cash')
        debt = metrics.get('total_debt')
        de_ratio = metrics.get('debt_equity')
        
        if net_inc is not None:
            finance_status = "黒字" if net_inc > 0 else "赤字"
            finance_color = "#16a34a" if net_inc > 0 else "#dc2626"
            status_text = f"<span style='color: {finance_color}; font-weight: bold;'>{finance_status}</span>"
        else:
            status_text = "N/A"
            
        st.markdown(f"""
        <div class="card" style="padding: 25px; line-height: 1.8;">
            <h4 style="margin: 0 0 15px 0;">財務基盤と収益性サマリー</h4>
            <ul style="list-style-type: none; padding-left: 0; margin: 0;">
                <li style="border-bottom: 1px solid #f1f5f9; padding: 10px 0;">
                    <strong>当期純損益の状態</strong>: {status_text} (当期利益額: {format_large_jpy(net_inc)})
                </li>
                <li style="border-bottom: 1px solid #f1f5f9; padding: 10px 0;">
                    <strong>本業の営業利益率</strong>: {f"{op_m:.2f}%" if op_m is not None else "N/A"}
                </li>
                <li style="border-bottom: 1px solid #f1f5f9; padding: 10px 0;">
                    <strong>手元現預金残高</strong>: {format_large_jpy(cash)}
                </li>
                <li style="border-bottom: 1px solid #f1f5f9; padding: 10px 0;">
                    <strong>有利子負債残高</strong>: {format_large_jpy(debt)}
                </li>
                <li style="border-bottom: 1px solid #f1f5f9; padding: 10px 0;">
                    <strong>有利子負債 / 自己資本比率 (D/E)</strong>: {f"{de_ratio:.2f}%" if de_ratio is not None else "N/A"}
                </li>
                <li style="padding: 10px 0 0 0;">
                    <strong>企業時価総額</strong>: {format_large_jpy(metrics.get('market_cap'))}
                </li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
        
    elif selected_tab == "🔍 類似パターン検索":
        st.markdown("### 🔍 類似パターン検索 (直近5年履歴対比)")
        st.markdown("""
        株価チャート上の任意の範囲（日付範囲）を指定し、その期間の値動き（形状）と最も類似した局面を直近5年間の歴史的データから検索します。
        過去に同じような値動きをした後、株価がどのように動いたかを分析することで、今後の投資戦略の参考にできます。
        """)
        
        df_current = raw_analysis['df']
        if df_current.empty:
            st.info("データが読み込めません。")
        else:
            min_date = df_current.index[0].date()
            max_date = df_current.index[-1].date()
            
            default_start = df_current.index[-21].date() if len(df_current) > 20 else min_date
            default_end = max_date
            
            range_key = f"pattern_range_{selected_ticker}{key_suffix}"
            chart_key = f"select_chart_{selected_ticker}{key_suffix}"
            if range_key not in st.session_state:
                st.session_state[range_key] = (default_start, default_end)
            
            # Sync from Plotly drag selection
            if chart_key in st.session_state:
                select_event = st.session_state[chart_key]
                if select_event and "selection" in select_event and "x" in select_event["selection"] and len(select_event["selection"]["x"]) >= 2:
                    x_range = select_event["selection"]["x"]
                    try:
                        sel_start = pd.to_datetime(x_range[0]).date()
                        sel_end = pd.to_datetime(x_range[-1]).date()
                        if (sel_start, sel_end) != st.session_state[range_key]:
                            st.session_state[range_key] = (sel_start, sel_end)
                    except Exception:
                        pass
            
            st.markdown("#### 1. 比較基準とする期間の選択")
            st.caption("💡 下部の日付スライダーのツマミを直接ドラッグして赤い境界線を動かすか、チャート上の任意の範囲を新しくマウスで左右にドラッグ（範囲選択）して期間を指定してください（※グラフ上の赤い線自体を直接掴んで動かすことはできません）。")
            
            chart_container = st.container()
            
            selected_range = st.slider(
                "基準となる値動きの期間を指定してください (2本の赤い縦線の範囲)：",
                min_value=min_date,
                max_value=max_date,
                value=st.session_state[range_key],
                format="YYYY-MM-DD",
                key=f"pattern_range_slider_{selected_ticker}{key_suffix}"
            )
            
            if selected_range != st.session_state[range_key]:
                st.session_state[range_key] = selected_range
            
            with chart_container:
                fig_select = create_selection_chart(
                    df_current, 
                    selected_ticker, 
                    selected_name, 
                    st.session_state[range_key][0], 
                    st.session_state[range_key][1]
                )
                fig_select.update_layout(dragmode="select")
                
                st.plotly_chart(
                    fig_select, 
                    on_select="rerun", 
                    key=chart_key
                )
            
            start_date_pd = localize_timestamp(st.session_state[range_key][0], df_current.index.tz)
            end_date_pd = localize_timestamp(st.session_state[range_key][1], df_current.index.tz)
            
            df_target = df_current.loc[start_date_pd : end_date_pd]
            N_len = len(df_target)
            st.info(f"選択された期間：**{st.session_state[range_key][0]} 〜 {st.session_state[range_key][1]}** (計 **{N_len}** 営業日)")
            
            if N_len < 5:
                st.warning("⚠️ パターン照合には、少なくとも5営業日以上の期間を選択してください。")
            else:
                if st.button("類似パターン検索を実行する", type="primary", key=f"run_pattern_search_{selected_ticker}{key_suffix}", use_container_width=True):
                    with st.spinner("直近5年の歴史データを読み込み、形状パターンマッチングを計算中..."):
                        df_5y = get_stock_5y_history(selected_ticker)
                        if df_5y.empty:
                            st.error("直近5年の株価データを取得できませんでした。")
                        else:
                            target_prices = df_target['Close'].values
                            Z_target = z_normalize(target_prices)
                            
                            matches = []
                            for i in range(len(df_5y) - N_len - 20 + 1):
                                window_df = df_5y.iloc[i : i + N_len]
                                w_start = window_df.index[0]
                                w_end = window_df.index[-1]
                                
                                w_start_dt = w_start.date() if hasattr(w_start, 'date') else w_start
                                w_end_dt = w_end.date() if hasattr(w_end, 'date') else w_end
                                target_start_dt = st.session_state[range_key][0]
                                target_end_dt = st.session_state[range_key][1]
                                
                                if not (w_end_dt < target_start_dt or w_start_dt > target_end_dt):
                                    continue
                                    
                                window_prices = window_df['Close'].values
                                if np.any(np.isnan(window_prices)):
                                    continue
                                    
                                Z_hist = z_normalize(window_prices)
                                r = np.dot(Z_target, Z_hist) / N_len
                                similarity = max(0.0, r * 100)
                                
                                end_idx = min(len(df_5y), i + N_len + 20)
                                all_prices = df_5y['Close'].iloc[i : end_idx].values
                                
                                matches.append({
                                    'similarity': similarity,
                                    'start_date': w_start,
                                    'end_date': w_end,
                                    'all_prices': all_prices
                                })
                            
                            matches = sorted(matches, key=lambda x: x['similarity'], reverse=True)
                            
                            # Filter close matches
                            filtered_matches = []
                            for m in matches:
                                too_close = False
                                for fm in filtered_matches:
                                    if abs((m['start_date'] - fm['start_date']).days) < 30:
                                        too_close = True
                                        break
                                if not too_close:
                                    filtered_matches.append(m)
                                if len(filtered_matches) >= 3:
                                    break
                                    
                            st.session_state[f"pattern_matches_{selected_ticker}{key_suffix}"] = {
                                'target_prices': target_prices,
                                'matches': filtered_matches,
                                'N': N_len
                            }
                
                # Render results if cached in session state
                match_cache_key = f"pattern_matches_{selected_ticker}{key_suffix}"
                if match_cache_key in st.session_state:
                    data_matches = st.session_state[match_cache_key]
                    target_prices = data_matches['target_prices']
                    matches_data = data_matches['matches']
                    N_val = data_matches['N']
                    
                    if not matches_data:
                        st.warning("類似するパターンが見つかりませんでした。")
                    else:
                        st.markdown("---")
                        st.markdown("### 📊 検索結果とパターン比較")
                        
                        fig_pattern = create_pattern_overlay_chart(target_prices, matches_data, N_val, selected_ticker)
                        st.plotly_chart(fig_pattern, use_container_width=True)
                        
                        st.markdown("#### 類似期間の詳細データと「その後」の値動き")
                        
                        table_rows = []
                        t0_price = target_prices[0] if target_prices[0] != 0 else 1
                        for idx, m in enumerate(matches_data):
                            all_prices = m['all_prices']
                            price_at_end = all_prices[N_val-1]
                            price_after = all_prices[-1]
                            ret = (price_after - price_at_end) / price_at_end * 100
                            
                            a0_price = all_prices[0] if all_prices[0] != 0 else 1
                            scale_factor = t0_price / a0_price
                            scaled_price_at_end = price_at_end * scale_factor
                            scaled_price_after = price_after * scale_factor
                            
                            ret_str = f"{ret:+.2f}%"
                            
                            table_rows.append({
                                "順位": f"{idx+1}位",
                                "類似度": f"{m['similarity']:.1f}%",
                                "歴史的期間": f"{m['start_date'].strftime('%Y-%m-%d')} 〜 {m['end_date'].strftime('%Y-%m-%d')}",
                                "パターン終了時株価 (円)": f"¥{int(scaled_price_at_end):,}",
                                "20営業日後の株価 (円)": f"¥{int(scaled_price_after):,}",
                                "その後の上昇・下落率": ret_str,
                                "raw_ret": ret
                            })
                            
                        df_table = pd.DataFrame(table_rows)
                        
                        def style_ret(val):
                            if isinstance(val, str):
                                if val.startswith('+'): return 'color: #16a34a; font-weight: bold;'
                                elif val.startswith('-'): return 'color: #dc2626; font-weight: bold;'
                            return ''
                            
                        styled_df = df_table.style.map(style_ret, subset=["その後の上昇・下落率"])
                        st.dataframe(styled_df, use_container_width=True, hide_index=True)
                        
                        st.markdown("#### 🕒 各類似期間における背景・市況分析")
                        fetch_all_historical_news_in_parallel(selected_name, matches_data)
                        for m in matches_data:
                            expl_html = generate_similar_pattern_explanation(selected_ticker, selected_name, m, N_val)
                            st.markdown(expl_html, unsafe_allow_html=True)
                            
                        avg_ret = df_table['raw_ret'].mean()
                        implication_html = generate_final_pattern_implication(selected_name, matches_data, avg_ret)
                        st.markdown(implication_html, unsafe_allow_html=True)
        
    # Virtual simulated trading panel inside function
    st.markdown("#### 💼 仮想シミュレーション（デモトレード）に追加 / 売却")
    sim_col1, sim_col2 = st.columns([3, 1])
    with sim_col1:
        lot_size = 1 if is_us_stock(selected_ticker) else 100
        lot_desc = "米国株は1株単位推奨" if is_us_stock(selected_ticker) else "日本株は100株単位推奨"
        sim_qty = st.number_input(
            f"購入・売却株数 ({lot_desc} / 1単元={format_price(metrics['price'] * lot_size, selected_ticker)})", 
            min_value=1, 
            value=lot_size, 
            step=1, 
            format="%d", 
            key=f"purchase_qty_input_{selected_ticker}{key_suffix}"
        )
        
        current_price_val = metrics['price']
        total_cost = sim_qty * current_price_val
        usdjpy_rate = get_usdjpy_rate()
        if is_us_stock(selected_ticker):
            st.write(f"概算売買金額: **{format_price(total_cost, selected_ticker)}** (約 ¥{int(total_cost * usdjpy_rate):,})")
        else:
            st.write(f"概算売買金額: **{format_price(total_cost, selected_ticker)}**")
    with sim_col2:
        st.write("") # スペース調整
        st.write("")
        if st.button("仮想購入する", type="primary", use_container_width=True, key=f"sim_purchase_btn_{selected_ticker}{key_suffix}"):
            portfolio = load_portfolio()
            purchase_records = portfolio.get("purchase_records", [])
            
            existing_rec = next((r for r in purchase_records if r["ticker"] == selected_ticker), None)
            if existing_rec:
                old_qty = existing_rec["quantity"]
                old_price = existing_rec["purchase_price"]
                new_qty = old_qty + sim_qty
                new_invest_amount = (old_qty * old_price) + (sim_qty * current_price_val)
                new_price = new_invest_amount / new_qty
                
                existing_rec["quantity"] = float(new_qty)
                existing_rec["purchase_price"] = float(new_price)
                existing_rec["invest_amount"] = float(new_invest_amount)
                existing_rec["purchase_date"] = datetime.date.today().strftime("%Y-%m-%d")
            else:
                purchase_records.append({
                    "ticker": selected_ticker,
                    "name": selected_name,
                    "purchase_date": datetime.date.today().strftime("%Y-%m-%d"),
                    "purchase_price": float(current_price_val),
                    "invest_amount": float(total_cost),
                    "quantity": float(sim_qty)
                })
            
            portfolio["purchase_records"] = purchase_records
            last_prices = portfolio.get("last_valid_prices", {})
            last_prices[selected_ticker] = float(current_price_val)
            portfolio["last_valid_prices"] = last_prices
            
            if save_portfolio(portfolio):
                st.session_state['show_purchase_dialog'] = {
                    'name': selected_name,
                    'ticker': selected_ticker,
                    'qty': int(sim_qty),
                    'price': float(current_price_val),
                    'total_cost': float(total_cost)
                }
                st.rerun()

        # Add virtual sell button directly inside this dashboard!
        if owned_rec and owned_rec["quantity"] > 0:
            if st.button("仮想売却する", type="secondary", use_container_width=True, key=f"sim_sell_btn_{selected_ticker}{key_suffix}"):
                if sim_qty > owned_rec["quantity"]:
                    st.error(f"保有数量（{int(owned_rec['quantity']):,}株）を超える売却はできません。")
                else:
                    portfolio = load_portfolio()
                    purchase_records = portfolio.get("purchase_records", [])
                    sales_records = portfolio.get("sales_records", [])
                    
                    target_rec = next((r for r in purchase_records if r["ticker"] == selected_ticker), None)
                    p_price = target_rec["purchase_price"]
                    
                    pl = (current_price_val - p_price) * sim_qty
                    
                    # Convert USD PL to JPY for realized PL total calculation
                    rate = get_usdjpy_rate() if is_us_stock(selected_ticker) else 1.0
                    pl_jpy = pl * rate
                    
                    sales_records.append({
                        "ticker": selected_ticker,
                        "name": selected_name,
                        "sell_date": datetime.date.today().strftime("%Y-%m-%d"),
                        "purchase_price": float(p_price),
                        "sell_price": float(current_price_val),
                        "quantity": float(sim_qty),
                        "realized_pl": float(pl),
                        "currency": "USD" if is_us_stock(selected_ticker) else "JPY"
                    })
                    
                    target_rec["quantity"] -= float(sim_qty)
                    target_rec["invest_amount"] -= float(sim_qty * p_price)
                    
                    if target_rec["quantity"] <= 0:
                        purchase_records.remove(target_rec)
                        
                    portfolio["purchase_records"] = purchase_records
                    portfolio["sales_records"] = sales_records
                    portfolio["total_realized_pl_jpy"] += float(pl_jpy)
                    
                    if save_portfolio(portfolio):
                        st.session_state['show_sell_dialog'] = {
                            'name': selected_name,
                            'ticker': selected_ticker,
                            'qty': int(sim_qty),
                            'price': float(current_price_val),
                            'total_return': float(sim_qty * current_price_val),
                            'realized_pl': float(pl)
                        }
                        st.rerun()

# Virtual Portfolio Data Persistence
PORTFOLIO_FILE = "virtual_portfolio.json"

def get_portfolio_filename():
    user_key = st.session_state.get('user_key', 'default')
    safe_key = "".join([c for c in str(user_key) if c.isalnum() or c in ('-', '_')]).strip()
    if not safe_key or safe_key == "default":
        return PORTFOLIO_FILE
    return f"virtual_portfolio_{safe_key}.json"

def load_portfolio():
    filename = get_portfolio_filename()
    if not os.path.exists(filename):
        return {
            "purchase_records": [],
            "sales_records": [],
            "total_realized_pl_jpy": 0.0,
            "last_valid_prices": {},
            "watchlist": {}
        }
    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Ensure keys exist
            if "purchase_records" not in data:
                data["purchase_records"] = []
            if "sales_records" not in data:
                data["sales_records"] = []
            if "total_realized_pl_jpy" not in data:
                data["total_realized_pl_jpy"] = 0.0
            if "last_valid_prices" not in data:
                data["last_valid_prices"] = {}
            if "watchlist" not in data:
                data["watchlist"] = {}
            return data
    except Exception as e:
        st.error(f"ポートフォリオデータの読み込みエラー ({filename}): {e}")
        return {
            "purchase_records": [],
            "sales_records": [],
            "total_realized_pl_jpy": 0.0,
            "last_valid_prices": {},
            "watchlist": {}
        }

def load_watchlist():
    portfolio = load_portfolio()
    return portfolio.get("watchlist", {})

def save_watchlist(watchlist):
    portfolio = load_portfolio()
    portfolio["watchlist"] = watchlist
    save_portfolio(portfolio)

def save_portfolio(data):
    filename = get_portfolio_filename()
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        st.error(f"ポートフォリオデータの保存エラー ({filename}): {e}")
        return False

# CSS styling color coding for tables
def color_pl_cell(val):
    if isinstance(val, str):
        if '+' in val:
            return 'color: #16a34a; font-weight: bold;'
        elif '-' in val:
            return 'color: #dc2626; font-weight: bold;'
    return ''

# Sidebar setup for personalizing portfolios
query_user = st.query_params.get("user", "default")

if query_user == "default":
    # ---------------------------------------------------------
    # WELCOME PORTAL PAGE (Shown when no user ID is set)
    # ---------------------------------------------------------
    st.markdown("""
    <div class="title-container" style="text-align: center; margin-top: 40px; margin-bottom: 20px;">
        <h1 class="title-text" style="font-size: 2.5rem; color: #1e3a8a;">Rising Stock Screener</h1>
        <p class="subtitle-text" style="font-size: 1.1rem; color: #64748b;">AI分析とファンダメンタルズによる上昇期待銘柄選定システム</p>
    </div>
    """, unsafe_allow_html=True)
    
    col_w1, col_w2, col_w3 = st.columns([0.8, 2.4, 0.8])
    with col_w2:
        st.markdown("""
        <div style="background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 30px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); margin-bottom: 20px;">
            <h3 style="font-size: 1.3rem; font-weight: bold; margin-bottom: 15px; color: #0f172a; text-align: center; border-bottom: 2px solid #f1f5f9; padding-bottom: 10px;">
                👤 マイページ（専用フォルダ）へのログイン
            </h3>
            <p style="font-size: 0.95rem; color: #475569; margin-bottom: 20px; line-height: 1.6;">
                本システムは、ユーザーごとに独立したポートフォリオ、デモトレード記録、お気に入り銘柄（ウォッチリスト）を管理できます。<br>
                下にお名前または専用IDを入力してマイページにアクセスしてください。
            </p>
        """, unsafe_allow_html=True)
        
        entered_id = st.text_input(
            "名前・専用IDを入力してください（半角英数字のみ）",
            value="",
            placeholder="例: takkun, user_abc",
            autocomplete="off",
            key="portal_user_id_input"
        )
        
        st.markdown("""
            <div style="background-color: #fef2f2; border-left: 4px solid #ef4444; padding: 12px 15px; border-radius: 4px; margin-top: 15px; margin-bottom: 20px;">
                <span style="font-size: 0.85rem; color: #991b1b; font-weight: bold; display: block; margin-bottom: 3px;">⚠️ 注意事項</span>
                <span style="font-size: 0.8rem; color: #7f1d1d; line-height: 1.4; display: block;">
                    初めて入力された名前の場合は、自動的にその名前で新しい専用マイページファイルが作成されます。<br>
                    <b>入力した名前を忘れると、これまでのデモトレードやウォッチリストの記録にアクセスできなくなります</b>ので、必ず名前をメモするか、アクセス後のURLをブックマークして保存してください。
                </span>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button("🚀 マイページを開く", type="primary", use_container_width=True, key="portal_login_btn"):
            safe_id = "".join([c for c in str(entered_id) if c.isalnum() or c in ('-', '_')]).strip()
            if safe_id:
                st.query_params["user"] = safe_id
                st.session_state['user_key'] = safe_id
                st.rerun()
            else:
                st.error("有効な名前（英数字のみ）を入力してください。")
    # Stop execution of the remaining script
    st.stop()

# ---------------------------------------------------------
# MAIN APP INTERFACE (Shown when user ID is set)
# ---------------------------------------------------------
st.sidebar.markdown("### 👤 専用ページの切り替え")
user_key = st.sidebar.text_input(
    "名前・専用IDを入力してください",
    value=query_user,
    autocomplete="off",
    help="ここに名前（半角英数字）を入力すると、他のユーザーと混ざらない『あなた専用のページ』に切り替わります。同じIDを入力すれば別のデバイスからもアクセス可能です。"
)
st.sidebar.caption("💡 **【重要】** 初めて入力されたIDであなた専用のマイページファイルが自動作成されます。**IDを忘れるとこれまでの取引データにアクセスできなくなります**ので、必ずIDをメモするか、URLをブックマークして保存してください。")

if st.sidebar.button("🚪 ログアウト (ログイン画面に戻る)", use_container_width=True, key="sidebar_logout_btn"):
    st.query_params["user"] = "default"
    st.session_state['user_key'] = "default"
    st.rerun()

st.session_state['user_key'] = user_key
st.query_params["user"] = user_key

# Initialize portfolio data in session state
portfolio_data = load_portfolio()

# UI LAYOUT
# Check if we need to show the purchase dialog
if 'show_purchase_dialog' in st.session_state:
    dlg_data = st.session_state['show_purchase_dialog']
    show_purchase_success_dialog(
        name=dlg_data['name'],
        ticker=dlg_data['ticker'],
        qty=dlg_data['qty'],
        price=dlg_data['price'],
        total_cost=dlg_data['total_cost']
    )
    del st.session_state['show_purchase_dialog']

if 'show_sell_dialog' in st.session_state:
    dlg_data = st.session_state['show_sell_dialog']
    show_sell_success_dialog(
        name=dlg_data['name'],
        ticker=dlg_data['ticker'],
        qty=dlg_data['qty'],
        price=dlg_data['price'],
        total_return=dlg_data['total_return'],
        realized_pl=dlg_data['realized_pl']
    )
    del st.session_state['show_sell_dialog']

# Header
st.markdown("""
<div class="title-container">
    <h1 class="title-text">Rising Stock Screener</h1>
    <p class="subtitle-text">AI分析とファンダメンタルズ指標による日本株上昇期待銘柄の選定システム</p>
</div>
""", unsafe_allow_html=True)

# Persistent purchase success alert
if 'purchase_success_msg' in st.session_state:
    st.success(st.session_state['purchase_success_msg'])
    del st.session_state['purchase_success_msg']

# Main Navigation Tabs
tab_screen, tab_favorite, tab_simulation, tab_explanation = st.tabs([
    "🔍 スクリーニング実行と結果分析", 
    "⭐ 保有・お気に入り銘柄の分析",
    "💼 仮想シミュレーション（デモトレード）", 
    "📚 指標とシグナルの解説"
])

# -----------------------------------------------------------------------------
# TAB 1: SCREENING & ANALYSIS
# -----------------------------------------------------------------------------
with tab_screen:
    st.markdown("### ⚙️ スクリーニング条件の設定")
    
    col_cfg1, col_cfg2, col_cfg3 = st.columns([1.5, 1.5, 1.0])
    with col_cfg1:
        market = st.selectbox(
            "全体集合（スクリーニング対象）の選択",
            [
                f"日本株 厳選トレンド銘柄 ({len(JP_TICKERS)}件)",
                f"米国株 厳選トレンド銘柄 ({len(US_TICKERS)}件)",
                "日経平均株価 (日経225全銘柄 - 動的取得)",
                "カスタム指定"
            ],
            key="scr_market"
        )
    with col_cfg2:
        theme_filter = st.selectbox(
            "トレンドテーマ絞り込み",
            [
                "すべて",
                "AI・半導体関連",
                "宇宙産業・開発関連",
                "爆発的急騰期待株",
                "高配当・バリュー株",
                "暗号資産・ネットミーム・ハイベータ",
                "エンタメ・VTuber・ゲーム",
                "防衛・宇宙・重工業"
            ],
            key="scr_theme"
        )
    with col_cfg3:
        period = st.selectbox("データ期間 (チャート用)", ["6ヶ月", "1年", "2年"], index=1, key="scr_period")
        period_map = {"6ヶ月": "6m", "1年": "1y", "2年": "2y"}
        selected_period = period_map[period]

    # Custom tickers input
    custom_tickers = ""
    if market == "カスタム指定":
        custom_tickers = st.text_area(
            "カスタムティッカー入力",
            placeholder="例: 7203.T, 6758.T, 9984.T\n(カンマまたは改行で区切ってください)",
            help="日本株は末尾に .T をつけてください (例: トヨタは 7203.T)",
            key="scr_custom_tickers"
        )

    # Details expander for score and financial criteria
    with st.expander("📊 詳細なスコア・財務条件フィルタ (クリックで開閉)", expanded=False):
        col_f1, col_f2, col_f3 = st.columns([1.3, 1.3, 1.4])
        with col_f1:
            st.markdown("**🎯 最小スコア設定**")
            min_total_score = st.slider("最小総合スコア (最大10点)", 0, 10, 5, key="scr_min_total")
            min_tech_score = st.slider("最小テクニカルスコア (最大3点)", 0, 3, 1, key="scr_min_tech")
            min_fund_score = st.slider("最小ファンダメンタルスコア (最大7点)", 0, 7, 3, key="scr_min_fund")
        with col_f2:
            st.markdown("**💰 財務指標フィルタ**")
            filter_pbr = st.checkbox("PBR 1.0倍未満 (割安バリュー) のみ", key="scr_filter_pbr")
            filter_per = st.checkbox("PER 15倍未満 (低PER) のみ", key="scr_filter_per")
            filter_roe = st.checkbox("ROE 10%以上 (高PBR効率) のみ", key="scr_filter_roe")
            filter_dividend = st.checkbox("配当利回り 3%以上 のみ", key="scr_filter_dividend")
        with col_f3:
            st.markdown("**📈 テクニカル指標フィルタ**")
            filter_golden_cross = st.checkbox("5日/25日ゴールデンクロス", key="scr_filter_gc")
            filter_macd_cross = st.checkbox("MACDゴールデンクロス", key="scr_filter_macd")
            filter_rsi_oversold = st.checkbox("RSI 30以下 (売られすぎ/割安)", key="scr_filter_rsi_os")
            filter_rsi_overbought = st.checkbox("RSI 70以上 (買われすぎ/過熱)", key="scr_filter_rsi_ob")
            filter_bb_rebound = st.checkbox("ボリンジャーバンド -2σ以下", key="scr_filter_bb_re")
            filter_volume_surge = st.checkbox("出来高急増 (5日平均 > 25日平均*1.2)", key="scr_filter_vol_su")

    # Prepare target ticker list
    tickers_pool = {}
    if market == f"日本株 厳選トレンド銘柄 ({len(JP_TICKERS)}件)":
        tickers_pool = JP_TICKERS
    elif market == f"米国株 厳選トレンド銘柄 ({len(US_TICKERS)}件)":
        tickers_pool = US_TICKERS
    elif market == "日経平均株価 (日経225全銘柄 - 動的取得)":
        tickers_pool = fetch_nikkei225_tickers()
    else:
        # Custom
        if custom_tickers:
            parsed = [t.strip().upper() for t in custom_tickers.replace('\n', ',').split(',') if t.strip()]
            for p in parsed:
                tickers_pool[p] = {"name": p, "tags": ["カスタム"]}
                
    # Apply theme filter
    filtered_pool = {}
    for ticker, info in tickers_pool.items():
        tags = info.get('tags', [])
        
        # Sector matching based tags
        is_ai_semi = "AI" in tags or "半導体" in tags or any(x in str(tags) for x in ["Technology", "Semiconductor", "Software", "ソフトウェア", "電気機器", "設計"])
        is_space = "宇宙" in tags or any(x in str(tags) for x in ["Space", "Aerospace", "Defense", "防衛", "航空宇宙", "航空重工", "ロケット", "月面開発", "月面着陸", "衛星システム", "衛星レーダー", "衛星データ分析"])
        is_explosive = "急騰期待" in tags
        is_high_dividend_value = "高配当" in tags or "商社" in tags or "銀行業" in tags or "銀行" in tags or "保険業" in tags or "保険" in tags or "金融" in tags or "その他金融" in tags or "バリュー" in tags or "高配当" in str(tags) or "卸売業" in tags or "商業" in tags
        is_crypto_meme = "ビットコイン保有" in tags or "暗号資産" in tags or "ミーム株" in tags or "暗号資産取引所" in tags or "暗号資産マイニング" in tags or any(x in str(tags) for x in ["Bitcoin", "Crypto", "Meme"])
        is_entertainment_vtuber_game = "VTuber" in tags or "ゲーム" in tags or "エンタメ" in tags or "ゲーム・メタバース" in tags or "その他製品" in tags or "ストリーミング" in tags or "SNS" in tags
        is_defense_heavy = "防衛" in tags or "宇宙" in tags or "ロケット" in tags or "機械" in tags or "輸送用機器" in tags or "航空重工" in tags or "精密機器" in tags
        
        if theme_filter == "AI・半導体関連":
            if is_ai_semi:
                filtered_pool[ticker] = info
        elif theme_filter == "宇宙産業・開発関連":
            if is_space:
                filtered_pool[ticker] = info
        elif theme_filter == "爆発的急騰期待株":
            if is_explosive:
                filtered_pool[ticker] = info
        elif theme_filter == "高配当・バリュー株":
            if is_high_dividend_value:
                filtered_pool[ticker] = info
        elif theme_filter == "暗号資産・ネットミーム・ハイベータ":
            if is_crypto_meme:
                filtered_pool[ticker] = info
        elif theme_filter == "エンタメ・VTuber・ゲーム":
            if is_entertainment_vtuber_game:
                filtered_pool[ticker] = info
        elif theme_filter == "防衛・宇宙・重工業":
            if is_defense_heavy:
                filtered_pool[ticker] = info
        else:
            filtered_pool[ticker] = info

    # Display configuration results
    if not filtered_pool:
        st.info("条件に該当する銘柄がありません。他の市場を選択するか、カスタムティッカーを入力してください。")
    else:
        st.markdown(f"**現在のスクリーニング対象候補数**: {len(filtered_pool)} 銘柄")
        
        # Start button
        if st.button("スクリーニングを開始する", type="primary", use_container_width=True):
            with st.spinner("株価データ及び企業財務データをYahoo Financeから取得中..."):
                
                # 1. Download price history in batch for fast loading
                tickers_list = list(filtered_pool.keys())
                histories = batch_download_histories(tickers_list, period=selected_period)
                
                # 2. Analyze each ticker
                results = []
                progress_bar = st.progress(0)
                
                for idx, ticker in enumerate(tickers_list):
                    progress_bar.progress((idx + 1) / len(tickers_list))
                    
                    df = histories.get(ticker)
                    if df is None or df.empty or len(df) < 75:
                        continue
                        
                    # 1. Run technical analysis first (Fast!)
                    tech_analysis = evaluate_stock(ticker, df, info=None)
                    if tech_analysis is None:
                        continue
                        
                    # Apply technical score filter first (Skip slow API if it doesn't match technical criteria)
                    if tech_analysis['tech_score'] < min_tech_score:
                        continue
                        
                    # Apply advanced technical filters in the fast-track step
                    if filter_golden_cross and not tech_analysis['signals']['golden_cross']:
                        continue
                    if filter_macd_cross and not tech_analysis['signals']['macd_cross']:
                        continue
                    if filter_rsi_oversold and not tech_analysis['signals']['rsi_oversold']:
                        continue
                    if filter_rsi_overbought and not tech_analysis['signals']['rsi_overbought']:
                        continue
                    if filter_bb_rebound and not tech_analysis['signals']['bb_rebound']:
                        continue
                    if filter_volume_surge and not tech_analysis['signals']['volume_surge']:
                        continue
                        
                    # 2. Fetch fundamentals ONLY for stocks passing technical checks
                    info = get_ticker_info(ticker)
                    
                    # Run full analysis
                    analysis = evaluate_stock(ticker, df, info)
                    if analysis is None:
                        continue
                        
                    metrics = analysis['metrics']
                    
                    # Apply manual sidebar filters
                    if analysis['total_score'] < min_total_score:
                        continue
                    if analysis['fund_score'] < min_fund_score:
                        continue
                        
                    if filter_pbr and (metrics['pbr'] is None or metrics['pbr'] >= 1.0):
                        continue
                    if filter_per and (metrics['per'] is None or metrics['per'] >= 15.0):
                        continue
                    if filter_roe and (metrics['roe'] is None or metrics['roe'] < 10.0):
                        continue
                    if filter_dividend and (metrics['dividend_yield'] is None or metrics['dividend_yield'] < 3.0):
                        continue
                        
                    # Advanced technical checks (Full)
                    if filter_golden_cross and not analysis['signals']['golden_cross']:
                        continue
                    if filter_macd_cross and not analysis['signals']['macd_cross']:
                        continue
                    if filter_rsi_oversold and not analysis['signals']['rsi_oversold']:
                        continue
                    if filter_rsi_overbought and not analysis['signals']['rsi_overbought']:
                        continue
                    if filter_bb_rebound and not analysis['signals']['bb_rebound']:
                        continue
                    if filter_volume_surge and not analysis['signals']['volume_surge']:
                        continue
                        
                    results.append({
                        'ティッカー': ticker,
                        '銘柄名': filtered_pool[ticker]['name'],
                        '総合スコア (10点)': f"{analysis['total_score']} / 10",
                        'テクニカルスコア (3点)': f"{analysis['tech_score']} / 3",
                        'ファンダスコア (7点)': f"{analysis['fund_score']} / 7",
                        '株価': format_price(metrics['price'], ticker),
                        '前日比 (%)': f"{metrics['change_pct']:.2f}%",
                        'PER (倍)': f"{metrics['per']:.1f}" if metrics['per'] is not None else "N/A",
                        'PBR (倍)': f"{metrics['pbr']:.2f}" if metrics['pbr'] is not None else "N/A",
                        'ROE (%)': f"{metrics['roe']:.1f}%" if metrics['roe'] is not None else "N/A",
                        '配当利回り (%)': f"{metrics['dividend_yield']:.2f}%" if metrics['dividend_yield'] is not None else "N/A",
                        'テーマ/タグ': ", ".join(filtered_pool[ticker].get('tags', [])),
                        'raw_data': analysis
                    })
                
                # Store in session state to persist results
                st.session_state['screening_results'] = results
                progress_bar.empty()
                
        # Display screening results if they exist in session state
        if 'screening_results' in st.session_state:
            results = st.session_state['screening_results']
            
            if not results:
                st.warning("指定された条件に一致する銘柄が見つかりませんでした。サイドバーのフィルタ条件を緩めて再実行してください。")
            else:
                st.success(f"条件に合致する銘柄が {len(results)} 件検出されました！ (スコア順で並び替えています)")
                
                # Convert results to display DataFrame
                display_data = []
                portfolio = load_portfolio()
                owned_stocks = {r["ticker"]: r["quantity"] for r in portfolio.get("purchase_records", [])}
                
                for r in results:
                    row = {k: v for k, v in r.items() if k != 'raw_data'}
                    ticker = r['ティッカー']
                    qty = owned_stocks.get(ticker, 0)
                    row['保有状況'] = f"保有中 ({int(qty):,}株)" if qty > 0 else "未保有"
                    
                    # Add clean text signals
                    raw = r['raw_data']
                    badges = []
                    if raw['signals']['perfect_order']: badges.append("上昇トレンド")
                    if raw['signals']['trend_reversal']: badges.append("転換シグナル")
                    if raw['signals']['volume_surge']: badges.append("出来高急増")
                    
                    row['点灯シグナル'] = " ".join(badges) if badges else "なし"
                    display_data.append(row)
                    
                df_display = pd.DataFrame(display_data)
                
                # Sort by score descending
                df_display['sort_val'] = df_display['総合スコア (10点)'].apply(lambda x: int(x.split('/')[0]))
                df_display = df_display.sort_values(by='sort_val', ascending=False).drop(columns=['sort_val']).reset_index(drop=True)
                
                # Show dataframe (Enable row selection)
                selected_rows = st.dataframe(
                    df_display, 
                    use_container_width=True,
                    column_config={
                        "ティッカー": st.column_config.TextColumn("ティッカー", width="small"),
                        "前日比 (%)": st.column_config.TextColumn("前日比 (%)"),
                    },
                    on_select="rerun",
                    selection_mode="single-row",
                    key="screening_df_selection"
                )
                
                # Select stock for deep analysis based on selected row index
                st.markdown('<div id="deep-analysis-section"></div>', unsafe_allow_html=True)
                st.caption("上記のスクリーニング結果リストの行をクリックすると、詳細分析ダッシュボードおよび下部の仮想購入フォームが自動的に切り替わります（未選択時は1位の企業が表示されます）。")
                
                selected_row_indices = selected_rows.get("selection", {}).get("rows", [])
                if selected_row_indices and len(selected_row_indices) > 0:
                    selected_idx = selected_row_indices[0]
                else:
                    selected_idx = 0
                
                # Boundary check safety
                if selected_idx >= len(df_display):
                    selected_idx = 0
                    
                selected_ticker = df_display.iloc[selected_idx]["ティッカー"]
                
                # Scroll detection logic based on selected row index list
                if "prev_selected_row_indices" not in st.session_state:
                    st.session_state["prev_selected_row_indices"] = []
                
                if selected_row_indices != st.session_state["prev_selected_row_indices"]:
                    if len(selected_row_indices) > 0:
                        # Scroll smoothly when a row is clicked (even the 1st row [0] changing from default empty selection [])
                        js_scroll = """
                        <script>
                            setTimeout(function() {
                                var el = window.parent.document.getElementById('deep-analysis-section');
                                if (el) {
                                    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
                                }
                            }, 100);
                        </script>
                        """
                        st.components.v1.html(js_scroll, height=0, width=0)
                    st.session_state["prev_selected_row_indices"] = selected_row_indices
                
                # Find corresponding raw data
                selected_item = next(item for item in results if item['ティッカー'] == selected_ticker)
                raw_analysis = selected_item['raw_data']
                render_detail_dashboard(selected_ticker, selected_item['銘柄名'], raw_analysis, key_suffix="_screen")


# -----------------------------------------------------------------------------
# TAB 1.5: HOLDINGS & FAVORITES ANALYSIS
# -----------------------------------------------------------------------------
with tab_favorite:
    # Inject premium CSS and Javascript styling
    st.markdown("""
    <style>
    /* Base style for premium list buttons */
    div[data-testid="column"] button.premium-list-btn {
        text-align: left !important;
        display: flex !important;
        justify-content: flex-start !important;
        align-items: center !important;
        border-radius: 12px !important;
        padding: 14px 18px !important;
        font-size: 0.92rem !important;
        font-weight: 600 !important;
        border: 1px solid #e2e8f0 !important;
        background: #ffffff !important;
        color: #1e293b !important;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05) !important;
        transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
        margin-bottom: 8px !important;
    }
    /* Hover effect */
    div[data-testid="column"] button.premium-list-btn:hover {
        border-color: #3b82f6 !important;
        background-color: #f8fafc !important;
        color: #2563eb !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 4px 12px -2px rgba(37, 99, 235, 0.12) !important;
    }
    /* Active selected style (Primary button override) */
    div[data-testid="column"] button.premium-list-btn.premium-active {
        border-color: #2563eb !important;
        background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%) !important;
        color: #ffffff !important;
        box-shadow: 0 4px 14px 0 rgba(37, 99, 235, 0.3) !important;
    }
    div[data-testid="column"] button.premium-list-btn.premium-active:hover {
        background: linear-gradient(135deg, #1d4ed8 0%, #1e40af 100%) !important;
        color: #ffffff !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 18px 0 rgba(37, 99, 235, 0.4) !important;
    }
    </style>
    """, unsafe_allow_html=True)

    st.components.v1.html("""
    <script>
        const parentDoc = window.parent.document;
        function applyStyles() {
            const buttons = parentDoc.querySelectorAll('button');
            buttons.forEach(btn => {
                const txt = btn.textContent || "";
                if (txt.includes('💼') || txt.includes('⭐')) {
                    if (!btn.classList.contains('premium-list-btn')) {
                        btn.classList.add('premium-list-btn');
                    }
                    const testid = btn.getAttribute('data-testid');
                    if (testid && testid.includes('primary')) {
                        btn.classList.add('premium-active');
                    } else {
                        btn.classList.remove('premium-active');
                    }
                }
            });
        }
        setInterval(applyStyles, 150);
        applyStyles();
    </script>
    """, height=0, width=0)

    st.markdown("### ⭐ 保有・お気に入り銘柄の分析")
    st.markdown("現在保有している仮想ポートフォリオ銘柄、およびお気に入り（ウォッチリスト）に登録されている銘柄のリアルタイム分析・値動きを表示します。")
    
    watchlist = load_watchlist()
    portfolio = load_portfolio()
    purchase_records = portfolio.get("purchase_records", [])
    
    # Generate unique list of tickers
    ticker_display = {}
    ticker_names = {}
    
    # 1. Process purchased stocks
    for rec in purchase_records:
        ticker = rec["ticker"]
        name = rec["name"]
        qty = int(rec["quantity"])
        ticker_names[ticker] = name
        ticker_display[ticker] = f"💼 {name} ({ticker}) [保有中: {qty:,}株]"
        
    # 2. Process watchlisted stocks
    for ticker, name in watchlist.items():
        ticker_names[ticker] = name
        if ticker in ticker_display:
            ticker_display[ticker] += " ⭐"
        else:
            ticker_display[ticker] = f"⭐ {name} ({ticker}) [お気に入り]"
            
    all_tickers = sorted(list(ticker_display.keys()))
    
    if "selected_fav_ticker" not in st.session_state or st.session_state["selected_fav_ticker"] not in all_tickers:
        if all_tickers:
            st.session_state["selected_fav_ticker"] = all_tickers[0]
        
    if not all_tickers:
        st.info("保有銘柄、またはお気に入り登録された銘柄がありません。🔍「スクリーニング実行と結果分析」タブの銘柄詳細ダッシュボードから「☆ お気に入り追加」または「仮想購入する」をクリックして登録してください。")
    else:
        # Display the simple lists of owned and watchlisted stocks as clickable buttons
        col_list_owned, col_list_fav = st.columns(2)
        with col_list_owned:
            st.markdown("##### 💼 保有銘柄一覧 (クリックして選択)")
            if purchase_records:
                for rec in purchase_records:
                    qty_str = f"{int(rec['quantity']):,}株" if not is_us_stock(rec['ticker']) else f"{rec['quantity']:,.2f}株" if int(rec['quantity']) != rec['quantity'] else f"{int(rec['quantity']):,}株"
                    btn_label = f"💼 {rec['name']} ({rec['ticker']}) | {qty_str} (平均取得: {format_price(rec['purchase_price'], rec['ticker'])})"
                    is_active = (rec['ticker'] == st.session_state.get("selected_fav_ticker"))
                    btn_type = "primary" if is_active else "secondary"
                    if st.button(btn_label, key=f"btn_owned_{rec['ticker']}", use_container_width=True, type=btn_type):
                        st.session_state["selected_fav_ticker"] = rec['ticker']
                        st.session_state["scroll_fav"] = True
                        st.rerun()
            else:
                st.caption("保有している銘柄はありません。")
                
        with col_list_fav:
            st.markdown("##### ⭐ お気に入り銘柄一覧 (クリックして選択)")
            if watchlist:
                for t, n in watchlist.items():
                    btn_label = f"⭐ {n} ({t})"
                    is_active = (t == st.session_state.get("selected_fav_ticker"))
                    btn_type = "primary" if is_active else "secondary"
                    if st.button(btn_label, key=f"btn_fav_{t}", use_container_width=True, type=btn_type):
                        st.session_state["selected_fav_ticker"] = t
                        st.session_state["scroll_fav"] = True
                        st.rerun()
            else:
                st.caption("お気に入り登録されている銘柄はありません。")
                
        st.markdown("<hr style='margin: 15px 0; border: none; border-top: 1px solid #e2e8f0;'>", unsafe_allow_html=True)
        
        # Scroll anchor
        st.markdown('<div id="fav-deep-analysis-section"></div>', unsafe_allow_html=True)
        
        # Trigger smooth scroll if requested
        if st.session_state.get("scroll_fav"):
            js_scroll = """
            <script>
                setTimeout(function() {
                    var el = window.parent.document.getElementById('fav-deep-analysis-section');
                    if (el) {
                        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    }
                }, 100);
            </script>
            """
            st.components.v1.html(js_scroll, height=0, width=0)
            st.session_state["scroll_fav"] = False
            
        # Determine currently selected ticker
        selected_fav_ticker = st.session_state["selected_fav_ticker"]
        selected_fav_name = ticker_names[selected_fav_ticker]
        cache_key = f"fav_analysis_{selected_fav_ticker}"
        
        # Row with a small caption and refresh button
        col_cap, col_ref = st.columns([3.8, 1.2])
        with col_cap:
            st.caption("💡 上記リストの銘柄ボタンをクリックすると、その銘柄の分析とチャートが以下に表示されます。")
        with col_ref:
            if st.button("🔄 最新データに更新", key=f"inline_ref_btn_{selected_fav_ticker}", use_container_width=True):
                if cache_key in st.session_state:
                    del st.session_state[cache_key]
                st.rerun()
        
        if cache_key not in st.session_state:
            with st.spinner(f"{selected_fav_name} ({selected_fav_ticker}) のデータを取得・分析中..."):
                try:
                    tk = yf.Ticker(selected_fav_ticker)
                    df = tk.history(period="1y")
                    df = patch_history_with_fast_info(selected_fav_ticker, df)
                    if df.empty or len(df) < 75:
                        st.error(f"{selected_fav_name} ({selected_fav_ticker}) の十分な株価履歴データを取得できませんでした（取引日数が75日未満、または非上場）。")
                    else:
                        info = get_ticker_info(selected_fav_ticker)
                        raw_analysis = evaluate_stock(selected_fav_ticker, df, info)
                        if raw_analysis:
                            st.session_state[cache_key] = raw_analysis
                            st.rerun()
                        else:
                            st.error("銘柄の評価に失敗しました。")
                except Exception as e:
                    st.error(f"データ取得中にエラーが発生しました: {e}")
                    
        if cache_key in st.session_state:
            raw_analysis = st.session_state[cache_key]
            # Call the dashboard with _fav suffix to prevent any key collisions
            render_detail_dashboard(selected_fav_ticker, selected_fav_name, raw_analysis, key_suffix="_fav")


# -----------------------------------------------------------------------------
# TAB 2: VIRTUAL PORTFOLIO SIMULATION (JPY Only)
# -----------------------------------------------------------------------------
with tab_simulation:
    st.markdown("### 仮想ポートフォリオ状況")
    
    # Reload local portfolio data
    portfolio_data = load_portfolio()
    records = portfolio_data.get("purchase_records", [])
    sales_records = portfolio_data.get("sales_records", [])
    cached_prices = portfolio_data.get("last_valid_prices", {})
    
    # Setup cache inside session_state
    if 'last_valid_prices' not in st.session_state:
        st.session_state['last_valid_prices'] = cached_prices
    else:
        # Merge local storage into session cache
        st.session_state['last_valid_prices'].update(cached_prices)
        
    histories = {}
    latest_prices = {}
    
    total_invest_jpy = 0.0
    total_curr_jpy = 0.0
    
    portfolio_table = []
    usdjpy_rate = get_usdjpy_rate()
    
    if records:
        unique_tickers = list(set([r["ticker"] for r in records]))
        
        # Determine earliest purchase date for time series
        purchase_dates_parsed = []
        for r in records:
            try:
                d = datetime.datetime.strptime(r["purchase_date"], "%Y-%m-%d").date()
                purchase_dates_parsed.append(d)
            except ValueError:
                purchase_dates_parsed.append(datetime.date.today())
        
        min_date = min(purchase_dates_parsed)
        start_fetch_date = (min_date - datetime.timedelta(days=5)).strftime("%Y-%m-%d")
        
        # Download latest prices
        with st.spinner("保有銘柄の最新株価・履歴を読み込み中..."):
            for t in unique_tickers:
                try:
                    tk = yf.Ticker(t)
                    df_h = tk.history(start=start_fetch_date)
                    df_h = patch_history_with_fast_info(t, df_h)
                    if not df_h.empty:
                        histories[t] = df_h
                        closes = df_h['Close'].dropna()
                        if not closes.empty:
                            price_val = float(closes.iloc[-1])
                            latest_prices[t] = price_val
                            # Update session state cache & local record dictionary
                            st.session_state['last_valid_prices'][t] = price_val
                            portfolio_data['last_valid_prices'][t] = price_val
                    else:
                        df_h = tk.history(period="1mo")
                        df_h = patch_history_with_fast_info(t, df_h)
                        if not df_h.empty:
                            histories[t] = df_h
                            closes = df_h['Close'].dropna()
                            if not closes.empty:
                                price_val = float(closes.iloc[-1])
                                latest_prices[t] = price_val
                                st.session_state['last_valid_prices'][t] = price_val
                                portfolio_data['last_valid_prices'][t] = price_val
                except Exception as e:
                    # Silence warnings and rely on cache fallback
                    pass
            
            # Save updated price cache back to portfolio file
            save_portfolio(portfolio_data)
                    
        # Calculate active records
        for i, r in enumerate(records):
            ticker = r["ticker"]
            qty = r["quantity"]
            purchase_price = r["purchase_price"]
            invest_amount = r["invest_amount"]
            purchase_date_str = r["purchase_date"]
            
            # Retrieve from latest or session state cache, fallback to purchase_price
            curr_price = latest_prices.get(ticker)
            if curr_price is None or pd.isna(curr_price):
                curr_price = st.session_state['last_valid_prices'].get(ticker)
                if curr_price is None or pd.isna(curr_price):
                    curr_price = purchase_price
                    
            curr_val = qty * curr_price
            pl_amount = curr_val - invest_amount
            pl_pct = ((curr_price - purchase_price) / purchase_price) * 100
            
            rate = usdjpy_rate if is_us_stock(ticker) else 1.0
            total_invest_jpy += invest_amount * rate
            total_curr_jpy += curr_val * rate
            
            qty_str = f"{int(qty):,} 株" if not is_us_stock(ticker) else f"{qty:,.2f} 株" if int(qty) != qty else f"{int(qty):,} 株"
            
            if pd.isna(pl_amount):
                pl_str = "N/A"
            elif is_us_stock(ticker):
                sign = "+" if pl_amount >= 0 else ""
                pl_str = f"{sign}${abs(pl_amount):,.2f} ({sign}¥{int(pl_amount * rate):,})"
            else:
                pl_str = f"¥{int(pl_amount):+,}"
                
            portfolio_table.append({
                "ID": i,
                "ティッカー": ticker,
                "銘柄名": r["name"],
                "購入日": purchase_date_str,
                "平均取得単価": format_price(purchase_price, ticker),
                "現在値": format_price(curr_price, ticker),
                "保有株数": qty_str,
                "投資額": format_price(invest_amount, ticker),
                "評価額": format_price(curr_val, ticker),
                "評価損益": pl_str,
                "損益率": f"{pl_pct:+.2f}%" if not pd.isna(pl_pct) else "N/A",
                "raw_pl": pl_amount,
                "raw_pl_pct": pl_pct
            })
            
    df_show = pd.DataFrame(portfolio_table)
    
    # ----------------------------------------------------
    # Portfolio summary cards at the top
    # ----------------------------------------------------
    sum_col1, sum_col2, sum_col3, sum_col4 = st.columns(4)
    
    with sum_col1:
        st.markdown(f"""
        <div class="card" style="border-left: 5px solid #2563eb; padding: 15px; border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); background-color: #ffffff; margin-bottom: 10px;">
            <div style="font-size: 0.85rem; color: #64748b; font-weight: 600;">初期総投資額</div>
            <div style="font-size: 1.5rem; font-weight: bold; margin-top: 5px; color: #1e293b;">{format_price(total_invest_jpy)}</div>
        </div>
        """, unsafe_allow_html=True)
        
    with sum_col2:
        st.markdown(f"""
        <div class="card" style="border-left: 5px solid #475569; padding: 15px; border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); background-color: #ffffff; margin-bottom: 10px;">
            <div style="font-size: 0.85rem; color: #64748b; font-weight: 600;">現在合計評価額</div>
            <div style="font-size: 1.5rem; font-weight: bold; margin-top: 5px; color: #1e293b;">{format_price(total_curr_jpy)}</div>
        </div>
        """, unsafe_allow_html=True)

    with sum_col3:
        total_pl = total_curr_jpy - total_invest_jpy
        total_pl_pct = (total_pl / total_invest_jpy * 100) if total_invest_jpy > 0 else 0.0
        
        pl_color = "#16a34a" if total_pl >= 0 else "#dc2626"
        pl_border = "#16a34a" if total_pl >= 0 else "#dc2626"
        pl_sign = "+" if total_pl >= 0 else ""
        
        st.markdown(f"""
        <div class="card" style="border-left: 5px solid {pl_border}; padding: 15px; border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); background-color: #ffffff; margin-bottom: 10px;">
            <div style="font-size: 0.85rem; color: #64748b; font-weight: 600;">評価損益 (含み損益)</div>
            <div style="font-size: 1.5rem; font-weight: bold; margin-top: 5px; color: {pl_color};">
                {pl_sign}¥{int(total_pl):,}<br>
                <span style="font-size: 0.8rem; font-weight: normal; color: #64748b;">
                    損益率: {total_pl_pct:+.2f}%
                </span>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
    with sum_col4:
        realized_jpy = portfolio_data.get("total_realized_pl_jpy", 0.0)
        real_color = "#16a34a" if realized_jpy >= 0 else "#dc2626"
        real_border = "#16a34a" if realized_jpy >= 0 else "#dc2626"
        real_sign = "+" if realized_jpy >= 0 else ""
        
        st.markdown(f"""
        <div class="card" style="border-left: 5px solid {real_border}; padding: 15px; border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); background-color: #ffffff; margin-bottom: 10px;">
            <div style="font-size: 0.85rem; color: #64748b; font-weight: 600;">確定損益 (累計実益)</div>
            <div style="font-size: 1.5rem; font-weight: bold; margin-top: 5px; color: {real_color};">
                {real_sign}¥{int(realized_jpy):,}
            </div>
        </div>
        """, unsafe_allow_html=True)

    # ----------------------------------------------------
    # Active Portfolio Records Table & Action Panel
    # ----------------------------------------------------
    st.markdown("---")
    selected_portfolio_row_indices = []
    col_left, col_right = st.columns([1.2, 0.8])
    
    with col_left:
        st.markdown("### 保有銘柄一覧")
        if not records:
            st.info("現在、仮想保有している銘柄はありません。上の『スクリーニング実行と結果分析』タブから評価レポートを表示し、購入ウィジェットから追加してください。")
        else:
            st.caption("※ 保有銘柄の行をクリックして選択すると、右側のパネルから売却手続きが可能です。")
            df_display = df_show.drop(columns=["ID", "raw_pl", "raw_pl_pct"])
            
            styled_df = df_display.style
            try:
                styled_df = styled_df.map(color_pl_cell, subset=["評価損益", "損益率"])
            except AttributeError:
                styled_df = styled_df.applymap(color_pl_cell, subset=["評価損益", "損益率"])
                
            selected_portfolio_rows = st.dataframe(
                styled_df,
                use_container_width=True,
                on_select="rerun",
                selection_mode="single-row",
                key="portfolio_df_selection"
            )
            selected_portfolio_row_indices = selected_portfolio_rows.get("selection", {}).get("rows", [])
            
    with col_right:
        st.markdown("### 仮想売却")
        
        if records and selected_portfolio_row_indices and len(selected_portfolio_row_indices) > 0:
            sell_idx = selected_portfolio_row_indices[0]
            selected_rec = records[sell_idx]
            
            total_qty = int(selected_rec["quantity"])
            curr_price = latest_prices.get(selected_rec["ticker"])
            if curr_price is None or pd.isna(curr_price):
                curr_price = st.session_state['last_valid_prices'].get(selected_rec["ticker"], selected_rec["purchase_price"])
            
            st.markdown(f"""
            <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 12px; margin-bottom: 10px; color: #1e293b;">
                <div style="display: flex; justify-content: space-between;">
                    <span style="color: #64748b;">売却対象:</span>
                    <span style="font-weight: bold; color: #0f172a;">{selected_rec['name']} ({selected_rec['ticker']})</span>
                </div>
                <div style="display: flex; justify-content: space-between; margin-top: 5px;">
                    <span style="color: #64748b;">保有数量:</span>
                    <span style="font-weight: bold; color: #0f172a;">{total_qty:,} 株</span>
                </div>
                <div style="display: flex; justify-content: space-between; margin-top: 5px;">
                    <span style="color: #64748b;">現在価格:</span>
                    <span style="font-weight: bold; color: #1e293b;">{format_price(curr_price, selected_rec['ticker'])}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # 売却株数の入力 (数値入力方式 / 最小単位1株)
            sell_qty = st.number_input(
                "売却株数 (株)",
                min_value=1,
                max_value=total_qty,
                value=total_qty,
                step=1,
                format="%d",
                key=f"sell_qty_input_{sell_idx}"
            )
            
            # 売却による予想回収額 (現在値 * 売却株数)
            expected_return = sell_qty * curr_price
            original_cost = sell_qty * selected_rec["purchase_price"]
            realized_pl = expected_return - original_cost
            
            pl_color_style = "color: #16a34a;" if realized_pl >= 0 else "color: #dc2626;"
            pl_sign = "+" if realized_pl >= 0 else ""
            
            ticker = selected_rec["ticker"]
            rate = get_usdjpy_rate() if is_us_stock(ticker) else 1.0
            
            if is_us_stock(ticker):
                expected_return_str = f"{format_price(expected_return, ticker)} (約 ¥{int(expected_return * rate):,})"
                realized_pl_str = f"{pl_sign}{format_price(realized_pl, ticker)} ({pl_sign}¥{int(realized_pl * rate):,})"
            else:
                expected_return_str = format_price(expected_return, ticker)
                realized_pl_str = f"{pl_sign}{format_price(realized_pl, ticker)}"
            
            st.markdown(f"""
            <div style="background-color: #f1f5f9; border-radius: 6px; padding: 10px 12px; margin-bottom: 15px; font-size: 0.9rem;">
                <div style="display: flex; justify-content: space-between;">
                    <span style="color: #475569;">売却予定金額:</span>
                    <span style="font-weight: bold; color: #0f172a;">{expected_return_str}</span>
                </div>
                <div style="display: flex; justify-content: space-between; margin-top: 5px;">
                    <span style="color: #475569;">確定実現損益:</span>
                    <span style="font-weight: bold; {pl_color_style}">{realized_pl_str}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            if st.button("選択した株数を売却する", use_container_width=True, key="sim_sell_btn", type="primary"):
                realized_pl_val = (curr_price - selected_rec["purchase_price"]) * sell_qty
                
                if sell_qty == total_qty:
                    del_rec = records.pop(sell_idx)
                else:
                    qty_to_sell = float(sell_qty)
                    selected_rec["quantity"] -= qty_to_sell
                    selected_rec["invest_amount"] -= selected_rec["purchase_price"] * qty_to_sell
                
                sales = portfolio_data.get("sales_records", [])
                sales.append({
                    "ticker": selected_rec["ticker"],
                    "name": selected_rec["name"],
                    "sell_date": datetime.date.today().strftime("%Y-%m-%d"),
                    "purchase_price": float(selected_rec["purchase_price"]),
                    "sell_price": float(curr_price),
                    "quantity": float(sell_qty),
                    "realized_pl": float(realized_pl_val),
                    "currency": "USD" if is_us_stock(selected_rec["ticker"]) else "JPY"
                })
                portfolio_data["sales_records"] = sales
                
                # Convert realized PL to JPY for cumulative tracking
                realized_pl_jpy_val = realized_pl_val * rate
                portfolio_data["total_realized_pl_jpy"] = portfolio_data.get("total_realized_pl_jpy", 0.0) + realized_pl_jpy_val
                portfolio_data["purchase_records"] = records
                
                if save_portfolio(portfolio_data):
                    st.session_state['show_sell_dialog'] = {
                        'name': del_rec['name'] if sell_qty == total_qty else selected_rec['name'],
                        'ticker': del_rec['ticker'] if sell_qty == total_qty else selected_rec['ticker'],
                        'qty': int(sell_qty),
                        'price': float(curr_price),
                        'total_return': float(expected_return),
                        'realized_pl': float(realized_pl_val)
                    }
                    st.rerun()
        else:
            if not records:
                st.info("保有している銘柄がありません。")
            else:
                st.info("保有銘柄一覧から売却したい銘柄の行をクリックして選択してください。")
            st.button("売却を実行する", use_container_width=True, key="sim_sell_btn_disabled", disabled=True)

    # ----------------------------------------------------
    # Portfolio performance timeline chart
    # ----------------------------------------------------
    if records:
        st.markdown("---")
        st.markdown("### ポートフォリオ評価額推移と個別パフォーマンス分析")
        
        # Calculate daily aggregate portfolio values
        today_date = datetime.date.today()
        timeline = pd.date_range(start=min_date, end=today_date, freq='B')
        if timeline.empty:
            timeline = pd.DatetimeIndex([pd.to_datetime(today_date)])
            
        # 集計用データフレーム
        df_total = pd.DataFrame(0.0, index=timeline, columns=['invested', 'current'])
        
        # Get historical JPY=X exchange rate aligned to timeline
        try:
            usdjpy_ticker = yf.Ticker("JPY=X")
            df_usdjpy = usdjpy_ticker.history(start=start_fetch_date)
            df_usdjpy_aligned = df_usdjpy.reindex(timeline).ffill().bfill()
            usdjpy_series = df_usdjpy_aligned['Close'].fillna(usdjpy_rate)
        except Exception:
            usdjpy_series = pd.Series(usdjpy_rate, index=timeline)
        
        for r in records:
            ticker = r["ticker"]
            qty = r["quantity"]
            invest_amount = r["invest_amount"]
            p_date = pd.to_datetime(r["purchase_date"])
            
            if ticker in histories:
                df_h = histories[ticker]
                df_h_aligned = df_h.reindex(timeline).ffill().bfill()
                
                mask = timeline >= p_date
                if is_us_stock(ticker):
                    df_total.loc[mask, 'invested'] += invest_amount * usdjpy_series.loc[mask]
                    df_total.loc[mask, 'current'] += qty * df_h_aligned.loc[mask, 'Close'] * usdjpy_series.loc[mask]
                else:
                    df_total.loc[mask, 'invested'] += invest_amount
                    df_total.loc[mask, 'current'] += qty * df_h_aligned.loc[mask, 'Close']
                    
        df_total['pl'] = df_total['current'] - df_total['invested']
        
        # 銘柄別の評価損益データ作成
        item_pl_list = []
        for r in records:
            ticker = r["ticker"]
            qty = r["quantity"]
            purchase_price = r["purchase_price"]
            curr_price = latest_prices.get(ticker)
            if curr_price is None or pd.isna(curr_price):
                curr_price = st.session_state['last_valid_prices'].get(ticker, purchase_price)
            
            rate = usdjpy_rate if is_us_stock(ticker) else 1.0
            pl_jpy = (curr_price - purchase_price) * qty * rate
            
            item_pl_list.append({
                "label": f"{r['name']} ({ticker})",
                "pl_jpy": pl_jpy,
                "color": "#16a34a" if pl_jpy >= 0 else "#dc2626"
            })
            
        # 損益順にソート (Plotly横棒は下から上に描画されるので昇順ソートが適している)
        item_pl_list = sorted(item_pl_list, key=lambda x: x["pl_jpy"])

        # 過去の売却履歴から銘柄ごとの累計確定損益を計算
        realized_by_ticker = {}
        for s in sales_records:
            t = s["ticker"]
            name = s["name"]
            
            # backward compatibility for key
            pl = s.get("realized_pl") or s.get("profit_loss_jpy") or 0.0
            rate = usdjpy_rate if is_us_stock(t) else 1.0
            pl_jpy = pl * rate
            
            key = f"{name} ({t})"
            realized_by_ticker[key] = realized_by_ticker.get(key, 0.0) + pl_jpy
            
        realized_pl_list = []
        for key, pl_jpy in realized_by_ticker.items():
            realized_pl_list.append({
                "label": key,
                "pl_jpy": pl_jpy,
                "color": "#16a34a" if pl_jpy >= 0 else "#dc2626"
            })
        realized_pl_list = sorted(realized_pl_list, key=lambda x: x["pl_jpy"])
        
        chart_tab_total, chart_tab_items = st.tabs(["全体損益推移", "個別銘柄 of 損益寄与"])
        
        with chart_tab_total:
            fig_total = go.Figure()
            fig_total.add_trace(go.Scatter(
                x=df_total.index,
                y=df_total['pl'],
                name="総合評価損益",
                mode='lines+markers',
                line=dict(color='#1e3a8a', width=2.5),
                marker=dict(size=4),
                hovertemplate="日付: %{x|%Y-%m-%d}<br>総合損益: ¥%{y:,.0f}<extra></extra>"
            ))
            fig_total.add_shape(
                type="line",
                x0=timeline[0], y0=0,
                x1=timeline[-1], y1=0,
                line=dict(color="#94a3b8", width=1.5, dash="dash")
            )
            fig_total.update_layout(
                title=None,
                xaxis_title="日付",
                yaxis_title="評価損益 (円)",
                template="plotly_white",
                height=380,
                margin=dict(l=10, r=10, t=20, b=10),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_total, use_container_width=True)
            
        with chart_tab_items:
            if realized_pl_list:
                item_col1, item_col2 = st.columns(2)
                with item_col1:
                    st.markdown("<h5 style='text-align: center; color: #1e293b; margin-bottom: 10px;'>保有銘柄の評価損益 (含み損益)</h5>", unsafe_allow_html=True)
                    if item_pl_list:
                        fig_bar_active = go.Figure()
                        fig_bar_active.add_trace(go.Bar(
                            y=[x["label"] for x in item_pl_list],
                            x=[x["pl_jpy"] for x in item_pl_list],
                            orientation='h',
                            marker_color=[x["color"] for x in item_pl_list],
                            hovertemplate="銘柄: %{y}<br>評価損益: ¥%{x:,.0f}<extra></extra>"
                        ))
                        fig_bar_active.add_vline(x=0, line_width=1.5, line_dash="dash", line_color="#94a3b8")
                        fig_bar_active.update_layout(
                            xaxis_title="評価損益 (円)",
                            yaxis_title=None,
                            template="plotly_white",
                            height=320,
                            margin=dict(l=10, r=10, t=10, b=10)
                        )
                        st.plotly_chart(fig_bar_active, use_container_width=True)
                    else:
                        st.info("現在保有している銘柄はありません。")
                with item_col2:
                    st.markdown("<h5 style='text-align: center; color: #1e293b; margin-bottom: 10px;'>売却銘柄の累計確定損益 (実現損益)</h5>", unsafe_allow_html=True)
                    fig_bar_realized = go.Figure()
                    fig_bar_realized.add_trace(go.Bar(
                        y=[x["label"] for x in realized_pl_list],
                        x=[x["pl_jpy"] for x in realized_pl_list],
                        orientation='h',
                        marker_color=[x["color"] for x in realized_pl_list],
                        hovertemplate="銘柄: %{y}<br>累計確定損益: ¥%{x:,.0f}<extra></extra>"
                    ))
                    fig_bar_realized.add_vline(x=0, line_width=1.5, line_dash="dash", line_color="#94a3b8")
                    fig_bar_realized.update_layout(
                        xaxis_title="実現損益 (円)",
                        yaxis_title=None,
                        template="plotly_white",
                        height=320,
                        margin=dict(l=10, r=10, t=10, b=10)
                    )
                    st.plotly_chart(fig_bar_realized, use_container_width=True)
            else:
                st.markdown("<h5 style='text-align: center; color: #1e293b; margin-bottom: 10px;'>保有銘柄の評価損益 (含み損益)</h5>", unsafe_allow_html=True)
                if item_pl_list:
                    fig_bar_active = go.Figure()
                    fig_bar_active.add_trace(go.Bar(
                        y=[x["label"] for x in item_pl_list],
                        x=[x["pl_jpy"] for x in item_pl_list],
                        orientation='h',
                        marker_color=[x["color"] for x in item_pl_list],
                        hovertemplate="銘柄: %{y}<br>評価損益: ¥%{x:,.0f}<extra></extra>"
                    ))
                    fig_bar_active.add_vline(x=0, line_width=1.5, line_dash="dash", line_color="#94a3b8")
                    fig_bar_active.update_layout(
                        xaxis_title="評価損益 (円)",
                        yaxis_title=None,
                        template="plotly_white",
                        height=320,
                        margin=dict(l=10, r=10, t=10, b=10)
                    )
                    st.plotly_chart(fig_bar_active, use_container_width=True)
                else:
                    st.info("現在保有している銘柄はありません。")

    # ----------------------------------------------------
    # Past trade history logs (Expander)
    # ----------------------------------------------------
    if sales_records:
        st.markdown("---")
        with st.expander("確定取引（仮想売却）履歴一覧"):
            sales_table = []
            for s in sales_records:
                ticker = s["ticker"]
                rate = usdjpy_rate if is_us_stock(ticker) else 1.0
                
                # backward-compatible key reading
                sell_date = s.get("sell_date") or s.get("sales_date") or "N/A"
                purchase_price = s.get("purchase_price") or 0.0
                sell_price = s.get("sell_price") or s.get("sales_price") or 0.0
                qty = s.get("quantity") or 0.0
                pl = s.get("realized_pl") or s.get("profit_loss_jpy") or 0.0
                
                pl_sign = "+" if pl >= 0 else ""
                
                if is_us_stock(ticker):
                    pl_str = f"{pl_sign}{format_price(pl, ticker)} ({pl_sign}¥{int(pl * rate):,})"
                else:
                    pl_str = f"¥{int(pl):+,}"
                
                sales_table.append({
                    "売却日": sell_date,
                    "ティッカー": ticker,
                    "銘柄名": s["name"],
                    "取得単価": format_price(purchase_price, ticker),
                    "売却単価": format_price(sell_price, ticker),
                    "売却株数": f"{int(qty):,} 株" if not is_us_stock(ticker) else f"{qty:,.2f} 株" if int(qty) != qty else f"{int(qty):,} 株",
                    "確定損益": pl_str
                })
            df_sales_show = pd.DataFrame(sales_table)
            
            styled_sales_df = df_sales_show.style
            try:
                styled_sales_df = styled_sales_df.map(color_pl_cell, subset=["確定損益"])
            except AttributeError:
                styled_sales_df = styled_sales_df.applymap(color_pl_cell, subset=["確定損益"])
                
            st.dataframe(styled_sales_df, use_container_width=True, hide_index=True)
            
    # ----------------------------------------------------
    # Safe system data reset (Bottom-most section)
    # ----------------------------------------------------
    st.markdown("---")
    with st.expander("システム設定とシミュレーションデータのクリア"):
        st.write("これまでのシミュレーション取引（保有データ、売却データ、確定損益など）をすべて初期化し、クリア状態に戻します。")
        confirm_reset = st.checkbox("シミュレーションの全取引データを初期化することに同意する", key="confirm_reset_check")
        if confirm_reset:
            if st.button("すべてのシミュレーションデータをリセットする", key="sim_reset_btn", type="primary"):
                reset_data = {
                    "purchase_records": [],
                    "sales_records": [],
                    "total_realized_pl_jpy": 0.0,
                    "last_valid_prices": {}
                }
                if save_portfolio(reset_data):
                    st.success("すべての取引データを正常に初期化しました。")
                    st.rerun()

# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# TAB 3: SYSTEM METHODOLOGY EXPLANATIONS
# -----------------------------------------------------------------------------
with tab_explanation:
    st.markdown("""
    ## 高視座スクリーニング指標の解説：プロ投資家の選定基準
    
    単なる「目先のチャート反発」ではなく、中長期的な**「クオリティ（収益・財務健全性）」**と、大口の買い手が入ったことを示す**「出来高モメンタム」**、そしてトレンドの調和度合いを総合した **最高10点満点（テクニカル3点、ファンダメンタルズ7点）** のファンダメンタルズ重視型レーティングシステムです。
    
    ---
    
    ### 📈 テクニカル・モメンタム評価 (3点満点)
    
    1. **トレンド調和 (パーフェクトオーダー) [+1点]**
       - **仕組み**: 短期・中期・長期の移動平均線（5日・25日・75日）がすべて上向きであり、かつ株価が主要平均線の上方にある状態。
       - **上昇期待の理由**: 短期的なノイズを排除し、**「大口資金のトレンドが完全に上を向いている」という順張りの強さ**を検出します。
       
    2. **トレンド転換点検知 (ゴールデンクロス/MACD同期) [+1点]**
       - **仕組み**: 25日移動平均線が75日移動平均線を上抜く（ゴールデンクロス）、またはMACD線がシグナル線を下から上抜くシグナルの発生。
       - **上昇期待の理由**: 相場のボトムアウト（底打ち）から上昇トレンドへの初期転換を、**移動平均とオシレーターの両面から多角的に判定**し、最適なエントリータイミングを捉えます。
       
    3. **大口資金の流入 (出来高急増 / Volume Surge) [+1点]**
       - **仕組み**: 直近5日間の平均出来高が、過去25日間の平均出来高の **1.2倍以上** に急増していること。
       - **上昇期待の理由**: 出来高を伴わない株価上昇は「個人投資家による一時的な買い（ダマシ）」であることが多いため、**「機関投資家や外国人投資家といった巨大資本が本格買いに入った本物の兆候」**を出来高の急増から捉えます。
    
    ---
    
    ### 🏢 ファンダメンタルズ・クオリティ評価 (7点満点)
    
    1. **自己資本利益率 (ROE 10%以上) [+1点]**
       - **仕組み**: 企業の自己資本に対する当期純利益の割合。
       - **上昇期待の理由**: 効率的に資本を利益に変えられているかを示す世界共通の経営指標。**「株主還元や再投資に十分な原資を生み出す高い経営効率」**を証明します。
       
    2. **営業利益率 (8%以上) [+1点]**
       - **仕組み**: 売上高に対する営業利益（本業の儲け）の割合。
       - **上昇期待の理由**: 他社との競争力やビジネスモデルの強さを示します。営業利益率が8%以上ある企業は、**原材料高などの外部環境の変化にも耐えうる高い付加価値**を持っています。
       
    3. **利益の質 (当期純利益 利益黒字維持) [+1点]**
       - **仕組み**: 最新決算または予想純利益が確実に黒字であること。
       - **上昇期待の理由**: 赤字垂れ流しの状態での「ただ株価が安いだけのバリュートラップ企業（破綻リスク）」をスクリーニングから厳格に除外します。
       
    4. **利益面での割安性 (PER 15倍未満) [+1点]**
       - **仕組み**: 1株当たり利益に対する株価の倍率。
       - **上昇期待の理由**: 稼ぐ利益に対して株価が低く放置されている状態。市場全体の好転や決算の進捗をきっかけに、**適正な価格（平均値）へ戻る水準訂正**が期待できます。
       
    5. **資産面での割安性・東証改革期待 (PBR 1.0倍未満) [+1点]**
       - **仕組み**: 1株当たり純資産に対する株価の倍率。
       - **上昇期待の理由**: 企業の解散価値（PBR1.0倍）を下回る状態。東証による資本効率改善要求の直接対象となりやすく、**「増配や大規模な自社株買いといった株価上昇トリガー（カタリスト）」**が発生しやすい状態です。
       
    6. **財務健全性 (D/E比率 100%未満 または キャッシュリッチ) [+1点]**
       - **仕組み**: 自己資本に対する有利子負債の割合が100%未満、または手元の現預金が有利子負債総額を上回る状態。
       - **上昇期待の理由**: 利上げ局面において**金利負担で業績が悪化するリスクが極めて低く**、不況期でも強固なビジネスを継続できる財務基盤を評価します。
       
    7. **高配当インカム (配当利回り 3.0%以上) [+1点]**
       - **仕組み**: 株価に対する年間配当金の割合。
       - **上昇期待の理由**: 高い配当利回りは、株価が下落した際に「利回り妙味」から下値支持（クッション）として機能します。また、**長期投資家が保有し続けやすいポートフォリオの土台**となります。
    """)
