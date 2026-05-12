"""Handle incoming business messages — command-only mode (.sc, .sv)."""

import asyncio
import logging
import os
import re
import tempfile

from aiogram import Bot, Router
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.database import Database
from bot.emoji import Emoji, tg_emoji
from bot.services.soundcloud import download_soundcloud, search_soundcloud

logger = logging.getLogger(__name__)

router = Router()

# In-memory state for multi-step commands per chat
# Key: (owner_id, chat_id) -> {"step": str, "data": dict}
_cmd_state: dict[tuple[int, int], dict] = {}


# ── Helper functions ──────────────────────────────────────────────


async def _delete_business_msg(bot: Bot, biz_id: str, chat_id: int, msg_id: int) -> None:
    try:
        await bot.delete_business_messages(
            business_connection_id=biz_id,
            message_ids=[msg_id],
        )
    except Exception:
        logger.debug("Could not delete msg %s in chat %s", msg_id, chat_id)


async def _resolve_owner(db: Database, business_id: str) -> int | None:
    cur = await db.db.execute(
        "SELECT user_id FROM users WHERE business_id = ? AND is_connected = 1",
        (business_id,),
    )
    row = await cur.fetchone()
    return row["user_id"] if row else None


def _format_duration(seconds: float | int) -> str:
    s = int(seconds)
    if s >= 3600:
        h, remainder = divmod(s, 3600)
        m, sec = divmod(remainder, 60)
        return f"{h}:{m:02d}:{sec:02d}"
    m, sec = divmod(s, 60)
    return f"{m}:{sec:02d}"


# ── Main business message handler ────────────────────────────────


COMMANDS_HELP = {
    ".sc": "скачать музыку с SoundCloud",
    ".sv": "скачать видео с любой соцсети (YouTube, TikTok, Instagram...)",
    ".commands": "показать все доступные команды",
}


@router.business_message()
async def on_business_message(message: Message, db: Database, bot: Bot) -> None:
    biz_id = message.business_connection_id
    if not biz_id:
        return

    owner_id = await _resolve_owner(db, biz_id)
    if owner_id is None:
        return

    chat_id = message.chat.id
    is_owner_message = message.from_user and message.from_user.id == owner_id
    text = message.text or ""

    logger.info(
        "Business msg: chat=%s from=%s owner=%s text=%s",
        chat_id,
        message.from_user.first_name if message.from_user else "?",
        is_owner_message,
        text[:50],
    )

    if is_owner_message and text:
        await _handle_owner_commands(message, bot, biz_id, chat_id, text, owner_id)


async def _handle_owner_commands(
    message: Message, bot: Bot, biz_id: str, chat_id: int, text: str, owner_id: int
) -> None:
    lower = text.strip().lower()
    key = (owner_id, chat_id)

    state = _cmd_state.get(key)
    logger.info("CMD: key=%s text=%s state_step=%s", key, lower[:30], state["step"] if state else None)

    # ── .commands ──
    if lower == ".commands":
        await _delete_business_msg(bot, biz_id, chat_id, message.message_id)
        await _cmd_commands(bot, biz_id, chat_id)
        return

    # ── .sc ──
    if lower == ".sc" or lower == ". sc":
        await _delete_business_msg(bot, biz_id, chat_id, message.message_id)
        await _cmd_sc_start(bot, biz_id, chat_id, key)
        return

    # ── .sv ──
    if lower == ".sv" or lower == ". sv":
        await _delete_business_msg(bot, biz_id, chat_id, message.message_id)
        await _cmd_sv_start(bot, biz_id, chat_id, key)
        return

    if lower.startswith(".sv ") or lower.startswith(". sv "):
        await _delete_business_msg(bot, biz_id, chat_id, message.message_id)
        url = text.strip()[3:].strip() if lower.startswith(".sv ") else text.strip()[4:].strip()
        await _cmd_sv_download(bot, biz_id, chat_id, key, url)
        return

    # ── Multi-step state handlers ──
    if state:
        step = state["step"]
        biz = state["data"].get("biz_id", biz_id)
        await _delete_business_msg(bot, biz, chat_id, message.message_id)

        prompt_id = state["data"].get("prompt_msg_id")
        if prompt_id:
            await _delete_business_msg(bot, biz, chat_id, prompt_id)

        if step == "sc_waiting_query":
            await _cmd_sc_search(bot, biz, chat_id, key, text.strip())
            return

        if step == "sc_waiting_pick":
            await _cmd_sc_pick_text(bot, biz, chat_id, key, text.strip(), state)
            return

        if step == "sv_waiting_url":
            await _cmd_sv_download(bot, biz, chat_id, key, text.strip())
            return


# ══════════════════════════════════════════════════════════════════
# .commands
# ══════════════════════════════════════════════════════════════════


async def _cmd_commands(bot: Bot, biz_id: str, chat_id: int) -> None:
    lines = [f'<b>{tg_emoji(Emoji.INFO, "📋")} Команды:</b>\n']
    for cmd, desc in COMMANDS_HELP.items():
        lines.append(f'<code>{cmd}</code> — {desc}')
    try:
        await bot.send_message(
            chat_id=chat_id,
            text="\n".join(lines),
            parse_mode="HTML",
            business_connection_id=biz_id,
        )
    except Exception:
        logger.exception("commands failed")


# ══════════════════════════════════════════════════════════════════
# .sc — SoundCloud download
# ══════════════════════════════════════════════════════════════════


async def _cmd_sc_start(bot: Bot, biz_id: str, chat_id: int, key: tuple) -> None:
    try:
        msg = await bot.send_message(
            chat_id=chat_id,
            text=(
                f'<b>{tg_emoji(Emoji.DOWNLOAD, "⬇")} SoundCloud</b>\n\n'
                f'{tg_emoji(Emoji.WRITE, "✍")} какую песню ищем'
            ),
            parse_mode="HTML",
            business_connection_id=biz_id,
        )
        _cmd_state[key] = {
            "step": "sc_waiting_query",
            "data": {"biz_id": biz_id, "prompt_msg_id": msg.message_id},
        }
    except Exception:
        logger.exception("sc_start failed")


async def _cmd_sc_search(bot: Bot, biz_id: str, chat_id: int, key: tuple, query: str) -> None:
    try:
        status_msg = await bot.send_message(
            chat_id=chat_id,
            text=f'{tg_emoji(Emoji.LOADING, "🔄")} ищу <b>{query}</b>...',
            parse_mode="HTML",
            business_connection_id=biz_id,
        )
    except Exception:
        _cmd_state.pop(key, None)
        return

    results = await search_soundcloud(query, limit=8)
    if not results:
        try:
            await bot.edit_message_text(
                text=f'{tg_emoji(Emoji.CROSS, "❌")} ничего не нашел по <b>{query}</b>',
                parse_mode="HTML",
                chat_id=chat_id,
                message_id=status_msg.message_id,
                business_connection_id=biz_id,
            )
        except Exception:
            pass
        _cmd_state.pop(key, None)
        return

    lines = [f'<b>{tg_emoji(Emoji.DOWNLOAD, "⬇")} Результаты по {query}:</b>\n']
    for i, t in enumerate(results, 1):
        dur = f" [{_format_duration(t['duration'])}]" if t.get("duration") else ""
        up = f" — {t['uploader']}" if t.get("uploader") else ""
        lines.append(f"{i}. {t['title']}{up}{dur}")

    buttons = []
    for i, t in enumerate(results):
        buttons.append([InlineKeyboardButton(
            text=f"{i + 1}. {t['title'][:30]}",
            callback_data=f"sc:pick:{key[0]}:{key[1]}:{i}",
        )])
    buttons.append([InlineKeyboardButton(
        text="отмена",
        callback_data=f"sc:cancel:{key[0]}:{key[1]}",
    )])

    try:
        await bot.edit_message_text(
            text="\n".join(lines),
            parse_mode="HTML",
            chat_id=chat_id,
            message_id=status_msg.message_id,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            business_connection_id=biz_id,
        )
    except Exception:
        pass

    _cmd_state[key] = {
        "step": "sc_waiting_pick",
        "data": {
            "results": results,
            "status_msg_id": status_msg.message_id,
            "biz_id": biz_id,
        },
    }


async def _cmd_sc_pick_text(
    bot: Bot, biz_id: str, chat_id: int, key: tuple, text: str, state: dict
) -> None:
    results = state["data"]["results"]
    status_msg_id = state["data"].get("status_msg_id")
    try:
        pick = int(text)
    except ValueError:
        return
    if pick < 1 or pick > len(results):
        return
    track = results[pick - 1]
    _cmd_state.pop(key, None)
    await _sc_download_and_send(bot, biz_id, chat_id, track, status_msg_id)


async def _sc_download_and_send(
    bot: Bot, biz_id: str, chat_id: int, track: dict, list_msg_id: int | None = None
) -> None:
    if list_msg_id:
        await _delete_business_msg(bot, biz_id, chat_id, list_msg_id)

    try:
        dl_msg = await bot.send_message(
            chat_id=chat_id,
            text=f'{tg_emoji(Emoji.LOADING, "🔄")} скачиваю <b>{track["title"]}</b>...',
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
                text=f'{tg_emoji(Emoji.CROSS, "❌")} не смог отправить файл',
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


# ══════════════════════════════════════════════════════════════════
# .sv — Video download from any social network
# ══════════════════════════════════════════════════════════════════


async def _cmd_sv_start(bot: Bot, biz_id: str, chat_id: int, key: tuple) -> None:
    try:
        msg = await bot.send_message(
            chat_id=chat_id,
            text=(
                f'<b>{tg_emoji(Emoji.MEDIA, "🎬")} Скачать видео</b>\n\n'
                f'{tg_emoji(Emoji.WRITE, "✍")} скинь ссылку на видео\n'
                f'<i>YouTube, TikTok, Instagram, Twitter, VK...</i>'
            ),
            parse_mode="HTML",
            business_connection_id=biz_id,
        )
        _cmd_state[key] = {
            "step": "sv_waiting_url",
            "data": {"biz_id": biz_id, "prompt_msg_id": msg.message_id},
        }
    except Exception:
        logger.exception("sv_start failed")


async def _cmd_sv_download(bot: Bot, biz_id: str, chat_id: int, key: tuple, url: str) -> None:
    _cmd_state.pop(key, None)

    if not re.match(r'https?://', url, re.IGNORECASE):
        url = "https://" + url

    try:
        status_msg = await bot.send_message(
            chat_id=chat_id,
            text=f'{tg_emoji(Emoji.LOADING, "🔄")} скачиваю видео...',
            parse_mode="HTML",
            business_connection_id=biz_id,
        )
    except Exception:
        return

    tmp_dir = tempfile.mkdtemp(prefix="sv_")
    output_path = os.path.join(tmp_dir, "%(title).80s.%(ext)s")

    try:
        # Try with impersonation first (helps with TikTok etc)
        proc = await asyncio.create_subprocess_exec(
            "yt-dlp",
            "--no-playlist",
            "-f", "best[filesize<50M]/best",
            "--merge-output-format", "mp4",
            "--impersonate", "chrome",
            "--no-check-certificates",
            "-o", output_path,
            url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=180)

        # Retry without impersonation if it failed on that
        if proc.returncode != 0 and b"impersonat" in stderr.lower():
            proc = await asyncio.create_subprocess_exec(
                "yt-dlp",
                "--no-playlist",
                "-f", "best[filesize<50M]/best",
                "--merge-output-format", "mp4",
                "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "--no-check-certificates",
                "-o", output_path,
                url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=180)

        # Retry with cobalt API for TikTok/Instagram if yt-dlp failed
        if proc.returncode != 0:
            cobalt_ok = await _try_cobalt_download(tmp_dir, url)
            if cobalt_ok:
                proc = None  # mark as success

        if proc is not None and proc.returncode != 0:
            err_text = stderr.decode(errors="ignore")[:500]
            logger.error("yt-dlp video failed: %s", err_text)
            error_detail = ""
            if "blocked" in err_text.lower() or "ip" in err_text.lower():
                error_detail = "\n<i>IP сервера заблокирован этим сайтом</i>"
            elif "not found" in err_text.lower() or "404" in err_text:
                error_detail = "\n<i>видео не найдено</i>"
            try:
                await bot.edit_message_text(
                    text=f'{tg_emoji(Emoji.CROSS, "❌")} не получилось скачать видео{error_detail}',
                    parse_mode="HTML",
                    chat_id=chat_id,
                    message_id=status_msg.message_id,
                    business_connection_id=biz_id,
                )
            except Exception:
                pass
            return

        # Find downloaded file
        video_file = None
        for f in os.listdir(tmp_dir):
            full = os.path.join(tmp_dir, f)
            if os.path.isfile(full):
                video_file = full
                break

        if not video_file:
            try:
                await bot.edit_message_text(
                    text=f'{tg_emoji(Emoji.CROSS, "❌")} файл не найден после скачивания',
                    parse_mode="HTML",
                    chat_id=chat_id,
                    message_id=status_msg.message_id,
                    business_connection_id=biz_id,
                )
            except Exception:
                pass
            return

        file_size = os.path.getsize(video_file)
        if file_size > 50 * 1024 * 1024:
            try:
                await bot.edit_message_text(
                    text=f'{tg_emoji(Emoji.CROSS, "❌")} видео слишком большое ({file_size // (1024*1024)}MB)',
                    parse_mode="HTML",
                    chat_id=chat_id,
                    message_id=status_msg.message_id,
                    business_connection_id=biz_id,
                )
            except Exception:
                pass
            return

        await _delete_business_msg(bot, biz_id, chat_id, status_msg.message_id)

        vid = FSInputFile(video_file, filename=os.path.basename(video_file))
        await bot.send_video(
            chat_id=chat_id,
            video=vid,
            business_connection_id=biz_id,
        )

    except asyncio.TimeoutError:
        try:
            await bot.edit_message_text(
                text=f'{tg_emoji(Emoji.CROSS, "❌")} таймаут скачивания',
                parse_mode="HTML",
                chat_id=chat_id,
                message_id=status_msg.message_id,
                business_connection_id=biz_id,
            )
        except Exception:
            pass
    except Exception:
        logger.exception("sv download error")
        try:
            await bot.edit_message_text(
                text=f'{tg_emoji(Emoji.CROSS, "❌")} ошибка при скачивании',
                parse_mode="HTML",
                chat_id=chat_id,
                message_id=status_msg.message_id,
                business_connection_id=biz_id,
            )
        except Exception:
            pass
    finally:
        try:
            for f in os.listdir(tmp_dir):
                os.unlink(os.path.join(tmp_dir, f))
            os.rmdir(tmp_dir)
        except Exception:
            pass


async def _try_cobalt_download(tmp_dir: str, url: str) -> bool:
    """Try downloading via cobalt.tools API (works for TikTok, Instagram, etc)."""
    import aiohttp

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.cobalt.tools/",
                json={"url": url},
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                data = await resp.json()

            download_url = data.get("url")
            if not download_url:
                return False

            async with session.get(download_url, timeout=aiohttp.ClientTimeout(total=120)) as dl_resp:
                if dl_resp.status != 200:
                    return False
                content = await dl_resp.read()
                if len(content) < 1000:
                    return False
                ext = "mp4"
                ct = dl_resp.headers.get("content-type", "")
                if "webm" in ct:
                    ext = "webm"
                out_path = os.path.join(tmp_dir, f"video.{ext}")
                with open(out_path, "wb") as f:
                    f.write(content)
                return True
    except Exception:
        logger.debug("cobalt download failed for %s", url)
        return False


# ══════════════════════════════════════════════════════════════════
# Callback handlers
# ══════════════════════════════════════════════════════════════════


@router.callback_query(lambda c: c.data and c.data.startswith("sc:"))
async def on_sc_callback(callback: CallbackQuery, bot: Bot) -> None:
    parts = callback.data.split(":")

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
