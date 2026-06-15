import streamlit as st
import streamlit.components.v1 as components
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

# Plotly config for scroll/pinch-to-zoom and permanently visible modebar
PLOTLY_CONFIG = {
    'scrollZoom': False,
    'displayModeBar': True,
    'displaylogo': False,
    'responsive': True,
    'modeBarButtons': [['zoomIn2d', 'zoomOut2d', 'resetScale2d']]
}

# UI theme and mode settings
st.sidebar.markdown("### 📱 表示・デザイン設定")
ui_mode_label = st.sidebar.radio(
    "レイアウトの最適化",
    options=["PC版 (マルチカラム)", "スマホ版 (縦並び)"],
    index=0 if st.session_state.get('ui_mode', 'PC') == 'PC' else 1,
    key="sidebar_ui_mode_selector"
)
st.session_state['ui_mode'] = 'PC' if ui_mode_label == "PC版 (マルチカラム)" else 'スマホ'
is_mobile = st.session_state.get('ui_mode', 'PC') == 'スマホ'

theme_label = st.sidebar.radio(
    "表示テーマ",
    options=["ライトモード", "ダークモード"],
    index=0 if st.session_state.get('color_theme', 'light') == 'light' else 1,
    key="sidebar_color_theme_selector"
)
st.session_state['color_theme'] = 'light' if theme_label == "ライトモード" else 'dark'
is_dark = st.session_state.get('color_theme', 'light') == 'dark'

# Default Firebase configuration fallback
DEFAULT_FIREBASE_PROJECT_ID = "zenstock-screener"
if "firebase_project_id" in st.secrets:
    DEFAULT_FIREBASE_PROJECT_ID = st.secrets["firebase_project_id"]

# Declare custom component for localStorage access
_parent_dir = os.path.dirname(os.path.abspath(__file__))
_build_dir = os.path.join(_parent_dir, "local_storage_component")
_local_storage_component = components.declare_component("local_storage", path=_build_dir)

def local_storage(action, item_key, value=None, key=None):
    return _local_storage_component(action=action, item_key=item_key, value=value, key=key, default=None)

def load_portfolio_from_gsheet(user_key, gas_url):
    if not gas_url:
        return None
    try:
        url = f"{gas_url}?user={urllib.parse.quote(user_key)}"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            if res_data.get("status") == "success":
                return res_data.get("value")
    except Exception:
        pass
    return None

def save_portfolio_to_gsheet(user_key, gas_url, val_str):
    if not gas_url:
        return False
    try:
        data = json.dumps({"user": user_key, "value": val_str}).encode("utf-8")
        req = urllib.request.Request(
            gas_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            res_content = response.read().decode("utf-8")
            if "success" in res_content:
                return True
    except Exception:
        pass
    return True

def load_portfolio_from_firebase(user_key, project_id):
    if not project_id:
        return None
    try:
        url = f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/(default)/documents/portfolios/{user_key}"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            fields = res_data.get("fields", {})
            portfolio_str = fields.get("portfolio_data", {}).get("stringValue")
            return portfolio_str
    except Exception:
        # Expected if document doesn't exist yet (returns 404)
        pass
    return None

def save_portfolio_to_firebase(user_key, project_id, val_str):
    if not project_id:
        return False
    try:
        url = f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/(default)/documents/portfolios/{user_key}?updateMask.fieldPaths=portfolio_data"
        body = {
            "fields": {
                "portfolio_data": {
                    "stringValue": val_str
                }
            }
        }
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="PATCH" # Creates document if it doesn't exist, updates if it does
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            res_content = response.read().decode("utf-8")
            if "portfolio_data" in res_content:
                return True
    except Exception:
        pass
    return True

# Page config
st.set_page_config(
    page_title="ZenStockScreener | 株価上昇シグナル選定ツール",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inject premium custom CSS dynamically based on theme selection
bg_color = "#0b0f19" if is_dark else "#f8fafc"
card_bg = "#151d30" if is_dark else "#ffffff"
text_color = "#e2e8f0" if is_dark else "#1e293b" # Softer text color for dark mode to prevent eye strain
primary_color = "#3b82f6" if is_dark else "#2563eb"
border_color = "#1e293b" if is_dark else "#e2e8f0"
unselected_btn_bg = "#0b0f19" if is_dark else "#e2e8f0" # Dark black background for unselected buttons in dark mode, soft grey in light mode
title_bg = "linear-gradient(135deg, #151d30 0%, #0b0f19 100%)" if is_dark else "linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%)"
title_border = "#1e293b" if is_dark else "#cbd5e1"
title_text_color = "#3b82f6" if is_dark else "#1e3a8a"
subtitle_text_color = "#94a3b8" if is_dark else "#475569"

# Specific colors for Glide Data Grid (st.dataframe) to make it black-based in dark mode
gdg_bg_cell = "#0b0f19" if is_dark else "#ffffff"
gdg_bg_header = "#05070c" if is_dark else "#f8fafc"
gdg_bg_cell_hover = "#151d30" if is_dark else "#f8fafc"
gdg_bg_header_hover = "#151d30" if is_dark else "#ffffff"
dataframe_filter = "invert(0.94) hue-rotate(180deg)" if is_dark else "none"

st.markdown(f"""
<style>
    /* CSS theme overrides on root */
    :root, .stApp {{
        --background-color: {bg_color};
        --secondary-background-color: {card_bg};
        --text-color: {text_color};
        --primary-color: {primary_color};
        --border-color: {border_color};
        --unselected-button-bg: {unselected_btn_bg};
        
        /* Streamlit Generic Theme Variable Overrides */
        --theme-background-color: {bg_color};
        --theme-secondary-background-color: {card_bg};
        --theme-text-color: {text_color};
        --theme-primary-color: {primary_color};
        --theme-border-color: {border_color};
        
        /* Glide Data Grid (st.dataframe) overrides on root */
        --gdg-bg-cell: {gdg_bg_cell} !important;
        --gdg-bg-header: {gdg_bg_header} !important;
        --gdg-bg-cell-hover: {gdg_bg_cell_hover} !important;
        --gdg-bg-header-hover: {gdg_bg_header_hover} !important;
        --gdg-text-dark: {text_color} !important;
        --gdg-text-light: {text_color} !important;
        --gdg-text-group-header: {text_color} !important;
        --gdg-text-header: {text_color} !important;
        --gdg-text-medium: {text_color} !important;
        --gdg-border-color: {border_color} !important;
        --gdg-accent-color: {primary_color} !important;
        --gdg-accent-light: rgba(59, 130, 246, 0.12) !important;
    }}
    
    /* Target Glide Data Grid elements specifically */
    div.stDataFrame, div.stDataFrameGlideDataEditor, [data-testid="stDataFrame"], [data-testid="stDataFrameResizable"] {{
        --gdg-bg-cell: {gdg_bg_cell} !important;
        --gdg-bg-header: {gdg_bg_header} !important;
        --gdg-bg-cell-hover: {gdg_bg_cell_hover} !important;
        --gdg-bg-header-hover: {gdg_bg_header_hover} !important;
        --gdg-text-dark: {text_color} !important;
        --gdg-text-light: {text_color} !important;
        --gdg-text-group-header: {text_color} !important;
        --gdg-text-header: {text_color} !important;
        --gdg-text-medium: {text_color} !important;
        --gdg-border-color: {border_color} !important;
        --gdg-accent-color: {primary_color} !important;
        --gdg-accent-light: rgba(59, 130, 246, 0.12) !important;
        filter: {dataframe_filter} !important;
    }}
    
    /* Ensure Streamlit's native background matches our theme */
    .stApp, [data-testid="stApp"], [data-testid="stAppViewContainer"], [data-testid="stMainViewContainer"], [data-testid="stHeader"] {{
        background-color: {bg_color} !important;
        color: {text_color} !important;
    }}
    
    /* Styling headers and blocks */
    .title-container {{
        background: {title_bg};
        border-radius: 12px;
        padding: 25px;
        margin-bottom: 25px;
        border: 1px solid {title_border};
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
    }}
    .title-text {{
        font-family: 'Outfit', sans-serif;
        color: {title_text_color} !important;
        font-weight: 800 !important;
        font-size: 2.5rem !important;
        margin: 0 !important;
        display: block !important;
    }}
    .subtitle-text {{
        color: {subtitle_text_color} !important;
        font-size: 1.1rem !important;
        margin-top: 10px !important;
        margin-bottom: 0 !important;
        display: block !important;
    }}
    .card {{
        background: {card_bg};
        border-radius: 10px;
        padding: 20px;
        border: 1px solid {border_color};
        margin-bottom: 20px;
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05), 0 2px 4px -1px rgba(0,0,0,0.03);
        color: {text_color};
    }}
    .metric-title {{
        color: {'#94a3b8' if is_dark else '#64748b'};
        font-size: 0.85rem;
        margin-bottom: 5px;
    }}
    .metric-value {{
        font-size: 1.5rem;
        font-weight: bold;
        color: {text_color};
    }}
    .metric-accent {{
        color: {'#10b981' if is_dark else '#16a34a'};
    }}
    /* Base style for premium list buttons */
    button.premium-list-btn {{
        display: flex !important;
        align-items: center !important;
        border-radius: 12px !important;
        font-weight: 600 !important;
        border: 1px solid {border_color} !important;
        background: {card_bg} !important;
        color: {text_color} !important;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05) !important;
        transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
        margin-bottom: 8px !important;
        width: 100% !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
    }}
    /* Centered styling for shape toggle buttons */
    button.premium-list-btn.premium-center {{
        text-align: center !important;
        justify-content: center !important;
        padding: 8px 4px !important;
        font-size: 0.8rem !important;
    }}
    /* Left-aligned styling for portfolio and watchlist buttons */
    button.premium-list-btn.premium-left {{
        text-align: left !important;
        justify-content: flex-start !important;
        padding: 14px 18px !important;
        font-size: 0.92rem !important;
    }}
    /* Hover effect */
    button.premium-list-btn:hover {{
        border-color: {primary_color} !important;
        background-color: {'#1e293b' if is_dark else '#f8fafc'} !important;
        color: {primary_color} !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 4px 12px -2px rgba(37, 99, 235, 0.12) !important;
    }}
    /* Active selected style (Primary button override) */
    button.premium-list-btn.premium-active {{
        border-color: {primary_color} !important;
        background: linear-gradient(135deg, {primary_color} 0%, {'#1d4ed8' if not is_dark else '#2563eb'} 100%) !important;
        color: #ffffff !important;
        box-shadow: 0 4px 14px 0 rgba(37, 99, 235, 0.3) !important;
    }}
    button.premium-list-btn.premium-active:hover {{
        background: linear-gradient(135deg, {'#1d4ed8' if not is_dark else '#2563eb'} 0%, {'#1e40af' if not is_dark else '#1d4ed8'} 100%) !important;
        color: #ffffff !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 18px 0 rgba(37, 99, 235, 0.4) !important;
    }}
    
    /* Native Streamlit Base Buttons (Secondary) */
    div.stButton > button, div.stDownloadButton > button, [data-testid="stBaseButton-secondary"] button {{
        background: var(--unselected-button-bg) !important;
        color: var(--text-color) !important;
        border: 1px solid var(--border-color) !important;
        transition: all 0.2s ease !important;
    }}
    div.stButton > button:hover, div.stDownloadButton > button:hover, [data-testid="stBaseButton-secondary"] button:hover {{
        border-color: var(--primary-color) !important;
        color: var(--primary-color) !important;
        background: var(--background-color) !important;
    }}
    
    /* Native Streamlit Primary Buttons */
    [data-testid="stBaseButton-primary"] button, div.stButton > button[type="primary"] {{
        background: var(--primary-color) !important;
        color: #ffffff !important;
        border: 1px solid var(--primary-color) !important;
        transition: all 0.2s ease !important;
    }}
    [data-testid="stBaseButton-primary"] button:hover, div.stButton > button[type="primary"]:hover {{
        background: var(--primary-color) !important;
        opacity: 0.9 !important;
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.25) !important;
    }}
    
    /* Text Inputs, Number Inputs, Date Inputs, Textareas */
    div[data-testid="stTextInput"] input, div[data-testid="stNumberInput"] input, div[data-testid="stDateInput"] input, textarea {{
        background-color: var(--secondary-background-color) !important;
        color: var(--text-color) !important;
        border: 1px solid var(--border-color) !important;
    }}
    div[data-testid="stTextInput"] input:focus, div[data-testid="stNumberInput"] input:focus, div[data-testid="stDateInput"] input:focus, textarea:focus {{
        border-color: var(--primary-color) !important;
        box-shadow: 0 0 0 1px var(--primary-color) !important;
    }}
    
    /* Selectbox (BaseWeb dropdown select) */
    div[data-baseweb="select"] > div {{
        background-color: var(--secondary-background-color) !important;
        color: var(--text-color) !important;
        border: 1px solid var(--border-color) !important;
    }}
    div[data-baseweb="select"] * {{
        color: var(--text-color) !important;
    }}
    
    /* Dropdown menu list styling */
    ul[role="listbox"] {{
        background-color: var(--secondary-background-color) !important;
        border: 1px solid var(--border-color) !important;
    }}
    li[role="option"] {{
        background-color: var(--secondary-background-color) !important;
        color: var(--text-color) !important;
        transition: all 0.15s ease !important;
    }}
    li[role="option"]:hover, li[role="option"][aria-selected="true"] {{
        background-color: var(--background-color) !important;
        color: var(--primary-color) !important;
    }}
    
    /* Tabs styling */
    button[data-baseweb="tab"] {{
        color: var(--text-color) !important;
        border-bottom-width: 2px !important;
        transition: all 0.2s ease !important;
        opacity: 0.55 !important;
    }}
    button[data-baseweb="tab"] div {{
        color: var(--text-color) !important;
    }}
    button[data-baseweb="tab"]:hover {{
        opacity: 0.85 !important;
    }}
    button[data-baseweb="tab"][aria-selected="true"] {{
        border-bottom-color: var(--primary-color) !important;
        opacity: 1 !important;
    }}
    button[data-baseweb="tab"][aria-selected="true"] div {{
        color: var(--primary-color) !important;
        font-weight: 600 !important;
    }}
    div[role="tablist"] {{
        border-bottom-color: var(--border-color) !important;
    }}
    
    /* Expanders styling */
    [data-testid="stExpander"] {{
        background-color: var(--secondary-background-color) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: 8px !important;
    }}
    [data-testid="stExpander"] * {{
        color: var(--text-color) !important;
    }}
    
    /* Sidebar styling overrides */
    [data-testid="stSidebar"] {{
        background-color: var(--secondary-background-color) !important;
        border-right: 1px solid var(--border-color) !important;
    }}
    [data-testid="stSidebar"] * {{
        color: var(--text-color) !important;
    }}
    /* Ensure radio label text etc doesn't get messed up */
    [data-testid="stSidebar"] div[data-testid="stWidgetLabel"] p {{
        color: var(--text-color) !important;
        opacity: 0.95;
    }}
    
    /* Segmented Control Styling */
    div[data-testid="stButtonGroup"] {{
        background: transparent !important;
    }}
    div[data-testid="stButtonGroup"] button[data-testid^="stBaseButton-segmented_control"] {{
        background: var(--unselected-button-bg) !important;
        color: var(--text-color) !important;
        opacity: 0.6 !important;
        border: 1px solid var(--border-color) !important;
        transition: all 0.2s ease !important;
    }}
    div[data-testid="stButtonGroup"] button[data-testid^="stBaseButton-segmented_control"]:hover {{
        border-color: var(--primary-color) !important;
        color: var(--primary-color) !important;
        opacity: 0.9 !important;
        background: var(--background-color) !important;
    }}
    /* Selected segment */
    div[data-testid="stButtonGroup"] button[data-testid="stBaseButton-segmented_controlActive"],
    div[data-testid="stButtonGroup"] button[aria-checked="true"],
    div[data-testid="stButtonGroup"] button[aria-selected="true"],
    div[data-testid="stButtonGroup"] button[aria-pressed="true"] {{
        background: var(--primary-color) !important;
        background-color: var(--primary-color) !important;
        color: #ffffff !important;
        opacity: 1 !important;
        border-color: var(--primary-color) !important;
    }}
    div[data-testid="stButtonGroup"] button[data-testid^="stBaseButton-segmented_control"] * {{
        color: var(--text-color) !important;
    }}
    div[data-testid="stButtonGroup"] button[data-testid="stBaseButton-segmented_controlActive"] *,
    div[data-testid="stButtonGroup"] button[aria-checked="true"] *,
    div[data-testid="stButtonGroup"] button[aria-selected="true"] *,
    div[data-testid="stButtonGroup"] button[aria-pressed="true"] * {{
        color: #ffffff !important;
    }}
</style>

""", unsafe_allow_html=True)

# Inject global Javascript for premium button styling
st.components.v1.html("""
<script>
    const parentDoc = window.parent.document;
    function applyStyles() {
        const buttons = parentDoc.querySelectorAll('button');
        buttons.forEach(btn => {
            const txt = btn.textContent || "";
            if (btn.closest('[data-testid="stSegmentedControl"]') || btn.closest('[data-testid="stButtonGroup"]') || btn.closest('[data-testid="stTabs"]') || btn.getAttribute('role') === 'tab') {
                if (btn.classList.contains('premium-list-btn')) {
                    btn.classList.remove('premium-list-btn');
                    btn.classList.remove('premium-active');
                    btn.classList.remove('premium-left');
                    btn.classList.remove('premium-center');
                }
                return;
            }
            if (txt.includes('💼') || txt.includes('⭐') || txt.includes('📈') || txt.includes('📉') || txt.includes('🔄')) {
                if (!btn.classList.contains('premium-list-btn')) {
                    btn.classList.add('premium-list-btn');
                }
                const testid = btn.getAttribute('data-testid');
                if (testid && testid.includes('primary')) {
                    btn.classList.add('premium-active');
                } else {
                    btn.classList.remove('premium-active');
                }
                
                if (txt.includes('💼') || txt.includes('⭐')) {
                    btn.classList.add('premium-left');
                    btn.classList.remove('premium-center');
                } else {
                    btn.classList.add('premium-center');
                    btn.classList.remove('premium-left');
                }
            }
        });
    }
    setInterval(applyStyles, 150);
    applyStyles();
</script>
""", height=0, width=0)

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
    
    <div style="background-color: var(--secondary-background-color, #f8fafc); border: 1px solid var(--border-color, #e2e8f0); border-radius: 8px; padding: 15px; margin-top: 15px; margin-bottom: 20px; color: var(--text-color, #1e293b);">
        <!-- 購入銘柄 -->
        <div style="display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 1px solid var(--border-color, #e2e8f0); padding: 10px 0;">
            <span style="color: var(--text-color, #64748b); opacity: 0.8; font-weight: bold; min-width: 100px; flex-shrink: 0; text-align: left;">購入銘柄</span>
            <span style="text-align: right; font-weight: bold; color: var(--text-color, #0f172a); word-break: break-all; margin-left: 10px;">{name} ({ticker})</span>
        </div>
        <!-- 購入株数 -->
        <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color, #e2e8f0); padding: 10px 0;">
            <span style="color: var(--text-color, #64748b); opacity: 0.8; min-width: 100px; flex-shrink: 0; text-align: left;">購入株数</span>
            <span style="text-align: right; font-weight: bold; color: var(--text-color, #0f172a);">{qty:,} 株</span>
        </div>
        <!-- 平均取得単価 -->
        <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color, #e2e8f0); padding: 10px 0;">
            <span style="color: var(--text-color, #64748b); opacity: 0.8; min-width: 100px; flex-shrink: 0; text-align: left;">平均取得単価</span>
            <span style="text-align: right; font-weight: bold; color: #16a34a;">{format_price(price, ticker)}</span>
        </div>
        <!-- 概算投資金額 -->
        <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px 0;">
            <span style="color: var(--text-color, #64748b); opacity: 0.8; font-weight: bold; min-width: 100px; flex-shrink: 0; text-align: left;">概算投資金額</span>
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
    
    <div style="background-color: var(--secondary-background-color, #f8fafc); border: 1px solid var(--border-color, #e2e8f0); border-radius: 8px; padding: 15px; margin-top: 15px; margin-bottom: 20px; color: var(--text-color, #1e293b);">
        <!-- 売却銘柄 -->
        <div style="display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 1px solid var(--border-color, #e2e8f0); padding: 10px 0;">
            <span style="color: var(--text-color, #64748b); opacity: 0.8; font-weight: bold; min-width: 100px; flex-shrink: 0; text-align: left;">売却銘柄</span>
            <span style="text-align: right; font-weight: bold; color: var(--text-color, #0f172a); word-break: break-all; margin-left: 10px;">{name} ({ticker})</span>
        </div>
        <!-- 売却株数 -->
        <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color, #e2e8f0); padding: 10px 0;">
            <span style="color: var(--text-color, #64748b); opacity: 0.8; min-width: 100px; flex-shrink: 0; text-align: left;">売却株数</span>
            <span style="text-align: right; font-weight: bold; color: var(--text-color, #0f172a);">{qty:,} 株</span>
        </div>
        <!-- 売却単価 -->
        <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color, #e2e8f0); padding: 10px 0;">
            <span style="color: var(--text-color, #64748b); opacity: 0.8; min-width: 100px; flex-shrink: 0; text-align: left;">売却単価</span>
            <span style="text-align: right; font-weight: bold; color: var(--text-color, #0f172a);">{price_str}</span>
        </div>
        <!-- 売却受取金額 -->
        <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color, #e2e8f0); padding: 10px 0;">
            <span style="color: var(--text-color, #64748b); opacity: 0.8; min-width: 100px; flex-shrink: 0; text-align: left;">売却受取金額</span>
            <span style="text-align: right; font-weight: bold; color: #2563eb;">{total_return_str}</span>
        </div>
        <!-- 確定実現損益 -->
        <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px 0;">
            <span style="color: var(--text-color, #64748b); font-weight: bold; min-width: 100px; flex-shrink: 0; text-align: left;">確定実現損益</span>
            <span style="text-align: right; font-weight: bold; color: {pl_color}; font-size: 1.2rem;">{realized_pl_str}</span>
        </div>
    </div>
    
    ※ ポートフォリオの「確定取引（仮想売却）履歴一覧」にて履歴が確認できます。
    """, unsafe_allow_html=True)
    if st.button("確認して閉じる", type="primary", use_container_width=True, key="dlg_sell_confirm_close_btn"):
        st.rerun()

def patch_history_with_fast_info(ticker, df, skip_fast_info=False):
    if df.empty:
        return df
        
    # Drop rows where Close is NaN first
    df = df.dropna(subset=['Close'])
    if df.empty:
        return df
        
    if not skip_fast_info:
        try:
            tk = yf.Ticker(ticker)
            f_info = tk.fast_info
            last_price = f_info.get('lastPrice')
            if last_price is not None and not pd.isna(last_price):
                tz = df.index.tz
                today = datetime.datetime.now(tz)
                today_start = today.replace(hour=0, minute=0, second=0, microsecond=0)
                
                # If today's date is not in the history index, append a new row for today
                if today_start not in df.index:
                    new_row = pd.DataFrame(index=[today_start])
                    new_row['Close'] = last_price
                    if 'Open' in df.columns: new_row['Open'] = f_info.get('open') or last_price
                    if 'High' in df.columns: new_row['High'] = f_info.get('dayHigh') or last_price
                    if 'Low' in df.columns: new_row['Low'] = f_info.get('dayLow') or last_price
                    if 'Volume' in df.columns: new_row['Volume'] = f_info.get('lastVolume') or 0.0
                    df = pd.concat([df, new_row])
                else:
                    # Update today's row with the latest real-time price
                    df.loc[today_start, 'Close'] = last_price
                    if 'Open' in df.columns and f_info.get('open') is not None:
                        df.loc[today_start, 'Open'] = f_info.get('open')
                    if 'High' in df.columns and f_info.get('dayHigh') is not None:
                        df.loc[today_start, 'High'] = f_info.get('dayHigh')
                    if 'Low' in df.columns and f_info.get('dayLow') is not None:
                        df.loc[today_start, 'Low'] = f_info.get('dayLow')
                    if 'Volume' in df.columns and f_info.get('lastVolume') is not None:
                        df.loc[today_start, 'Volume'] = f_info.get('lastVolume')
        except Exception:
            pass
            
    return df

def z_normalize(seq):
    arr = np.array(seq)
    std = np.std(arr)
    if std == 0:
        return np.zeros_like(arr)
    return (arr - np.mean(arr)) / std

def check_shape_match(prices, threshold=0.70):
    if len(prices) < 30:
        return None, 0.0
    
    # Take last 30 days
    y_stock = prices[-30:]
    Z_stock = z_normalize(y_stock)
    
    t = np.arange(30)
    # Template 1: Upward Trend (上昇傾向)
    temp1 = t
    Z_temp1 = z_normalize(temp1)
    
    # Template 2: Downward Attenuation (下降減衰)
    temp2 = np.exp(-0.05 * t)
    Z_temp2 = z_normalize(temp2)
    
    # Template 3: Reversal / Bottomed Out & Rising (上昇反転)
    temp3 = (t - 12) ** 2
    Z_temp3 = z_normalize(temp3)
    
    # Calculate correlations
    r1 = np.dot(Z_stock, Z_temp1) / 30.0
    r2 = np.dot(Z_stock, Z_temp2) / 30.0
    r3 = np.dot(Z_stock, Z_temp3) / 30.0
    
    corrs = [r1, r2, r3]
    max_idx = np.argmax(corrs)
    max_corr = corrs[max_idx]
    
    labels = ["上昇傾向", "下降減衰", "上昇反転"]
    matched_label = labels[max_idx]
    
    # If the matched label is "上昇反転" and the price has gone up in the last 5 days,
    # we allow a lower correlation threshold (e.g. 0.45 instead of 0.70) to classify it!
    effective_threshold = threshold
    if matched_label == "上昇反転" and len(prices) >= 5 and prices[-1] > prices[-5]:
        effective_threshold = 0.45
        
    if max_corr >= effective_threshold:
        return matched_label, max_corr
    return None, 0.0

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
    
    is_mobile = False
    is_dark = False
    try:
        import streamlit as st
        is_mobile = st.session_state.get('ui_mode', 'PC') == 'スマホ'
        is_dark = st.session_state.get('color_theme', 'light') == 'dark'
    except:
        pass
        
    symbol = "$" if ticker and is_us_stock(ticker) else "¥"
    fmt = ".2f" if ticker and is_us_stock(ticker) else ".0f"
    unit = "ドル" if ticker and is_us_stock(ticker) else "円"
    
    # Target pattern
    fig.add_trace(go.Scatter(
        x=list(range(N)),
        y=target_prices,
        mode='lines+markers',
        name='基準パターン (指定範囲)',
        line=dict(color='#60a5fa' if is_dark else '#1e3a8a', width=4),
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
    
    title_text = "類似パターンの重ね合わせ" if is_mobile else "類似パターンの株価値動き重ね合わせ (現在値基準でスケール調整)"
    fig.update_layout(
        title=dict(
            text=title_text,
            font=dict(size=13 if is_mobile else 15)
        ),
        template="plotly_dark" if is_dark else "plotly_white",
        height=450,
        margin=dict(l=10, r=10, t=50, b=50),
        legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5),
        dragmode=False if is_mobile else "pan"
    )
    
    gridcolor = '#1e293b' if is_dark else '#f1f5f9'
    zerolinecolor = '#334155' if is_dark else '#cbd5e1'
    fig.update_yaxes(gridcolor=gridcolor, zerolinecolor=zerolinecolor)
    fig.update_xaxes(gridcolor=gridcolor)
    return fig

def create_selection_chart(df, ticker, name, start_date, end_date):
    fig = go.Figure()
    
    is_mobile = False
    is_dark = False
    try:
        import streamlit as st
        is_mobile = st.session_state.get('ui_mode', 'PC') == 'スマホ'
        is_dark = st.session_state.get('color_theme', 'light') == 'dark'
    except:
        pass
        
    symbol = "$" if is_us_stock(ticker) else "¥"
    fmt = ".2f" if is_us_stock(ticker) else ".0f"
    unit = "ドル" if is_us_stock(ticker) else "円"
    
    # Plot Close price
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['Close'],
        mode='lines',
        name='株価 (終値)',
        line=dict(color='#3b82f6' if is_dark else '#2563eb', width=2),
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
    
    title_text = f"{ticker} - 期間選択" if is_mobile else f"{name} ({ticker}) - パターン範囲選択（ドラッグして期間を調整）"
    fig.update_layout(
        title=dict(
            text=title_text,
            font=dict(size=13 if is_mobile else 15)
        ),
        template="plotly_dark" if is_dark else "plotly_white",
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
    gridcolor = '#1e293b' if is_dark else '#f1f5f9'
    zerolinecolor = '#334155' if is_dark else '#cbd5e1'
    fig.update_yaxes(gridcolor=gridcolor, zerolinecolor=zerolinecolor)
    fig.update_xaxes(gridcolor=gridcolor)
    return fig

@st.cache_data(ttl=3600)
def batch_download_histories(tickers_list, period="1y"):
    import time
    if not tickers_list:
        return {}
        
    chunk_size = 150
    histories = {}
    
    # Process in chunks of 150 to avoid URL length limitations and reduce rate limiting risk
    for i in range(0, len(tickers_list), chunk_size):
        chunk = tickers_list[i:i+chunk_size]
        try:
            data = yf.download(chunk, period=period, progress=False)
            if data.empty:
                continue
                
            if len(chunk) == 1:
                ticker = chunk[0]
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
                df = patch_history_with_fast_info(ticker, df, skip_fast_info=True)
                df = df.dropna(subset=['Close'])
                if not df.empty:
                    histories[ticker] = df
            else:
                for ticker in chunk:
                    try:
                        if isinstance(data.columns, pd.MultiIndex) and 'Close' in data and ticker in data['Close'].columns:
                            df = pd.DataFrame({
                                'Open': data['Open'][ticker],
                                'High': data['High'][ticker],
                                'Low': data['Low'][ticker],
                                'Close': data['Close'][ticker],
                                'Volume': data['Volume'][ticker]
                            })
                            df = patch_history_with_fast_info(ticker, df, skip_fast_info=True)
                            df = df.dropna(subset=['Close'])
                            if not df.empty:
                                histories[ticker] = df
                    except Exception:
                        continue
            # Small throttle delay between chunks
            if len(tickers_list) > chunk_size:
                time.sleep(0.3)
        except Exception:
            continue
            
    return histories

# Cached function for downloading ticker fundamental info
@st.cache_data(ttl=86400)
def get_ticker_info(ticker):
    raw_info = None
    try:
        t = yf.Ticker(ticker)
        raw_info = t.info
    except Exception:
        raw_info = {}
        
    # If raw_info failed or is empty (typical on Streamlit Cloud due to rate limit/IP block), 
    # and it is a Japanese stock, fall back to official Yahoo Finance JP scraping!
    if (not raw_info or not raw_info.get('longName')) and ticker.endswith('.T'):
        code = ticker.split('.')[0]
        try:
            import re
            url = f"https://finance.yahoo.co.jp/quote/{code}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            html = urllib.request.urlopen(req, timeout=5).read().decode('utf-8')
            
            # Find detailData block
            target = '\\"detailData\\":'
            idx = html.find(target)
            if idx == -1:
                target = '"detailData":'
                idx = html.find(target)
                
            if idx != -1:
                start_idx = idx + len(target)
                brace_count = 0
                end_idx = start_idx
                for i in range(start_idx, len(html)):
                    if html[i] == '{':
                        brace_count += 1
                    elif html[i] == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end_idx = i + 1
                            break
                            
                json_str = html[start_idx:end_idx].replace('\\"', '"').replace('\\\\', '\\')
                data = json.loads(json_str)
                
                # Parse title for company name
                long_name = ticker
                title_match = re.search(r'<title>(.+?)</title>', html)
                if title_match:
                    title_text = title_match.group(1)
                    name_match = re.search(r'(.+?)【[^】]+】', title_text)
                    if name_match:
                        long_name = name_match.group(1).strip()
                
                indicators = data.get('indicators', {})
                industry = data.get('industry', {}).get('name')
                
                raw_info = {
                    'longName': long_name,
                    'shortName': long_name,
                    'trailingPE': indicators.get('per', {}).get('value'),
                    'priceToBook': indicators.get('pbr', {}).get('value'),
                    'returnOnEquity': indicators.get('roe', {}).get('value'),
                    'dividendYield': indicators.get('shareDividendYield', {}).get('value'),
                    'marketCap': None,
                    'fiftyTwoWeekHigh': None,
                    'fiftyTwoWeekLow': None,
                    'sector': industry,
                    'industry': industry,
                    'longBusinessSummary': "",
                    'netIncome': None,
                    'opMargin': indicators.get('operatingMargins', {}).get('value'),
                    'totalCash': None,
                    'totalDebt': None,
                    'debtToEquity': indicators.get('equityRatio', {}).get('value')
                }
        except Exception:
            pass

    if not raw_info:
        raw_info = {}

    try:
        # Extract net income keys
        net_income = raw_info.get('netIncome') or raw_info.get('netIncomeToCommon')
        op_margin = raw_info.get('operatingMargins') if raw_info.get('operatingMargins') is not None else raw_info.get('opMargin')
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
        
        def safe_float(val):
            if val is None:
                return None
            try:
                if isinstance(val, str):
                    val = val.replace(',', '').replace('%', '').strip()
                    if val == '---' or val == '':
                        return None
                return float(val)
            except (ValueError, TypeError):
                return None

        # Clean numeric fields
        needed['trailingPE'] = safe_float(needed['trailingPE'])
        needed['priceToBook'] = safe_float(needed['priceToBook'])
        needed['returnOnEquity'] = safe_float(needed['returnOnEquity'])
        needed['dividendYield'] = safe_float(needed['dividendYield'])
        needed['marketCap'] = safe_float(needed['marketCap'])
        needed['fiftyTwoWeekHigh'] = safe_float(needed['fiftyTwoWeekHigh'])
        needed['fiftyTwoWeekLow'] = safe_float(needed['fiftyTwoWeekLow'])
        needed['netIncome'] = safe_float(needed['netIncome'])
        needed['opMargin'] = safe_float(needed['opMargin'])
        needed['totalCash'] = safe_float(needed['totalCash'])
        needed['totalDebt'] = safe_float(needed['totalDebt'])
        needed['debtToEquity'] = safe_float(needed['debtToEquity'])
        
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

def parse_jpx_df(df):
    market_col = '市場・商品区分'
    if market_col not in df.columns:
        for col in df.columns:
            if '市場' in str(col) or '区分' in str(col):
                if df[col].astype(str).str.contains("プライム").any():
                    market_col = col
                    break
                    
    size_col = '規模区分'
    if size_col not in df.columns:
        for col in df.columns:
            if '規模' in str(col):
                size_col = col
                break
    
    prime_df = df[df[market_col].astype(str).str.contains("プライム")]
    components = {}
    for idx, row in prime_df.iterrows():
        code = str(row['コード']).strip()
        if len(code) == 4 and code.isalnum():
            ticker = f"{code}.T"
            name = str(row['銘柄名']).strip()
            sector = str(row['33業種区分']).strip()
            
            size_val = "-"
            if size_col in df.columns:
                size_val = str(row[size_col]).strip()
            
            # Map size division to a cleaner tag
            size_tag = "その他"
            if "Core30" in size_val:
                size_tag = "TOPIX Core30 (超大型株)"
            elif "Large70" in size_val:
                size_tag = "TOPIX Large70 (大型株)"
            elif "Mid400" in size_val:
                size_tag = "TOPIX Mid400 (中堅・中型株)"
            elif "Small 1" in size_val:
                size_tag = "TOPIX Small 1 (中小型株)"
            elif "Small 2" in size_val:
                size_tag = "TOPIX Small 2 (小型株)"
                
            inherited_tags = []
            if ticker in JP_TICKERS:
                inherited_tags = JP_TICKERS[ticker].get("tags", [])
                
            components[ticker] = {
                "name": name,
                "tags": list(set(["東証プライム", sector, size_tag] + inherited_tags)),
                "sector": sector,
                "size": size_tag
            }
    return components

@st.cache_data(ttl=86400)
def fetch_tse_prime_tickers():
    # 1. Try to load from local JSON (High Performance & Stable)
    try:
        json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tse_prime_tickers.json")
        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                res = json.load(f)
                if res:
                    # Merge JP_TICKERS tags for matching tickers
                    for k, v in JP_TICKERS.items():
                        if k in res:
                            existing_tags = res[k].get("tags", [])
                            merged_tags = list(set(existing_tags + v.get("tags", [])))
                            res[k]["tags"] = merged_tags
                    return res
    except Exception:
        pass

    # 2. Fallback to dynamic URL download
    url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
    try:
        df = pd.read_excel(url)
        res = parse_jpx_df(df)
        if res:
            return res
    except Exception:
        pass
        
    try:
        page_url = "https://www.jpx.co.jp/markets/statistics-equities/misc/01.html"
        headers = {"User-Agent": "Mozilla/5.0"}
        req = urllib.request.Request(page_url, headers=headers)
        with urllib.request.urlopen(req) as response:
            html = response.read()
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            if "data_j.xls" in a["href"]:
                resolved_url = urllib.parse.urljoin(page_url, a["href"])
                df = pd.read_excel(resolved_url)
                res = parse_jpx_df(df)
                if res:
                    return res
    except Exception as e:
        st.warning(f"東証プライム銘柄の動的取得に失敗しました。ローカルデータを使用します。エラー: {e}")
        
@st.cache_data(ttl=86400)
def fetch_tse_growth_tickers():
    # 1. Try to load from local JSON (High Performance & Stable)
    try:
        json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tse_growth_tickers.json")
        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                res = json.load(f)
                if res:
                    # Merge JP_TICKERS tags for matching tickers
                    for k, v in JP_TICKERS.items():
                        if k in res:
                            existing_tags = res[k].get("tags", [])
                            merged_tags = list(set(existing_tags + v.get("tags", [])))
                            res[k]["tags"] = merged_tags
                    return res
    except Exception:
        pass
    return {}

    # 3. Last resort fallback based on JP_TICKERS
    fallback_res = {}
    for k, v in JP_TICKERS.items():
        fallback_res[k] = {
            "name": v.get("name", k),
            "tags": v.get("tags", []) + ["東証プライム"],
            "sector": v.get("tags", ["その他"])[0],
            "size": "その他"
        }
    return fallback_res

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
                'vol_surge_ratio': vol_5d / vol_25d if vol_25d > 0 else 1.0,
                'rev_growth': None,
                'eps_growth': None
            }
        }
        
    # --- 2. ファンダメンタルズスコアリング（7点満点に拡張） ---
    def safe_float(val):
        if val is None:
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    per = safe_float(info.get('trailingPE'))
    pbr = safe_float(info.get('priceToBook'))
    roe = safe_float(info.get('returnOnEquity'))
    div_yield = safe_float(info.get('dividendYield'))
    net_inc = safe_float(info.get('netIncome'))
    op_margin = safe_float(info.get('opMargin'))
    de_ratio = safe_float(info.get('debtToEquity'))
    
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
        cash_val = safe_float(info.get('totalCash')) or 0.0
        debt_val = safe_float(info.get('totalDebt')) or 0.0
        f_solvency = cash_val >= debt_val
        
    # (g) 還元・インカム (配当利回り >= 3%)
    f_dividend = div_yield is not None and div_yield >= 3.0
    
    fund_score = sum([f_roe, f_op_margin, f_profitable, f_per, f_pbr, f_solvency, f_dividend])
    
    rev_growth = safe_float(info.get('revenueGrowth'))
    if rev_growth is not None:
        rev_growth = rev_growth * 100.0
        
    eps_growth = safe_float(info.get('earningsGrowth'))
    if eps_growth is not None:
        eps_growth = eps_growth * 100.0
        
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
        'vol_surge_ratio': vol_5d / vol_25d if vol_25d > 0 else 1.0,
        'rev_growth': rev_growth,
        'eps_growth': eps_growth
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

# Helper to translate text dynamically
@st.cache_data(ttl=86400)
def translate_text(text, dest_lang="ja", src_lang="en"):
    if not text:
        return ""
    try:
        import urllib.request
        import urllib.parse
        import json
        truncated_text = text[:1200]
        url = 'https://translate.googleapis.com/translate_a/single?client=gtx&sl=' + src_lang + '&tl=' + dest_lang + '&dt=t&q=' + urllib.parse.quote(truncated_text)
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            res = json.loads(response.read().decode('utf-8'))
            result = ''.join([item[0] for item in res[0] if item[0]])
            return result
    except Exception:
        return text

# Helper to classify industry
def classify_industry(industry, sector, summary_lower):
    ind_lower = (industry or "").lower()
    sec_lower = (sector or "").lower()
    
    if "auto" in ind_lower or "vehicle" in ind_lower or "automotive" in ind_lower:
        return "automotive"
    elif "semiconductor" in ind_lower or "silicon" in ind_lower or "lithography" in ind_lower or "wafer" in ind_lower:
        return "semiconductors"
    elif "conglomerates" in ind_lower or "trading company" in ind_lower or "trading" in ind_lower or "物産" in ind_lower or "商事" in ind_lower:
        return "trading_conglomerates"
    elif "electronic components" in ind_lower or "scientific" in ind_lower or "sensor" in ind_lower or "precision" in ind_lower or "instruments" in ind_lower:
        return "electronics"
    elif "telecom" in ind_lower or "communication services" in sec_lower or "carrier" in ind_lower:
        return "telecom"
    elif "internet content" in ind_lower or "internet retail" in ind_lower or "e-commerce" in ind_lower or "web" in ind_lower:
        return "internet"
    elif "software—application" in ind_lower or "software—infrastructure" in ind_lower or "saas" in ind_lower or "system integrator" in ind_lower or "information technology services" in ind_lower:
        return "software"
    elif "drug" in ind_lower or "biotechnology" in ind_lower or "pharmaceutical" in ind_lower:
        return "biotech"
    elif "medical devices" in ind_lower or "medical instruments" in ind_lower or "diagnostics" in ind_lower:
        return "medical_devices"
    elif "chemical" in ind_lower:
        return "chemicals"
    elif "steel" in ind_lower or "metal" in ind_lower or "mining" in ind_lower:
        return "metals"
    elif "machinery" in ind_lower or "tool" in ind_lower or "automation" in ind_lower:
        return "machinery"
    elif "construction" in ind_lower or "engineering" in ind_lower or "infrastructure" in ind_lower:
        return "construction"
    elif "real estate" in ind_lower or "reit" in ind_lower or "property" in ind_lower:
        return "realestate"
    elif "banks" in ind_lower:
        return "banks"
    elif "capital markets" in ind_lower or "brokerage" in ind_lower or "financial conglomerates" in ind_lower or "asset management" in ind_lower:
        return "brokerage"
    elif "insurance" in ind_lower:
        return "insurance"
    elif "gaming" in ind_lower or "entertainment" in ind_lower or "toy" in ind_lower or "game" in ind_lower:
        return "entertainment"
    elif "retail" in ind_lower or "store" in ind_lower or "shop" in ind_lower:
        return "retail"
    elif "packaged foods" in ind_lower or "beverage" in ind_lower or "food" in ind_lower:
        return "food"
    elif "marine shipping" in ind_lower or "shipping" in ind_lower or "vessel" in ind_lower or "ocean freight" in ind_lower:
        return "marine_shipping"
    elif "airline" in ind_lower or "rail" in ind_lower or "freight" in ind_lower or "transportation" in ind_lower or "logistics" in ind_lower:
        return "transportation"
    elif "utilities" in sec_lower or "power" in ind_lower or "gas" in ind_lower:
        return "utilities"
    elif "wholesale" in ind_lower:
        if "conglomerate" in sec_lower or "trading" in sec_lower:
            return "trading_conglomerates"
        elif "electronic" in sec_lower or "computer" in sec_lower:
            return "electronics"
        return "retail"
    
    if "technology" in sec_lower:
        return "software"
    elif "financial" in sec_lower:
        return "banks"
    elif "energy" in sec_lower:
        return "utilities"
    elif "materials" in sec_lower:
        return "chemicals"
    elif "industrials" in sec_lower:
        return "machinery"
    
    return "other"

# Dictionary of industry catalysts
INDUSTRY_CATALYSTS = {
    "automotive": [
        "**新型EV・ハイブリッド車(HEV)のグローバル販売増**: 北米やアジア等の主要市場における新型車両のシェア伸長や電動化ロードマップの進捗IR。",
        "**為替の円安推移に伴う輸出利益の上振れ**: 輸出比率が高いため、想定為替レートより円安で推移した四半期決算時の大幅な経常利益上振れシナリオ。",
        "**車載半導体や重要部材サプライチェーンの正常化**: 部品調達不足の解消に伴う生産稼働率の向上と、操業度改善による営業マージンの回復。"
    ],
    "semiconductors": [
        "**生成AI向けGPU・HBM（高帯域幅メモリ）向け受注の拡大**: AIサーバーやデータセンター需要に伴う、最先端の微細化・パッケージング関連装置の大口受注獲得IR。",
        "**大手ファウンドリ（TSMC・Samsung等）の設備投資計画(CapEx)の引き上げ**: 主要顧客の巨額投資ニュースは、直接的な中長期受注残の拡大期待として株価の強い押し上げ要因になります。",
        "**シリコンサイクルの底打ちと在庫調整完了**: 半導体製造業界全体の需給バランス回復に伴う、装置および周辺部材の新規受注サイクルの再加速。"
    ],
    "trading_conglomerates": [
        "**原油・LNG・鉄鉱石・銅などの国際商品市況の上昇**: 資源価格の高騰は、資源権益比率の高い総合商社の持分法投資損益を直接押し上げる最大の好材料です。",
        "**非資源分野（DX・リテール・ヘルスケア・再エネ）の事業拡大**: 投資ポートフォリオの多角化による収益の安定化と、新規事業立ち上げによる企業価値向上への期待。",
        "**東証の要請を受けた株主還元の強化（増配・積極的な自社株買い）**: 豊富なキャッシュフローを背景とした、累進配当の導入や機動的な株主還元姿勢の発表。"
    ],
    "electronics": [
        "**スマートフォン（新型iPhone等）や車載電子部品向けの需要回復**: 積層セラミックコンデンサ（MLCC）や基板用材料の出荷数量の反転回復。",
        "**ファクトリーオートメーション（FA）向け高精度センサやアクチュエータの受注底打ち**: グローバルな製造業設備投資の回復サイクルへの突入実績の開示。",
        "**最先端電子デバイスの新規顧客開拓**: 米国や欧州の主要メーカーへの新規格部品の採用決定に関するリリース。"
    ],
    "telecom": [
        "**5G/6Gインフラ構築と法人向けDX・セキュリティソリューションの売上成長**: 単なる回線提供にとどまらない、クラウド連携やサイバーセキュリティ等の高付加価値ソリューションの契約獲得。",
        "**データセンター・生成AIインフラ事業の本格収益化**: 生成AIの爆発的普及に伴うデータ通信量増加に対応したデータセンターの増設と、稼働率の上昇による増収寄与。",
        "**インフレに連動した通信プランの価格改定およびARPU（ユーザー平均単価）の向上**: 顧客離脱を防ぎつつ単価を改善する料金プラン戦略の成功。"
    ],
    "internet": [
        "**EC流通取引総額（GMV）の拡大および加盟店手数料・広告枠売上の成長**: プラットフォームの活性化と広告出稿企業の増加による売上高の伸長。",
        "**生成AI等の新テクノロジーを活用した体験向上とLTV（顧客生涯価値）改善**: ユーザーにパーソナライズされた提案機能や業務効率化ツールのリリースによる解約率の低下。",
        "**フィンテック（決済・金融）分野や独自ポイント経済圏とのクロスセル進展**: サービス内での金融取引アクティブ化に伴う高利益率の周辺事業の収益寄与。"
    ],
    "software": [
        "**ARR（年間経常収益）の伸長と解約率（Churn Rate）の低水準維持**: サブスクリプションSaaSビジネスにおける安定した収益基盤の成長実績と顧客定着率の高さの証明。",
        "**大手企業（エンタープライズ領域）での大口パッケージ導入IR**: システムインテグレーションや基幹システムクラウド移行（DX）におけるメガ顧客の獲得発表。",
        "**自社ソフトへのAI機能搭載に伴うアップセル・基本料金の値上げ**: プロダクト価値の向上に合わせた上位プランへの移行促進や価格転嫁による、売上総利益率の向上。"
    ],
    "biotech": [
        "**開発中パイプライン（新薬候補）の治験（第II相/第III相）での良好な結果公表**: 主要評価項目のクリアや良好な臨床データの発表は、バイオテクノロジー企業の企業価値を飛躍的に高めます。",
        "**規制当局（厚労省PMDA、米国FDAなど）からの製造販売承認の獲得**: 開発フェーズから販売・収益化フェーズへと切り替わる、最も事業リスクが低下するマイルストーン達成。",
        "**グローバルメガファーマとのライセンスアウト（導出）および共同開発契約の締結**: 一時金の獲得や開発進捗に伴うマイルストーン収入、および将来の販売ロイヤリティの確保。"
    ],
    "medical_devices": [
        "**低侵襲手術用デバイスや最先端内視鏡装置のグローバルシェア拡大**: 北米、中国、新興国での販売実績の伸長や、病院での新規導入契約の獲得実績。",
        "**海外での薬事承認取得および販売パートナーシップ締結**: 巨大市場での販売活動が可能になるマイルストーンの達成と、現地ディストリビューターの販売網活用による立ち上がり加速。",
        "**配送される消耗品の販売比率上昇に伴う収益安定化（ストックビジネス化）**: 機器本体の累積稼働台数増加に伴う、定期的な消耗品・メンテナンス売上の積み上がりによる粗利益率の改善。"
    ],
    "chemicals": [
        "**EV電池用セパレータや半導体レジストなど高機能・高付加価値素材の採用獲得**: 次世代成長産業向け部材の特定顧客での独占採用やサプライヤー指定IR。",
        "**ナフサなど原油由来原料コストの下落に伴うスプレッド（利ざや）の拡大**: 原材料価格下落に対して製品価格を維持、あるいは迅速な価格改定を行うことによるマージン改善。",
        "**環境配慮型素材（バイオプラスチック・再生材料）の商用化とグリーン調達の受注**: 大手メーカーの環境基準に対応した製品供給の本格化によるシェア獲得。"
    ],
    "metals": [
        "**銅・ニッケル等の非鉄金属や鉄鋼・石炭の国際市況（LME価格等）の上昇**: グローバルな需要逼迫に伴う販売単価の引き上げと、保有権益からの持分法利益の大幅な増加。",
        "**EV向け高性能電磁鋼板など高付加価値金属材料の販売比率拡大**: 競合他社が追随しにくい独自の高合金材料や環境負荷低減素材の受注増による単価・マージンの向上。",
        "**自動車・産業機械など主要製造業顧客の在庫調整完了に伴う出荷量回復**: 製造業の景気循環回復に連動した、稼働率上昇による利益の急復元。"
    ],
    "machinery": [
        "**工作機械・産業用ロボットの月次受注動向の底打ち・反転上昇**: 設備投資の先行指標である受注高が反転することによる、中長期的な業績成長期待の復活。",
        "**海外（北米、インド、東南アジア）のインフラ・建設需要を取り込んだ建機販売の拡大**: 各国の公共投資や宅地開発に伴う、中大型機・油圧ショベル等の好調な出荷実績。",
        "**IoT・予兆保全サービス（ストック事業）の拡大と営業利益率の向上**: 稼働データを活用したメンテナンスや消耗品供給の直接提供比率向上による、安定高収益モデルの構築。"
    ],
    "construction": [
        "**都心再開発や半導体工場建設などに伴う大型受注・施工の進捗**: 豊富な手持ち工事残高の確実な竣工と、採算重視の選別受注による利益率の確保。",
        "**資材価格・労務費の上昇に対する請負価格の適正なスライド改定**: コスト上昇分を発注者に適正に転嫁する交渉の進展による、利益率のボトムアウト確認。",
        "**脱炭素・新エネルギー関連（洋上風力や水素インフラ）の土木施工案件の獲得**: 新たな大型インフラ投資分野におけるフロントランナーとしての受注実績IR。"
    ],
    "realestate": [
        "**都心オフィスビルの空室率低下と平均賃料の上昇トレンド維持**: 新築ビルの満室稼働や、既存ビルの契約更改におけるインフレを反映した賃料引き上げの成功。",
        "**物流施設や高級マンション開発物件の販売好調による早期売却益の計上**: 機動的なアセットローテーション（私募リート等への売却）によるまとまった特別利益の計上。",
        "**保有不動産の含み益拡大を背景とした資産価値評価の引き上げ**: 低PBR解消に向けた、保有資産の売却や還元枠の拡大を伴う経営戦略の発表。"
    ],
    "banks": [
        "**日本銀行の利上げ局面に伴う貸出金利ざや（純金利マージン）の拡大**: 金利上昇による預貸スプレッドの改善は、銀行のコア収益（資金利益）を飛躍的に増加させます。",
        "**国債等の保有資産の利回り改善とポートフォリオ再構築**: 高金利環境における再投資利回りの向上に伴う、中長期的な資金運用収益の上振れ。",
        "**資本効率重視の還元姿勢（配当性向の引き上げ、積極的な自社株買い）**: 豊富な自己資本を原資とした、東証のPBR改善要請への積極的なコミットメント開示。"
    ],
    "brokerage": [
        "**株式市場の活況・取引高急増に伴う委託手数料の拡大**: 個人投資家の取引活発化によるブローカレッジ収入の急増、および信用取引残高の増加に伴う金利収入の拡大。",
        "**新NISA等の普及による投資信託・預かり資産残高（AUM）の継続的増加**: 顧客層の拡大に伴う、ストック収益である信託報酬・口座管理手数料の安定的な積み上がり。",
        "**M&A仲介・IPO支援等のコーポレートファイナンス業務の好調**: 企業の再編意欲の高まりを背景とした、アドバイザリー手数料および引受手数料の増加。"
    ],
    "insurance": [
        "**金利上昇による運用環境の改善（利回り向上メリット）**: 生保・損保における超長期債等での新規運用利回り向上による、将来的な利差益の拡大・安定化。",
        "**保険料率（自動車保険・火災保険等）の改定による収益力の復元**: 事故率や災害発生率のデータに基づいた適正な保険料引き上げによる、コンバインド・レシオ（費用率）の低下改善。",
        "**政策保有株式の縮減前倒しに伴う売却益と株主還元枠の設定**: 保有株売却で得たキャッシュを原資とする増配・大規模自社株買いの発表による需給改善。"
    ],
    "entertainment": [
        "**新規ゲームタイトルや大型IP商品のグローバル市場での大ヒット**: 発売初期のセールス本数ミリオン突破や、アプリストアのセールスランキング上位維持による業績急拡大サプライズ。",
        "**人気IP（知的財産）の多角化・メディアミックス展開（アニメ・映画・グッズ）の成功**: ライセンス収入（ロイヤリティ）の増加と、ゲーム等本業へのファン流入相乗効果のIR。",
        "**主力タイトルの大型アップデートや有名コラボイベントによる月次売上の急増**: アプリ運営におけるMAU（月間アクティブ）の再活性化と、課金率の反転回復実績。"
    ],
    "retail": [
        "**月次既存店売上高の好調持続（客数・客単価の前年比上振れ）**: 独自ブランド（PB）製品のヒットや店舗改装効果による、毎月開示される業績数値の好進捗実績。",
        "**訪日外国人（インバウンド）による免税売上の急拡大**: インバウンド客の増加や為替の円安基調を受けた、免税売上比率の拡大とそれに伴う利益率の向上。",
        "**海外店舗（アジア・北米等）の新規出店と黒字化ペースの加速**: 国内の人口減少を見据えたグローバル展開の成功と、海外現地でのブランド認知度の高まり。"
    ],
    "food": [
        "**国内での適正な価格改定（値上げ）の浸透とマージン回復**: 原材料費・エネルギーコストの上昇に対する値上げが定着し、販売数量が底堅く推移することによる粗利率の急上昇。",
        "**海外事業（北米やアジア等）におけるローカライズ展開の好調**: 海外市場での販売網開拓や現地工場の稼働本格化による、高成長率・高利益率路線の獲得。",
        "**小麦・大豆・コーヒー豆等の主要輸入原材料価格の落ち着き**: コモディティ相場の下落や為替の安定化に伴う、四半期決算での原価率引き下げ効果。"
    ],
    "marine_shipping": [
        "**バルチック海運指数 (BDI) やコンテナ運賃などの海運市況の反発**: グローバルな船腹需給タイト化による運賃高騰は、海運株の売上・利益を最も強烈に押し上げるカタリストです。",
        "**地政学的リスク（運河の通航制限等）に伴う運賃市況の高騰**: 迂回ルートの発生による船腹の供給不足と、それに伴うスポット運賃（SCFI等）の急上昇シナリオ。",
        "**新造船の竣工スケジュールとスクラップ動向**: 業界全体の供給能力調整や、老朽船の環境規制対応に伴う廃船進捗による船腹需給のタイト化。"
    ],
    "transportation": [
        "**「物流2024年問題」に対応した運賃改定（基本運賃値上げ）の成否**: 陸運・宅配における積載効率の向上や適正運賃交渉の妥結による、営業利益率の復元。",
        "**インバウンド旅客および国内外 of ビジネス人流の本格回復に伴う鉄道・航空搭乗率の上昇**: 新幹線や国際線の需要増加による、高マージンな長距離旅客セグメントの収益寄与。",
        "**燃油サーチャージや為替変動（円高方向への修正）に伴う燃料コスト負担の軽減**: 航空・陸運における原燃料費の負担軽減によるマージン率の改善。"
    ],
    "utilities": [
        "**燃料調整制度のタイムラグ解消やエネルギー原料市況（LNG・石炭）の下落**: 発電コストの低下に対して電気料金の改定効果が発現することによる、経常損益の大幅な黒字転換・拡大。",
        "**原子力発電所の安全対策工事完了と再稼働プロセスの進捗**: 火力発電用の燃料調達コスト（LNG等）の莫大な削減効果をもたらす、最もインパクトの大きい収益改善カタリスト。",
        "**再生可能エネルギー（洋上風力・地熱等）の新規発電所運転開始**: クリーンエネルギー調達を重視する法人向け契約の増加と、長期安定的な売電キャッシュフローの創出。"
    ],
    "other": [
        "**四半期決算における進捗率の高さと営業利益の上振れサプライズ**: 市場コンセンサスを上回る決算数値の公表による、短期的な買い需要の呼び込み。",
        "**新規顧客向けのパイロット導入・業務提携IR**: 新たな成長の足がかりとなる業務資本提携や、新規市場への進出ロードマップの発表。"
    ]
}

# Generate IR and Catalyst scenario analysis
def generate_ir_catalysts(ticker, tags, info):
    # Retrieve raw fields safely
    summary = info.get('longBusinessSummary') or ""
    sector = info.get('sector') or "未分類"
    industry = info.get('industry') or "未分類"
    
    # Translate industry & sector to Japanese dynamically
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
    }.get(sector, None)
    
    if sector_ja is None and sector != "未分類":
        sector_ja = translate_text(sector)
    elif sector_ja is None:
        sector_ja = "未分類"
        
    industry_ja = "未分類"
    if industry != "未分類":
        industry_ja = translate_text(industry)
        
    # Translate description summary
    translated_summary = ""
    if summary:
        translated_summary = translate_text(summary)
    else:
        translated_summary = "事業サマリー情報はありませんでした。"
        
    # Classify the industry
    summary_lower = summary.lower()
    classified = classify_industry(industry, sector, summary_lower)
    
    # Initialize catalysts list
    catalysts = []
    
    # 1. Add Industry-specific Catalysts
    ind_cats = INDUSTRY_CATALYSTS.get(classified, INDUSTRY_CATALYSTS["other"])
    catalysts.extend(ind_cats)
    
    # 2. Keyword-Specific Catalyst Injector
    # EV / Battery
    if any(k in summary_lower for k in ["ev ", "battery", "batteries", "electric vehicle", "electrification", "hybrid"]):
        catalysts.append("**EV（電気自動車）および次世代バッテリー向け製品・部材の需要拡大**: 主要メーカーによる新型EVの投入や、自社部材（電極材料、バッテリーパック、車載センサー等）の採用実績・販売動向が株価を大きく動かす可能性があります。")
    
    # Hydrogen / Ammonia / Decarbon
    if any(k in summary_lower for k in ["hydrogen", "ammonia", "decarbon", "renewable", "wind power", "solar power"]):
        catalysts.append("**水素・アンモニアおよびクリーンエネルギー（脱炭素）関連プロジェクトの進展**: 政府の温室効果ガス削減目標や補助金支援を受けて開発中の、次世代クリーン燃料供給チェーン構築や大規模実証事業のニュース。")
        
    # AI / Machine Learning
    if any(k in summary_lower for k in ["ai ", "artificial intelligence", "machine learning", "deep learning", "generative ai"]):
        catalysts.append("**生成AI（人工知能）ソリューションや機械学習プラットフォームの機能拡張・受注**: 顧客企業の業務効率化やDX（デジタルトランスフォーメーション）加速に向けた新規AI機能の実装や、特化型AIモデルの共同開発IR。")
        
    # Defense / Space
    if "宇宙" in tags or "防衛" in tags or any(k in summary_lower for k in ["defense", "military", "aerospace", "jaxa"]):
        catalysts.append("**防衛装備品や宇宙産業（JAXA等官公庁）関連の大型プロジェクト受注**: 国防予算増額や宇宙開発推進基金を背景とした、国家主導の新型レーダー、飛翔体、宇宙デブリ回収等の大型受注・補助金採択。")
        
    # Inbound / Tourist
    if any(k in summary_lower for k in ["inbound", "tourist", "tourism", "hotel", "lodging"]):
        catalysts.append("**訪日外国人観光客（インバウンド）による免税売上および客単価の上振れ**: 旅行需要の活況や為替の円安傾向を受けた、インバウンド顧客向けの高付加価値サービス販売や免税売上比率の向上。")
        
    # M&A
    if any(k in summary_lower for k in ["acquisition", "merger", "m&a", "takeover"]):
        catalysts.append("**M&A（合併・買収）や資本業務提携によるシナジー発揮と事業拡大**: 成長余地の大きい海外企業や、競合・周辺領域企業の買収に伴う連結売上高の急増および新市場への参入スピード加速。")
        
    # Global expansion
    if any(k in summary_lower for k in ["global", "overseas", "north america", "europe", "china", "asia"]):
        catalysts.append("**海外事業（グローバル市場）における販売比率の増加と為替影響**: 北米、アジア、欧州など巨大市場でのローカライズ展開や、想定為替レート（円安）に対する上振れ利益メリット。")

    # 3. Financial/Structure Catalysts
    def local_safe_float(val):
        if val is None:
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    pbr = local_safe_float(info.get('priceToBook'))
    if pbr is not None and pbr < 1.0:
        catalysts.append(f"**PBR改善要求（現状PBR: {pbr:.2f}倍）に対する資本効率改善策の発表**: PBRが1倍を下回っているため、東証からの改善要請に基づき、配当増額や大規模な自社株買い、政策保有株の縮減といった還元強化策が出やすい株価位置にあります。")
        
    div_yield = local_safe_float(info.get('dividendYield'))
    if div_yield is not None and div_yield >= 0.035:
        catalysts.append(f"**高配当利回り（現状予想配当利回り: {div_yield*100:.2f}%）による株価下値の堅さとインカム買い**: 安定した配当利回りが投資家の買いを呼び込みやすく、市場全体の下落局面でも下値のサポートとして機能します。")
        
    market_cap = local_safe_float(info.get('marketCap'))
    if market_cap is not None and market_cap < 150 * 10**8: # Under 150億円
        catalysts.append(f"**中小型株特有のアナリスト新規カバレッジ開始や買収プレミアム期待 (時価総額: {market_cap/10**8:.1f}億円)**: 流動性が低いため、証券会社のアナリストによるカバー開始や、大手企業による資本提携・TOB等のニュースで株価が急上昇しやすい材料性があります。")

    # Compile the final layout
    text = f"### 💡 ビジネスモデルとカタリスト（株価上昇材料）分析\n\n"
    text += f"**セクター**: `{sector_ja}` | **業界**: `{industry_ja}`\n\n"
    
    text += f"#### 🏢 企業の主要事業活動（詳細サマリー）\n"
    text += f"{translated_summary}\n\n"
    
    text += f"#### 🚀 期待される今後の株価上昇材料 (カタリスト)\n"
    
    # Deduplicate and limit to top 4
    seen = set()
    unique_catalysts = []
    for c in catalysts:
        title = c.split(":")[0] if ":" in c else c
        if title not in seen:
            seen.add(title)
            unique_catalysts.append(c)
            
    if not unique_catalysts:
        unique_catalysts.extend([
            "**四半期決算時の利益進捗（コンセンサス上振れ）**: 定期決算における、市場予想を上回る営業利益・純利益のポジティブサプライズ発表。",
            "**新規プロダクトのローンチ・主要アップデート**: 既存顧客へのアップセルや、新規市場への進出ロードマップの公表による売上期待。"
        ])
        
    for c in unique_catalysts[:4]:
        text += f"- {c}\n\n"
        
    text += f"#### ⚠️ 直近の注目点・リスク要因\n"
    text += "- **決算発表時のガイダンス（今期見通し）の強さ**: 株価の上昇トレンド維持には、実績値だけでなく次回ガイダンスの数値が市場コンセンサスをクリアすることが重要です。\n"
    text += "- **為替・金利動向およびマクロ経済環境**: 各種為替動向や金利上昇シナリオが企業の支払利息や輸出採算に与える影響に留意してください。\n"
    
    return text

@st.cache_data(ttl=300)
def fetch_chart_data(ticker, interval="1d", period="1y"):
    try:
        tk = yf.Ticker(ticker)
        df = tk.history(period=period, interval=interval)
        if df.empty:
            return pd.DataFrame()
        df = patch_history_with_fast_info(ticker, df)
        return df
    except Exception as e:
        st.error(f"データ取得中にエラーが発生しました: {e}")
        return pd.DataFrame()

def calculate_indicators_for_df(df, interval="1d"):
    if df.empty:
        return df
    close = df['Close']
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
    return df

# Create Plotly interactive chart
def create_chart(df, ticker, name, interval="1d"):
    is_mobile = False
    is_dark = False
    try:
        import streamlit as st
        is_mobile = st.session_state.get('ui_mode', 'PC') == 'スマホ'
        is_dark = st.session_state.get('color_theme', 'light') == 'dark'
    except:
        pass

    subplot_titles = ("株価/MA/BB", "RSI", "MACD") if is_mobile else ("株価 / 移動平均線 / ボリンジャーバンド (-2σから+2σ)", "RSI (相対力指数 - 30/70基準線)", "MACD / シグナル線")

    fig = make_subplots(
        rows=3, cols=1, 
        shared_xaxes=True, 
        vertical_spacing=0.08, # Spacing increased to prevent subplot titles overlapping
        row_width=[0.2, 0.2, 0.6],
        subplot_titles=subplot_titles
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
    
    # Row 1: Moving Averages legend adjustments based on interval
    if interval == "5m":
        ma5_name, ma25_name, ma75_name = 'SMA5 (25分)', 'SMA25 (125分)', 'SMA75 (375分)'
    elif interval == "1wk":
        ma5_name, ma25_name, ma75_name = '5週線', '25週線', '75週線'
    elif interval == "1mo":
        ma5_name, ma25_name, ma75_name = '5ヶ月線', '25ヶ月線', '75ヶ月線'
    else:
        ma5_name, ma25_name, ma75_name = '5日線', '25日線', '75日線'
        
    # Row 1: Moving Averages (high visibility on white background)
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA5'], name=ma5_name, line=dict(color='#d97706', width=1.2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA25'], name=ma25_name, line=dict(color='#2563eb', width=1.5)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA75'], name=ma75_name, line=dict(color='#7c3aed', width=1.5)), row=1, col=1)
    
    # Row 1: Bollinger Bands
    fig.add_trace(go.Scatter(x=df.index, y=df['BB_Upper'], name='BB上限 (+2σ)', line=dict(color='rgba(100,116,139,0.3)', width=1, dash='dash'), showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=df['BB_Lower'], name='BB下限 (-2σ)', 
        line=dict(color='rgba(100,116,139,0.3)', width=1, dash='dash'),
        fill='tonexty', fillcolor='rgba(37, 99, 235, 0.03)',
        showlegend=False
    ), row=1, col=1)
    
    # Row 2: RSI
    fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], name='RSI (14)', line=dict(color='#ea580c', width=1.5), showlegend=False), row=2, col=1)
    fig.add_shape(type="line", x0=df.index[0], y0=30, x1=df.index[-1], y1=30, line=dict(color="#dc2626", width=1, dash="dash"), row=2, col=1)
    fig.add_shape(type="line", x0=df.index[0], y0=70, x1=df.index[-1], y1=70, line=dict(color="#16a34a", width=1, dash="dash"), row=2, col=1)
    fig.update_yaxes(range=[10, 90], row=2, col=1)
    
    # Row 3: MACD
    fig.add_trace(go.Scatter(x=df.index, y=df['MACD'], name='MACD', line=dict(color='#2563eb', width=1.5), showlegend=False), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MACD_Signal'], name='シグナル', line=dict(color='#ea580c', width=1.5), showlegend=False), row=3, col=1)
    
    # MACD Hist bars
    hist_colors = ['#16a34a' if val >= 0 else '#dc2626' for val in df['MACD_Hist']]
    fig.add_trace(go.Bar(x=df.index, y=df['MACD_Hist'], name='ヒストグラム', marker_color=hist_colors, opacity=0.5, showlegend=False), row=3, col=1)
    
    # Detect UI mode for responsive layout sizing
    is_mobile = False
    try:
        import streamlit as st
        is_mobile = st.session_state.get('ui_mode', 'PC') == 'スマホ'
    except:
        pass

    chart_height = 600 if is_mobile else 750
    legend_cfg = dict(
        orientation="h",
        yanchor="top",
        y=-0.12,
        xanchor="center",
        x=0.5
    )

    # Formatting layout
    fig.update_layout(
        xaxis_rangeslider_visible=False,
        height=chart_height,
        template="plotly_dark" if is_dark else "plotly_white", # Dynamic template
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=10, r=10, t=40, b=50),
        legend=legend_cfg,
        dragmode=False if is_mobile else "pan"
    )
    
    # Clean grids and adjust tick/font sizes for mobile
    gridcolor = '#1e293b' if is_dark else '#f1f5f9'
    zerolinecolor = '#334155' if is_dark else '#cbd5e1'
    fig.update_yaxes(gridcolor=gridcolor, zerolinecolor=zerolinecolor, tickfont=dict(size=9 if is_mobile else 11))
    fig.update_xaxes(gridcolor=gridcolor, tickfont=dict(size=9 if is_mobile else 11))
    fig.update_annotations(font_size=10 if is_mobile else 12)
    
    # Adjust y-axis range of Row 1 (candlestick chart) to fit the stock price nicely
    # and prevent extreme BB values from compressing the candles.
    valid_df = df.dropna(subset=['Low', 'High'])
    if not valid_df.empty:
        ymin = valid_df['Low'].min()
        ymax = valid_df['High'].max()
        if 'BB_Lower' in df.columns:
            bb_min = df['BB_Lower'].dropna().min()
            if pd.notna(bb_min):
                ymin = min(ymin, bb_min)
        if 'BB_Upper' in df.columns:
            bb_max = df['BB_Upper'].dropna().max()
            if pd.notna(bb_max):
                ymax = max(ymax, bb_max)
                
        price_min = valid_df['Low'].min()
        price_max = valid_df['High'].max()
        if ymin < price_min * 0.9:
            ymin = price_min * 0.9
        if ymax > price_max * 1.1:
            ymax = price_max * 1.1
            
        yrange = ymax - ymin
        if yrange > 0:
            fig.update_yaxes(range=[ymin - yrange * 0.02, ymax + yrange * 0.02], row=1, col=1)
            
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

def generate_similar_pattern_explanation(ticker, name, m, N, future_days=20):
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
            source_badge = f"""<span style="background-color: var(--border-color, #e2e8f0); color: var(--text-color, #475569); opacity: 0.85; font-size: 0.72rem; padding: 2px 6px; border-radius: 4px; margin-left: 6px; font-weight: 500; display: inline-block; vertical-align: middle;">{item['source']}</span>""" if item['source'] else ""
            news_html += f"""
            <li style="margin-bottom: 6px; list-style-type: square; margin-left: 15px;">
                <span style="color: var(--text-color, #64748b); opacity: 0.7; font-size: 0.85rem; font-family: monospace; margin-right: 6px;">[{item['date']}]</span>
                <a href="{item['link']}" target="_blank" style="color: var(--primary-color, #2563eb); text-decoration: none; font-weight: 500; font-size: 0.88rem; border-bottom: 1px dashed var(--primary-color, #93c5fd);">{item['title']}</a>
                {source_badge}
            </li>
            """
    else:
        news_html = """
        <li style="margin-bottom: 6px; list-style-type: none; margin-left: 0px; color: var(--text-color, #64748b); opacity: 0.7; font-size: 0.88rem;">
            ℹ️ 当時のニュース履歴を取得できませんでした（期間外、またはインデックス未登録）。
        </li>
        """

    explanation = f"""
    <div style="background-color: var(--secondary-background-color, #f8fafc); border-radius: 8px; padding: 16px; border-left: 4px solid {'#10b981' if ret >= 0 else '#ef4444'}; margin-bottom: 12px; border-top: 1px solid var(--border-color, #e2e8f0); border-right: 1px solid var(--border-color, #e2e8f0); border-bottom: 1px solid var(--border-color, #e2e8f0);">
        <div style="display: flex; justify-content: space-between; font-weight: bold; margin-bottom: 8px;">
            <span style="font-size: 0.95rem; color: var(--text-color, #1e293b);">🕒 類似期間: {start_dt.strftime('%Y-%m-%d')} 〜 {end_dt.strftime('%Y-%m-%d')} (類似度: {similarity:.1f}%)</span>
            <span style="font-size: 1rem; {ret_style}">その後の{future_days}営業日の動向: {ret:+.2f}% ({direction})</span>
        </div>
        <div style="font-size: 0.9rem; color: var(--text-color, #334155); opacity: 0.9; line-height: 1.6; margin-bottom: 8px;">
            <strong>【当時の主要な時事・市況イベント】：{macro_title}</strong><br/>
            {macro_desc}
        </div>
        <div style="font-size: 0.9rem; color: var(--text-color, #334155); opacity: 0.9; line-height: 1.6; border-top: 1px dashed var(--border-color, #cbd5e1); padding-top: 8px; margin-bottom: 8px;">
            <strong>📰 当時（同日〜同月内）に報道された主要ニュース（リアルタイム取得）</strong>:<br/>
            <ul style="margin: 6px 0 0 0; padding-left: 5px; line-height: 1.5;">
                {news_html}
            </ul>
        </div>
        <div style="font-size: 0.9rem; color: var(--text-color, #1e293b); line-height: 1.6; border-top: 1px dashed var(--border-color, #cbd5e1); padding-top: 8px; background-color: rgba(59, 130, 246, 0.08); padding: 8px; border-radius: 6px; margin-top: 8px;">
            <strong>🏢 当時の {name} に関係した主要出来事・材料（専門分析）</strong>:<br/>
            {corp_event}
        </div>
    </div>
    """
    return "\n".join([line.strip() for line in explanation.split("\n")])

def generate_final_pattern_implication(name, matches_data, avg_ret, future_days=20):
    avg_color = "#16a34a" if avg_ret >= 0 else "#dc2626"
    avg_sign = "+" if avg_ret >= 0 else ""
    direction_text = "上昇する傾向" if avg_ret >= 0 else "下落（または調整）する傾向"
    
    up_count = 0
    for m in matches_data:
        N = len(m['all_prices']) - future_days
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
    <div style="background-color: var(--secondary-background-color, #f8fafc); border-left: 5px solid {avg_color}; border-radius: 8px; padding: 20px; margin-top: 20px; box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05); border-top: 1px solid var(--border-color, #e2e8f0); border-right: 1px solid var(--border-color, #e2e8f0); border-bottom: 1px solid var(--border-color, #e2e8f0);">
        <h5 style="margin: 0 0 10px 0; color: var(--text-color, #1e293b); font-size: 1.05rem;">💡 歴史的パターンから導かれる総合考察</h5>
        <div style="font-size: 0.95rem; color: var(--text-color, #334155); opacity: 0.9; line-height: 1.6; margin-bottom: 12px;">
            過去5年間のデータから抽出された類似パターン上位3例において、形状終了から{future_days}営業日後の平均騰落率は 
            <strong style="color: {avg_color}; font-size: 1.2rem;">{avg_sign}{avg_ret:.2f}%</strong> となり、
            過去の統計上は<strong>{direction_text}</strong>が見られます。（3回中 {up_count} 回で上昇）
        </div>
        <div style="font-size: 0.92rem; color: var(--text-color, #475569); opacity: 0.8; line-height: 1.6; border-top: 1px dashed var(--border-color, #cbd5e1); padding-top: 12px;">
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
    
    is_mobile = st.session_state.get('ui_mode', 'PC') == 'スマホ'
    
    if is_mobile:
        st.markdown(f"#### {selected_name} ({selected_ticker})")
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
                
        m_col1, m_col2 = st.columns(2)
        with m_col1:
            st.markdown(f"""<div class="card">
                 <div class="metric-title">現在株価</div>
                 <div class="metric-value metric-accent">{format_price(metrics['price'], selected_ticker)}</div>
             </div>""", unsafe_allow_html=True)
            st.markdown(f"""<div class="card">
                 <div class="metric-title">PER (倍)</div>
                 <div class="metric-value">{f"{metrics['per']:.1f}" if metrics['per'] is not None else "N/A"}</div>
             </div>""", unsafe_allow_html=True)
            st.markdown(f"""<div class="card">
                 <div class="metric-title">配当利回り</div>
                 <div class="metric-value">{f"{metrics['dividend_yield']:.2f}%" if metrics['dividend_yield'] is not None else "N/A"}</div>
             </div>""", unsafe_allow_html=True)
        with m_col2:
            st.markdown(f"""<div class="card">
                 <div class="metric-title">前日比</div>
                 <div class="metric-value" style="color: {'#16a34a' if metrics['change_pct'] >= 0 else '#dc2626'}">{metrics['change_pct']:.2f}%</div>
             </div>""", unsafe_allow_html=True)
            st.markdown(f"""<div class="card">
                 <div class="metric-title">PBR (倍)</div>
                 <div class="metric-value">{f"{metrics['pbr']:.2f}" if metrics['pbr'] is not None else "N/A"}</div>
             </div>""", unsafe_allow_html=True)
            st.markdown(f"""<div class="card" style="border-left: 4px solid {owned_color};">
                 <div class="metric-title">保有状況</div>
                 <div class="metric-value" style="color: {owned_color};">{owned_text}</div>
                 <div style="font-size: 0.8rem; color: #64748b; margin-top: 2px;">{owned_sub}</div>
             </div>""", unsafe_allow_html=True)
    else:
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
    
    # Hardcoded theme colors for segmented control styling
    local_is_dark = st.session_state.get('color_theme', 'light') == 'dark'
    local_unselected_bg = "#0b0f19" if local_is_dark else "#e2e8f0"
    local_text_color = "#e2e8f0" if local_is_dark else "#1e293b"
    local_border_color = "#1e293b" if local_is_dark else "#cbd5e1"
    local_primary_color = "#3b82f6" if local_is_dark else "#2563eb"
    local_bg_color = "#0b0f19" if local_is_dark else "#f8fafc"

    # CSS styling to stretch st.segmented_control to full width and make buttons equal width
    st.markdown(f"""
    <style>
    div[data-testid="stButtonGroup"] {{
        width: 100% !important;
        background: transparent !important;
    }}
    div[data-testid="stButtonGroup"] > div {{
        display: flex !important;
        width: 100% !important;
        flex-direction: row !important;
        gap: 8px !important;
        background: transparent !important;
    }}
    div[data-testid="stButtonGroup"] button[data-testid^="stBaseButton-segmented_control"],
    div[class*="st-key-det_tab_select"] button,
    div[class*="st-key-chart_interval"] button {{
        flex: 1 1 0% !important;
        text-align: center !important;
        font-size: 0.95rem !important;
        padding: 10px 16px !important;
        white-space: nowrap !important;
        font-weight: 600 !important;
        background: {local_unselected_bg} !important;
        background-color: {local_unselected_bg} !important;
        background-image: none !important;
        color: {local_text_color} !important;
        opacity: 0.65 !important;
        border: 1px solid {local_border_color} !important;
        transition: all 0.2s ease !important;
        box-shadow: none !important;
    }}
    div[data-testid="stButtonGroup"] button[data-testid^="stBaseButton-segmented_control"]:hover,
    div[class*="st-key-det_tab_select"] button:hover,
    div[class*="st-key-chart_interval"] button:hover {{
        border-color: {local_primary_color} !important;
        color: {local_primary_color} !important;
        opacity: 0.9 !important;
        background: {local_bg_color} !important;
        background-color: {local_bg_color} !important;
    }}
    /* Selected segment */
    div[data-testid="stButtonGroup"] button[data-testid="stBaseButton-segmented_controlActive"],
    div[data-testid="stButtonGroup"] button[aria-checked="true"], 
    div[data-testid="stButtonGroup"] button[aria-selected="true"],
    div[data-testid="stButtonGroup"] button[aria-pressed="true"],
    div[class*="st-key-det_tab_select"] button[data-testid="stBaseButton-segmented_controlActive"],
    div[class*="st-key-det_tab_select"] button[aria-checked="true"],
    div[class*="st-key-det_tab_select"] button[aria-selected="true"],
    div[class*="st-key-det_tab_select"] button[aria-pressed="true"],
    div[class*="st-key-chart_interval"] button[data-testid="stBaseButton-segmented_controlActive"],
    div[class*="st-key-chart_interval"] button[aria-checked="true"],
    div[class*="st-key-chart_interval"] button[aria-selected="true"],
    div[class*="st-key-chart_interval"] button[aria-pressed="true"] {{
        background: {local_primary_color} !important;
        background-color: {local_primary_color} !important;
        color: #ffffff !important;
        opacity: 1 !important;
        border-color: {local_primary_color} !important;
    }}
    /* Style child elements (text) of buttons explicitly */
    div[data-testid="stButtonGroup"] button[data-testid^="stBaseButton-segmented_control"] *,
    div[class*="st-key-det_tab_select"] button *,
    div[class*="st-key-chart_interval"] button * {{
        color: {local_text_color} !important;
    }}
    div[data-testid="stButtonGroup"] button[data-testid="stBaseButton-segmented_controlActive"] *,
    div[data-testid="stButtonGroup"] button[aria-checked="true"] *,
    div[data-testid="stButtonGroup"] button[aria-selected="true"] *,
    div[data-testid="stButtonGroup"] button[aria-pressed="true"] *,
    div[class*="st-key-det_tab_select"] button[data-testid="stBaseButton-segmented_controlActive"] *,
    div[class*="st-key-det_tab_select"] button[aria-checked="true"] *,
    div[class*="st-key-det_tab_select"] button[aria-selected="true"] *,
    div[class*="st-key-det_tab_select"] button[aria-pressed="true"] *,
    div[class*="st-key-chart_interval"] button[data-testid="stBaseButton-segmented_controlActive"] *,
    div[class*="st-key-chart_interval"] button[aria-checked="true"] *,
    div[class*="st-key-chart_interval"] button[aria-selected="true"] *,
    div[class*="st-key-chart_interval"] button[aria-pressed="true"] * {{
        color: #ffffff !important;
    }}
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
        # Add interval selector for chart: 5m, 1d, 1wk, 1mo
        st.markdown('<div style="margin-top: 10px; margin-bottom: 6px; font-weight: 600; font-size: 0.9rem; color: var(--text-color, #1e293b);">📊 表示時間足の選択:</div>', unsafe_allow_html=True)
        interval_options = {
            "5分足": ("5m", "5d"),
            "日足 (標準)": ("1d", "1y"),
            "週足": ("1wk", "5y"),
            "月足": ("1mo", "10y")
        }
        selected_interval_label = st.segmented_control(
            "時間足",
            options=list(interval_options.keys()),
            default="日足 (標準)",
            key=f"chart_interval_{selected_ticker}{key_suffix}",
            label_visibility="collapsed"
        )
        if not selected_interval_label:
            selected_interval_label = "日足 (標準)"
            
        interval, period = interval_options[selected_interval_label]
        
        # Load chart data based on interval
        if interval == "1d":
            chart_df = raw_analysis['df'].copy()
        else:
            with st.spinner(f"{selected_interval_label}のデータを取得中..."):
                chart_df = fetch_chart_data(selected_ticker, interval=interval, period=period)
                if not chart_df.empty:
                    chart_df = calculate_indicators_for_df(chart_df, interval=interval)
                    
        if chart_df.empty:
            st.warning(f"{selected_interval_label}のデータを十分に取得できませんでした。")
            chart_df = raw_analysis['df']
            interval = "1d"
            
        fig = create_chart(chart_df, selected_ticker, selected_name, interval=interval)
        with st.container(border=True):
            st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)
        
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
        rev_g = metrics.get('rev_growth')
        eps_g = metrics.get('eps_growth')
        
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
                <li style="border-bottom: 1px solid #f1f5f9; padding: 10px 0;">
                    <strong>売上高成長率 (YoY)</strong>: {f"{rev_g:.1f}%" if rev_g is not None else "N/A"}
                </li>
                <li style="border-bottom: 1px solid #f1f5f9; padding: 10px 0;">
                    <strong>EPS成長率 (YoY)</strong>: {f"{eps_g:.1f}%" if eps_g is not None else "N/A"}
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
                
            future_days_key = f"pattern_future_days_{selected_ticker}{key_suffix}"
            if future_days_key not in st.session_state:
                st.session_state[future_days_key] = 20
                
            future_days = st.slider(
                "予測・比較したいその後の期間（営業日）：",
                min_value=5,
                max_value=120,
                value=st.session_state[future_days_key],
                step=5,
                key=f"pattern_future_days_slider_{selected_ticker}{key_suffix}"
            )
            
            if future_days != st.session_state[future_days_key]:
                st.session_state[future_days_key] = future_days
            
            with chart_container:
                fig_select = create_selection_chart(
                    df_current, 
                    selected_ticker, 
                    selected_name, 
                    st.session_state[range_key][0], 
                    st.session_state[range_key][1]
                )
                fig_select.update_layout(dragmode="select")
                
                with st.container(border=True):
                    st.plotly_chart(
                        fig_select, 
                        on_select="rerun", 
                        key=chart_key,
                        config=PLOTLY_CONFIG
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
                            for i in range(len(df_5y) - N_len - future_days + 1):
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
                                
                                end_idx = min(len(df_5y), i + N_len + future_days)
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
                                'N': N_len,
                                'future_days': future_days
                            }
                            st.session_state[f"scroll_to_pattern_results_{selected_ticker}{key_suffix}"] = True
                
                # Render results if cached in session state
                match_cache_key = f"pattern_matches_{selected_ticker}{key_suffix}"
                if match_cache_key in st.session_state:
                    data_matches = st.session_state[match_cache_key]
                    target_prices = data_matches['target_prices']
                    matches_data = data_matches['matches']
                    N_val = data_matches['N']
                    future_days_val = data_matches.get('future_days', 20)
                    
                    if not matches_data:
                        st.warning("類似するパターンが見つかりませんでした。")
                    else:
                        st.markdown("---")
                        st.markdown('<div id="pattern-results-anchor"></div>', unsafe_allow_html=True)
                        st.markdown("### 📊 検索結果とパターン比較")
                        
                        # Smooth scroll to results on calculation
                        scroll_flag_key = f"scroll_to_pattern_results_{selected_ticker}{key_suffix}"
                        if st.session_state.get(scroll_flag_key):
                            js = """
                            <script>
                                setTimeout(function() {
                                    var element = window.parent.document.getElementById('pattern-results-anchor');
                                    if (element) {
                                        element.scrollIntoView({behavior: 'smooth', block: 'start'});
                                    }
                                }, 300);
                            </script>
                            """
                            components.html(js, height=0)
                            st.session_state[scroll_flag_key] = False
                            
                        fig_pattern = create_pattern_overlay_chart(target_prices, matches_data, N_val, selected_ticker)
                        with st.container(border=True):
                            st.plotly_chart(fig_pattern, use_container_width=True, config=PLOTLY_CONFIG)
                        
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
                                f"{future_days_val}営業日後の株価 (円)": f"¥{int(scaled_price_after):,}",
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
                            expl_html = generate_similar_pattern_explanation(selected_ticker, selected_name, m, N_val, future_days_val)
                            st.markdown(expl_html, unsafe_allow_html=True)
                            
                        avg_ret = df_table['raw_ret'].mean()
                        implication_html = generate_final_pattern_implication(selected_name, matches_data, avg_ret, future_days_val)
                        st.markdown(implication_html, unsafe_allow_html=True)
        
    # Virtual simulated trading panel inside function
    st.markdown("#### 💼 仮想シミュレーション（デモトレード）に追加 / 売却")
    if is_mobile:
        sim_container1 = st.container()
        sim_container2 = st.container()
    else:
        sim_col1, sim_col2 = st.columns([3, 1])
        sim_container1 = sim_col1
        sim_container2 = sim_col2
        
    with sim_container1:
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
            
    with sim_container2:
        if not is_mobile:
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
    
    # Base directory where app.py is located
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    if not safe_key or safe_key == "default":
        local_filename = "virtual_portfolio.json"
    else:
        local_filename = f"virtual_portfolio_{safe_key}.json"
        
    target_path = os.path.join(base_dir, local_filename)
    
    # Fallback / migration: if target_path does NOT exist, but the file exists in the parent directory of base_dir,
    # let's migrate (copy) it so the user doesn't lose their data!
    if not os.path.exists(target_path):
        parent_dir = os.path.dirname(base_dir)
        parent_path = os.path.join(parent_dir, local_filename)
        if os.path.exists(parent_path):
            try:
                import shutil
                shutil.copy2(parent_path, target_path)
                st.toast(f"ℹ️ 前回の保存データ ({local_filename}) を移行しました。")
            except Exception:
                pass
                
    return target_path

def load_portfolio():
    filename = get_portfolio_filename()
    if not os.path.exists(filename):
        return {
            "purchase_records": [],
            "sales_records": [],
            "total_realized_pl_jpy": 0.0,
            "last_valid_prices": {},
            "watchlist": {},
            "last_updated": "1970-01-01T00:00:00"
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
            if "last_updated" not in data:
                data["last_updated"] = "1970-01-01T00:00:00"
            return data
    except Exception as e:
        st.error(f"ポートフォリオデータの読み込みエラー ({filename}): {e}")
        return {
            "purchase_records": [],
            "sales_records": [],
            "total_realized_pl_jpy": 0.0,
            "last_valid_prices": {},
            "watchlist": {},
            "last_updated": "1970-01-01T00:00:00"
        }

def load_watchlist():
    portfolio = load_portfolio()
    return portfolio.get("watchlist", {})

def save_watchlist(watchlist):
    portfolio = load_portfolio()
    portfolio["watchlist"] = watchlist
    save_portfolio(portfolio)

def save_portfolio(data):
    data["last_updated"] = datetime.datetime.now().isoformat()
    filename = get_portfolio_filename()
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        st.session_state['ls_needs_sync'] = True
        st.session_state['ls_sync_counter'] = st.session_state.get('ls_sync_counter', 0) + 1
        
        user_key = st.session_state.get('user_key', 'default')
        val_str = json.dumps(data, indent=4, ensure_ascii=False)
        
        # 1. Sync to Firebase Firestore if configured (extremely fast!)
        firebase_project_id = st.session_state.get('firebase_project_id', DEFAULT_FIREBASE_PROJECT_ID)
        if firebase_project_id:
            save_portfolio_to_firebase(user_key, firebase_project_id, val_str)
        
        # 2. Sync to Google Sheets if configured (simulating the write latency/lag)
        gas_url = st.session_state.get('gas_url', '')
        if gas_url:
            save_portfolio_to_gsheet(user_key, gas_url, val_str)
            
        return True
    except Exception as e:
        st.error(f"ポートフォリオデータの保存エラー ({filename}): {e}")
        return False

def save_portfolio_cache_only(data):
    data["last_updated"] = datetime.datetime.now().isoformat()
    filename = get_portfolio_filename()
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return True
    except Exception:
        return False

# CSS styling color coding for tables
def color_pl_cell(val):
    if isinstance(val, str):
        if '+' in val:
            return 'color: #16a34a; font-weight: bold;'
        elif '-' in val:
            return 'color: #dc2626; font-weight: bold;'
    return ''

# UI Mode selector (Already configured at top, commented out here to preserve structure)
# is_mobile = st.session_state.get('ui_mode', 'PC') == 'スマホ'

# Sidebar setup for personalizing portfolios
query_user = st.query_params.get("user", "default")

if query_user == "default":
    # ---------------------------------------------------------
    # WELCOME PORTAL PAGE (Shown when no user ID is set)
    # ---------------------------------------------------------
    portal_bg = "#0b0f19" if is_dark else "#f8fafc"
    st.markdown(("""
    <div class="portal-bg-container">
        <div class="portal-blob portal-blob-1"></div>
        <div class="portal-blob portal-blob-2"></div>
        <div class="portal-blob portal-blob-3"></div>
    </div>
    <style>
    html, body {
        background-color: {portal_bg} !important;
    }
    .stApp, 
    [data-testid="stApp"], 
    [data-testid="stAppViewContainer"], 
    [data-testid="stMainViewContainer"], 
    [data-testid="stHeader"], 
    .main {
        background-color: transparent !important;
    }
    .portal-bg-container {
        position: fixed;
        top: 0;
        left: 0;
        width: 100vw;
        height: 100vh;
        overflow: hidden;
        z-index: -1;
        pointer-events: none;
    }
    .portal-blob {
        position: absolute;
        border-radius: 50%;
        filter: blur(120px);
        opacity: 0.65;
        animation: float-blob 22s infinite alternate ease-in-out;
    }
    .portal-blob-1 {
        width: 500px;
        height: 500px;
        background: #34d399;
        top: -100px;
        left: -100px;
        animation-delay: 0s;
        animation-duration: 20s;
    }
    .portal-blob-2 {
        width: 550px;
        height: 550px;
        background: #2dd4bf;
        bottom: -150px;
        right: -100px;
        animation-delay: -5s;
        animation-duration: 25s;
    }
    .portal-blob-3 {
        width: 380px;
        height: 380px;
        background: #60a5fa;
        top: 30%;
        left: 35%;
        animation-delay: -10s;
        animation-duration: 22s;
    }
    @keyframes float-blob {
        0% {
            transform: translate(0px, 0px) scale(1);
        }
        33% {
            transform: translate(50px, -70px) scale(1.15);
        }
        66% {
            transform: translate(-40px, 40px) scale(0.9);
        }
        100% {
            transform: translate(0px, 0px) scale(1);
        }
    }
    [data-testid="stForm"] {
        background: rgba(255, 255, 255, 0.75) !important;
        padding: 35px !important;
        border-radius: 20px !important;
        box-shadow: 0 20px 45px rgba(30, 41, 59, 0.06) !important;
        border: 1px solid rgba(255, 255, 255, 0.6) !important;
        backdrop-filter: blur(15px) !important;
        -webkit-backdrop-filter: blur(15px) !important;
        margin-bottom: 25px !important;
        position: relative !important;
        z-index: 1 !important;
    }
    .login-title-glow {
        font-size: 2.5rem !important;
        font-weight: 900 !important;
        background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 50%, #3b82f6 100%) !important;
        -webkit-background-clip: text !important;
        -webkit-text-fill-color: transparent !important;
        text-align: center !important;
        margin-top: 30px !important;
        margin-bottom: 5px !important;
        letter-spacing: -0.8px !important;
        display: block !important;
    }
    .login-subtitle-glow {
        font-size: 1.05rem !important;
        color: #64748b !important;
        text-align: center !important;
        margin-bottom: 35px !important;
        font-weight: 500 !important;
        display: block !important;
    }
    .login-header-section {
        border-bottom: 1.5px solid #f1f5f9;
        padding-bottom: 18px;
        margin-bottom: 22px;
    }
    .login-section-title {
        font-size: 1.35rem;
        font-weight: 800;
        color: #0f172a;
        text-align: center;
        margin-bottom: 10px;
        letter-spacing: -0.3px;
    }
    .login-intro-text {
        font-size: 0.92rem;
        color: #475569;
        line-height: 1.6;
        text-align: center;
        margin: 0;
    }
    .login-info-box {
        background: #f8fafc;
        border-left: 4px solid #3b82f6;
        padding: 15px;
        border-radius: 8px;
        margin-top: 20px;
        margin-bottom: 10px;
    }
    .login-info-title {
        font-size: 0.85rem;
        font-weight: 700;
        color: #1e3a8a;
        display: block;
        margin-bottom: 4px;
    }
    .login-info-text {
        font-size: 0.8rem;
        color: #475569;
        line-height: 1.5;
        display: block;
    }
    </style>
    """).replace("{portal_bg}", portal_bg), unsafe_allow_html=True)
    
    if is_mobile:
        col_w1, col_w2, col_w3 = st.columns([0.02, 0.96, 0.02])
    else:
        col_w1, col_w2, col_w3 = st.columns([0.6, 2.8, 0.6])
        
    with col_w2:
        st.markdown('<div class="login-title-glow">ZenStockScreener</div>', unsafe_allow_html=True)
        st.markdown('<div class="login-subtitle-glow">AI・ファンダメンタルズ指標分析システム</div>', unsafe_allow_html=True)
        
        with st.form("login_form", clear_on_submit=False):
            st.markdown("""
            <div class="login-header-section">
                <h3 class="login-section-title">👤 マイページへのアクセス</h3>
                <p class="login-intro-text">
                    お気に入り銘柄、シミュレーション取引、ポートフォリオを個別に管理・保存できる専用領域をロードします。
                </p>
            </div>
            <div style="margin-bottom: 8px; font-weight: 600; font-size: 0.9rem; color: #334155;">マイページID（半角英数字）</div>
            """, unsafe_allow_html=True)
            
            entered_id = st.text_input(
                "名前・専用IDを入力してください（半角英数字のみ）",
                value="",
                placeholder="例: takkun, user_abc",
                autocomplete="off",
                key="portal_user_id_input",
                label_visibility="collapsed"
            )
            
            submitted = st.form_submit_button("マイページを開く", type="primary", use_container_width=True)
            
        st.markdown("""
            <div class="login-info-box">
                <span class="login-info-title">ℹ️ IDについて</span>
                <span class="login-info-text">
                    新規のIDを入力すると、自動的にそのID用の専用マイページが生成されます。<br>
                    IDはデータのアクセス・復元キーとなります。ログイン後は<b>このURLをブックマークして保存</b>することをお勧めします。
                </span>
            </div>
        """, unsafe_allow_html=True)
            
        if submitted:
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
st.sidebar.markdown(f"### 👤 ログイン中: **{query_user}**")
st.sidebar.caption("💡 別のIDに切り替える、または初期画面に戻るには下のボタンからログアウトしてください。")

if st.sidebar.button("🚪 ログアウト (ログイン画面に戻る)", use_container_width=True, key="sidebar_logout_btn"):
    st.query_params["user"] = "default"
    st.session_state['user_key'] = "default"
    st.rerun()

user_key = query_user
st.session_state['user_key'] = user_key
st.query_params["user"] = user_key

# --- localStorage Auto-Restore & Sync Setup ---
if 'ls_loaded_keys' not in st.session_state:
    st.session_state['ls_loaded_keys'] = {}

if user_key not in st.session_state['ls_loaded_keys']:
    with st.spinner("📂 ブラウザの保存データを読み込んでいます..."):
        res = local_storage(action="get", item_key=f"zen_portfolio_{user_key}", key=f"ls_get_{user_key}")
        if res is not None:
            # Mark as loaded for this user_key
            st.session_state['ls_loaded_keys'][user_key] = True
            
            val_str = None
            data_source = None
            
            # 1. Try loading from Firebase first if configured (extremely fast!)
            firebase_project_id = st.session_state.get('firebase_project_id', DEFAULT_FIREBASE_PROJECT_ID)
            if firebase_project_id:
                val_str = load_portfolio_from_firebase(user_key, firebase_project_id)
                if val_str:
                    data_source = "Firebase"
                
            # 2. Try loading from Google Sheets next if configured and Firebase was empty
            if not val_str:
                gas_url = st.session_state.get('gas_url', '')
                if gas_url:
                    val_str = load_portfolio_from_gsheet(user_key, gas_url)
                    if val_str:
                        data_source = "Google Sheets"
            
            # 3. Fallback to browser localStorage if not found on cloud
            if not val_str:
                val_str = res.get("value")
                if val_str:
                    data_source = "Browser LocalStorage"
            
            # Load local portfolio file to check if it's empty
            local_portfolio_data = load_portfolio()
            local_is_empty = (
                not local_portfolio_data.get("purchase_records") and 
                not local_portfolio_data.get("sales_records") and 
                not local_portfolio_data.get("watchlist")
            )
            
            if val_str:
                try:
                    browser_portfolio_data = json.loads(val_str)
                    if isinstance(browser_portfolio_data, dict) and ("purchase_records" in browser_portfolio_data or "watchlist" in browser_portfolio_data):
                        # Always prioritize cloud/browser data if it exists.
                        # The local file on the server is just a static template from Git and should never overwrite user's actual database.
                        filename = get_portfolio_filename()
                        with open(filename, "w", encoding="utf-8") as f:
                            json.dump(browser_portfolio_data, f, indent=4, ensure_ascii=False)
                        
                        if data_source == "Firebase":
                            st.toast("🔥 Firebaseから最新データを同期しました。")
                        elif data_source == "Google Sheets":
                            st.toast("☁️ Googleスプレッドシートからデータを復元しました。")
                        else:
                            st.toast("🔄 ブラウザ保存のデータを復元しました。")
                except Exception as e:
                    pass
            else:
                # If local file has data but browser has nothing, queue a sync to browser
                if not local_is_empty:
                    st.session_state['ls_needs_sync'] = True
                    st.session_state['ls_sync_counter'] = st.session_state.get('ls_sync_counter', 0) + 1
        else:
            st.stop()

# Initialize portfolio data in session state
portfolio_data = load_portfolio()

# Sidebar Data Backup & Restore



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
    <div class="title-text">ZenStockScreener</div>
    <div class="subtitle-text">AI分析とファンダメンタルズ指標による日本株上昇期待銘柄の選定システム</div>
</div>
""", unsafe_allow_html=True)

# Persistent purchase success alert
if 'purchase_success_msg' in st.session_state:
    st.success(st.session_state['purchase_success_msg'])
    del st.session_state['purchase_success_msg']

# Initialize screening widget defaults in session state so they exist
widget_defaults = {
    "scr_min_total": 5,
    "scr_min_tech": 1,
    "scr_min_fund": 3,
    "scr_filter_pbr": False,
    "scr_filter_per": False,
    "scr_filter_roe": False,
    "scr_filter_dividend": False,
    "scr_filter_rev_growth": False,
    "scr_filter_eps_growth": False,
    "scr_filter_gc": False,
    "scr_filter_macd": False,
    "scr_filter_rsi_os": False,
    "scr_filter_rsi_ob": False,
    "scr_filter_bb_re": False,
    "scr_filter_vol_su": False,
    "scr_filter_similarity": False,
    "scr_filter_shape_match": False,
    "scr_filter_shape_match_mobile": False,
    "active_preset": "カスタム設定",
    "prac_market": f"日本株 厳選トレンド銘柄 ({len(JP_TICKERS)}件)",
    "prac_start_date": pd.Timestamp.now().date() - pd.Timedelta(days=365),
    "prac_duration": 60,
    "prac_preset": "🚀 大化け成長株",
    "prac_portfolio": [],
    "prac_results": None,
    "prac_show_results": False,
    "prac_min_total": 5,
    "prac_min_tech": 1,
    "prac_min_fund": 3,
    "prac_filter_pbr": False,
    "prac_filter_per": False,
    "prac_filter_roe": False,
    "prac_filter_dividend": False,
    "prac_filter_rev_growth": False,
    "prac_filter_eps_growth": False,
    "prac_filter_gc": False,
    "prac_filter_macd": False,
    "prac_filter_rsi_os": False,
    "prac_filter_rsi_ob": False,
    "prac_filter_bb_re": False,
    "prac_filter_vol_su": False,
    "prac_filter_similarity": False,
    "prac_filter_shape_match": False,
    "prac_filter_shape_match_mobile": False,
    "prac_active_preset": "カスタム設定"
}
for k, v in widget_defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

def apply_preset(preset_name):
    st.session_state["scr_min_total"] = 0
    st.session_state["scr_min_tech"] = 0
    st.session_state["scr_min_fund"] = 0
    st.session_state["scr_filter_pbr"] = False
    st.session_state["scr_filter_per"] = False
    st.session_state["scr_filter_roe"] = False
    st.session_state["scr_filter_dividend"] = False
    st.session_state["scr_filter_rev_growth"] = False
    st.session_state["scr_filter_eps_growth"] = False
    st.session_state["scr_filter_gc"] = False
    st.session_state["scr_filter_macd"] = False
    st.session_state["scr_filter_rsi_os"] = False
    st.session_state["scr_filter_rsi_ob"] = False
    st.session_state["scr_filter_bb_re"] = False
    st.session_state["scr_filter_vol_su"] = False
    st.session_state["scr_filter_similarity"] = False
    st.session_state["scr_filter_shape_match"] = False
    st.session_state["scr_filter_shape_match_mobile"] = False
    
    if preset_name == "大化け成長株":
        st.session_state["scr_min_total"] = 7
        st.session_state["scr_min_tech"] = 2
        st.session_state["scr_min_fund"] = 4
        st.session_state["scr_filter_roe"] = True
        st.session_state["scr_filter_rev_growth"] = True
        st.session_state["scr_filter_eps_growth"] = True
        st.session_state["scr_filter_vol_su"] = True
        st.session_state["scr_filter_shape_match"] = True
        st.session_state["scr_filter_shape_match_mobile"] = True
    elif preset_name == "高配当割安株":
        st.session_state["scr_min_total"] = 6
        st.session_state["scr_min_tech"] = 1
        st.session_state["scr_min_fund"] = 5
        st.session_state["scr_filter_pbr"] = True
        st.session_state["scr_filter_per"] = True
        st.session_state["scr_filter_dividend"] = True
    elif preset_name == "逆張り・大底打ち":
        st.session_state["scr_min_total"] = 4
        st.session_state["scr_min_tech"] = 1
        st.session_state["scr_min_fund"] = 2
        st.session_state["scr_filter_rsi_os"] = True
        st.session_state["scr_filter_bb_re"] = True
        st.session_state["scr_filter_macd"] = True
    elif preset_name == "急騰ブレイクアウト":
        st.session_state["scr_min_total"] = 5
        st.session_state["scr_min_tech"] = 2
        st.session_state["scr_min_fund"] = 2
        st.session_state["scr_filter_vol_su"] = True
        st.session_state["scr_filter_gc"] = True
        
    st.session_state["active_preset"] = preset_name
    presets_inv = {
        "カスタム設定": "⚙️ カスタム設定",
        "大化け成長株": "🚀 大化け成長株 (CANSLIM風)",
        "高配当割安株": "💰 高配当割安株",
        "逆張り・大底打ち": "🔄 逆張り・大底打ち狙い",
        "急騰ブレイクアウト": "⚡ 急騰ブレイクアウト狙い"
    }
    if preset_name in presets_inv:
        st.session_state["preset_select_mobile"] = presets_inv[preset_name]

def check_preset_match():
    curr = st.session_state.get("active_preset", "カスタム設定")
    if curr == "カスタム設定":
        return
        
    expected = {
        "scr_min_total": 0, "scr_min_tech": 0, "scr_min_fund": 0,
        "scr_filter_pbr": False, "scr_filter_per": False, "scr_filter_roe": False,
        "scr_filter_dividend": False, "scr_filter_rev_growth": False, "scr_filter_eps_growth": False,
        "scr_filter_gc": False, "scr_filter_macd": False, "scr_filter_rsi_os": False,
        "scr_filter_rsi_ob": False, "scr_filter_bb_re": False, "scr_filter_vol_su": False,
        "scr_filter_similarity": False,
        "scr_filter_shape_match" if st.session_state.get('ui_mode', 'PC') != 'スマホ' else "scr_filter_shape_match_mobile": False
    }
    
    if curr == "大化け成長株":
        expected.update({
            "scr_min_total": 7, "scr_min_tech": 2, "scr_min_fund": 4,
            "scr_filter_roe": True, "scr_filter_rev_growth": True, "scr_filter_eps_growth": True,
            "scr_filter_vol_su": True,
            "scr_filter_shape_match" if st.session_state.get('ui_mode', 'PC') != 'スマホ' else "scr_filter_shape_match_mobile": True
        })
    elif curr == "高配当割安株":
        expected.update({
            "scr_min_total": 6, "scr_min_tech": 1, "scr_min_fund": 5,
            "scr_filter_pbr": True, "scr_filter_per": True, "scr_filter_dividend": True
        })
    elif curr == "逆張り・大底打ち":
        expected.update({
            "scr_min_total": 4, "scr_min_tech": 1, "scr_min_fund": 2,
            "scr_filter_rsi_os": True, "scr_filter_bb_re": True, "scr_filter_macd": True
        })
    elif curr == "急騰ブレイクアウト":
        expected.update({
            "scr_min_total": 5, "scr_min_tech": 2, "scr_min_fund": 2,
            "scr_filter_vol_su": True, "scr_filter_gc": True
        })
        
    mismatch = False
    for k, expected_v in expected.items():
        if k in st.session_state and st.session_state[k] != expected_v:
            mismatch = True
            break
            
    if mismatch:
        st.session_state["active_preset"] = "カスタム設定"
        st.session_state["preset_select_mobile"] = "⚙️ カスタム設定"

def apply_practice_preset(preset_name):
    st.session_state["prac_min_tech"] = 0
    st.session_state["prac_filter_gc"] = False
    st.session_state["prac_filter_macd"] = False
    st.session_state["prac_filter_rsi_os"] = False
    st.session_state["prac_filter_rsi_ob"] = False
    st.session_state["prac_filter_bb_re"] = False
    st.session_state["prac_filter_vol_su"] = False
    st.session_state["prac_filter_similarity"] = False
    st.session_state["prac_filter_shape_match"] = False
    st.session_state["prac_filter_shape_match_mobile"] = False
    
    if preset_name == "急騰ブレイクアウト":
        st.session_state["prac_min_tech"] = 2
        st.session_state["prac_filter_vol_su"] = True
        st.session_state["prac_filter_gc"] = True
    elif preset_name == "逆張り・大底打ち":
        st.session_state["prac_min_tech"] = 1
        st.session_state["prac_filter_rsi_os"] = True
        st.session_state["prac_filter_bb_re"] = True
        st.session_state["prac_filter_macd"] = True
    elif preset_name == "トレンド順張り":
        st.session_state["prac_min_tech"] = 2
        st.session_state["prac_filter_shape_match"] = True
        st.session_state["prac_filter_shape_match_mobile"] = True
        
    st.session_state["prac_active_preset"] = preset_name
    presets_inv = {
        "カスタム設定": "⚙️ カスタム設定",
        "急騰ブレイクアウト": "⚡ 急騰ブレイクアウト狙い",
        "逆張り・大底打ち": "🔄 逆張り・大底打ち狙い",
        "トレンド順張り": "📈 トレンド順張り（強モメンタム）"
    }
    if preset_name in presets_inv:
        st.session_state["prac_preset_select_mobile"] = presets_inv[preset_name]

def check_practice_preset_match():
    curr = st.session_state.get("prac_active_preset", "カスタム設定")
    if curr == "カスタム設定":
        return
        
    expected = {
        "prac_min_tech": 0,
        "prac_filter_gc": False, "prac_filter_macd": False, "prac_filter_rsi_os": False,
        "prac_filter_rsi_ob": False, "prac_filter_bb_re": False, "prac_filter_vol_su": False,
        "prac_filter_similarity": False,
        "prac_filter_shape_match" if st.session_state.get('ui_mode', 'PC') != 'スマホ' else "prac_filter_shape_match_mobile": False
    }
    
    if curr == "急騰ブレイクアウト":
        expected.update({
            "prac_min_tech": 2,
            "prac_filter_vol_su": True, "prac_filter_gc": True
        })
    elif curr == "逆張り・大底打ち":
        expected.update({
            "prac_min_tech": 1,
            "prac_filter_rsi_os": True, "prac_filter_bb_re": True, "prac_filter_macd": True
        })
    elif curr == "トレンド順張り":
        expected.update({
            "prac_min_tech": 2,
            "prac_filter_shape_match" if st.session_state.get('ui_mode', 'PC') != 'スマホ' else "prac_filter_shape_match_mobile": True
        })
        
    mismatch = False
    for k, expected_v in expected.items():
        if k in st.session_state and st.session_state[k] != expected_v:
            mismatch = True
            break
            
    if mismatch:
        st.session_state["prac_active_preset"] = "カスタム設定"
        st.session_state["prac_preset_select_mobile"] = "⚙️ カスタム設定"

# Main Navigation Tabs
tab_screen, tab_favorite, tab_simulation, tab_practice, tab_explanation = st.tabs([
    "🔍 スクリーニング実行と結果分析", 
    "⭐ 保有・お気に入り銘柄の分析",
    "💼 仮想シミュレーション（デモトレード）", 
    "🏋️ 過去チャート練習モード",
    "📚 指標とシグナルの解説"
])

# -----------------------------------------------------------------------------
# TAB 1: SCREENING & ANALYSIS
# -----------------------------------------------------------------------------
with tab_screen:
    st.markdown("### ⚙️ スクリーニング条件の設定")
    
    is_mobile = st.session_state.get('ui_mode', 'PC') == 'スマホ'
    
    if is_mobile:
        market = st.selectbox(
            "全体集合（スクリーニング対象）の選択",
            [
                f"日本株 厳選トレンド銘柄 ({len(JP_TICKERS)}件)",
                f"米国株 厳選トレンド銘柄 ({len(US_TICKERS)}件)",
                "日経平均株価 (日経225全銘柄 - 動的取得)",
                "東証プライム (全上場銘柄 - 動的取得)",
                "東証グロース (全上場銘柄 - 動的取得)",
                "カスタム指定"
            ],
            key="scr_market"
        )
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
        period = st.selectbox("データ期間 (チャート用)", ["6ヶ月", "1年", "2年"], index=1, key="scr_period")
    else:
        col_cfg1, col_cfg2, col_cfg3 = st.columns([1.5, 1.5, 1.0])
        with col_cfg1:
            market = st.selectbox(
                "全体集合（スクリーニング対象）の選択",
                [
                    f"日本株 厳選トレンド銘柄 ({len(JP_TICKERS)}件)",
                    f"米国株 厳選トレンド銘柄 ({len(US_TICKERS)}件)",
                    "日経平均株価 (日経225全銘柄 - 動的取得)",
                    "東証プライム (全上場銘柄 - 動的取得)",
                    "東証グロース (全上場銘柄 - 動的取得)",
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

    # Added: Conditional Sector & Size filters for TSE Prime & Growth
    selected_sectors = []
    selected_sizes = []
    if market == "東証プライム (全上場銘柄 - 動的取得)":
        prime_tickers = fetch_tse_prime_tickers()
        all_prime_sectors = ["✨ AI・半導体関連 (テーマ)", "✨ 宇宙開発・防衛関連 (テーマ)"] + sorted(list(set(info.get("sector", "その他") for info in prime_tickers.values() if info.get("sector"))))
        all_prime_sizes = ["TOPIX Core30 (超大型株)", "TOPIX Large70 (大型株)", "TOPIX Mid400 (中堅・中型株)", "TOPIX Small 1 (中小型株)", "TOPIX Small 2 (小型株)"]
        
        st.markdown(
            '<div style="background-color: rgba(37, 99, 235, 0.03); border: 1px solid rgba(37, 99, 235, 0.1); border-radius: 12px; padding: 16px; margin-bottom: 20px;">'
            '<span style="font-size: 0.95rem; font-weight: 600; color: #2563eb;">⚡️ 東証プライム対象銘柄の絞り込み (推奨)</span>'
            '<div style="font-size: 0.8rem; color: #64748b; margin-top: 4px; margin-bottom: 12px;">'
            '※ 候補銘柄数を100〜200銘柄程度に絞り込むことで、スクリーニング速度が劇的に向上し、APIのレートリミットを回避できます。'
            '</div>'
            '</div>', 
            unsafe_allow_html=True
        )
        
        if is_mobile:
            selected_sectors = st.multiselect(
                "🎨 対象業種（33業種区分）で絞り込む (未選択で全業種)",
                options=all_prime_sectors,
                default=[],
                placeholder="すべての業種 (未選択)",
                key="scr_prime_sectors"
            )
            selected_sizes = st.multiselect(
                "🏢 企業規模（TOPIX規模区分）で絞り込む (未選択で全規模)",
                options=all_prime_sizes,
                default=[],
                placeholder="すべての規模 (未選択)",
                key="scr_prime_sizes"
            )
        else:
            col_prime1, col_prime2 = st.columns(2)
            with col_prime1:
                selected_sectors = st.multiselect(
                    "🎨 対象業種（33業種区分）で絞り込む (未選択で全業種)",
                    options=all_prime_sectors,
                    default=[],
                    placeholder="すべての業種 (未選択)",
                    key="scr_prime_sectors"
                )
            with col_prime2:
                selected_sizes = st.multiselect(
                    "🏢 企業規模（TOPIX規模区分）で絞り込む (未選択で全規模)",
                    options=all_prime_sizes,
                    default=[],
                    placeholder="すべての規模 (未選択)",
                    key="scr_prime_sizes"
                )
    elif market == "東証グロース (全上場銘柄 - 動的取得)":
        growth_tickers = fetch_tse_growth_tickers()
        all_growth_sectors = ["✨ AI・半導体関連 (テーマ)", "✨ 宇宙開発・防衛関連 (テーマ)"] + sorted(list(set(info.get("sector", "その他") for info in growth_tickers.values() if info.get("sector"))))
        
        st.markdown(
            '<div style="background-color: rgba(37, 99, 235, 0.03); border: 1px solid rgba(37, 99, 235, 0.1); border-radius: 12px; padding: 16px; margin-bottom: 20px;">'
            '<span style="font-size: 0.95rem; font-weight: 600; color: #2563eb;">⚡️ 東証グロース対象銘柄の絞り込み (推奨)</span>'
            '<div style="font-size: 0.8rem; color: #64748b; margin-top: 4px; margin-bottom: 12px;">'
            '※ 候補銘柄数を絞り込むことで、スクリーニング速度が向上し、APIのレートリミットを回避できます。'
            '</div>'
            '</div>', 
            unsafe_allow_html=True
        )
        
        selected_sectors = st.multiselect(
            "🎨 対象業種（33業種区分）で絞り込む (未選択で全業種)",
            options=all_growth_sectors,
            default=[],
            placeholder="すべての業種 (未選択)",
            key="scr_growth_sectors"
        )
    # Skip original prime checks because we redefine it
    skip_flag = True
    if not skip_flag:
        pass

    # Details expander for score and financial criteria
    with st.expander("📊 詳細なスコア・財務条件フィルタ (クリックで開閉)", expanded=False):
        check_preset_match()
        
        if is_mobile:
            st.markdown("**💡 スクリーニング・プリセット選択**")
            presets = {
                "⚙️ カスタム設定": "カスタム設定",
                "🚀 大化け成長株 (CANSLIM風)": "大化け成長株",
                "💰 高配当割安株": "高配当割安株",
                "🔄 逆張り・大底打ち狙い": "逆張り・大底打ち",
                "⚡ 急騰ブレイクアウト狙い": "急騰ブレイクアウト"
            }
            active_p_name = st.session_state.get("active_preset", "カスタム設定")
            default_index = 0
            for idx, (label, val) in enumerate(presets.items()):
                if val == active_p_name:
                    default_index = idx
                    break
                    
            active_p_label = st.selectbox(
                "プリセットを選択",
                options=list(presets.keys()),
                index=default_index,
                key="preset_select_mobile",
                label_visibility="collapsed"
            )
            active_p = presets[active_p_label]
            if st.session_state.get("active_preset") != active_p:
                apply_preset(active_p)
                st.rerun()
                
            st.markdown('<hr style="margin: 10px 0; border: none; border-top: 1px solid var(--border-color); opacity: 0.5;">', unsafe_allow_html=True)
            
            st.markdown("**🎯 最小スコア設定**")
            min_total_score = st.slider("最小総合スコア (最大10点)", 0, 10, 5, key="scr_min_total")
            min_tech_score = st.slider("最小テクニカルスコア (最大3点)", 0, 3, 1, key="scr_min_tech")
            min_fund_score = st.slider("最小ファンダメンタルスコア (最大7点)", 0, 7, 3, key="scr_min_fund")
            
            st.markdown("**💰 財務指標フィルタ**")
            filter_pbr = st.checkbox("PBR 1.0倍未満 (割安バリュー) のみ", key="scr_filter_pbr")
            filter_per = st.checkbox("PER 15倍未満 (低PER) のみ", key="scr_filter_per")
            filter_roe = st.checkbox("ROE 10%以上 (高PBR効率) のみ", key="scr_filter_roe")
            filter_dividend = st.checkbox("配当利回り 3%以上 のみ", key="scr_filter_dividend")
            filter_rev_growth = st.checkbox("売上高成長率 10%以上 のみ", key="scr_filter_rev_growth")
            filter_eps_growth = st.checkbox("EPS成長率 15%以上 のみ", key="scr_filter_eps_growth")
            
            st.markdown("**📈 テクニナル指標フィルタ**")
            filter_golden_cross = st.checkbox("5日/25日ゴールデンクロス", key="scr_filter_gc")
            filter_macd_cross = st.checkbox("MACDゴールデンクロス", key="scr_filter_macd")
            filter_rsi_oversold = st.checkbox("RSI 30以下 (売られすぎ/割安)", key="scr_filter_rsi_os")
            filter_rsi_overbought = st.checkbox("RSI 70以上 (買われすぎ/過熱)", key="scr_filter_rsi_ob")
            filter_bb_rebound = st.checkbox("ボリンジャーバンド -2σ以下", key="scr_filter_bb_re")
            filter_volume_surge = st.checkbox("出来高急増 (5日平均 > 25日平均*1.2)", key="scr_filter_vol_su")
            filter_similarity_pattern = st.checkbox("🔍 類似連動 (過去類似3局面の20日後上昇率フィルタ)", key="scr_filter_similarity", help="直近20日間のチャート形状に類似する過去 of 局面を直近5年間の歴史データから3つ抽出し、そのすべての局面において20営業日後の上昇率が指定値以上となった銘柄のみを抽出します。他フィルタで絞り込んだ後、最後に実行されます。")
            if filter_similarity_pattern:
                similarity_threshold_pct = st.slider("   ↳ 必要上昇率 (%)", 0.0, 15.0, 5.0, step=0.5, key="scr_similarity_pct")
            else:
                similarity_threshold_pct = 5.0
                
            # Define shape matching filter on mobile
            filter_shape_match = st.checkbox("📈 チャート形状パターン指定", key="scr_filter_shape_match_mobile", help="直近30日間のチャート形状が、指定した特定のパターン（上昇傾向、下降減衰、上昇反転）に類似する銘柄のみを抽出します。")
            if filter_shape_match:
                if "selected_shapes" not in st.session_state:
                    st.session_state["selected_shapes"] = ["上昇傾向", "下降減衰", "上昇反転"]
                st.markdown('<div style="margin-top: 5px; margin-bottom: 5px; font-size: 0.9rem; font-weight: 600; color: #475569;">   ↳ 対象形状を選択 (クリックして切替):</div>', unsafe_allow_html=True)
                
                m_col_s1, m_col_s2, m_col_s3 = st.columns(3)
                with m_col_s1:
                    s_name = "上昇傾向"
                    is_active = s_name in st.session_state["selected_shapes"]
                    if st.button(f"📈 {s_name}", key="btn_shape_up_mobile", use_container_width=True, type="primary" if is_active else "secondary"):
                        if is_active:
                            if len(st.session_state["selected_shapes"]) > 1:
                                st.session_state["selected_shapes"].remove(s_name)
                        else:
                            st.session_state["selected_shapes"].append(s_name)
                        st.rerun()
                with m_col_s2:
                    s_name = "下降減衰"
                    is_active = s_name in st.session_state["selected_shapes"]
                    if st.button(f"📉 {s_name}", key="btn_shape_down_mobile", use_container_width=True, type="primary" if is_active else "secondary"):
                        if is_active:
                            if len(st.session_state["selected_shapes"]) > 1:
                                st.session_state["selected_shapes"].remove(s_name)
                        else:
                            st.session_state["selected_shapes"].append(s_name)
                        st.rerun()
                with m_col_s3:
                    s_name = "上昇反転"
                    is_active = s_name in st.session_state["selected_shapes"]
                    if st.button(f"🔄 {s_name}", key="btn_shape_rev_mobile", use_container_width=True, type="primary" if is_active else "secondary"):
                        if is_active:
                            if len(st.session_state["selected_shapes"]) > 1:
                                st.session_state["selected_shapes"].remove(s_name)
                        else:
                            st.session_state["selected_shapes"].append(s_name)
                        st.rerun()
                selected_shapes = st.session_state["selected_shapes"]
                shape_threshold = st.slider("   ↳ 形状類似度しきい値", 0.70, 0.95, 0.80, step=0.02, key="scr_shape_threshold_mobile", help="しきい値が高いほど、理想的な形状に近い銘柄のみが抽出されます（0.80推奨）。")
            else:
                selected_shapes = []
                shape_threshold = 0.80
        else:
            st.markdown('<div style="font-weight: bold; font-size: 0.95rem; color: var(--text-color); margin-bottom: 8px;">💡 スクリーニング・プリセット選択:</div>', unsafe_allow_html=True)
            col_p1, col_p2, col_p3, col_p4, col_p5 = st.columns(5)
            curr_preset = st.session_state.get("active_preset", "カスタム設定")
            
            with col_p1:
                if st.button("⚙️ カスタム設定", key="btn_preset_custom", use_container_width=True, type="primary" if curr_preset == "カスタム設定" else "secondary"):
                    apply_preset("カスタム設定")
                    st.rerun()
            with col_p2:
                if st.button("🚀 大化け成長株", key="btn_preset_growth", use_container_width=True, type="primary" if curr_preset == "大化け成長株" else "secondary"):
                    apply_preset("大化け成長株")
                    st.rerun()
            with col_p3:
                if st.button("💰 高配当割安株", key="btn_preset_dividend", use_container_width=True, type="primary" if curr_preset == "高配当割安株" else "secondary"):
                    apply_preset("高配当割安株")
                    st.rerun()
            with col_p4:
                if st.button("🔄 逆張り大底打ち", key="btn_preset_reversal", use_container_width=True, type="primary" if curr_preset == "逆張り・大底打ち" else "secondary"):
                    apply_preset("逆張り・大底打ち")
                    st.rerun()
            with col_p5:
                if st.button("⚡ 急騰ブレイク", key="btn_preset_breakout", use_container_width=True, type="primary" if curr_preset == "急騰ブレイクアウト" else "secondary"):
                    apply_preset("急騰ブレイクアウト")
                    st.rerun()
            
            st.markdown('<hr style="margin: 15px 0; border: none; border-top: 1px solid var(--border-color); opacity: 0.5;">', unsafe_allow_html=True)
            
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
                filter_rev_growth = st.checkbox("売上高成長率 10%以上 のみ", key="scr_filter_rev_growth")
                filter_eps_growth = st.checkbox("EPS成長率 15%以上 のみ", key="scr_filter_eps_growth")
            with col_f3:
                st.markdown("**📈 テクニカル指標フィルタ**")
                filter_golden_cross = st.checkbox("5日/25日ゴールデンクロス", key="scr_filter_gc")
                filter_macd_cross = st.checkbox("MACDゴールデンクロス", key="scr_filter_macd")
                filter_rsi_oversold = st.checkbox("RSI 30以下 (売られすぎ/割安)", key="scr_filter_rsi_os")
                filter_rsi_overbought = st.checkbox("RSI 70以上 (買われすぎ/過熱)", key="scr_filter_rsi_ob")
                filter_bb_rebound = st.checkbox("ボリンジャーバンド -2σ以下", key="scr_filter_bb_re")
                filter_volume_surge = st.checkbox("出来高急増 (5日平均 > 25日平均*1.2)", key="scr_filter_vol_su")
                filter_similarity_pattern = st.checkbox("🔍 類似連動 (過去類似3局面の20日後上昇率フィルタ)", key="scr_filter_similarity", help="直近20日間のチャート形状に類似する過去 of 局面を直近5年間の歴史データから3つ抽出し、そのすべての局面において20営業日後の上昇率が指定値以上となった銘柄のみを抽出します。他フィルタで絞り込んだ後、最後に実行されます。")
                if filter_similarity_pattern:
                    similarity_threshold_pct = st.slider("   ↳ 必要上昇率 (%)", 0.0, 15.0, 5.0, step=0.5, key="scr_similarity_pct")
                else:
                    similarity_threshold_pct = 5.0
                
                filter_shape_match = st.checkbox("📈 チャート形状パターン指定", key="scr_filter_shape_match", help="直近30日間のチャート形状が、指定した特定のパターン（上昇傾向、下降減衰、上昇反転）に類似する銘柄のみを抽出します。")
                if filter_shape_match:
                    # Store selected shapes in session state to enable toggle buttons
                    if "selected_shapes" not in st.session_state:
                        st.session_state["selected_shapes"] = ["上昇傾向", "下降減衰", "上昇反転"]
                    
                    st.markdown('<div style="margin-top: 5px; margin-bottom: 5px; font-size: 0.9rem; font-weight: 600; color: #475569;">   ↳ 対象形状を選択 (クリックして切替):</div>', unsafe_allow_html=True)
                    
                    # Render 3 toggle buttons in columns
                    col_s1, col_s2, col_s3 = st.columns(3)
                    with col_s1:
                        s_name = "上昇傾向"
                        is_active = s_name in st.session_state["selected_shapes"]
                        if st.button(f"📈 {s_name}", key="btn_shape_up", use_container_width=True, type="primary" if is_active else "secondary"):
                            if is_active:
                                if len(st.session_state["selected_shapes"]) > 1:
                                    st.session_state["selected_shapes"].remove(s_name)
                            else:
                                st.session_state["selected_shapes"].append(s_name)
                            st.rerun()
                    with col_s2:
                        s_name = "下降減衰"
                        is_active = s_name in st.session_state["selected_shapes"]
                        if st.button(f"📉 {s_name}", key="btn_shape_down", use_container_width=True, type="primary" if is_active else "secondary"):
                            if is_active:
                                if len(st.session_state["selected_shapes"]) > 1:
                                    st.session_state["selected_shapes"].remove(s_name)
                            else:
                                st.session_state["selected_shapes"].append(s_name)
                            st.rerun()
                    with col_s3:
                        s_name = "上昇反転"
                        is_active = s_name in st.session_state["selected_shapes"]
                        if st.button(f"🔄 {s_name}", key="btn_shape_rev", use_container_width=True, type="primary" if is_active else "secondary"):
                            if is_active:
                                if len(st.session_state["selected_shapes"]) > 1:
                                    st.session_state["selected_shapes"].remove(s_name)
                            else:
                                st.session_state["selected_shapes"].append(s_name)
                            st.rerun()
                    
                    selected_shapes = st.session_state["selected_shapes"]
                    shape_threshold = st.slider("   ↳ 形状類似度しきい値", 0.70, 0.95, 0.80, step=0.02, key="scr_shape_threshold", help="しきい値が高いほど、理想的な形状に近い銘柄のみが抽出されます（0.80推奨）。")
                else:
                    selected_shapes = []
                    shape_threshold = 0.80

    tickers_pool = {}
    if market == f"日本株 厳選トレンド銘柄 ({len(JP_TICKERS)}件)":
        tickers_pool = JP_TICKERS
    elif market == f"米国株 厳選トレンド銘柄 ({len(US_TICKERS)}件)":
        tickers_pool = US_TICKERS
    elif market == "日経平均株価 (日経225全銘柄 - 動的取得)":
        tickers_pool = fetch_nikkei225_tickers()
    elif market == "東証プライム (全上場銘柄 - 動的取得)":
        tickers_pool = fetch_tse_prime_tickers()
    elif market == "東証グロース (全上場銘柄 - 動的取得)":
        tickers_pool = fetch_tse_growth_tickers()
    else:
        # Custom
        if custom_tickers:
            parsed = [t.strip().upper() for t in custom_tickers.replace('\n', ',').split(',') if t.strip()]
            
            # Fetch local databases to lookup names
            prime_dir = fetch_tse_prime_tickers()
            growth_dir = fetch_tse_growth_tickers()
            
            for p in parsed:
                name_lookup = p
                if p in prime_dir:
                    name_lookup = prime_dir[p].get("name", p)
                elif p in growth_dir:
                    name_lookup = growth_dir[p].get("name", p)
                elif p in JP_TICKERS:
                    name_lookup = JP_TICKERS[p].get("name", p)
                elif p in US_TICKERS:
                    name_lookup = US_TICKERS[p].get("name", p)
                    
                tickers_pool[p] = {"name": name_lookup, "tags": ["カスタム"]}
                
    # Apply theme filter
    filtered_pool = {}
    for ticker, info in tickers_pool.items():
        tags = info.get('tags', [])
        name = info.get('name', '')
        sector = info.get('sector', '')
        
        # Smart thematic matching
        is_ai_semi = (
            "AI" in tags or "半導体" in tags or 
            any(x in name for x in ["半導体", "ソシオネクスト", "ルネサス", "アドバンテスト", "エレクトロン", "ディスコ", "レーザーテック", "信越化", "東京応化", "ＳＣＲＥＥＮ", "ソフトバンク", "さくらインターネット", "ブレインパッド", "ヘッドウォータ", "ＰＫＳＨＡ", "Ａｐｐｉｅｒ"]) or
            any(x in str(tags) for x in ["Technology", "Semiconductor", "Software", "ソフトウェア", "電気機器", "設計", "情報・通信業"]) or
            sector in ["電気機器", "情報・通信業"]
        )
        
        is_space = (
            "宇宙" in tags or "防衛" in tags or
            any(x in name for x in ["宇宙", "防衛", "重工", "ＩＨＩ", "川崎重", "ispace", "ＱＰＳ", "パスコ", "セック", "明星電気", "細谷火工", "石川製作", "日本アビオ", "東京計器"]) or
            any(x in str(tags) for x in ["Space", "Aerospace", "Defense", "防衛", "航空宇宙", "航空重工", "ロケット", "月面開発", "月面着陸", "衛星システム", "衛星レーダー", "衛星データ分析"])
        )
        
        is_explosive = "急騰期待" in tags or any(x in name for x in ["さくらインターネット", "カバー", "ANYCOLOR", "ＱＰＳ", "ispace", "ヘッドウォータ"])
        is_high_dividend_value = "高配当" in tags or "商社" in tags or "銀行業" in tags or "銀行" in tags or "保険業" in tags or "保険" in tags or "金融" in tags or "その他金融" in tags or "バリュー" in tags or "高配当" in str(tags) or "卸売業" in tags or "商業" in tags or sector in ["卸売業", "銀行業", "保険業", "証券、商品先物取引業", "その他金融業"]
        is_crypto_meme = "ビットコイン保有" in tags or "暗号資産" in tags or "ミーム株" in tags or "暗号資産取引所" in tags or "暗号資産マイニング" in tags or any(x in str(tags) for x in ["Bitcoin", "Crypto", "Meme"]) or any(x in name for x in ["マネックス", "セレス", "リミックス"])
        is_entertainment_vtuber_game = "VTuber" in tags or "ゲーム" in tags or "エンタメ" in tags or "ゲーム・メタバース" in tags or "その他製品" in tags or "ストリーミング" in tags or "SNS" in tags or any(x in name for x in ["任天堂", "ソニー", "カプコン", "スクエニ", "コーエー", "ネクソン", "コナミ", "バンダイ", "カバー", "ANYCOLOR"])
        is_defense_heavy = "防衛" in tags or "宇宙" in tags or "ロケット" in tags or "機械" in tags or "輸送用機器" in tags or "航空重工" in tags or "精密機器" in tags or is_space
        
        # Apply market-specific filters
        if market == "東証プライム (全上場銘柄 - 動的取得)" or market == "東証グロース (全上場銘柄 - 動的取得)":
            if selected_sectors:
                match_sector = False
                for sel in selected_sectors:
                    if sel == "✨ AI・半導体関連 (テーマ)":
                        if is_ai_semi:
                            match_sector = True
                            break
                    elif sel == "✨ 宇宙開発・防衛関連 (テーマ)":
                        if is_space:
                            match_sector = True
                            break
                    else:
                        if sector == sel:
                            match_sector = True
                            break
                if not match_sector:
                    continue
            if market == "東証プライム (全上場銘柄 - 動的取得)" and selected_sizes and info.get("size") not in selected_sizes:
                continue
                
        # Apply theme filter
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
        if len(filtered_pool) > 300:
            st.warning(f"⚠️ 候補銘柄数が多いため（現在 {len(filtered_pool)} 銘柄）、スクリーニング開始時のデータ取得に10〜20秒程度かかる場合があります。必要に応じてサイドバーの「業種・テーマ絞り込み」や「詳細なスコア・財務条件フィルタ」を活用して事前に候補数を絞り込んでください。")
        
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
                    if filter_rev_growth and (metrics['rev_growth'] is None or metrics['rev_growth'] < 10.0):
                        continue
                    if filter_eps_growth and (metrics['eps_growth'] is None or metrics['eps_growth'] < 15.0):
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
                        
                    # 3. Apply the similarity pattern search filter if enabled (Run last for optimal performance)
                    if filter_similarity_pattern:
                        df_5y = get_stock_5y_history(ticker)
                        if df_5y.empty:
                            continue
                        
                        N_len = 20
                        if len(df) < N_len:
                            continue
                            
                        target_prices = df['Close'].iloc[-N_len:].values
                        Z_target = z_normalize(target_prices)
                        
                        matches = []
                        for i in range(len(df_5y) - N_len - 20 + 1):
                            window_df = df_5y.iloc[i : i + N_len]
                            w_start = window_df.index[0]
                            w_end = window_df.index[-1]
                            
                            # Avoid overlapping with the current target window (the last N_len days of df_5y)
                            if i + N_len > len(df_5y) - N_len:
                                continue
                                
                            window_prices = window_df['Close'].values
                            if np.any(np.isnan(window_prices)):
                                continue
                                
                            Z_hist = z_normalize(window_prices)
                            r = np.dot(Z_target, Z_hist) / N_len
                            similarity = max(0.0, r * 100)
                            
                            end_idx = i + N_len + 20
                            all_prices = df_5y['Close'].iloc[i : end_idx].values
                            
                            matches.append({
                                'similarity': similarity,
                                'start_date': w_start,
                                'end_date': w_end,
                                'all_prices': all_prices
                            })
                        
                        # Sort by similarity desc
                        matches = sorted(matches, key=lambda x: x['similarity'], reverse=True)
                        
                        # Filter close matches (must be at least 30 days apart)
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
                                
                        # Check if for all 3 matches, 20-day return is >= 5%
                        pass_similarity_filter = True
                        if len(filtered_matches) < 3:
                            pass_similarity_filter = False
                        else:
                            for m in filtered_matches:
                                all_prices = m['all_prices']
                                if len(all_prices) < N_len + 20:
                                    pass_similarity_filter = False
                                    break
                                price_at_end = all_prices[N_len-1]
                                price_after = all_prices[-1]
                                if price_at_end == 0:
                                    pass_similarity_filter = False
                                    break
                                ret = (price_after - price_at_end) / price_at_end * 100
                                if ret < similarity_threshold_pct:
                                    pass_similarity_filter = False
                                    break
                                    
                        if not pass_similarity_filter:
                            continue
                            
                    # 4. Apply the chart shape match filter (Computed anyway to show in results table)
                    matched_shape_label = "判定不可"
                    matched_shape_corr = 0.0
                    
                    prices_for_shape = df['Close'].values
                    if len(prices_for_shape) >= 30:
                        shape_lbl, shape_corr = check_shape_match(prices_for_shape, threshold=0.70)
                        if shape_lbl:
                            matched_shape_label = f"{shape_lbl} ({shape_corr*100:.0f}%)"
                            matched_shape_corr = shape_corr
                            
                    if filter_shape_match:
                        if matched_shape_label == "判定不可":
                            continue
                        # Extract the base label (e.g. "上昇傾向")
                        base_lbl = matched_shape_label.split(" ")[0]
                        if base_lbl not in selected_shapes:
                            continue
                            
                        # Bypass the strict threshold if it is a Reversal shape and has a positive 5-day price change
                        is_reversal_rising = False
                        if base_lbl == "上昇反転" and len(prices_for_shape) >= 5:
                            if prices_for_shape[-1] > prices_for_shape[-5]:
                                is_reversal_rising = True
                                
                        if not is_reversal_rising and matched_shape_corr < shape_threshold:
                            continue
                        
                    # Determine display name: prefer offline name unless it is equal to ticker
                    display_name = filtered_pool[ticker].get('name', ticker)
                    if (display_name == ticker or not display_name) and metrics.get('name'):
                        display_name = metrics['name']
                        
                    results.append({
                        'ティッカー': ticker,
                        '銘柄名': display_name,
                        '総合スコア (10点)': f"{analysis['total_score']} / 10",
                        'チャート形状': matched_shape_label,
                        'テクニカルスコア (3点)': f"{analysis['tech_score']} / 3",
                        'ファンダスコア (7点)': f"{analysis['fund_score']} / 7",
                        '株価': format_price(metrics['price'], ticker),
                        '前日比 (%)': f"{metrics['change_pct']:.2f}%",
                        '売上高成長率 (%)': f"{metrics['rev_growth']:.1f}%" if metrics['rev_growth'] is not None else "N/A",
                        'EPS成長率 (%)': f"{metrics['eps_growth']:.1f}%" if metrics['eps_growth'] is not None else "N/A",
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
                if is_mobile:
                    cols_to_show = ['ティッカー', '銘柄名', '総合スコア (10点)', '株価', '前日比 (%)', '保有状況']
                    existing_cols = [c for c in cols_to_show if c in df_display.columns]
                    df_display_table = df_display[existing_cols]
                else:
                    df_display_table = df_display

                selected_rows = st.dataframe(
                    df_display_table, 
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
        if is_mobile:
            col_list_owned = st.container()
            col_list_fav = st.container()
        else:
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
            if is_mobile:
                st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
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
        if is_mobile:
            st.caption("💡 選択した銘柄の分析とチャートが以下に表示されます。")
            if st.button("🔄 最新データに更新", key=f"inline_ref_btn_{selected_fav_ticker}", use_container_width=True):
                if cache_key in st.session_state:
                    del st.session_state[cache_key]
                st.rerun()
        else:
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
            # Use batch download to fetch all tickers in one go (fast and robust!)
            histories = batch_download_histories(unique_tickers, period="1y")
            for t in unique_tickers:
                df_h = histories.get(t)
                if df_h is not None and not df_h.empty:
                    # Try to patch with fast_info individually since portfolio size is very small
                    df_h = patch_history_with_fast_info(t, df_h, skip_fast_info=False)
                    histories[t] = df_h
                    closes = df_h['Close'].dropna()
                    if not closes.empty:
                        price_val = float(closes.iloc[-1])
                        latest_prices[t] = price_val
                        # Update session state cache & local record dictionary
                        st.session_state['last_valid_prices'][t] = price_val
                        portfolio_data['last_valid_prices'][t] = price_val
            
            # Save updated price cache back to portfolio file without triggering localStorage sync
            save_portfolio_cache_only(portfolio_data)
                    
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
    if is_mobile:
        row1_col1, row1_col2 = st.columns(2)
        row2_col1, row2_col2 = st.columns(2)
        sum_col1, sum_col2, sum_col3, sum_col4 = row1_col1, row1_col2, row2_col1, row2_col2
    else:
        sum_col1, sum_col2, sum_col3, sum_col4 = st.columns(4)
    
    with sum_col1:
        st.markdown(f"""
        <div class="card" style="border-left: 5px solid #2563eb; padding: 15px; border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); background-color: var(--secondary-background-color); color: var(--text-color); margin-bottom: 10px;">
            <div style="font-size: 0.85rem; color: #64748b; font-weight: 600;">初期総投資額</div>
            <div style="font-size: 1.5rem; font-weight: bold; margin-top: 5px; color: var(--text-color);">{format_price(total_invest_jpy)}</div>
        </div>
        """, unsafe_allow_html=True)
        
    with sum_col2:
        st.markdown(f"""
        <div class="card" style="border-left: 5px solid #475569; padding: 15px; border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); background-color: var(--secondary-background-color); color: var(--text-color); margin-bottom: 10px;">
            <div style="font-size: 0.85rem; color: #64748b; font-weight: 600;">現在合計評価額</div>
            <div style="font-size: 1.5rem; font-weight: bold; margin-top: 5px; color: var(--text-color);">{format_price(total_curr_jpy)}</div>
        </div>
        """, unsafe_allow_html=True)

    with sum_col3:
        total_pl = total_curr_jpy - total_invest_jpy
        total_pl_pct = (total_pl / total_invest_jpy * 100) if total_invest_jpy > 0 else 0.0
        
        pl_color = "#10b981" if total_pl >= 0 else "#ef4444"
        pl_border = "#10b981" if total_pl >= 0 else "#ef4444"
        pl_sign = "+" if total_pl >= 0 else ""
        
        st.markdown(f"""
        <div class="card" style="border-left: 5px solid {pl_border}; padding: 15px; border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); background-color: var(--secondary-background-color); color: var(--text-color); margin-bottom: 10px;">
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
        real_color = "#10b981" if realized_jpy >= 0 else "#ef4444"
        real_border = "#10b981" if realized_jpy >= 0 else "#ef4444"
        real_sign = "+" if realized_jpy >= 0 else ""
        
        st.markdown(f"""
        <div class="card" style="border-left: 5px solid {real_border}; padding: 15px; border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); background-color: var(--secondary-background-color); color: var(--text-color); margin-bottom: 10px;">
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
    
    if is_mobile:
        left_container = st.container()
        right_container = st.container()
    else:
        col_left, col_right = st.columns([1.2, 0.8])
        left_container = col_left
        right_container = col_right
        
    with left_container:
        st.markdown("### 保有銘柄一覧")
        if not records:
            st.info("現在、仮想保有している銘柄はありません。上の『スクリーニング実行と結果分析』タブから評価レポートを表示し、購入ウィジェットから追加してください。")
        else:
            st.caption("※ 保有銘柄の行をクリックして選択すると、売却手続きが可能です。")
            df_display = df_show.drop(columns=["ID", "raw_pl", "raw_pl_pct"])
            
            # Mobile table column optimization
            if is_mobile:
                cols_to_show = ["ティッカー", "銘柄名", "現在値", "保有株数", "評価損益", "損益率"]
                existing_cols = [c for c in cols_to_show if c in df_display.columns]
                df_display_table = df_display[existing_cols]
            else:
                df_display_table = df_display
                
            styled_df = df_display_table.style
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
            
    with right_container:
        st.markdown("### 仮想売却")
        
        if records and selected_portfolio_row_indices and len(selected_portfolio_row_indices) > 0:
            sell_idx = selected_portfolio_row_indices[0]
            selected_rec = records[sell_idx]
            
            total_qty = int(selected_rec["quantity"])
            curr_price = latest_prices.get(selected_rec["ticker"])
            if curr_price is None or pd.isna(curr_price):
                curr_price = st.session_state['last_valid_prices'].get(selected_rec["ticker"], selected_rec["purchase_price"])
            
            st.markdown(f"""
            <div style="background-color: var(--secondary-background-color); border: 1px solid var(--border-color); border-radius: 6px; padding: 12px; margin-bottom: 10px; color: var(--text-color);">
                <div style="display: flex; justify-content: space-between;">
                    <span style="color: var(--text-color); opacity: 0.75;">売却対象:</span>
                    <span style="font-weight: bold; color: var(--text-color);">{selected_rec['name']} ({selected_rec['ticker']})</span>
                </div>
                <div style="display: flex; justify-content: space-between; margin-top: 5px;">
                    <span style="color: var(--text-color); opacity: 0.75;">保有数量:</span>
                    <span style="font-weight: bold; color: var(--text-color);">{total_qty:,} 株</span>
                </div>
                <div style="display: flex; justify-content: space-between; margin-top: 5px;">
                    <span style="color: var(--text-color); opacity: 0.75;">現在価格:</span>
                    <span style="font-weight: bold; color: var(--text-color);">{format_price(curr_price, selected_rec['ticker'])}</span>
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
            
            pl_color_style = "color: #10b981;" if realized_pl >= 0 else "color: #ef4444;"
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
            <div style="background-color: var(--secondary-background-color); border: 1px solid var(--border-color); border-radius: 6px; padding: 10px 12px; margin-bottom: 15px; font-size: 0.9rem; color: var(--text-color);">
                <div style="display: flex; justify-content: space-between;">
                    <span style="color: var(--text-color); opacity: 0.75;">売却予定金額:</span>
                    <span style="font-weight: bold; color: var(--text-color);">{expected_return_str}</span>
                </div>
                <div style="display: flex; justify-content: space-between; margin-top: 5px;">
                    <span style="color: var(--text-color); opacity: 0.75;">確定実現損益:</span>
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
        is_mobile = st.session_state.get('ui_mode', 'PC') == 'スマホ'
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
                line=dict(color='#60a5fa' if is_dark else '#1e3a8a', width=2.5),
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
                template="plotly_dark" if is_dark else "plotly_white",
                height=380,
                margin=dict(l=10, r=10, t=20, b=10),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                dragmode=False if is_mobile else "pan",
                showlegend=not is_mobile
            )
            gridcolor = '#1e293b' if is_dark else '#f1f5f9'
            zerolinecolor = '#334155' if is_dark else '#cbd5e1'
            fig_total.update_yaxes(gridcolor=gridcolor, zerolinecolor=zerolinecolor)
            fig_total.update_xaxes(gridcolor=gridcolor)
            
            with st.container(border=True):
                st.plotly_chart(fig_total, use_container_width=True, config=PLOTLY_CONFIG)
            
        with chart_tab_items:
            is_mobile = st.session_state.get('ui_mode', 'PC') == 'スマホ'
            if realized_pl_list:
                if is_mobile:
                    item_container1 = st.container()
                    item_container2 = st.container()
                else:
                    item_col1, item_col2 = st.columns(2)
                    item_container1 = item_col1
                    item_container2 = item_col2
                    
                with item_container1:
                    st.markdown("<h5 style='text-align: center; color: var(--text-color, #1e293b); margin-bottom: 10px;'>保有銘柄の評価損益 (含み損益)</h5>", unsafe_allow_html=True)
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
                            template="plotly_dark" if is_dark else "plotly_white",
                            height=320,
                            margin=dict(l=10, r=10, t=10, b=10),
                            dragmode=False if is_mobile else "pan"
                        )
                        gridcolor = '#1e293b' if is_dark else '#f1f5f9'
                        zerolinecolor = '#334155' if is_dark else '#cbd5e1'
                        fig_bar_active.update_xaxes(gridcolor=gridcolor, zerolinecolor=zerolinecolor)
                        
                        with st.container(border=True):
                            st.plotly_chart(fig_bar_active, use_container_width=True, config=PLOTLY_CONFIG)
                    else:
                        st.info("現在保有している銘柄はありません。")
                with item_container2:
                    if is_mobile:
                        st.markdown("<hr style='margin: 20px 0; border: none; border-top: 1px solid var(--border-color, #e2e8f0);'>", unsafe_allow_html=True)
                    st.markdown("<h5 style='text-align: center; color: var(--text-color, #1e293b); margin-bottom: 10px;'>売却銘柄の累計確定損益 (実現損益)</h5>", unsafe_allow_html=True)
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
                        template="plotly_dark" if is_dark else "plotly_white",
                        height=320,
                        margin=dict(l=10, r=10, t=10, b=10),
                        dragmode=False if is_mobile else "pan"
                    )
                    gridcolor = '#1e293b' if is_dark else '#f1f5f9'
                    zerolinecolor = '#334155' if is_dark else '#cbd5e1'
                    fig_bar_realized.update_xaxes(gridcolor=gridcolor, zerolinecolor=zerolinecolor)
                    
                    with st.container(border=True):
                        st.plotly_chart(fig_bar_realized, use_container_width=True, config=PLOTLY_CONFIG)
            else:
                st.markdown("<h5 style='text-align: center; color: var(--text-color, #1e293b); margin-bottom: 10px;'>保有銘柄の評価損益 (含み損益)</h5>", unsafe_allow_html=True)
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
                        template="plotly_dark" if is_dark else "plotly_white",
                        height=320,
                        margin=dict(l=10, r=10, t=10, b=10),
                        dragmode=False if is_mobile else "pan"
                    )
                    gridcolor = '#1e293b' if is_dark else '#f1f5f9'
                    zerolinecolor = '#334155' if is_dark else '#cbd5e1'
                    fig_bar_active.update_xaxes(gridcolor=gridcolor, zerolinecolor=zerolinecolor)
                    
                    with st.container(border=True):
                        st.plotly_chart(fig_bar_active, use_container_width=True, config=PLOTLY_CONFIG)
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
# TAB 1.7: PRACTICE MODE (🏋️ 過去チャート練習モード)
# -----------------------------------------------------------------------------
with tab_practice:
    st.markdown("### 🏋️ 過去チャート練習モード（タイムトラベルトレード）")
    st.markdown("""
    過去の特定の時点（基準日）にタイムトラベルし、その時点の株価・テクニカル指標をもとにスクリーニングと仮想購入を行い、
    その後の実際の値動きを追跡してトレードの成果を測定（バックテスト）する練習機能です。
    
    * ※本練習モードでは、過去時点でのバックテストの正確性（先読みバイアスの排除）を担保するため、財務データ（PER、PBR、配当利回り等）は使用せず、純粋なテクニカル指標・株価・出来高およびチャート形状のみでスクリーニングを行います。
    * 練習用データ取得のため、基準日は **2年前〜1ヶ月前** の範囲から選択してください。
    """)
    
    # 1. Settings Columns
    col_s1, col_s2, col_s3 = st.columns(3)
    
    with col_s1:
        # Market pools
        prac_markets = [
            f"日本株 厳選トレンド銘柄 ({len(JP_TICKERS)}件)",
            f"米国株 厳選トレンド銘柄 ({len(US_TICKERS)}件)",
            "日経平均株価 (日経225全銘柄 - 動的取得)",
            "東証プライム (全上場銘柄 - 動的取得)",
            "東証グロース (全上場銘柄 - 動的取得)"
        ]
        prac_market = st.selectbox(
            "練習対象の市場",
            options=prac_markets,
            key="prac_market_selectbox"
        )
        
    with col_s2:
        # Date Input (between 2 years ago and 30 days ago)
        min_prac_date = pd.Timestamp.now().date() - pd.Timedelta(days=730)
        max_prac_date = pd.Timestamp.now().date() - pd.Timedelta(days=30)
        default_prac_date = pd.Timestamp.now().date() - pd.Timedelta(days=365)
        
        prac_start_date = st.date_input(
            "基準日 (練習のスタート日)",
            value=st.session_state.get("prac_start_date", default_prac_date),
            min_value=min_prac_date,
            max_value=max_prac_date,
            key="prac_start_date_input"
        )
        st.session_state["prac_start_date"] = prac_start_date
        
    with col_s3:
        # Holding Period
        durations = {
            "20営業日 (約1ヶ月)": 20,
            "60営業日 (約3ヶ月)": 60,
            "120営業日 (約6ヶ月)": 120,
            "240営業日 (約1年)": 240
        }
        prac_duration_label = st.selectbox(
            "トレード保有期間",
            options=list(durations.keys()),
            index=1, # Default 60 days
            key="prac_duration_selectbox"
        )
        prac_duration = durations[prac_duration_label]
        st.session_state["prac_duration"] = prac_duration
        
    # Presets & Custom filters expander
    with st.expander("🔍 練習用スクリーニング条件の設定 (クリックで開閉)", expanded=True):
        check_practice_preset_match()
        
        if is_mobile:
            st.markdown("**💡 練習用スクリーニング・プリセット選択**")
            prac_presets = {
                "⚙️ カスタム設定": "カスタム設定",
                "⚡ 急騰ブレイクアウト狙い": "急騰ブレイクアウト",
                "🔄 逆張り・大底打ち狙い": "逆張り・大底打ち",
                "📈 トレンド順張り（強モメンタム）": "トレンド順張り"
            }
            prac_active_p_name = st.session_state.get("prac_active_preset", "カスタム設定")
            default_index = 0
            for idx, (label, val) in enumerate(prac_presets.items()):
                if val == prac_active_p_name:
                    default_index = idx
                    break
                    
            prac_active_p_label = st.selectbox(
                "プリセットを選択 (練習用)",
                options=list(prac_presets.keys()),
                index=default_index,
                key="prac_preset_select_mobile",
                label_visibility="collapsed"
            )
            prac_active_p = prac_presets[prac_active_p_label]
            if st.session_state.get("prac_active_preset") != prac_active_p:
                apply_practice_preset(prac_active_p)
                st.rerun()
                
            st.markdown('<hr style="margin: 10px 0; border: none; border-top: 1px solid var(--border-color); opacity: 0.5;">', unsafe_allow_html=True)
            
            st.markdown("**🎯 最小スコア設定**")
            prac_min_tech = st.slider("最小テクニカルスコア (最大3点)", 0, 3, key="prac_min_tech")
            
            st.markdown("**📈 テクニカル指標フィルタ**")
            prac_filter_gc = st.checkbox("5日/25日ゴールデンクロス", key="prac_filter_gc")
            prac_filter_macd = st.checkbox("MACDゴールデンクロス", key="prac_filter_macd")
            prac_filter_rsi_os = st.checkbox("RSI 30以下 (売られすぎ/割安)", key="prac_filter_rsi_os")
            prac_filter_rsi_ob = st.checkbox("RSI 70以上 (買われすぎ/過熱)", key="prac_filter_rsi_ob")
            prac_filter_bb_re = st.checkbox("ボリンジャーバンド -2σ以下", key="prac_filter_bb_re")
            prac_filter_vol_su = st.checkbox("出来高急増 (5日平均 > 25日平均*1.2)", key="prac_filter_vol_su")
            prac_filter_similarity = st.checkbox("🔍 類似連動 (過去類似3局面の20日後上昇率フィルタ)", key="prac_filter_similarity", help="直近20日間のチャート形状に類似する過去の局面を直近5年間の歴史データから3つ抽出し、そのすべての局面において20営業日後の上昇率が指定値以上となった銘柄のみを抽出します。他フィルタで絞り込んだ後、最後に実行されます。")
            if prac_filter_similarity:
                prac_similarity_pct = st.slider("   ↳ 必要上昇率 (%)", 0.0, 15.0, 5.0, step=0.5, key="prac_similarity_pct")
            else:
                prac_similarity_pct = 5.0
                
            prac_filter_shape_match = st.checkbox("📈 チャート形状パターン指定", key="prac_filter_shape_match_mobile", help="直近30日間のチャート形状が、指定した特定のパターン（上昇傾向、下降減衰、上昇反転）に類似する銘柄のみを抽出します。")
            if prac_filter_shape_match:
                if "prac_selected_shapes" not in st.session_state:
                    st.session_state["prac_selected_shapes"] = ["上昇傾向", "下降減衰", "上昇反転"]
                st.markdown('<div style="margin-top: 5px; margin-bottom: 5px; font-size: 0.9rem; font-weight: 600; color: #475569;">   ↳ 対象形状を選択 (クリックして切替):</div>', unsafe_allow_html=True)
                
                m_col_s1, m_col_s2, m_col_s3 = st.columns(3)
                with m_col_s1:
                    s_name = "上昇傾向"
                    is_active = s_name in st.session_state["prac_selected_shapes"]
                    if st.button(f"📈 {s_name}", key="btn_prac_shape_up_mobile", use_container_width=True, type="primary" if is_active else "secondary"):
                        if is_active:
                            if len(st.session_state["prac_selected_shapes"]) > 1:
                                st.session_state["prac_selected_shapes"].remove(s_name)
                        else:
                            st.session_state["prac_selected_shapes"].append(s_name)
                        st.rerun()
                with m_col_s2:
                    s_name = "下降減衰"
                    is_active = s_name in st.session_state["prac_selected_shapes"]
                    if st.button(f"📉 {s_name}", key="btn_prac_shape_down_mobile", use_container_width=True, type="primary" if is_active else "secondary"):
                        if is_active:
                            if len(st.session_state["prac_selected_shapes"]) > 1:
                                st.session_state["prac_selected_shapes"].remove(s_name)
                        else:
                            st.session_state["prac_selected_shapes"].append(s_name)
                        st.rerun()
                with m_col_s3:
                    s_name = "上昇反転"
                    is_active = s_name in st.session_state["prac_selected_shapes"]
                    if st.button(f"🔄 {s_name}", key="btn_prac_shape_rev_mobile", use_container_width=True, type="primary" if is_active else "secondary"):
                        if is_active:
                            if len(st.session_state["prac_selected_shapes"]) > 1:
                                st.session_state["prac_selected_shapes"].remove(s_name)
                        else:
                            st.session_state["prac_selected_shapes"].append(s_name)
                        st.rerun()
                prac_selected_shapes = st.session_state["prac_selected_shapes"]
                prac_shape_threshold = st.slider("   ↳ 形状類似度しきい値", 0.70, 0.95, 0.80, step=0.02, key="prac_shape_threshold_mobile")
            else:
                prac_selected_shapes = []
                prac_shape_threshold = 0.80
        else:
            st.markdown('<div style="font-weight: bold; font-size: 0.95rem; color: var(--text-color); margin-bottom: 8px;">💡 練習用スクリーニング・プリセット選択:</div>', unsafe_allow_html=True)
            col_p1, col_p2, col_p3, col_p4 = st.columns(4)
            prac_curr_preset = st.session_state.get("prac_active_preset", "カスタム設定")
            
            with col_p1:
                if st.button("⚙️ カスタム設定", key="btn_prac_preset_custom", use_container_width=True, type="primary" if prac_curr_preset == "カスタム設定" else "secondary"):
                    apply_practice_preset("カスタム設定")
                    st.rerun()
            with col_p2:
                if st.button("⚡ 急騰ブレイク", key="btn_prac_preset_breakout", use_container_width=True, type="primary" if prac_curr_preset == "急騰ブレイクアウト" else "secondary"):
                    apply_practice_preset("急騰ブレイクアウト")
                    st.rerun()
            with col_p3:
                if st.button("🔄 逆張り大底打ち", key="btn_prac_preset_reversal", use_container_width=True, type="primary" if prac_curr_preset == "逆張り・大底打ち" else "secondary"):
                    apply_practice_preset("逆張り・大底打ち")
                    st.rerun()
            with col_p4:
                if st.button("📈 トレンド順張り", key="btn_prac_preset_trend", use_container_width=True, type="primary" if prac_curr_preset == "トレンド順張り" else "secondary"):
                    apply_practice_preset("トレンド順張り")
                    st.rerun()
            
            st.markdown('<hr style="margin: 15px 0; border: none; border-top: 1px solid var(--border-color); opacity: 0.5;">', unsafe_allow_html=True)
            
            col_f1, col_f2 = st.columns([1.0, 1.5])
            with col_f1:
                st.markdown("**🎯 最小スコア設定**")
                prac_min_tech = st.slider("最小テクニカルスコア (最大3点)", 0, 3, key="prac_min_tech")
            with col_f2:
                st.markdown("**📈 テクニカル指標フィルタ**")
                prac_filter_gc = st.checkbox("5日/25日ゴールデンクロス", key="prac_filter_gc")
                prac_filter_macd = st.checkbox("MACDゴールデンクロス", key="prac_filter_macd")
                prac_filter_rsi_os = st.checkbox("RSI 30以下 (売られすぎ/割安)", key="prac_filter_rsi_os")
                prac_filter_rsi_ob = st.checkbox("RSI 70以上 (買われすぎ/過熱)", key="prac_filter_rsi_ob")
                prac_filter_bb_re = st.checkbox("ボリンジャーバンド -2σ以下", key="prac_filter_bb_re")
                prac_filter_vol_su = st.checkbox("出来高急増 (5日平均 > 25日平均*1.2)", key="prac_filter_vol_su")
                prac_filter_similarity = st.checkbox("🔍 類似連動 (過去類似3局面の20日後上昇率フィルタ)", key="prac_filter_similarity")
                if prac_filter_similarity:
                    prac_similarity_pct = st.slider("   ↳ 必要上昇率 (%)", 0.0, 15.0, 5.0, step=0.5, key="prac_similarity_pct")
                else:
                    prac_similarity_pct = 5.0
                    
                prac_filter_shape_match = st.checkbox("📈 チャート形状パターン指定", key="prac_filter_shape_match")
                if prac_filter_shape_match:
                    if "prac_selected_shapes" not in st.session_state:
                        st.session_state["prac_selected_shapes"] = ["上昇傾向", "下降減衰", "上昇反転"]
                    
                    st.markdown('<div style="margin-top: 5px; margin-bottom: 5px; font-size: 0.9rem; font-weight: 600; color: #475569;">   ↳ 対象形状を選択 (クリックして切替):</div>', unsafe_allow_html=True)
                    
                    col_s1, col_s2, col_s3 = st.columns(3)
                    with col_s1:
                        s_name = "上昇傾向"
                        is_active = s_name in st.session_state["prac_selected_shapes"]
                        if st.button("📈 上昇傾向", key="btn_prac_shape_up", use_container_width=True, type="primary" if is_active else "secondary"):
                            if is_active:
                                if len(st.session_state["prac_selected_shapes"]) > 1:
                                    st.session_state["prac_selected_shapes"].remove(s_name)
                            else:
                                st.session_state["prac_selected_shapes"].append(s_name)
                            st.rerun()
                    with col_s2:
                        s_name = "下降減衰"
                        is_active = s_name in st.session_state["prac_selected_shapes"]
                        if st.button("📉 下降減衰", key="btn_prac_shape_down", use_container_width=True, type="primary" if is_active else "secondary"):
                            if is_active:
                                if len(st.session_state["prac_selected_shapes"]) > 1:
                                    st.session_state["prac_selected_shapes"].remove(s_name)
                            else:
                                st.session_state["prac_selected_shapes"].append(s_name)
                            st.rerun()
                    with col_s3:
                        s_name = "上昇反転"
                        is_active = s_name in st.session_state["prac_selected_shapes"]
                        if st.button("🔄 上昇反転", key="btn_prac_shape_rev", use_container_width=True, type="primary" if is_active else "secondary"):
                            if is_active:
                                if len(st.session_state["prac_selected_shapes"]) > 1:
                                    st.session_state["prac_selected_shapes"].remove(s_name)
                            else:
                                st.session_state["prac_selected_shapes"].append(s_name)
                            st.rerun()
                    prac_selected_shapes = st.session_state["prac_selected_shapes"]
                    prac_shape_threshold = st.slider("   ↳ 形状類似度しきい値", 0.70, 0.95, 0.80, step=0.02, key="prac_shape_threshold")
                else:
                    prac_selected_shapes = []
                    prac_shape_threshold = 0.80
            
    # Trigger button
    if st.button("🏋️ 練習用スクリーニングを実行", type="primary", use_container_width=True, key="btn_prac_screening"):
        # Reset portfolio and result view when running a new screening
        st.session_state["prac_portfolio"] = []
        st.session_state["prac_results"] = None
        st.session_state["prac_show_results"] = False
        st.session_state["prac_selected_labels"] = []
        
        # Load tickers pool
        prac_pool = {}
        if prac_market.startswith("日本株"):
            prac_pool = JP_TICKERS
        elif prac_market.startswith("米国株"):
            prac_pool = US_TICKERS
        elif "日経平均" in prac_market:
            prac_pool = fetch_nikkei225_tickers()
        elif "プライム" in prac_market:
            prac_pool = fetch_tse_prime_tickers()
        elif "グロース" in prac_market:
            prac_pool = fetch_tse_growth_tickers()
            
        if not prac_pool:
            st.error("スクリーニング対象がありません。")
        else:
            with st.spinner("過去データの取得とタイムトラベル分析を実行中..."):
                tickers_list = list(prac_pool.keys())
                # Download 2 years of history for analysis + practice exit tracking
                histories = batch_download_histories(tickers_list, period="2y")
                
                prac_results = []
                p_start_ts = pd.Timestamp(prac_start_date)
                
                # Read granular filters from session state
                p_min_total = st.session_state.get("prac_min_total", 5)
                p_min_tech = st.session_state.get("prac_min_tech", 1)
                p_min_fund = st.session_state.get("prac_min_fund", 3)
                
                p_pbr = st.session_state.get("prac_filter_pbr", False)
                p_per = st.session_state.get("prac_filter_per", False)
                p_roe = st.session_state.get("prac_filter_roe", False)
                p_div = st.session_state.get("prac_filter_dividend", False)
                p_rev = st.session_state.get("prac_filter_rev_growth", False)
                p_eps = st.session_state.get("prac_filter_eps_growth", False)
                
                p_gc = st.session_state.get("prac_filter_gc", False)
                p_macd = st.session_state.get("prac_filter_macd", False)
                p_rsi_os = st.session_state.get("prac_filter_rsi_os", False)
                p_rsi_ob = st.session_state.get("prac_filter_rsi_ob", False)
                p_bb = st.session_state.get("prac_filter_bb_re", False)
                p_vol = st.session_state.get("prac_filter_vol_su", False)
                
                p_similarity = st.session_state.get("prac_filter_similarity", False)
                p_similarity_pct = st.session_state.get("prac_similarity_pct", 5.0) if p_similarity else 5.0
                
                is_mobile_mode = st.session_state.get('ui_mode', 'PC') == 'スマホ'
                p_shape = st.session_state.get("prac_filter_shape_match_mobile" if is_mobile_mode else "prac_filter_shape_match", False)
                p_shape_threshold = st.session_state.get("prac_shape_threshold_mobile" if is_mobile_mode else "prac_shape_threshold", 0.80)
                p_selected_shapes = st.session_state.get("prac_selected_shapes", [])
                
                for ticker in tickers_list:
                    df = histories.get(ticker)
                    if df is None or df.empty:
                        continue
                        
                    # Slice history up to start date
                    df_sliced = df[df.index <= p_start_ts]
                    if len(df_sliced) < 75:
                        continue
                        
                    # Run technical analysis on sliced history (as of start date)
                    tech_analysis = evaluate_stock(ticker, df_sliced, info=None)
                    if tech_analysis is None:
                        continue
                        
                    # Skip if technical score doesn't match
                    if tech_analysis['tech_score'] < p_min_tech:
                        continue
                    if p_gc and not tech_analysis['signals']['golden_cross']:
                        continue
                    if p_macd and not tech_analysis['signals']['macd_cross']:
                        continue
                    if p_rsi_os and not tech_analysis['signals']['rsi_oversold']:
                        continue
                    if p_rsi_ob and not tech_analysis['signals']['rsi_overbought']:
                        continue
                    if p_bb and not tech_analysis['signals']['bb_rebound']:
                        continue
                    if p_vol and not tech_analysis['signals']['volume_surge']:
                        continue
                        
                    metrics = tech_analysis['metrics']
                    
                    # Similarity pattern search filter
                    if p_similarity:
                        df_hist = df_sliced
                        N_len = 20
                        if len(df_hist) < N_len + 20:
                            continue
                            
                        target_prices = df_hist['Close'].iloc[-N_len:].values
                        Z_target = z_normalize(target_prices)
                        
                        matches = []
                        for i in range(len(df_hist) - N_len - 20 - N_len + 1):
                            window_df = df_hist.iloc[i : i + N_len]
                            w_start = window_df.index[0]
                            w_end = window_df.index[-1]
                            
                            window_prices = window_df['Close'].values
                            if np.any(np.isnan(window_prices)):
                                continue
                                
                            Z_hist = z_normalize(window_prices)
                            r = np.dot(Z_target, Z_hist) / N_len
                            similarity = max(0.0, r * 100)
                            
                            end_idx = i + N_len + 20
                            all_prices = df_hist['Close'].iloc[i : end_idx].values
                            
                            matches.append({
                                'similarity': similarity,
                                'start_date': w_start,
                                'end_date': w_end,
                                'all_prices': all_prices
                            })
                            
                        matches = sorted(matches, key=lambda x: x['similarity'], reverse=True)
                        
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
                                
                        pass_similarity_filter = True
                        if len(filtered_matches) < 3:
                            pass_similarity_filter = False
                        else:
                            for m in filtered_matches:
                                all_prices = m['all_prices']
                                if len(all_prices) < N_len + 20:
                                    pass_similarity_filter = False
                                    break
                                price_at_end = all_prices[N_len-1]
                                price_after = all_prices[-1]
                                if price_at_end == 0:
                                    pass_similarity_filter = False
                                    break
                                ret = (price_after - price_at_end) / price_at_end * 100
                                if ret < p_similarity_pct:
                                    pass_similarity_filter = False
                                    break
                                    
                        if not pass_similarity_filter:
                            continue
                            
                    # Shape match check
                    matched_shape = "判定不可"
                    matched_shape_corr = 0.0
                    prices_for_shape = df_sliced['Close'].values
                    if len(prices_for_shape) >= 30:
                        shape_lbl, shape_corr = check_shape_match(prices_for_shape, threshold=0.70)
                        if shape_lbl:
                            matched_shape = f"{shape_lbl} ({shape_corr*100:.0f}%)"
                            matched_shape_corr = shape_corr
                            
                    if p_shape:
                        if matched_shape == "判定不可":
                            continue
                        base_lbl = matched_shape.split(" ")[0]
                        if base_lbl not in p_selected_shapes:
                            continue
                            
                        is_reversal_rising = False
                        if base_lbl == "上昇反転" and len(prices_for_shape) >= 5:
                            if prices_for_shape[-1] > prices_for_shape[-5]:
                                is_reversal_rising = True
                                
                        if not is_reversal_rising and matched_shape_corr < p_shape_threshold:
                            continue
                            
                    display_name = prac_pool[ticker].get('name', ticker)
                    
                    # Store candidate
                    prac_results.append({
                        'ティッカー': ticker,
                        '銘柄名': display_name,
                        '基準日株価': metrics['price'],
                        'テクニカルスコア': tech_analysis['tech_score'],
                        'チャート形状': matched_shape,
                        'full_history': df
                    })
                
                # Sort by score desc
                prac_results = sorted(prac_results, key=lambda x: x['テクニカルスコア'], reverse=True)
                st.session_state["prac_results"] = prac_results
                if prac_results:
                    st.toast(f"✅ {len(prac_results)} 件の銘柄がスクリーニングされました！")
                else:
                    st.toast("⚠️ 条件に合致する銘柄が見つかりませんでした。")
                    
    # 2. Display Screening Results
    if st.session_state.get("prac_results"):
        results = st.session_state["prac_results"]
        st.markdown(f"#### 🔍 基準日 **{prac_start_date}** 時点のスクリーニング結果 ({len(results)}件)")
        
        # Create display dataframe
        df_display_list = []
        for r in results:
            df_display_list.append({
                'ティッカー': r['ティッカー'],
                '銘柄名': r['銘柄名'],
                'テクニカルスコア': f"{r['テクニカルスコア']} / 3",
                '基準日株価': f"{r['基準日株価']:,.1f} 円" if r['ティッカー'].endswith(('.T', 'T')) or '日経平均' in st.session_state.get("prac_market", "") or 'プライム' in st.session_state.get("prac_market", "") or 'グロース' in st.session_state.get("prac_market", "") else f"${r['基準日株価']:,.2f}",
                'チャート形状': r['チャート形状'],
            })
            
        st.dataframe(pd.DataFrame(df_display_list), use_container_width=True)
        
        # 3. Buy Section
        st.markdown("#### 🛍️ 練習用仮想購入（複数選択可）")
        st.caption("※購入したい銘柄を選択し、各銘柄への投資金額（予算）を設定して購入してください。購入後、「結果を見る」ボタンを押すことで、将来のトレード結果を即座に計算できます。")
        
        col_b1, col_b2 = st.columns([2, 1])
        with col_b1:
            ticker_options = [f"{r['ティッカー']} : {r['銘柄名']}" for r in results]
            selected_tickers_labels = st.multiselect(
                "購入する銘柄を選択してください",
                options=ticker_options,
                default=st.session_state.get("prac_selected_labels", [])
            )
            st.session_state["prac_selected_labels"] = selected_tickers_labels
            
        with col_b2:
            budget_per_stock = st.number_input(
                "1銘柄あたりの投資額 (円またはUSD)",
                min_value=1000,
                max_value=10000000,
                value=100000,
                step=10000,
                key="prac_budget_input"
            )
            
        selected_tickers = [lbl.split(" : ")[0] for lbl in selected_tickers_labels]
        
        if st.button("📥 選択した銘柄をポートフォリオに追加", type="secondary", use_container_width=True):
            prac_portfolio = []
            for t in selected_tickers:
                # Find ticker raw data
                match_r = next(r for r in results if r['ティッカー'] == t)
                price = match_r['基準日株価']
                qty = budget_per_stock / price if price > 0 else 0
                prac_portfolio.append({
                    'ticker': t,
                    'name': match_r['銘柄名'],
                    'entry_price': price,
                    'quantity': qty,
                    'budget': budget_per_stock,
                    'full_history': match_r['full_history']
                })
            st.session_state["prac_portfolio"] = prac_portfolio
            st.toast(f"💼 ポートフォリオに {len(prac_portfolio)} 銘柄を追加しました！")
            
    # 4. Display Portfolio and View Results
    if st.session_state.get("prac_portfolio"):
        portfolio = st.session_state["prac_portfolio"]
        st.markdown("---")
        st.markdown("### 💼 練習用ポートフォリオ保有銘柄一覧")
        
        p_rows = []
        for p in portfolio:
            p_rows.append({
                'ティッカー': p['ticker'],
                '銘柄名': p['name'],
                '購入日価格': f"{p['entry_price']:,.1f} 円" if p['ticker'].endswith(('.T', 'T')) or '日経平均' in st.session_state.get("prac_market", "") or 'プライム' in st.session_state.get("prac_market", "") or 'グロース' in st.session_state.get("prac_market", "") else f"${p['entry_price']:,.2f}",
                '購入数量': f"{p['quantity']:,.2f} 株",
                '投資金額': f"{p['budget']:,} 円" if p['ticker'].endswith(('.T', 'T')) or '日経平均' in st.session_state.get("prac_market", "") or 'プライム' in st.session_state.get("prac_market", "") or 'グロース' in st.session_state.get("prac_market", "") else f"${p['budget']:,}"
            })
        st.dataframe(pd.DataFrame(p_rows), use_container_width=True)
        
        # Result decision button
        col_res1, col_res2 = st.columns([2, 1])
        with col_res1:
            btn_results = st.button("🚀 タイムトラベル！指定期間後のトレード結果を見る", type="primary", use_container_width=True, key="btn_prac_results")
        with col_res2:
            if st.button("🗑️ ポートフォリオをクリア", type="secondary", use_container_width=True):
                st.session_state["prac_portfolio"] = []
                st.session_state["prac_show_results"] = False
                st.session_state["prac_selected_labels"] = []
                st.rerun()
                
        if btn_results or st.session_state.get("prac_show_results"):
            st.session_state["prac_show_results"] = True
            
            st.markdown("### 📊 トレード結果レポート")
            
            total_invested = 0
            total_exit_value = 0
            win_count = 0
            loss_count = 0
            
            result_rows = []
            normalized_histories = {} # For chart plotting
            
            is_dark = st.session_state.get('color_theme', 'light') == 'dark'
            
            for p in portfolio:
                df = p['full_history']
                ticker = p['ticker']
                p_start_ts = pd.Timestamp(st.session_state["prac_start_date"])
                
                # Sliced history up to start date to locate the starting index
                df_sliced = df[df.index <= p_start_ts]
                start_idx = len(df_sliced) - 1
                
                # Target index in full history: start_idx + prac_duration
                dur = st.session_state["prac_duration"]
                exit_idx = start_idx + dur
                
                if exit_idx >= len(df):
                    exit_idx = len(df) - 1
                    is_future_limited = True
                else:
                    is_future_limited = False
                    
                entry_date = df.index[start_idx]
                exit_date = df.index[exit_idx]
                
                entry_price = p['entry_price']
                exit_price = df['Close'].iloc[exit_idx]
                
                ret_pct = ((exit_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0
                pl_amount = p['quantity'] * (exit_price - entry_price)
                
                total_invested += p['budget']
                total_exit_value += p['budget'] + pl_amount
                
                if pl_amount > 0:
                    win_count += 1
                else:
                    loss_count += 1
                    
                # Format prices for table display
                is_jpy = ticker.endswith(('.T', 'T')) or '日経平均' in st.session_state.get("prac_market", "") or 'プライム' in st.session_state.get("prac_market", "") or 'グロース' in st.session_state.get("prac_market", "")
                
                result_rows.append({
                    'ティッカー': ticker,
                    '銘柄名': p['name'],
                    '購入日 (価格)': f"{entry_date.strftime('%Y-%m-%d')} ({f'{entry_price:,.1f} 円' if is_jpy else f'${entry_price:,.2f}'})",
                    '売却日 (価格)': f"{exit_date.strftime('%Y-%m-%d')} ({f'{exit_price:,.1f} 円' if is_jpy else f'${exit_price:,.2f}'}){' ⚠️(最終データ)' if is_future_limited else ''}",
                    '損益率 (%)': f"{ret_pct:+.2f}%",
                    '損益額': f"{pl_amount:+,.0f} 円" if is_jpy else f"${pl_amount:+,.2f}"
                })
                
                # Fetch sub-series for returns chart
                sub_df = df.iloc[start_idx : exit_idx + 1]
                if not sub_df.empty:
                    # Normalize to 100
                    normalized_histories[ticker] = (sub_df['Close'] / entry_price) * 100
            
            # Display metrics cards
            net_pl = total_exit_value - total_invested
            net_pct = (net_pl / total_invested) * 100 if total_invested > 0 else 0
            win_rate = (win_count / len(portfolio)) * 100 if portfolio else 0
            
            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            is_jpy_market = any(p['ticker'].endswith(('.T', 'T')) for p in portfolio) or '日経平均' in st.session_state.get("prac_market", "") or 'プライム' in st.session_state.get("prac_market", "") or 'グロース' in st.session_state.get("prac_market", "")
            
            with col_m1:
                st.metric("総投資金額", f"{total_invested:,.0f} 円" if is_jpy_market else f"${total_invested:,.2f}")
            with col_m2:
                # Color code green/red
                color_class = "green-text" if net_pl >= 0 else "red-text"
                prefix = "+" if net_pl >= 0 else ""
                st.markdown(f"""
                <div class="metric-container" style="background-color: var(--card-bg); border: 1px solid var(--border-color); padding: 12px; border-radius: 8px;">
                    <div style="font-size: 0.85rem; color: var(--text-color); opacity: 0.8;">合計純損益</div>
                    <div style="font-size: 1.4rem; font-weight: bold; color: {'#16a34a' if net_pl >= 0 else '#dc2626'}">{prefix}{net_pl:,.0f} 円</div>
                </div>
                """ if is_jpy_market else f"""
                <div class="metric-container" style="background-color: var(--card-bg); border: 1px solid var(--border-color); padding: 12px; border-radius: 8px;">
                    <div style="font-size: 0.85rem; color: var(--text-color); opacity: 0.8;">合計純損益</div>
                    <div style="font-size: 1.4rem; font-weight: bold; color: {'#16a34a' if net_pl >= 0 else '#dc2626'}">{prefix}{net_pl:+,.2f}</div>
                </div>
                """, unsafe_allow_html=True)
            with col_m3:
                prefix = "+" if net_pct >= 0 else ""
                st.markdown(f"""
                <div class="metric-container" style="background-color: var(--card-bg); border: 1px solid var(--border-color); padding: 12px; border-radius: 8px;">
                    <div style="font-size: 0.85rem; color: var(--text-color); opacity: 0.8;">トータル収益率</div>
                    <div style="font-size: 1.4rem; font-weight: bold; color: {'#16a34a' if net_pct >= 0 else '#dc2626'}">{prefix}{net_pct:.2f}%</div>
                </div>
                """, unsafe_allow_html=True)
            with col_m4:
                st.metric("勝率", f"{win_rate:.1f}%", f"{win_count}勝 {loss_count}敗")
                
            # Results table
            st.markdown("#### 📋 銘柄別の取引明細")
            st.dataframe(pd.DataFrame(result_rows), use_container_width=True)
            
            # Plotly return path chart
            if normalized_histories:
                st.markdown("#### 📈 トレード期間中の収益推移 (元本を100%とした比較)")
                
                # Combine normalized histories into one DataFrame for plotting
                combined_chart_df = pd.DataFrame(normalized_histories)
                # Fill missing dates
                combined_chart_df = combined_chart_df.ffill().interpolate()
                
                fig = go.Figure()
                
                for col in combined_chart_df.columns:
                    # Find ticker name
                    t_name = next(p['name'] for p in portfolio if p['ticker'] == col)
                    fig.add_trace(go.Scatter(
                        x=combined_chart_df.index,
                        y=combined_chart_df[col],
                        mode='lines',
                        name=f"{t_name} ({col})",
                        line=dict(width=2.5)
                    ))
                    
                # Add 100% baseline
                fig.add_shape(
                    type="line",
                    x0=combined_chart_df.index[0],
                    y0=100,
                    x1=combined_chart_df.index[-1],
                    y1=100,
                    line=dict(color="grey", width=1.5, dash="dash")
                )
                
                # Style layout
                fig.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    template="plotly_dark" if is_dark else "plotly_white",
                    font=dict(color="white" if is_dark else "black"),
                    xaxis=dict(showgrid=True, gridcolor="rgba(128,128,128,0.2)"),
                    yaxis=dict(title="パフォーマンス (%)", showgrid=True, gridcolor="rgba(128,128,128,0.2)"),
                    legend=dict(x=0.01, y=0.99),
                    margin=dict(l=20, r=20, t=30, b=20)
                )
                st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)

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

# --- localStorage SET synchronization block ---
if st.session_state.get('ls_needs_sync', False):
    portfolio_data_to_sync = load_portfolio()
    portfolio_json_to_sync = json.dumps(portfolio_data_to_sync, indent=4, ensure_ascii=False)
    sync_counter = st.session_state.get('ls_sync_counter', 0)
    res_set = local_storage(
        action="set",
        item_key=f"zen_portfolio_{user_key}",
        value=portfolio_json_to_sync,
        key=f"ls_set_{user_key}_{sync_counter}"
    )
    if res_set is not None:
        st.session_state['ls_needs_sync'] = False
        st.toast("💾 データをブラウザに自動保存しました。")
        st.rerun()
