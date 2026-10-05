"""
Sniper Position Manager
Handles entry position recording, 15-trading-day (~3 weeks) holding period tracking,
and noon (12:00 PM JST) exit signal notification.
"""

import os
import json
import time
import datetime
from typing import List, Dict, Tuple, Optional
import yfinance as yf
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POSITIONS_FILE = os.path.join(BASE_DIR, "sniper_positions.json")

# Japanese National Holidays (2025 - 2027) for trading days calculation
JP_HOLIDAYS_SET = {
    # 2025
    "2025-01-01", "2025-01-13", "2025-02-11", "2025-02-23", "2025-02-24",
    "2025-03-20", "2025-04-29", "2025-05-03", "2025-05-04", "2025-05-05", "2025-05-06",
    "2025-07-21", "2025-08-11", "2025-09-15", "2025-09-23", "2025-10-13",
    "2025-11-03", "2025-11-23", "2025-11-24",
    # 2026
    "2026-01-01", "2026-01-12", "2026-02-11", "2026-02-23", "2026-03-20",
    "2026-04-29", "2026-05-03", "2026-05-04", "2026-05-05", "2026-05-06",
    "2026-07-20", "2026-08-11", "2026-09-21", "2026-09-22", "2026-09-23",
    "2026-10-12", "2026-11-03", "2026-11-23",
    # 2027
    "2027-01-01", "2027-01-11", "2027-02-11", "2027-02-23", "2027-03-21", "2027-03-22",
    "2027-04-29", "2027-05-03", "2027-05-04", "2027-05-05",
    "2027-07-19", "2027-08-11", "2027-09-20", "2027-09-23",
    "2027-10-11", "2027-11-03", "2027-11-23"
}

def is_trading_day(d: datetime.date) -> bool:
    """Check if date is a Tokyo Stock Exchange trading day (weekday and not holiday)."""
    if d.weekday() >= 5:  # Saturday or Sunday
        return False
    d_str = d.strftime('%Y-%m-%d')
    if d_str in JP_HOLIDAYS_SET:
        return False
    return True

def add_trading_days(start_date_str: str, trading_days: int = 15) -> str:
    """Calculate date after N trading days (excluding weekends & Japanese holidays)."""
    curr = datetime.datetime.strptime(start_date_str, '%Y-%m-%d').date()
    counted = 0
    while counted < trading_days:
        curr += datetime.timedelta(days=1)
        if is_trading_day(curr):
            counted += 1
    return curr.strftime('%Y-%m-%d')

def count_elapsed_trading_days(start_date_str: str, current_date_str: str) -> int:
    """Count how many trading days have elapsed since start_date up to current_date."""
    start = datetime.datetime.strptime(start_date_str, '%Y-%m-%d').date()
    curr = datetime.datetime.strptime(current_date_str, '%Y-%m-%d').date()
    if curr <= start:
        return 0
    count = 0
    d = start + datetime.timedelta(days=1)
    while d <= curr:
        if is_trading_day(d):
            count += 1
        d += datetime.timedelta(days=1)
    return count

def load_sniper_positions() -> List[Dict]:
    """Load all sniper positions from disk JSON."""
    if not os.path.exists(POSITIONS_FILE):
        return []
    try:
        with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[POSITIONS LOAD ERROR] {e}")
        return []

def save_sniper_positions(positions: List[Dict]) -> bool:
    """Persist sniper positions to disk JSON."""
    try:
        with open(POSITIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(positions, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[POSITIONS SAVE ERROR] {e}")
        return False

def record_sniper_positions(sniped_stocks: List[Dict], entry_date_str: Optional[str] = None) -> int:
    """
    Record newly sniped stocks into positions store with target exit date (15 trading days / ~3 weeks).
    Returns count of newly registered positions.
    """
    if not sniped_stocks:
        return 0
        
    jst = datetime.timezone(datetime.timedelta(hours=9))
    if not entry_date_str:
        entry_date_str = datetime.datetime.now(jst).strftime('%Y-%m-%d')
        
    target_exit = add_trading_days(entry_date_str, trading_days=15)
    
    positions = load_sniper_positions()
    existing_keys = {(p.get("ticker"), p.get("entry_date")) for p in positions}
    
    added_count = 0
    for s in sniped_stocks:
        ticker = s.get("ticker")
        if not ticker:
            continue
        key = (ticker, entry_date_str)
        if key in existing_keys:
            continue
            
        pos_id = f"{ticker.replace('.T', '')}_{entry_date_str}"
        entry_price = s.get("last_price")
        
        pos = {
            "id": pos_id,
            "ticker": ticker,
            "name": s.get("name", ticker),
            "sector": s.get("sector", ""),
            "entry_date": entry_date_str,
            "entry_price": float(entry_price) if entry_price is not None else 0.0,
            "pbr": s.get("pbr"),
            "min_past_return": s.get("min_ret"),
            "avg_past_return": s.get("avg_ret"),
            "target_days": 15,
            "target_exit_date": target_exit,
            "status": "holding",
            "notified_entry": True,
            "notified_exit": False,
            "exit_date": None,
            "exit_price": None,
            "exit_return_pct": None
        }
        positions.append(pos)
        existing_keys.add(key)
        added_count += 1
        
    if added_count > 0:
        save_sniper_positions(positions)
        print(f"🎯 [SNIPER POSITION] Registered {added_count} new entry positions! Target exit: {target_exit} (15 trading days)")
        
    return added_count

def check_due_exits_and_fetch_prices(today_date_str: Optional[str] = None) -> List[Dict]:
    """
    Find positions that have reached their target exit date (<= today) and fetch current prices.
    """
    jst = datetime.timezone(datetime.timedelta(hours=9))
    if not today_date_str:
        today_date_str = datetime.datetime.now(jst).strftime('%Y-%m-%d')
        
    positions = load_sniper_positions()
    due_positions = []
    
    for p in positions:
        if p.get("status") == "holding" and not p.get("notified_exit", False):
            target_date = p.get("target_exit_date")
            if target_date and target_date <= today_date_str:
                due_positions.append(p)
                
    if not due_positions:
        return []
        
    # Fetch latest real-time prices for due positions
    print(f"🔍 [EXIT CHECK] {len(due_positions)} positions reached exit date {today_date_str}. Fetching current prices...")
    for p in due_positions:
        ticker = p["ticker"]
        try:
            t = yf.Ticker(ticker)
            df = t.history(period="5d")
            if df is not None and not df.empty:
                c_now = float(df['Close'].dropna().iloc[-1])
            else:
                c_now = p.get("entry_price", 0.0)
        except Exception as e:
            print(f"Error fetching current price for {ticker}: {e}")
            c_now = p.get("entry_price", 0.0)
            
        p["current_price"] = c_now
        entry_price = p.get("entry_price", 0.0)
        if entry_price > 0 and c_now > 0:
            diff = c_now - entry_price
            ret_pct = (diff / entry_price) * 100.0
            p["diff_price"] = diff
            p["return_pct"] = ret_pct
        else:
            p["diff_price"] = 0.0
            p["return_pct"] = 0.0
            
    return due_positions

def mark_positions_as_exited(due_positions: List[Dict], exit_date_str: Optional[str] = None) -> bool:
    """Mark positions as exited and save performance figures."""
    if not due_positions:
        return False
        
    jst = datetime.timezone(datetime.timedelta(hours=9))
    if not exit_date_str:
        exit_date_str = datetime.datetime.now(jst).strftime('%Y-%m-%d')
        
    positions = load_sniper_positions()
    due_ids = {p["id"] for p in due_positions}
    
    for p in positions:
        if p["id"] in due_ids:
            matching_due = next((d for d in due_positions if d["id"] == p["id"]), None)
            c_price = matching_due.get("current_price", p.get("entry_price", 0.0)) if matching_due else p.get("entry_price", 0.0)
            ret_pct = matching_due.get("return_pct", 0.0) if matching_due else 0.0
            
            p["status"] = "exited"
            p["notified_exit"] = True
            p["exit_date"] = exit_date_str
            p["exit_price"] = c_price
            p["exit_return_pct"] = ret_pct
            
    return save_sniper_positions(positions)

def build_noon_exit_premium_msg(due_stocks: List[Dict], user_name: str = "会員") -> str:
    """Compose premium exit alert message for 12:00 PM JST broadcast."""
    count = len(due_stocks)
    msg = f"🔔【ZenStock スナイパー売却シグナル（満了期日）】\n"
    msg += f"{user_name} 様\n\n"
    msg += f"約3週間前（15営業日前）にエントリーした以下の【{count}銘柄】が、スナイパー目標保有期間を満了しました！\n\n"
    msg += f"検証ルールに従い、本日（後場の寄り付きまたは大引け）での【利益確定・ポジション解消（売却）】を推奨します。\n"
    msg += "━━━━━━━━━━━━━━\n"
    
    total_ret = 0.0
    for s in due_stocks:
        name = s.get("name", s["ticker"])
        ticker_str = s["ticker"] if ".T" in s["ticker"] else f"{s['ticker']}.T"
        entry_p = s.get("entry_price", 0.0)
        curr_p = s.get("current_price", 0.0)
        diff_p = s.get("diff_price", 0.0)
        ret_pct = s.get("return_pct", 0.0)
        total_ret += ret_pct
        
        sign = "+" if ret_pct >= 0 else ""
        diff_sign = "+" if diff_p >= 0 else ""
        ret_icon = "🎉" if ret_pct >= 5.0 else ("📈" if ret_pct > 0 else "📉")
        
        entry_p_str = f"¥{int(round(entry_p)):,}" if entry_p >= 1000 else f"¥{entry_p:,.1f}"
        curr_p_str = f"¥{int(round(curr_p)):,}" if curr_p >= 1000 else f"¥{curr_p:,.1f}"
        diff_str = f"{diff_sign}¥{int(round(diff_p)):,}" if abs(diff_p) >= 1000 else f"{diff_sign}¥{diff_p:,.1f}"
        
        msg += f"【銘柄】{name}（{ticker_str}）\n"
        msg += f"【エントリー日】{s.get('entry_date')}（{entry_p_str}）\n"
        msg += f"【現在株価】{curr_p_str}\n"
        msg += f"【損益】{diff_str}（{ret_icon} {sign}{ret_pct:.1f}%）\n"
        msg += "━━━━━━━━━━━━━━\n"
        
    avg_ret = total_ret / count if count > 0 else 0.0
    avg_sign = "+" if avg_ret >= 0 else ""
    msg += f"📊 今回の平均損益: {avg_sign}{avg_ret:.1f}%\n"
    msg += f"💡 スナイパー投資法の鉄則:\n"
    msg += f"「欲張らずにルール通り15営業日（約3週間）で確実に手仕舞う」ことで、過去4年間のバックテスト勝率72.7%を達成しています。後場の売却をご検討ください。"
    return msg.strip()

def build_noon_exit_free_msg(due_stocks: List[Dict], user_name: str = "会員") -> str:
    """Compose free tier teaser exit alert message for 12:00 PM JST broadcast."""
    count = len(due_stocks)
    total_ret = sum(s.get("return_pct", 0.0) for s in due_stocks)
    avg_ret = total_ret / count if count > 0 else 0.0
    avg_sign = "+" if avg_ret >= 0 else ""
    
    msg = f"🔔【ZenStock スナイパー売却期日アラート】\n"
    msg += f"{user_name} 様\n\n"
    msg += f"約3週間前に配信された神シグナル銘柄【{count}銘柄】が、本日15営業日の目標保有期間を満了しました！\n\n"
    msg += f"📈 3週間の推定平均パフォーマンス: {avg_sign}{avg_ret:.1f}%\n"
    msg += "━━━━━━━━━━━━━━\n"
    for idx, s in enumerate(due_stocks, 1):
        ret_pct = s.get("return_pct", 0.0)
        sign = "+" if ret_pct >= 0 else ""
        ret_icon = "🎉" if ret_pct >= 5.0 else ("📈" if ret_pct > 0 else "📉")
        msg += f"【{idx}社目】東証プライム（{s.get('sector', '割安バリュー')}）\n"
        msg += f"【保有期間】15営業日（約3週間）満了\n"
        msg += f"【損益実績】{ret_icon} {sign}{ret_pct:.1f}%\n"
        msg += "━━━━━━━━━━━━━━\n"
    msg += "🔒 売却対象の銘柄名・コード・適正売却価格はプレミアム会員限定機能です。\n\n"
    msg += "👇 今すぐプレミアム登録して売却シグナルを受け取る\n"
    msg += "https://stock-screener-app-crrzltcyekqdt7uulhgpaa.streamlit.app/?source=line_exit"
    return msg.strip()

def build_holding_summary_msg(user_name: str = "会員") -> str:
    """Build summary of currently holding positions for LINE user query."""
    jst = datetime.timezone(datetime.timedelta(hours=9))
    today_str = datetime.datetime.now(jst).strftime('%Y-%m-%d')
    positions = load_sniper_positions()
    holdings = [p for p in positions if p.get("status") == "holding"]
    
    if not holdings:
        return f"📋【ZenStock 保有中スナイパー銘柄】\n{user_name} 様\n\n現在、保有中のスナイパーポジションはありません。\n朝10:00のシグナルをお待ちください。"
        
    msg = f"📋【ZenStock 保有中スナイパー銘柄】\n{user_name} 様\n\n現在保有中のスナイパー銘柄（全{len(holdings)}件）:\n━━━━━━━━━━━━━━\n"
    for p in holdings:
        entry_date = p.get("entry_date", "")
        exit_date = p.get("target_exit_date", "")
        elapsed = count_elapsed_trading_days(entry_date, today_str)
        remaining = max(0, 15 - elapsed)
        
        name = p.get("name", p["ticker"])
        ticker_str = p["ticker"] if ".T" in p["ticker"] else f"{p['ticker']}.T"
        entry_p = p.get("entry_price", 0.0)
        entry_p_str = f"¥{int(round(entry_p)):,}" if entry_p >= 1000 else f"¥{entry_p:,.1f}"
        
        msg += f"【銘柄】{name}（{ticker_str}）\n"
        msg += f"【エントリー】{entry_date}（{entry_p_str}）\n"
        msg += f"【進捗】{elapsed}/15営業日（売却まで あと{remaining}営業日）\n"
        msg += f"【売却期日】{exit_date}（昼12:00通知）\n"
        msg += "━━━━━━━━━━━━━━\n"
        
    msg += "💡 目標の15営業日（約3週間）を迎えた当日の【お昼12:00】に自動で売却推奨アラートが届きます。"
    return msg.strip()

def get_positions_summary() -> Dict:
    """Get count and overview of positions for dashboard / API."""
    positions = load_sniper_positions()
    holding = [p for p in positions if p.get("status") == "holding"]
    exited = [p for p in positions if p.get("status") == "exited"]
    return {
        "total_positions": len(positions),
        "holding_count": len(holding),
        "exited_count": len(exited),
        "holding_tickers": [p.get("ticker") for p in holding],
        "next_exit_date": min([p.get("target_exit_date") for p in holding if p.get("target_exit_date")], default=None)
    }

# Convenient aliases
load_positions = load_sniper_positions
save_positions = save_sniper_positions
build_noon_exit_msg_premium = build_noon_exit_premium_msg
build_noon_exit_msg_free = build_noon_exit_free_msg

