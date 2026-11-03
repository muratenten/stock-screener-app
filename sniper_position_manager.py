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

# ------------------------------------------------------------------
# 対策2: 動的リスク管理ルール (Dynamic Stop-Loss & Take-Profit)
# ------------------------------------------------------------------
STOP_LOSS_PCT = -4.5     # 許容最大ドローダウン (-4.5%到達で即時強制損切り)
TAKE_PROFIT_PCT = 10.0   # 目標利益確定ライン (+10.0%到達でスピード利確)
TARGET_HOLDING_DAYS = 15 # 目標保有期間 (15営業日 / 約3週間)

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
        hold_days = int(s.get("hold_days", 15))
        target_exit = add_trading_days(entry_date_str, trading_days=hold_days)
        strategy_label = s.get("strategy_name", "本命スイング" if hold_days >= 15 else "超短期スナイパー")
        
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
            "target_days": hold_days,
            "target_exit_date": target_exit,
            "strategy": strategy_label,
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
    Monitor all holding positions in real time:
      1. Stop-Loss Trigger: return_pct <= -4.5% (Early exit to prevent major drawdowns)
      2. Take-Profit Trigger: return_pct >= +10.0% (Early exit to lock in strong gains)
      3. Time-Exit Trigger: elapsed trading days >= 15 (Standard strategy maturity)
    """
    jst = datetime.timezone(datetime.timedelta(hours=9))
    if not today_date_str:
        today_date_str = datetime.datetime.now(jst).strftime('%Y-%m-%d')
        
    positions = load_sniper_positions()
    holding_positions = [p for p in positions if p.get("status") == "holding" and not p.get("notified_exit", False)]
    
    if not holding_positions:
        return []
        
    print(f"🔍 [SIGNAL MONITOR] Monitoring {len(holding_positions)} holding positions on {today_date_str}...")
    due_positions = []
    
    for p in holding_positions:
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
            ret_pct = 0.0
            
        target_date = p.get("target_exit_date")
        is_time_due = bool(target_date and target_date <= today_date_str)
        is_stop_loss = bool(ret_pct <= STOP_LOSS_PCT)
        is_take_profit = bool(ret_pct >= TAKE_PROFIT_PCT)
        
        if is_stop_loss:
            p["exit_reason"] = "stop_loss"
            p["exit_title"] = "⚠️ 損切りシグナル (-4.5%ストップロス到達)"
            due_positions.append(p)
            print(f"  [STOP LOSS HIT] {ticker} {p.get('name')} return {ret_pct:.1f}% <= {STOP_LOSS_PCT}%")
        elif is_take_profit:
            p["exit_reason"] = "take_profit"
            p["exit_title"] = "🎉 目標利確シグナル (+10.0%スピード到達)"
            due_positions.append(p)
            print(f"  [TAKE PROFIT HIT] {ticker} {p.get('name')} return {ret_pct:.1f}% >= +{TAKE_PROFIT_PCT}%")
        elif is_time_due:
            p["exit_reason"] = "time_exit"
            p["exit_title"] = "🔔 目標保有期日（15営業日）満了"
            due_positions.append(p)
            print(f"  [TIME EXIT HIT] {ticker} {p.get('name')} reached target exit {target_date}")
            
    return due_positions

def mark_positions_as_exited(due_positions: List[Dict], exit_date_str: Optional[str] = None) -> bool:
    """Mark positions as exited and save performance figures and exit reason."""
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
            reason = matching_due.get("exit_reason", "time_exit") if matching_due else "time_exit"
            
            p["status"] = "exited"
            p["notified_exit"] = True
            p["exit_reason"] = reason
            p["exit_date"] = exit_date_str
            p["exit_price"] = c_price
            p["exit_return_pct"] = ret_pct
            
    return save_sniper_positions(positions)

def build_noon_exit_premium_msg(due_stocks: List[Dict], user_name: str = "会員") -> str:
    """Compose premium exit alert message for 12:00 PM JST broadcast with risk-management details."""
    count = len(due_stocks)
    stop_losses = [s for s in due_stocks if s.get("exit_reason") == "stop_loss"]
    take_profits = [s for s in due_stocks if s.get("exit_reason") == "take_profit"]
    time_exits = [s for s in due_stocks if s.get("exit_reason") == "time_exit"]
    
    if stop_losses and not take_profits and not time_exits:
        main_title = "【ZenStock エグジット通知（損切り）】"
        lead_desc = f"保有中のスナイパー銘柄（{count}件）が、損切りライン（-4.5%）に到達しました。\nリスク管理に基づき、本日後場での手仕舞いを推奨します。"
    elif take_profits and not stop_losses and not time_exits:
        main_title = "【ZenStock エグジット通知（利確）】"
        lead_desc = f"保有中のスナイパー銘柄（{count}件）が、利確目標を達成しました。\n本日後場での利益確定手仕舞いを推奨します。"
    else:
        main_title = "【ZenStock エグジット通知（売却期日）】"
        lead_desc = f"保有中のスナイパー銘柄（{count}件）にエグジットシグナルが発生しました。\n検証ルールに従い、本日後場でのポジション解消を推奨します。"

    msg = f"{main_title}\n{user_name} 様\n\n{lead_desc}\n─────────────────\n"
    
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
        
        reason = s.get("exit_reason", "time_exit")
        if reason == "stop_loss":
            tag = "[損切り発動 / -4.5%到達]"
        elif reason == "take_profit":
            tag = "[利確達成 / +10%超]"
        else:
            tag = "[満期手仕舞い / 保有期間満了]"
            
        entry_p_str = f"¥{int(round(entry_p)):,}" if entry_p >= 1000 else f"¥{entry_p:,.1f}"
        curr_p_str = f"¥{int(round(curr_p)):,}" if curr_p >= 1000 else f"¥{curr_p:,.1f}"
        diff_str = f"{diff_sign}¥{int(round(diff_p)):,}" if abs(diff_p) >= 1000 else f"{diff_sign}¥{diff_p:,.1f}"
        
        msg += f"【銘柄】{name}（{ticker_str}）\n"
        msg += f"【区分】{tag}\n"
        msg += f"【エントリー】{s.get('entry_date')}（{entry_p_str}）\n"
        msg += f"【現在株価】{curr_p_str}\n"
        msg += f"【損益】{diff_str}（{sign}{ret_pct:.1f}%）\n"
        msg += "─────────────────\n"
        
    avg_ret = total_ret / count if count > 0 else 0.0
    avg_sign = "+" if avg_ret >= 0 else ""
    msg += f"対象銘柄の平均損益: {avg_sign}{avg_ret:.1f}%\n\n"
    msg += f"※ 利益は伸ばし、思惑が外れた損失は -4.5% で確実に限定する規律運用です。"
    return msg.strip()

def build_noon_exit_free_msg(due_stocks: List[Dict], user_name: str = "会員") -> str:
    """Compose free tier teaser exit alert message for 12:00 PM JST broadcast."""
    count = len(due_stocks)
    total_ret = sum(s.get("return_pct", 0.0) for s in due_stocks)
    avg_ret = total_ret / count if count > 0 else 0.0
    avg_sign = "+" if avg_ret >= 0 else ""
    
    msg = f"【ZenStock 手仕舞いアラート（無料版）】\n"
    msg += f"{user_name} 様\n\n"
    msg += f"過去配信のスナイパー銘柄（{count}件）に、本日エグジットシグナルが発生しました。\n\n"
    msg += f"損益実績（平均）: {avg_sign}{avg_ret:.1f}%\n"
    msg += "─────────────────\n"
    for idx, s in enumerate(due_stocks, 1):
        ret_pct = s.get("return_pct", 0.0)
        sign = "+" if ret_pct >= 0 else ""
        reason = s.get("exit_reason", "time_exit")
        reason_label = "損切りルール適用" if reason == "stop_loss" else ("利確目標達成" if reason == "take_profit" else "保有期間満了")
        msg += f"【候補 #{idx}】東証プライム（{s.get('sector', 'プライム')}）\n"
        msg += f"【区分】{reason_label}\n"
        msg += f"【損益実績】{sign}{ret_pct:.1f}%\n"
        msg += "─────────────────\n"
    msg += "※ 銘柄名・現在価格・詳細判定はプレミアム会員限定機能です。\n\n"
    msg += "プレミアムプランのご案内:\n"
    msg += "https://stock-screener-app-crrzltcyekqdt7uulhgpaa.streamlit.app/?source=line_exit"
    return msg.strip()

def build_holding_summary_msg(user_name: str = "会員") -> str:
    """Build summary of currently holding positions for LINE user query."""
    jst = datetime.timezone(datetime.timedelta(hours=9))
    today_str = datetime.datetime.now(jst).strftime('%Y-%m-%d')
    positions = load_sniper_positions()
    holdings = [p for p in positions if p.get("status") == "holding"]
    
    if not holdings:
        return f"【ZenStock 保有中スナイパー銘柄】\n{user_name} 様\n\n現在、保有中のポジションはありません。\n朝10:00のシグナルをお待ちください。"
        
    msg = f"【ZenStock 保有中スナイパー銘柄】\n{user_name} 様\n\n現在保有中の銘柄（計 {len(holdings)}件）:\n─────────────────\n"
    for p in holdings:
        entry_date = p.get("entry_date", "")
        exit_date = p.get("target_exit_date", "")
        hold_target = p.get("hold_days", 15)
        elapsed = count_elapsed_trading_days(entry_date, today_str)
        remaining = max(0, hold_target - elapsed)
        
        name = p.get("name", p["ticker"])
        ticker_str = p["ticker"] if ".T" in p["ticker"] else f"{p['ticker']}.T"
        entry_p = p.get("entry_price", 0.0)
        entry_p_str = f"¥{int(round(entry_p)):,}" if entry_p >= 1000 else f"¥{entry_p:,.1f}"
        strat = p.get("strategy_name", "本命スイング")
        
        msg += f"【銘柄】{name}（{ticker_str}）[{strat}]\n"
        msg += f"【エントリー】{entry_date}（{entry_p_str}）\n"
        msg += f"【進捗】{elapsed}/{hold_target}営業日（残 {remaining}営業日）\n"
        msg += f"【売却期日】{exit_date}（昼12:00通知）\n"
        msg += "─────────────────\n"
        
    msg += "※ 保有期日を迎えた当日の昼12:00に自動で売却推奨アラートが届きます。"
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

