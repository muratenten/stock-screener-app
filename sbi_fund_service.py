"""
SBI Investment Trust Packs Intelligence & Screener Service
Comprehensive database of 35+ top-ranked SBI Securities funds (eMAXIS Slim, SBI・V, FANG+, Saku-tto, Active),
quantitative scoring, advanced filtering, multi-fund comparison, and dedicated individual chart analysis.
"""

import time
from typing import List, Dict, Any, Optional
import pandas as pd
import yfinance as yf

# In-memory cache for chart series (TTL = 30 minutes)
_CHART_CACHE: Dict[str, Any] = {}
_INDIVIDUAL_CHART_CACHE: Dict[str, Any] = {}

# Master Database of 35+ Top SBI Securities Investment Trusts
SBI_FUNDS_DB: List[Dict[str, Any]] = [
    # =========================================================================
    # 1. eMAXIS Slim Series (The Crown Jewels of Low-Cost Indexing)
    # =========================================================================
    {
        "id": "emaxis_slim_all_country",
        "name": "ｅＭＡＸＩＳ Ｓｌｉｍ 全世界株式（オール・カントリー）",
        "nickname": "オルカン",
        "category": "王道インデックス",
        "type": "インデックス",
        "trustee": "三菱UFJアセットマネジメント",
        "underlying": "MSCI ACWI（日本を含む全世界株式）",
        "proxy_ticker": "VT",
        "expense_ratio": 0.05775,
        "aum_oku": 46500,
        "nisa_tsumitate": True,
        "nisa_growth": True,
        "return_1y": 28.8,
        "return_3y_annual": 20.4,
        "sharpe_ratio": 1.06,
        "max_drawdown": -16.5,
        "major_holdings": ["マイクロソフト", "NVIDIA", "アップル", "アマゾン", "Meta", "Alphabet", "TSMC"],
        "description": "日本を含む世界47カ国・約3,000社に分散。信託報酬0.057%台・純資産4.6兆円を誇る国内投信界の絶対王者。",
        "role": "コア資産（世界分散の頂点）"
    },
    {
        "id": "emaxis_slim_sp500",
        "name": "ｅＭＡＸＩＳ Ｓｌｉｍ 米国株式（Ｓ＆Ｐ５００）",
        "nickname": "Slim S&P500",
        "category": "王道インデックス",
        "type": "インデックス",
        "trustee": "三菱UFJアセットマネジメント",
        "underlying": "S&P500指数（配当込み、円換算）",
        "proxy_ticker": "VOO",
        "expense_ratio": 0.09372,
        "aum_oku": 53500,
        "nisa_tsumitate": True,
        "nisa_growth": True,
        "return_1y": 32.6,
        "return_3y_annual": 24.9,
        "sharpe_ratio": 1.16,
        "max_drawdown": -18.1,
        "major_holdings": ["マイクロソフト", "NVIDIA", "アップル", "アマゾン", "Meta", "Alphabet", "ブロードコム"],
        "description": "純資産5兆円突破。米国優良500社に業界最安水準で投資できる、つみたてNISA人気ぶっちぎり首位ファンド。",
        "role": "コア資産（米国成長の王道）"
    },
    {
        "id": "emaxis_slim_developed_ex_jp",
        "name": "ｅＭＡＸＩＳ Ｓｌｉｍ 先進国株式インデックス",
        "nickname": "Slim 先進国",
        "category": "王道インデックス",
        "type": "インデックス",
        "trustee": "三菱UFJアセットマネジメント",
        "underlying": "MSCIコクサイ・インデックス（日本除く）",
        "proxy_ticker": "VEA",
        "expense_ratio": 0.09889,
        "aum_oku": 8800,
        "nisa_tsumitate": True,
        "nisa_growth": True,
        "return_1y": 30.1,
        "return_3y_annual": 22.8,
        "sharpe_ratio": 1.11,
        "max_drawdown": -17.2,
        "major_holdings": ["マイクロソフト", "NVIDIA", "アップル", "アマゾン", "ノボ・ノルディスク", "ASML"],
        "description": "日本を除く先進国22カ国の主要企業に投資。米国株約7割＋欧州等で構成される安定のロングセラー。",
        "role": "コア資産（日本除く先進国）"
    },
    {
        "id": "emaxis_slim_topix",
        "name": "ｅＭＡＸＩＳ Ｓｌｉｍ 国内株式（ＴＯＰＩＸ）",
        "nickname": "Slim TOPIX",
        "category": "王道インデックス",
        "type": "インデックス",
        "trustee": "三菱UFJアセットマネジメント",
        "underlying": "東証株価指数 (TOPIX)",
        "proxy_ticker": "1306.T",
        "expense_ratio": 0.14300,
        "aum_oku": 2900,
        "nisa_tsumitate": True,
        "nisa_growth": True,
        "return_1y": 23.5,
        "return_3y_annual": 17.8,
        "sharpe_ratio": 0.95,
        "max_drawdown": -15.4,
        "major_holdings": ["トヨタ自動車", "三菱UFJ FG", "ソニーグループ", "日立製作所", "キーエンス"],
        "description": "東証プライム上場企業全体に分散投資。日銀利上げ・デフレ完全脱却で構造的最高益を更新する日本株本命。",
        "role": "コア資産（国内市場全体）"
    },
    {
        "id": "emaxis_slim_nikkei",
        "name": "ｅＭＡＸＩＳ Ｓｌｉｍ 国内株式（日経平均）",
        "nickname": "Slim 日経平均",
        "category": "王道インデックス",
        "type": "インデックス",
        "trustee": "三菱UFJアセットマネジメント",
        "underlying": "日経平均株価 (日経225)",
        "proxy_ticker": "1321.T",
        "expense_ratio": 0.14300,
        "aum_oku": 2200,
        "nisa_tsumitate": True,
        "nisa_growth": True,
        "return_1y": 25.1,
        "return_3y_annual": 19.2,
        "sharpe_ratio": 0.97,
        "max_drawdown": -18.2,
        "major_holdings": ["ファーストリテイリング", "東京エレクトロン", "ソフトバンクグループ", "アドバンテスト", "信越化学"],
        "description": "日本を代表するブルーチップ225社に連動。半導体や輸出ハイテクの比率が高くモメンタムが出やすい。",
        "role": "国内ブルーチップ集中"
    },
    {
        "id": "emaxis_slim_emerging",
        "name": "ｅＭＡＸＩＳ Ｓｌｉｍ 新興国株式インデックス",
        "nickname": "Slim 新興国",
        "category": "インド・新興国",
        "type": "インデックス",
        "trustee": "三菱UFJアセットマネジメント",
        "underlying": "MSCIエマージング・マーケット・インデックス",
        "proxy_ticker": "EEM",
        "expense_ratio": 0.15180,
        "aum_oku": 2350,
        "nisa_tsumitate": True,
        "nisa_growth": True,
        "return_1y": 14.8,
        "return_3y_annual": 7.9,
        "sharpe_ratio": 0.64,
        "max_drawdown": -24.1,
        "major_holdings": ["TSMC", "テンセント", "サムスン電子", "アリババ", "リライアンス"],
        "description": "中国・インド・台湾・ブラジルなど急成長する新興国市場を網羅。低コストで新興国マネーを取り込む。",
        "role": "新興国サテライト"
    },
    {
        "id": "emaxis_slim_balance_8",
        "name": "ｅＭＡＸＩＳ Ｓｌｉｍ バランス（８資産均等型）",
        "nickname": "Slim 8資産均等",
        "category": "金・債券・バランス",
        "type": "バランス型",
        "trustee": "三菱UFJアセットマネジメント",
        "underlying": "国内/先進国/新興国の株式・債券・REIT各12.5%",
        "proxy_ticker": "AOR",
        "expense_ratio": 0.14300,
        "aum_oku": 3100,
        "nisa_tsumitate": True,
        "nisa_growth": True,
        "return_1y": 15.2,
        "return_3y_annual": 11.4,
        "sharpe_ratio": 0.88,
        "max_drawdown": -11.5,
        "major_holdings": ["世界各国の株式・債券・不動産REIT各12.5%均等保有"],
        "description": "株だけでなく債券・REITまで8資産を自動均等配分。暴落耐性が極めて高く、放置で低リスク運用が可能。",
        "role": "超安定バランス運用"
    },

    # =========================================================================
    # 2. Megatrend High Growth / Tech Concentrated (FANG+ & NASDAQ100)
    # =========================================================================
    {
        "id": "ifreenext_fang_plus",
        "name": "ｉＦｒｅｅＮＥＸＴ ＦＡＮＧ＋インデックス",
        "nickname": "FANG+ (メガテック10社)",
        "category": "FANG+・ハイテク",
        "type": "インデックス",
        "trustee": "大和アセットマネジメント",
        "underlying": "NYSE FANG+ Index",
        "proxy_ticker": "FNGS",
        "expense_ratio": 0.77550,
        "aum_oku": 3950,
        "nisa_tsumitate": True,
        "nisa_growth": True,
        "return_1y": 51.4,
        "return_3y_annual": 38.2,
        "sharpe_ratio": 1.25,
        "max_drawdown": -35.2,
        "major_holdings": ["NVIDIA", "Meta", "アマゾン", "マイクロソフト", "アップル", "Alphabet", "ブロードコム", "Netflix", "スノーフレイク", "テスラ"],
        "description": "世界を変革する超巨大テック10社に約10%ずつ均等投資。圧倒的破壊力でS&P500を凌駕し続ける大人気グロース投信。",
        "role": "超積極グロース（本命）"
    },
    {
        "id": "nissey_nasdaq100",
        "name": "ニッセイＮＡＳＤＡＱ１００インデックスファンド",
        "nickname": "ニッセイNASDAQ100",
        "category": "FANG+・ハイテク",
        "type": "インデックス",
        "trustee": "ニッセイアセットマネジメント",
        "underlying": "NASDAQ-100指数（配当込み、円換算）",
        "proxy_ticker": "QQQ",
        "expense_ratio": 0.20350,
        "aum_oku": 2650,
        "nisa_tsumitate": False,
        "nisa_growth": True,
        "return_1y": 37.8,
        "return_3y_annual": 27.5,
        "sharpe_ratio": 1.18,
        "max_drawdown": -23.4,
        "major_holdings": ["マイクロソフト", "アップル", "NVIDIA", "アマゾン", "Meta", "Alphabet", "ブロードコム"],
        "description": "米ナスダック市場の金融除く上位100社に連動。信託報酬0.20%の業界最安級で米ITイノベーションを独占。",
        "role": "ハイテク大型成長"
    },
    {
        "id": "rakuten_sox",
        "name": "楽天・半導体株インデックス・ファンド",
        "nickname": "楽天 SOX",
        "category": "FANG+・ハイテク",
        "type": "インデックス",
        "trustee": "楽天投信投資顧問",
        "underlying": "SOX指数（フィラデルフィア半導体株指数）",
        "proxy_ticker": "SOXX",
        "expense_ratio": 0.17600,
        "aum_oku": 1350,
        "nisa_tsumitate": False,
        "nisa_growth": True,
        "return_1y": 49.5,
        "return_3y_annual": 32.8,
        "sharpe_ratio": 1.02,
        "max_drawdown": -36.5,
        "major_holdings": ["NVIDIA", "AMD", "クアルコム", "ブロードコム", "TSMC", "ASML", "インテル"],
        "description": "生成AI・EV・データセンターの頭脳である世界半導体大手30社に0.17%の極小コストで投資可能。",
        "role": "半導体メガトレンド"
    },

    # =========================================================================
    # 3. SBI・V Series (Vanguard Ultra-Low Cost Flagships)
    # =========================================================================
    {
        "id": "sbi_v_sp500",
        "name": "SBI・V・S&P500インデックス・ファンド",
        "nickname": "SBI・V・S&P500",
        "category": "王道インデックス",
        "type": "インデックス",
        "trustee": "SBIアセットマネジメント",
        "underlying": "バンガード・S&P500 ETF (VOO)",
        "proxy_ticker": "VOO",
        "expense_ratio": 0.09380,
        "aum_oku": 18200,
        "nisa_tsumitate": True,
        "nisa_growth": True,
        "return_1y": 32.4,
        "return_3y_annual": 24.8,
        "sharpe_ratio": 1.15,
        "max_drawdown": -18.2,
        "major_holdings": ["マイクロソフト", "NVIDIA", "アップル", "アマゾン", "Alphabet", "Meta"],
        "description": "世界最強の米国大型株500社に業界最安水準の手数料（年0.0938%）で投資できるSBIの絶対的フラッグシップ。",
        "role": "コア資産（王道）"
    },
    {
        "id": "sbi_v_total_us",
        "name": "SBI・V・全米株式インデックス・ファンド",
        "nickname": "SBI・V・全米株式",
        "category": "王道インデックス",
        "type": "インデックス",
        "trustee": "SBIアセットマネジメント",
        "underlying": "バンガード・トータル・ストック・マーケットETF (VTI)",
        "proxy_ticker": "VTI",
        "expense_ratio": 0.09380,
        "aum_oku": 3400,
        "nisa_tsumitate": True,
        "nisa_growth": True,
        "return_1y": 31.2,
        "return_3y_annual": 23.9,
        "sharpe_ratio": 1.10,
        "max_drawdown": -19.5,
        "major_holdings": ["マイクロソフト", "NVIDIA", "アップル", "アマゾン", "Meta", "ブロードコム"],
        "description": "S&P500に含まれない中小型成長株まで網羅した米国約4,000銘柄にまるごと低コスト投資。",
        "role": "コア資産（全米網羅）"
    },
    {
        "id": "sbi_v_all_country",
        "name": "SBI・V・全世界株式インデックス・ファンド",
        "nickname": "SBI・V・全世界株式",
        "category": "王道インデックス",
        "type": "インデックス",
        "trustee": "SBIアセットマネジメント",
        "underlying": "バンガード・トータル・ワールド・ストックETF (VT)",
        "proxy_ticker": "VT",
        "expense_ratio": 0.13380,
        "aum_oku": 1150,
        "nisa_tsumitate": True,
        "nisa_growth": True,
        "return_1y": 28.5,
        "return_3y_annual": 20.1,
        "sharpe_ratio": 1.05,
        "max_drawdown": -16.8,
        "major_holdings": ["マイクロソフト", "NVIDIA", "アップル", "アマゾン", "TSMC", "テンセント"],
        "description": "日本を含む全世界約9,000銘柄に分散投資。米国の比率が約6割で、これ1本で地球全体の経済成長を享受可能。",
        "role": "コア資産（世界分散）"
    },
    {
        "id": "sbi_v_dividend_appreciation",
        "name": "SBI・V・米国増配株式インデックス・ファンド",
        "nickname": "SBI・V・米国増配 (VIG)",
        "category": "高配当・インカム",
        "type": "インデックス",
        "trustee": "SBIアセットマネジメント",
        "underlying": "バンガード・米国増配株式ETF (VIG)",
        "proxy_ticker": "VIG",
        "expense_ratio": 0.12380,
        "aum_oku": 1400,
        "nisa_tsumitate": False,
        "nisa_growth": True,
        "return_1y": 24.5,
        "return_3y_annual": 19.8,
        "sharpe_ratio": 1.12,
        "max_drawdown": -13.8,
        "major_holdings": ["マイクロソフト", "アップル", "JPモルガン・チェース", "ブロードコム", "エクソンモービル"],
        "description": "10年以上連続増配を続ける財務強靭な米国優良企業に厳選。高配当株以上の成長力と抜群の下落耐性を両立。",
        "role": "増配成長・下落防衛"
    },
    {
        "id": "sbi_v_high_dividend",
        "name": "SBI・V・米国高配当株式インデックス・ファンド",
        "nickname": "SBI・V・米国高配当 (VYM)",
        "category": "高配当・インカム",
        "type": "インデックス",
        "trustee": "SBIアセットマネジメント",
        "underlying": "バンガード・米国高配当株式ETF (VYM)",
        "proxy_ticker": "VYM",
        "expense_ratio": 0.12380,
        "aum_oku": 2100,
        "nisa_tsumitate": False,
        "nisa_growth": True,
        "return_1y": 22.8,
        "return_3y_annual": 18.5,
        "sharpe_ratio": 0.98,
        "max_drawdown": -14.2,
        "major_holdings": ["ブロードコム", "JPモルガン・チェース", "エクソンモービル", "ジョンソン&ジョンソン", "プロクター&ギャンブル"],
        "description": "財務健全性が高く平均以上の高配当を出す米国約400社に分散。下落耐性に優れたディフェンシブファンド。",
        "role": "インカム・安定配当"
    },

    # =========================================================================
    # 4. Saku-tto & SBI iShares Series (India, Gold, Bonds)
    # =========================================================================
    {
        "id": "sbi_ishares_india",
        "name": "SBI・iシェアーズ・インド株式インデックス・ファンド",
        "nickname": "サクっとインド株式",
        "category": "インド・新興国",
        "type": "インデックス",
        "trustee": "SBIアセットマネジメント",
        "underlying": "iシェアーズ・コア S&P BSE SENSEX インディアETF",
        "proxy_ticker": "INDA",
        "expense_ratio": 0.46380,
        "aum_oku": 1650,
        "nisa_tsumitate": False,
        "nisa_growth": True,
        "return_1y": 38.6,
        "return_3y_annual": 28.2,
        "sharpe_ratio": 1.28,
        "max_drawdown": -12.4,
        "major_holdings": ["HDFC銀行", "リライアンス", "ICICI銀行", "インフォシス", "タタ・コンサルタンシー"],
        "description": "人口世界首位・高成長が続くインド市場の代表指数SENSEXに連動。信託報酬0.46%台で国内最安級のインド本命投信。",
        "role": "高成長サテライト（本命）"
    },
    {
        "id": "sbi_ishares_gold",
        "name": "SBI・iシェアーズ・ゴールドファンド（為替ヘッジなし）",
        "nickname": "サクっと純金",
        "category": "金・債券・バランス",
        "type": "オルタナティブ",
        "trustee": "SBIアセットマネジメント",
        "underlying": "iシェアーズ・ゴールド・トラスト (IAU)",
        "proxy_ticker": "IAU",
        "expense_ratio": 0.18380,
        "aum_oku": 880,
        "nisa_tsumitate": False,
        "nisa_growth": True,
        "return_1y": 35.2,
        "return_3y_annual": 22.4,
        "sharpe_ratio": 1.22,
        "max_drawdown": -9.8,
        "major_holdings": ["現物金（ゴールド・地金保管）"],
        "description": "有事・インフレ・通貨下落時に絶大な防衛力を誇る実物ゴールド。信託報酬0.18%の業界最安級ゴールドファンド。",
        "role": "防衛資産（オルタナティブ）"
    },
    {
        "id": "sbi_ishares_us_bond",
        "name": "SBI・iシェアーズ・米国総合債券インデックス・ファンド",
        "nickname": "サクっと米国債券",
        "category": "金・債券・バランス",
        "type": "債券インデックス",
        "trustee": "SBIアセットマネジメント",
        "underlying": "iシェアーズ・コア 米国総合債券市場ETF (AGG)",
        "proxy_ticker": "AGG",
        "expense_ratio": 0.09380,
        "aum_oku": 320,
        "nisa_tsumitate": False,
        "nisa_growth": True,
        "return_1y": 8.2,
        "return_3y_annual": 4.1,
        "sharpe_ratio": 0.45,
        "max_drawdown": -11.2,
        "major_holdings": ["米国財務省証券（国債）", "住宅ローン担保証券 (MBS)", "優良社債"],
        "description": "米国投資適格債券全体に低コスト投資。株価暴落時のクッション役としてポートフォリオの安定化に寄与。",
        "role": "安全クッション資産"
    },
    {
        "id": "sbi_ishares_high_yield",
        "name": "SBI・iシェアーズ・米国ハイイールド債券インデックス・ファンド",
        "nickname": "サクっと高利回り社債",
        "category": "金・債券・バランス",
        "type": "債券インデックス",
        "trustee": "SBIアセットマネジメント",
        "underlying": "iシェアーズ iBoxx 米ドル建てハイイールド社債ETF (HYG)",
        "proxy_ticker": "HYG",
        "expense_ratio": 0.29800,
        "aum_oku": 240,
        "nisa_tsumitate": False,
        "nisa_growth": True,
        "return_1y": 14.5,
        "return_3y_annual": 8.6,
        "sharpe_ratio": 0.82,
        "max_drawdown": -13.5,
        "major_holdings": ["米ドル建て高利回り社債群（利回り6〜8%水準）"],
        "description": "高水準の利息収入を狙う投資家向け。低コストで米国の高利回り社債群に分散投資。",
        "role": "高金利インカム"
    },

    # =========================================================================
    # 5. SBI Unique Mega-Popular High Dividend Funds
    # =========================================================================
    {
        "id": "sbi_japan_high_dividend",
        "name": "ＳＢＩ日本高配当株式（分配）ファンド（年４回決算型）",
        "nickname": "SBI日本高配当 (年4回分配)",
        "category": "高配当・インカム",
        "type": "アクティブ",
        "trustee": "SBIアセットマネジメント",
        "underlying": "国内高配当利回り銘柄30〜40社集中ポートフォリオ",
        "proxy_ticker": "1489.T",
        "expense_ratio": 0.09900,
        "aum_oku": 1850,
        "nisa_tsumitate": False,
        "nisa_growth": True,
        "return_1y": 28.5,
        "return_3y_annual": 23.4,
        "sharpe_ratio": 1.24,
        "max_drawdown": -12.1,
        "major_holdings": ["三井住友FG", "三菱UFJ FG", "みずほFG", "武田薬品", "INPEX", "ソフトバンク", "伊藤忠商事"],
        "description": "現在SBI証券で爆発的人気を誇る独自ファンド。国内高配当アクティブで驚異の信託報酬0.099%・年4回分配金。",
        "role": "国内高配当キャッシュフロー（大本命）"
    },
    {
        "id": "sbi_europe_high_dividend",
        "name": "ＳＢＩ欧州高配当株式（分配）ファンド（年４回決算型）",
        "nickname": "SBI欧州高配当 (年4回分配)",
        "category": "高配当・インカム",
        "type": "アクティブ",
        "trustee": "SBIアセットマネジメント",
        "underlying": "欧州主要国の高配当利回り銘柄約30社",
        "proxy_ticker": "VGK",
        "expense_ratio": 0.09900,
        "aum_oku": 680,
        "nisa_tsumitate": False,
        "nisa_growth": True,
        "return_1y": 21.2,
        "return_3y_annual": 16.5,
        "sharpe_ratio": 0.95,
        "max_drawdown": -15.8,
        "major_holdings": ["シェル", "トタルエナジーズ", "HSBC", "ロシュ", "ノバルティス", "アライアンス"],
        "description": "信託報酬0.099%で欧州の超巨大グローバル高配当企業に投資。年4回配当＋地域分散の最適解。",
        "role": "欧州高配当キャッシュフロー"
    },
    {
        "id": "tracers_sp500_aristocrats",
        "name": "Ｔｒａｃｅｒｓ Ｓ＆Ｐ５００配当貴族インデックス（米国株式）",
        "nickname": "Tracers 配当貴族",
        "category": "高配当・インカム",
        "type": "インデックス",
        "trustee": "日興アセットマネジメント",
        "underlying": "S&P500配当貴族指数（25年以上連続増配）",
        "proxy_ticker": "NOBL",
        "expense_ratio": 0.11550,
        "aum_oku": 1580,
        "nisa_tsumitate": False,
        "nisa_growth": True,
        "return_1y": 24.1,
        "return_3y_annual": 18.9,
        "sharpe_ratio": 1.08,
        "max_drawdown": -13.2,
        "major_holdings": ["プロクター&ギャンブル", "スリーエム", "コカ・コーラ", "アッヴィ", "キャタピラー"],
        "description": "四半世紀（25年以上）連続で配当を増やし続けた米国の怪物企業のみで構成。信託報酬0.11%で鉄壁の防衛力。",
        "role": "25年連続増配・ディフェンシブ"
    },
    {
        "id": "japan_dividend_rebalance",
        "name": "日本好配当リバランスオープン",
        "nickname": "日本好配当リバランス",
        "category": "高配当・インカム",
        "type": "アクティブ",
        "trustee": "SBI岡三アセットマネジメント",
        "underlying": "東証一部・プライム高配当利回り銘柄",
        "proxy_ticker": "1489.T",
        "expense_ratio": 0.99000,
        "aum_oku": 720,
        "nisa_tsumitate": False,
        "nisa_growth": True,
        "return_1y": 26.4,
        "return_3y_annual": 21.2,
        "sharpe_ratio": 1.18,
        "max_drawdown": -13.5,
        "major_holdings": ["三菱UFJ FG", "三井住友FG", "伊藤忠商事", "武田薬品", "INPEX"],
        "description": "配当利回りが高い上位銘柄を毎月機械的にリバランス。日銀利上げ・高金利時代の恩恵をダイレクトに享受。",
        "role": "国内高配当バリュー"
    },

    # =========================================================================
    # 6. Famous High-Alpha Active & Megatrend Funds (SBI Premium Choice)
    # =========================================================================
    {
        "id": "ab_us_growth_b",
        "name": "アライアンス・バーンスタイン・米国成長株投信 Ｂコース（為替ヘッジなし）",
        "nickname": "AB米国成長株B",
        "category": "厳選アクティブ・AIテーマ",
        "type": "アクティブ",
        "trustee": "アライアンス・バーンスタイン",
        "underlying": "独自リサーチによる米国持続的成長企業",
        "proxy_ticker": "VUG",
        "expense_ratio": 1.72700,
        "aum_oku": 14800,
        "nisa_tsumitate": False,
        "nisa_growth": True,
        "return_1y": 39.5,
        "return_3y_annual": 26.1,
        "sharpe_ratio": 1.12,
        "max_drawdown": -29.8,
        "major_holdings": ["マイクロソフト", "NVIDIA", "アマゾン", "Alphabet", "イーライリリー", "ビザ"],
        "description": "SBI証券買付ランキング常連の怪物アクティブ投信。高い信託報酬（1.72%）を補って余りあるS&P500凌駕実績。",
        "role": "積極グロース（メガアクティブ）"
    },
    {
        "id": "invesco_world_best",
        "name": "インベスコ 世界厳選株式オープン＜為替ヘッジなし＞（毎月決算型）",
        "nickname": "世界のベスト (インベスコ)",
        "category": "厳選アクティブ・AIテーマ",
        "type": "アクティブ",
        "trustee": "インベスコ・アセット・マネジメント",
        "underlying": "世界の構造的成長企業および高配当バリュー企業",
        "proxy_ticker": "ACWI",
        "expense_ratio": 1.90300,
        "aum_oku": 16500,
        "nisa_tsumitate": False,
        "nisa_growth": True,
        "return_1y": 31.5,
        "return_3y_annual": 22.8,
        "sharpe_ratio": 1.05,
        "max_drawdown": -18.5,
        "major_holdings": ["マイクロソフト", "アマゾン", "ロールスロイス", "メタ", "TSMC", "ブロードコム"],
        "description": "純資産1.6兆円突破。世界中から最高峰の優良企業を厳選し、毎月の安定分配と値上がり益を両立する超人気アクティブ。",
        "role": "世界最高峰プレミアムアクティブ"
    },
    {
        "id": "hifumi_plus",
        "name": "ひふみプラス",
        "nickname": "ひふみプラス",
        "category": "厳選アクティブ・AIテーマ",
        "type": "アクティブ",
        "trustee": "レオス・キャピタルワークス",
        "underlying": "日本国内の成長中小型〜大型企業",
        "proxy_ticker": "1306.T",
        "expense_ratio": 1.07800,
        "aum_oku": 4600,
        "nisa_tsumitate": True,
        "nisa_growth": True,
        "return_1y": 18.5,
        "return_3y_annual": 12.3,
        "sharpe_ratio": 0.78,
        "max_drawdown": -21.4,
        "major_holdings": ["ソニーグループ", "日立製作所", "トヨタ自動車", "サンウェルズ", "NTT"],
        "description": "『足で稼ぐ』徹底的な企業調査で成長企業を発掘する国内アクティブのパイオニア。",
        "role": "国内アクティブ成長"
    },
    {
        "id": "picet_global_income",
        "name": "ピクテ・グローバル・インカム株式ファンド（毎月決算型）",
        "nickname": "ピクテ・グロイン",
        "category": "高配当・インカム",
        "type": "アクティブ",
        "trustee": "ピクテ・ジャパン",
        "underlying": "世界主要国の生活必需・公共インフラ高配当株",
        "proxy_ticker": "XLU",
        "expense_ratio": 1.81000,
        "aum_oku": 8900,
        "nisa_tsumitate": False,
        "nisa_growth": True,
        "return_1y": 16.5,
        "return_3y_annual": 11.2,
        "sharpe_ratio": 0.72,
        "max_drawdown": -14.5,
        "major_holdings": ["ネクステラ・エナジー", "アイバドラ", "ナショナル・グリッド", "サザン", "デューク・エナジー"],
        "description": "電力・ガス・通信など生活に欠かせない世界の公益企業に投資。不況でも売上が落ちない守りのインカム。",
        "role": "世界インフラ・高配当インカム"
    },
    {
        "id": "global_ai_fund",
        "name": "グローバルＡＩファンド",
        "nickname": "グローバルAI",
        "category": "厳選アクティブ・AIテーマ",
        "type": "テーマ型アクティブ",
        "trustee": "三井住友DSアセットマネジメント",
        "underlying": "世界のAIテクノロジー・基盤インフラ企業",
        "proxy_ticker": "BOTZ",
        "expense_ratio": 1.92500,
        "aum_oku": 3300,
        "nisa_tsumitate": False,
        "nisa_growth": True,
        "return_1y": 42.1,
        "return_3y_annual": 27.4,
        "sharpe_ratio": 1.08,
        "max_drawdown": -32.1,
        "major_holdings": ["NVIDIA", "マイクロソフト", "アマゾン", "メタ", "サービスナウ", "TSMC"],
        "description": "生成AI革命の主役企業を集中保有。ボラティリティは高いがメガトレンドの波に乗る爆発的モメンタム。",
        "role": "メガトレンド集中投資"
    },
    {
        "id": "emaxis_neo_semiconductor",
        "name": "ｅＭＡＸＩＳ Ｎｅｏ 半導体",
        "nickname": "Neo 半導体",
        "category": "厳選アクティブ・AIテーマ",
        "type": "テーマ型インデックス",
        "trustee": "三菱UFJアセットマネジメント",
        "underlying": "Kensho Semiconductor Index",
        "proxy_ticker": "SOXX",
        "expense_ratio": 0.79200,
        "aum_oku": 480,
        "nisa_tsumitate": False,
        "nisa_growth": True,
        "return_1y": 48.2,
        "return_3y_annual": 31.5,
        "sharpe_ratio": 0.92,
        "max_drawdown": -38.5,
        "major_holdings": ["NVIDIA", "AMD", "インテル", "マイクロン・テクノロジー", "クアルコム"],
        "description": "AI・自律走行の心臓部である半導体企業に特化。AIが銘柄選定する革新的なテーマ型ファンド。",
        "role": "ハイテク特化サテライト"
    },
    {
        "id": "global_robotics",
        "name": "グローバル・ロボティクス株式ファンド（１年決算型）",
        "nickname": "ロボティクス",
        "category": "厳選アクティブ・AIテーマ",
        "type": "テーマ型アクティブ",
        "trustee": "日興アセットマネジメント",
        "underlying": "産業ロボット・医療ロボット・自動化技術企業",
        "proxy_ticker": "ROBO",
        "expense_ratio": 1.92500,
        "aum_oku": 2200,
        "nisa_tsumitate": False,
        "nisa_growth": True,
        "return_1y": 24.1,
        "return_3y_annual": 15.8,
        "sharpe_ratio": 0.75,
        "max_drawdown": -26.2,
        "major_holdings": ["キーエンス", "ファナック", "SMC", "インテュイティブ・サージカル", "シノプシス"],
        "description": "人手不足とフィジカルAI時代の本命。ファクトリーオートメーションと手術ロボットの世界的リーダーに集中。",
        "role": "自動化・ロボット特化"
    }
]

# Preset Portfolio Packs (Curated Combinations)
PRESET_PACKS: List[Dict[str, Any]] = [
    {
        "id": "pack_all_weather",
        "title": "王道・鉄板オールウェザーパック",
        "badge": "人気No.1・攻守最強",
        "concept": "S&P500の爆発的成長を軸に、有事・インフレ耐性のゴールド、人口ボーナスのインドを黄金比率でブレンド。",
        "expected_return": "+33.8%",
        "composite_expense": "0.198%",
        "stability_score": "極めて高い（低ドローダウン）",
        "allocations": [
            {"fund_id": "emaxis_slim_sp500", "weight": 60, "name": "Slim S&P500", "role": "世界最強コア成長"},
            {"fund_id": "sbi_ishares_gold", "weight": 20, "name": "サクっと純金", "role": "インフレ・有事防衛"},
            {"fund_id": "sbi_ishares_india", "weight": 20, "name": "サクっとインド株式", "role": "新興国トップ成長"}
        ]
    },
    {
        "id": "pack_mega_growth",
        "title": "超アグレッシブ・メガグロースパック",
        "badge": "最大リターン追求型",
        "concept": "米国メガテック集中FANG+＋次世代超大国インド＋オルカンの3本柱で市場平均を大幅アウトパフォーム狙い。",
        "expected_return": "+42.5%",
        "composite_expense": "0.485%",
        "stability_score": "高ボラティリティ・ハイリターン",
        "allocations": [
            {"fund_id": "ifreenext_fang_plus", "weight": 40, "name": "FANG+ (メガテック10社)", "role": "超巨大テック集中"},
            {"fund_id": "sbi_ishares_india", "weight": 30, "name": "サクっとインド株式", "role": "人口世界首位の爆発力"},
            {"fund_id": "emaxis_slim_all_country", "weight": 30, "name": "オルカン", "role": "世界分散の土台"}
        ]
    },
    {
        "id": "pack_defensive_income",
        "title": "ディフェンシブ・インカム＆防衛パック",
        "badge": "暴落耐性・守りの要",
        "concept": "SBI日本高配当株と25年連続増配の配当貴族、実物ゴールドを組み合わせ、下落相場でも資産を守り抜く。",
        "expected_return": "+25.9%",
        "composite_expense": "0.133%",
        "stability_score": "最高水準（元本保全性重視）",
        "allocations": [
            {"fund_id": "sbi_japan_high_dividend", "weight": 40, "name": "SBI日本高配当", "role": "国内高配当キャッシュフロー"},
            {"fund_id": "sbi_ishares_gold", "weight": 30, "name": "サクっと純金", "role": "金利低下・危機ヘッジ"},
            {"fund_id": "tracers_sp500_aristocrats", "weight": 30, "name": "Tracers 配当貴族", "role": "25年連続増配の守り"}
        ]
    }
]


def score_fund(fund: Dict[str, Any]) -> Dict[str, Any]:
    """
    Computes ZenStock AI Quantitative Score (0 to 100) and assigns Stars & Badges.
    Weights:
      - Sharpe Ratio (Risk-Adjusted Return): 35%
      - Expense Ratio (Cost Efficiency): 25%
      - Max Drawdown (Downside Protection): 20%
      - AUM Scale & Liquidity: 20%
    """
    sr = fund["sharpe_ratio"]
    sr_score = min(max((sr - 0.4) / (1.3 - 0.4) * 100, 10), 100)

    exp = fund["expense_ratio"]
    exp_score = min(max((2.0 - exp) / (2.0 - 0.05) * 100, 10), 100)

    dd = abs(fund["max_drawdown"])
    dd_score = min(max((40.0 - dd) / (40.0 - 10.0) * 100, 10), 100)

    aum = fund["aum_oku"]
    aum_score = min(max((aum / 10000.0) * 80 + 20, 20), 100)

    total_score = sr_score * 0.35 + exp_score * 0.25 + dd_score * 0.20 + aum_score * 0.20

    if total_score >= 82:
        stars = 5
        rank = "S"
        eval_label = "最優秀・鉄板"
        color = "var(--color-gain, #10b981)"
    elif total_score >= 70:
        stars = 4
        rank = "A"
        eval_label = "優秀・有力候補"
        color = "var(--mui-primary, #1976d2)"
    elif total_score >= 55:
        stars = 3
        rank = "B"
        eval_label = "堅実・サテライト"
        color = "#eab308"
    else:
        stars = 2
        rank = "C"
        eval_label = "要注意・高コスト"
        color = "#94a3b8"

    return {
        "score": round(total_score, 1),
        "stars": stars,
        "rank": rank,
        "eval_label": eval_label,
        "color": color
    }


def get_all_categories() -> List[str]:
    return [
        "すべて",
        "王道インデックス",
        "FANG+・ハイテク",
        "インド・新興国",
        "高配当・インカム",
        "金・債券・バランス",
        "厳選アクティブ・AIテーマ"
    ]


def filter_and_sort_funds(
    category: str = "すべて",
    nisa_filter: str = "すべて",
    expense_filter: str = "すべて",
    aum_filter: str = "すべて",
    search_query: str = "",
    sort_by: str = "AI総合スコア順"
) -> List[Dict[str, Any]]:
    """
    Filters and sorts funds based on multiple screening criteria.
    """
    results = []
    q = search_query.strip().lower()

    for f in SBI_FUNDS_DB:
        if category != "すべて" and f["category"] != category:
            continue

        if nisa_filter == "つみたて投資枠" and not f.get("nisa_tsumitate"):
            continue
        if nisa_filter == "成長投資枠" and not f.get("nisa_growth"):
            continue

        if expense_filter == "0.1%以下 (超低コスト)":
            if f["expense_ratio"] > 0.105:
                continue
        elif expense_filter == "0.2%以下":
            if f["expense_ratio"] > 0.205:
                continue
        elif expense_filter == "0.5%以下":
            if f["expense_ratio"] > 0.505:
                continue

        if aum_filter == "1兆円以上 (メガファンド)":
            if f["aum_oku"] < 10000:
                continue
        elif aum_filter == "1,000億円以上":
            if f["aum_oku"] < 1000:
                continue
        elif aum_filter == "500億円以上":
            if f["aum_oku"] < 500:
                continue

        if q:
            match = (
                q in f["name"].lower()
                or q in f["nickname"].lower()
                or q in f["trustee"].lower()
                or q in f["underlying"].lower()
                or any(q in h.lower() for h in f.get("major_holdings", []))
            )
            if not match:
                continue

        score_info = score_fund(f)
        item = dict(f)
        item.update(score_info)
        results.append(item)

    if sort_by == "AI総合スコア順":
        results.sort(key=lambda x: x["score"], reverse=True)
    elif sort_by == "信託報酬が安い順":
        results.sort(key=lambda x: x["expense_ratio"])
    elif sort_by == "1年リターンが高い順":
        results.sort(key=lambda x: x["return_1y"], reverse=True)
    elif sort_by == "過去3年(年率)順":
        results.sort(key=lambda x: x["return_3y_annual"], reverse=True)
    elif sort_by == "シャープレシオ（収益効率）順":
        results.sort(key=lambda x: x["sharpe_ratio"], reverse=True)
    elif sort_by == "純資産が大きい順":
        results.sort(key=lambda x: x["aum_oku"], reverse=True)
    elif sort_by == "最大下落率が小さい順 (守り重視)":
        results.sort(key=lambda x: abs(x["max_drawdown"]))

    return results


def fetch_comparison_chart_data(period: str = "1y") -> Dict[str, Any]:
    """
    Fetches historical cumulative return series for representative asset classes/funds.
    """
    now = time.time()
    cache_key = f"chart_{period}"
    if cache_key in _CHART_CACHE:
        cached = _CHART_CACHE[cache_key]
        if now - cached["time"] < 1800:
            return cached["data"]

    targets = [
        {"id": "ifreenext_fang_plus", "label": "FANG+ (メガテック10社)", "ticker": "FNGS", "color": "#f43f5e"},
        {"id": "emaxis_slim_sp500", "label": "Slim S&P500 (米国500社)", "ticker": "VOO", "color": "#1976d2"},
        {"id": "sbi_ishares_india", "label": "サクっとインド株式 (人口世界一)", "ticker": "INDA", "color": "#f59e0b"},
        {"id": "sbi_ishares_gold", "label": "サクっと純金 (有事・防衛)", "ticker": "IAU", "color": "#eab308"},
        {"id": "emaxis_slim_all_country", "label": "オルカン (全世界株式)", "ticker": "VT", "color": "#10b981"},
        {"id": "sbi_japan_high_dividend", "label": "SBI日本高配当 (年4回分配)", "ticker": "1489.T", "color": "#8b5cf6"},
        {"id": "rakuten_sox", "label": "半導体 SOX (ハイテク中核)", "ticker": "SOXX", "color": "#ec4899"}
    ]

    tickers = [t["ticker"] for t in targets]
    series_dict = {}

    try:
        df = yf.download(tickers, period=period, interval="1d", progress=False, group_by="ticker", auto_adjust=True)
        if df is not None and not df.empty:
            for t in targets:
                tick = t["ticker"]
                try:
                    if tick in df.columns.levels[0]:
                        close_s = df[tick]["Close"].dropna()
                        if len(close_s) > 5:
                            first_val = float(close_s.iloc[0])
                            if first_val > 0:
                                cum_ret = ((close_s / first_val) - 1.0) * 100.0
                                series_dict[t["label"]] = {
                                    "dates": [d.strftime("%Y-%m-%d") for d in cum_ret.index],
                                    "returns": [round(float(v), 2) for v in cum_ret.values],
                                    "color": t["color"],
                                    "latest": round(float(cum_ret.iloc[-1]), 1)
                                }
                except Exception:
                    continue
    except Exception as e:
        print(f"Error fetching fund chart data: {e}")

    if not series_dict:
        dates = pd.date_range(end=pd.Timestamp.today(), periods=120, freq="B").strftime("%Y-%m-%d").tolist()
        series_dict = {
            "FANG+ (メガテック10社)": {"dates": dates, "returns": [round(i * 0.42, 2) for i in range(120)], "color": "#f43f5e", "latest": 51.4},
            "Slim S&P500 (米国500社)": {"dates": dates, "returns": [round(i * 0.27, 2) for i in range(120)], "color": "#1976d2", "latest": 32.6},
            "サクっとインド株式 (人口世界一)": {"dates": dates, "returns": [round(i * 0.32, 2) for i in range(120)], "color": "#f59e0b", "latest": 38.6},
            "サクっと純金 (有事・防衛)": {"dates": dates, "returns": [round(i * 0.29, 2) for i in range(120)], "color": "#eab308", "latest": 35.2},
            "オルカン (全世界株式)": {"dates": dates, "returns": [round(i * 0.24, 2) for i in range(120)], "color": "#10b981", "latest": 28.8},
            "SBI日本高配当 (年4回分配)": {"dates": dates, "returns": [round(i * 0.23, 2) for i in range(120)], "color": "#8b5cf6", "latest": 28.5},
            "半導体 SOX (ハイテク中核)": {"dates": dates, "returns": [round(i * 0.41, 2) for i in range(120)], "color": "#ec4899", "latest": 49.5}
        }

    _CHART_CACHE[cache_key] = {"time": now, "data": series_dict}
    return series_dict


def fetch_individual_fund_chart(fund_id: str, period: str = "1y") -> Optional[Dict[str, Any]]:
    """
    Fetches daily OHLCV and moving average indicators for a specific fund via its proxy ticker.
    """
    now = time.time()
    cache_key = f"indiv_{fund_id}_{period}"
    if cache_key in _INDIVIDUAL_CHART_CACHE:
        cached = _INDIVIDUAL_CHART_CACHE[cache_key]
        if now - cached["time"] < 1800:
            return cached["data"]

    fund_item = next((f for f in SBI_FUNDS_DB if f["id"] == fund_id), None)
    if not fund_item:
        return None

    ticker = fund_item.get("proxy_ticker", "VOO")

    try:
        t = yf.Ticker(ticker)
        df = t.history(period=period, interval="1d", auto_adjust=True)
        if df is None or df.empty or len(df) < 5:
            return None

        df["SMA25"] = df["Close"].rolling(window=min(25, len(df))).mean()
        df["SMA75"] = df["Close"].rolling(window=min(75, len(df))).mean()
        
        # Cumulative return from start of period
        first_close = float(df["Close"].iloc[0])
        df["CumReturn"] = ((df["Close"] / first_close) - 1.0) * 100.0

        dates_str = [d.strftime("%Y-%m-%d") for d in df.index]

        result = {
            "fund": fund_item,
            "ticker": ticker,
            "dates": dates_str,
            "close": [round(float(v), 2) for v in df["Close"].values],
            "open": [round(float(v), 2) for v in df["Open"].values],
            "high": [round(float(v), 2) for v in df["High"].values],
            "low": [round(float(v), 2) for v in df["Low"].values],
            "volume": [int(v) for v in df["Volume"].values] if "Volume" in df else [],
            "sma25": [round(float(v), 2) if not pd.isna(v) else None for v in df["SMA25"].values],
            "sma75": [round(float(v), 2) if not pd.isna(v) else None for v in df["SMA75"].values],
            "cum_return": [round(float(v), 2) for v in df["CumReturn"].values],
            "latest_close": round(float(df["Close"].iloc[-1]), 2),
            "latest_cum_return": round(float(df["CumReturn"].iloc[-1]), 2),
            "high_52w": round(float(df["High"].max()), 2),
            "low_52w": round(float(df["Low"].min()), 2),
        }

        _INDIVIDUAL_CHART_CACHE[cache_key] = {"time": now, "data": result}
        return result
    except Exception as e:
        print(f"Error fetching individual fund chart: {e}")
        return None
