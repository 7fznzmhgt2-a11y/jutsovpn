"""Handle incoming business messages — read, store, and auto-reply via AI."""

import logging

from aiogram import Bot, Router, F
from aiogram.types import Message

from bot.config import CONTEXT_MESSAGES, DEFAULT_API_URL, DEFAULT_MODEL, DEFAULT_PROMPT
from bot.database import Database
from bot.emoji import Emoji, tg_emoji
from bot.services.ai_service import get_ai_response

logger = logging.getLogger(__name__)

router = Router()


@router.business_message()
async def on_business_message(message: Message, db: Database, bot: Bot) -> None:
    """Process every business-chat message."""
    biz_id = message.business_connection_id
    if not biz_id:
        return

    # Resolve the owner (the user who connected the business bot)
    owner_id = await _resolve_owner(db, biz_id)
    if owner_id is None:
        return

    chat_id = message.chat.id
    text = message.text or message.caption or ""
    if not text:
        return

    # Determine if this message is from the owner or from a customer
    is_owner_message = message.from_user and message.from_user.id == owner_id

    # Auto-register the chat for monitoring
    chat_name = ""
    if message.chat.first_name:
        chat_name = message.chat.first_name
        if message.chat.last_name:
            chat_name += " " + message.chat.last_name
    elif message.chat.title:
        chat_name = message.chat.title

    await db.add_monitored_chat(owner_id, chat_id, chat_name)

    # Store the message
    role = "assistant" if is_owner_message else "user"
    await db.save_message(owner_id, chat_id, role, text)

    # Only auto-reply to customer messages (not owner's own messages)
    if is_owner_message:
        return

    # Check if auto-reply is enabled globally
    user = await db.get_user(owner_id)
    if not user or not user["auto_reply"]:
        return

    # Check if auto-reply is enabled for this specific chat
    monitored = await db.get_monitored_chats(owner_id)
    chat_entry = next((c for c in monitored if c["chat_id"] == chat_id), None)
    if chat_entry and not chat_entry["auto_reply"]:
        return

    # Check if API key is set
    api_key = user["api_key"] or ""
    if not api_key:
        return

    # Build context from history
    prompt = user["prompt"] or DEFAULT_PROMPT
    model = user["model"] or DEFAULT_MODEL
    api_url = user["api_url"] or DEFAULT_API_URL

    history = await db.get_history(owner_id, chat_id, limit=CONTEXT_MESSAGES)
    context_messages = [{"role": m["role"], "content": m["content"]} for m in history]

    # Get AI response
    reply_text = await get_ai_response(
        api_key=api_key,
        api_url=api_url,
        model=model,
        system_prompt=prompt,
        messages=context_messages,
    )

    if not reply_text:
        logger.warning("AI returned empty response for chat %s", chat_id)
        return

    # Send the reply in the business chat
    try:
        sent = await bot.send_message(
            chat_id=chat_id,
            text=reply_text,
            business_connection_id=biz_id,
        )
        # Store the bot's reply
        await db.save_message(owner_id, chat_id, "assistant", reply_text)
    except Exception:
        logger.exception("Failed to send business reply to chat %s", chat_id)


async def _resolve_owner(db: Database, business_id: str) -> int | None:
    """Find the user_id who owns this business connection."""
    cur = await db.db.execute(
        "SELECT user_id FROM users WHERE business_id = ? AND is_connected = 1",
        (business_id,),
    )
    row = await cur.fetchone()
    return row["user_id"] if row else None
