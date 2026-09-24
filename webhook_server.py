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
import time
import resource
from typing import Optional
from fastapi import FastAPI, Request, Header, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# Import screener logic
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)
import threading
from daily_sniper_screener import run_sniper_screening, send_line_message, warm_up_cache

app = FastAPI(title="ZenStock LINE Bot & LIFF")

# Enable CORS for LIFF iframe and external origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SERVER_START_TIME = time.time()
LAST_HEALTH_PING = 0
HEALTH_PING_COUNT = 0

def get_memory_mb():
    try:
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform == "darwin":
            return round(rss / (1024 * 1024), 1)
        return round(rss / 1024, 1)
    except Exception:
        return 0.0

@app.on_event("startup")
def startup_event():
    print("🚀 Server starting: launching background cache pre-warm...")
    threading.Thread(target=warm_up_cache, daemon=True).start()
    start_morning_scheduler()

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
LINE_LIFF_ID = os.environ.get("LINE_LIFF_ID", "2011538719-L0SX8ZZU")
LINE_USER_ID = os.environ.get("LINE_USER_ID", "U808d7431c75b1a6dded4e6be45447e27")
USER_PREF_FILE = os.path.join(BASE_DIR, "user_preferences.json")

# In-memory debug logs (last 50 events)
RECENT_LOGS = []

def add_log(message: str):
    import datetime
    timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime("%H:%M:%S")
    entry = f"[{timestamp}] {message}"
    print(entry, flush=True)
    RECENT_LOGS.append(entry)
    if len(RECENT_LOGS) > 50:
        RECENT_LOGS.pop(0)

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
    is_valid = hmac.compare_digest(expected, signature)
    if not is_valid:
        add_log(f"⚠️ Signature verification FAILED! expected={expected[:8]}... got={signature[:8]}...")
    return is_valid

def reply_line_message(reply_token: str, message_text: str):
    """Send immediate reply to user via LINE Reply API."""
    if not reply_token or not LINE_CHANNEL_ACCESS_TOKEN:
        add_log("⚠️ reply_line_message: missing reply_token or token")
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
        if res.status_code == 200:
            add_log(f"✅ Reply sent successfully (token: {reply_token[:8]}...)")
            return True
        else:
            add_log(f"❌ Reply API error: {res.status_code} - {res.text}")
            return False
    except Exception as e:
        add_log(f"❌ Reply exception: {e}")
        return False

def get_line_user_profile(user_id: str) -> dict:
    """Fetch LINE user profile (display name, picture)."""
    if not LINE_CHANNEL_ACCESS_TOKEN or not user_id:
        return {}
    url = f"https://api.line.me/v2/bot/profile/{user_id}"
    headers = {"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        add_log(f"⚠️ Profile API error: {e}")
    return {}

def load_all_preferences() -> dict:
    prefs = {}
    if os.path.exists(USER_PREF_FILE):
        try:
            with open(USER_PREF_FILE, "r", encoding="utf-8") as f:
                prefs = json.load(f)
        except Exception:
            prefs = {}
    if LINE_USER_ID not in prefs:
        prefs[LINE_USER_ID] = {
            "name": "村本拓海 (管理者)",
            "match_days": 50,
            "hold_days": 15,
            "thresh": 8.0,
            "pbr": 1.0,
            "active": True,
            "registered_at": "初期登録"
        }
    return prefs

def save_all_preferences(prefs: dict):
    try:
        with open(USER_PREF_FILE, "w", encoding="utf-8") as f:
            json.dump(prefs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        add_log(f"⚠️ save_all_preferences error: {e}")

def save_user_preference(user_id: str, params: dict, name: str = None):
    prefs = load_all_preferences()
    if user_id not in prefs:
        prefs[user_id] = {
            "name": name or "知人ユーザー",
            "match_days": 50,
            "hold_days": 15,
            "thresh": 8.0,
            "pbr": 1.0,
            "active": True,
            "registered_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
    prefs[user_id].update(params)
    if name and prefs[user_id].get("name") in ("知人ユーザー", None, ""):
        prefs[user_id]["name"] = name
    prefs[user_id]["active"] = True
    save_all_preferences(prefs)
    add_log(f"👤 Subscriber updated: {prefs[user_id].get('name')} ({user_id[:8]}...)")

def get_user_preference(user_id: str) -> dict:
    prefs = load_all_preferences()
    return prefs.get(user_id, {
        "match_days": 50,
        "hold_days": 15,
        "thresh": 8.0,
        "pbr": 1.0
    })

def deactivate_user(user_id: str):
    prefs = load_all_preferences()
    if user_id in prefs:
        prefs[user_id]["active"] = False
        save_all_preferences(prefs)
        add_log(f"🚫 Subscriber deactivated (blocked): {user_id[:8]}...")

def broadcast_morning_sniper_routine(force=False):
    """Execute morning screening and push to all registered active subscribers."""
    add_log("🌅 [MORNING ROUTINE] Starting morning sniper routine...")
    prefs = load_all_preferences()
    active_subscribers = {uid: u for uid, u in prefs.items() if u.get("active", True)}
    
    if not active_subscribers:
        add_log("⚠️ [MORNING ROUTINE] No active subscribers found.")
        return 0, "配信対象の登録者がいません。"
        
    add_log(f"🎯 [MORNING ROUTINE] Target subscribers: {len(active_subscribers)} people")
    
    # Run screening with golden default: 50d x 15d x +8.0% x PBR<1.0
    sniped_stocks, msg = run_sniper_screening(
        n_match=50,
        future_day=15,
        thresh=8.0,
        pbr_max=1.0,
        send_push=False,
        is_interactive=False
    )
    
    sent_count = 0
    if sniped_stocks or force:
        for uid, uinfo in active_subscribers.items():
            uname = uinfo.get("name", "会員")
            p_msg = f"🌅【毎朝10:00 スナイパーシグナル】\n{uname} 様\n\n" + msg
            ok = send_line_message(p_msg, target_user_id=uid)
            if ok:
                sent_count += 1
            time.sleep(0.3)
        add_log(f"✅ [MORNING ROUTINE] Delivered to {sent_count} subscribers successfully!")
        return sent_count, f"{sent_count}名に朝の通知を配信しました。"
    else:
        add_log("ℹ️ [MORNING ROUTINE] No sniper hits today. Notification skipped to avoid spam.")
        return 0, "本日の条件合致銘柄はありませんでした（無駄な通知をスキップ）。"

def _morning_scheduler_loop():
    last_run_date = ""
    last_warmup_date = ""
    add_log("⏰ Morning Routine Scheduler background loop started.")
    import datetime
    while True:
        try:
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            now_jst = now_utc + datetime.timedelta(hours=9)
            
            # Weekday check: Monday (0) to Friday (4)
            is_weekday = now_jst.weekday() < 5
            today_str = now_jst.strftime("%Y-%m-%d")
            
            # 1. Pre-warm & refresh cache at 09:55 AM JST on weekdays (5 mins before broadcast)
            if is_weekday and now_jst.hour == 9 and now_jst.minute == 55:
                if last_warmup_date != today_str:
                    last_warmup_date = today_str
                    add_log("🌅 [SCHEDULER 09:55] Running pre-broadcast cache refresh with latest market data...")
                    warm_up_cache(force=True)

            # 2. Trigger broadcast at 10:00 AM JST on weekdays
            if is_weekday and now_jst.hour == 10 and now_jst.minute == 0:
                if last_run_date != today_str:
                    last_run_date = today_str
                    broadcast_morning_sniper_routine()
                    
            time.sleep(30)
        except Exception as e:
            add_log(f"❌ Scheduler loop error: {e}")
            time.sleep(60)

def start_morning_scheduler():
    t = threading.Thread(target=_morning_scheduler_loop, daemon=True, name="MorningRoutineScheduler")
    t.start()


# ================= Endpoints =================

@app.api_route("/", methods=["GET", "HEAD"])
def index(request: Request):
    global LAST_HEALTH_PING, HEALTH_PING_COUNT
    now = time.time()
    LAST_HEALTH_PING = now
    HEALTH_PING_COUNT += 1
    ua = request.headers.get("user-agent", "unknown")
    client_ip = request.client.host if request.client else "unknown"
    add_log(f"🌐 Root visit #{HEALTH_PING_COUNT} from {ua[:20]} ({client_ip})")
    return {
        "status": "online",
        "app": "ZenStock Sniper LINE Bot & LIFF",
        "liff_url": f"https://liff.line.me/{LINE_LIFF_ID}" if LINE_LIFF_ID else "/liff"
    }

@app.api_route("/health", methods=["GET", "HEAD"])
def health(request: Request):
    global LAST_HEALTH_PING, HEALTH_PING_COUNT
    now = time.time()
    LAST_HEALTH_PING = now
    HEALTH_PING_COUNT += 1
    ua = request.headers.get("user-agent", "unknown")
    client_ip = request.client.host if request.client else "unknown"
    add_log(f"💓 Ping #{HEALTH_PING_COUNT} from {ua[:20]} ({client_ip})")
    return {
        "status": "ok",
        "uptime_sec": int(now - SERVER_START_TIME),
        "pings": HEALTH_PING_COUNT,
        "ram_mb": get_memory_mb()
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

def clean_for_json(v):
    if hasattr(v, 'item'):
        return v.item()
    if isinstance(v, list):
        return [clean_for_json(x) for x in v]
    if isinstance(v, dict):
        return {k: clean_for_json(val) for k, val in v.items()}
    return v

@app.post("/api/scan")
def api_scan(payload: dict, background_tasks: BackgroundTasks):
    try:
        match_days = int(payload.get("match_days", 50))
        hold_days = int(payload.get("hold_days", 15))
        thresh = float(payload.get("thresh", 8.0))
        pbr_raw = payload.get("pbr", "pbr1")
        pbr_max = 1.0 if pbr_raw in ("pbr1", 1.0, 1) else None
        raw_uid = payload.get("user_id")
        user_id = raw_uid if (raw_uid and str(raw_uid).strip()) else None

        pbr_label = f"PBR < {pbr_max:.1f}" if pbr_max else "制限なし"
        
        # 1. Send immediate start notification via push only if from LINE client
        if user_id:
            start_msg = (
                f"🎯 スナイパースキャンを開始しました...\n"
                f"━━━━━━━━━━━━━━\n"
                f"・照合期間: {match_days}日\n"
                f"・保有期間: {hold_days}日\n"
                f"・上昇閾値: +{thresh:.1f}%\n"
                f"・PBR条件: {pbr_label}\n"
                f"━━━━━━━━━━━━━━\n"
                f"約1秒でスクリーニング結果をお届けします！"
            )
            send_line_message(start_msg, target_user_id=user_id)

        # 2. Run scan directly (completes in ~0.1s via disk cache!)
        sniped_stocks, result_msg = run_sniper_screening(
            n_match=match_days,
            future_day=hold_days,
            thresh=thresh,
            pbr_max=pbr_max,
            target_user_id=user_id,
            send_push=bool(user_id),
            is_interactive=True
        )

        cleaned_stocks = clean_for_json(sniped_stocks)
        return {
            "status": "success",
            "hit_count": len(cleaned_stocks),
            "stocks": cleaned_stocks,
            "message": result_msg,
            "params": {"match": match_days, "hold": hold_days, "thresh": thresh, "pbr": pbr_max}
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        add_log(f"❌ api_scan error: {e}")
        return JSONResponse({
            "status": "error",
            "message": f"スキャン実行中にエラーが発生しました: {str(e)}"
        }, status_code=500)

@app.post("/api/save_pref")
def api_save_pref(payload: dict):
    match_days = int(payload.get("match_days", 60))
    hold_days = int(payload.get("hold_days", 25))
    thresh = float(payload.get("thresh", 10.0))
    pbr_raw = payload.get("pbr", "pbr1")
    pbr_max = 1.0 if pbr_raw in ("pbr1", 1.0, 1) else None
    user_id = payload.get("user_id") or LINE_USER_ID

    save_user_preference(user_id, {
        "match_days": match_days,
        "hold_days": hold_days,
        "thresh": thresh,
        "pbr": pbr_max
    })

    pbr_label = f"PBR < {pbr_max:.1f}" if pbr_max else "制限なし"
    save_msg = (
        f"🔔 毎朝の通知条件を更新しました！\n"
        f"━━━━━━━━━━━━━━\n"
        f"・照合期間: {match_days}日\n"
        f"・保有期間: {hold_days}日\n"
        f"・上昇閾値: +{thresh:.1f}%\n"
        f"・PBR条件: {pbr_label}\n"
        f"━━━━━━━━━━━━━━\n"
        f"毎平日 10:00 JST にこの条件で自動検知して通知します。"
    )
    send_line_message(save_msg, target_user_id=user_id)
    return {"status": "saved"}

@app.post("/api/refresh_cache")
def api_refresh_cache(background_tasks: BackgroundTasks):
    add_log("🔄 Cache refresh requested via API (force=True)")
    background_tasks.add_task(warm_up_cache, force=True)
    return {"status": "refresh_started", "message": "Latest stock data download started in background"}

@app.get("/api/subscribers")
def api_subscribers():
    prefs = load_all_preferences()
    results = []
    for uid, info in prefs.items():
        masked_id = uid[:5] + "..." + uid[-4:] if len(uid) > 10 else uid
        results.append({
            "user_id_masked": masked_id,
            "name": info.get("name", "知人"),
            "active": info.get("active", True),
            "registered_at": info.get("registered_at", "初期"),
            "params": {
                "match": info.get("match_days", 50),
                "hold": info.get("hold_days", 15),
                "thresh": info.get("thresh", 8.0),
                "pbr": info.get("pbr", 1.0)
            }
        })
    return {
        "count": len(results),
        "active_count": sum(1 for r in results if r["active"]),
        "subscribers": results
    }

@app.post("/api/trigger_morning_broadcast")
def api_trigger_morning(background_tasks: BackgroundTasks, force: bool = False):
    add_log("📢 Manual morning broadcast triggered via API")
    background_tasks.add_task(broadcast_morning_sniper_routine, force=force)
    return {"status": "broadcast_queued", "force": force}

@app.post("/api/register_subscriber")
def api_register_subscriber(payload: dict):
    user_id = payload.get("user_id")
    name = payload.get("name")
    if not user_id:
        return {"status": "error", "message": "user_id is required"}
    save_user_preference(user_id, {}, name=name)
    add_log(f"👤 Subscriber auto-registered via LIFF: {name} ({user_id[:8]}...)")
    return {"status": "registered", "user_id": user_id, "name": name}

# ================= Stripe Webhook & Firestore Sync =================
FIREBASE_PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID", "zenstock-screener")
FIREBASE_API_KEY = os.environ.get("FIREBASE_API_KEY", "AIzaSyDyq0O937Xeyc7dhNQqh8HL01KkjZuCwUI")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
PROCESSED_STRIPE_EVENTS = set()

def update_user_tier_in_firebase(user_key: str, tier: str = "premium") -> bool:
    """Update user's tier field in Firebase Firestore and local preference store."""
    if not user_key or user_key in ("default", "guest", ""):
        return False
        
    # Always persist locally for instant and resilient lookup
    save_user_preference(user_key, {"tier": tier})
    clean_k = user_key.replace("firebase_", "").replace("line_", "")
    if clean_k != user_key:
        save_user_preference(clean_k, {"tier": tier})

    url = f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}/databases/(default)/documents/portfolios/{user_key}?updateMask.fieldPaths=tier"
    if FIREBASE_API_KEY:
        url += f"&key={FIREBASE_API_KEY}"
    body = {
        "fields": {
            "tier": {"stringValue": tier}
        }
    }
    headers = {"Content-Type": "application/json"}
    try:
        res = requests.patch(url, headers=headers, json=body, timeout=10)
        if res.status_code in (200, 201):
            add_log(f"✅ [FIREBASE] Successfully updated {user_key} to tier='{tier}'")
            return True
        elif res.status_code == 404:
            # Create document if not exists
            url_create = f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}/databases/(default)/documents/portfolios/{user_key}"
            if FIREBASE_API_KEY:
                url_create += f"?key={FIREBASE_API_KEY}"
            body_create = {
                "fields": {
                    "tier": {"stringValue": tier},
                    "portfolio_data": {"stringValue": "{}"},
                    "display_name": {"stringValue": user_key}
                }
            }
            res_c = requests.post(url_create, headers=headers, json=body_create, timeout=10)
            if res_c.status_code in (200, 201):
                add_log(f"✅ [FIREBASE] Created new document for {user_key} with tier='{tier}'")
                return True
        add_log(f"⚠️ [FIREBASE] HTTP {res.status_code}: {res.text[:100]} (Local preference fallback saved)")
    except Exception as e:
        add_log(f"❌ [FIREBASE EXCEPTION] {e} (Local preference fallback saved)")
    return True

@app.get("/api/user_tier")
def api_get_user_tier(user_key: str):
    """Query user's subscription tier for PC app and LIFF."""
    if not user_key or user_key in ("default", "guest", ""):
        return {"user_key": user_key, "tier": "free"}

    # Admin privilege check
    if user_key in ("google_111998389463136687256", "takkun", "line_Uf3de8f9ba3463f32a3e05b3e019b22f4", "U808d7431c75b1a6dded4e6be45447e27") or "111998389463136687256" in user_key:
        return {"user_key": user_key, "tier": "premium"}

    prefs = load_all_preferences()
    if user_key in prefs and prefs[user_key].get("tier") == "premium":
        return {"user_key": user_key, "tier": "premium"}

    clean_k = user_key.replace("firebase_", "").replace("line_", "")
    if clean_k in prefs and prefs[clean_k].get("tier") == "premium":
        return {"user_key": user_key, "tier": "premium"}

    return {"user_key": user_key, "tier": "free"}

@app.post("/api/stripe_webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe Subscription & Checkout events to automatically grant premium tier."""
    body_bytes = await request.body()
    sig_header = request.headers.get("stripe-signature")
    event = None

    if STRIPE_WEBHOOK_SECRET and sig_header:
        try:
            import stripe
            event = stripe.Webhook.construct_event(
                body_bytes, sig_header, STRIPE_WEBHOOK_SECRET
            )
        except Exception as e:
            add_log(f"❌ Stripe signature verification failed: {e}")
            raise HTTPException(status_code=400, detail="Invalid Stripe signature")
    else:
        try:
            event = json.loads(body_bytes.decode("utf-8"))
        except Exception as e:
            add_log(f"❌ Stripe invalid JSON: {e}")
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_id = event.get("id")
    if event_id:
        if event_id in PROCESSED_STRIPE_EVENTS:
            add_log(f"ℹ️ [STRIPE] Event {event_id} already processed. Skipping.")
            return {"status": "already_processed"}
        PROCESSED_STRIPE_EVENTS.add(event_id)
        if len(PROCESSED_STRIPE_EVENTS) > 500:
            PROCESSED_STRIPE_EVENTS.clear()

    event_type = event.get("type", "")
    add_log(f"💳 [STRIPE EVENT] Received: {event_type}")

    # 1. Checkout completed (subscription started)
    if event_type == "checkout.session.completed":
        session = event.get("data", {}).get("object", {})
        client_ref_id = session.get("client_reference_id")
        customer_email = session.get("customer_details", {}).get("email") or session.get("customer_email")
        
        add_log(f"💳 Checkout completed: client_ref_id={client_ref_id}, email={customer_email}")
        if client_ref_id and client_ref_id not in ("default", "guest", ""):
            ok = update_user_tier_in_firebase(client_ref_id, "premium")
            if ok:
                add_log(f"🎉 User {client_ref_id} successfully upgraded to PREMIUM in Firestore!")
            
            # If LINE user ID, also send LINE push
            if client_ref_id.startswith("line_") or client_ref_id.startswith("U"):
                clean_uid = client_ref_id.replace("line_", "")
                save_user_preference(clean_uid, {"tier": "premium"})
                send_line_message(
                    "🎉 プレミアムプランへのご登録ありがとうございます！\n"
                    "PCアプリ（過去チャート無制限練習など）およびLINEでの全機能がアンロックされました！",
                    target_user_id=clean_uid
                )

    # 2. Subscription cancelled or payment failed
    elif event_type in ("customer.subscription.deleted", "invoice.payment_failed"):
        obj = event.get("data", {}).get("object", {})
        client_ref_id = obj.get("metadata", {}).get("client_reference_id") or obj.get("client_reference_id")
        if client_ref_id and client_ref_id not in ("default", "guest", ""):
            add_log(f"⚠️ Subscription ended/failed for {client_ref_id}. Downgrading to free...")
            update_user_tier_in_firebase(client_ref_id, "free")

    return {"status": "success"}

@app.get("/logs", response_class=HTMLResponse)
def view_logs():
    now = time.time()
    uptime_sec = int(now - SERVER_START_TIME)
    uptime_str = f"{uptime_sec // 3600}時間 {(uptime_sec % 3600) // 60}分 {uptime_sec % 60}秒"
    last_ping_str = f"{int(now - LAST_HEALTH_PING)}秒前" if LAST_HEALTH_PING > 0 else "まだ受信なし"
    mem_mb = get_memory_mb()

    logs_html = "".join(f"<div style='padding:6px 0; border-bottom:1px solid #334155;'>{log}</div>" for log in reversed(RECENT_LOGS))
    return f"""
    <!DOCTYPE html>
    <html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1.0'><title>ZenStock Logs</title></head>
    <body style='background:#0f172a; color:#f8fafc; font-family:monospace; padding:20px; font-size:13px;'>
      <h2>ZenStock Server Debug Logs</h2>
      <div style='background:#1e293b; padding:14px; border-radius:8px; margin-bottom:16px; border:1px solid #334155; line-height:1.8;'>
        <div>⏱️ <b>サーバー稼働時間:</b> {uptime_str}</div>
        <div>💓 <b>死活監視Ping受信数:</b> {HEALTH_PING_COUNT} 回 (直近: {last_ping_str})</div>
        <div>🧠 <b>メモリ(RAM)使用量:</b> {mem_mb} MB / 512 MB</div>
      </div>
      <button onclick='location.reload()' style='padding:8px 16px; background:#10b981; color:#fff; border:none; border-radius:6px; cursor:pointer; font-weight:bold; margin-bottom:16px;'>🔄 最新に更新</button>
      <div>{logs_html if RECENT_LOGS else "<div>No logs recorded yet.</div>"}</div>
    </body></html>
    """

@app.post("/webhook")
async def line_webhook(request: Request, background_tasks: BackgroundTasks, x_line_signature: Optional[str] = Header(None)):
    body_bytes = await request.body()
    body_str = body_bytes.decode('utf-8')

    add_log(f"📥 Webhook received ({len(body_bytes)} bytes)")

    # Verify signature if secret is present
    if LINE_CHANNEL_SECRET and x_line_signature:
        if not verify_signature(body_bytes, x_line_signature):
            add_log("❌ Signature mismatch! Rejecting request.")
            raise HTTPException(status_code=400, detail="Invalid signature")

    try:
        data = json.loads(body_str)
    except Exception as e:
        add_log(f"❌ JSON decode error: {e}")
        return JSONResponse({"status": "invalid json"}, status_code=400)

    events = data.get("events", [])
    add_log(f"📨 Events received: {len(events)}")
    for ev in events:
        ev_type = ev.get("type")
        reply_token = ev.get("replyToken")
        source = ev.get("source", {})
        user_id = source.get("userId")

        # Handle Friend Add (follow)
        if ev_type == "follow":
            add_log(f"🎉 New friend added: {user_id[:8] if user_id else 'unknown'}")
            user_name = "知人"
            if user_id:
                profile = get_line_user_profile(user_id)
                user_name = profile.get("displayName") or "知人"
                save_user_preference(user_id, {}, name=user_name)
            welcome_msg = (
                f"こんにちは、{user_name}さん！🎯\n"
                f"ZenStock スナイパーBotへようこそ。\n\n"
                f"平日の毎朝 10:00 に、東証プライム全社から過去5年勝率72.7%・超過α+1.99%を誇る【神シグナル銘柄】を自動配信します。\n\n"
                f"「スキャン」と送信すると、今すぐリアルタイムスクリーニングも実行できます！"
            )
            if reply_token:
                reply_line_message(reply_token, welcome_msg)
            continue

        # Handle Friend Block (unfollow)
        if ev_type == "unfollow":
            add_log(f"😢 Friend blocked (unfollow): {user_id[:8] if user_id else 'unknown'}")
            if user_id:
                deactivate_user(user_id)
            continue

        if ev_type != "message":
            add_log(f"ℹ️ Non-message event: {ev_type}")
            continue

        msg = ev.get("message", {})
        msg_type = msg.get("type", "unknown")

        # Auto register or refresh profile name for ANY message type (text, sticker, image, etc.)
        if user_id:
            prefs = load_all_preferences()
            if user_id not in prefs or prefs[user_id].get("name") in ("知人ユーザー", "知人", None, ""):
                profile = get_line_user_profile(user_id)
                display_name = profile.get("displayName") or "知人"
                save_user_preference(user_id, {}, name=display_name)
            elif not prefs[user_id].get("active", True):
                prefs[user_id]["active"] = True
                save_all_preferences(prefs)

        if msg_type != "text":
            add_log(f"ℹ️ Non-text message ({msg_type}) from {user_id[:8] if user_id else 'unknown'}")
            if reply_token:
                reply_line_message(
                    reply_token,
                    "メッセージありがとうございます！🎯\n"
                    "平日毎朝 10:00 の【神シグナル銘柄】自動配信リストに登録されました！\n\n"
                    "「スキャン」と返信すると、今すぐリアルタイムスクリーニングも試せます。"
                )
            continue

        text = msg.get("text", "").strip()
        add_log(f"💬 Message from {user_id[:8] if user_id else 'unknown'}: '{text}'")

        # Admin Command: Manual Add Friend (e.g. "手動登録 U808... 山田")
        if user_id == LINE_USER_ID and text.startswith("手動登録"):
            parts = text.split()
            if len(parts) >= 2:
                target_uid = parts[1]
                target_name = parts[2] if len(parts) >= 3 else None
                if not target_name:
                    p = get_line_user_profile(target_uid)
                    target_name = p.get("displayName", "知人")
                save_user_preference(target_uid, {}, name=target_name)
                reply_line_message(reply_token, f"✅ 知人「{target_name}」({target_uid[:8]}...) を配信リストに追加しました！")
                continue

        # Admin Command: List Subscribers
        if user_id == LINE_USER_ID and any(k in text for k in ["知人一覧", "登録者", "購読者", "メンバー", "知人リスト"]):
            prefs = load_all_preferences()
            lines = []
            for i, (uid, info) in enumerate(prefs.items(), 1):
                status_mark = "✅ 配信ON" if info.get("active", True) else "❌ 配信OFF"
                reg_date = info.get("registered_at", "")[:10]
                lines.append(f"{i}. {info.get('name', '知人')} ({status_mark}) [{reg_date}]")
            list_msg = (
                f"👥【ZenStock 購読知人一覧】\n"
                f"合計: {len(prefs)}名 (有効: {sum(1 for u in prefs.values() if u.get('active', True))}名)\n"
                f"━━━━━━━━━━━━━━\n" +
                ("\n".join(lines) if lines else "登録者はいません") +
                f"\n━━━━━━━━━━━━━━\n"
                f"※平日毎朝10:00に全員へ自動配信されます。\n"
                f"「朝通知テスト」と送ると全員へ今すぐテスト配信できます。"
            )
            reply_line_message(reply_token, list_msg)
            continue

        # Admin Command: Test Morning Broadcast
        if user_id == LINE_USER_ID and any(k in text for k in ["朝通知テスト", "一斉配信テスト", "配信テスト"]):
            reply_line_message(reply_token, "🌅 知人全員への朝通知テスト配信を開始します...")
            background_tasks.add_task(broadcast_morning_sniper_routine, force=True)
            continue

        # Admin Command: Force Cache Refresh
        if user_id == LINE_USER_ID and any(k in text for k in ["キャッシュ更新", "データ更新", "最新データ更新", "株価更新"]):
            reply_line_message(reply_token, "🔄 最新の株価データを市場からダウンロードし、キャッシュを更新しています（約15秒）...")
            background_tasks.add_task(warm_up_cache, force=True)
            continue

        # Invite & Friend Sharing Command
        if any(k in text for k in ["招待", "友達追加", "友だち追加", "リンク", "シェア", "知人追加"]):
            invite_msg = (
                f"🔗【ZenStock 知人招待リンク】\n\n"
                f"知人や友人に以下のリンクを共有してください👇\n"
                f"https://line.me/R/ti/p/@317uxnml\n\n"
                f"💡 友だち追加するだけで自動登録され、平日毎朝10:00に【神シグナル銘柄】が届くようになります。\n"
                f"（管理者の村本さんは「知人一覧」と送れば登録者数とメンバーを確認できます）"
            )
            reply_line_message(reply_token, invite_msg)
            continue

        # 1. Trigger Scan (e.g. "スキャン", "スナイプ", "今すぐ", "スキャン 60 25 10 1")
        if text.startswith("スキャン") or text.startswith("スナイプ") or "スキャン実行" in text:
            # Parse parameters if given
            # Format: "スキャン 60 25 10 1" or "🎯 【スナイパースキャン実行】\n照合:60日 | 保有:25日..."
            match_days = 50
            hold_days = 15
            thresh = 8.0
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
                f"「スキャン」と送信すると、東証プライム全社から勝率72.7%・超過α+1.99%の神シグナル銘柄を即座にスキャンします。\n\n"
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
