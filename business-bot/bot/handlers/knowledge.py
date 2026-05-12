"""Handler for 'Что узнал' (What I learned) feature."""

from aiogram import Router, F
from aiogram.types import CallbackQuery

from bot.config import DEFAULT_API_URL, DEFAULT_MODEL
from bot.database import Database
from bot.emoji import Emoji, tg_emoji
from bot.keyboards import back_to_menu_kb, knowledge_kb
from bot.services.ai_service import analyze_chat_knowledge, analyze_speech_style

router = Router()


@router.callback_query(F.data == "menu:knowledge")
async def show_knowledge(callback: CallbackQuery, db: Database) -> None:
    user_id = callback.from_user.id
    stats = await db.get_all_content_stats(user_id)
    total = stats.get("total", 0)
    by_type = stats.get("by_type", {})
    chats_count = stats.get("chats", 0)

    type_labels = {
        "text": "текст", "photo": "фото", "video": "видео",
        "gif": "GIF", "sticker": "стикер", "voice": "голос",
        "video_note": "кружок", "document": "файл",
    }

    stats_lines = []
    for t, label in type_labels.items():
        cnt = by_type.get(t, 0)
        if cnt:
            stats_lines.append(f"  {label}: <b>{cnt}</b>")

    stats_text = "\n".join(stats_lines) if stats_lines else "  Пока ничего"

    await callback.message.edit_text(
        f"<b>{tg_emoji(Emoji.GROWTH, '📊')} Что узнал бот</b>\n\n"
        f"{tg_emoji(Emoji.STATS_CHART, '📊')} Всего записей: <b>{total}</b>\n"
        f"{tg_emoji(Emoji.EYE, '👁')} Чатов: <b>{chats_count}</b>\n\n"
        f"{tg_emoji(Emoji.FILE, '📁')} По типам:\n{stats_text}",
        parse_mode="HTML",
        reply_markup=knowledge_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "knowledge:stats")
async def knowledge_stats(callback: CallbackQuery, db: Database) -> None:
    user_id = callback.from_user.id
    chats = await db.get_monitored_chats(user_id)

    if not chats:
        await callback.message.edit_text(
            f"{tg_emoji(Emoji.INFO, 'ℹ')} Нет отслеживаемых чатов.\n\n"
            f"Бот начнёт учиться, когда будут приходить сообщения в бизнес-чаты.",
            parse_mode="HTML",
            reply_markup=back_to_menu_kb(),
        )
        await callback.answer()
        return

    lines = []
    for chat in chats:
        chat_id = chat["chat_id"]
        name = chat.get("chat_name") or str(chat_id)
        stats = await db.get_chat_content_stats(user_id, chat_id)
        total = stats.get("total", 0)
        texts = stats.get("text", 0)
        photos = stats.get("photo", 0)
        lines.append(
            f"<b>{name}</b>: {total} записей "
            f"({texts} текст, {photos} фото)"
        )

    await callback.message.edit_text(
        f"<b>{tg_emoji(Emoji.STATS_CHART, '📊')} Статистика по чатам</b>\n\n"
        + "\n".join(lines),
        parse_mode="HTML",
        reply_markup=knowledge_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "knowledge:analyze_all")
async def knowledge_analyze(callback: CallbackQuery, db: Database) -> None:
    user_id = callback.from_user.id
    user = await db.get_user(user_id)
    api_key = (user["api_key"] if user else "") or ""
    if not api_key:
        await callback.answer("Установите API ключ для анализа", show_alert=True)
        return

    await callback.answer("Анализирую чаты... Подождите", show_alert=False)

    model = user["model"] or DEFAULT_MODEL
    api_url = user["api_url"] or DEFAULT_API_URL

    texts = await db.get_recent_texts_for_learning(user_id, limit=200)
    if not texts:
        await callback.message.edit_text(
            f"{tg_emoji(Emoji.INFO, 'ℹ')} Пока нет данных для анализа.\n\n"
            f"Бот начнёт учиться, когда будут приходить сообщения.",
            parse_mode="HTML",
            reply_markup=knowledge_kb(),
        )
        return

    analysis = await analyze_chat_knowledge(api_key, api_url, model, texts)

    # Truncate if too long for Telegram
    if len(analysis) > 3500:
        analysis = analysis[:3500] + "..."

    await callback.message.edit_text(
        f"<b>{tg_emoji(Emoji.BOT, '🤖')} Анализ чатов</b>\n\n{analysis}",
        parse_mode="HTML",
        reply_markup=knowledge_kb(),
    )


@router.callback_query(F.data == "knowledge:style")
async def knowledge_style(callback: CallbackQuery, db: Database) -> None:
    user_id = callback.from_user.id
    user = await db.get_user(user_id)
    api_key = (user["api_key"] if user else "") or ""
    if not api_key:
        await callback.answer("Установите API ключ для анализа стиля", show_alert=True)
        return

    await callback.answer("Анализирую стиль общения...", show_alert=False)

    model = user["model"] or DEFAULT_MODEL
    api_url = user["api_url"] or DEFAULT_API_URL

    texts = await db.get_recent_texts_for_learning(user_id, limit=300)
    if not texts:
        await callback.message.edit_text(
            f"{tg_emoji(Emoji.INFO, 'ℹ')} Пока нет данных для анализа стиля.\n\n"
            f"Нужно больше сообщений в чатах.",
            parse_mode="HTML",
            reply_markup=knowledge_kb(),
        )
        return

    style = await analyze_speech_style(api_key, api_url, model, texts)

    if len(style) > 3500:
        style = style[:3500] + "..."

    await callback.message.edit_text(
        f"<b>{tg_emoji(Emoji.WRITE, '✍')} Стиль общения</b>\n\n{style}",
        parse_mode="HTML",
        reply_markup=knowledge_kb(),
    )


@router.callback_query(F.data.startswith("chats:learned:"))
async def chat_learned(callback: CallbackQuery, db: Database) -> None:
    chat_id = int(callback.data.split(":")[-1])
    user_id = callback.from_user.id
    user = await db.get_user(user_id)
    api_key = (user["api_key"] if user else "") or ""
    if not api_key:
        await callback.answer("Установите API ключ", show_alert=True)
        return

    await callback.answer("Анализирую чат...", show_alert=False)

    model = user["model"] or DEFAULT_MODEL
    api_url = user["api_url"] or DEFAULT_API_URL

    texts = await db.get_recent_texts_for_learning(user_id, chat_id, limit=100)
    if not texts:
        await callback.message.edit_text(
            f"{tg_emoji(Emoji.INFO, 'ℹ')} Нет данных по этому чату.",
            parse_mode="HTML",
            reply_markup=back_to_menu_kb(),
        )
        return

    analysis = await analyze_chat_knowledge(api_key, api_url, model, texts)
    if len(analysis) > 3500:
        analysis = analysis[:3500] + "..."

    await callback.message.edit_text(
        f"<b>{tg_emoji(Emoji.GROWTH, '📊')} Что узнал из чата</b>\n\n{analysis}",
        parse_mode="HTML",
        reply_markup=back_to_menu_kb(),
    )


@router.callback_query(F.data.startswith("chats:stats:"))
async def chat_stats(callback: CallbackQuery, db: Database) -> None:
    chat_id = int(callback.data.split(":")[-1])
    user_id = callback.from_user.id

    stats = await db.get_chat_content_stats(user_id, chat_id)
    total = stats.get("total", 0)

    type_labels = {
        "text": "Текст", "photo": "Фото", "video": "Видео",
        "gif": "GIF", "sticker": "Стикеры", "voice": "Голос",
        "video_note": "Кружки", "document": "Файлы",
    }

    lines = []
    for t, label in type_labels.items():
        cnt = stats.get(t, 0)
        if cnt:
            lines.append(f"  {label}: <b>{cnt}</b>")

    stats_text = "\n".join(lines) if lines else "  Пока ничего"

    await callback.message.edit_text(
        f"<b>{tg_emoji(Emoji.STATS_CHART, '📊')} Статистика чата</b>\n\n"
        f"Всего записей: <b>{total}</b>\n\n"
        f"{stats_text}",
        parse_mode="HTML",
        reply_markup=back_to_menu_kb(),
    )
    await callback.answer()
