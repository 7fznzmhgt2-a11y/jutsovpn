"""Handle incoming business messages — read, store ALL content, and auto-reply via AI."""

import logging

from aiogram import Bot, Router
from aiogram.types import Message, ReactionTypeEmoji

from bot.config import CONTEXT_MESSAGES, DEFAULT_API_URL, DEFAULT_MODEL, DEFAULT_PROMPT
from bot.database import Database
from bot.services.ai_service import get_ai_response

logger = logging.getLogger(__name__)

router = Router()

PREMIUM_REACTIONS = ["👍", "❤", "🔥", "🎉", "👏", "😎", "🤝", "💯", "⚡", "🏆"]


@router.business_message()
async def on_business_message(message: Message, db: Database, bot: Bot) -> None:
    """Process every business-chat message — store everything."""
    biz_id = message.business_connection_id
    if not biz_id:
        logger.info("No business_connection_id, skipping")
        return

    owner_id = await _resolve_owner(db, biz_id)
    if owner_id is None:
        logger.warning("Could not resolve owner for biz_id=%s", biz_id)
        return

    logger.info(
        "Business msg: chat=%s from=%s text=%s",
        message.chat.id,
        message.from_user.first_name if message.from_user else "?",
        (message.text or message.caption or "<media>")[:50],
    )

    chat_id = message.chat.id
    is_owner_message = message.from_user and message.from_user.id == owner_id

    # Build sender info
    sender_id = message.from_user.id if message.from_user else 0
    sender_name = ""
    if message.from_user:
        sender_name = message.from_user.first_name or ""
        if message.from_user.last_name:
            sender_name += " " + message.from_user.last_name

    # Auto-register the chat
    chat_name = ""
    if message.chat.first_name:
        chat_name = message.chat.first_name
        if message.chat.last_name:
            chat_name += " " + message.chat.last_name
    elif message.chat.title:
        chat_name = message.chat.title
    await db.add_monitored_chat(owner_id, chat_id, chat_name)

    # ── Store ALL content types ────────────────────────────────────
    text = message.text or ""
    caption = message.caption or ""

    if message.text:
        await db.save_content(
            owner_id, chat_id, sender_id, sender_name,
            content_type="text", text_content=text,
        )

    if message.photo:
        photo = message.photo[-1]  # highest resolution
        await db.save_content(
            owner_id, chat_id, sender_id, sender_name,
            content_type="photo", file_id=photo.file_id, caption=caption,
        )

    if message.video:
        await db.save_content(
            owner_id, chat_id, sender_id, sender_name,
            content_type="video", file_id=message.video.file_id, caption=caption,
        )

    if message.animation:
        await db.save_content(
            owner_id, chat_id, sender_id, sender_name,
            content_type="gif", file_id=message.animation.file_id, caption=caption,
        )

    if message.sticker:
        await db.save_content(
            owner_id, chat_id, sender_id, sender_name,
            content_type="sticker", file_id=message.sticker.file_id,
            emoji=message.sticker.emoji or "",
        )

    if message.voice:
        await db.save_content(
            owner_id, chat_id, sender_id, sender_name,
            content_type="voice", file_id=message.voice.file_id,
        )

    if message.video_note:
        await db.save_content(
            owner_id, chat_id, sender_id, sender_name,
            content_type="video_note", file_id=message.video_note.file_id,
        )

    if message.document and not message.animation:
        await db.save_content(
            owner_id, chat_id, sender_id, sender_name,
            content_type="document", file_id=message.document.file_id,
            caption=caption,
        )

    # Save text to message history for AI context
    content_for_history = text or caption
    if content_for_history:
        role = "assistant" if is_owner_message else "user"
        await db.save_message(owner_id, chat_id, role, content_for_history)
        logger.info("Saved to DB: chat=%s role=%s text=%s", chat_id, role, content_for_history[:50])

    # ── Auto-reply logic ───────────────────────────────────────────
    if is_owner_message:
        return

    user = await db.get_user(owner_id)
    if not user or not user["auto_reply"]:
        return

    monitored = await db.get_monitored_chats(owner_id)
    chat_entry = next((c for c in monitored if c["chat_id"] == chat_id), None)
    if chat_entry and not chat_entry["auto_reply"]:
        return

    api_key = user["api_key"] or ""
    if not api_key:
        return

    if not content_for_history:
        return

    prompt = user["prompt"] or DEFAULT_PROMPT
    model = user["model"] or DEFAULT_MODEL
    api_url = user["api_url"] or DEFAULT_API_URL

    # Get owner's real name from Telegram profile
    try:
        owner_chat = await bot.get_chat(owner_id)
        owner_name = owner_chat.first_name or ""
        if owner_chat.last_name:
            owner_name += " " + owner_chat.last_name
    except Exception:
        owner_name = ""

    # Inject owner name into prompt
    if owner_name:
        prompt = f"Тебя зовут {owner_name}. " + prompt

    # Build context from history
    history = await db.get_history(owner_id, chat_id, limit=CONTEXT_MESSAGES)
    context_messages = [{"role": m["role"], "content": m["content"]} for m in history]

    # Build learned style from recent chat messages
    learned_texts = await db.get_recent_texts_for_learning(owner_id, chat_id, limit=50)
    learned_style = ""
    if learned_texts:
        learned_style = "\n".join(
            f"{t['sender_name']}: {t['text_content']}" for t in learned_texts[-30:]
        )

    reply_text = await get_ai_response(
        api_key=api_key,
        api_url=api_url,
        model=model,
        system_prompt=prompt,
        messages=context_messages,
        learned_style=learned_style,
    )

    if not reply_text:
        logger.warning("AI returned empty response for chat %s", chat_id)
        return

    try:
        await bot.send_message(
            chat_id=chat_id,
            text=reply_text,
            business_connection_id=biz_id,
        )
        await db.save_message(owner_id, chat_id, "assistant", reply_text)
    except Exception:
        logger.exception("Failed to send business reply to chat %s", chat_id)


@router.message()
async def on_group_message(message: Message, db: Database, bot: Bot) -> None:
    """Read messages from groups/chats where bot is a member — store everything."""
    # Skip private chats (handled by business_message or /start)
    if message.chat.type == "private":
        return
    # Skip if it's a command
    if message.text and message.text.startswith("/"):
        return

    chat_id = message.chat.id

    # Find which user monitors this chat
    cur = await db.db.execute(
        "SELECT user_id FROM monitored_chats WHERE chat_id = ?", (chat_id,)
    )
    row = await cur.fetchone()
    if not row:
        return

    owner_id = row["user_id"]

    sender_id = message.from_user.id if message.from_user else 0
    sender_name = ""
    if message.from_user:
        sender_name = message.from_user.first_name or ""
        if message.from_user.last_name:
            sender_name += " " + message.from_user.last_name

    logger.info(
        "Group msg: chat=%s from=%s text=%s",
        chat_id, sender_name,
        (message.text or message.caption or "<media>")[:50],
    )

    text = message.text or ""
    caption = message.caption or ""

    if message.text:
        await db.save_content(
            owner_id, chat_id, sender_id, sender_name,
            content_type="text", text_content=text,
        )
    if message.photo:
        photo = message.photo[-1]
        await db.save_content(
            owner_id, chat_id, sender_id, sender_name,
            content_type="photo", file_id=photo.file_id, caption=caption,
        )
    if message.video:
        await db.save_content(
            owner_id, chat_id, sender_id, sender_name,
            content_type="video", file_id=message.video.file_id, caption=caption,
        )
    if message.animation:
        await db.save_content(
            owner_id, chat_id, sender_id, sender_name,
            content_type="gif", file_id=message.animation.file_id, caption=caption,
        )
    if message.sticker:
        await db.save_content(
            owner_id, chat_id, sender_id, sender_name,
            content_type="sticker", file_id=message.sticker.file_id,
            emoji=message.sticker.emoji or "",
        )
    if message.voice:
        await db.save_content(
            owner_id, chat_id, sender_id, sender_name,
            content_type="voice", file_id=message.voice.file_id,
        )
    if message.video_note:
        await db.save_content(
            owner_id, chat_id, sender_id, sender_name,
            content_type="video_note", file_id=message.video_note.file_id,
        )
    if message.document and not message.animation:
        await db.save_content(
            owner_id, chat_id, sender_id, sender_name,
            content_type="document", file_id=message.document.file_id,
            caption=caption,
        )

    content_for_history = text or caption
    if content_for_history:
        await db.save_message(owner_id, chat_id, "user", content_for_history)
        logger.info("Group saved: chat=%s from=%s text=%s", chat_id, sender_name, content_for_history[:50])


async def _resolve_owner(db: Database, business_id: str) -> int | None:
    """Find the user_id who owns this business connection."""
    cur = await db.db.execute(
        "SELECT user_id FROM users WHERE business_id = ? AND is_connected = 1",
        (business_id,),
    )
    row = await cur.fetchone()
    return row["user_id"] if row else None
