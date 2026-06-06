import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime
import urllib.request
import urllib.parse
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

# Helper function to format price based on ticker
def format_price(price, ticker):
    if ticker.endswith(".T") or ticker.isdigit():
        return f"{int(price):,}"
    else:
        return f"{price:.2f}"

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
            }).dropna(subset=['Close'])
        else:
            df = data.dropna(subset=['Close'])
        histories[ticker] = df
    else:
        for ticker in tickers_list:
            try:
                # Ensure the ticker has close data in the columns
                if ticker in data['Close'].columns:
                    df = pd.DataFrame({
                        'Open': data['Open'][ticker],
                        'High': data['High'][ticker],
                        'Low': data['Low'][ticker],
                        'Close': data['Close'][ticker],
                        'Volume': data['Volume'][ticker]
                    }).dropna(subset=['Close'])
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
            'longBusinessSummary': raw_info.get('longBusinessSummary')
        }
        
        # Adjust percentages (fraction to % value)
        if needed['returnOnEquity'] is not None and abs(needed['returnOnEquity']) < 1.0:
            needed['returnOnEquity'] *= 100
        if needed['dividendYield'] is not None and needed['dividendYield'] < 1.0:
            needed['dividendYield'] *= 100
            
        return needed
    except Exception:
        return {}

# Dynamic Index constituent fetchers (Scraping from Wikipedia with custom User-Agent)
@st.cache_data(ttl=86400)
def fetch_nikkei225_tickers():
    try:
        url = "https://ja.wikipedia.org/wiki/" + urllib.parse.quote("日経平均株価")
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        html = urllib.request.urlopen(req).read()
        tables = pd.read_html(html)
        components = {}
        for df in tables:
            if '証券コード' in df.columns and '銘柄' in df.columns:
                for _, row in df.iterrows():
                    try:
                        code_val = row['証券コード']
                        if isinstance(code_val, (int, float)) and not pd.isna(code_val):
                            code = str(int(code_val))
                        else:
                            code = str(code_val).strip()
                        if code.isdigit() and len(code) == 4:
                            ticker = f"{code}.T"
                            name = str(row['銘柄']).strip()
                            components[ticker] = {"name": name, "tags": ["日経225"]}
                    except:
                        continue
        if components:
            return components
    except Exception as e:
        st.sidebar.warning(f"日経225の動的取得に失敗しました。ローカルデータを使用します。: {e}")
    return JP_TICKERS

@st.cache_data(ttl=86400)
def fetch_nasdaq100_tickers():
    try:
        url = "https://en.wikipedia.org/wiki/Nasdaq-100"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        html = urllib.request.urlopen(req).read()
        tables = pd.read_html(html)
        components = {}
        for df in tables:
            if 'Ticker' in df.columns and 'Company' in df.columns:
                for _, row in df.iterrows():
                    ticker = str(row['Ticker']).strip().upper()
                    if ticker and ticker.isalpha() and len(ticker) <= 5:
                        name = str(row['Company']).strip()
                        components[ticker] = {"name": name, "tags": ["NASDAQ100", str(row.get('ICB Industry[14]', ''))]}
                if components:
                    return components
    except Exception as e:
        st.sidebar.warning(f"NASDAQ-100の動的取得に失敗しました。ローカルデータを使用します。: {e}")
    return US_TICKERS

@st.cache_data(ttl=86400)
def fetch_sp500_tickers():
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        html = urllib.request.urlopen(req).read()
        tables = pd.read_html(html)
        components = {}
        df = tables[0]
        if 'Symbol' in df.columns and 'Security' in df.columns:
            for _, row in df.iterrows():
                ticker = str(row['Symbol']).strip().upper().replace('.', '-')
                name = str(row['Security']).strip()
                components[ticker] = {"name": name, "tags": ["S&P500", str(row.get('GICS Sector', ''))]}
            if components:
                return components
    except Exception as e:
        st.sidebar.warning(f"S&P 500の動的取得に失敗しました。ローカルデータを使用します。: {e}")
    return US_TICKERS

# Build indicator scoring logic
def evaluate_stock(ticker, df, info=None):
    if df.empty or len(df) < 75:
        return None
        
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
    
    # 1. Technical Signals Check
    # (a) Golden Cross (SMA25 > SMA75 and crossed recently within last 5 days)
    golden_cross = False
    for i in range(-5, 0):
        if abs(i) < len(df):
            if df['SMA25'].iloc[i] > df['SMA75'].iloc[i] and df['SMA25'].iloc[i-1] <= df['SMA75'].iloc[i-1]:
                golden_cross = True
                break
                
    # (b) RSI Oversold / Rebound
    # RSI is below 35 or was below 30 in the last 5 days and is now rising
    rsi_oversold = df['RSI'].iloc[-1] < 35
    rsi_rebound = False
    if not rsi_oversold:
        for i in range(-5, -1):
            if abs(i) < len(df) and df['RSI'].iloc[i] < 30:
                if df['RSI'].iloc[-1] > 30:
                    rsi_rebound = True
                    break
                    
    # (c) MACD Golden Cross (MACD line crosses above Signal line recently)
    macd_cross = False
    for i in range(-5, 0):
        if abs(i) < len(df):
            if df['MACD'].iloc[i] > df['MACD_Signal'].iloc[i] and df['MACD'].iloc[i-1] <= df['MACD_Signal'].iloc[i-1]:
                macd_cross = True
                break
                
    # (d) Bollinger Band Rebound
    # Close price is below or close to the lower band (-2σ)
    bb_rebound = close.iloc[-1] <= df['BB_Lower'].iloc[-1] * 1.02
    
    # (e) Strong Uptrend (Current Close > SMA25 > SMA75)
    uptrend = close.iloc[-1] > df['SMA25'].iloc[-1] and df['SMA25'].iloc[-1] > df['SMA75'].iloc[-1]
    
    # Technical Score calculation (0 to 5)
    tech_score = sum([golden_cross, (rsi_oversold or rsi_rebound), macd_cross, bb_rebound, uptrend])
    
    signals = {
        'golden_cross': golden_cross,
        'rsi_oversold': rsi_oversold or rsi_rebound,
        'macd_cross': macd_cross,
        'bb_rebound': bb_rebound,
        'uptrend': uptrend
    }
    
    # If info is not provided, return technical analysis only (for fast pre-screening)
    if info is None:
        return {
            'df': df,
            'tech_score': tech_score,
            'signals': signals,
            'metrics': {
                'price': close.iloc[-1],
                'change_pct': ((close.iloc[-1] - close.iloc[-2]) / close.iloc[-2]) * 100 if len(close) > 1 else 0.0
            }
        }
        
    # 2. Fundamental Signals Check
    per = info.get('trailingPE')
    pbr = info.get('priceToBook')
    roe = info.get('returnOnEquity')
    div_yield = info.get('dividendYield')
    
    f_pbr_low = pbr is not None and pbr < 1.0
    f_per_low = per is not None and per < 15.0
    f_roe_high = roe is not None and roe >= 10.0
    f_div_high = div_yield is not None and div_yield >= 3.0
    
    # Fundamental Score calculation (0 to 4)
    fund_score = sum([f_pbr_low, f_per_low, f_roe_high, f_div_high])
    
    metrics = {
        'price': close.iloc[-1],
        'change_pct': ((close.iloc[-1] - close.iloc[-2]) / close.iloc[-2]) * 100 if len(close) > 1 else 0.0,
        'per': per,
        'pbr': pbr,
        'roe': roe,
        'dividend_yield': div_yield,
        'market_cap': info.get('marketCap'),
        'name': info.get('longName') or info.get('shortName') or ticker
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
    max_score = 9
    
    if total_score >= 7:
        rating = "**非常に強い上昇シグナル (推奨)**"
    elif total_score >= 5:
        rating = "**上昇期待シグナル (買い推奨)**"
    elif total_score >= 3:
        rating = "**中立・監視対象**"
    else:
        rating = "**買いシグナル弱 / 調整局面**"
        
    text += f"**総合判定**: {rating} (総合スコア: **{total_score}/{max_score}** | テクニカル: {tech_score}/5, ファンダ: {fund_score}/4)\n\n"
    
    text += "#### テクニカル分析の所見\n"
    tech_bullets = []
    if signals['golden_cross']:
        tech_bullets.append("- **ゴールデンクロス成立**: 25日移動平均線が75日移動平均線を上抜け。中期トレンドの上昇転換を示唆する強いシグナルです。")
    if signals['rsi_oversold']:
        tech_bullets.append("- **RSI底値圏からの反発**: RSIが35未満に低下後、反発しています。売られすぎ水準からの買い戻しが入る展開です。")
    if signals['macd_cross']:
        tech_bullets.append("- **MACDゴールデンクロス**: MACDラインがシグナル線を下から上に突き抜けました。上昇モメンタムの発生を示します。")
    if signals['bb_rebound']:
        tech_bullets.append("- **ボリンジャーバンド下限反発**: 株価が-2σラインに接触した後に反発し、移動平均線への平均回帰（上昇）の足がかりを作っています。")
    if signals['uptrend']:
        tech_bullets.append("- **堅調な上昇トレンド**: 株価が主要移動平均線の上側にあり、順並び（SMA25 > SMA75）を維持する安定的な上昇相場です。")
        
    if not tech_bullets:
        tech_bullets.append("- テクニカル面で目立った反発・上昇シグナルは現在点灯していません。")
    text += "\n".join(tech_bullets) + "\n\n"
    
    text += "#### ファンダメンタルズ分析の所見\n"
    fund_bullets = []
    
    pbr = metrics.get('pbr')
    per = metrics.get('per')
    roe = metrics.get('roe')
    div = metrics.get('dividend_yield')
    
    if pbr is not None and pbr < 1.0:
        fund_bullets.append(f"- **解散価値割れ (PBR: {pbr:.2f}倍)**: 解散価値である1倍を下回る、きわめて割安な状態です。東証の株価・資本効率改革の追い風を受けやすい銘柄です。")
    if per is not None and per < 15.0:
        fund_bullets.append(f"- **低PER割安 (PER: {per:.1f}倍)**: 利益に対して株価が割安な水準にあります。市場平均や同業他社に対してバリューの魅力があります。")
    if roe is not None and roe >= 10.0:
        fund_bullets.append(f"- **高資本効率 (ROE: {roe:.1f}%)**: 自己資本を使って高水準の利益を稼ぎ出す優良企業です。株主還元力もあります。")
    if div is not None and div >= 3.0:
        fund_bullets.append(f"- **高配当インカム (配当利回り: {div:.2f}%)**: 年利3%を超える配当があり、株価の下値支持力になると同時に、長期保有の強い味方です。")
        
    if not fund_bullets:
        fund_bullets.append("- ファンダメンタルズ面で割安または超高収益に該当する特定指標はありません（成長投資優先株など）。")
    text += "\n".join(fund_bullets) + "\n\n"
    
    text += "#### 投資戦略アドバイス\n"
    if total_score >= 7:
        text += "バリュー（割安さ）とテクニカル（勢い）が完全に一致した稀有なトレードチャンスです。底値が固く、上に大きく伸びるポテンシャルを有しています。現値付近からの打診買いを推奨します。"
    elif total_score >= 5:
        if tech_score > fund_score:
            text += "目先の株価上昇の勢い（モメンタム）が優勢なトレードに適した銘柄です。ただし割安度は高くないため、25日移動平均線を下抜けした場合には一時撤退するなど、ルールを決めた順張りエントリーが向いています。"
        else:
            text += "強固なビジネスモデルや高い配当に裏打ちされた下値不安の極めて少ないバリュー銘柄です。急騰はせずとも、中期的なポートフォリオの土台として、押し目（下がった場面）で拾い集めていくのに適しています。"
    elif total_score >= 3:
        text += "買いシグナルは一部点灯していますが、相場全体や業界のトレンドなど他の条件も確認しながら慎重に判断してください。現在は監視リストに入れて買いの勢いが強まるのを待つのが無難です。"
    else:
        text += "現在の上昇確度は低めです。焦って購入せず、よりシグナルの点灯数が多い他の推奨銘柄を選択するか、チャートの本格的なボトムアウトを確認するまで様子見を推奨します。"
        
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
        vertical_spacing=0.03, 
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
        height=720,
        template="plotly_white", # White template for clean charting
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=10, r=10, t=35, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    
    # Clean grids
    fig.update_yaxes(gridcolor='#f1f5f9', zerolinecolor='#cbd5e1')
    fig.update_xaxes(gridcolor='#f1f5f9')
    
    return fig

# UI LAYOUT
# Header
st.markdown("""
<div class="title-container">
    <h1 class="title-text">Rising Stock Screener</h1>
    <p class="subtitle-text">AI分析とファンダメンタルズ指標による株価上昇期待銘柄の選定システム</p>
</div>
""", unsafe_allow_html=True)

# Sidebar configurations
st.sidebar.markdown("### スクリーニング設定")

market = st.sidebar.selectbox(
    "全体集合（スクリーニング対象）の選択",
    [
        "日本株 厳選トレンド銘柄 (55件)",
        "米国株 厳選トレンド銘柄 (46件)",
        "日経平均株価 (日経225全銘柄 - 動的取得)",
        "NASDAQ-100 (米国主要100銘柄 - 動的取得)",
        "S&P 500 (米国主要500銘柄 - 動的取得)",
        "カスタム指定"
    ]
)

period = st.sidebar.selectbox("データ期間 (チャート分析用)", ["6ヶ月", "1年", "2年"], index=1)
period_map = {"6ヶ月": "6m", "1年": "1y", "2年": "2y"}
selected_period = period_map[period]

# Custom tickers input
custom_tickers = ""
if market == "カスタム指定":
    custom_tickers = st.sidebar.text_area(
        "カスタムティッカー入力",
        placeholder="例: 7203.T, 6758.T, AAPL, NVDA\n(カンマまたは改行で区切ってください)",
        help="日本株は末尾に .T をつけてください (例: トヨタは 7203.T)"
    )

# Filters
st.sidebar.markdown("### スコア・財務条件フィルタ")
min_total_score = st.sidebar.slider("最小総合スコア (最大9点)", 0, 9, 3)
min_tech_score = st.sidebar.slider("最小テクニカルスコア (最大5点)", 0, 5, 1)
min_fund_score = st.sidebar.slider("最小ファンダメンタルスコア (最大4点)", 0, 4, 0)

filter_pbr = st.sidebar.checkbox("PBR 1.0倍未満 (解散価値割れ) のみ")
filter_per = st.sidebar.checkbox("PER 15倍未満 (低PER) のみ")
filter_roe = st.sidebar.checkbox("ROE 10%以上 (高収益率) のみ")
filter_dividend = st.sidebar.checkbox("配当利回り 3%以上 のみ")

# Prepare target ticker list
tickers_pool = {}
if market == "日本株 厳選トレンド銘柄 (55件)":
    tickers_pool = JP_TICKERS
elif market == "米国株 厳選トレンド銘柄 (46件)":
    tickers_pool = US_TICKERS
elif market == "日経平均株価 (日経225全銘柄 - 動的取得)":
    tickers_pool = fetch_nikkei225_tickers()
elif market == "NASDAQ-100 (米国主要100銘柄 - 動的取得)":
    tickers_pool = fetch_nasdaq100_tickers()
elif market == "S&P 500 (米国主要500銘柄 - 動的取得)":
    tickers_pool = fetch_sp500_tickers()
else:
    # Custom
    if custom_tickers:
        parsed = [t.strip().upper() for t in custom_tickers.replace('\n', ',').split(',') if t.strip()]
        for p in parsed:
            tickers_pool[p] = {"name": p, "tags": ["カスタム"]}
            
# Theme filter in sidebar
theme_filter = st.sidebar.selectbox(
    "トレンドテーマ絞り込み",
    ["すべて", "AI・半導体関連", "宇宙産業・開発関連", "爆発的急騰期待株"]
)

# Apply theme filter
filtered_pool = {}
for ticker, info in tickers_pool.items():
    tags = info.get('tags', [])
    # Support sector matching for dynamic indexes in addition to pre-defined tags
    is_ai_semi = "AI" in tags or "半導体" in tags or any(x in str(tags) for x in ["Technology", "Semiconductor", "Software", "ソフトウェア"])
    is_space = "宇宙" in tags or any(x in str(tags) for x in ["Space", "Aerospace", "Defense", "防衛", "航空宇宙"])
    is_explosive = "急騰期待" in tags
    
    if theme_filter == "AI・半導体関連":
        if is_ai_semi:
            filtered_pool[ticker] = info
    elif theme_filter == "宇宙産業・開発関連":
        if is_space:
            filtered_pool[ticker] = info
    elif theme_filter == "爆発的急騰期待株":
        if is_explosive:
            filtered_pool[ticker] = info
    else:
        filtered_pool[ticker] = info
            
# Main Navigation Tabs
tab_screen, tab_explanation = st.tabs(["スクリーニング実行と結果分析", "指標とシグナルの解説"])

with tab_screen:
    if not filtered_pool:
        st.info("左側のサイドバーから市場を選択するか、カスタムティッカーを入力してください。また絞り込みテーマに該当する銘柄があるか確認してください。")
    else:
        st.markdown(f"**対象銘柄数**: {len(filtered_pool)} 銘柄が読み込まれました。")
        
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
                        
                    # 2. Fetch fundamentals ONLY for stocks passing technical checks (Huge speedup!)
                    info = get_ticker_info(ticker)
                    
                    # Run full analysis
                    analysis = evaluate_stock(ticker, df, info)
                    if analysis is None:
                        continue
                        
                    metrics = analysis['metrics']
                    signals = analysis['signals']
                    
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
                        
                    results.append({
                        'ティッカー': ticker,
                        '銘柄名': filtered_pool[ticker]['name'],
                        '総合スコア (9点)': f"{analysis['total_score']} / 9",
                        'テクニカルスコア (5点)': f"{analysis['tech_score']} / 5",
                        'ファンダスコア (4点)': f"{analysis['fund_score']} / 4",
                        '株価': format_price(metrics['price'], ticker),
                        '前日比 (%)': f"{metrics['change_pct']:.2f}%",
                        'PER (倍)': f"{metrics['per']:.1f}" if metrics['per'] is not None else "N/A",
                        'PBR (倍)': f"{metrics['pbr']:.2f}" if metrics['pbr'] is not None else "N/A",
                        'ROE (%)': f"{metrics['roe']:.1f}%" if metrics['roe'] is not None else "N/A",
                        '配当利回り (%)': f"{metrics['dividend_yield']:.2f}%" if metrics['dividend_yield'] is not None else "N/A",
                        'テーマ/タグ': ", ".join(filtered_pool[ticker].get('tags', [])),
                        # Hidden data used for details
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
                for r in results:
                    row = {k: v for k, v in r.items() if k != 'raw_data'}
                    # Add clean text signals
                    raw = r['raw_data']
                    badges = []
                    if raw['signals']['golden_cross']: badges.append("GC")
                    if raw['signals']['rsi_oversold']: badges.append("RSI底")
                    if raw['signals']['macd_cross']: badges.append("MACD")
                    if raw['signals']['bb_rebound']: badges.append("BB底")
                    if raw['signals']['uptrend']: badges.append("上昇トレンド")
                    
                    row['点灯シグナル'] = " ".join(badges) if badges else "なし"
                    display_data.append(row)
                    
                df_display = pd.DataFrame(display_data)
                
                # Sort by score descending
                df_display['sort_val'] = df_display['総合スコア (9点)'].apply(lambda x: int(x.split('/')[0]))
                df_display = df_display.sort_values(by='sort_val', ascending=False).drop(columns=['sort_val']).reset_index(drop=True)
                
                # Show dataframe
                st.dataframe(
                    df_display, 
                    use_container_width=True,
                    column_config={
                        "ティッカー": st.column_config.TextColumn("ティッカー", width="small"),
                        "前日比 (%)": st.column_config.TextColumn("前日比 (%)"),
                    }
                )
                
                # Select stock for deep analysis
                st.markdown("---")
                st.markdown("### 個別銘柄のテクニカル・ファンダメンタルズ詳細分析")
                selected_ticker_label = st.selectbox(
                    "詳細なチャートと推奨レポートを表示する銘柄を選択してください",
                    options=[f"{r['ティッカー']} - {r['銘柄名']}" for r in results]
                )
                
                if selected_ticker_label:
                    selected_ticker = selected_ticker_label.split(" - ")[0]
                    # Find corresponding raw data
                    selected_item = next(item for item in results if item['ティッカー'] == selected_ticker)
                    raw_analysis = selected_item['raw_data']
                    
                    # Layout layout for detailed metrics
                    st.markdown(f"#### {selected_item['銘柄名']} ({selected_ticker}) の分析ダッシュボード")
                    
                    col1, col2, col3, col4, col5 = st.columns(5)
                    with col1:
                        st.markdown("""<div class="card">
                            <div class="metric-title">現在株価</div>
                            <div class="metric-value metric-accent">{}</div>
                        </div>""".format(selected_item['株価']), unsafe_allow_html=True)
                    with col2:
                        st.markdown("""<div class="card">
                            <div class="metric-title">前日比</div>
                            <div class="metric-value">{}</div>
                        </div>""".format(selected_item['前日比 (%)']), unsafe_allow_html=True)
                    with col3:
                        st.markdown("""<div class="card">
                            <div class="metric-title">PER / PBR</div>
                            <div class="metric-value">{}倍 / {}倍</div>
                        </div>""".format(selected_item['PER (倍)'], selected_item['PBR (倍)']), unsafe_allow_html=True)
                    with col4:
                        st.markdown("""<div class="card">
                            <div class="metric-title">ROE (自己資本利益率)</div>
                            <div class="metric-value">{}</div>
                        </div>""".format(selected_item['ROE (%)']), unsafe_allow_html=True)
                    with col5:
                        st.markdown("""<div class="card">
                            <div class="metric-title">配当利回り</div>
                            <div class="metric-value">{}</div>
                        </div>""".format(selected_item['配当利回り (%)']), unsafe_allow_html=True)
                    
                    # Detailed analysis tabs (Technical Chart vs Business/IR Catalyst Analysis)
                    det_tab_chart, det_tab_ir = st.tabs(["チャートと技術分析", "事業内容とカタリスト予測"])
                    
                    with det_tab_chart:
                        chart_col, rpt_col = st.columns([1.3, 0.7])
                        with chart_col:
                            fig = create_chart(raw_analysis['df'], selected_ticker, selected_item['銘柄名'])
                            st.plotly_chart(fig, use_container_width=True)
                        with rpt_col:
                            report_md = generate_recommendation_text(
                                ticker=selected_ticker,
                                name=selected_item['銘柄名'],
                                tech_score=raw_analysis['tech_score'],
                                fund_score=raw_analysis['fund_score'],
                                signals=raw_analysis['signals'],
                                metrics=raw_analysis['metrics']
                            )
                            st.markdown(f'<div class="card" style="height: 720px; overflow-y: auto;">{report_md}</div>', unsafe_allow_html=True)
                            
                    with det_tab_ir:
                        # Business & IR analysis
                        ir_md = generate_ir_catalysts(
                            ticker=selected_ticker,
                            tags=filtered_pool.get(selected_ticker, {}).get('tags', []),
                            info=raw_analysis.get('info_raw', {})
                        )
                        st.markdown(f'<div class="card" style="padding: 25px; max-height: 720px; overflow-y: auto;">{ir_md}</div>', unsafe_allow_html=True)

with tab_explanation:
    st.markdown("""
    ## スクリーニング指標の基礎知識と上昇期待の理由
    
    株価が上昇する背景には、**「テクニカル（チャートの勢いや売られすぎからの反発）」**と**「ファンダメンタルズ（企業の割安性や稼ぐ力）」**の2大要素があります。本アプリは、この2つを総合的にスコアリング（最高9点）して銘柄を選定します。
    
    ### テクニカル指標 (5点満点)
    テクニカル分析は、買い手と売り手の心理をチャートから読み取り、株価が上昇するタイミングを捉えます。
    
    1. **ゴールデンクロス (GC)**
       - **仕組み**: 短期（25日）の移動平均線が、長期（75日）の移動平均線を下から上に抜ける現象です。
       - **上昇期待の理由**: 下落トレンドが終わり、買い圧力が上回って**中期的な上昇トレンドに転換したサイン**と捉えられます。
       
    2. **RSI (相対力指数) 底値反発**
       - **仕組み**: 株価の「買われすぎ（70%以上）」「売られすぎ（30%以下）」を示す指標です。
       - **上昇期待の理由**: 30%以下は市場が過剰に売っている状態で、そこからの反発は**悪材料出尽くしや自律反発による急上昇**が期待できます。
       
    3. **MACD (マックディー) ゴールデンクロス**
       - **仕組み**: 移動平均線の発展版で、価格の「勢い（モメンタム）」を捉えます。MACD線がシグナル線を下から上抜けるポイントです。
       - **上昇期待の理由**: 移動平均線のゴールデンクロスよりも**素早くトレンド転換を検知**できるため、上昇の初期微動に乗ることができます。
       
    4. **ボリンジャーバンド下限 (-2σ) 反発**
       - **仕組み**: 統計学を用いて株価が収まる価格帯（バンド）を計算します。株価の95.4%は ±2σ のバンド内に収まります。
       - **上昇期待の理由**: 株価が下のバンド (-2σ) に接触、または突き抜けるのは統計的に「極端な売られすぎ」であり、**バンドの中心（平均値）に向けて株価が戻る反発力**が働きやすくなります。
       
    5. **安定上昇トレンド (順並び)**
       - **仕組み**: 株価 > 25日線 > 75日線 という綺麗な並び順が成立している状態です。
       - **上昇期待の理由**: 支持線（押し目買いの目処）がしっかりしており、投資家の信頼が厚いため、**突発的な悪材料がなければ持続的に高値を更新しやすい**状態です。
    
    ---
    
    ### ファンダメンタルズ指標 (4点満点)
    ファンダメンタルズ分析は、企業の実力（資産・業績）と現在の株価を比較し、本来の価値より安く放置されているものを探します。
    
    1. **PBR (株価純資産倍率) < 1.0倍**
       - **仕組み**: 株価が1株当たり純資産の何倍かを示します。1.0倍＝会社の解散価値と同額です。
       - **上昇期待の理由**: PBR 1倍割れは「会社を解散して資産を分けた方がマシ」な状態であり、極めて割安です。特に東京証券取引所はPBR1倍割れ企業に対して改善（自社株買いや増配など）を求めており、**企業のアクションによる株価上昇**が強く見込めます。
       
    2. **PER (株価収益率) < 15倍**
       - **仕組み**: 株価が1株当たり利益の何倍かを示します。
       - **上昇期待の理由**: 企業の稼ぐ利益に対して株価が割安であることを意味します。割安な状態で放置されている優良株は、市場全体が好転した際に買いが集まりやすく、**適正水準への水準訂正（株価上昇）**が期待できます。
       
    3. **ROE (自己資本利益率) >= 10%**
       - **仕組み**: 株主から集めた資金をどれだけ効率よく利益に変えられているかを示す「経営効率」の指標です。
       - **上昇期待の理由**: ROE 10%以上はグローバル基準でも優良な水準です。効率的にお金を生み出せる企業は、さらなる事業拡大や増配を行いやすく、**機関投資家などの大口資金が好んで買ってくるため、長期的な株価上昇**につながります。
       
    4. **配当利回り >= 3.0%**
       - **仕組み**: 株価に対する年間配当金の割合です。
       - **上昇期待の理由**: 配当利回りが高いと、株価が下がった際に「配当金目当て」の買い（下値支持）が入りやすくなり、下落リスクが下がります。また、配当を維持できる財務の健全性があることの証明でもあり、**安定した上昇**が期待できます。
    """)
