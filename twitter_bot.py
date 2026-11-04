"""
twitter_bot.py - ZenStock Automated Twitter (X) Bot
Handles automated posting of morning quant signals and noon exit reports to X (Twitter)
via Twitter API v2 (Free Tier compatible).
"""

import os
import sys
import json
import logging
from typing import List, Dict, Optional

logger = logging.getLogger("TwitterBot")
logger.setLevel(logging.INFO)

# Environment variables for X API v2 (OAuth 1.0a User Context)
TWITTER_API_KEY = os.environ.get("TWITTER_API_KEY") or os.environ.get("X_API_KEY")
TWITTER_API_SECRET = os.environ.get("TWITTER_API_SECRET") or os.environ.get("X_API_SECRET")
TWITTER_ACCESS_TOKEN = os.environ.get("TWITTER_ACCESS_TOKEN") or os.environ.get("X_ACCESS_TOKEN")
TWITTER_ACCESS_TOKEN_SECRET = os.environ.get("TWITTER_ACCESS_TOKEN_SECRET") or os.environ.get("X_ACCESS_TOKEN_SECRET")

WEB_APP_URL = "https://stock-screener-app-crrzltcyekqdt7uulhgpaa.streamlit.app/"

def is_twitter_configured() -> bool:
    """Check if all required Twitter credentials are set."""
    return bool(TWITTER_API_KEY and TWITTER_API_SECRET and TWITTER_ACCESS_TOKEN and TWITTER_ACCESS_TOKEN_SECRET)

def post_tweet(text: str) -> Dict:
    """
    Post a tweet using Twitter API v2 /tweets endpoint with OAuth 1.0a User Context.
    Requires Free tier with write permissions.
    """
    if not is_twitter_configured():
        msg = "Twitter API credentials not configured (TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET)."
        logger.warning(msg)
        return {"status": "skipped", "message": msg}

    try:
        import requests
        from requests_oauthlib import OAuth1
    except ImportError:
        msg = "requests-oauthlib is not installed. Run `pip install requests-oauthlib`."
        logger.error(msg)
        return {"status": "error", "message": msg}

    url = "https://api.twitter.com/2/tweets"
    auth = OAuth1(
        TWITTER_API_KEY,
        TWITTER_API_SECRET,
        TWITTER_ACCESS_TOKEN,
        TWITTER_ACCESS_TOKEN_SECRET
    )
    headers = {"Content-Type": "application/json"}
    payload = {"text": text.strip()}

    try:
        resp = requests.post(url, auth=auth, headers=headers, json=payload, timeout=15)
        if resp.status_code in (200, 201):
            data = resp.json()
            tweet_id = data.get("data", {}).get("id")
            logger.info(f"✅ Successfully posted tweet! ID: {tweet_id}")
            return {"status": "success", "tweet_id": tweet_id, "data": data}
        else:
            logger.error(f"❌ Twitter API error {resp.status_code}: {resp.text}")
            return {"status": "error", "code": resp.status_code, "response": resp.text}
    except Exception as e:
        logger.exception(f"❌ Exception posting tweet: {e}")
        return {"status": "error", "message": str(e)}

def build_morning_tweet(sniped_stocks: List[Dict], latest_market_date: str = "---") -> str:
    """
    Generate morning 10:00 JST market scan announcement tweet (within 140 Japanese chars).
    Focuses on quant rigor, backtest stats (PF 3.01 / 2.83), and teaser call to action.
    """
    short_hits = [s for s in sniped_stocks if s.get("hold_days", 15) <= 5 or s.get("strategy_key") == "short"]
    main_hits = [s for s in sniped_stocks if s.get("hold_days", 15) > 5 or s.get("strategy_key") == "main"]
    total_count = len(sniped_stocks)

    if total_count > 0:
        tweet = f"【ZenStock クオンツ厳選シグナル】\n"
        tweet += f"東証プライム全1,529社×PBR1倍未満の過去全パターン照合（DTW波形分析）を完了しました📊\n\n"
        tweet += f"本日検知（計{total_count}件）:\n"
        tweet += f"・高回転モメンタム (5日保有/PF 3.01): {len(short_hits)}件\n"
        tweet += f"・中短期リバウンド (15日保有/PF 2.83): {len(main_hits)}件\n\n"
        tweet += f"▼ 該当銘柄・過去検証チャートはこちら\n{WEB_APP_URL}\n\n"
        tweet += "#日本株 #株式投資 #高配当株 #クオンツ"
    else:
        tweet = f"【ZenStock クオンツ運用ログ】\n"
        tweet += f"本日の東証プライム全銘柄DTW波形スキャンを完了。\n\n"
        tweet += "本日、高期待値（PF 2.8以上・PBR1倍割れ）を満たす銘柄は0件でした。\n"
        tweet += "エッジのない日は無理に買わずキャッシュ待機を徹底するのがクオンツ運用の鉄則です規律遵守。\n\n"
        tweet += f"▼ 詳細分析ツール\n{WEB_APP_URL}\n\n"
        tweet += "#日本株 #株式投資 #クオンツ"

    return tweet.strip()

def build_noon_exit_tweet(due_stocks: List[Dict]) -> str:
    """
    Generate noon 12:00 JST exit report tweet.
    Reports realized performance, profit targets, and -4.5% stop loss discipline.
    """
    count = len(due_stocks)
    if count == 0:
        return ""

    total_ret = sum(s.get("return_pct", 0.0) for s in due_stocks)
    avg_ret = total_ret / count if count > 0 else 0.0
    avg_sign = "+" if avg_ret >= 0 else ""

    take_profits = [s for s in due_stocks if s.get("exit_reason") == "take_profit"]
    stop_losses = [s for s in due_stocks if s.get("exit_reason") == "stop_loss"]
    time_exits = [s for s in due_stocks if s.get("exit_reason") == "time_exit"]

    tweet = f"【クオンツ保有銘柄 手仕舞い速報】⚖️\n"
    tweet += f"本日、保有期日を迎えた厳選銘柄（{count}件）を後場寄りで手仕舞い推奨。\n\n"
    tweet += f"・平均損益: {avg_sign}{avg_ret:.1f}%\n"
    if take_profits:
        tweet += f"・利確達成: {len(take_profits)}件\n"
    if stop_losses:
        tweet += f"・逆指値損切り: {len(stop_losses)}件（-4.5%限定）\n"
    if time_exits:
        tweet += f"・期日満了解消: {len(time_exits)}件\n"
    tweet += "\n利益は伸ばし、損失はルール通り機械的に切る規律を徹底しています。\n\n"
    tweet += f"{WEB_APP_URL}\n#日本株 #スイングトレード"

    return tweet.strip()

def post_morning_tweet(sniped_stocks: List[Dict], latest_market_date: str = "---") -> Dict:
    """Public helper to build and send morning market tweet."""
    tweet_text = build_morning_tweet(sniped_stocks, latest_market_date=latest_market_date)
    return post_tweet(tweet_text)

def post_noon_exit_tweet(due_stocks: List[Dict]) -> Dict:
    """Public helper to build and send noon exit tweet."""
    tweet_text = build_noon_exit_tweet(due_stocks)
    if not tweet_text:
        return {"status": "skipped", "message": "No stocks due for exit today"}
    return post_tweet(tweet_text)

if __name__ == "__main__":
    print("=" * 60)
    print("ZenStock Twitter (X) Bot Module")
    print(f"Configured: {is_twitter_configured()}")
    print("=" * 60)

    # Demo mock sample
    mock_stocks = [
        {"ticker": "8001.T", "name": "伊藤忠商事", "hold_days": 5, "strategy_key": "short", "win_rate": 60.0, "avg_ret": 8.0, "pbr": 0.95},
        {"ticker": "8031.T", "name": "三井物産", "hold_days": 15, "strategy_key": "main", "win_rate": 60.2, "avg_ret": 7.0, "pbr": 0.88}
    ]
    print("\n[Preview 1: Morning Signal Tweet (Hit)]")
    print(build_morning_tweet(mock_stocks, "2026-11-04"))

    print("\n" + "-" * 40)
    print("[Preview 2: Morning Signal Tweet (0 Hit)]")
    print(build_morning_tweet([], "2026-11-04"))

    print("\n" + "-" * 40)
    mock_exits = [
        {"ticker": "8001.T", "name": "伊藤忠商事", "return_pct": 5.4, "exit_reason": "take_profit"},
        {"ticker": "8031.T", "name": "三井物産", "return_pct": -2.1, "exit_reason": "time_exit"}
    ]
    print("[Preview 3: Noon Exit Tweet]")
    print(build_noon_exit_tweet(mock_exits))
    print("=" * 60)

    if "--send-test" in sys.argv:
        if is_twitter_configured():
            res = post_tweet("ZenStock クオンツシステム 稼働テスト 📊 #日本株")
            print("Send Result:", res)
        else:
            print("Credentials missing. Set TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET.")
