import asyncio
import html as _html
import logging
import os

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    MenuButtonDefault,
    PreCheckoutQuery,
    WebAppInfo,
)

logging.basicConfig(level=logging.INFO)

TOKEN = (os.environ.get("BOT_TOKEN") or "8617108727:AAFA9A3QaR9hmAzLsrtqW6A74A6VhpCEubQ").strip()
WEBAPP_URL = os.environ.get("WEBAPP_URL", "https://jutsovpn-backend-gfyfeciw.fly.dev/")
ADMIN_URL = os.environ.get("ADMIN_URL", "https://jutsovpn-backend-gfyfeciw.fly.dev/jutso")
BACKEND_URL = os.environ.get("BACKEND_URL", "https://jutsovpn-backend-gfyfeciw.fly.dev").rstrip("/")
INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "") or "sendvpn-internal-prod-2026-Tt7Lp9Qr"
SUPPORT_URL_FALLBACK = os.environ.get("SUPPORT_URL", "https://t.me/jutsodev")
CHANNEL_URL_FALLBACK = os.environ.get("CHANNEL_URL", "https://t.me/jutsovpn")
ADMIN_IDS = {
    int(value)
    for value in os.environ.get("ADMIN_IDS", "8228905313").replace(",", " ").split()
    if value.strip().isdigit()
}

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Default bot UI strings — used as a fallback when backend is unreachable.
DEFAULT_SETTINGS: dict[str, object] = {
    "bot_start_text": "<b>Ваш профиль:</b>\n<blockquote>Откройте приложение. Для подключения VPN.</blockquote>",
    "bot_button_app": "📱 Открыть приложение",
    "bot_button_info": "ℹ Информация",
    "bot_button_admin": "🛠 Админ-панель",
    "bot_info_text": "<b>Информация</b>\n<blockquote>JutsoVPN — быстрый и приватный VPN с подпиской через Telegram.</blockquote>",
    "bot_button_support": "💬 Поддержка",
    "bot_button_channel": "📢 Новостной канал",
    "bot_button_back": "◀ Назад",
    "support_url": SUPPORT_URL_FALLBACK,
    "channel_url": CHANNEL_URL_FALLBACK,
    "bot_locked_message": "🛠 <b>Бот временно отключён</b> и находится в стадии разработки.\n<blockquote>Зайдите чуть позже.</blockquote>",
    "bot_locked": False,
}
# Keys that are booleans (toggles); everything else is a string.
BOOL_KEYS: set[str] = {"bot_locked"}

# In-memory cache of bot settings (refreshed lazily on each /start and /admin).
SETTINGS_CACHE: dict[str, object] = dict(DEFAULT_SETTINGS)
# Pending edit state per admin user: {user_id: setting_key}
PENDING_EDITS: dict[int, str] = {}

# Human-readable labels for /admin panel buttons.
ADMIN_FIELD_LABELS: dict[str, str] = {
    "bot_start_text": "✏ Текст /start",
    "bot_button_app": "🔘 Кнопка приложения",
    "bot_button_info": "🔘 Кнопка «Информация»",
    "bot_button_admin": "🔘 Кнопка админки",
    "bot_info_text": "✏ Текст «Информация»",
    "bot_button_support": "🔘 Кнопка поддержки",
    "bot_button_channel": "🔘 Кнопка канала",
    "bot_button_back": "🔘 Кнопка «Назад»",
    "support_url": "🔗 Ссылка поддержки",
    "channel_url": "🔗 Ссылка канала",
    "bot_locked_message": "✏ Текст «Бот в разработке»",
}


def _merge_settings(remote: dict) -> None:
    for k, default in DEFAULT_SETTINGS.items():
        v = remote.get(k)
        if k in BOOL_KEYS:
            SETTINGS_CACHE[k] = bool(v) if v is not None else bool(default)
        else:
            SETTINGS_CACHE[k] = v if isinstance(v, str) and v else default


async def fetch_bot_settings() -> dict[str, object]:
    """Pull editable bot UI strings from backend; cache locally."""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
            async with session.get(
                f"{BACKEND_URL}/api/internal/bot-settings",
                headers={"X-Internal-Key": INTERNAL_API_KEY},
            ) as response:
                if response.status == 200:
                    data = await response.json(content_type=None)
                    _merge_settings(data.get("settings") or {})
    except Exception:  # noqa: BLE001
        logging.exception("fetch_bot_settings failed")
    return SETTINGS_CACHE


async def save_bot_setting(key: str, value) -> bool:
    if key not in DEFAULT_SETTINGS:
        return False
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.post(
                f"{BACKEND_URL}/api/internal/bot-settings",
                json={key: value},
                headers={"X-Internal-Key": INTERNAL_API_KEY},
            ) as response:
                if response.status == 200:
                    data = await response.json(content_type=None)
                    _merge_settings(data.get("settings") or {})
                    return True
    except Exception:  # noqa: BLE001
        logging.exception("save_bot_setting failed")
    return False


def main_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    s = SETTINGS_CACHE
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=s["bot_button_app"], web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton(text=s["bot_button_info"], callback_data="info:open")],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton(text=s["bot_button_admin"], web_app=WebAppInfo(url=ADMIN_URL))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def info_keyboard() -> InlineKeyboardMarkup:
    s = SETTINGS_CACHE
    rows = [
        [InlineKeyboardButton(text=s["bot_button_support"], url=s["support_url"])],
        [InlineKeyboardButton(text=s["bot_button_channel"], url=s["channel_url"])],
        [InlineKeyboardButton(text=s["bot_button_back"], callback_data="info:close")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    locked = bool(SETTINGS_CACHE.get("bot_locked"))
    toggle_label = "🟢 Вкл бота (сейчас в разработке)" if locked else "🛑 Выключить бота (разработка)"
    rows.append([InlineKeyboardButton(text=toggle_label, callback_data="adm:toggle_lock")])
    rows.append([InlineKeyboardButton(text="👥 Пользователи", callback_data="adm:users:0")])
    for key, label in ADMIN_FIELD_LABELS.items():
        rows.append([InlineKeyboardButton(text=label, callback_data=f"adm:edit:{key}")])
    rows.append([InlineKeyboardButton(text="🔍 Превью /start", callback_data="adm:preview")])
    rows.append([InlineKeyboardButton(text="🔍 Превью заглушки «в разработке»", callback_data="adm:preview_lock")])
    rows.append([InlineKeyboardButton(text="🔄 Сбросить всё к дефолту", callback_data="adm:reset")])
    rows.append([InlineKeyboardButton(text="✖ Закрыть", callback_data="adm:close")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_panel_text() -> str:
    """Compact summary for the /admin panel.

    The user-editable values may contain HTML (e.g. <blockquote>), so we MUST
    NOT nest them inside another <blockquote> — Telegram does not support
    nested blockquotes and silently rejects edit_text. Show only short
    previews of HTML fields and full plain text for short fields.
    """
    s = SETTINGS_CACHE
    locked = bool(s.get("bot_locked"))
    status_line = "🛑 <b>Бот выключен</b> (режим разработки)" if locked else "🟢 <b>Бот работает</b>"
    def _preview(value: str, limit: int = 80) -> str:
        # Strip HTML tags for the inline summary, then escape & truncate.
        import re
        plain = re.sub(r"<[^>]+>", "", value or "").strip()
        if len(plain) > limit:
            plain = plain[: limit - 1] + "…"
        return _html.escape(plain) if plain else "—"
    lines = [
        f"<b>🛠 Админ-панель бота</b>",
        status_line,
        "",
        f"📝 <b>/start</b>: {_preview(str(s['bot_start_text']))}",
        f"🔘 <b>Приложение</b>: {_html.escape(str(s['bot_button_app']))}",
        f"🔘 <b>Информация</b>: {_html.escape(str(s['bot_button_info']))}",
        f"🔘 <b>Админка</b>: {_html.escape(str(s['bot_button_admin']))}",
        f"📝 <b>Информация</b>: {_preview(str(s['bot_info_text']))}",
        f"🔘 <b>Поддержка</b>: {_html.escape(str(s['bot_button_support']))} → <code>{_html.escape(str(s['support_url']))}</code>",
        f"🔘 <b>Канал</b>: {_html.escape(str(s['bot_button_channel']))} → <code>{_html.escape(str(s['channel_url']))}</code>",
        f"🔘 <b>Назад</b>: {_html.escape(str(s['bot_button_back']))}",
        f"📝 <b>Разработка</b>: {_preview(str(s['bot_locked_message']))}",
        "",
        "Жми на пункт ниже — пришлёшь новое значение одним сообщением. HTML работает: <code>&lt;b&gt;</code>, <code>&lt;i&gt;</code>, <code>&lt;u&gt;</code>, <code>&lt;s&gt;</code>, <code>&lt;code&gt;</code>, <code>&lt;a href=…&gt;</code>, <code>&lt;blockquote&gt;</code>, эмодзи.",
    ]
    return "\n".join(lines)


async def fetch_users_list(offset: int = 0, limit: int = 10, q: str = "") -> dict:
    try:
        params: dict[str, str] = {"offset": str(offset), "limit": str(limit)}
        if q:
            params["q"] = q
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
            async with session.get(
                f"{BACKEND_URL}/api/internal/users",
                params=params,
                headers={"X-Internal-Key": INTERNAL_API_KEY},
            ) as response:
                if response.status == 200:
                    return await response.json(content_type=None)
    except Exception:  # noqa: BLE001
        logging.exception("fetch_users_list failed")
    return {"ok": False, "items": [], "total": 0, "offset": offset, "limit": limit}


async def fetch_user_detail(tg_id: int) -> dict:
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
            async with session.get(
                f"{BACKEND_URL}/api/internal/users/{tg_id}",
                headers={"X-Internal-Key": INTERNAL_API_KEY},
            ) as response:
                if response.status == 200:
                    return await response.json(content_type=None)
    except Exception:  # noqa: BLE001
        logging.exception("fetch_user_detail failed")
    return {"ok": False, "user": None}


async def do_user_action(tg_id: int, body: dict) -> dict:
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
            async with session.post(
                f"{BACKEND_URL}/api/internal/users/{tg_id}/action",
                json=body,
                headers={"X-Internal-Key": INTERNAL_API_KEY},
            ) as response:
                return await response.json(content_type=None)
    except Exception:  # noqa: BLE001
        logging.exception("do_user_action failed")
    return {"ok": False, "error": "network"}


def _fmt_ts(ts: int) -> str:
    if not ts:
        return "—"
    try:
        from datetime import datetime, timezone, timedelta
        dt = datetime.fromtimestamp(int(ts), tz=timezone.utc) + timedelta(hours=3)
        months_ru = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
        return f"{dt.day} {months_ru[dt.month-1]} {dt.year}, {dt.hour:02d}:{dt.minute:02d}"
    except Exception:  # noqa: BLE001
        return "—"


def users_list_keyboard(items: list, offset: int, limit: int, total: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for u in items:
        tg_id = int(u.get("tg_id") or 0)
        name = (u.get("name") or "—")[:24]
        username = u.get("username") or ""
        days = int(u.get("days_left") or 0)
        balance = int(u.get("balance") or 0)
        flag = "🚫" if u.get("banned") else ("⭐" if u.get("has_subscription") else ("🆓" if not u.get("free_used") else "·"))
        handle = f" @{username}" if username else ""
        label = f"{flag} {name}{handle} · {days}д · {balance}₽"
        if len(label) > 60:
            label = label[:59] + "…"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"adm:u:{tg_id}")])
    nav: list[InlineKeyboardButton] = []
    if offset > 0:
        prev_off = max(0, offset - limit)
        nav.append(InlineKeyboardButton(text="◀ Назад", callback_data=f"adm:users:{prev_off}"))
    nav.append(InlineKeyboardButton(text=f"📄 {offset // limit + 1} / {(total + limit - 1) // max(1,limit)}", callback_data="adm:users:noop"))
    if offset + limit < total:
        nav.append(InlineKeyboardButton(text="Вперёд ▶", callback_data=f"adm:users:{offset + limit}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="↩ В админ-панель", callback_data="adm:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def users_list_text(items: list, offset: int, limit: int, total: int) -> str:
    lines = [f"<b>👥 Пользователи · всего {total}</b>"]
    if not items:
        lines.append("\n<i>Пусто.</i>")
        return "\n".join(lines)
    lines.append(f"<i>Показано {offset+1}–{offset+len(items)}</i>")
    return "\n".join(lines)


def user_card_text(u: dict) -> str:
    if not u:
        return "Пользователь не найден."
    tg_id = int(u.get("tg_id") or 0)
    name = u.get("name") or "—"
    username = u.get("username") or ""
    handle = f"@{_html.escape(username)}" if username else "—"
    lang = u.get("language_code") or "—"
    has_sub = bool(u.get("has_subscription"))
    tariff = u.get("tariff_name") or "—"
    days_left = int(u.get("days_left") or 0)
    expires_human = u.get("expires_human") or "—"
    balance = int(u.get("balance") or 0)
    stars = int(u.get("stars_balance") or 0)
    devices_active = int(u.get("devices_active") or 0)
    devices_max = int(u.get("devices_max") or 0)
    free_used = bool(u.get("free_used"))
    banned = bool(u.get("banned"))
    created_at = int(u.get("created_at") or 0)
    last_seen = int(u.get("last_seen") or 0)
    ref_code = u.get("ref_code") or ""
    ref_count = len(u.get("referrals") or [])
    referred_by = int(u.get("referred_by") or 0)
    sub_status = "🟢 активна" if has_sub else "⚪ нет"
    if banned:
        sub_status = "🚫 забанен"
    sub_block = (
        f"<b>{_html.escape(tariff)}</b> · {sub_status}\n"
        f"{'до ' + _html.escape(expires_human) if has_sub else 'нет'} · осталось {days_left} д."
    )
    trial_block = "✅ использован" if free_used else "🆓 доступен"
    referred_block = f"👤 пригласил: <code>{referred_by}</code>" if referred_by else "👤 не приглашал никто"
    lines = [
        f"<b>👤 {_html.escape(name)}</b>  ·  {handle}",
        f"🆔 <code>{tg_id}</code>  ·  🌐 {_html.escape(lang)}",
        "",
        f"📅 <b>Зашёл впервые:</b> {_fmt_ts(created_at)}",
        f"⏱ <b>Был активен:</b> {_fmt_ts(last_seen)}",
        "",
        f"💳 <b>Подписка:</b> {sub_block}",
        f"🎁 <b>Триал:</b> {trial_block}",
        f"📱 <b>Устройств:</b> {devices_active} / {devices_max}",
        "",
        f"💰 <b>Баланс:</b> {balance} ₽  ·  ⭐ {stars}",
        "",
        f"👥 <b>Рефералов:</b> {ref_count}" + (f"  ·  код <code>{_html.escape(ref_code)}</code>" if ref_code else ""),
        referred_block,
    ]
    return "\n".join(lines)


def user_card_keyboard(u: dict) -> InlineKeyboardMarkup:
    tg_id = int(u.get("tg_id") or 0)
    banned = bool(u.get("banned"))
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text="➕ 1 день", callback_data=f"adm:ug:1:{tg_id}"),
            InlineKeyboardButton(text="➕ 7 дней", callback_data=f"adm:ug:7:{tg_id}"),
            InlineKeyboardButton(text="➕ 30 дней", callback_data=f"adm:ug:30:{tg_id}"),
        ],
        [
            InlineKeyboardButton(text="➖ Отозвать подписку", callback_data=f"adm:ua:revoke:{tg_id}"),
        ],
        [
            InlineKeyboardButton(text="💰 +100₽", callback_data=f"adm:ub:100:{tg_id}"),
            InlineKeyboardButton(text="💰 +500₽", callback_data=f"adm:ub:500:{tg_id}"),
            InlineKeyboardButton(text="💰 −100₽", callback_data=f"adm:ub:-100:{tg_id}"),
        ],
        [
            InlineKeyboardButton(text="⭐ +50", callback_data=f"adm:us:50:{tg_id}"),
            InlineKeyboardButton(text="⭐ +200", callback_data=f"adm:us:200:{tg_id}"),
            InlineKeyboardButton(text="⭐ −50", callback_data=f"adm:us:-50:{tg_id}"),
        ],
        [
            InlineKeyboardButton(text="🆓 Сбросить триал", callback_data=f"adm:ua:reset_trial:{tg_id}"),
            InlineKeyboardButton(text="📱 Очистить устройства", callback_data=f"adm:ua:clear_devices:{tg_id}"),
        ],
        [
            InlineKeyboardButton(text="✅ Разбан" if banned else "🚫 Бан",
                                 callback_data=f"adm:ua:{'unban' if banned else 'ban'}:{tg_id}"),
            InlineKeyboardButton(text="🔄 Перевыпустить sub_uuid", callback_data=f"adm:ua:regen_sub:{tg_id}"),
        ],
        [
            InlineKeyboardButton(text="🗑 Удалить пользователя", callback_data=f"adm:ua:delete:{tg_id}"),
        ],
        [
            InlineKeyboardButton(text="↩ К списку", callback_data="adm:users:0"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def fetch_maintenance() -> dict:
    """Fetch current site/bot maintenance flags from backend (best-effort)."""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
            async with session.get(f"{BACKEND_URL}/api/config/maintenance") as response:
                if response.status == 200:
                    return await response.json(content_type=None)
    except Exception:  # noqa: BLE001
        pass
    return {}


async def fetch_user_profile(tg_id: int, user_obj=None) -> dict:
    """Fetch user snapshot from backend; upserts on first call."""
    params: dict[str, str] = {}
    if user_obj is not None:
        for key in ("first_name", "last_name", "username", "language_code"):
            val = getattr(user_obj, key, "") or ""
            if val:
                params[key] = str(val)
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
            async with session.get(
                f"{BACKEND_URL}/api/internal/user/{tg_id}",
                params=params,
                headers={"X-Internal-Key": INTERNAL_API_KEY},
            ) as response:
                if response.status == 200:
                    return await response.json(content_type=None)
    except Exception:  # noqa: BLE001
        logging.exception("fetch_user_profile failed")
    return {}


async def grant_subscription(tg_id: int, tariff_key: str, payment: str, user_obj=None) -> dict:
    try:
        body = {"tg_id": tg_id, "tariff_key": tariff_key, "payment": payment}
        if user_obj:
            body["first_name"] = getattr(user_obj, "first_name", "") or ""
            body["username"] = getattr(user_obj, "username", "") or ""
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.post(
                f"{BACKEND_URL}/api/internal/grant-subscription",
                json=body,
                headers={"X-Internal-Key": INTERNAL_API_KEY},
            ) as response:
                return await response.json(content_type=None)
    except Exception:  # noqa: BLE001
        logging.exception("grant_subscription failed")
        return {"ok": False, "error": "network"}


@dp.message(CommandStart())
async def on_start(message: Message) -> None:
    user = message.from_user
    user_id = user.id if user else 0
    is_admin = user_id in ADMIN_IDS
    await fetch_bot_settings()
    if SETTINGS_CACHE.get("bot_locked") and not is_admin:
        text = str(SETTINGS_CACHE.get("bot_locked_message") or DEFAULT_SETTINGS["bot_locked_message"])
        try:
            await message.answer(text, disable_web_page_preview=True)
        except TelegramBadRequest:
            await message.answer(_html.escape(text), disable_web_page_preview=True)
        return
    await fetch_user_profile(user_id, user)
    text = str(SETTINGS_CACHE["bot_start_text"])
    try:
        await message.answer(text, reply_markup=main_keyboard(is_admin=is_admin), disable_web_page_preview=True)
    except TelegramBadRequest as e:
        logging.warning("start text invalid HTML, sending plain: %s", e)
        await message.answer(_html.escape(text), reply_markup=main_keyboard(is_admin=is_admin), disable_web_page_preview=True)


@dp.callback_query(F.data == "info:open")
async def on_info_open(query: CallbackQuery) -> None:
    if not query.message:
        await query.answer()
        return
    await fetch_bot_settings()
    try:
        try:
            await query.message.edit_text(SETTINGS_CACHE["bot_info_text"], reply_markup=info_keyboard(), disable_web_page_preview=True)
        except TelegramBadRequest:
            try:
                await query.message.answer(SETTINGS_CACHE["bot_info_text"], reply_markup=info_keyboard(), disable_web_page_preview=True)
            except Exception:  # noqa: BLE001
                pass
        await query.answer()
    except Exception:  # noqa: BLE001
        logging.exception("info_open failed")
        try:
            await query.answer("Не удалось открыть, попробуйте позже.", show_alert=True)
        except Exception:  # noqa: BLE001
            pass


@dp.callback_query(F.data == "info:close")
async def on_info_close(query: CallbackQuery) -> None:
    if not query.message:
        await query.answer()
        return
    user_obj = query.from_user
    user_id = user_obj.id if user_obj else 0
    is_admin = user_id in ADMIN_IDS
    await fetch_bot_settings()
    try:
        try:
            await query.message.edit_text(
                SETTINGS_CACHE["bot_start_text"],
                reply_markup=main_keyboard(is_admin=is_admin),
                disable_web_page_preview=True,
            )
        except TelegramBadRequest:
            pass
        await query.answer()
    except Exception:  # noqa: BLE001
        logging.exception("info_close failed")
        try:
            await query.answer()
        except Exception:  # noqa: BLE001
            pass


# ---------- /admin command ----------

@dp.message(Command("admin"))
async def on_admin(message: Message) -> None:
    user = message.from_user
    user_id = user.id if user else 0
    if user_id not in ADMIN_IDS:
        return
    await fetch_bot_settings()
    PENDING_EDITS.pop(user_id, None)
    try:
        await message.answer(admin_panel_text(), reply_markup=admin_panel_keyboard(), disable_web_page_preview=True)
    except TelegramBadRequest as e:
        await message.answer(f"Не удалось показать панель: {_html.escape(str(e))}")


@dp.callback_query(F.data.startswith("adm:"))
async def on_admin_callback(query: CallbackQuery) -> None:
    user_obj = query.from_user
    user_id = user_obj.id if user_obj else 0
    if user_id not in ADMIN_IDS:
        await query.answer("Только для админа.", show_alert=True)
        return
    if not query.message:
        await query.answer()
        return
    data = query.data or ""
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "close":
        try:
            await query.message.delete()
        except Exception:  # noqa: BLE001
            pass
        PENDING_EDITS.pop(user_id, None)
        await query.answer("Закрыто.")
        return

    if action == "preview":
        await fetch_bot_settings()
        try:
            await query.message.answer(
                str(SETTINGS_CACHE["bot_start_text"]),
                reply_markup=main_keyboard(is_admin=True),
                disable_web_page_preview=True,
            )
            await query.answer("Превью /start отправлено.")
        except TelegramBadRequest as e:
            await query.answer(f"Ошибка HTML: {e}", show_alert=True)
        return

    if action == "preview_lock":
        await fetch_bot_settings()
        text = str(SETTINGS_CACHE.get("bot_locked_message") or DEFAULT_SETTINGS["bot_locked_message"])
        header = "🔍 <i>Так выглядит сообщение для обычных пользователей, когда тех.режим включён:</i>"
        try:
            await query.message.answer(header, disable_web_page_preview=True)
            await query.message.answer(text, disable_web_page_preview=True)
            await query.answer("Превью заглушки отправлено.")
        except TelegramBadRequest as e:
            await query.answer(f"Ошибка HTML: {e}", show_alert=True)
        return

    if action == "toggle_lock":
        new_val = not bool(SETTINGS_CACHE.get("bot_locked"))
        ok = await save_bot_setting("bot_locked", new_val)
        try:
            await query.message.edit_text(admin_panel_text(), reply_markup=admin_panel_keyboard(), disable_web_page_preview=True)
        except TelegramBadRequest:
            pass
        if ok and new_val:
            # Show admin what users now see — they themselves bypass the lock.
            text = str(SETTINGS_CACHE.get("bot_locked_message") or DEFAULT_SETTINGS["bot_locked_message"])
            try:
                await query.message.answer(
                    "🛑 <b>Тех.режим ВКЛЮЧЁН.</b>\n"
                    "<i>Тебе как админу /start продолжает работать — это так и задумано. Обычные пользователи теперь видят:</i>",
                    disable_web_page_preview=True,
                )
                await query.message.answer(text, disable_web_page_preview=True)
            except TelegramBadRequest:
                pass
        if ok:
            await query.answer("Бот выключен (в разработке)." if new_val else "Бот включён.")
        else:
            await query.answer("Не удалось переключить.", show_alert=True)
        return

    if action == "reset":
        ok = True
        for k, v in DEFAULT_SETTINGS.items():
            if not await save_bot_setting(k, v):
                ok = False
        await fetch_bot_settings()
        try:
            await query.message.edit_text(admin_panel_text(), reply_markup=admin_panel_keyboard(), disable_web_page_preview=True)
        except TelegramBadRequest:
            pass
        await query.answer("Сброшено к дефолту." if ok else "Сброшено частично — проверь логи.")
        return

    if action == "back":
        await fetch_bot_settings()
        try:
            await query.message.edit_text(admin_panel_text(), reply_markup=admin_panel_keyboard(), disable_web_page_preview=True)
        except TelegramBadRequest:
            try:
                await query.message.answer(admin_panel_text(), reply_markup=admin_panel_keyboard(), disable_web_page_preview=True)
            except Exception:  # noqa: BLE001
                pass
        await query.answer()
        return

    if action == "users":
        # adm:users:{offset} or adm:users:noop
        raw = parts[2] if len(parts) > 2 else "0"
        if raw == "noop":
            await query.answer()
            return
        try:
            offset = max(0, int(raw))
        except ValueError:
            offset = 0
        limit = 10
        data_resp = await fetch_users_list(offset=offset, limit=limit)
        items = data_resp.get("items") or []
        total = int(data_resp.get("total") or 0)
        text = users_list_text(items, offset, limit, total)
        kb = users_list_keyboard(items, offset, limit, total)
        try:
            await query.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
        except TelegramBadRequest:
            try:
                await query.message.answer(text, reply_markup=kb, disable_web_page_preview=True)
            except Exception:  # noqa: BLE001
                pass
        await query.answer()
        return

    if action == "u":
        # adm:u:{tg_id}
        try:
            tid = int(parts[2])
        except (ValueError, IndexError):
            await query.answer("Bad id", show_alert=True)
            return
        data_resp = await fetch_user_detail(tid)
        u = data_resp.get("user") or {}
        text = user_card_text(u)
        kb = user_card_keyboard(u) if u else InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="↩ К списку", callback_data="adm:users:0")]])
        try:
            await query.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
        except TelegramBadRequest:
            try:
                await query.message.answer(text, reply_markup=kb, disable_web_page_preview=True)
            except Exception:  # noqa: BLE001
                pass
        await query.answer()
        return

    if action == "ua":
        # adm:ua:{action_name}:{tg_id}
        if len(parts) < 4:
            await query.answer("Bad", show_alert=True)
            return
        act_name = parts[2]
        try:
            tid = int(parts[3])
        except ValueError:
            await query.answer("Bad id", show_alert=True)
            return
        result = await do_user_action(tid, {"action": act_name})
        if not result.get("ok"):
            await query.answer(f"Ошибка: {result.get('error') or 'unknown'}", show_alert=True)
            return
        if act_name == "delete" or result.get("deleted"):
            try:
                await query.message.edit_text("🗑 Пользователь удалён.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="↩ К списку", callback_data="adm:users:0")]]))
            except TelegramBadRequest:
                pass
            await query.answer("Удалено.")
            return
        # Re-render card
        u = result.get("user") or {}
        try:
            await query.message.edit_text(user_card_text(u), reply_markup=user_card_keyboard(u), disable_web_page_preview=True)
        except TelegramBadRequest:
            pass
        await query.answer({"ban": "Забанен.", "unban": "Разбанен.", "revoke": "Подписка отозвана.",
                            "reset_trial": "Триал сброшен.", "regen_sub": "sub_uuid обновлён.",
                            "clear_devices": "Устройства очищены."}.get(act_name, "Готово."))
        return

    if action in ("ug", "ub", "us"):
        # adm:ug:{days}:{tg_id} | adm:ub:{delta}:{tg_id} | adm:us:{delta}:{tg_id}
        if len(parts) < 4:
            await query.answer("Bad", show_alert=True)
            return
        try:
            value = int(parts[2])
            tid = int(parts[3])
        except ValueError:
            await query.answer("Bad number", show_alert=True)
            return
        if action == "ug":
            payload = {"action": "grant_days", "days": value}
            label = f"+{value} дней"
        elif action == "ub":
            payload = {"action": "balance_delta", "delta": value}
            label = f"баланс {value:+d}₽"
        else:
            payload = {"action": "stars_delta", "delta": value}
            label = f"⭐ {value:+d}"
        result = await do_user_action(tid, payload)
        if not result.get("ok"):
            await query.answer(f"Ошибка: {result.get('error') or 'unknown'}", show_alert=True)
            return
        u = result.get("user") or {}
        try:
            await query.message.edit_text(user_card_text(u), reply_markup=user_card_keyboard(u), disable_web_page_preview=True)
        except TelegramBadRequest:
            pass
        await query.answer(f"Готово: {label}")
        return

    if action == "edit":
        key = parts[2] if len(parts) > 2 else ""
        if key not in DEFAULT_SETTINGS:
            await query.answer("Неизвестное поле.", show_alert=True)
            return
        PENDING_EDITS[user_id] = key
        label = ADMIN_FIELD_LABELS.get(key, key)
        current = str(SETTINGS_CACHE.get(key, ""))
        # HTML-rich fields show raw markup; URLs / button labels are plain text.
        is_html_field = key.endswith("_text") or key.endswith("_message")
        prompt = (
            f"<b>{_html.escape(label)}</b>\n"
            f"<blockquote>Текущее значение:\n{current if is_html_field else _html.escape(current)}</blockquote>\n"
            "Пришли новое значение одним сообщением. HTML работает: "
            "<code>&lt;b&gt;</code>, <code>&lt;i&gt;</code>, <code>&lt;u&gt;</code>, <code>&lt;s&gt;</code>, "
            "<code>&lt;code&gt;</code>, <code>&lt;a href=&quot;…&quot;&gt;</code>, <code>&lt;blockquote&gt;</code>.\n\n"
            "Чтобы отменить — пришли <code>/cancel</code>."
        )
        cancel_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✖ Отмена", callback_data="adm:cancel")]])
        try:
            await query.message.answer(prompt, reply_markup=cancel_kb, disable_web_page_preview=True)
        except TelegramBadRequest as e:
            await query.message.answer(f"Не получилось показать текущее: {_html.escape(str(e))}")
        await query.answer()
        return

    if action == "cancel":
        PENDING_EDITS.pop(user_id, None)
        try:
            await query.message.edit_text("Редактирование отменено.")
        except TelegramBadRequest:
            pass
        await query.answer()
        return

    await query.answer()


@dp.message(Command("cancel"))
async def on_cancel(message: Message) -> None:
    user = message.from_user
    user_id = user.id if user else 0
    if user_id not in ADMIN_IDS:
        return
    if PENDING_EDITS.pop(user_id, None):
        await message.answer("Редактирование отменено.")


@dp.message(F.text & ~F.text.startswith("/"))
async def on_admin_input(message: Message) -> None:
    """If admin has a pending edit, treat the next text message as the new value."""
    user = message.from_user
    user_id = user.id if user else 0
    if user_id not in ADMIN_IDS:
        return
    key = PENDING_EDITS.get(user_id)
    if not key:
        return
    raw = message.html_text if message.html_text else (message.text or "")
    if key in {"support_url", "channel_url"}:
        # URL fields: strip HTML, keep plain text only.
        raw = (message.text or "").strip()
        if not (raw.startswith("http://") or raw.startswith("https://") or raw.startswith("tg://")):
            await message.answer("Ссылка должна начинаться с <code>https://</code> или <code>tg://</code>. Попробуй ещё раз или /cancel.")
            return
    PENDING_EDITS.pop(user_id, None)
    ok = await save_bot_setting(key, raw)
    if not ok:
        await message.answer("Не удалось сохранить — попробуй ещё раз через /admin.")
        return
    label = ADMIN_FIELD_LABELS.get(key, key)
    confirm = f"✅ <b>{_html.escape(label)}</b> обновлено.\n\nПревью:"
    await message.answer(confirm, disable_web_page_preview=True)
    # Send a real preview that mirrors what users will see.
    try:
        if key == "bot_start_text":
            await message.answer(raw, reply_markup=main_keyboard(is_admin=True), disable_web_page_preview=True)
        elif key == "bot_info_text":
            await message.answer(raw, reply_markup=info_keyboard(), disable_web_page_preview=True)
        elif key == "bot_locked_message":
            await message.answer(raw, disable_web_page_preview=True)
        else:
            # Re-render /start so the new button label/url is visible.
            await message.answer(SETTINGS_CACHE["bot_start_text"], reply_markup=main_keyboard(is_admin=True), disable_web_page_preview=True)
    except TelegramBadRequest as e:
        await message.answer(f"⚠ Сохранил, но HTML невалидный: <code>{_html.escape(str(e))}</code>\nЗайди в /admin и поправь.")
    # Re-show the panel below for further edits.
    await message.answer(admin_panel_text(), reply_markup=admin_panel_keyboard(), disable_web_page_preview=True)


@dp.pre_checkout_query()
async def on_pre_checkout_query(query: PreCheckoutQuery) -> None:
    try:
        await query.answer(ok=True)
    except Exception:  # noqa: BLE001
        logging.exception("pre_checkout answer failed")


@dp.message(F.successful_payment)
async def on_successful_payment(message: Message) -> None:
    payment = message.successful_payment
    if not payment:
        return
    payload = payment.invoice_payload or ""
    stars = payment.total_amount or 0
    user = message.from_user
    user_id = user.id if user else 0
    logging.info("Stars paid by %s — %s ⭐ payload=%s", user_id, stars, payload)
    if payload.startswith("sub:"):
        try:
            _, _, tariff_key = payload.split(":", 2)
        except ValueError:
            tariff_key = ""
        if tariff_key:
            result = await grant_subscription(user_id, tariff_key, "stars", user)
            if result.get("ok"):
                await message.answer(
                    "Подписка оформлена! ✅\n"
                    f"<blockquote>"
                    f"Тариф: <b>{_html.escape(str(result.get('tariff_name') or tariff_key))}</b>\n"
                    f"Ссылка: <code>{_html.escape(result.get('sub_url') or '—')}</code>"
                    f"</blockquote>",
                    reply_markup=main_keyboard(),
                )
                return
        await message.answer("Платёж получен, но активация не прошла — свяжитесь с поддержкой.")
        return
    credited = None
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.post(
                f"{BACKEND_URL}/api/internal/stars-paid",
                json={"payload": payload, "stars": stars, "tg_id": user_id},
                headers={"X-Internal-Key": INTERNAL_API_KEY},
            ) as response:
                data = await response.json(content_type=None)
                if response.status == 200 and data.get("ok"):
                    credited = data.get("credited_rub")
    except Exception:  # noqa: BLE001
        logging.exception("stars-paid POST failed")
    if credited is None:
        await message.answer(
            "Платёж получен, но баланс не удалось зачислить автоматически. "
            "Свяжитесь с поддержкой — мы поправим вручную."
        )
        return
    await message.answer(
        "Оплата получена! ✅\n"
        f"<blockquote>Зачислено: <b>{credited} ₽</b> ({stars} ⭐)</blockquote>",
        reply_markup=main_keyboard(),
    )


@dp.message(F.web_app_data)
async def on_web_app_data(message: Message) -> None:
    pass


async def run_bot() -> None:
    """Long-running coroutine — spawn from FastAPI startup."""
    me = await bot.get_me()
    logging.info("Bot started: @%s (id=%s) admin_ids=%s", me.username, me.id, sorted(ADMIN_IDS))
    await fetch_bot_settings()
    try:
        await bot.set_my_commands([])
    except Exception:  # noqa: BLE001
        logging.exception("set_my_commands failed")
    try:
        await bot.set_chat_menu_button(menu_button=MenuButtonDefault())
    except Exception:  # noqa: BLE001
        logging.exception("set_chat_menu_button failed")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


async def main() -> None:
    await run_bot()


if __name__ == "__main__":
    asyncio.run(main())
