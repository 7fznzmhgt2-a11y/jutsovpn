"""Handle incoming business messages — read, store ALL content, and auto-reply via AI."""

import logging
import os

from aiogram import Bot, Router
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReactionTypeEmoji,
)

from bot.config import CONTEXT_MESSAGES, DEFAULT_API_URL, DEFAULT_MODEL, DEFAULT_PROMPT
from bot.database import Database
from bot.emoji import Emoji, tg_emoji
from bot.services.ai_service import get_ai_response
from bot.services.soundcloud import download_soundcloud, search_soundcloud

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

    # ── Owner commands (.sc, etc) ───────────────────────────────────
    if is_owner_message and text:
        handled = await _handle_owner_commands(message, bot, biz_id, chat_id, text, owner_id)
        if handled:
            return
        return  # Don't auto-reply to own messages

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


# In-memory state for multi-step commands per chat
# Key: (owner_id, chat_id) -> {"step": str, "data": dict}
_cmd_state: dict[tuple[int, int], dict] = {}


async def _delete_business_msg(bot: Bot, biz_id: str, chat_id: int, msg_id: int) -> None:
    """Try to delete a message in a business chat."""
    try:
        await bot.delete_business_messages(
            business_connection_id=biz_id,
            message_ids=[msg_id],
        )
    except Exception:
        logger.debug("Could not delete msg %s in chat %s", msg_id, chat_id)


async def _handle_owner_commands(
    message: Message, bot: Bot, biz_id: str, chat_id: int, text: str, owner_id: int
) -> bool:
    """Handle owner dot-commands like .sc — returns True if handled."""
    lower = text.strip().lower()
    key = (owner_id, chat_id)

    # Check if we're in a multi-step flow
    state = _cmd_state.get(key)
    logger.info("CMD check: key=%s text=%s state=%s", key, text[:30], state)

    # .sc — start SoundCloud flow
    if lower == ".sc" or lower == ". sc":
        await _delete_business_msg(bot, biz_id, chat_id, message.message_id)
        try:
            prompt_msg = await bot.send_message(
                chat_id=chat_id,
                text=(
                    f'<b>{tg_emoji(Emoji.DOWNLOAD, "⬇")} SoundCloud</b>\n\n'
                    f'{tg_emoji(Emoji.WRITE, "✍")} какую песню ищем'
                ),
                parse_mode="HTML",
                business_connection_id=biz_id,
            )
            prompt_msg_id = prompt_msg.message_id
        except Exception:
            prompt_msg_id = None
        _cmd_state[key] = {"step": "sc_waiting_query", "data": {"biz_id": biz_id, "prompt_msg_id": prompt_msg_id}}
        return True

    # Waiting for song name
    if state and state["step"] == "sc_waiting_query":
        query = text.strip()
        biz = state["data"].get("biz_id", biz_id)
        await _delete_business_msg(bot, biz, chat_id, message.message_id)

        # Delete the "какую песню ищем" prompt
        prompt_msg_id = state["data"].get("prompt_msg_id")
        if prompt_msg_id:
            await _delete_business_msg(bot, biz, chat_id, prompt_msg_id)

        # Send searching status
        try:
            status_msg = await bot.send_message(
                chat_id=chat_id,
                text=(
                    f'{tg_emoji(Emoji.LOADING, "🔄")} ищу <b>{query}</b>...'
                ),
                parse_mode="HTML",
                business_connection_id=biz,
            )
        except Exception:
            _cmd_state.pop(key, None)
            return True

        results = await search_soundcloud(query, limit=8)
        if not results:
            try:
                await bot.edit_message_text(
                    text=(
                        f'{tg_emoji(Emoji.CROSS, "❌")} ничего не нашел по <b>{query}</b>'
                    ),
                    parse_mode="HTML",
                    chat_id=chat_id,
                    message_id=status_msg.message_id,
                    business_connection_id=biz,
                )
            except Exception:
                pass
            _cmd_state.pop(key, None)
            return True

        # Build list text with premium emoji
        lines = [f'<b>{tg_emoji(Emoji.DOWNLOAD, "⬇")} Результаты по {query}:</b>\n']
        for i, track in enumerate(results, 1):
            dur = ""
            if track.get("duration"):
                m, s = divmod(int(track["duration"]), 60)
                dur = f" [{m}:{s:02d}]"
            uploader = f" — {track['uploader']}" if track.get("uploader") else ""
            lines.append(f"{i}. {track['title']}{uploader}{dur}")

        list_text = "\n".join(lines)

        # Build inline keyboard with buttons for each track
        buttons = []
        for i, track in enumerate(results):
            title_short = track["title"][:30]
            buttons.append([InlineKeyboardButton(
                text=f"{i + 1}. {title_short}",
                callback_data=f"sc:pick:{key[0]}:{key[1]}:{i}",
                icon_custom_emoji_id=Emoji.DOWNLOAD,
            )])
        buttons.append([InlineKeyboardButton(
            text="отмена",
            callback_data=f"sc:cancel:{key[0]}:{key[1]}",
            icon_custom_emoji_id=Emoji.CROSS,
        )])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)

        try:
            await bot.edit_message_text(
                text=list_text,
                parse_mode="HTML",
                chat_id=chat_id,
                message_id=status_msg.message_id,
                reply_markup=kb,
                business_connection_id=biz,
            )
        except Exception:
            pass

        # Save results in state for callback handler
        _cmd_state[key] = {
            "step": "sc_waiting_pick",
            "data": {
                "results": results,
                "status_msg_id": status_msg.message_id,
                "biz_id": biz,
            },
        }
        return True

    # Text-based number pick fallback (if inline buttons don't work)
    if state and state["step"] == "sc_waiting_pick":
        biz = state["data"].get("biz_id", biz_id)
        await _delete_business_msg(bot, biz, chat_id, message.message_id)

        results = state["data"]["results"]
        status_msg_id = state["data"].get("status_msg_id")

        try:
            pick = int(text.strip())
        except ValueError:
            return True

        if pick < 1 or pick > len(results):
            return True

        track = results[pick - 1]
        _cmd_state.pop(key, None)

        await _sc_download_and_send(bot, biz, chat_id, track, status_msg_id)
        return True

    return False


async def _sc_download_and_send(
    bot: Bot, biz_id: str, chat_id: int, track: dict, list_msg_id: int | None = None
) -> None:
    """Download a SoundCloud track and send it to the chat."""
    # Delete the list message
    if list_msg_id:
        await _delete_business_msg(bot, biz_id, chat_id, list_msg_id)

    # Send downloading status
    try:
        dl_msg = await bot.send_message(
            chat_id=chat_id,
            text=(
                f'{tg_emoji(Emoji.LOADING, "🔄")} скачиваю '
                f'<b>{track["title"]}</b>...'
            ),
            parse_mode="HTML",
            business_connection_id=biz_id,
        )
    except Exception:
        return

    file_path = await download_soundcloud(track["url"])
    if not file_path:
        try:
            await bot.edit_message_text(
                text=f'{tg_emoji(Emoji.CROSS, "❌")} не получилось скачать',
                parse_mode="HTML",
                chat_id=chat_id,
                message_id=dl_msg.message_id,
                business_connection_id=biz_id,
            )
        except Exception:
            pass
        return

    await _delete_business_msg(bot, biz_id, chat_id, dl_msg.message_id)

    try:
        audio_file = FSInputFile(file_path, filename=os.path.basename(file_path))
        await bot.send_audio(
            chat_id=chat_id,
            audio=audio_file,
            title=track["title"],
            performer=track.get("uploader", ""),
            business_connection_id=biz_id,
        )
    except Exception:
        logger.exception("Failed to send audio")
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=f'{tg_emoji(Emoji.CROSS, "❌")} не смог отправить',
                parse_mode="HTML",
                business_connection_id=biz_id,
            )
        except Exception:
            pass
    finally:
        try:
            if file_path:
                os.unlink(file_path)
                os.rmdir(os.path.dirname(file_path))
        except Exception:
            pass


# Callback handler for SoundCloud inline buttons
@router.callback_query(lambda c: c.data and c.data.startswith("sc:"))
async def on_sc_callback(callback: CallbackQuery, bot: Bot) -> None:
    """Handle SoundCloud pick/cancel inline button presses."""
    data = callback.data
    parts = data.split(":")

    if parts[1] == "cancel":
        owner_id = int(parts[2])
        chat_id = int(parts[3])
        key = (owner_id, chat_id)
        state = _cmd_state.pop(key, None)
        if state and state["data"].get("status_msg_id"):
            biz = state["data"].get("biz_id", "")
            await _delete_business_msg(bot, biz, chat_id, state["data"]["status_msg_id"])
        await callback.answer("отменено")
        return

    if parts[1] == "pick":
        owner_id = int(parts[2])
        chat_id = int(parts[3])
        pick_idx = int(parts[4])
        key = (owner_id, chat_id)
        state = _cmd_state.pop(key, None)
        if not state:
            await callback.answer("истекло")
            return

        results = state["data"].get("results", [])
        if pick_idx < 0 or pick_idx >= len(results):
            await callback.answer("ошибка")
            return

        track = results[pick_idx]
        biz = state["data"].get("biz_id", "")
        status_msg_id = state["data"].get("status_msg_id")

        await callback.answer(f"скачиваю {track['title'][:30]}...")
        await _sc_download_and_send(bot, biz, chat_id, track, status_msg_id)


async def _resolve_owner(db: Database, business_id: str) -> int | None:
    """Find the user_id who owns this business connection."""
    cur = await db.db.execute(
        "SELECT user_id FROM users WHERE business_id = ? AND is_connected = 1",
        (business_id,),
    )
    row = await cur.fetchone()
    return row["user_id"] if row else None
