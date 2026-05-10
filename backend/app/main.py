from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
import string
import time
import datetime as dt
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl

import base64

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from itsdangerous import BadSignature, URLSafeSerializer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sendvpn")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8277937596:AAGalxgUyYDUw5_wQuL7yB1_oDaW7brGOfU")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "jutsovpnbot")
SESSION_SECRET = os.environ.get("SESSION_SECRET", "sendvpn-dev-secret-change-me")
ADMIN_IDS = {
    int(value)
    for value in os.environ.get("ADMIN_IDS", "8228905313").replace(",", " ").split()
    if value.strip().isdigit()
}
SUB_BASE = os.environ.get("SUB_BASE", "https://sub.jutsovpn.online")
COOKIE_NAME = "sendvpn_session"

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI()
serializer = URLSafeSerializer(SESSION_SECRET, salt="sendvpn")

# In-memory data stores (persisted to disk via STATE_FILE — see persist_state / load_state below).
USERS: dict[int, dict[str, Any]] = {}
PAYMENTS: list[dict[str, Any]] = []
BROADCASTS: list[dict[str, Any]] = []
ADMIN_LOG: list[dict[str, Any]] = []
PROMOS: dict[str, dict[str, Any]] = {}  # code -> {kind,value,limit,used,expires_at,created_by,created_at,note}

DATA_DIR = Path(os.environ.get("DATA_DIR") or "/data")
try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    DATA_DIR = Path("/tmp")
STATE_FILE = DATA_DIR / "state.json"
_state_lock = asyncio.Lock() if False else None  # placeholder; we use sync writes
_state_dirty = False


def _persist_state_sync() -> None:
    """Atomic JSON dump of all in-memory state. Best-effort."""
    try:
        snapshot = {
            "version": 1,
            "saved_at": int(time.time()),
            "users": {str(k): v for k, v in USERS.items()},
            "payments": PAYMENTS[-5000:],
            "broadcasts": BROADCASTS[-2000:],
            "promos": PROMOS,
            "admin_log": ADMIN_LOG[-2000:],
            "config_overrides": {k: CONFIG.get(k) for k in (
                "tariffs", "providers",
                "stars_rate_rub", "stars_rate_usd", "stars_packs",
                "referral_trial_bonus_days", "referral_purchase_percent",
                "extra_device_price", "trial_days", "site_locked", "site_locked_message",
                "bot_locked", "bot_locked_message", "empty_image_url",
                "channel_url", "support_url",
                "bot_start_text", "bot_button_app", "bot_button_info", "bot_button_admin",
                "bot_info_text", "bot_button_support", "bot_button_channel", "bot_button_back",
            ) if k in CONFIG},
        }
        tmp = STATE_FILE.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False)
        tmp.replace(STATE_FILE)
    except Exception:
        logger.exception("persist_state failed")


def mark_dirty() -> None:
    """Mark state as needing persistence; flushed by background task."""
    global _state_dirty
    _state_dirty = True


def _load_state_sync() -> None:
    """Load state from disk into in-memory stores. Best-effort."""
    global USERS, PAYMENTS, BROADCASTS, PROMOS, ADMIN_LOG
    try:
        if not STATE_FILE.exists():
            return
        with STATE_FILE.open("r", encoding="utf-8") as f:
            snap = json.load(f)
        users = snap.get("users") or {}
        if isinstance(users, dict):
            for k, v in users.items():
                try:
                    USERS[int(k)] = v
                except Exception:
                    pass
        payments = snap.get("payments")
        if isinstance(payments, list):
            PAYMENTS[:] = payments
        broadcasts = snap.get("broadcasts")
        if isinstance(broadcasts, list):
            BROADCASTS[:] = broadcasts
        promos = snap.get("promos")
        if isinstance(promos, dict):
            PROMOS.update(promos)
        admin_log = snap.get("admin_log")
        if isinstance(admin_log, list):
            ADMIN_LOG[:] = admin_log
        cfg_over = snap.get("config_overrides") or {}
        if isinstance(cfg_over, dict):
            for k, v in cfg_over.items():
                if v is not None:
                    CONFIG[k] = v
        logger.info("state loaded: users=%d payments=%d promos=%d", len(USERS), len(PAYMENTS), len(PROMOS))
    except Exception:
        logger.exception("load_state failed")
# Detailed per-user activity events (page views, taps, purchases). Capped per user.
USER_EVENTS: dict[int, list[dict[str, Any]]] = {}
USER_EVENTS_GLOBAL: list[dict[str, Any]] = []
USER_EVENTS_MAX_PER_USER = 1000
USER_EVENTS_MAX_GLOBAL = 20000
APP_STARTED_AT: float = time.time()
CONFIG: dict[str, Any] = {
    "bot_username": BOT_USERNAME,
    "channel_url": "https://t.me/jutsovpn",
    "support_url": "https://t.me/jutsodev",
    "providers": {"sbp": True, "card": True, "crypto": False, "balance": True, "stars": True},
    "tariffs": [
        {"key": "m1", "name": "1 месяц", "days": 30, "devices": 3, "price_rub": 99, "price_stars": 66, "enabled": True},
        {"key": "m3", "name": "3 месяца", "days": 90, "devices": 4, "price_rub": 270, "price_stars": 180, "enabled": True},
        {"key": "m6", "name": "6 месяцев", "days": 180, "devices": 5, "price_rub": 480, "price_stars": 320, "enabled": True},
        {"key": "y1", "name": "1 год", "days": 365, "devices": 5, "price_rub": 870, "price_stars": 580, "enabled": True},
    ],
    "extra_device_rub": 49,
    "free_trial_days": 3,
    "referral_trial_bonus_days": 4,
    "referral_purchase_percent": 20,
    "site_locked": False,
    "site_locked_message": "",
    "bot_locked": False,
    "bot_locked_message": "",
    # Empty-state image shown on the main "Pока пусто" devices block.
    "empty_image_url": "https://i.ibb.co/5XgDpWSf/Chat-GPT-Image-30-2026-17-18-25.png",
    # Stars / currency
    "stars_rate_rub": 1.39,         # 1 star ≈ 1.39 ₽
    "stars_rate_usd": 0.013,        # 1 star ≈ $0.013
    "usd_rate_rub": 0.011,          # $1 ≈ 92 ₽ → 1 ₽ ≈ $0.011
    "stars_packs": [50, 100, 500, 1000, 2000],
    "stars_payload_secret": secrets.token_urlsafe(16),
    # Bot UI strings — editable by admin via /admin in the bot. HTML allowed.
    "bot_start_text": "<b>Ваш профиль:</b>\n<blockquote>Откройте приложение. Для подключения VPN.</blockquote>",
    "bot_button_app": "📱 Открыть приложение",
    "bot_button_info": "ℹ Информация",
    "bot_button_admin": "🛠 Админ-панель",
    "bot_info_text": "<b>Информация</b>\n<blockquote>JutsoVPN — быстрый и приватный VPN с подпиской через Telegram.</blockquote>",
    "bot_button_support": "💬 Поддержка",
    "bot_button_channel": "📢 Новостной канал",
    "bot_button_back": "◀ Назад",
}

# Local in-memory image store: maps an opaque id -> (mime, bytes).
UPLOADED_IMAGES: dict[str, tuple[str, bytes]] = {}

# Internal-API key used by the bot to credit balances after successful payments.
INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "sendvpn-internal-prod-2026-Tt7Lp9Qr")


# ---------------------------------------------------------------------------
# Telegram initData validation
# ---------------------------------------------------------------------------


def parse_init_data(init_data: str) -> tuple[dict[str, str], str | None]:
    if not init_data:
        return {}, None
    try:
        pairs = parse_qsl(init_data, keep_blank_values=True)
    except ValueError:
        return {}, None
    data = dict(pairs)
    received_hash = data.pop("hash", None)
    return data, received_hash


def compute_init_data_hash(data: dict[str, str], bot_token: str) -> str:
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    return hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()


def verify_init_data(init_data: str, bot_token: str) -> tuple[dict[str, Any], bool]:
    data, received_hash = parse_init_data(init_data)
    user_raw = data.get("user")
    user: dict[str, Any] = {}
    if user_raw:
        try:
            user = json.loads(user_raw)
        except json.JSONDecodeError:
            user = {}
    payload = {
        "user": user,
        "auth_date": int(data.get("auth_date") or 0),
        "query_id": data.get("query_id"),
        "start_param": data.get("start_param"),
    }
    if not bot_token or not received_hash:
        return payload, False
    expected = compute_init_data_hash(data, bot_token)
    verified = hmac.compare_digest(expected, received_hash)
    if not verified:
        for skip in ("signature", "chat", "chat_type", "chat_instance", "can_send_after"):
            if skip in data:
                trimmed = {k: v for k, v in data.items() if k != skip}
                if hmac.compare_digest(compute_init_data_hash(trimmed, bot_token), received_hash):
                    verified = True
                    break
    return payload, verified


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_SUB_ALPHABET = string.ascii_uppercase + string.ascii_lowercase + string.digits


def make_sub_uuid() -> str:
    return "".join(secrets.choice(_SUB_ALPHABET) for _ in range(12))


def make_session_cookie(tg_id: int) -> str:
    return serializer.dumps({"tg_id": tg_id, "ts": int(time.time())})


def read_session_cookie(value: str | None) -> int | None:
    if not value:
        return None
    try:
        payload = serializer.loads(value)
    except BadSignature:
        return None
    tg_id = payload.get("tg_id")
    return int(tg_id) if tg_id is not None else None


def display_name(user: dict[str, Any]) -> str:
    parts = [user.get("first_name") or "", user.get("last_name") or ""]
    name = " ".join(p for p in parts if p).strip()
    if name:
        return name
    return user.get("username") or "Профиль"


def is_admin_id(tg_id: int | None) -> bool:
    return bool(tg_id) and tg_id in ADMIN_IDS


def ensure_record(tg_id: int, user: dict[str, Any] | None = None) -> dict[str, Any]:
    record = USERS.get(tg_id)
    if record is None:
        record = {
            "id": tg_id,
            "created_at": int(time.time()),
            "balance": 0,
            "free_used": False,
            "banned": False,
            "subscription": {},
            "devices": [],
            "referrals": [],
            "sub_uuid": make_sub_uuid(),
        }
        USERS[tg_id] = record
    if user:
        for key in ("first_name", "last_name", "username", "language_code", "photo_url", "is_premium"):
            value = user.get(key)
            if value is not None:
                record[key] = value
    if not record.get("sub_uuid"):
        record["sub_uuid"] = make_sub_uuid()
    record.setdefault("devices", [])
    record.setdefault("referrals", [])
    record.setdefault("balance", 0)
    record.setdefault("free_used", False)
    record.setdefault("banned", False)
    record.setdefault("subscription", {})
    return record


_RU_MONTHS = [
    "", "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]


def format_expires_human(expires_at: int) -> str:
    moment = datetime.fromtimestamp(expires_at, tz=timezone.utc)
    # Human-readable Russian date: "12 мая 2026"
    return f"{moment.day} {_RU_MONTHS[moment.month]} {moment.year}"


def referral_code_for(record: dict[str, Any]) -> str:
    code = record.get("ref_code")
    if not code:
        # 8-character mixed-case alphanumeric (Q != q). Reuses the same alphabet
        # as sub_uuid for consistency.
        code = make_sub_uuid()[:8]
        record["ref_code"] = code
    return code


def referral_link_for(record_or_id) -> str:
    if isinstance(record_or_id, dict):
        return f"https://t.me/{BOT_USERNAME}?start={referral_code_for(record_or_id)}"
    rec = USERS.get(int(record_or_id or 0))
    if rec:
        return f"https://t.me/{BOT_USERNAME}?start={referral_code_for(rec)}"
    return f"https://t.me/{BOT_USERNAME}"


def sub_url_for(record: dict[str, Any]) -> str:
    sub_uuid = record.get("sub_uuid") or make_sub_uuid()
    record["sub_uuid"] = sub_uuid
    return f"{SUB_BASE.rstrip('/')}/{sub_uuid}"


def compute_subscription(record: dict[str, Any]) -> dict[str, Any]:
    sub = record.get("subscription") or {}
    expires_at = int(sub.get("expires_at") or 0)
    now = int(time.time())
    days_left = max(0, (expires_at - now) // 86400) if expires_at else 0
    has_subscription = expires_at > now
    return {
        "sub_url": sub_url_for(record) if expires_at else "",
        "days_left": days_left,
        "expires_at": expires_at,
        "expires_human": format_expires_human(expires_at) if expires_at else "",
        "devices_active": int(sub.get("devices_active") or 0),
        "devices_max": int(sub.get("devices_max") or 0),
        "traffic_used_bytes": int(sub.get("traffic_used_bytes") or 0),
        "traffic_limit_bytes": int(sub.get("traffic_limit_bytes") or 0),
        "tariff_name": sub.get("tariff_name") or "",
        "tariff_total_days": int(sub.get("tariff_total_days") or 0),
        "has_subscription": has_subscription,
        "free_used": bool(record.get("free_used")),
        "needs_free_trial": (not bool(record.get("free_used"))) and not has_subscription,
    }


def build_profile(record: dict[str, Any]) -> dict[str, Any]:
    tg_id = int(record.get("id") or 0)
    return {
        "tg_id": tg_id,
        "name": display_name(record),
        "first_name": record.get("first_name") or "",
        "last_name": record.get("last_name") or "",
        "username": record.get("username") or "",
        "login": record.get("username") or str(tg_id) or "—",
        "photo_url": record.get("photo_url") or "",
        "language_code": record.get("language_code") or "",
        "is_premium": bool(record.get("is_premium")),
        "is_admin": is_admin_id(tg_id),
    }


def build_referrals(record: dict[str, Any]) -> dict[str, Any]:
    tg_id = int(record.get("id") or 0)
    invited = list(record.get("referrals") or [])
    active = [item for item in invited if item.get("active")]
    bonus_total = sum(int(item.get("bonus_rub") or 0) for item in invited)
    return {
        "link": referral_link_for(record),
        "code": referral_code_for(record),
        "total": len(invited),
        "active": len(active),
        "bonus_total": bonus_total,
        "trial_bonus_days": int(CONFIG.get("referral_trial_bonus_days") or 0),
        "purchase_percent": int(CONFIG.get("referral_purchase_percent") or 0),
    }


def build_dashboard(record: dict[str, Any]) -> dict[str, Any]:
    sub = record.get("subscription") or {}
    return {
        "profile": build_profile(record),
        "subscription": compute_subscription(record),
        "devices": list(record.get("devices") or []),
        "balance": {"amount": int(record.get("balance") or 0), "currency": "RUB"},
        "traffic": {
            "used_bytes": int(sub.get("traffic_used_bytes") or 0),
            "limit_bytes": int(sub.get("traffic_limit_bytes") or 0),
        },
        "referrals": build_referrals(record),
        "meta": {
            "has_pending_payments": False,
            "pending_payments_count": 0,
            "site_locked": bool(CONFIG.get("site_locked")),
        },
    }


def build_session(record: dict[str, Any]) -> dict[str, Any]:
    profile = build_profile(record)
    return {
        "tg_id": profile["tg_id"],
        "name": profile["name"],
        "username": profile["username"],
        "is_admin": profile["is_admin"],
        "is_new_user": int(time.time()) - int(record.get("created_at") or 0) < 24 * 3600,
        "auth_method": "telegram_webapp",
    }


def get_current_user_id(request: Request) -> int | None:
    return read_session_cookie(request.cookies.get(COOKIE_NAME))


def attach_session_cookie(response: Response, tg_id: int) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=make_session_cookie(tg_id),
        httponly=True,
        secure=True,
        samesite="none",
        max_age=60 * 60 * 24 * 7,
        path="/",
    )


def admin_record(request: Request) -> dict[str, Any]:
    """Return the admin's user record. Auto-bootstraps a record on cold-start
    machines so that admin endpoints don't 403 just because in-memory state
    was wiped between requests (Fly auto-stop/auto-start)."""
    tg_id = get_current_user_id(request)
    if not is_admin_id(tg_id):
        raise HTTPException(status_code=403, detail="forbidden")
    record = USERS.get(tg_id)
    if not record:
        record = ensure_record(tg_id, {"first_name": "Admin", "username": "admin"})
        record["verified"] = True
    record["last_seen"] = int(time.time())
    return record


def log_admin(actor_id: int, action: str, target_id: int | None = None, payload: dict[str, Any] | None = None) -> None:
    ADMIN_LOG.append(
        {
            "ts": int(time.time()),
            "actor": actor_id,
            "action": action,
            "target": target_id,
            "payload": payload or {},
        }
    )
    ADMIN_LOG[:] = ADMIN_LOG[-500:]


def record_event(
    tg_id: int | None,
    event_type: str,
    label: str | None = None,
    payload: dict[str, Any] | None = None,
    source: str = "frontend",
) -> dict[str, Any]:
    """Append a per-user activity event (capped) and a global ring."""
    event = {
        "ts": int(time.time()),
        "tg_id": int(tg_id) if tg_id else None,
        "type": str(event_type)[:48],
        "label": (str(label)[:160] if label is not None else None),
        "payload": (payload or {}),
        "source": source,
    }
    if event["tg_id"]:
        bucket = USER_EVENTS.setdefault(event["tg_id"], [])
        bucket.append(event)
        if len(bucket) > USER_EVENTS_MAX_PER_USER:
            del bucket[: len(bucket) - USER_EVENTS_MAX_PER_USER]
    USER_EVENTS_GLOBAL.append(event)
    if len(USER_EVENTS_GLOBAL) > USER_EVENTS_MAX_GLOBAL:
        del USER_EVENTS_GLOBAL[: len(USER_EVENTS_GLOBAL) - USER_EVENTS_MAX_GLOBAL]
    return event


# ---------------------------------------------------------------------------
# User-facing endpoints
# ---------------------------------------------------------------------------


def _public_tariffs() -> list[dict[str, Any]]:
    """Return tariffs with both `price_rub` (admin) and `rub` (front-end) keys."""
    out: list[dict[str, Any]] = []
    for t in CONFIG.get("tariffs") or []:
        rub = int(t.get("price_rub") or t.get("rub") or 0)
        original = int(t.get("original_rub") or rub)
        item = dict(t)
        item["rub"] = rub
        item["price_rub"] = rub
        item["original_rub"] = original
        item["has_discount"] = bool(t.get("has_discount") and original > rub)
        out.append(item)
    return out


@app.get("/api/config")
async def api_config() -> JSONResponse:
    return JSONResponse(
        {
            "bot_username": CONFIG["bot_username"],
            "channel_url": CONFIG["channel_url"],
            "support_url": CONFIG["support_url"],
            "providers": CONFIG["providers"],
            "tariffs": _public_tariffs(),
            "extra_device_rub": CONFIG["extra_device_rub"],
            "stars_rate_rub": CONFIG.get("stars_rate_rub"),
            "stars_rate_usd": CONFIG.get("stars_rate_usd"),
            "usd_rate_rub": CONFIG.get("usd_rate_rub"),
            "stars_packs": CONFIG.get("stars_packs", [50, 100, 500, 1000, 2000]),
            "empty_image_url": CONFIG.get("empty_image_url") or "",
            "site_locked": bool(CONFIG.get("site_locked")),
            "site_locked_message": CONFIG.get("site_locked_message") or "",
            "admin_ids": sorted(ADMIN_IDS),
            "sub_page_url": CONFIG.get("sub_page_url") or "/sub",
        }
    )


@app.get("/api/config/maintenance")
async def api_maintenance_state() -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "site_locked": bool(CONFIG.get("site_locked")),
            "site_locked_message": CONFIG.get("site_locked_message") or "",
            "bot_locked": bool(CONFIG.get("bot_locked")),
            "bot_locked_message": CONFIG.get("bot_locked_message") or "",
        }
    )


@app.post("/api/auth/telegram-webapp")
async def api_auth_telegram_webapp(request: Request) -> Response:
    body = await request.json()
    init_data = body.get("initData") or body.get("init_data") or ""
    payload, verified = verify_init_data(init_data, BOT_TOKEN)
    user = payload["user"]
    if not user or not user.get("id"):
        return JSONResponse({"ok": False, "error": "invalid_init_data"}, status_code=401)
    tg_id = int(user["id"])
    record = ensure_record(tg_id, user)
    record["auth_date"] = payload["auth_date"]
    record["verified"] = verified
    record["last_seen"] = int(time.time())
    response = JSONResponse(
        {
            "ok": True,
            "verified": verified,
            "session": build_session(record),
            "dashboard": build_dashboard(record),
        }
    )
    attach_session_cookie(response, tg_id)
    return response


@app.post("/api/auth/telegram")
async def api_auth_telegram(request: Request) -> Response:
    body = await request.json()
    tg_id = int(body.get("id") or 0)
    if not tg_id:
        return JSONResponse({"ok": False, "error": "invalid_user"}, status_code=400)
    record = ensure_record(tg_id, body)
    record["last_seen"] = int(time.time())
    response = JSONResponse({"ok": True, "session": build_session(record), "dashboard": build_dashboard(record)})
    attach_session_cookie(response, tg_id)
    return response


@app.get("/api/session")
async def api_session(request: Request) -> JSONResponse:
    tg_id = get_current_user_id(request)
    record = USERS.get(tg_id) if tg_id else None
    if not record:
        return JSONResponse(
            {
                "ok": True,
                "authenticated": False,
                "session": None,
                "dashboard": None,
                "success_events": [],
                "notifications": [],
            }
        )
    return JSONResponse(
        {
            "ok": True,
            "authenticated": True,
            "session": build_session(record),
            "dashboard": build_dashboard(record),
            "success_events": [],
            "notifications": [],
        }
    )


@app.post("/api/session/refresh-profile")
async def api_refresh_profile(request: Request) -> JSONResponse:
    tg_id = get_current_user_id(request)
    record = USERS.get(tg_id) if tg_id else None
    if not record:
        return JSONResponse({"ok": False, "error": "not_authenticated"}, status_code=401)
    return JSONResponse({"ok": True, "session": build_session(record), "dashboard": build_dashboard(record)})


@app.post("/api/session/logout-all")
@app.post("/api/logout")
async def api_logout() -> JSONResponse:
    response = JSONResponse({"ok": True})
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


@app.post("/api/bot/profile-gate")
async def api_profile_gate() -> JSONResponse:
    return JSONResponse({"ok": True})


@app.post("/api/free-trial")
async def api_free_trial(request: Request) -> JSONResponse:
    tg_id = get_current_user_id(request)
    record = USERS.get(tg_id) if tg_id else None
    if not record:
        return JSONResponse({"ok": False, "error": "not_authenticated"}, status_code=401)
    if record.get("banned"):
        return JSONResponse({"ok": False, "error": "Аккаунт заблокирован"}, status_code=403)
    if record.get("free_used"):
        return JSONResponse({"ok": False, "error": "Пробный период уже использован"}, status_code=400)
    days = int(CONFIG.get("free_trial_days") or 3)
    sub = record.get("subscription") or {}
    base = max(int(sub.get("expires_at") or 0), int(time.time()))
    record["sub_uuid"] = make_sub_uuid()
    record["subscription"] = {
        **sub,
        "expires_at": base + days * 86400,
        "tariff_name": "Пробный",
        "tariff_total_days": days,
        "devices_max": max(int(sub.get("devices_max") or 0), 1),
        "devices_active": int(sub.get("devices_active") or 0),
        "traffic_used_bytes": int(sub.get("traffic_used_bytes") or 0),
        "traffic_limit_bytes": int(sub.get("traffic_limit_bytes") or 0),
    }
    record["free_used"] = True
    record["last_seen"] = int(time.time())
    return JSONResponse({"ok": True, "session": build_session(record), "dashboard": build_dashboard(record)})


@app.post("/api/payment")
async def api_payment_create(request: Request) -> JSONResponse:
    tg_id = get_current_user_id(request)
    if not tg_id or not USERS.get(tg_id):
        return JSONResponse({"ok": False, "error": "not_authenticated"}, status_code=401)
    body = await request.json()
    payment = {
        "id": secrets.token_hex(8),
        "tg_id": tg_id,
        "tariff": body.get("tariff"),
        "provider": body.get("provider"),
        "amount": body.get("amount"),
        "status": "pending",
        "created_at": int(time.time()),
    }
    PAYMENTS.append(payment)
    return JSONResponse({"ok": True, "payment": payment, "message": "Платёж создан, ждёт подтверждения админа"})


@app.post("/api/payment/check")
async def api_payment_check(request: Request) -> JSONResponse:
    tg_id = get_current_user_id(request)
    record = USERS.get(tg_id) if tg_id else None
    if not record:
        return JSONResponse({"ok": True, "dashboard": None})
    return JSONResponse({"ok": True, "dashboard": build_dashboard(record)})


@app.post("/api/payment/stars/create-invoice")
async def api_payment_stars_create_invoice(request: Request) -> JSONResponse:
    """Create a Telegram Stars invoice link for the current user.

    Front-end picks one of the predefined packs (50/100/500/1000/2000 ⭐).
    We call Telegram Bot API `createInvoiceLink` with currency=XTR and return
    the link; the Mini App then opens it via `Telegram.WebApp.openInvoice`.
    """
    tg_id = get_current_user_id(request)
    record = USERS.get(tg_id) if tg_id else None
    if not record:
        return JSONResponse({"ok": False, "error": "not_authenticated"}, status_code=401)
    if record.get("banned"):
        return JSONResponse({"ok": False, "error": "Аккаунт заблокирован"}, status_code=403)
    body = await request.json()
    try:
        stars = int(body.get("stars") or 0)
    except (TypeError, ValueError):
        stars = 0
    allowed = set(int(x) for x in CONFIG.get("stars_packs", []))
    if stars not in allowed:
        return JSONResponse({"ok": False, "error": "Недопустимое количество звёзд"}, status_code=400)
    currency_pref = (body.get("currency") or "rub").lower()
    if not BOT_TOKEN:
        return JSONResponse({"ok": False, "error": "bot token not configured"}, status_code=503)
    try:
        import aiohttp  # noqa: WPS433
    except ImportError:
        return JSONResponse({"ok": False, "error": "aiohttp not installed"}, status_code=500)
    payload_id = secrets.token_hex(8)
    payload_str = f"stars:{tg_id}:{stars}:{payload_id}"
    title = f"{stars} ⭐ — SendVPN"
    description = f"Пополнение баланса SendVPN ({stars} ⭐)"
    invoice_payload = {
        "title": title,
        "description": description,
        "payload": payload_str,
        "currency": "XTR",
        "prices": [{"label": f"{stars} Stars", "amount": stars}],
    }
    timeout = aiohttp.ClientTimeout(total=15)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/createInvoiceLink",
                json=invoice_payload,
            ) as response:
                data = await response.json()
    except Exception as exc:  # noqa: BLE001
        logger.exception("createInvoiceLink failed")
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=502)
    if not data.get("ok"):
        return JSONResponse(
            {"ok": False, "error": data.get("description") or "telegram_error"},
            status_code=502,
        )
    invoice_link = data.get("result")
    pending = {
        "id": payload_id,
        "tg_id": tg_id,
        "stars": stars,
        "status": "pending",
        "currency": "XTR",
        "provider": "stars",
        "payload": payload_str,
        "created_at": int(time.time()),
        "currency_pref": currency_pref,
    }
    PAYMENTS.append(pending)
    return JSONResponse(
        {
            "ok": True,
            "invoice_link": invoice_link,
            "payment_id": payload_id,
            "stars": stars,
        }
    )


@app.post("/api/internal/stars-paid")
async def api_internal_stars_paid(request: Request) -> JSONResponse:
    """Webhook endpoint called by the bot when it receives `successful_payment`.

    Authentication: requires header `X-Internal-Key: <INTERNAL_API_KEY>`.
    Credits the user's balance based on the configured `stars_rate_rub`.
    """
    if request.headers.get("x-internal-key") != INTERNAL_API_KEY:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    body = await request.json()
    payload_str = str(body.get("payload") or "")
    if not payload_str.startswith("stars:"):
        return JSONResponse({"ok": False, "error": "bad_payload"}, status_code=400)
    try:
        _, tg_id_raw, stars_raw, payment_id = payload_str.split(":", 3)
        tg_id = int(tg_id_raw)
        stars = int(stars_raw)
    except (ValueError, IndexError):
        return JSONResponse({"ok": False, "error": "bad_payload"}, status_code=400)
    record = USERS.get(tg_id)
    if not record:
        return JSONResponse({"ok": False, "error": "user_not_found"}, status_code=404)
    rate_rub = float(CONFIG.get("stars_rate_rub") or 1.39)
    rub_credit = round(stars * rate_rub, 2)
    record["balance"] = int(record.get("balance") or 0) + int(rub_credit)
    record["last_seen"] = int(time.time())
    # Record successful payment for admin visibility
    matching = next((p for p in PAYMENTS if p.get("id") == payment_id), None)
    if matching:
        matching["status"] = "completed"
        matching["completed_at"] = int(time.time())
        matching["amount"] = int(rub_credit)
    else:
        PAYMENTS.append(
            {
                "id": payment_id,
                "tg_id": tg_id,
                "stars": stars,
                "amount": int(rub_credit),
                "status": "completed",
                "provider": "stars",
                "currency": "XTR",
                "created_at": int(time.time()),
                "completed_at": int(time.time()),
            }
        )
    log_admin(0, "stars_paid", tg_id, {"stars": stars, "rub": int(rub_credit), "id": payment_id})
    return JSONResponse(
        {
            "ok": True,
            "credited_rub": int(rub_credit),
            "balance": int(record["balance"]),
        }
    )


@app.get("/api/internal/key")
async def api_internal_key(request: Request) -> JSONResponse:
    """Admin-only: reveal internal API key for the bot to call us back."""
    actor = admin_record(request)
    log_admin(actor["id"], "internal_key_view", None, None)
    return JSONResponse({"ok": True, "key": INTERNAL_API_KEY})


_BOT_SETTINGS_STR_KEYS = (
    "bot_start_text", "bot_button_app", "bot_button_info", "bot_button_admin",
    "bot_info_text", "bot_button_support", "bot_button_channel", "bot_button_back",
    "support_url", "channel_url",
    "bot_locked_message",
)
_BOT_SETTINGS_BOOL_KEYS = ("bot_locked",)


def _bot_settings_snapshot() -> dict[str, Any]:
    snap: dict[str, Any] = {k: CONFIG.get(k, "") for k in _BOT_SETTINGS_STR_KEYS}
    for k in _BOT_SETTINGS_BOOL_KEYS:
        snap[k] = bool(CONFIG.get(k))
    return snap


@app.get("/api/internal/bot-settings")
async def api_internal_bot_settings_get(request: Request) -> JSONResponse:
    """Bot-only: read editable bot UI strings + toggles."""
    if request.headers.get("x-internal-key") != INTERNAL_API_KEY:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    return JSONResponse({"ok": True, "settings": _bot_settings_snapshot()})


@app.post("/api/internal/bot-settings")
async def api_internal_bot_settings_set(request: Request) -> JSONResponse:
    """Bot-only: update one or more editable bot UI strings / toggles."""
    if request.headers.get("x-internal-key") != INTERNAL_API_KEY:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        return JSONResponse({"ok": False, "error": "bad_body"}, status_code=400)
    updated: dict[str, Any] = {}
    for k, v in body.items():
        if k in _BOT_SETTINGS_STR_KEYS and isinstance(v, str):
            CONFIG[k] = v
            updated[k] = v
        elif k in _BOT_SETTINGS_BOOL_KEYS:
            CONFIG[k] = bool(v)
            updated[k] = bool(v)
    # Mirror the maintenance flag to the Mini App so toggling the bot also
    # locks the site with the same message. One toggle covers both.
    if "bot_locked" in updated:
        CONFIG["site_locked"] = bool(updated["bot_locked"])
        updated["site_locked"] = CONFIG["site_locked"]
    if "bot_locked_message" in updated:
        CONFIG["site_locked_message"] = updated["bot_locked_message"]
        updated["site_locked_message"] = updated["bot_locked_message"]
    mark_dirty()
    return JSONResponse({"ok": True, "updated": updated, "settings": _bot_settings_snapshot()})


@app.get("/api/internal/users")
async def api_internal_users_list(request: Request, q: str = "", limit: int = 10, offset: int = 0) -> JSONResponse:
    """Bot-only: paginated user list for the in-bot admin panel."""
    if request.headers.get("x-internal-key") != INTERNAL_API_KEY:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    items = list(USERS.values())
    if q:
        ql = q.lower().strip()
        items = [
            u for u in items
            if ql in str(u.get("id") or "")
            or ql in (u.get("username") or "").lower()
            or ql in (u.get("first_name") or "").lower()
            or ql in (u.get("last_name") or "").lower()
        ]
    items.sort(key=lambda u: int(u.get("last_seen") or u.get("created_at") or 0), reverse=True)
    total = len(items)
    limit = max(1, min(50, int(limit or 10)))
    offset = max(0, int(offset or 0))
    page_items = items[offset : offset + limit]
    return JSONResponse({"ok": True, "total": total, "limit": limit, "offset": offset, "items": [_user_summary(u) for u in page_items]})


@app.get("/api/internal/users/{tg_id:int}")
async def api_internal_user_detail(request: Request, tg_id: int) -> JSONResponse:
    """Bot-only: full detail for one user."""
    if request.headers.get("x-internal-key") != INTERNAL_API_KEY:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    record = USERS.get(int(tg_id))
    if not record:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    summary = _user_summary(record)
    summary["devices"] = list(record.get("devices") or [])
    summary["referrals"] = list(record.get("referrals") or [])
    summary["ref_code"] = record.get("ref_code") or ""
    summary["referred_by"] = int(record.get("referred_by") or 0)
    return JSONResponse({"ok": True, "user": summary})


@app.post("/api/internal/users/{tg_id:int}/action")
async def api_internal_user_action(request: Request, tg_id: int) -> JSONResponse:
    """Bot-only: unified user action dispatcher (ban/unban/grant_days/...)."""
    if request.headers.get("x-internal-key") != INTERNAL_API_KEY:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    try:
        body = await request.json()
    except Exception:
        body = {}
    action = str((body or {}).get("action") or "").strip()
    record = USERS.get(int(tg_id))
    if not record:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    actor_id = next(iter(ADMIN_IDS), 0)
    if action == "ban":
        record["banned"] = True
    elif action == "unban":
        record["banned"] = False
    elif action == "revoke":
        record["subscription"] = {}
    elif action == "reset_trial":
        record["free_used"] = False
    elif action == "regen_sub":
        record["sub_uuid"] = make_sub_uuid()
    elif action == "clear_devices":
        record["devices"] = []
    elif action == "grant_days":
        days = int(body.get("days") or 0)
        if days <= 0:
            return JSONResponse({"ok": False, "error": "days_required"}, status_code=400)
        sub = record.get("subscription") or {}
        base = max(int(sub.get("expires_at") or 0), int(time.time()))
        record["subscription"] = {
            **sub,
            "expires_at": base + days * 86400,
            "tariff_name": sub.get("tariff_name") or "Админ",
            "tariff_total_days": int(sub.get("tariff_total_days") or 0) + days,
            "devices_max": int(sub.get("devices_max") or 3),
            "devices_active": int(sub.get("devices_active") or 0),
            "traffic_used_bytes": int(sub.get("traffic_used_bytes") or 0),
            "traffic_limit_bytes": int(sub.get("traffic_limit_bytes") or 0),
        }
    elif action == "balance_delta":
        record["balance"] = int(record.get("balance") or 0) + int(body.get("delta") or 0)
    elif action == "balance_set":
        record["balance"] = int(body.get("value") or 0)
    elif action == "stars_delta":
        record["stars_balance"] = int(record.get("stars_balance") or 0) + int(body.get("delta") or 0)
    elif action == "delete":
        USERS.pop(int(tg_id), None)
        log_admin(actor_id, "delete_via_bot", int(tg_id), {"by": "bot"})
        mark_dirty()
        return JSONResponse({"ok": True, "deleted": True})
    else:
        return JSONResponse({"ok": False, "error": "unknown_action"}, status_code=400)
    log_admin(actor_id, f"bot_{action}", int(tg_id), body)
    mark_dirty()
    return JSONResponse({"ok": True, "user": _user_summary(record)})


@app.get("/api/internal/user/{tg_id}")
async def api_internal_user(tg_id: int, request: Request) -> JSONResponse:
    """Bot-only: fetch user snapshot for inline menus.
    Optional query params first_name / username — upsert on miss."""
    if request.headers.get("x-internal-key") != INTERNAL_API_KEY:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    record = USERS.get(int(tg_id))
    if not record:
        # Upsert on first /start so the bot always has a profile to show.
        user_payload: dict[str, Any] = {}
        for key in ("first_name", "last_name", "username", "language_code"):
            val = request.query_params.get(key)
            if val:
                user_payload[key] = val
        record = ensure_record(int(tg_id), user_payload or None)
    sub = record.get("subscription") or {}
    expires_at = int(sub.get("expires_at") or 0)
    now = int(time.time())
    days_left = max(0, (expires_at - now) // 86400) if expires_at else 0
    sub_uuid = record.get("sub_uuid") or ""
    bot_username_local = (CONFIG.get("bot_username") or "jutsovpnbot").lstrip("@")
    return JSONResponse({
        "ok": True,
        "tg_id": int(tg_id),
        "first_name": record.get("first_name") or "",
        "username": record.get("username") or "",
        "balance_rub": int(record.get("balance") or 0),
        "stars_balance": int(record.get("stars_balance") or 0),
        "free_used": bool(record.get("free_used")),
        "banned": bool(record.get("banned")),
        "tariff_name": sub.get("tariff_name") or "",
        "expires_at": expires_at,
        "expires_human": format_expires_human(expires_at) if expires_at else "",
        "days_left": int(days_left),
        "has_subscription": bool(sub.get("tariff_name") and expires_at > now),
        "sub_url": f"{SUB_BASE.rstrip('/')}/{sub_uuid}" if sub_uuid else "",
        "ref_url": f"https://t.me/{bot_username_local}?start={referral_code_for(record)}",
        "ref_code": referral_code_for(record),
        "ref_count": int(record.get("ref_count") or 0),
        "devices": len(record.get("devices") or []),
    })


@app.get("/api/push/public-key")
async def api_push_public_key() -> JSONResponse:
    return JSONResponse({"ok": True, "key": ""})


@app.post("/api/push/subscribe")
@app.post("/api/push/unsubscribe")
@app.post("/api/notifications/read")
async def api_noop() -> JSONResponse:
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# Admin endpoints (under /api/admin/*)
# ---------------------------------------------------------------------------


def _user_summary(record: dict[str, Any]) -> dict[str, Any]:
    sub = compute_subscription(record)
    return {
        "tg_id": int(record.get("id") or 0),
        "name": display_name(record),
        "username": record.get("username") or "",
        "photo_url": record.get("photo_url") or "",
        "is_premium": bool(record.get("is_premium")),
        "language_code": record.get("language_code") or "",
        "balance": int(record.get("balance") or 0),
        "free_used": bool(record.get("free_used")),
        "banned": bool(record.get("banned")),
        "verified": bool(record.get("verified")),
        "created_at": int(record.get("created_at") or 0),
        "last_seen": int(record.get("last_seen") or 0),
        "tariff_name": sub["tariff_name"],
        "expires_at": sub["expires_at"],
        "expires_human": sub["expires_human"],
        "days_left": sub["days_left"],
        "has_subscription": sub["has_subscription"],
        "sub_url": sub["sub_url"],
        "sub_uuid": record.get("sub_uuid") or "",
        "devices_active": sub["devices_active"],
        "devices_max": sub["devices_max"],
        "traffic_used_bytes": sub["traffic_used_bytes"],
        "traffic_limit_bytes": sub["traffic_limit_bytes"],
        "is_admin": is_admin_id(int(record.get("id") or 0)),
    }


@app.get("/api/admin/me")
async def api_admin_me(request: Request) -> JSONResponse:
    tg_id = get_current_user_id(request)
    return JSONResponse(
        {
            "authenticated": bool(tg_id),
            "is_admin": is_admin_id(tg_id),
            "tg_id": tg_id,
            "admin_ids": sorted(ADMIN_IDS),
        }
    )


@app.get("/api/admin/stats")
async def api_admin_stats(request: Request) -> JSONResponse:
    admin_record(request)
    now = int(time.time())
    total = len(USERS)
    active = sum(1 for u in USERS.values() if int((u.get("subscription") or {}).get("expires_at") or 0) > now)
    trial = sum(1 for u in USERS.values() if u.get("free_used"))
    banned = sum(1 for u in USERS.values() if u.get("banned"))
    revenue = sum(int(p.get("amount") or 0) for p in PAYMENTS if p.get("status") == "paid")
    pending = sum(1 for p in PAYMENTS if p.get("status") == "pending")
    return JSONResponse(
        {
            "ok": True,
            "users_total": total,
            "users_active": active,
            "users_trial": trial,
            "users_banned": banned,
            "payments_total": len(PAYMENTS),
            "payments_pending": pending,
            "revenue_rub": revenue,
            "broadcasts_total": len(BROADCASTS),
            "config_locked": bool(CONFIG.get("site_locked")),
            "now": now,
        }
    )


@app.get("/api/admin/users")
async def api_admin_users(request: Request, q: str = "", limit: int = 100, offset: int = 0) -> JSONResponse:
    admin_record(request)
    items = list(USERS.values())
    if q:
        ql = q.lower()
        items = [
            u
            for u in items
            if ql in str(u.get("id") or "")
            or ql in (u.get("username") or "").lower()
            or ql in (u.get("first_name") or "").lower()
            or ql in (u.get("last_name") or "").lower()
        ]
    items.sort(key=lambda u: int(u.get("last_seen") or u.get("created_at") or 0), reverse=True)
    total = len(items)
    items = items[offset : offset + limit]
    return JSONResponse({"ok": True, "total": total, "items": [_user_summary(u) for u in items]})


@app.get("/api/admin/users/{tg_id:int}")
async def api_admin_user(request: Request, tg_id: int) -> JSONResponse:
    admin_record(request)
    record = USERS.get(tg_id)
    if not record:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    summary = _user_summary(record)
    summary["devices"] = list(record.get("devices") or [])
    summary["referrals"] = list(record.get("referrals") or [])
    return JSONResponse({"ok": True, "user": summary})


@app.post("/api/admin/users/{tg_id:int}/ban")
async def api_admin_ban(request: Request, tg_id: int) -> JSONResponse:
    actor = admin_record(request)
    record = USERS.get(tg_id)
    if not record:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    record["banned"] = True
    log_admin(actor["id"], "ban", tg_id)
    return JSONResponse({"ok": True, "user": _user_summary(record)})


@app.post("/api/admin/users/{tg_id:int}/unban")
async def api_admin_unban(request: Request, tg_id: int) -> JSONResponse:
    actor = admin_record(request)
    record = USERS.get(tg_id)
    if not record:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    record["banned"] = False
    log_admin(actor["id"], "unban", tg_id)
    return JSONResponse({"ok": True, "user": _user_summary(record)})


@app.post("/api/admin/users/{tg_id:int}/balance")
async def api_admin_balance(request: Request, tg_id: int) -> JSONResponse:
    actor = admin_record(request)
    body = await request.json()
    record = USERS.get(tg_id)
    if not record:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    if "set" in body:
        record["balance"] = int(body["set"])
    elif "delta" in body:
        record["balance"] = int(record.get("balance") or 0) + int(body["delta"])
    log_admin(actor["id"], "balance", tg_id, body)
    return JSONResponse({"ok": True, "user": _user_summary(record)})


@app.post("/api/admin/users/{tg_id:int}/grant-days")
async def api_admin_grant_days(request: Request, tg_id: int) -> JSONResponse:
    actor = admin_record(request)
    body = await request.json()
    record = USERS.get(tg_id)
    if not record:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    days = int(body.get("days") or 0)
    if days == 0:
        return JSONResponse({"ok": False, "error": "days required"}, status_code=400)
    sub = record.get("subscription") or {}
    base = max(int(sub.get("expires_at") or 0), int(time.time()))
    record["subscription"] = {
        **sub,
        "expires_at": base + days * 86400,
        "tariff_name": body.get("tariff_name") or sub.get("tariff_name") or "Админ",
        "tariff_total_days": int(sub.get("tariff_total_days") or 0) + days,
        "devices_max": int(body.get("devices_max") or sub.get("devices_max") or 3),
        "devices_active": int(sub.get("devices_active") or 0),
        "traffic_used_bytes": int(sub.get("traffic_used_bytes") or 0),
        "traffic_limit_bytes": int(sub.get("traffic_limit_bytes") or 0),
    }
    log_admin(actor["id"], "grant_days", tg_id, {"days": days})
    return JSONResponse({"ok": True, "user": _user_summary(record)})


@app.post("/api/admin/users/{tg_id:int}/revoke")
async def api_admin_revoke(request: Request, tg_id: int) -> JSONResponse:
    actor = admin_record(request)
    record = USERS.get(tg_id)
    if not record:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    record["subscription"] = {}
    log_admin(actor["id"], "revoke", tg_id)
    return JSONResponse({"ok": True, "user": _user_summary(record)})


@app.post("/api/admin/users/{tg_id:int}/regen-sub")
async def api_admin_regen_sub(request: Request, tg_id: int) -> JSONResponse:
    actor = admin_record(request)
    record = USERS.get(tg_id)
    if not record:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    record["sub_uuid"] = make_sub_uuid()
    log_admin(actor["id"], "regen_sub", tg_id)
    return JSONResponse({"ok": True, "user": _user_summary(record)})


@app.post("/api/admin/users/{tg_id:int}/reset-trial")
async def api_admin_reset_trial(request: Request, tg_id: int) -> JSONResponse:
    actor = admin_record(request)
    record = USERS.get(tg_id)
    if not record:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    record["free_used"] = False
    log_admin(actor["id"], "reset_trial", tg_id)
    return JSONResponse({"ok": True, "user": _user_summary(record)})


@app.post("/api/admin/users/{tg_id:int}/devices/clear")
async def api_admin_clear_devices(request: Request, tg_id: int) -> JSONResponse:
    actor = admin_record(request)
    record = USERS.get(tg_id)
    if not record:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    record["devices"] = []
    log_admin(actor["id"], "clear_devices", tg_id)
    return JSONResponse({"ok": True, "user": _user_summary(record)})


@app.post("/api/admin/users/{tg_id:int}/promote")
async def api_admin_promote(request: Request, tg_id: int) -> JSONResponse:
    actor = admin_record(request)
    if tg_id not in ADMIN_IDS:
        ADMIN_IDS.add(tg_id)
    log_admin(actor["id"], "promote", tg_id)
    record = USERS.get(tg_id)
    return JSONResponse({"ok": True, "admin_ids": sorted(ADMIN_IDS), "user": _user_summary(record) if record else None})


@app.post("/api/admin/users/{tg_id:int}/demote")
async def api_admin_demote(request: Request, tg_id: int) -> JSONResponse:
    actor = admin_record(request)
    if int(actor["id"]) == tg_id:
        return JSONResponse({"ok": False, "error": "Нельзя снять права с себя"}, status_code=400)
    ADMIN_IDS.discard(tg_id)
    log_admin(actor["id"], "demote", tg_id)
    return JSONResponse({"ok": True, "admin_ids": sorted(ADMIN_IDS)})


@app.post("/api/admin/users/{tg_id:int}/delete")
async def api_admin_delete(request: Request, tg_id: int) -> JSONResponse:
    actor = admin_record(request)
    if tg_id == int(actor["id"]):
        return JSONResponse({"ok": False, "error": "Нельзя удалить себя"}, status_code=400)
    USERS.pop(tg_id, None)
    log_admin(actor["id"], "delete_user", tg_id)
    return JSONResponse({"ok": True})


@app.get("/api/admin/payments")
async def api_admin_payments(request: Request) -> JSONResponse:
    admin_record(request)
    return JSONResponse({"ok": True, "items": list(reversed(PAYMENTS))[:200]})


@app.post("/api/admin/payments/{payment_id}/approve")
async def api_admin_approve_payment(request: Request, payment_id: str) -> JSONResponse:
    actor = admin_record(request)
    payment = next((p for p in PAYMENTS if p.get("id") == payment_id), None)
    if not payment:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    payment["status"] = "paid"
    payment["approved_at"] = int(time.time())
    log_admin(actor["id"], "approve_payment", payment.get("tg_id"), {"payment_id": payment_id})
    return JSONResponse({"ok": True, "payment": payment})


@app.post("/api/admin/payments/{payment_id}/reject")
async def api_admin_reject_payment(request: Request, payment_id: str) -> JSONResponse:
    actor = admin_record(request)
    payment = next((p for p in PAYMENTS if p.get("id") == payment_id), None)
    if not payment:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    payment["status"] = "rejected"
    log_admin(actor["id"], "reject_payment", payment.get("tg_id"), {"payment_id": payment_id})
    return JSONResponse({"ok": True, "payment": payment})


@app.get("/api/admin/config")
async def api_admin_get_config(request: Request) -> JSONResponse:
    admin_record(request)
    return JSONResponse({"ok": True, "config": CONFIG})


@app.post("/api/admin/config")
async def api_admin_set_config(request: Request) -> JSONResponse:
    actor = admin_record(request)
    body = await request.json()
    allowed_keys = {
        "bot_username",
        "channel_url",
        "support_url",
        "providers",
        "tariffs",
        "extra_device_rub",
        "free_trial_days",
        "referral_trial_bonus_days",
        "referral_purchase_percent",
        "site_locked",
        "site_locked_message",
        "stars_rate_rub",
        "stars_rate_usd",
        "usd_rate_rub",
        "stars_packs",
    }
    for key, value in body.items():
        if key in allowed_keys:
            CONFIG[key] = value
    log_admin(actor["id"], "config_update", None, body)
    return JSONResponse({"ok": True, "config": CONFIG})


@app.post("/api/admin/tariffs")
async def api_admin_set_tariffs(request: Request) -> JSONResponse:
    actor = admin_record(request)
    body = await request.json()
    tariffs = body.get("tariffs") or []
    CONFIG["tariffs"] = tariffs
    log_admin(actor["id"], "tariffs_update", None, {"count": len(tariffs)})
    return JSONResponse({"ok": True, "tariffs": CONFIG["tariffs"]})


@app.post("/api/admin/lock")
async def api_admin_lock(request: Request) -> JSONResponse:
    actor = admin_record(request)
    body = await request.json()
    CONFIG["site_locked"] = bool(body.get("locked"))
    CONFIG["site_locked_message"] = str(body.get("message") or "")
    log_admin(actor["id"], "lock", None, body)
    return JSONResponse({"ok": True, "config": CONFIG})


@app.post("/api/admin/broadcast")
async def api_admin_broadcast(request: Request) -> JSONResponse:
    actor = admin_record(request)
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        return JSONResponse({"ok": False, "error": "text required"}, status_code=400)
    target = body.get("target") or "all"
    items = list(USERS.values())
    if target == "active":
        now = int(time.time())
        items = [u for u in items if int((u.get("subscription") or {}).get("expires_at") or 0) > now]
    elif target == "trial":
        items = [u for u in items if u.get("free_used")]
    recipients = [int(u["id"]) for u in items if int(u.get("id") or 0)]
    broadcast = {
        "id": secrets.token_hex(6),
        "ts": int(time.time()),
        "actor": actor["id"],
        "text": text,
        "target": target,
        "recipients_count": len(recipients),
        "status": "queued",
    }
    BROADCASTS.append(broadcast)
    log_admin(actor["id"], "broadcast", None, {"text": text, "target": target, "count": len(recipients)})
    asyncio.create_task(_send_broadcast(broadcast, recipients, text))
    return JSONResponse({"ok": True, "broadcast": broadcast})


async def _send_broadcast(broadcast: dict[str, Any], recipients: list[int], text: str) -> None:
    if not BOT_TOKEN:
        broadcast["status"] = "failed"
        broadcast["error"] = "bot token not configured"
        return
    try:
        import aiohttp
    except ImportError:
        broadcast["status"] = "failed"
        broadcast["error"] = "aiohttp not installed"
        return
    sent = 0
    failed = 0
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for chat_id in recipients:
            try:
                async with session.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
                ) as response:
                    if response.status == 200:
                        sent += 1
                    else:
                        failed += 1
            except Exception:
                failed += 1
            await asyncio.sleep(0.05)
    broadcast["status"] = "sent"
    broadcast["sent_count"] = sent
    broadcast["failed_count"] = failed


@app.get("/api/admin/broadcasts")
async def api_admin_broadcasts(request: Request) -> JSONResponse:
    admin_record(request)
    return JSONResponse({"ok": True, "items": list(reversed(BROADCASTS))[:100]})


@app.get("/api/admin/log")
async def api_admin_get_log(request: Request) -> JSONResponse:
    admin_record(request)
    return JSONResponse({"ok": True, "items": list(reversed(ADMIN_LOG))[:200]})


@app.post("/api/admin/users/{tg_id:int}/message")
async def api_admin_send_message(request: Request, tg_id: int) -> JSONResponse:
    actor = admin_record(request)
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        return JSONResponse({"ok": False, "error": "text required"}, status_code=400)
    log_admin(actor["id"], "dm", tg_id, {"text": text})
    if not BOT_TOKEN:
        return JSONResponse({"ok": False, "error": "bot token missing"}, status_code=500)
    try:
        import aiohttp

        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": tg_id, "text": text, "parse_mode": "HTML"},
            ) as response:
                ok = response.status == 200
                data = await response.json(content_type=None)
        return JSONResponse({"ok": ok, "telegram": data})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


# ---------------------------------------------------------------------------
# Admin: bulk operations, exports, system tools (extra functions)
# ---------------------------------------------------------------------------


def _parse_ids(body: dict[str, Any]) -> list[int]:
    raw = body.get("tg_ids") or body.get("ids") or []
    out: list[int] = []
    for value in raw:
        try:
            out.append(int(value))
        except (TypeError, ValueError):
            continue
    return out


@app.post("/api/admin/users/bulk/grant-days")
async def api_admin_bulk_grant_days(request: Request) -> JSONResponse:
    actor = admin_record(request)
    body = await request.json()
    days = int(body.get("days") or 0)
    ids = _parse_ids(body)
    if days <= 0 or not ids:
        return JSONResponse({"ok": False, "error": "days and ids required"}, status_code=400)
    affected: list[int] = []
    now = int(time.time())
    for tg_id in ids:
        record = USERS.get(tg_id)
        if not record:
            continue
        sub = record.get("subscription") or {}
        base = max(int(sub.get("expires_at") or 0), now)
        record["subscription"] = {
            **sub,
            "expires_at": base + days * 86400,
            "tariff_name": sub.get("tariff_name") or "Админ-бонус",
            "tariff_total_days": int(sub.get("tariff_total_days") or 0) + days,
            "devices_max": int(sub.get("devices_max") or 3),
            "devices_active": int(sub.get("devices_active") or 0),
            "traffic_used_bytes": int(sub.get("traffic_used_bytes") or 0),
            "traffic_limit_bytes": int(sub.get("traffic_limit_bytes") or 0),
        }
        affected.append(tg_id)
    log_admin(actor["id"], "bulk_grant_days", None, {"days": days, "count": len(affected)})
    return JSONResponse({"ok": True, "affected": affected})


@app.post("/api/admin/users/bulk/ban")
async def api_admin_bulk_ban(request: Request) -> JSONResponse:
    actor = admin_record(request)
    body = await request.json()
    ids = _parse_ids(body)
    affected: list[int] = []
    for tg_id in ids:
        record = USERS.get(tg_id)
        if record:
            record["banned"] = True
            affected.append(tg_id)
    log_admin(actor["id"], "bulk_ban", None, {"count": len(affected)})
    return JSONResponse({"ok": True, "affected": affected})


@app.post("/api/admin/users/bulk/unban")
async def api_admin_bulk_unban(request: Request) -> JSONResponse:
    actor = admin_record(request)
    body = await request.json()
    ids = _parse_ids(body)
    affected: list[int] = []
    for tg_id in ids:
        record = USERS.get(tg_id)
        if record:
            record["banned"] = False
            affected.append(tg_id)
    log_admin(actor["id"], "bulk_unban", None, {"count": len(affected)})
    return JSONResponse({"ok": True, "affected": affected})


@app.post("/api/admin/users/bulk/balance")
async def api_admin_bulk_balance(request: Request) -> JSONResponse:
    actor = admin_record(request)
    body = await request.json()
    ids = _parse_ids(body)
    delta = int(body.get("delta") or 0)
    set_value = body.get("set")
    affected: list[int] = []
    for tg_id in ids:
        record = USERS.get(tg_id)
        if not record:
            continue
        if set_value is not None:
            record["balance"] = int(set_value)
        else:
            record["balance"] = int(record.get("balance") or 0) + delta
        affected.append(tg_id)
    log_admin(actor["id"], "bulk_balance", None, {"count": len(affected), "delta": delta, "set": set_value})
    return JSONResponse({"ok": True, "affected": affected})


@app.post("/api/admin/users/bulk/regen-sub")
async def api_admin_bulk_regen_sub(request: Request) -> JSONResponse:
    actor = admin_record(request)
    body = await request.json()
    ids = _parse_ids(body)
    affected: list[int] = []
    for tg_id in ids:
        record = USERS.get(tg_id)
        if record:
            record["sub_uuid"] = make_sub_uuid()
            affected.append(tg_id)
    log_admin(actor["id"], "bulk_regen_sub", None, {"count": len(affected)})
    return JSONResponse({"ok": True, "affected": affected})


@app.post("/api/admin/users/bulk/revoke")
async def api_admin_bulk_revoke(request: Request) -> JSONResponse:
    actor = admin_record(request)
    body = await request.json()
    ids = _parse_ids(body)
    affected: list[int] = []
    for tg_id in ids:
        record = USERS.get(tg_id)
        if record:
            record["subscription"] = {}
            affected.append(tg_id)
    log_admin(actor["id"], "bulk_revoke", None, {"count": len(affected)})
    return JSONResponse({"ok": True, "affected": affected})


@app.post("/api/admin/users/bulk/delete")
async def api_admin_bulk_delete(request: Request) -> JSONResponse:
    actor = admin_record(request)
    body = await request.json()
    ids = _parse_ids(body)
    removed: list[int] = []
    for tg_id in ids:
        if tg_id in ADMIN_IDS:
            continue
        if USERS.pop(tg_id, None) is not None:
            removed.append(tg_id)
    log_admin(actor["id"], "bulk_delete", None, {"count": len(removed)})
    return JSONResponse({"ok": True, "deleted": removed})


@app.get("/api/admin/users/export")
async def api_admin_users_export(request: Request, format: str = "json") -> Response:
    admin_record(request)
    summaries = [_user_summary(u) for u in USERS.values()]
    if format == "csv":
        import csv
        import io

        buffer = io.StringIO()
        keys = [
            "tg_id", "name", "username", "balance", "banned", "free_used",
            "tariff_name", "days_left", "expires_at", "created_at", "last_seen",
            "sub_uuid", "sub_url",
        ]
        writer = csv.DictWriter(buffer, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        for s in summaries:
            writer.writerow({k: s.get(k) for k in keys})
        return Response(
            buffer.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=users.csv"},
        )
    return JSONResponse({"ok": True, "items": summaries})


@app.get("/api/admin/payments/export")
async def api_admin_payments_export(request: Request, format: str = "json") -> Response:
    admin_record(request)
    if format == "csv":
        import csv
        import io

        buffer = io.StringIO()
        keys = ["id", "tg_id", "amount", "stars", "provider", "status", "created_at", "completed_at"]
        writer = csv.DictWriter(buffer, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        for p in PAYMENTS:
            writer.writerow({k: p.get(k) for k in keys})
        return Response(
            buffer.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=payments.csv"},
        )
    return JSONResponse({"ok": True, "items": PAYMENTS})


@app.get("/api/admin/log/export")
async def api_admin_log_export(request: Request) -> Response:
    admin_record(request)
    return JSONResponse({"ok": True, "items": ADMIN_LOG})


@app.post("/api/admin/maintenance/clear-expired")
async def api_admin_clear_expired(request: Request) -> JSONResponse:
    actor = admin_record(request)
    now = int(time.time())
    cleared = 0
    for record in USERS.values():
        sub = record.get("subscription") or {}
        if int(sub.get("expires_at") or 0) and int(sub["expires_at"]) < now:
            record["subscription"] = {}
            cleared += 1
    log_admin(actor["id"], "clear_expired", None, {"count": cleared})
    return JSONResponse({"ok": True, "cleared": cleared})


@app.post("/api/admin/maintenance/regen-all-uuids")
async def api_admin_regen_all_uuids(request: Request) -> JSONResponse:
    actor = admin_record(request)
    count = 0
    for record in USERS.values():
        record["sub_uuid"] = make_sub_uuid()
        count += 1
    log_admin(actor["id"], "regen_all_uuids", None, {"count": count})
    return JSONResponse({"ok": True, "regenerated": count})


@app.post("/api/admin/maintenance/reset-all-trials")
async def api_admin_reset_all_trials(request: Request) -> JSONResponse:
    actor = admin_record(request)
    count = 0
    for record in USERS.values():
        if record.get("free_used"):
            record["free_used"] = False
            count += 1
    log_admin(actor["id"], "reset_all_trials", None, {"count": count})
    return JSONResponse({"ok": True, "reset": count})


@app.post("/api/admin/maintenance/clear-all-payments")
async def api_admin_clear_all_payments(request: Request) -> JSONResponse:
    actor = admin_record(request)
    count = len(PAYMENTS)
    PAYMENTS.clear()
    log_admin(actor["id"], "clear_payments", None, {"count": count})
    return JSONResponse({"ok": True, "cleared": count})


@app.post("/api/admin/maintenance/clear-broadcasts")
async def api_admin_clear_broadcasts(request: Request) -> JSONResponse:
    actor = admin_record(request)
    count = len(BROADCASTS)
    BROADCASTS.clear()
    log_admin(actor["id"], "clear_broadcasts", None, {"count": count})
    return JSONResponse({"ok": True, "cleared": count})


@app.post("/api/admin/maintenance/clear-log")
async def api_admin_clear_log(request: Request) -> JSONResponse:
    actor = admin_record(request)
    count = len(ADMIN_LOG)
    ADMIN_LOG.clear()
    log_admin(actor["id"], "clear_log", None, {"count": count})
    return JSONResponse({"ok": True, "cleared": count})


@app.get("/api/admin/health")
async def api_admin_health(request: Request) -> JSONResponse:
    admin_record(request)
    return JSONResponse(
        {
            "ok": True,
            "users": len(USERS),
            "payments": len(PAYMENTS),
            "broadcasts": len(BROADCASTS),
            "log_entries": len(ADMIN_LOG),
            "config_keys": list(CONFIG.keys()),
            "now": int(time.time()),
            "bot_token_set": bool(BOT_TOKEN),
            "internal_key_set": bool(INTERNAL_API_KEY),
        }
    )


@app.get("/api/admin/users/active")
async def api_admin_users_active(request: Request) -> JSONResponse:
    admin_record(request)
    now = int(time.time())
    items = [
        _user_summary(u)
        for u in USERS.values()
        if int((u.get("subscription") or {}).get("expires_at") or 0) > now
    ]
    items.sort(key=lambda u: int(u.get("expires_at") or 0))
    return JSONResponse({"ok": True, "items": items})


@app.get("/api/admin/users/expiring")
async def api_admin_users_expiring(request: Request, days: int = 3) -> JSONResponse:
    admin_record(request)
    now = int(time.time())
    until = now + days * 86400
    items = [
        _user_summary(u)
        for u in USERS.values()
        if now < int((u.get("subscription") or {}).get("expires_at") or 0) <= until
    ]
    items.sort(key=lambda u: int(u.get("expires_at") or 0))
    return JSONResponse({"ok": True, "items": items, "days": days})


@app.get("/api/admin/users/banned")
async def api_admin_users_banned(request: Request) -> JSONResponse:
    admin_record(request)
    items = [_user_summary(u) for u in USERS.values() if u.get("banned")]
    return JSONResponse({"ok": True, "items": items})


@app.get("/api/admin/users/inactive")
async def api_admin_users_inactive(request: Request, days: int = 14) -> JSONResponse:
    admin_record(request)
    cutoff = int(time.time()) - days * 86400
    items = [
        _user_summary(u)
        for u in USERS.values()
        if int(u.get("last_seen") or u.get("created_at") or 0) < cutoff
    ]
    return JSONResponse({"ok": True, "items": items, "days": days})


@app.post("/api/admin/payments/{payment_id}/refund")
async def api_admin_refund_payment(request: Request, payment_id: str) -> JSONResponse:
    actor = admin_record(request)
    payment = next((p for p in PAYMENTS if p.get("id") == payment_id), None)
    if not payment:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    payment["status"] = "refunded"
    payment["refunded_at"] = int(time.time())
    log_admin(actor["id"], "refund_payment", payment.get("tg_id"), {"payment_id": payment_id})
    return JSONResponse({"ok": True, "payment": payment})


@app.post("/api/admin/seed-demo")
async def api_admin_seed_demo(request: Request) -> JSONResponse:
    actor = admin_record(request)
    created: list[int] = []
    base_id = 900_000_000 + (len(USERS) % 1000) * 1000
    for i in range(5):
        tg_id = base_id + i + 1
        record = ensure_record(
            tg_id,
            {"first_name": f"Demo{i + 1}", "last_name": "User", "username": f"demo{i + 1}", "language_code": "ru"},
        )
        record["balance"] = 100 * (i + 1)
        if i % 2 == 0:
            record["free_used"] = True
            record["subscription"] = {
                "expires_at": int(time.time()) + (3 + i) * 86400,
                "tariff_name": "Демо",
                "tariff_total_days": 3 + i,
                "devices_max": 3,
                "devices_active": i,
                "traffic_used_bytes": 0,
                "traffic_limit_bytes": 0,
            }
        created.append(tg_id)
    log_admin(actor["id"], "seed_demo", None, {"created": created})
    return JSONResponse({"ok": True, "created": created})


# ---------------------------------------------------------------------------
# Extra admin endpoints (notes, tags, search, stats, mobile-friendly)
# ---------------------------------------------------------------------------


@app.get("/api/admin/system/info")
async def api_admin_system_info(request: Request) -> JSONResponse:
    admin_record(request)
    import platform
    return JSONResponse(
        {
            "ok": True,
            "users": len(USERS),
            "payments": len(PAYMENTS),
            "broadcasts": len(BROADCASTS),
            "log_entries": len(ADMIN_LOG),
            "uptime_seconds": int(time.time() - APP_STARTED_AT),
            "now": int(time.time()),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "config_keys": list(CONFIG.keys()),
            "admin_ids": sorted(ADMIN_IDS),
            "bot_token_set": bool(BOT_TOKEN),
            "internal_key_set": bool(INTERNAL_API_KEY),
        }
    )


@app.get("/api/admin/stats/timeseries")
async def api_admin_stats_timeseries(request: Request) -> JSONResponse:
    admin_record(request)
    days = 14
    now = int(time.time())
    start = now - days * 86400
    buckets = {start + i * 86400: {"new_users": 0, "payments": 0, "revenue": 0, "stars": 0} for i in range(days)}
    bucket_keys = sorted(buckets.keys())

    def floor_day(ts: int) -> int:
        for i, k in enumerate(bucket_keys):
            if i + 1 < len(bucket_keys) and bucket_keys[i + 1] > ts:
                return k
        return bucket_keys[-1]

    for u in USERS.values():
        ts = int(u.get("created_at") or 0)
        if ts >= start:
            buckets[floor_day(ts)]["new_users"] += 1
    for p in PAYMENTS:
        ts = int(p.get("created_at") or 0)
        if ts < start:
            continue
        b = buckets[floor_day(ts)]
        b["payments"] += 1
        if p.get("status") in ("paid", "completed"):
            b["revenue"] += int(p.get("amount") or 0)
            b["stars"] += int(p.get("stars") or 0)
    series = [{"day": k, "iso": time.strftime("%Y-%m-%d", time.gmtime(k)), **v} for k, v in sorted(buckets.items())]
    return JSONResponse({"ok": True, "series": series})


@app.get("/api/admin/users/top")
async def api_admin_users_top(request: Request) -> JSONResponse:
    admin_record(request)
    by = (request.query_params.get("by") or "balance").lower()
    limit = max(1, min(100, int(request.query_params.get("limit") or 10)))
    items = list(USERS.values())
    if by == "spend":
        spend: dict[int, int] = {}
        for p in PAYMENTS:
            if p.get("status") in ("paid", "completed"):
                spend[int(p.get("tg_id") or 0)] = spend.get(int(p.get("tg_id") or 0), 0) + int(p.get("amount") or 0)
        items.sort(key=lambda u: spend.get(int(u.get("id") or 0), 0), reverse=True)
        out = []
        for u in items[:limit]:
            d = _user_summary(u)
            d["spend"] = spend.get(d["tg_id"], 0)
            out.append(d)
        return JSONResponse({"ok": True, "by": by, "items": out})
    if by == "stars":
        stars: dict[int, int] = {}
        for p in PAYMENTS:
            if p.get("provider") == "stars" and p.get("status") in ("paid", "completed"):
                stars[int(p.get("tg_id") or 0)] = stars.get(int(p.get("tg_id") or 0), 0) + int(p.get("stars") or 0)
        items.sort(key=lambda u: stars.get(int(u.get("id") or 0), 0), reverse=True)
        out = []
        for u in items[:limit]:
            d = _user_summary(u)
            d["stars"] = stars.get(d["tg_id"], 0)
            out.append(d)
        return JSONResponse({"ok": True, "by": by, "items": out})
    # default: balance
    items.sort(key=lambda u: int(u.get("balance") or 0), reverse=True)
    return JSONResponse({"ok": True, "by": "balance", "items": [_user_summary(u) for u in items[:limit]]})


@app.post("/api/admin/users/{tg_id:int}/note")
async def api_admin_user_note(tg_id: int, request: Request) -> JSONResponse:
    actor = admin_record(request)
    record = USERS.get(tg_id)
    if not record:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    body = await request.json()
    note = (body.get("note") or "").strip()
    record["admin_note"] = note
    log_admin(actor["id"], "user_note", tg_id, {"note": note[:200]})
    return JSONResponse({"ok": True, "note": note})


@app.post("/api/admin/users/{tg_id:int}/tag")
async def api_admin_user_tag(tg_id: int, request: Request) -> JSONResponse:
    actor = admin_record(request)
    record = USERS.get(tg_id)
    if not record:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    body = await request.json()
    tag = (body.get("tag") or "").strip().lower()
    if not tag:
        return JSONResponse({"ok": False, "error": "empty_tag"}, status_code=400)
    tags = set(record.get("tags") or [])
    tags.add(tag)
    record["tags"] = sorted(tags)
    log_admin(actor["id"], "user_tag_add", tg_id, {"tag": tag})
    return JSONResponse({"ok": True, "tags": record["tags"]})


@app.post("/api/admin/users/{tg_id:int}/tag/remove")
async def api_admin_user_tag_remove(tg_id: int, request: Request) -> JSONResponse:
    actor = admin_record(request)
    record = USERS.get(tg_id)
    if not record:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    body = await request.json()
    tag = (body.get("tag") or "").strip().lower()
    tags = set(record.get("tags") or [])
    tags.discard(tag)
    record["tags"] = sorted(tags)
    log_admin(actor["id"], "user_tag_remove", tg_id, {"tag": tag})
    return JSONResponse({"ok": True, "tags": record["tags"]})


@app.get("/api/admin/users/by-tag/{tag}")
async def api_admin_users_by_tag(tag: str, request: Request) -> JSONResponse:
    admin_record(request)
    tag = tag.strip().lower()
    items = [u for u in USERS.values() if tag in (u.get("tags") or [])]
    return JSONResponse({"ok": True, "tag": tag, "items": [_user_summary(u) for u in items]})


@app.post("/api/admin/users/{tg_id:int}/credit-stars")
async def api_admin_credit_stars(tg_id: int, request: Request) -> JSONResponse:
    actor = admin_record(request)
    record = USERS.get(tg_id)
    if not record:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    body = await request.json()
    stars = int(body.get("stars") or 0)
    if stars <= 0:
        return JSONResponse({"ok": False, "error": "bad_amount"}, status_code=400)
    rate = float(CONFIG.get("stars_rate_rub") or 1.39)
    rub = int(round(stars * rate))
    record["balance"] = int(record.get("balance") or 0) + rub
    PAYMENTS.append(
        {
            "id": secrets.token_hex(6),
            "tg_id": tg_id,
            "stars": stars,
            "amount": rub,
            "status": "completed",
            "provider": "stars-manual",
            "currency": "XTR",
            "created_at": int(time.time()),
            "completed_at": int(time.time()),
        }
    )
    log_admin(actor["id"], "credit_stars", tg_id, {"stars": stars, "rub": rub})
    return JSONResponse({"ok": True, "credited_rub": rub, "balance": record["balance"]})


@app.post("/api/admin/users/{tg_id:int}/extend-trial")
async def api_admin_extend_trial(tg_id: int, request: Request) -> JSONResponse:
    actor = admin_record(request)
    record = USERS.get(tg_id)
    if not record:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    body = await request.json()
    days = int(body.get("days") or 0)
    if days <= 0:
        return JSONResponse({"ok": False, "error": "bad_days"}, status_code=400)
    sub = record.setdefault("subscription", {})
    base = max(int(sub.get("expires_at") or 0), int(time.time()))
    sub["expires_at"] = base + days * 86400
    sub["tariff_name"] = sub.get("tariff_name") or "Расширенный пробный"
    sub["tariff_total_days"] = int(sub.get("tariff_total_days") or 0) + days
    log_admin(actor["id"], "extend_trial", tg_id, {"days": days})
    return JSONResponse({"ok": True, "expires_at": sub["expires_at"]})


@app.post("/api/admin/maintenance/unban-all")
async def api_admin_unban_all(request: Request) -> JSONResponse:
    actor = admin_record(request)
    affected = [u["id"] for u in USERS.values() if u.get("banned")]
    for u in USERS.values():
        u["banned"] = False
    log_admin(actor["id"], "unban_all", None, {"count": len(affected)})
    return JSONResponse({"ok": True, "unbanned": len(affected)})


@app.get("/api/admin/payments/summary")
async def api_admin_payments_summary(request: Request) -> JSONResponse:
    admin_record(request)
    summary: dict[str, dict[str, int]] = {}
    for p in PAYMENTS:
        prov = str(p.get("provider") or "unknown")
        s = summary.setdefault(prov, {"count": 0, "completed": 0, "revenue_rub": 0, "stars": 0})
        s["count"] += 1
        if p.get("status") in ("paid", "completed"):
            s["completed"] += 1
            s["revenue_rub"] += int(p.get("amount") or 0)
            s["stars"] += int(p.get("stars") or 0)
    return JSONResponse({"ok": True, "summary": summary, "total": len(PAYMENTS)})


@app.post("/api/admin/users/{tg_id:int}/sub-uuid")
async def api_admin_set_sub_uuid(tg_id: int, request: Request) -> JSONResponse:
    actor = admin_record(request)
    record = USERS.get(tg_id)
    if not record:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    body = await request.json()
    raw = (body.get("uuid") or "").strip().lower()
    if not raw or len(raw) != 12 or not raw.isalnum():
        return JSONResponse({"ok": False, "error": "bad_uuid"}, status_code=400)
    record["sub_uuid"] = raw
    log_admin(actor["id"], "set_sub_uuid", tg_id, {"uuid": raw})
    return JSONResponse({"ok": True, "sub_uuid": raw, "sub_url": f"{SUB_BASE}/{raw}"})


@app.get("/api/admin/users/search")
async def api_admin_users_search(request: Request) -> JSONResponse:
    admin_record(request)
    q = (request.query_params.get("q") or "").strip().lower()
    has_sub = request.query_params.get("has_sub")
    banned = request.query_params.get("banned")
    min_balance = int(request.query_params.get("min_balance") or 0)
    max_balance_raw = request.query_params.get("max_balance")
    max_balance = int(max_balance_raw) if max_balance_raw else None
    items: list[dict[str, Any]] = []
    for u in USERS.values():
        haystack = " ".join(
            [
                str(u.get("id") or ""),
                str(u.get("username") or ""),
                str(u.get("first_name") or ""),
                str(u.get("last_name") or ""),
                str(u.get("admin_note") or ""),
                " ".join(u.get("tags") or []),
            ]
        ).lower()
        if q and q not in haystack:
            continue
        bal = int(u.get("balance") or 0)
        if bal < min_balance:
            continue
        if max_balance is not None and bal > max_balance:
            continue
        if banned == "1" and not u.get("banned"):
            continue
        if banned == "0" and u.get("banned"):
            continue
        sub = compute_subscription(u)
        if has_sub == "1" and not sub.get("active"):
            continue
        if has_sub == "0" and sub.get("active"):
            continue
        items.append(_user_summary(u))
    return JSONResponse({"ok": True, "items": items, "total": len(items), "query": q})


@app.post("/api/admin/users/{tg_id:int}/devices/add")
async def api_admin_devices_add(tg_id: int, request: Request) -> JSONResponse:
    actor = admin_record(request)
    record = USERS.get(tg_id)
    if not record:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    body = await request.json()
    name = str(body.get("name") or "Device").strip()[:60]
    devices = record.setdefault("devices", [])
    devices.append({"id": secrets.token_hex(4), "name": name, "added_at": int(time.time())})
    log_admin(actor["id"], "device_add", tg_id, {"name": name})
    return JSONResponse({"ok": True, "devices": devices})


# ---------------------------------------------------------------------------
# Maintenance flags (site / bot independently)
# ---------------------------------------------------------------------------


@app.post("/api/admin/maintenance/site/lock")
async def api_admin_lock_site(request: Request) -> JSONResponse:
    actor = admin_record(request)
    body = await request.json()
    CONFIG["site_locked"] = bool(body.get("locked", True))
    CONFIG["site_locked_message"] = str(body.get("message") or "")
    log_admin(actor["id"], "site_lock", None, {"locked": CONFIG["site_locked"], "message": CONFIG["site_locked_message"][:120]})
    return JSONResponse({"ok": True, "site_locked": CONFIG["site_locked"]})


@app.post("/api/admin/maintenance/bot/lock")
async def api_admin_lock_bot(request: Request) -> JSONResponse:
    actor = admin_record(request)
    body = await request.json()
    CONFIG["bot_locked"] = bool(body.get("locked", True))
    CONFIG["bot_locked_message"] = str(body.get("message") or "")
    log_admin(actor["id"], "bot_lock", None, {"locked": CONFIG["bot_locked"], "message": CONFIG["bot_locked_message"][:120]})
    return JSONResponse({"ok": True, "bot_locked": CONFIG["bot_locked"]})


@app.post("/api/admin/maintenance/all/lock")
async def api_admin_lock_all(request: Request) -> JSONResponse:
    actor = admin_record(request)
    body = await request.json()
    locked = bool(body.get("locked", True))
    msg = str(body.get("message") or "")
    CONFIG["site_locked"] = locked
    CONFIG["bot_locked"] = locked
    CONFIG["site_locked_message"] = msg
    CONFIG["bot_locked_message"] = msg
    log_admin(actor["id"], "lock_all", None, {"locked": locked, "message": msg[:120]})
    return JSONResponse({"ok": True, "site_locked": locked, "bot_locked": locked})


# ---------------------------------------------------------------------------
# Empty-state image (upload or URL)
# ---------------------------------------------------------------------------


_ALLOWED_IMAGE_MIMES = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"}
_MAX_IMAGE_BYTES = 2 * 1024 * 1024  # 2 MiB


@app.post("/api/admin/empty-image/url")
async def api_admin_empty_image_url(request: Request) -> JSONResponse:
    actor = admin_record(request)
    body = await request.json()
    url = (body.get("url") or "").strip()
    if url and not (url.startswith("https://") or url.startswith("http://") or url.startswith("data:image/")):
        return JSONResponse({"ok": False, "error": "bad_url"}, status_code=400)
    CONFIG["empty_image_url"] = url
    log_admin(actor["id"], "empty_image_url", None, {"url": url[:200]})
    return JSONResponse({"ok": True, "url": url})


@app.post("/api/admin/empty-image/upload")
async def api_admin_empty_image_upload(request: Request, file: UploadFile = File(...)) -> JSONResponse:
    actor = admin_record(request)
    raw = await file.read()
    if len(raw) > _MAX_IMAGE_BYTES:
        return JSONResponse({"ok": False, "error": "too_large", "max_bytes": _MAX_IMAGE_BYTES}, status_code=400)
    mime = (file.content_type or "").lower()
    if mime not in _ALLOWED_IMAGE_MIMES:
        return JSONResponse({"ok": False, "error": "bad_mime", "allowed": sorted(_ALLOWED_IMAGE_MIMES)}, status_code=400)
    image_id = secrets.token_urlsafe(8)
    UPLOADED_IMAGES[image_id] = (mime, raw)
    public_url = f"/api/uploads/{image_id}"
    CONFIG["empty_image_url"] = public_url
    log_admin(actor["id"], "empty_image_upload", None, {"id": image_id, "mime": mime, "bytes": len(raw)})
    return JSONResponse({"ok": True, "url": public_url, "id": image_id, "bytes": len(raw)})


@app.get("/api/uploads/{image_id}")
async def api_get_uploaded_image(image_id: str) -> Response:
    item = UPLOADED_IMAGES.get(image_id)
    if not item:
        raise HTTPException(status_code=404, detail="not_found")
    mime, raw = item
    return Response(content=raw, media_type=mime, headers={"Cache-Control": "public, max-age=86400"})


@app.delete("/api/admin/empty-image")
async def api_admin_empty_image_clear(request: Request) -> JSONResponse:
    actor = admin_record(request)
    CONFIG["empty_image_url"] = ""
    log_admin(actor["id"], "empty_image_clear", None, {})
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# Danger zone — global wipes
# ---------------------------------------------------------------------------


def _confirm_token(request_body: dict[str, Any]) -> bool:
    token = str(request_body.get("confirm") or "").strip()
    # Accept a numeric code of 1..5 digits (UI generates a random 5-digit code).
    return token.isdigit() and 1 <= len(token) <= 5


@app.post("/api/admin/danger/zero-all-balances")
async def api_admin_zero_balances(request: Request) -> JSONResponse:
    actor = admin_record(request)
    body = await request.json()
    if not _confirm_token(body):
        return JSONResponse({"ok": False, "error": "need_confirm"}, status_code=400)
    affected = 0
    for u in USERS.values():
        if int(u.get("balance") or 0):
            affected += 1
        u["balance"] = 0
    log_admin(actor["id"], "zero_all_balances", None, {"affected": affected})
    return JSONResponse({"ok": True, "affected": affected})


@app.post("/api/admin/danger/revoke-all-subscriptions")
async def api_admin_revoke_all_subs(request: Request) -> JSONResponse:
    actor = admin_record(request)
    body = await request.json()
    if not _confirm_token(body):
        return JSONResponse({"ok": False, "error": "need_confirm"}, status_code=400)
    affected = 0
    for u in USERS.values():
        sub = u.get("subscription") or {}
        if sub.get("expires_at"):
            affected += 1
        u["subscription"] = {}
    log_admin(actor["id"], "revoke_all_subs", None, {"affected": affected})
    return JSONResponse({"ok": True, "affected": affected})


@app.post("/api/admin/danger/clear-all-devices")
async def api_admin_clear_all_devices(request: Request) -> JSONResponse:
    actor = admin_record(request)
    body = await request.json()
    if not _confirm_token(body):
        return JSONResponse({"ok": False, "error": "need_confirm"}, status_code=400)
    affected = 0
    for u in USERS.values():
        if u.get("devices"):
            affected += 1
        u["devices"] = []
        sub = u.get("subscription") or {}
        sub["devices_active"] = 0
    log_admin(actor["id"], "clear_all_devices", None, {"affected": affected})
    return JSONResponse({"ok": True, "affected": affected})


@app.post("/api/admin/danger/delete-all-non-admin")
async def api_admin_delete_non_admin(request: Request) -> JSONResponse:
    actor = admin_record(request)
    body = await request.json()
    if not _confirm_token(body):
        return JSONResponse({"ok": False, "error": "need_confirm"}, status_code=400)
    deleted: list[int] = []
    for tg_id in list(USERS.keys()):
        if tg_id in ADMIN_IDS:
            continue
        del USERS[tg_id]
        deleted.append(tg_id)
    log_admin(actor["id"], "delete_non_admin", None, {"count": len(deleted)})
    return JSONResponse({"ok": True, "deleted": len(deleted)})


@app.post("/api/admin/danger/wipe-all")
async def api_admin_wipe_all(request: Request) -> JSONResponse:
    actor = admin_record(request)
    body = await request.json()
    if not _confirm_token(body):
        return JSONResponse({"ok": False, "error": "need_confirm"}, status_code=400)
    USERS.clear()
    PAYMENTS.clear()
    BROADCASTS.clear()
    log_admin(actor["id"], "wipe_all", None, {})
    return JSONResponse({"ok": True})


@app.post("/api/internal/wipe-all")
async def api_internal_wipe_all(request: Request) -> JSONResponse:
    """Internal: nuke all in-memory state. Used by deploy automation only."""
    if request.headers.get("x-internal-key") != INTERNAL_API_KEY:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    USERS.clear()
    PAYMENTS.clear()
    BROADCASTS.clear()
    try:
        USER_EVENTS.clear()
        USER_EVENTS_GLOBAL.clear()
    except NameError:
        pass
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# Promo codes (admin CRUD + public redeem)
# ---------------------------------------------------------------------------

def _gen_promo_code(length: int = 8) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


@app.get("/api/admin/promos")
async def api_admin_promos_list(request: Request) -> JSONResponse:
    admin_record(request)
    items = []
    for code, p in PROMOS.items():
        items.append({"code": code, **p})
    items.sort(key=lambda x: x.get("created_at", 0), reverse=True)
    return JSONResponse({"ok": True, "items": items, "total": len(items)})


@app.post("/api/admin/promos")
async def api_admin_promos_create(request: Request) -> JSONResponse:
    actor = admin_record(request)
    body = await request.json()
    kind = str(body.get("kind") or "balance").strip()  # balance | days | stars | percent
    if kind not in {"balance", "days", "stars", "percent"}:
        return JSONResponse({"ok": False, "error": "bad_kind"}, status_code=400)
    try:
        value = int(body.get("value") or 0)
    except Exception:
        return JSONResponse({"ok": False, "error": "bad_value"}, status_code=400)
    if value <= 0 or value > 1_000_000:
        return JSONResponse({"ok": False, "error": "bad_value"}, status_code=400)
    limit = int(body.get("limit") or 0) or 0  # 0 = unlimited
    expires_in_days = int(body.get("expires_in_days") or 0) or 0
    note = str(body.get("note") or "").strip()[:200]
    code = str(body.get("code") or "").strip().upper() or _gen_promo_code()
    if code in PROMOS:
        return JSONResponse({"ok": False, "error": "exists"}, status_code=409)
    expires_at = int(time.time()) + expires_in_days * 86400 if expires_in_days else 0
    PROMOS[code] = {
        "kind": kind,
        "value": value,
        "limit": limit,
        "used": 0,
        "expires_at": expires_at,
        "created_by": actor["id"],
        "created_at": int(time.time()),
        "note": note,
    }
    log_admin(actor["id"], "promo_create", None, {"code": code, "kind": kind, "value": value})
    return JSONResponse({"ok": True, "code": code, "promo": {"code": code, **PROMOS[code]}})


@app.delete("/api/admin/promos/{code}")
async def api_admin_promos_delete(code: str, request: Request) -> JSONResponse:
    actor = admin_record(request)
    if code not in PROMOS:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    PROMOS.pop(code, None)
    log_admin(actor["id"], "promo_delete", None, {"code": code})
    return JSONResponse({"ok": True})


@app.post("/api/promo")
async def api_promo_redeem(request: Request) -> JSONResponse:
    """Public endpoint: redeem a promo code for the current logged-in user."""
    tg_id = get_current_user_id(request)
    if not tg_id:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    record = USERS.get(int(tg_id))
    if not record:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    body = await request.json()
    code = str(body.get("code") or "").strip().upper()
    if not code:
        return JSONResponse({"ok": False, "error": "empty"}, status_code=400)
    promo = PROMOS.get(code)
    if not promo:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    if promo.get("expires_at") and promo["expires_at"] < int(time.time()):
        return JSONResponse({"ok": False, "error": "expired"}, status_code=400)
    if promo.get("limit") and promo.get("used", 0) >= promo["limit"]:
        return JSONResponse({"ok": False, "error": "exhausted"}, status_code=400)
    used_by = promo.setdefault("used_by", [])
    if tg_id in used_by:
        return JSONResponse({"ok": False, "error": "already_used"}, status_code=400)
    kind = promo.get("kind") or "balance"
    value = int(promo.get("value") or 0)
    msg = ""
    now = int(time.time())
    if kind == "balance":
        record["balance"] = int(record.get("balance") or 0) + value
        msg = f"+{value} ₽ на баланс"
    elif kind == "stars":
        record["stars_balance"] = int(record.get("stars_balance") or 0) + value
        msg = f"+{value} ⭐"
    elif kind == "days":
        sub = record.setdefault("subscription", {})
        cur = int(sub.get("expires_at") or now)
        sub["expires_at"] = max(cur, now) + value * 86400
        if not sub.get("tariff_name"):
            sub["tariff_name"] = "Промо"
        msg = f"+{value} дней подписки"
    elif kind == "percent":
        record["balance"] = int(record.get("balance") or 0) + value
        msg = f"+{value} ₽ на баланс"
    promo["used"] = int(promo.get("used", 0)) + 1
    used_by.append(tg_id)
    log_admin(0, "promo_redeem", tg_id, {"code": code, "kind": kind, "value": value})
    return JSONResponse({"ok": True, "message": msg, "kind": kind, "value": value})


@app.post("/api/admin/promos/{code}/disable")
async def api_admin_promos_disable(code: str, request: Request) -> JSONResponse:
    actor = admin_record(request)
    promo = PROMOS.get(code)
    if not promo:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    promo["limit"] = max(promo.get("used", 0), 1)
    promo["expires_at"] = int(time.time()) - 1
    log_admin(actor["id"], "promo_disable", None, {"code": code})
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# Backup / restore (admin)
# ---------------------------------------------------------------------------

def _snapshot_state() -> dict[str, Any]:
    return {
        "version": 1,
        "exported_at": int(time.time()),
        "users": USERS,
        "payments": PAYMENTS,
        "broadcasts": BROADCASTS,
        "promos": PROMOS,
        "config": CONFIG,
        "admin_log": ADMIN_LOG[-2000:],
    }


@app.get("/api/admin/backup/export")
async def api_admin_backup_export(request: Request) -> JSONResponse:
    admin_record(request)
    return JSONResponse({"ok": True, "snapshot": _snapshot_state()})


@app.post("/api/admin/backup/import")
async def api_admin_backup_import(request: Request) -> JSONResponse:
    actor = admin_record(request)
    body = await request.json()
    snap = body.get("snapshot") or body
    if not isinstance(snap, dict):
        return JSONResponse({"ok": False, "error": "bad_snapshot"}, status_code=400)
    users = snap.get("users") or {}
    if isinstance(users, dict):
        USERS.clear()
        for k, v in users.items():
            try:
                USERS[int(k)] = v
            except Exception:
                pass
    payments = snap.get("payments")
    if isinstance(payments, list):
        PAYMENTS[:] = payments
    broadcasts = snap.get("broadcasts")
    if isinstance(broadcasts, list):
        BROADCASTS[:] = broadcasts
    promos = snap.get("promos")
    if isinstance(promos, dict):
        PROMOS.clear()
        PROMOS.update(promos)
    cfg = snap.get("config")
    if isinstance(cfg, dict):
        CONFIG.update(cfg)
    log_admin(actor["id"], "backup_import", None, {"users": len(USERS), "payments": len(PAYMENTS)})
    return JSONResponse({"ok": True, "users": len(USERS), "payments": len(PAYMENTS), "promos": len(PROMOS)})


# ---------------------------------------------------------------------------
# Bulk action (admin) — multi-target operations on selected user IDs.
# ---------------------------------------------------------------------------


@app.post("/api/admin/users/bulk/op")
async def api_admin_bulk_op(request: Request) -> JSONResponse:
    actor = admin_record(request)
    body = await request.json()
    op = str(body.get("op") or "").strip()
    ids = [int(x) for x in (body.get("tg_ids") or []) if str(x).lstrip("-").isdigit()]
    if not op or not ids:
        return JSONResponse({"ok": False, "error": "need_op_and_ids"}, status_code=400)
    try:
        amount = int(body.get("amount") or 0)
    except Exception:
        amount = 0
    affected: list[int] = []
    now = int(time.time())
    for tg_id in ids:
        rec = USERS.get(tg_id)
        if not rec:
            continue
        if op == "ban":
            rec["banned"] = True
        elif op == "unban":
            rec["banned"] = False
        elif op == "balance_add":
            rec["balance"] = int(rec.get("balance") or 0) + amount
        elif op == "balance_set":
            rec["balance"] = max(0, amount)
        elif op == "stars_add":
            rec["stars_balance"] = int(rec.get("stars_balance") or 0) + amount
        elif op == "stars_set":
            rec["stars_balance"] = max(0, amount)
        elif op == "days_add":
            sub = rec.setdefault("subscription", {})
            cur = int(sub.get("expires_at") or now)
            sub["expires_at"] = max(cur, now) + max(0, amount) * 86400
            if not sub.get("tariff_name"):
                sub["tariff_name"] = "Бонус"
        elif op == "revoke":
            rec["subscription"] = {}
        elif op == "clear_devices":
            rec["devices"] = []
        elif op == "reset_trial":
            rec["free_used"] = False
        elif op == "regen_uuid":
            rec["sub_uuid"] = make_sub_uuid()
        elif op == "delete":
            USERS.pop(tg_id, None)
        else:
            return JSONResponse({"ok": False, "error": f"unknown_op:{op}"}, status_code=400)
        affected.append(tg_id)
    log_admin(actor["id"], "bulk_op", None, {"op": op, "count": len(affected), "amount": amount})
    return JSONResponse({"ok": True, "affected": len(affected), "ids": affected})


# ---------------------------------------------------------------------------
# Bulk actions (extras)
# ---------------------------------------------------------------------------


@app.post("/api/admin/users/bulk/note")
async def api_admin_bulk_note(request: Request) -> JSONResponse:
    actor = admin_record(request)
    body = await request.json()
    ids = [int(x) for x in (body.get("tg_ids") or []) if int(x)]
    note = str(body.get("note") or "").strip()
    affected: list[int] = []
    for tg_id in ids:
        rec = USERS.get(tg_id)
        if rec is None:
            continue
        rec["admin_note"] = note
        affected.append(tg_id)
    log_admin(actor["id"], "bulk_note", None, {"count": len(affected)})
    return JSONResponse({"ok": True, "affected": affected})


@app.post("/api/admin/users/bulk/tag")
async def api_admin_bulk_tag(request: Request) -> JSONResponse:
    actor = admin_record(request)
    body = await request.json()
    ids = [int(x) for x in (body.get("tg_ids") or []) if int(x)]
    tag = str(body.get("tag") or "").strip().lower()
    if not tag:
        return JSONResponse({"ok": False, "error": "empty_tag"}, status_code=400)
    affected: list[int] = []
    for tg_id in ids:
        rec = USERS.get(tg_id)
        if rec is None:
            continue
        tags = set(rec.get("tags") or [])
        tags.add(tag)
        rec["tags"] = sorted(tags)
        affected.append(tg_id)
    log_admin(actor["id"], "bulk_tag_add", None, {"tag": tag, "count": len(affected)})
    return JSONResponse({"ok": True, "affected": affected})


@app.post("/api/admin/users/bulk/credit-stars")
async def api_admin_bulk_credit_stars(request: Request) -> JSONResponse:
    actor = admin_record(request)
    body = await request.json()
    ids = [int(x) for x in (body.get("tg_ids") or []) if int(x)]
    stars = int(body.get("stars") or 0)
    if stars <= 0:
        return JSONResponse({"ok": False, "error": "bad_amount"}, status_code=400)
    rate = float(CONFIG.get("stars_rate_rub") or 1.39)
    rub = int(round(stars * rate))
    affected: list[int] = []
    for tg_id in ids:
        rec = USERS.get(tg_id)
        if rec is None:
            continue
        rec["balance"] = int(rec.get("balance") or 0) + rub
        affected.append(tg_id)
    log_admin(actor["id"], "bulk_credit_stars", None, {"stars": stars, "rub": rub, "count": len(affected)})
    return JSONResponse({"ok": True, "affected": affected, "credited_rub": rub})


@app.post("/api/admin/users/bulk/extend-trial")
async def api_admin_bulk_extend_trial(request: Request) -> JSONResponse:
    actor = admin_record(request)
    body = await request.json()
    ids = [int(x) for x in (body.get("tg_ids") or []) if int(x)]
    days = int(body.get("days") or 0)
    if days <= 0:
        return JSONResponse({"ok": False, "error": "bad_days"}, status_code=400)
    affected: list[int] = []
    for tg_id in ids:
        rec = USERS.get(tg_id)
        if rec is None:
            continue
        sub = rec.setdefault("subscription", {})
        base = max(int(sub.get("expires_at") or 0), int(time.time()))
        sub["expires_at"] = base + days * 86400
        sub["tariff_name"] = sub.get("tariff_name") or "Расширенный пробный"
        sub["tariff_total_days"] = int(sub.get("tariff_total_days") or 0) + days
        affected.append(tg_id)
    log_admin(actor["id"], "bulk_extend_trial", None, {"days": days, "count": len(affected)})
    return JSONResponse({"ok": True, "affected": affected})


@app.post("/api/admin/users/bulk/clear-devices")
async def api_admin_bulk_clear_devices(request: Request) -> JSONResponse:
    actor = admin_record(request)
    body = await request.json()
    ids = [int(x) for x in (body.get("tg_ids") or []) if int(x)]
    affected: list[int] = []
    for tg_id in ids:
        rec = USERS.get(tg_id)
        if rec is None:
            continue
        rec["devices"] = []
        sub = rec.setdefault("subscription", {})
        sub["devices_active"] = 0
        affected.append(tg_id)
    log_admin(actor["id"], "bulk_clear_devices", None, {"count": len(affected)})
    return JSONResponse({"ok": True, "affected": affected})


@app.post("/api/admin/users/bulk/reset-trial")
async def api_admin_bulk_reset_trial(request: Request) -> JSONResponse:
    actor = admin_record(request)
    body = await request.json()
    ids = [int(x) for x in (body.get("tg_ids") or []) if int(x)]
    affected: list[int] = []
    for tg_id in ids:
        rec = USERS.get(tg_id)
        if rec is None:
            continue
        rec["free_used"] = False
        affected.append(tg_id)
    log_admin(actor["id"], "bulk_reset_trial", None, {"count": len(affected)})
    return JSONResponse({"ok": True, "affected": affected})


# ---------------------------------------------------------------------------
# Per-user activity events (frontend telemetry + admin viewer)
# ---------------------------------------------------------------------------


@app.post("/api/log/event")
async def api_log_event(request: Request) -> JSONResponse:
    """Lightweight event ingest from the Mini App. Signed-in users only."""
    tg_id = get_current_user_id(request)
    if not tg_id:
        return JSONResponse({"ok": False, "error": "auth_required"}, status_code=401)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    events = body.get("events") if isinstance(body, dict) else None
    if events is None and isinstance(body, dict) and body.get("type"):
        events = [body]
    if not isinstance(events, list):
        return JSONResponse({"ok": False, "error": "bad_request"}, status_code=400)
    written = 0
    for raw in events[:50]:  # safety cap per request
        if not isinstance(raw, dict):
            continue
        record_event(
            tg_id=tg_id,
            event_type=str(raw.get("type") or "unknown"),
            label=raw.get("label"),
            payload=raw.get("payload") if isinstance(raw.get("payload"), dict) else None,
            source=str(raw.get("source") or "frontend")[:24],
        )
        written += 1
    return JSONResponse({"ok": True, "written": written})


@app.get("/api/admin/events")
async def api_admin_events(request: Request) -> JSONResponse:
    admin_record(request)
    qp = request.query_params
    limit = max(1, min(int(qp.get("limit") or 200), 2000))
    tg_id = qp.get("tg_id")
    type_filter = qp.get("type")
    items = list(USER_EVENTS_GLOBAL[-5000:])
    if tg_id and tg_id.isdigit():
        items = [e for e in items if e.get("tg_id") == int(tg_id)]
    if type_filter:
        items = [e for e in items if e.get("type") == type_filter]
    items.reverse()
    return JSONResponse({"ok": True, "total": len(items), "items": items[:limit]})


@app.get("/api/admin/users/{tg_id}/events")
async def api_admin_user_events(tg_id: int, request: Request) -> JSONResponse:
    admin_record(request)
    items = list(USER_EVENTS.get(int(tg_id), []))
    items.reverse()
    return JSONResponse({"ok": True, "total": len(items), "items": items[:500]})


@app.delete("/api/admin/events")
async def api_admin_events_clear(request: Request) -> JSONResponse:
    actor = admin_record(request)
    USER_EVENTS_GLOBAL.clear()
    USER_EVENTS.clear()
    log_admin(actor["id"], "events_clear", None, None)
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# Bulk small admin/utility endpoints (filters, aggregates, per-user views)
# ---------------------------------------------------------------------------


def _users_filter(predicate) -> list[dict[str, Any]]:
    return [u for u in USERS.values() if predicate(u)]


@app.get("/api/admin/users/by-balance/min/{amount}")
async def api_admin_users_by_balance_min(amount: int, request: Request) -> JSONResponse:
    admin_record(request)
    return JSONResponse({"ok": True, "items": _users_filter(lambda u: int(u.get("balance") or 0) >= amount)})


@app.get("/api/admin/users/by-balance/max/{amount}")
async def api_admin_users_by_balance_max(amount: int, request: Request) -> JSONResponse:
    admin_record(request)
    return JSONResponse({"ok": True, "items": _users_filter(lambda u: int(u.get("balance") or 0) <= amount)})


@app.get("/api/admin/users/by-stars/min/{amount}")
async def api_admin_users_by_stars_min(amount: int, request: Request) -> JSONResponse:
    admin_record(request)
    return JSONResponse({"ok": True, "items": _users_filter(lambda u: int(u.get("stars_balance") or 0) >= amount)})


@app.get("/api/admin/users/no-devices")
async def api_admin_users_no_devices(request: Request) -> JSONResponse:
    admin_record(request)
    return JSONResponse({"ok": True, "items": _users_filter(lambda u: not (u.get("devices") or []))})


@app.get("/api/admin/users/many-devices/{n}")
async def api_admin_users_many_devices(n: int, request: Request) -> JSONResponse:
    admin_record(request)
    return JSONResponse({"ok": True, "items": _users_filter(lambda u: len(u.get("devices") or []) >= n)})


@app.get("/api/admin/users/with-trial")
async def api_admin_users_with_trial(request: Request) -> JSONResponse:
    admin_record(request)
    return JSONResponse({"ok": True, "items": _users_filter(lambda u: bool(u.get("free_used")))})


@app.get("/api/admin/users/without-trial")
async def api_admin_users_without_trial(request: Request) -> JSONResponse:
    admin_record(request)
    return JSONResponse({"ok": True, "items": _users_filter(lambda u: not u.get("free_used"))})


@app.get("/api/admin/users/with-sub")
async def api_admin_users_with_sub(request: Request) -> JSONResponse:
    admin_record(request)
    now = int(time.time())
    return JSONResponse({
        "ok": True,
        "items": _users_filter(lambda u: int((u.get("subscription") or {}).get("expires_at") or 0) > now),
    })


@app.get("/api/admin/users/without-sub")
async def api_admin_users_without_sub(request: Request) -> JSONResponse:
    admin_record(request)
    now = int(time.time())
    return JSONResponse({
        "ok": True,
        "items": _users_filter(lambda u: int((u.get("subscription") or {}).get("expires_at") or 0) <= now),
    })


@app.get("/api/admin/users/expiring-in/{days}")
async def api_admin_users_expiring_in(days: int, request: Request) -> JSONResponse:
    admin_record(request)
    now = int(time.time())
    horizon = now + max(0, int(days)) * 86400
    return JSONResponse({
        "ok": True,
        "items": _users_filter(
            lambda u: now < int((u.get("subscription") or {}).get("expires_at") or 0) <= horizon
        ),
    })


@app.get("/api/admin/users/expired-since/{days}")
async def api_admin_users_expired_since(days: int, request: Request) -> JSONResponse:
    admin_record(request)
    now = int(time.time())
    cutoff = now - max(0, int(days)) * 86400
    return JSONResponse({
        "ok": True,
        "items": _users_filter(
            lambda u: 0 < int((u.get("subscription") or {}).get("expires_at") or 0) < cutoff
        ),
    })


@app.get("/api/admin/users/by-tariff/{tariff_key}")
async def api_admin_users_by_tariff(tariff_key: str, request: Request) -> JSONResponse:
    admin_record(request)
    return JSONResponse({
        "ok": True,
        "items": _users_filter(lambda u: (u.get("subscription") or {}).get("tariff_key") == tariff_key),
    })


@app.get("/api/admin/users/by-lang/{lang}")
async def api_admin_users_by_lang(lang: str, request: Request) -> JSONResponse:
    admin_record(request)
    return JSONResponse({"ok": True, "items": _users_filter(lambda u: (u.get("lang") or "ru") == lang)})


@app.get("/api/admin/users/by-currency/{currency}")
async def api_admin_users_by_currency(currency: str, request: Request) -> JSONResponse:
    admin_record(request)
    return JSONResponse({
        "ok": True,
        "items": _users_filter(lambda u: (u.get("currency") or "rub").lower() == currency.lower()),
    })


@app.get("/api/admin/users/never-paid")
async def api_admin_users_never_paid(request: Request) -> JSONResponse:
    admin_record(request)
    return JSONResponse({"ok": True, "items": _users_filter(lambda u: int(u.get("total_spent") or 0) == 0)})


@app.get("/api/admin/users/top-spenders/{n}")
async def api_admin_users_top_spenders(n: int, request: Request) -> JSONResponse:
    admin_record(request)
    sorted_users = sorted(USERS.values(), key=lambda u: int(u.get("total_spent") or 0), reverse=True)
    return JSONResponse({"ok": True, "items": sorted_users[: max(1, min(int(n), 200))]})


@app.get("/api/admin/users/recent/{n}")
async def api_admin_users_recent(n: int, request: Request) -> JSONResponse:
    admin_record(request)
    sorted_users = sorted(USERS.values(), key=lambda u: int(u.get("created_at") or 0), reverse=True)
    return JSONResponse({"ok": True, "items": sorted_users[: max(1, min(int(n), 200))]})


@app.get("/api/admin/users/oldest/{n}")
async def api_admin_users_oldest(n: int, request: Request) -> JSONResponse:
    admin_record(request)
    sorted_users = sorted(USERS.values(), key=lambda u: int(u.get("created_at") or 0))
    return JSONResponse({"ok": True, "items": sorted_users[: max(1, min(int(n), 200))]})


@app.get("/api/admin/aggregate/by-tariff")
async def api_admin_aggregate_by_tariff(request: Request) -> JSONResponse:
    admin_record(request)
    counts: dict[str, int] = {}
    for u in USERS.values():
        key = (u.get("subscription") or {}).get("tariff_key") or ""
        if key:
            counts[key] = counts.get(key, 0) + 1
    return JSONResponse({"ok": True, "items": counts})


@app.get("/api/admin/aggregate/by-lang")
async def api_admin_aggregate_by_lang(request: Request) -> JSONResponse:
    admin_record(request)
    counts: dict[str, int] = {}
    for u in USERS.values():
        key = u.get("lang") or "ru"
        counts[key] = counts.get(key, 0) + 1
    return JSONResponse({"ok": True, "items": counts})


@app.get("/api/admin/aggregate/by-currency")
async def api_admin_aggregate_by_currency(request: Request) -> JSONResponse:
    admin_record(request)
    counts: dict[str, int] = {}
    for u in USERS.values():
        key = (u.get("currency") or "rub").lower()
        counts[key] = counts.get(key, 0) + 1
    return JSONResponse({"ok": True, "items": counts})


@app.get("/api/admin/aggregate/payments-by-day/{days}")
async def api_admin_aggregate_payments_by_day(days: int, request: Request) -> JSONResponse:
    admin_record(request)
    now = int(time.time())
    horizon = now - max(1, int(days)) * 86400
    bucket: dict[str, dict[str, int]] = {}
    for p in PAYMENTS:
        ts = int(p.get("ts") or p.get("created_at") or 0)
        if ts < horizon:
            continue
        key = dt.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
        slot = bucket.setdefault(key, {"count": 0, "rub": 0, "stars": 0})
        slot["count"] += 1
        slot["rub"] += int(p.get("amount_rub") or 0)
        slot["stars"] += int(p.get("amount_stars") or 0)
    return JSONResponse({"ok": True, "items": bucket})


@app.get("/api/admin/aggregate/registrations-by-day/{days}")
async def api_admin_aggregate_registrations_by_day(days: int, request: Request) -> JSONResponse:
    admin_record(request)
    now = int(time.time())
    horizon = now - max(1, int(days)) * 86400
    bucket: dict[str, int] = {}
    for u in USERS.values():
        ts = int(u.get("created_at") or 0)
        if ts < horizon:
            continue
        key = dt.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
        bucket[key] = bucket.get(key, 0) + 1
    return JSONResponse({"ok": True, "items": bucket})


@app.get("/api/admin/users/{tg_id}/snapshot")
async def api_admin_user_snapshot(tg_id: int, request: Request) -> JSONResponse:
    admin_record(request)
    rec = USERS.get(int(tg_id))
    if not rec:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    return JSONResponse({"ok": True, "user": rec, "events": list(USER_EVENTS.get(int(tg_id), []))[-200:]})


@app.post("/api/admin/users/{tg_id}/lang")
async def api_admin_user_set_lang(tg_id: int, request: Request) -> JSONResponse:
    actor = admin_record(request)
    body = await request.json()
    lang = (body.get("lang") or "").lower()
    if lang not in {"ru", "en"}:
        return JSONResponse({"ok": False, "error": "bad_lang"}, status_code=400)
    rec = USERS.get(int(tg_id))
    if not rec:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    rec["lang"] = lang
    log_admin(actor["id"], "set_lang", int(tg_id), {"lang": lang})
    return JSONResponse({"ok": True})


@app.post("/api/admin/users/{tg_id}/currency")
async def api_admin_user_set_currency(tg_id: int, request: Request) -> JSONResponse:
    actor = admin_record(request)
    body = await request.json()
    cur = (body.get("currency") or "").lower()
    if cur not in {"rub", "usd"}:
        return JSONResponse({"ok": False, "error": "bad_currency"}, status_code=400)
    rec = USERS.get(int(tg_id))
    if not rec:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    rec["currency"] = cur
    log_admin(actor["id"], "set_currency", int(tg_id), {"currency": cur})
    return JSONResponse({"ok": True})


@app.post("/api/admin/users/{tg_id}/clear-events")
async def api_admin_user_clear_events(tg_id: int, request: Request) -> JSONResponse:
    actor = admin_record(request)
    USER_EVENTS.pop(int(tg_id), None)
    log_admin(actor["id"], "clear_events", int(tg_id), None)
    return JSONResponse({"ok": True})


@app.get("/api/admin/system/counters")
async def api_admin_system_counters(request: Request) -> JSONResponse:
    admin_record(request)
    now = int(time.time())
    active = sum(1 for u in USERS.values() if int((u.get("subscription") or {}).get("expires_at") or 0) > now)
    banned = sum(1 for u in USERS.values() if u.get("banned"))
    trial = sum(1 for u in USERS.values() if u.get("free_used"))
    day_start = now - (now % 86400)
    today_regs = sum(1 for u in USERS.values() if int(u.get("created_at") or 0) >= day_start)
    paid_payments = [p for p in PAYMENTS if (p.get("status") or "").lower() in {"paid", "success", "succeeded", "ok"}]
    total_rub = sum(int(p.get("amount_rub") or p.get("amount") or 0) for p in paid_payments)
    total_stars = sum(int(p.get("amount_stars") or 0) for p in paid_payments)
    return JSONResponse({
        "ok": True,
        "users": len(USERS),
        "active_subs": active,
        "banned": banned,
        "trial_used": trial,
        "events": len(USER_EVENTS_GLOBAL),
        "payments": len(PAYMENTS),
        "broadcasts": len(BROADCASTS),
        "admin_log": len(ADMIN_LOG),
        "promos": len(PROMOS),
        "today_registrations": today_regs,
        "total_rub": total_rub,
        "total_stars": total_stars,
        "uptime_sec": int(time.time() - APP_STARTED_AT),
    })


# Internal — bot subscribes a user via tariff (used when user buys directly in chat).
@app.post("/api/internal/grant-subscription")
async def api_internal_grant_subscription(request: Request) -> JSONResponse:
    if request.headers.get("x-internal-key") != INTERNAL_API_KEY:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    body = await request.json()
    tg_id = int(body.get("tg_id") or 0)
    tariff_key = str(body.get("tariff_key") or "")
    payment_kind = str(body.get("payment") or "stars")
    if not tg_id or not tariff_key:
        return JSONResponse({"ok": False, "error": "bad_request"}, status_code=400)
    tariff = next((t for t in (CONFIG.get("tariffs") or []) if t.get("key") == tariff_key), None)
    if not tariff:
        return JSONResponse({"ok": False, "error": "unknown_tariff"}, status_code=404)
    record = USERS.setdefault(int(tg_id), {
        "id": int(tg_id), "first_name": body.get("first_name") or "", "username": body.get("username") or "",
        "balance": 0, "stars_balance": 0, "devices": [], "subscription": {},
        "free_used": False, "banned": False, "created_at": int(time.time()),
        "last_seen": int(time.time()), "sub_uuid": make_sub_uuid(), "ref_count": 0,
        "lang": "ru", "currency": "rub", "total_spent": 0,
    })
    if not record.get("sub_uuid"):
        record["sub_uuid"] = make_sub_uuid()
    days = int(tariff.get("days") or 30)
    now = int(time.time())
    base = max(now, int((record.get("subscription") or {}).get("expires_at") or 0))
    record["subscription"] = {
        "tariff_key": tariff.get("key"),
        "tariff_name": tariff.get("name"),
        "expires_at": base + days * 86400,
        "devices_limit": int(tariff.get("devices") or 3),
    }
    record["last_seen"] = now
    if payment_kind == "stars":
        stars_cost = int(tariff.get("price_stars") or 0)
        if stars_cost:
            record["stars_balance"] = max(0, int(record.get("stars_balance") or 0) - stars_cost)
        record["total_spent"] = int(record.get("total_spent") or 0) + int(tariff.get("price_rub") or 0)
        PAYMENTS.append({
            "ts": now, "tg_id": tg_id, "provider": "stars", "amount_stars": stars_cost,
            "amount_rub": int(tariff.get("price_rub") or 0), "tariff_key": tariff.get("key"), "status": "paid",
        })
    elif payment_kind == "balance":
        cost = int(tariff.get("price_rub") or 0)
        record["balance"] = max(0, int(record.get("balance") or 0) - cost)
        record["total_spent"] = int(record.get("total_spent") or 0) + cost
        PAYMENTS.append({
            "ts": now, "tg_id": tg_id, "provider": "balance", "amount_stars": 0,
            "amount_rub": cost, "tariff_key": tariff.get("key"), "status": "paid",
        })
    record_event(tg_id, "purchase", f"bot:{tariff.get('key')}:{payment_kind}", {
        "tariff_key": tariff.get("key"), "payment": payment_kind,
    }, source="bot")
    return JSONResponse({
        "ok": True,
        "tariff_name": tariff.get("name"),
        "expires_at": record["subscription"]["expires_at"],
        "sub_url": f"{SUB_BASE.rstrip('/')}/{record['sub_uuid']}",
        "balance_rub": record.get("balance", 0),
        "stars_balance": record.get("stars_balance", 0),
    })


# Internal — bot triggers free 3-day trial activation.
@app.post("/api/internal/grant-trial")
async def api_internal_grant_trial(request: Request) -> JSONResponse:
    if request.headers.get("x-internal-key") != INTERNAL_API_KEY:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    body = await request.json()
    tg_id = int(body.get("tg_id") or 0)
    if not tg_id:
        return JSONResponse({"ok": False, "error": "bad_request"}, status_code=400)
    record = USERS.setdefault(int(tg_id), {
        "id": int(tg_id), "first_name": body.get("first_name") or "", "username": body.get("username") or "",
        "balance": 0, "stars_balance": 0, "devices": [], "subscription": {},
        "free_used": False, "banned": False, "created_at": int(time.time()),
        "last_seen": int(time.time()), "sub_uuid": make_sub_uuid(), "ref_count": 0,
        "lang": "ru", "currency": "rub", "total_spent": 0,
    })
    if record.get("free_used"):
        return JSONResponse({"ok": False, "error": "already_used"}, status_code=400)
    if not record.get("sub_uuid"):
        record["sub_uuid"] = make_sub_uuid()
    days = int(CONFIG.get("trial_days") or 3)
    now = int(time.time())
    base = max(now, int((record.get("subscription") or {}).get("expires_at") or 0))
    record["subscription"] = {
        "tariff_key": "trial", "tariff_name": "Пробный",
        "expires_at": base + days * 86400, "devices_limit": 3,
    }
    record["free_used"] = True
    record_event(tg_id, "trial_claim", "bot:claim", {"days": days}, source="bot")
    return JSONResponse({
        "ok": True,
        "days": days,
        "expires_at": record["subscription"]["expires_at"],
        "sub_url": f"{SUB_BASE.rstrip('/')}/{record['sub_uuid']}",
    })


# Internal — bot credits stars to a user balance after successful Stars payment.
@app.post("/api/internal/credit-stars")
async def api_internal_credit_stars(request: Request) -> JSONResponse:
    if request.headers.get("x-internal-key") != INTERNAL_API_KEY:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    body = await request.json()
    tg_id = int(body.get("tg_id") or 0)
    stars = int(body.get("stars") or 0)
    if not tg_id or stars <= 0:
        return JSONResponse({"ok": False, "error": "bad_request"}, status_code=400)
    record = USERS.setdefault(int(tg_id), {
        "id": int(tg_id), "first_name": body.get("first_name") or "", "username": body.get("username") or "",
        "balance": 0, "stars_balance": 0, "devices": [], "subscription": {},
        "free_used": False, "banned": False, "created_at": int(time.time()),
        "last_seen": int(time.time()), "sub_uuid": make_sub_uuid(), "ref_count": 0,
        "lang": "ru", "currency": "rub", "total_spent": 0,
    })
    record["stars_balance"] = int(record.get("stars_balance") or 0) + stars
    rate = float(CONFIG.get("stars_rate_rub") or 1.5)
    rub_value = int(stars * rate)
    record["balance"] = int(record.get("balance") or 0) + rub_value
    record["total_spent"] = int(record.get("total_spent") or 0) + rub_value
    PAYMENTS.append({
        "ts": int(time.time()), "tg_id": tg_id, "provider": "stars",
        "amount_stars": stars, "amount_rub": rub_value, "status": "paid",
    })
    record_event(tg_id, "credit_stars", f"+{stars}⭐", {"stars": stars, "rub": rub_value}, source="bot")
    return JSONResponse({"ok": True, "stars_balance": record["stars_balance"], "balance_rub": record["balance"]})


# ---------------------------------------------------------------------------
# Many small per-user/admin convenience endpoints (filters / actions)
# ---------------------------------------------------------------------------


def _need_user(tg_id: int) -> dict[str, Any] | None:
    return USERS.get(int(tg_id))


@app.post("/api/admin/users/{tg_id}/balance/add/{amount}")
async def api_admin_balance_add(tg_id: int, amount: int, request: Request) -> JSONResponse:
    actor = admin_record(request)
    rec = _need_user(tg_id)
    if not rec:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    rec["balance"] = int(rec.get("balance") or 0) + int(amount)
    log_admin(actor["id"], "balance_add", tg_id, {"amount": int(amount)})
    return JSONResponse({"ok": True, "balance": rec["balance"]})


@app.post("/api/admin/users/{tg_id}/balance/subtract/{amount}")
async def api_admin_balance_sub(tg_id: int, amount: int, request: Request) -> JSONResponse:
    actor = admin_record(request)
    rec = _need_user(tg_id)
    if not rec:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    rec["balance"] = max(0, int(rec.get("balance") or 0) - int(amount))
    log_admin(actor["id"], "balance_sub", tg_id, {"amount": int(amount)})
    return JSONResponse({"ok": True, "balance": rec["balance"]})


@app.post("/api/admin/users/{tg_id}/balance/zero")
async def api_admin_balance_zero(tg_id: int, request: Request) -> JSONResponse:
    actor = admin_record(request)
    rec = _need_user(tg_id)
    if not rec:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    rec["balance"] = 0
    log_admin(actor["id"], "balance_zero", tg_id, None)
    return JSONResponse({"ok": True})


@app.post("/api/admin/users/{tg_id}/stars/add/{amount}")
async def api_admin_stars_add(tg_id: int, amount: int, request: Request) -> JSONResponse:
    actor = admin_record(request)
    rec = _need_user(tg_id)
    if not rec:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    rec["stars_balance"] = int(rec.get("stars_balance") or 0) + int(amount)
    log_admin(actor["id"], "stars_add", tg_id, {"amount": int(amount)})
    return JSONResponse({"ok": True, "stars_balance": rec["stars_balance"]})


@app.post("/api/admin/users/{tg_id}/stars/subtract/{amount}")
async def api_admin_stars_sub(tg_id: int, amount: int, request: Request) -> JSONResponse:
    actor = admin_record(request)
    rec = _need_user(tg_id)
    if not rec:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    rec["stars_balance"] = max(0, int(rec.get("stars_balance") or 0) - int(amount))
    log_admin(actor["id"], "stars_sub", tg_id, {"amount": int(amount)})
    return JSONResponse({"ok": True})


@app.post("/api/admin/users/{tg_id}/days/add/{days}")
async def api_admin_days_add(tg_id: int, days: int, request: Request) -> JSONResponse:
    actor = admin_record(request)
    rec = _need_user(tg_id)
    if not rec:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    sub = rec.setdefault("subscription", {})
    base = max(int(time.time()), int(sub.get("expires_at") or 0))
    sub["expires_at"] = base + int(days) * 86400
    if not sub.get("tariff_name"):
        sub["tariff_name"] = "Подарок"
    log_admin(actor["id"], "days_add", tg_id, {"days": int(days)})
    return JSONResponse({"ok": True, "expires_at": sub["expires_at"]})


@app.post("/api/admin/users/{tg_id}/days/subtract/{days}")
async def api_admin_days_sub(tg_id: int, days: int, request: Request) -> JSONResponse:
    actor = admin_record(request)
    rec = _need_user(tg_id)
    if not rec:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    sub = rec.setdefault("subscription", {})
    sub["expires_at"] = max(int(time.time()), int(sub.get("expires_at") or 0) - int(days) * 86400)
    log_admin(actor["id"], "days_sub", tg_id, {"days": int(days)})
    return JSONResponse({"ok": True, "expires_at": sub["expires_at"]})


@app.post("/api/admin/users/{tg_id}/sub/revoke")
async def api_admin_sub_revoke(tg_id: int, request: Request) -> JSONResponse:
    actor = admin_record(request)
    rec = _need_user(tg_id)
    if not rec:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    rec["subscription"] = {}
    log_admin(actor["id"], "sub_revoke", tg_id, None)
    return JSONResponse({"ok": True})


@app.post("/api/admin/users/{tg_id}/sub/regen-uuid")
async def api_admin_sub_regen(tg_id: int, request: Request) -> JSONResponse:
    actor = admin_record(request)
    rec = _need_user(tg_id)
    if not rec:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    rec["sub_uuid"] = make_sub_uuid()
    log_admin(actor["id"], "sub_regen", tg_id, None)
    return JSONResponse({"ok": True, "sub_uuid": rec["sub_uuid"]})


@app.post("/api/admin/users/{tg_id}/ban")
async def api_admin_user_ban(tg_id: int, request: Request) -> JSONResponse:
    actor = admin_record(request)
    rec = _need_user(tg_id)
    if not rec:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    rec["banned"] = True
    log_admin(actor["id"], "ban", tg_id, None)
    return JSONResponse({"ok": True})


@app.post("/api/admin/users/{tg_id}/unban")
async def api_admin_user_unban(tg_id: int, request: Request) -> JSONResponse:
    actor = admin_record(request)
    rec = _need_user(tg_id)
    if not rec:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    rec["banned"] = False
    log_admin(actor["id"], "unban", tg_id, None)
    return JSONResponse({"ok": True})


@app.post("/api/admin/users/{tg_id}/devices/clear")
async def api_admin_devices_clear(tg_id: int, request: Request) -> JSONResponse:
    actor = admin_record(request)
    rec = _need_user(tg_id)
    if not rec:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    rec["devices"] = []
    log_admin(actor["id"], "devices_clear", tg_id, None)
    return JSONResponse({"ok": True})


@app.post("/api/admin/users/{tg_id}/trial/reset")
async def api_admin_trial_reset(tg_id: int, request: Request) -> JSONResponse:
    actor = admin_record(request)
    rec = _need_user(tg_id)
    if not rec:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    rec["free_used"] = False
    log_admin(actor["id"], "trial_reset", tg_id, None)
    return JSONResponse({"ok": True})


@app.post("/api/admin/users/{tg_id}/trial/used")
async def api_admin_trial_used(tg_id: int, request: Request) -> JSONResponse:
    actor = admin_record(request)
    rec = _need_user(tg_id)
    if not rec:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    rec["free_used"] = True
    log_admin(actor["id"], "trial_used", tg_id, None)
    return JSONResponse({"ok": True})


@app.post("/api/admin/users/{tg_id}/note/set")
async def api_admin_note_set(tg_id: int, request: Request) -> JSONResponse:
    actor = admin_record(request)
    body = await request.json()
    rec = _need_user(tg_id)
    if not rec:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    rec["note"] = str(body.get("note") or "")[:1024]
    log_admin(actor["id"], "note_set", tg_id, None)
    return JSONResponse({"ok": True})


@app.delete("/api/admin/users/{tg_id}/note")
async def api_admin_note_clear(tg_id: int, request: Request) -> JSONResponse:
    actor = admin_record(request)
    rec = _need_user(tg_id)
    if not rec:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    rec.pop("note", None)
    log_admin(actor["id"], "note_clear", tg_id, None)
    return JSONResponse({"ok": True})


@app.post("/api/admin/users/{tg_id}/tag/add/{tag}")
async def api_admin_tag_add(tg_id: int, tag: str, request: Request) -> JSONResponse:
    actor = admin_record(request)
    rec = _need_user(tg_id)
    if not rec:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    tags = set(rec.get("tags") or [])
    tags.add(str(tag)[:32])
    rec["tags"] = sorted(tags)
    log_admin(actor["id"], "tag_add", tg_id, {"tag": tag})
    return JSONResponse({"ok": True, "tags": rec["tags"]})


@app.post("/api/admin/users/{tg_id}/tag/remove/{tag}")
async def api_admin_tag_remove(tg_id: int, tag: str, request: Request) -> JSONResponse:
    actor = admin_record(request)
    rec = _need_user(tg_id)
    if not rec:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    rec["tags"] = [t for t in (rec.get("tags") or []) if t != tag]
    log_admin(actor["id"], "tag_remove", tg_id, {"tag": tag})
    return JSONResponse({"ok": True})


@app.delete("/api/admin/users/{tg_id}/tags")
async def api_admin_tags_clear(tg_id: int, request: Request) -> JSONResponse:
    actor = admin_record(request)
    rec = _need_user(tg_id)
    if not rec:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    rec["tags"] = []
    log_admin(actor["id"], "tags_clear", tg_id, None)
    return JSONResponse({"ok": True})


@app.get("/api/admin/users/{tg_id}/payments")
async def api_admin_user_payments(tg_id: int, request: Request) -> JSONResponse:
    admin_record(request)
    items = [p for p in PAYMENTS if int(p.get("tg_id") or 0) == int(tg_id)]
    items.reverse()
    return JSONResponse({"ok": True, "items": items[:200]})


@app.get("/api/admin/users/{tg_id}/payments/total")
async def api_admin_user_payments_total(tg_id: int, request: Request) -> JSONResponse:
    admin_record(request)
    items = [p for p in PAYMENTS if int(p.get("tg_id") or 0) == int(tg_id)]
    return JSONResponse({
        "ok": True,
        "count": len(items),
        "rub": sum(int(p.get("amount_rub") or 0) for p in items),
        "stars": sum(int(p.get("amount_stars") or 0) for p in items),
    })


@app.get("/api/admin/users/{tg_id}/devices")
async def api_admin_user_devices(tg_id: int, request: Request) -> JSONResponse:
    admin_record(request)
    rec = _need_user(tg_id)
    if not rec:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    return JSONResponse({"ok": True, "items": rec.get("devices") or []})


@app.get("/api/admin/users/{tg_id}/sub")
async def api_admin_user_sub(tg_id: int, request: Request) -> JSONResponse:
    admin_record(request)
    rec = _need_user(tg_id)
    if not rec:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    return JSONResponse({"ok": True, "subscription": rec.get("subscription") or {}, "sub_uuid": rec.get("sub_uuid")})


@app.get("/api/admin/users/count")
async def api_admin_users_count(request: Request) -> JSONResponse:
    admin_record(request)
    return JSONResponse({"ok": True, "count": len(USERS)})


@app.get("/api/admin/users/count/active")
async def api_admin_users_count_active(request: Request) -> JSONResponse:
    admin_record(request)
    now = int(time.time())
    return JSONResponse({"ok": True, "count": sum(1 for u in USERS.values() if int((u.get("subscription") or {}).get("expires_at") or 0) > now)})


@app.get("/api/admin/users/count/banned")
async def api_admin_users_count_banned(request: Request) -> JSONResponse:
    admin_record(request)
    return JSONResponse({"ok": True, "count": sum(1 for u in USERS.values() if u.get("banned"))})


@app.get("/api/admin/users/count/trial")
async def api_admin_users_count_trial(request: Request) -> JSONResponse:
    admin_record(request)
    return JSONResponse({"ok": True, "count": sum(1 for u in USERS.values() if u.get("free_used"))})


@app.get("/api/admin/users/sum/balance")
async def api_admin_users_sum_balance(request: Request) -> JSONResponse:
    admin_record(request)
    return JSONResponse({"ok": True, "sum": sum(int(u.get("balance") or 0) for u in USERS.values())})


@app.get("/api/admin/users/sum/stars")
async def api_admin_users_sum_stars(request: Request) -> JSONResponse:
    admin_record(request)
    return JSONResponse({"ok": True, "sum": sum(int(u.get("stars_balance") or 0) for u in USERS.values())})


@app.get("/api/admin/users/sum/spent")
async def api_admin_users_sum_spent(request: Request) -> JSONResponse:
    admin_record(request)
    return JSONResponse({"ok": True, "sum": sum(int(u.get("total_spent") or 0) for u in USERS.values())})


@app.get("/api/admin/payments/count")
async def api_admin_payments_count(request: Request) -> JSONResponse:
    admin_record(request)
    return JSONResponse({"ok": True, "count": len(PAYMENTS)})


@app.get("/api/admin/payments/sum/rub")
async def api_admin_payments_sum_rub(request: Request) -> JSONResponse:
    admin_record(request)
    return JSONResponse({"ok": True, "sum": sum(int(p.get("amount_rub") or 0) for p in PAYMENTS)})


@app.get("/api/admin/payments/sum/stars")
async def api_admin_payments_sum_stars(request: Request) -> JSONResponse:
    admin_record(request)
    return JSONResponse({"ok": True, "sum": sum(int(p.get("amount_stars") or 0) for p in PAYMENTS)})


@app.get("/api/admin/payments/recent/{n}")
async def api_admin_payments_recent(n: int, request: Request) -> JSONResponse:
    admin_record(request)
    items = list(PAYMENTS)[-max(1, min(int(n), 500)):]
    items.reverse()
    return JSONResponse({"ok": True, "items": items})


@app.get("/api/admin/payments/by-provider/{provider}")
async def api_admin_payments_by_provider(provider: str, request: Request) -> JSONResponse:
    admin_record(request)
    return JSONResponse({"ok": True, "items": [p for p in PAYMENTS if p.get("provider") == provider]})


@app.get("/api/admin/payments/by-status/{status}")
async def api_admin_payments_by_status(status: str, request: Request) -> JSONResponse:
    admin_record(request)
    return JSONResponse({"ok": True, "items": [p for p in PAYMENTS if p.get("status") == status]})


@app.get("/api/admin/payments/last")
async def api_admin_payments_last(request: Request) -> JSONResponse:
    admin_record(request)
    return JSONResponse({"ok": True, "item": PAYMENTS[-1] if PAYMENTS else None})


@app.delete("/api/admin/payments/clear")
async def api_admin_payments_clear(request: Request) -> JSONResponse:
    actor = admin_record(request)
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    confirm = str(body.get("confirm") or "")
    if not (confirm.isdigit() and 1 <= len(confirm) <= 5):
        return JSONResponse({"ok": False, "error": "confirm_required"}, status_code=400)
    PAYMENTS.clear()
    log_admin(actor["id"], "payments_clear", None, None)
    return JSONResponse({"ok": True})


@app.get("/api/admin/log/recent/{n}")
async def api_admin_log_recent(n: int, request: Request) -> JSONResponse:
    admin_record(request)
    return JSONResponse({"ok": True, "items": ADMIN_LOG[-max(1, min(int(n), 500)):][::-1]})


@app.get("/api/admin/log/by-action/{action}")
async def api_admin_log_by_action(action: str, request: Request) -> JSONResponse:
    admin_record(request)
    return JSONResponse({"ok": True, "items": [r for r in ADMIN_LOG if r.get("action") == action]})


@app.get("/api/admin/log/by-actor/{actor_id}")
async def api_admin_log_by_actor(actor_id: int, request: Request) -> JSONResponse:
    admin_record(request)
    return JSONResponse({"ok": True, "items": [r for r in ADMIN_LOG if int(r.get("actor") or 0) == int(actor_id)]})


@app.get("/api/admin/log/by-target/{target_id}")
async def api_admin_log_by_target(target_id: int, request: Request) -> JSONResponse:
    admin_record(request)
    return JSONResponse({"ok": True, "items": [r for r in ADMIN_LOG if int(r.get("target") or 0) == int(target_id)]})


@app.delete("/api/admin/log")
async def api_admin_log_clear(request: Request) -> JSONResponse:
    actor = admin_record(request)
    ADMIN_LOG.clear()
    log_admin(actor["id"], "log_clear", None, None)
    return JSONResponse({"ok": True})


@app.get("/api/admin/events/by-type/{type_}")
async def api_admin_events_by_type(type_: str, request: Request) -> JSONResponse:
    admin_record(request)
    return JSONResponse({"ok": True, "items": [e for e in USER_EVENTS_GLOBAL if e.get("type") == type_][-500:][::-1]})


@app.get("/api/admin/events/types")
async def api_admin_events_types(request: Request) -> JSONResponse:
    admin_record(request)
    counts: dict[str, int] = {}
    for e in USER_EVENTS_GLOBAL:
        t = e.get("type") or "?"
        counts[t] = counts.get(t, 0) + 1
    return JSONResponse({"ok": True, "items": counts})


@app.get("/api/admin/events/recent/{n}")
async def api_admin_events_recent(n: int, request: Request) -> JSONResponse:
    admin_record(request)
    return JSONResponse({"ok": True, "items": USER_EVENTS_GLOBAL[-max(1, min(int(n), 2000)):][::-1]})


@app.get("/api/admin/events/count")
async def api_admin_events_count(request: Request) -> JSONResponse:
    admin_record(request)
    return JSONResponse({"ok": True, "count": len(USER_EVENTS_GLOBAL)})


@app.get("/api/admin/events/active-users")
async def api_admin_events_active_users(request: Request) -> JSONResponse:
    admin_record(request)
    horizon = int(time.time()) - 86400
    active = {e.get("tg_id") for e in USER_EVENTS_GLOBAL if e.get("ts") and e["ts"] > horizon and e.get("tg_id")}
    return JSONResponse({"ok": True, "count": len(active), "users": sorted(x for x in active if x)})


@app.get("/api/admin/maintenance/status")
async def api_admin_maintenance_status(request: Request) -> JSONResponse:
    admin_record(request)
    return JSONResponse({
        "ok": True,
        "site_locked": bool(CONFIG.get("site_locked")),
        "bot_locked": bool(CONFIG.get("bot_locked")),
        "message": CONFIG.get("maintenance_message") or "",
    })


@app.get("/api/admin/config/all")
async def api_admin_config_all(request: Request) -> JSONResponse:
    admin_record(request)
    return JSONResponse({"ok": True, "config": CONFIG})


@app.post("/api/admin/config/set/{key}")
async def api_admin_config_set(key: str, request: Request) -> JSONResponse:
    actor = admin_record(request)
    body = await request.json()
    if key not in CONFIG and key not in {"channel_url", "support_url", "stars_rate_rub", "stars_rate_usd",
                                          "trial_days", "maintenance_message"}:
        return JSONResponse({"ok": False, "error": "unknown_key"}, status_code=400)
    CONFIG[key] = body.get("value")
    log_admin(actor["id"], f"config_set:{key}", None, {"value": body.get("value")})
    return JSONResponse({"ok": True})


# Tariff CRUD shortcuts
@app.get("/api/admin/tariffs")
async def api_admin_tariffs(request: Request) -> JSONResponse:
    admin_record(request)
    return JSONResponse({"ok": True, "items": CONFIG.get("tariffs") or []})


@app.post("/api/admin/tariffs/{key}/price/rub/{value}")
async def api_admin_tariff_price_rub(key: str, value: int, request: Request) -> JSONResponse:
    actor = admin_record(request)
    for t in CONFIG.get("tariffs") or []:
        if t.get("key") == key:
            t["price_rub"] = int(value)
            log_admin(actor["id"], "tariff_price_rub", None, {"key": key, "value": int(value)})
            return JSONResponse({"ok": True})
    return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)


@app.post("/api/admin/tariffs/{key}/price/stars/{value}")
async def api_admin_tariff_price_stars(key: str, value: int, request: Request) -> JSONResponse:
    actor = admin_record(request)
    for t in CONFIG.get("tariffs") or []:
        if t.get("key") == key:
            t["price_stars"] = int(value)
            log_admin(actor["id"], "tariff_price_stars", None, {"key": key, "value": int(value)})
            return JSONResponse({"ok": True})
    return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)


@app.post("/api/admin/tariffs/{key}/days/{days}")
async def api_admin_tariff_days(key: str, days: int, request: Request) -> JSONResponse:
    actor = admin_record(request)
    for t in CONFIG.get("tariffs") or []:
        if t.get("key") == key:
            t["days"] = int(days)
            log_admin(actor["id"], "tariff_days", None, {"key": key, "value": int(days)})
            return JSONResponse({"ok": True})
    return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)


@app.post("/api/admin/tariffs/{key}/devices/{n}")
async def api_admin_tariff_devices(key: str, n: int, request: Request) -> JSONResponse:
    actor = admin_record(request)
    for t in CONFIG.get("tariffs") or []:
        if t.get("key") == key:
            t["devices"] = int(n)
            log_admin(actor["id"], "tariff_devices", None, {"key": key, "value": int(n)})
            return JSONResponse({"ok": True})
    return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)


@app.post("/api/admin/tariffs/{key}/enable")
async def api_admin_tariff_enable(key: str, request: Request) -> JSONResponse:
    actor = admin_record(request)
    for t in CONFIG.get("tariffs") or []:
        if t.get("key") == key:
            t["enabled"] = True
            log_admin(actor["id"], "tariff_enable", None, {"key": key})
            return JSONResponse({"ok": True})
    return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)


@app.post("/api/admin/tariffs/{key}/disable")
async def api_admin_tariff_disable(key: str, request: Request) -> JSONResponse:
    actor = admin_record(request)
    for t in CONFIG.get("tariffs") or []:
        if t.get("key") == key:
            t["enabled"] = False
            log_admin(actor["id"], "tariff_disable", None, {"key": key})
            return JSONResponse({"ok": True})
    return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)


@app.delete("/api/admin/tariffs/{key}")
async def api_admin_tariff_delete(key: str, request: Request) -> JSONResponse:
    actor = admin_record(request)
    before = len(CONFIG.get("tariffs") or [])
    CONFIG["tariffs"] = [t for t in (CONFIG.get("tariffs") or []) if t.get("key") != key]
    if len(CONFIG["tariffs"]) == before:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    log_admin(actor["id"], "tariff_delete", None, {"key": key})
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# Exception safety net — catch unhandled exceptions instead of crashing
# ---------------------------------------------------------------------------


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, HTTPException):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    logger.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        {"ok": False, "error": "server_error", "detail": str(exc)[:200]},
        status_code=500,
    )


# ---------------------------------------------------------------------------
# Static + admin page
# ---------------------------------------------------------------------------


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static-assets")


def _serve_static(name: str) -> Response:
    safe = (STATIC_DIR / name).resolve()
    if not str(safe).startswith(str(STATIC_DIR.resolve())) or not safe.is_file():
        return Response(status_code=404)
    media_types = {
        ".html": "text/html",
        ".css": "text/css",
        ".js": "application/javascript",
        ".mjs": "application/javascript",
        ".json": "application/json",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".svg": "image/svg+xml",
        ".ico": "image/x-icon",
        ".webp": "image/webp",
        ".woff": "font/woff",
        ".woff2": "font/woff2",
        ".ttf": "font/ttf",
        ".webmanifest": "application/manifest+json",
    }
    return Response(safe.read_bytes(), media_type=media_types.get(safe.suffix, "application/octet-stream"))


@app.get("/")
async def index() -> Response:
    return _serve_static("index.html")


@app.get("/jutso")
@app.get("/jutso/")
@app.get("/sendvpn")
@app.get("/sendvpn/")
async def jutso_index() -> Response:
    return _serve_static("jutso/index.html")


@app.get("/jutso/{filename}")
async def jutso_file(filename: str) -> Response:
    return _serve_static(f"jutso/{filename}")


@app.get("/sendvpn/{filename}")
async def sendvpn_file(filename: str) -> Response:
    return _serve_static(f"jutso/{filename}")


@app.get("/sub")
@app.get("/sub/")
async def sub_index() -> Response:
    return _serve_static("sub/index.html")


@app.get("/sub/{filename:path}")
async def sub_file(filename: str) -> Response:
    return _serve_static(f"sub/{filename}")


@app.get("/assets/.app-config-v2.json")
async def sub_app_config() -> Response:
    """The Remnawave subscription page bundle hard-codes a fetch to
    `/assets/.app-config-v2.json` (root-absolute, not /sub-relative). Serve a
    valid config here so the React app can finish booting on /sub."""
    return _serve_static("sub-app-config-v2.json")


@app.get("/legal/offer")
@app.get("/legal/offer/")
async def legal_offer() -> Response:
    return _serve_static("legal/offer.html")


@app.get("/legal/privacy")
@app.get("/legal/privacy/")
async def legal_privacy() -> Response:
    return _serve_static("legal/privacy.html")


@app.get("/legal/{filename}")
async def legal_file(filename: str) -> Response:
    return _serve_static(f"legal/{filename}")


@app.get("/{filename}")
async def root_file(filename: str) -> Response:
    return _serve_static(filename)


# ---------------------------------------------------------------------------
# Persistence: load on startup, flush periodically + on shutdown.
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def _on_startup() -> None:
    _load_state_sync()

    async def _flusher() -> None:
        global _state_dirty
        while True:
            await asyncio.sleep(2.0)
            if _state_dirty:
                _state_dirty = False
                _persist_state_sync()
            else:
                # Periodic safety flush every ~60s in case of missed mark_dirty
                pass

    async def _periodic_safety() -> None:
        while True:
            await asyncio.sleep(60.0)
            _persist_state_sync()

    asyncio.create_task(_flusher())
    asyncio.create_task(_periodic_safety())

    # Run the Telegram bot polling loop in-process so /start, /admin etc.
    # work without a separate worker.
    if os.environ.get("RUN_BOT", "1") not in {"0", "false", "False", ""}:
        try:
            from app.bot import run_bot  # noqa: WPS433

            async def _bot_supervisor() -> None:
                while True:
                    try:
                        await run_bot()
                    except Exception:  # noqa: BLE001
                        logger.exception("Bot polling crashed; restarting in 5s")
                        await asyncio.sleep(5.0)

            asyncio.create_task(_bot_supervisor())
            logger.info("Telegram bot polling task scheduled")
        except Exception:  # noqa: BLE001
            logger.exception("Failed to schedule bot polling task")


@app.on_event("shutdown")
async def _on_shutdown() -> None:
    _persist_state_sync()


@app.middleware("http")
async def _persist_middleware(request: Request, call_next):
    """Mark state dirty on any non-GET request so the flusher saves it within ~2s."""
    response = await call_next(request)
    try:
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            mark_dirty()
    except Exception:
        pass
    return response
