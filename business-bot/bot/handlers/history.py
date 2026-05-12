import html as _html
import time

from aiogram import Router, F
from aiogram.types import CallbackQuery

from bot.database import Database
from bot.emoji import Emoji, tg_emoji
from bot.keyboards import history_chat_kb, history_kb, main_menu_kb

router = Router()


@router.callback_query(F.data == "menu:history")
async def show_history(callback: CallbackQuery, db: Database) -> None:
    user_id = callback.from_user.id
    chats = await db.get_recent_chats(user_id)

    if not chats:
        await callback.message.edit_text(
            f"<b>{tg_emoji(Emoji.STATS, '📊')} История</b>\n\n"
            f"{tg_emoji(Emoji.INFO, 'ℹ')} Пока нет сообщений. "
            f"История появится после того, как бот начнёт "
            f"читать ваши чаты.",
            parse_mode="HTML",
            reply_markup=main_menu_kb(),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        f"<b>{tg_emoji(Emoji.STATS, '📊')} История</b>\n\n"
        f"{tg_emoji(Emoji.INFO, 'ℹ')} Выберите чат для просмотра:",
        parse_mode="HTML",
        reply_markup=history_kb(chats),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("history:chat:"))
async def show_chat_history(callback: CallbackQuery, db: Database) -> None:
    chat_id = int(callback.data.split(":")[-1])
    user_id = callback.from_user.id
    messages = await db.get_history(user_id, chat_id, limit=20)

    if not messages:
        text = (
            f"<b>{tg_emoji(Emoji.FILE, '📁')} Чат {chat_id}</b>\n\n"
            f"{tg_emoji(Emoji.INFO, 'ℹ')} Нет сообщений."
        )
    else:
        lines = [f"<b>{tg_emoji(Emoji.FILE, '📁')} Чат {chat_id}</b>\n"]
        for msg in messages[-15:]:
            role_icon = "👤" if msg["role"] == "user" else "🤖"
            content = _html.escape(str(msg["content"])[:200])
            ts = msg.get("ts", 0)
            time_str = _format_time(ts) if ts else ""
            lines.append(f"<b>{role_icon}</b> {content}")
            if time_str:
                lines[-1] += f"  <i>({time_str})</i>"
        text = "\n".join(lines)

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=history_chat_kb(chat_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("history:clear:"))
async def clear_chat_history(callback: CallbackQuery, db: Database) -> None:
    chat_id = int(callback.data.split(":")[-1])
    count = await db.clear_history(callback.from_user.id, chat_id)
    await callback.message.edit_text(
        f"{tg_emoji(Emoji.TRASH, '🗑')} Удалено {count} сообщений из чата {chat_id}.",
        parse_mode="HTML",
        reply_markup=main_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "history:clear_all")
async def clear_all_history(callback: CallbackQuery, db: Database) -> None:
    count = await db.clear_history(callback.from_user.id)
    await callback.message.edit_text(
        f"{tg_emoji(Emoji.TRASH, '🗑')} Удалено {count} сообщений из всех чатов.",
        parse_mode="HTML",
        reply_markup=main_menu_kb(),
    )
    await callback.answer()


def _format_time(ts: float) -> str:
    elapsed = time.time() - ts
    if elapsed < 60:
        return "только что"
    if elapsed < 3600:
        m = int(elapsed // 60)
        return f"{m} мин. назад"
    if elapsed < 86400:
        h = int(elapsed // 3600)
        return f"{h} ч. назад"
    d = int(elapsed // 86400)
    return f"{d} дн. назад"
