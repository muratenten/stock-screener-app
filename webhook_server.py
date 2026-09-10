"""
ZenStock LINE Webhook & LIFF Server
FastAPI-based server providing:
  - GET /liff: LIFF Interactive Slider Settings
  - POST /webhook: LINE Messaging API Webhook
  - POST /api/scan: Direct scan execution
  - Background task processing for real-time sniper scanning
"""

import os
import sys
import hmac
import json
import base64
import hashlib
import re
import requests
from typing import Optional
from fastapi import FastAPI, Request, Header, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

# Import screener logic
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)
from daily_sniper_screener import run_sniper_screening, send_line_message

app = FastAPI(title="ZenStock LINE Bot & LIFF")

# Mount Static Files
static_dir = os.path.join(BASE_DIR, "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# LINE Configurations
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get(
    "LINE_CHANNEL_ACCESS_TOKEN",
    "+0Ql7i4RQPQM6mDsg1H679hpdIDWRU9clQ3q4XoR9Mgz3es3mhsQJOJNQKHVhVHwO4OmUeQnYxw7cCkXrqzETunIi+VrDX8P19aoBnefzQVKaBSuKDp9kb8rj+QT3rdI4VX7UjaL+K+0NfKW1FWgwQdB04t89/1O/w1cDnyilFU="
)
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")
LINE_LIFF_ID = os.environ.get("LINE_LIFF_ID", "")
USER_PREF_FILE = os.path.join(BASE_DIR, "user_preferences.json")

def verify_signature(body_bytes: bytes, signature: str) -> bool:
    """Verify LINE Webhook signature if secret is set."""
    if not LINE_CHANNEL_SECRET:
        return True
    hash_val = hmac.new(
        LINE_CHANNEL_SECRET.encode('utf-8'),
        body_bytes,
        hashlib.sha256
    ).digest()
    expected = base64.b64encode(hash_val).decode('utf-8')
    return hmac.compare_digest(expected, signature)

def reply_line_message(reply_token: str, message_text: str):
    """Send immediate reply to user via LINE Reply API."""
    if not reply_token or not LINE_CHANNEL_ACCESS_TOKEN:
        return False
    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    payload = {
        "replyToken": reply_token,
        "messages": [
            {
                "type": "text",
                "text": message_text
            }
        ]
    }
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        return res.status_code == 200
    except Exception as e:
        print(f"[REPLY ERROR] {e}")
        return False

def save_user_preference(user_id: str, params: dict):
    prefs = {}
    if os.path.exists(USER_PREF_FILE):
        try:
            with open(USER_PREF_FILE, "r", encoding="utf-8") as f:
                prefs = json.load(f)
        except Exception:
            prefs = {}
    prefs[user_id] = params
    with open(USER_PREF_FILE, "w", encoding="utf-8") as f:
        json.dump(prefs, f, ensure_ascii=False, indent=2)

def get_user_preference(user_id: str) -> dict:
    if os.path.exists(USER_PREF_FILE):
        try:
            with open(USER_PREF_FILE, "r", encoding="utf-8") as f:
                prefs = json.load(f)
                if user_id in prefs:
                    return prefs[user_id]
        except Exception:
            pass
    return {
        "match_days": 60,
        "hold_days": 25,
        "thresh": 10.0,
        "pbr": 1.0
    }

# ================= Endpoints =================

@app.get("/")
def index():
    return {
        "status": "online",
        "app": "ZenStock Sniper LINE Bot & LIFF",
        "liff_url": f"https://liff.line.me/{LINE_LIFF_ID}" if LINE_LIFF_ID else "/liff"
    }

@app.get("/liff", response_class=HTMLResponse)
def serve_liff():
    liff_path = os.path.join(static_dir, "liff.html")
    if os.path.exists(liff_path):
        with open(liff_path, "r", encoding="utf-8") as f:
            html = f.read()
        # Inject LIFF ID if configured
        if LINE_LIFF_ID:
            html = html.replace("DEFAULT_LIFF_ID", LINE_LIFF_ID)
        return HTMLResponse(content=html)
    return HTMLResponse(content="<h3>LIFF file not found.</h3>", status_code=404)

@app.post("/api/scan")
def api_scan(payload: dict, background_tasks: BackgroundTasks):
    match_days = int(payload.get("match_days", 60))
    hold_days = int(payload.get("hold_days", 25))
    thresh = float(payload.get("thresh", 10.0))
    pbr_raw = payload.get("pbr", "pbr1")
    pbr_max = 1.0 if pbr_raw in ("pbr1", 1.0, 1) else None
    user_id = payload.get("user_id")

    background_tasks.add_task(
        run_sniper_screening,
        n_match=match_days,
        future_day=hold_days,
        thresh=thresh,
        pbr_max=pbr_max,
        target_user_id=user_id,
        send_push=True,
        is_interactive=True
    )
    return {"status": "scanning_started", "params": {"match": match_days, "hold": hold_days, "thresh": thresh, "pbr": pbr_max}}

@app.post("/webhook")
async def line_webhook(request: Request, background_tasks: BackgroundTasks, x_line_signature: Optional[str] = Header(None)):
    body_bytes = await request.body()
    body_str = body_bytes.decode('utf-8')

    # Verify signature if secret is present
    if LINE_CHANNEL_SECRET and x_line_signature:
        if not verify_signature(body_bytes, x_line_signature):
            raise HTTPException(status_code=400, detail="Invalid signature")

    try:
        data = json.loads(body_str)
    except Exception:
        return JSONResponse({"status": "invalid json"}, status_code=400)

    events = data.get("events", [])
    for ev in events:
        if ev.get("type") != "message":
            continue
        msg = ev.get("message", {})
        if msg.get("type") != "text":
            continue

        text = msg.get("text", "").strip()
        reply_token = ev.get("replyToken")
        source = ev.get("source", {})
        user_id = source.get("userId")

        # 1. Trigger Scan (e.g. "スキャン", "スナイプ", "今すぐ", "スキャン 60 25 10 1")
        if text.startswith("スキャン") or text.startswith("スナイプ") or "スキャン実行" in text:
            # Parse parameters if given
            # Format: "スキャン 60 25 10 1" or "🎯 【スナイパースキャン実行】\n照合:60日 | 保有:25日..."
            match_days = 60
            hold_days = 25
            thresh = 10.0
            pbr_max = 1.0

            # Direct numbers: "スキャン 60 25 10 1"
            nums = re.findall(r"[-+]?\d*\.\d+|\d+", text)
            if len(nums) >= 3:
                try:
                    match_days = int(nums[0])
                    hold_days = int(nums[1])
                    thresh = float(nums[2])
                    if len(nums) >= 4:
                        pbr_val = float(nums[3])
                        pbr_max = 1.0 if pbr_val == 1.0 or pbr_val == 1 else (None if pbr_val == 0 else pbr_val)
                    if "制限なし" in text or "全銘柄" in text:
                        pbr_max = None
                except Exception:
                    pass

            pbr_label = f"PBR < {pbr_max:.1f}" if pbr_max else "制限なし"

            # Send immediate reply
            reply_text = (
                f"🎯 スナイパースキャンを開始しました...\n"
                f"━━━━━━━━━━━━━━\n"
                f"・照合期間: {match_days}日\n"
                f"・保有期間: {hold_days}日\n"
                f"・上昇閾値: +{thresh:.1f}%\n"
                f"・PBR条件: {pbr_label}\n"
                f"━━━━━━━━━━━━━━\n"
                f"約5秒でスクリーニング結果をお届けします！"
            )
            reply_line_message(reply_token, reply_text)

            # Background task
            background_tasks.add_task(
                run_sniper_screening,
                n_match=match_days,
                future_day=hold_days,
                thresh=thresh,
                pbr_max=pbr_max,
                target_user_id=user_id,
                send_push=True,
                is_interactive=True
            )

        # 2. Save preference (e.g. "保存 60 25 10 1")
        elif text.startswith("保存") or "毎朝通知条件を更新" in text:
            nums = re.findall(r"[-+]?\d*\.\d+|\d+", text)
            match_days = int(nums[0]) if len(nums) >= 1 else 60
            hold_days = int(nums[1]) if len(nums) >= 2 else 25
            thresh = float(nums[2]) if len(nums) >= 3 else 10.0
            pbr_max = 1.0
            if len(nums) >= 4:
                pbr_max = None if float(nums[3]) == 0 else 1.0
            if "制限なし" in text or "全銘柄" in text:
                pbr_max = None

            if user_id:
                save_user_preference(user_id, {
                    "match_days": match_days,
                    "hold_days": hold_days,
                    "thresh": thresh,
                    "pbr": pbr_max
                })

            pbr_label = f"PBR < {pbr_max:.1f}" if pbr_max else "制限なし"
            reply_text = (
                f"🔔 毎朝の通知条件を更新しました！\n"
                f"━━━━━━━━━━━━━━\n"
                f"・照合期間: {match_days}日\n"
                f"・保有期間: {hold_days}日\n"
                f"・上昇閾値: +{thresh:.1f}%\n"
                f"・PBR条件: {pbr_label}\n"
                f"━━━━━━━━━━━━━━\n"
                f"毎平日 10:00 JST にこの条件で自動検知して通知します。"
            )
            reply_line_message(reply_token, reply_text)

        # 3. Settings / Open LIFF
        elif any(k in text for k in ["設定", "条件", "スライダー", "メニュー", "ヘルプ", "開く"]):
            liff_link = f"https://liff.line.me/{LINE_LIFF_ID}" if LINE_LIFF_ID else "https://YOUR_SERVER_URL/liff"
            reply_text = (
                f"🎯【ZenStock スナイパー設定】\n\n"
                f"下のリンクからスライダーを動かして、自分好みの条件設定＆即時スキャンができます👇\n\n"
                f"{liff_link}\n\n"
                f"💡 操作可能な項目:\n"
                f"・照合期間（10〜120日）\n"
                f"・保有期間（5〜120日）\n"
                f"・上昇閾値（+3.0%〜+10.0%）\n"
                f"・PBRフィルター（<1.0倍 / 制限なし）\n\n"
                f"※過去5年間のバックテスト勝率や期待利益がリアルタイムに表示されます！"
            )
            reply_line_message(reply_token, reply_text)

        # 4. Default Guidance
        else:
            liff_link = f"https://liff.line.me/{LINE_LIFF_ID}" if LINE_LIFF_ID else "https://YOUR_SERVER_URL/liff"
            reply_text = (
                f"こんにちは！ZenStock スナイパーBotです🎯\n\n"
                f"「スキャン」と送信すると、現在の市場から勝率80%の神シグナル銘柄を即座にスキャンします。\n\n"
                f"条件を自由に変更したい場合は「設定」と送るか、以下からスライダーを開いてください👇\n"
                f"{liff_link}"
            )
            reply_line_message(reply_token, reply_text)

    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    print(f"🚀 Starting ZenStock Webhook & LIFF Server on port {port}...")
    uvicorn.run("webhook_server:app", host="0.0.0.0", port=port, reload=False)
