import asyncio
import html as _html
import logging
import os

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
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

TOKEN = os.environ["BOT_TOKEN"]
WEBAPP_URL = os.environ.get("WEBAPP_URL", "https://jutsovpn-backend-gfyfeciw.fly.dev/")
ADMIN_URL = os.environ.get("ADMIN_URL", "https://jutsovpn-backend-gfyfeciw.fly.dev/jutso")
BACKEND_URL = os.environ.get("BACKEND_URL", "https://jutsovpn-backend-gfyfeciw.fly.dev").rstrip("/")
INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "")
SUPPORT_URL = os.environ.get("SUPPORT_URL", "https://t.me/jutsovpn_support")
CHANNEL_URL = os.environ.get("CHANNEL_URL", "https://t.me/jutsovpn_news")
ADMIN_IDS = {
    int(value)
    for value in os.environ.get("ADMIN_IDS", "8228905313").replace(",", " ").split()
    if value.strip().isdigit()
}

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


def main_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="📱 Открыть приложение", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton(text="ℹ Информация", callback_data="info:open")],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton(text="🛠 Админ-панель", web_app=WebAppInfo(url=ADMIN_URL))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def info_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="💬 Поддержка", url=SUPPORT_URL)],
        [InlineKeyboardButton(text="📢 Новостной канал", url=CHANNEL_URL)],
        [InlineKeyboardButton(text="◀ Назад", callback_data="info:close")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def info_text() -> str:
    return (
        "<b>Информация</b>\n"
        "<blockquote>"
        "JutsoVPN — быстрый и приватный VPN с подпиской через Telegram.\n\n"
        f"• Поддержка: {_html.escape(SUPPORT_URL)}\n"
        f"• Канал: {_html.escape(CHANNEL_URL)}"
        "</blockquote>"
    )


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


def render_profile_text(profile: dict, user) -> str:
    name = (profile.get("first_name") or (getattr(user, "first_name", "") or "") or "Профиль").strip()
    username = profile.get("username") or (getattr(user, "username", "") or "")
    tg_id = profile.get("tg_id") or (getattr(user, "id", 0) or 0)
    balance = int(profile.get("balance_rub") or 0)
    stars = int(profile.get("stars_balance") or 0)
    days_left = int(profile.get("days_left") or 0)
    expires_human = profile.get("expires_human") or ""
    has_sub = bool(profile.get("has_subscription"))
    free_used = bool(profile.get("free_used"))
    tariff_name = profile.get("tariff_name") or ""
    ref_code = profile.get("ref_code") or ""
    ref_count = int(profile.get("ref_count") or 0)
    devices = int(profile.get("devices") or 0)

    if has_sub:
        sub_line = f"Активна — {_html.escape(tariff_name)} (до {_html.escape(expires_human)})"
    elif free_used:
        sub_line = "Нет активной подписки"
    else:
        sub_line = "Нет подписки · доступен пробный период"

    handle = f"@{_html.escape(username)}" if username else "—"

    lines = [
        "<b>Ваш профиль:</b>",
        "<blockquote>",
        f"👤 <b>{_html.escape(name)}</b>  ·  {handle}",
        f"🆔 ID: <code>{tg_id}</code>",
        f"💳 Подписка: {sub_line}",
        f"📅 Дней осталось: <b>{days_left}</b>",
        f"💰 Баланс: <b>{balance} ₽</b>  ·  ⭐ {stars}",
        f"📱 Устройств: <b>{devices}</b>",
        f"👥 Рефералов: <b>{ref_count}</b>" + (f"  ·  код <code>{_html.escape(ref_code)}</code>" if ref_code else ""),
        "</blockquote>",
    ]
    return "\n".join(lines)


async def grant_subscription(tg_id: int, tariff_key: str, payment: str, user_obj=None) -> dict:
    """Grant a paid subscription via the bot. Best-effort, returns {ok:bool}."""
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
    maintenance = await fetch_maintenance()
    if maintenance.get("bot_locked") and not is_admin:
        reason = maintenance.get("bot_locked_message") or "Сейчас идёт технический перерыв. Попробуйте чуть позже."
        await message.answer(f"<blockquote>{reason}</blockquote>")
        return
    profile = await fetch_user_profile(user_id, user)
    text = render_profile_text(profile, user) if profile.get("ok") else "<b>Ваш профиль:</b>\n<blockquote>Профиль будет создан при первом входе в приложение.</blockquote>"
    await message.answer(text, reply_markup=main_keyboard(is_admin=is_admin), disable_web_page_preview=True)


@dp.callback_query(F.data == "info:open")
async def on_info_open(query: CallbackQuery) -> None:
    if not query.message:
        await query.answer()
        return
    try:
        try:
            await query.message.edit_text(info_text(), reply_markup=info_keyboard(), disable_web_page_preview=True)
        except TelegramBadRequest:
            try:
                await query.message.answer(info_text(), reply_markup=info_keyboard(), disable_web_page_preview=True)
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
    try:
        profile = await fetch_user_profile(user_id, user_obj)
        text = render_profile_text(profile, user_obj) if profile.get("ok") else "<b>Ваш профиль:</b>\n<blockquote>Профиль будет создан при первом входе в приложение.</blockquote>"
        try:
            await query.message.edit_text(text, reply_markup=main_keyboard(is_admin=is_admin), disable_web_page_preview=True)
        except TelegramBadRequest:
            pass
        await query.answer()
    except Exception:  # noqa: BLE001
        logging.exception("info_close failed")
        try:
            await query.answer()
        except Exception:  # noqa: BLE001
            pass


@dp.pre_checkout_query()
async def on_pre_checkout_query(query: PreCheckoutQuery) -> None:
    """Always approve Stars pre-checkout (we already validated server-side)."""
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
    # Web App may send arbitrary payloads via Telegram.WebApp.sendData(). We
    # silently acknowledge — handled by the Mini App itself.
    pass


async def main() -> None:
    me = await bot.get_me()
    logging.info("Bot started: @%s (id=%s) admin_ids=%s", me.username, me.id, sorted(ADMIN_IDS))
    # No persistent commands menu — only /start exists, so an empty list keeps
    # the chat clean.
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


if __name__ == "__main__":
    asyncio.run(main())
