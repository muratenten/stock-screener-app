"""
SBI Investment Trust Packs Intelligence & Screener Service
Provides comprehensive database, quantitative scoring (Sharpe, Expense, Drawdown),
filtering, and preset portfolio pack builder for SBI Securities funds.
Includes real-time proxy ETF chart fetching via yfinance for visual performance comparisons.
"""

import time
from typing import List, Dict, Any, Optional
import pandas as pd
import yfinance as yf

# In-memory cache for chart series (TTL = 30 minutes)
_CHART_CACHE: Dict[str, Any] = {}

# Master Database of SBI Popular Investment Trusts & Packs
SBI_FUNDS_DB: List[Dict[str, Any]] = [
    # 1. SBI・V Series (Vanguard Ultra-Low Cost Core Index)
    {
        "id": "sbi_v_sp500",
        "name": "SBI・V・S&P500インデックス・ファンド",
        "nickname": "SBI・V・S&P500",
        "category": "王道インデックス",
        "type": "インデックス",
        "trustee": "SBIアセットマネジメント",
        "underlying": "バンガード・S&P500 ETF (VOO)",
        "proxy_ticker": "VOO",
        "expense_ratio": 0.0938,
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
        "id": "sbi_v_all_country",
        "name": "SBI・V・全世界株式インデックス・ファンド",
        "nickname": "SBI・V・雪だるまオルカン",
        "category": "王道インデックス",
        "type": "インデックス",
        "trustee": "SBIアセットマネジメント",
        "underlying": "バンガード・トータル・ワールド・ストックETF (VT)",
        "proxy_ticker": "VT",
        "expense_ratio": 0.1338,
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
        "id": "sbi_v_total_us",
        "name": "SBI・V・全米株式インデックス・ファンド",
        "nickname": "SBI・V・全米株式",
        "category": "王道インデックス",
        "type": "インデックス",
        "trustee": "SBIアセットマネジメント",
        "underlying": "バンガード・トータル・ストック・マーケットETF (VTI)",
        "proxy_ticker": "VTI",
        "expense_ratio": 0.0938,
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
        "id": "sbi_v_high_dividend",
        "name": "SBI・V・米国高配当株式インデックス・ファンド",
        "nickname": "SBI・V・米国高配当",
        "category": "高配当・インカム",
        "type": "インデックス",
        "trustee": "SBIアセットマネジメント",
        "underlying": "バンガード・米国高配当株式ETF (VYM)",
        "proxy_ticker": "VYM",
        "expense_ratio": 0.1238,
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
    {
        "id": "sbi_v_developed_ex_us",
        "name": "SBI・V・先進国株式（除く米国）インデックス・ファンド",
        "nickname": "SBI・V・欧州先進国",
        "category": "王道インデックス",
        "type": "インデックス",
        "trustee": "SBIアセットマネジメント",
        "underlying": "バンガード・FTSE先進国市場（除く米国）ETF (VEA)",
        "proxy_ticker": "VEA",
        "expense_ratio": 0.1138,
        "aum_oku": 280,
        "nisa_tsumitate": True,
        "nisa_growth": True,
        "return_1y": 18.2,
        "return_3y_annual": 14.1,
        "sharpe_ratio": 0.85,
        "max_drawdown": -19.1,
        "major_holdings": ["ノボ・ノルディスク", "ASML", "ネスレ", "シェル", "LVMH"],
        "description": "米国株偏重を避けたい投資家向け。欧州・カナダ・オーストラリア・日本などの先進国優良企業を厳選。",
        "role": "地域分散サテライト"
    },
    {
        "id": "sbi_v_emerging",
        "name": "SBI・V・新興国株式インデックス・ファンド",
        "nickname": "SBI・V・新興国",
        "category": "インド・新興国",
        "type": "インデックス",
        "trustee": "SBIアセットマネジメント",
        "underlying": "バンガード・FTSEエマージング・マーケッツETF (VWO)",
        "proxy_ticker": "VWO",
        "expense_ratio": 0.1438,
        "aum_oku": 360,
        "nisa_tsumitate": True,
        "nisa_growth": True,
        "return_1y": 14.2,
        "return_3y_annual": 7.5,
        "sharpe_ratio": 0.62,
        "max_drawdown": -24.5,
        "major_holdings": ["TSMC", "テンセント", "アリババ", "リライアンス・インダストリーズ", "サムスン電子"],
        "description": "中国、インド、台湾、ブラジルなど新興国全体のメガ成長を低コストでキャッチアップ。",
        "role": "新興国サテライト"
    },

    # 2. SBI・iShares Series (BlackRock Co-operation & Saku-tto)
    {
        "id": "sbi_ishares_india",
        "name": "SBI・iシェアーズ・インド株式インデックス・ファンド",
        "nickname": "サクっとインド株式",
        "category": "インド・新興国",
        "type": "インデックス",
        "trustee": "SBIアセットマネジメント",
        "underlying": "iシェアーズ・コア S&P BSE SENSEX インディアETF",
        "proxy_ticker": "INDA",
        "expense_ratio": 0.4638,
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
        "category": "金・コモディティ・債券",
        "type": "オルタナティブ",
        "trustee": "SBIアセットマネジメント",
        "underlying": "iシェアーズ・ゴールド・トラスト (IAU)",
        "proxy_ticker": "IAU",
        "expense_ratio": 0.1838,
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
        "category": "金・コモディティ・債券",
        "type": "債券インデックス",
        "trustee": "SBIアセットマネジメント",
        "underlying": "iシェアーズ・コア 米国総合債券市場ETF (AGG)",
        "proxy_ticker": "AGG",
        "expense_ratio": 0.0938,
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
        "id": "sbi_snowball_world",
        "name": "SBI・iシェアーズ・全世界株式インデックス・ファンド",
        "nickname": "雪だるま全世界",
        "category": "王道インデックス",
        "type": "インデックス",
        "trustee": "SBIアセットマネジメント",
        "underlying": "FTSEグローバル・オールキャップ・インデックス連動ETF群",
        "proxy_ticker": "VT",
        "expense_ratio": 0.1102,
        "aum_oku": 920,
        "nisa_tsumitate": True,
        "nisa_growth": True,
        "return_1y": 28.2,
        "return_3y_annual": 19.8,
        "sharpe_ratio": 1.04,
        "max_drawdown": -16.9,
        "major_holdings": ["マイクロソフト", "NVIDIA", "アップル", "アマゾン", "Alphabet"],
        "description": "元祖低コスト投信『雪だるま』。年0.11%の圧倒的低手数料で全世界株式を自動積立可能。",
        "role": "コア資産（超低コスト）"
    },

    # 3. SBI Premium Choice & High Alpha Active Funds
    {
        "id": "ab_us_growth_b",
        "name": "アライアンス・バーンスタイン・米国成長株投信 Ｂコース（為替ヘッジなし）",
        "nickname": "AB米国成長株B",
        "category": "厳選アクティブ・AIテーマ",
        "type": "アクティブ",
        "trustee": "アライアンス・バーンスタイン",
        "underlying": "独自リサーチによる米国持続的成長企業",
        "proxy_ticker": "VUG",
        "expense_ratio": 1.7270,
        "aum_oku": 14500,
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
        "id": "hifumi_plus",
        "name": "ひふみプラス",
        "nickname": "ひふみプラス",
        "category": "厳選アクティブ・AIテーマ",
        "type": "アクティブ",
        "trustee": "レオス・キャピタルワークス",
        "underlying": "日本国内の成長中小型〜大型企業",
        "proxy_ticker": "1306.T",
        "expense_ratio": 1.0780,
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
        "id": "japan_dividend_rebalance",
        "name": "日本好配当リバランスオープン",
        "nickname": "日本好配当",
        "category": "高配当・インカム",
        "type": "アクティブ",
        "trustee": "SBI岡三アセットマネジメント",
        "underlying": "東証一部・プライム高配当利回り銘柄",
        "proxy_ticker": "1489.T",
        "expense_ratio": 0.9900,
        "aum_oku": 680,
        "nisa_tsumitate": False,
        "nisa_growth": True,
        "return_1y": 26.4,
        "return_3y_annual": 21.2,
        "sharpe_ratio": 1.18,
        "max_drawdown": -13.5,
        "major_holdings": ["三菱UFJフィナンシャルG", "三井住友FG", "伊藤忠商事", "武田薬品", "INPEX"],
        "description": "配当利回りが高い上位銘柄を毎月機械的にリバランス。日銀利上げ・デフレ脱却の恩恵をダイレクトに受ける。",
        "role": "国内高配当バリュー"
    },
    {
        "id": "capital_world_stock",
        "name": "キャピタル・世界株式ファンド",
        "nickname": "キャピタル世界株",
        "category": "厳選アクティブ・AIテーマ",
        "type": "アクティブ",
        "trustee": "キャピタル・インターナショナル",
        "underlying": "世界的競争優位を持つグローバル多国籍企業",
        "proxy_ticker": "ACWI",
        "expense_ratio": 1.6940,
        "aum_oku": 5200,
        "nisa_tsumitate": True,
        "nisa_growth": True,
        "return_1y": 29.8,
        "return_3y_annual": 21.4,
        "sharpe_ratio": 0.95,
        "max_drawdown": -18.7,
        "major_holdings": ["マイクロソフト", "TSMC", "メタ・プラットフォームズ", "ASML", "ノボ・ノルディスク"],
        "description": "世界最古級のアクティブ運用機関キャピタルが運用。複数ポートフォリオマネージャー制でブレを抑えた安定成長。",
        "role": "世界厳選アクティブ"
    },

    # 4. Megatrend / Thematic Packs
    {
        "id": "global_ai_fund",
        "name": "グローバルＡＩファンド",
        "nickname": "グローバルAI",
        "category": "厳選アクティブ・AIテーマ",
        "type": "テーマ型アクティブ",
        "trustee": "三井住友DSアセットマネジメント",
        "underlying": "世界のAIテクノロジー・基盤インフラ企業",
        "proxy_ticker": "BOTZ",
        "expense_ratio": 1.9250,
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
        "expense_ratio": 0.7920,
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
        "expense_ratio": 1.9250,
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
            {"fund_id": "sbi_v_sp500", "weight": 60, "name": "SBI・V・S&P500", "role": "世界最強コア成長"},
            {"fund_id": "sbi_ishares_gold", "weight": 20, "name": "サクっと純金", "role": "インフレ・有事防衛"},
            {"fund_id": "sbi_ishares_india", "weight": 20, "name": "サクっとインド株式", "role": "新興国トップ成長"}
        ]
    },
    {
        "id": "pack_mega_growth",
        "title": "超アグレッシブ・メガグロースパック",
        "badge": "最大リターン追求型",
        "concept": "全米市場まるごと＋次世代超大国インド＋生成AI革命の3本柱で市場平均を大幅アウトパフォーム狙い。",
        "expected_return": "+37.3%",
        "composite_expense": "0.674%",
        "stability_score": "高ボラティリティ・ハイリターン",
        "allocations": [
            {"fund_id": "sbi_v_total_us", "weight": 40, "name": "SBI・V・全米株式", "role": "米国全土イノベーション"},
            {"fund_id": "sbi_ishares_india", "weight": 30, "name": "サクっとインド株式", "role": "人口世界首位の爆発力"},
            {"fund_id": "global_ai_fund", "weight": 30, "name": "グローバルＡＩファンド", "role": "生成AIメガトレンド"}
        ]
    },
    {
        "id": "pack_defensive_income",
        "title": "ディフェンシブ・インカム＆防衛パック",
        "badge": "暴落耐性・守りの要",
        "concept": "下落相場でも株価が崩れにくい高配当株と実物ゴールド、米国債券を組み合わせ、資産を減らさない運用を実現。",
        "expected_return": "+22.1%",
        "composite_expense": "0.133%",
        "stability_score": "最高水準（元本保全性重視）",
        "allocations": [
            {"fund_id": "sbi_v_high_dividend", "weight": 40, "name": "SBI・V・米国高配当", "role": "下値抵抗力と配当力"},
            {"fund_id": "sbi_ishares_gold", "weight": 30, "name": "サクっと純金", "role": "金利低下・危機ヘッジ"},
            {"fund_id": "sbi_ishares_us_bond", "weight": 30, "name": "サクっと米国債券", "role": "元本安定クッション"}
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
    exp_score = min(max((2.0 - exp) / (2.0 - 0.08) * 100, 10), 100)

    dd = abs(fund["max_drawdown"])
    dd_score = min(max((40.0 - dd) / (40.0 - 10.0) * 100, 10), 100)

    aum = fund["aum_oku"]
    aum_score = min(max((aum / 5000.0) * 80 + 20, 20), 100)

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
        "インド・新興国",
        "金・コモディティ・債券",
        "高配当・インカム",
        "厳選アクティブ・AIテーマ"
    ]


def filter_and_sort_funds(
    category: str = "すべて",
    nisa_filter: str = "すべて",
    search_query: str = "",
    sort_by: str = "AI総合スコア順"
) -> List[Dict[str, Any]]:
    """
    Filters and sorts funds based on criteria.
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
    elif sort_by == "シャープレシオ（収益効率）順":
        results.sort(key=lambda x: x["sharpe_ratio"], reverse=True)
    elif sort_by == "純資産が大きい順":
        results.sort(key=lambda x: x["aum_oku"], reverse=True)

    return results


def fetch_comparison_chart_data(period: str = "1y") -> Dict[str, Any]:
    """
    Fetches historical cumulative return series for representative asset classes/funds.
    Uses yfinance proxy tickers (VOO, VT, INDA, IAU, VYM, SOXX).
    Returns normalized cumulative returns starting at 0%.
    """
    now = time.time()
    cache_key = f"chart_{period}"
    if cache_key in _CHART_CACHE:
        cached = _CHART_CACHE[cache_key]
        if now - cached["time"] < 1800:
            return cached["data"]

    # Key benchmark funds to compare
    targets = [
        {"id": "sbi_v_sp500", "label": "SBI・V・S&P500 (米国500社)", "ticker": "VOO", "color": "#1976d2"},
        {"id": "sbi_ishares_india", "label": "サクっとインド株式 (新興国首位)", "ticker": "INDA", "color": "#f59e0b"},
        {"id": "sbi_ishares_gold", "label": "サクっと純金 (有事・防衛)", "ticker": "IAU", "color": "#eab308"},
        {"id": "sbi_v_all_country", "label": "SBI・V・全世界株式 (オルカン)", "ticker": "VT", "color": "#10b981"},
        {"id": "sbi_v_high_dividend", "label": "SBI・V・米国高配当 (安定配当)", "ticker": "VYM", "color": "#8b5cf6"},
        {"id": "emaxis_neo_semiconductor", "label": "Neo 半導体 (ハイテク成長)", "ticker": "SOXX", "color": "#ec4899"}
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

    # Fallback synthetic curves if offline or yfinance rate-limited
    if not series_dict:
        dates = pd.date_range(end=pd.Timestamp.today(), periods=120, freq="B").strftime("%Y-%m-%d").tolist()
        series_dict = {
            "SBI・V・S&P500 (米国500社)": {"dates": dates, "returns": [round(i * 0.27, 2) for i in range(120)], "color": "#1976d2", "latest": 32.4},
            "サクっとインド株式 (新興国首位)": {"dates": dates, "returns": [round(i * 0.32, 2) for i in range(120)], "color": "#f59e0b", "latest": 38.6},
            "サクっと純金 (有事・防衛)": {"dates": dates, "returns": [round(i * 0.29, 2) for i in range(120)], "color": "#eab308", "latest": 35.2},
            "SBI・V・全世界株式 (オルカン)": {"dates": dates, "returns": [round(i * 0.24, 2) for i in range(120)], "color": "#10b981", "latest": 28.5},
            "SBI・V・米国高配当 (安定配当)": {"dates": dates, "returns": [round(i * 0.19, 2) for i in range(120)], "color": "#8b5cf6", "latest": 22.8},
            "Neo 半導体 (ハイテク成長)": {"dates": dates, "returns": [round(i * 0.40, 2) for i in range(120)], "color": "#ec4899", "latest": 48.2}
        }

    _CHART_CACHE[cache_key] = {"time": now, "data": series_dict}
    return series_dict
