"""Handle incoming business messages — command-only mode (.sc, .sv, .ping, .gift, etc)."""

import asyncio
import json
import logging
import os
import re
import tempfile
import time

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
    """Try to delete a message in a business chat."""
    try:
        await bot.delete_business_messages(
            business_connection_id=biz_id,
            message_ids=[msg_id],
        )
    except Exception:
        logger.debug("Could not delete msg %s in chat %s", msg_id, chat_id)


async def _resolve_owner(db: Database, business_id: str) -> int | None:
    """Find the user_id who owns this business connection."""
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


@router.business_message()
async def on_business_message(message: Message, db: Database, bot: Bot) -> None:
    """Process every business-chat message — handle owner commands only."""
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

    # Only handle owner commands
    if is_owner_message and text:
        await _handle_owner_commands(message, bot, biz_id, chat_id, text, owner_id)


# ── Command dispatcher ────────────────────────────────────────────


COMMANDS_HELP = {
    ".sc": "скачать музыку с SoundCloud",
    ".sv": "скачать видео с любой соцсети (YouTube, TikTok, Instagram...)",
    ".ping": "проверить VPN протокол (vless, vmess, и тд) — пинг, скорость",
    ".gift": "отправить подарок пользователю в Telegram",
    ".calc": "калькулятор — математический + конвертер валют (все валюты мира + крипта)",
    ".qr": "создать QR-код из текста или ссылки",
    ".weather": "узнать погоду в городе",
    ".translate": "перевести текст (авто-определение языка)",
    ".whois": "информация о домене",
    ".short": "сократить ссылку",
    ".commands": "показать все доступные команды",
}


async def _handle_owner_commands(
    message: Message, bot: Bot, biz_id: str, chat_id: int, text: str, owner_id: int
) -> None:
    """Handle owner dot-commands — dispatch to specific handlers."""
    lower = text.strip().lower()
    key = (owner_id, chat_id)

    # Check if we're in a multi-step flow
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

    # ── .ping ──
    if lower == ".ping" or lower == ". ping":
        await _delete_business_msg(bot, biz_id, chat_id, message.message_id)
        await _cmd_ping_start(bot, biz_id, chat_id, key)
        return

    # ── .gift ──
    if lower == ".gift" or lower == ". gift":
        await _delete_business_msg(bot, biz_id, chat_id, message.message_id)
        await _cmd_gift_start(bot, biz_id, chat_id, key)
        return

    # ── .calc ──
    if lower == ".calc" or lower == ". calc":
        await _delete_business_msg(bot, biz_id, chat_id, message.message_id)
        await _cmd_calc_start(bot, biz_id, chat_id, key)
        return

    # ── .qr ──
    if lower.startswith(".qr"):
        await _delete_business_msg(bot, biz_id, chat_id, message.message_id)
        qr_text = text.strip()[3:].strip()
        if qr_text:
            await _cmd_qr(bot, biz_id, chat_id, qr_text)
        else:
            _cmd_state[key] = {"step": "qr_waiting", "data": {"biz_id": biz_id}}
            try:
                msg = await bot.send_message(
                    chat_id=chat_id,
                    text=f'{tg_emoji(Emoji.LINK, "🔗")} <b>QR-код</b>\n\nнапиши текст или ссылку',
                    parse_mode="HTML",
                    business_connection_id=biz_id,
                )
                _cmd_state[key]["data"]["prompt_msg_id"] = msg.message_id
            except Exception:
                _cmd_state.pop(key, None)
        return

    # ── .weather ──
    if lower.startswith(".weather"):
        await _delete_business_msg(bot, biz_id, chat_id, message.message_id)
        city = text.strip()[8:].strip()
        if city:
            await _cmd_weather(bot, biz_id, chat_id, city)
        else:
            _cmd_state[key] = {"step": "weather_waiting", "data": {"biz_id": biz_id}}
            try:
                msg = await bot.send_message(
                    chat_id=chat_id,
                    text=f'{tg_emoji(Emoji.GEO, "🌍")} <b>Погода</b>\n\nнапиши название города',
                    parse_mode="HTML",
                    business_connection_id=biz_id,
                )
                _cmd_state[key]["data"]["prompt_msg_id"] = msg.message_id
            except Exception:
                _cmd_state.pop(key, None)
        return

    # ── .translate ──
    if lower.startswith(".translate"):
        await _delete_business_msg(bot, biz_id, chat_id, message.message_id)
        tr_text = text.strip()[10:].strip()
        if tr_text:
            await _cmd_translate(bot, biz_id, chat_id, tr_text)
        else:
            _cmd_state[key] = {"step": "translate_waiting", "data": {"biz_id": biz_id}}
            try:
                msg = await bot.send_message(
                    chat_id=chat_id,
                    text=f'{tg_emoji(Emoji.FONT, "🌐")} <b>Переводчик</b>\n\nнапиши текст для перевода',
                    parse_mode="HTML",
                    business_connection_id=biz_id,
                )
                _cmd_state[key]["data"]["prompt_msg_id"] = msg.message_id
            except Exception:
                _cmd_state.pop(key, None)
        return

    # ── .whois ──
    if lower.startswith(".whois"):
        await _delete_business_msg(bot, biz_id, chat_id, message.message_id)
        domain = text.strip()[6:].strip()
        if domain:
            await _cmd_whois(bot, biz_id, chat_id, domain)
        else:
            _cmd_state[key] = {"step": "whois_waiting", "data": {"biz_id": biz_id}}
            try:
                msg = await bot.send_message(
                    chat_id=chat_id,
                    text=f'{tg_emoji(Emoji.LINK, "🔍")} <b>WHOIS</b>\n\nнапиши домен',
                    parse_mode="HTML",
                    business_connection_id=biz_id,
                )
                _cmd_state[key]["data"]["prompt_msg_id"] = msg.message_id
            except Exception:
                _cmd_state.pop(key, None)
        return

    # ── .short ──
    if lower.startswith(".short"):
        await _delete_business_msg(bot, biz_id, chat_id, message.message_id)
        url = text.strip()[6:].strip()
        if url:
            await _cmd_short(bot, biz_id, chat_id, url)
        else:
            _cmd_state[key] = {"step": "short_waiting", "data": {"biz_id": biz_id}}
            try:
                msg = await bot.send_message(
                    chat_id=chat_id,
                    text=f'{tg_emoji(Emoji.LINK, "🔗")} <b>Сократить ссылку</b>\n\nскинь ссылку',
                    parse_mode="HTML",
                    business_connection_id=biz_id,
                )
                _cmd_state[key]["data"]["prompt_msg_id"] = msg.message_id
            except Exception:
                _cmd_state.pop(key, None)
        return

    # ── Multi-step state handlers ──
    if state:
        step = state["step"]
        biz = state["data"].get("biz_id", biz_id)
        await _delete_business_msg(bot, biz, chat_id, message.message_id)

        # Delete prompt message
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

        if step == "ping_waiting":
            await _cmd_ping_run(bot, biz, chat_id, key, text.strip())
            return

        if step == "gift_waiting_user":
            await _cmd_gift_pick_user(bot, biz, chat_id, key, text.strip())
            return

        if step == "calc_math_waiting":
            await _cmd_calc_math(bot, biz, chat_id, text.strip())
            _cmd_state.pop(key, None)
            return

        if step == "calc_currency_amount":
            # User typed the amount; now show "TO" currency categories
            try:
                amount = float(text.strip().replace(",", "."))
            except ValueError:
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=f'{tg_emoji(Emoji.CROSS, "❌")} напиши число',
                        parse_mode="HTML",
                        business_connection_id=biz,
                    )
                except Exception:
                    pass
                return
            from_cur = state["data"].get("from_cur", "USD")
            amount_str = f"{amount:g}"
            buttons = _currency_category_buttons(key[0], key[1], "to")
            try:
                msg = await bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f'{tg_emoji(Emoji.MONEY, "💱")} <b>{amount_str} {from_cur}</b>\n\n'
                        f'в какую валюту конвертируем'
                    ),
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
                    business_connection_id=biz,
                )
                _cmd_state[key] = {
                    "step": "calc_currency_to",
                    "data": {"biz_id": biz, "from_cur": from_cur, "amount": amount, "menu_msg_id": msg.message_id},
                }
            except Exception:
                _cmd_state.pop(key, None)
            return

        if step == "qr_waiting":
            await _cmd_qr(bot, biz, chat_id, text.strip())
            _cmd_state.pop(key, None)
            return

        if step == "weather_waiting":
            await _cmd_weather(bot, biz, chat_id, text.strip())
            _cmd_state.pop(key, None)
            return

        if step == "translate_waiting":
            await _cmd_translate(bot, biz, chat_id, text.strip())
            _cmd_state.pop(key, None)
            return

        if step == "whois_waiting":
            await _cmd_whois(bot, biz, chat_id, text.strip())
            _cmd_state.pop(key, None)
            return

        if step == "short_waiting":
            await _cmd_short(bot, biz, chat_id, text.strip())
            _cmd_state.pop(key, None)
            return

        # Unknown state — clear it
        _cmd_state.pop(key, None)


# ══════════════════════════════════════════════════════════════════
# .commands
# ══════════════════════════════════════════════════════════════════


async def _cmd_commands(bot: Bot, biz_id: str, chat_id: int) -> None:
    lines = [f'<b>{tg_emoji(Emoji.CODE, "📋")} Все команды:</b>\n']
    for cmd, desc in COMMANDS_HELP.items():
        lines.append(f'<b>{cmd}</b> — {desc}')
    try:
        await bot.send_message(
            chat_id=chat_id,
            text="\n".join(lines),
            parse_mode="HTML",
            business_connection_id=biz_id,
        )
    except Exception:
        logger.exception("Failed to send commands list")


# ══════════════════════════════════════════════════════════════════
# .sc — SoundCloud
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
    """Handle text-based number pick for SoundCloud."""
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

    # Validate URL
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
    output_path = os.path.join(tmp_dir, "%(title)s.%(ext)s")

    try:
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

        # If impersonation failed, retry without it
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

        if proc.returncode != 0:
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

        # Check file size (Telegram limit ~50MB)
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
        # Cleanup
        try:
            for f in os.listdir(tmp_dir):
                os.unlink(os.path.join(tmp_dir, f))
            os.rmdir(tmp_dir)
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════
# .ping — VPN protocol testing
# ══════════════════════════════════════════════════════════════════


async def _cmd_ping_start(bot: Bot, biz_id: str, chat_id: int, key: tuple) -> None:
    try:
        msg = await bot.send_message(
            chat_id=chat_id,
            text=(
                f'<b>{tg_emoji(Emoji.LOADING, "📡")} VPN Ping</b>\n\n'
                f'{tg_emoji(Emoji.WRITE, "✍")} скинь протокол (vless://, vmess://, ss://, trojan://, hy2:// и тд)\n\n'
                f'<i>поддерживаемые: vless, vmess, shadowsocks, trojan, hysteria2, wireguard</i>'
            ),
            parse_mode="HTML",
            business_connection_id=biz_id,
        )
        _cmd_state[key] = {
            "step": "ping_waiting",
            "data": {"biz_id": biz_id, "prompt_msg_id": msg.message_id},
        }
    except Exception:
        logger.exception("ping_start failed")


def _parse_vpn_protocol(uri: str) -> dict | None:
    """Parse VPN protocol URI and extract server info."""
    uri = uri.strip()

    # Try to extract protocol and host
    proto_match = re.match(r'^(\w+)://', uri)
    if not proto_match:
        return None

    protocol = proto_match.group(1).lower()
    rest = uri[proto_match.end():]

    # Extract host:port from various formats
    host = None
    port = None

    # For vmess:// (base64 encoded JSON)
    if protocol == "vmess":
        import base64
        try:
            # vmess://base64_json
            decoded = base64.b64decode(rest + "==").decode("utf-8", errors="ignore")
            data = json.loads(decoded)
            host = data.get("add") or data.get("host")
            port = int(data.get("port", 443))
            return {"protocol": protocol, "host": host, "port": port, "raw": uri[:80]}
        except Exception:
            pass

    # For vless, ss, trojan, hy2 — format: user@host:port?params#remark
    # or just host:port
    at_split = rest.split("@", 1)
    server_part = at_split[-1]  # take part after @ or the whole thing

    # Remove fragment (#remark)
    server_part = server_part.split("#")[0]
    # Remove query (?params)
    server_part = server_part.split("?")[0]

    # Extract host:port
    hp_match = re.match(r'\[?([^\]\[:]+)\]?:(\d+)', server_part)
    if hp_match:
        host = hp_match.group(1)
        port = int(hp_match.group(2))
    elif re.match(r'[\w.-]+', server_part):
        host = server_part.split(":")[0]
        port = 443

    if host:
        return {"protocol": protocol, "host": host, "port": port or 443, "raw": uri[:80]}
    return None


async def _cmd_ping_run(bot: Bot, biz_id: str, chat_id: int, key: tuple, protocol_uri: str) -> None:
    _cmd_state.pop(key, None)

    parsed = _parse_vpn_protocol(protocol_uri)
    if not parsed:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=f'{tg_emoji(Emoji.CROSS, "❌")} не могу распарсить протокол\n\nскинь полную ссылку (vless://... vmess://... и тд)',
                parse_mode="HTML",
                business_connection_id=biz_id,
            )
        except Exception:
            pass
        return

    host = parsed["host"]
    port = parsed["port"]
    protocol = parsed["protocol"]

    try:
        status_msg = await bot.send_message(
            chat_id=chat_id,
            text=f'{tg_emoji(Emoji.LOADING, "🔄")} тестирую <b>{protocol}://{host}:{port}</b>...',
            parse_mode="HTML",
            business_connection_id=biz_id,
        )
    except Exception:
        return

    results = []

    # 1. ICMP Ping
    try:
        proc = await asyncio.create_subprocess_exec(
            "ping", "-c", "4", "-W", "3", host,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
        ping_output = stdout.decode()

        # Parse ping results
        rtt_match = re.search(r'rtt min/avg/max/mdev = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)', ping_output)
        loss_match = re.search(r'(\d+)% packet loss', ping_output)

        if rtt_match:
            ping_min = float(rtt_match.group(1))
            ping_avg = float(rtt_match.group(2))
            ping_max = float(rtt_match.group(3))
            loss = loss_match.group(1) if loss_match else "?"
            results.append(f"📡 <b>Пинг:</b> {ping_avg:.1f}ms (мин {ping_min:.1f} / макс {ping_max:.1f})")
            results.append(f"📉 <b>Потери:</b> {loss}%")
        else:
            results.append("📡 <b>Пинг:</b> хост недоступен")
    except Exception:
        results.append("📡 <b>Пинг:</b> таймаут")

    # 2. TCP port check
    try:
        proc = await asyncio.create_subprocess_exec(
            "bash", "-c", f"timeout 5 bash -c 'echo > /dev/tcp/{host}/{port}' 2>/dev/null && echo OPEN || echo CLOSED",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=8)
        port_status = stdout.decode().strip()
        if "OPEN" in port_status:
            results.append(f"🔌 <b>Порт {port}:</b> открыт")
        else:
            results.append(f"🔌 <b>Порт {port}:</b> закрыт")
    except Exception:
        results.append(f"🔌 <b>Порт {port}:</b> не удалось проверить")

    # 3. Download speed test (small file)
    try:
        start_time = time.time()
        proc = await asyncio.create_subprocess_exec(
            "curl", "-o", "/dev/null", "-w", "%{speed_download}", "--connect-timeout", "5", "--max-time", "10",
            f"https://{host}:{port}/",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=12)
        elapsed = time.time() - start_time
        results.append(f"⏱ <b>Время ответа:</b> {elapsed:.2f}s")
    except Exception:
        pass

    # 4. DNS resolution time
    try:
        proc = await asyncio.create_subprocess_exec(
            "bash", "-c", f"dig +noall +stats {host} 2>/dev/null | grep 'Query time'",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        dns_out = stdout.decode().strip()
        dns_match = re.search(r'Query time: (\d+)', dns_out)
        if dns_match:
            results.append(f"🌐 <b>DNS:</b> {dns_match.group(1)}ms")
    except Exception:
        pass

    # Build result message
    text_lines = [
        f'<b>{tg_emoji(Emoji.CHECK, "📊")} Результат теста</b>\n',
        f'<b>Протокол:</b> {protocol.upper()}',
        f'<b>Сервер:</b> {host}:{port}\n',
    ] + results

    try:
        await bot.edit_message_text(
            text="\n".join(text_lines),
            parse_mode="HTML",
            chat_id=chat_id,
            message_id=status_msg.message_id,
            business_connection_id=biz_id,
        )
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════
# .gift — Send Telegram gift
# ══════════════════════════════════════════════════════════════════


async def _cmd_gift_start(bot: Bot, biz_id: str, chat_id: int, key: tuple) -> None:
    try:
        msg = await bot.send_message(
            chat_id=chat_id,
            text=(
                f'<b>{tg_emoji(Emoji.GIFT, "🎁")} Подарок</b>\n\n'
                f'{tg_emoji(Emoji.WRITE, "✍")} напиши юзернейм кому отправить\n'
                f'<i>например: @username</i>'
            ),
            parse_mode="HTML",
            business_connection_id=biz_id,
        )
        _cmd_state[key] = {
            "step": "gift_waiting_user",
            "data": {"biz_id": biz_id, "prompt_msg_id": msg.message_id},
        }
    except Exception:
        logger.exception("gift_start failed")


async def _cmd_gift_pick_user(bot: Bot, biz_id: str, chat_id: int, key: tuple, username: str) -> None:
    _cmd_state.pop(key, None)

    username = username.strip().lstrip("@")
    if not username:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=f'{tg_emoji(Emoji.CROSS, "❌")} напиши юзернейм',
                parse_mode="HTML",
                business_connection_id=biz_id,
            )
        except Exception:
            pass
        return

    try:
        gifts_response = await bot.get_available_gifts()
        gifts = gifts_response.gifts if hasattr(gifts_response, 'gifts') else []
    except Exception:
        logger.exception("Failed to get gifts")
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=f'{tg_emoji(Emoji.CROSS, "❌")} не удалось загрузить подарки\n<i>боту нужны звёзды для отправки подарков</i>',
                parse_mode="HTML",
                business_connection_id=biz_id,
            )
        except Exception:
            pass
        return

    if not gifts:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=f'{tg_emoji(Emoji.CROSS, "❌")} нет доступных подарков',
                parse_mode="HTML",
                business_connection_id=biz_id,
            )
        except Exception:
            pass
        return

    lines = [f'<b>{tg_emoji(Emoji.GIFT, "🎁")} Подарки для @{username}:</b>\n']
    buttons = []
    for i, gift in enumerate(gifts[:10]):
        star_count = getattr(gift, 'star_count', 0)
        gift_id = getattr(gift, 'id', str(i))
        lines.append(f'{i + 1}. {star_count} ⭐')
        buttons.append([InlineKeyboardButton(
            text=f"🎁 {star_count} ⭐",
            callback_data=f"gift:{username}:{gift_id}",
        )])

    buttons.append([InlineKeyboardButton(
        text="отмена",
        callback_data="gift:cancel:0:0:0",
    )])

    try:
        await bot.send_message(
            chat_id=chat_id,
            text="\n".join(lines),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            business_connection_id=biz_id,
        )
    except Exception:
        logger.exception("Failed to show gifts")


# ══════════════════════════════════════════════════════════════════
# .calc — Calculator (math + currency converter)
# ══════════════════════════════════════════════════════════════════

CURRENCY_CATEGORIES = {
    "Основные": ["USD", "EUR", "RUB", "GBP", "CNY", "JPY", "CHF", "UAH", "KZT", "BYN", "TRY", "AED", "INR"],
    "Крипта": ["BTC", "ETH", "TON", "USDT", "BNB", "SOL", "XRP", "DOGE", "ADA", "DOT", "LTC"],
    "Другие": ["CAD", "AUD", "NZD", "SGD", "HKD", "KRW", "BRL", "MXN", "ZAR", "THB", "PLN", "CZK", "SEK", "NOK"],
}


async def _cmd_calc_start(bot: Bot, biz_id: str, chat_id: int, key: tuple) -> None:
    buttons = [
        [
            InlineKeyboardButton(text="🔢 Математический", callback_data=f"calc:math:{key[0]}:{key[1]}"),
            InlineKeyboardButton(text="💱 Валюты", callback_data=f"calc:currency:{key[0]}:{key[1]}"),
        ],
        [InlineKeyboardButton(text="отмена", callback_data=f"calc:cancel:{key[0]}:{key[1]}")],
    ]
    try:
        msg = await bot.send_message(
            chat_id=chat_id,
            text=(
                f'<b>{tg_emoji(Emoji.CODE, "🔢")} Калькулятор</b>\n\n'
                f'выбери какой используем'
            ),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            business_connection_id=biz_id,
        )
        _cmd_state[key] = {"step": "calc_menu", "data": {"biz_id": biz_id, "menu_msg_id": msg.message_id}}
    except Exception:
        logger.exception("calc_start failed")


async def _cmd_calc_math(bot: Bot, biz_id: str, chat_id: int, expr: str) -> None:
    allowed = set("0123456789+-*/().% ")
    if not all(c in allowed for c in expr):
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=f'{tg_emoji(Emoji.CROSS, "❌")} только цифры и операторы (+, -, *, /, %)',
                parse_mode="HTML",
                business_connection_id=biz_id,
            )
        except Exception:
            pass
        return

    try:
        result = eval(expr)  # noqa: S307
        if isinstance(result, float):
            result = round(result, 8)
        await bot.send_message(
            chat_id=chat_id,
            text=f'{tg_emoji(Emoji.CODE, "🔢")} <b>{expr}</b> = <code>{result}</code>',
            parse_mode="HTML",
            business_connection_id=biz_id,
        )
    except Exception:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=f'{tg_emoji(Emoji.CROSS, "❌")} ошибка в выражении',
                parse_mode="HTML",
                business_connection_id=biz_id,
            )
        except Exception:
            pass


async def _fetch_rates() -> dict:
    """Fetch currency rates from multiple APIs."""
    import aiohttp
    rates = {}

    # Fiat currencies from exchangerate-api
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://open.er-api.com/v6/latest/USD",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                if data.get("rates"):
                    rates.update(data["rates"])
    except Exception:
        logger.warning("Failed to fetch fiat rates")

    # Crypto from CoinGecko
    crypto_ids = {
        "bitcoin": "BTC", "ethereum": "ETH", "toncoin": "TON",
        "tether": "USDT", "binancecoin": "BNB", "solana": "SOL",
        "ripple": "XRP", "dogecoin": "DOGE", "cardano": "ADA",
        "polkadot": "DOT", "litecoin": "LTC",
    }
    try:
        async with aiohttp.ClientSession() as session:
            ids = ",".join(crypto_ids.keys())
            async with session.get(
                f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                for cg_id, symbol in crypto_ids.items():
                    if cg_id in data and "usd" in data[cg_id]:
                        price_usd = data[cg_id]["usd"]
                        if price_usd > 0:
                            rates[symbol] = 1.0 / price_usd
    except Exception:
        logger.warning("Failed to fetch crypto rates")

    rates["USD"] = 1.0
    return rates


def _currency_category_buttons(owner_id: int, chat_id: int, prefix: str) -> list:
    """Build inline buttons for currency category selection."""
    return [
        [
            InlineKeyboardButton(text="💵 Основные", callback_data=f"cur:{prefix}:main:{owner_id}:{chat_id}"),
            InlineKeyboardButton(text="🪙 Крипта", callback_data=f"cur:{prefix}:crypto:{owner_id}:{chat_id}"),
        ],
        [
            InlineKeyboardButton(text="🌍 Другие", callback_data=f"cur:{prefix}:other:{owner_id}:{chat_id}"),
        ],
        [InlineKeyboardButton(text="отмена", callback_data=f"cur:cancel:x:{owner_id}:{chat_id}")],
    ]


def _currency_buttons(currencies: list, owner_id: int, chat_id: int, prefix: str) -> list:
    """Build inline buttons for individual currencies (3 per row)."""
    buttons = []
    row = []
    for cur in currencies:
        row.append(InlineKeyboardButton(text=cur, callback_data=f"cur:{prefix}:{cur}:{owner_id}:{chat_id}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="⬅ назад", callback_data=f"cur:{prefix}:back:{owner_id}:{chat_id}")])
    return buttons


CATEGORY_MAP = {
    "main": CURRENCY_CATEGORIES["Основные"],
    "crypto": CURRENCY_CATEGORIES["Крипта"],
    "other": CURRENCY_CATEGORIES["Другие"],
}


async def _do_currency_convert(bot: Bot, biz_id: str, chat_id: int, from_cur: str, to_cur: str, amount: float, msg_id: int) -> None:
    """Perform the actual conversion and edit the message with the result."""
    rates = await _fetch_rates()

    if from_cur not in rates or to_cur not in rates:
        missing = from_cur if from_cur not in rates else to_cur
        try:
            await bot.edit_message_text(
                text=f'{tg_emoji(Emoji.CROSS, "❌")} валюта <b>{missing}</b> не найдена',
                parse_mode="HTML",
                chat_id=chat_id,
                message_id=msg_id,
                business_connection_id=biz_id,
            )
        except Exception:
            pass
        return

    usd_amount = amount / rates[from_cur]
    result = usd_amount * rates[to_cur]

    if result >= 1:
        result_str = f"{result:,.2f}"
    elif result >= 0.01:
        result_str = f"{result:.4f}"
    else:
        result_str = f"{result:.8f}"

    amount_str = f"{amount:,.2f}" if amount == int(amount) else f"{amount:g}"

    rate = rates[to_cur] / rates[from_cur]
    rate_str = f"{rate:.6g}"

    try:
        await bot.edit_message_text(
            text=(
                f'{tg_emoji(Emoji.MONEY, "💱")} <b>Конвертер валют</b>\n\n'
                f'<code>{amount_str} {from_cur}</code> = <code>{result_str} {to_cur}</code>\n\n'
                f'📊 курс: 1 {from_cur} = {rate_str} {to_cur}'
            ),
            parse_mode="HTML",
            chat_id=chat_id,
            message_id=msg_id,
            business_connection_id=biz_id,
        )
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════
# .qr — QR Code
# ══════════════════════════════════════════════════════════════════


async def _cmd_qr(bot: Bot, biz_id: str, chat_id: int, text: str) -> None:
    try:
        import urllib.parse
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=400x400&data={urllib.parse.quote(text)}"
        await bot.send_photo(
            chat_id=chat_id,
            photo=qr_url,
            caption=f'{tg_emoji(Emoji.LINK, "🔗")} QR-код',
            parse_mode="HTML",
            business_connection_id=biz_id,
        )
    except Exception:
        logger.exception("QR failed")
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=f'{tg_emoji(Emoji.CROSS, "❌")} не получилось создать QR-код',
                parse_mode="HTML",
                business_connection_id=biz_id,
            )
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════
# .weather — Weather
# ══════════════════════════════════════════════════════════════════


async def _cmd_weather(bot: Bot, biz_id: str, chat_id: int, city: str) -> None:
    import aiohttp
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://wttr.in/{city}?format=j1",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    raise ValueError("bad response")
                data = await resp.json()

        current = data.get("current_condition", [{}])[0]
        area = data.get("nearest_area", [{}])[0]
        area_name = area.get("areaName", [{}])[0].get("value", city)
        country = area.get("country", [{}])[0].get("value", "")

        temp = current.get("temp_C", "?")
        feels = current.get("FeelsLikeC", "?")
        humidity = current.get("humidity", "?")
        wind = current.get("windspeedKmph", "?")
        desc_list = current.get("lang_ru", current.get("weatherDesc", [{}]))
        desc = desc_list[0].get("value", "") if desc_list else ""

        text_msg = (
            f'<b>{tg_emoji(Emoji.GEO, "🌍")} {area_name}, {country}</b>\n\n'
            f'🌡 <b>Температура:</b> {temp}°C (ощущается {feels}°C)\n'
            f'💧 <b>Влажность:</b> {humidity}%\n'
            f'💨 <b>Ветер:</b> {wind} км/ч\n'
            f'☁ <b>Описание:</b> {desc}'
        )

        await bot.send_message(
            chat_id=chat_id,
            text=text_msg,
            parse_mode="HTML",
            business_connection_id=biz_id,
        )
    except Exception:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=f'{tg_emoji(Emoji.CROSS, "❌")} не нашел погоду для <b>{city}</b>',
                parse_mode="HTML",
                business_connection_id=biz_id,
            )
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════
# .translate — Translate text
# ══════════════════════════════════════════════════════════════════


async def _cmd_translate(bot: Bot, biz_id: str, chat_id: int, text: str) -> None:
    import aiohttp

    # Detect if text is Russian -> translate to English, otherwise -> Russian
    has_cyrillic = bool(re.search('[а-яА-ЯёЁ]', text))
    target = "en" if has_cyrillic else "ru"
    target_name = "English" if has_cyrillic else "Русский"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.mymemory.translated.net/get",
                params={"q": text[:500], "langpair": f"{'ru' if has_cyrillic else 'auto'}|{target}"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()

        translated = data.get("responseData", {}).get("translatedText", "")
        if not translated:
            raise ValueError("empty translation")

        await bot.send_message(
            chat_id=chat_id,
            text=(
                f'{tg_emoji(Emoji.FONT, "🌐")} <b>Перевод ({target_name}):</b>\n\n'
                f'<code>{translated}</code>'
            ),
            parse_mode="HTML",
            business_connection_id=biz_id,
        )
    except Exception:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=f'{tg_emoji(Emoji.CROSS, "❌")} не получилось перевести',
                parse_mode="HTML",
                business_connection_id=biz_id,
            )
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════
# .whois — Domain info
# ══════════════════════════════════════════════════════════════════


async def _cmd_whois(bot: Bot, biz_id: str, chat_id: int, domain: str) -> None:
    domain = domain.strip().lower()
    domain = re.sub(r'^https?://', '', domain)
    domain = domain.split("/")[0]

    try:
        proc = await asyncio.create_subprocess_exec(
            "whois", domain,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        output = stdout.decode(errors="ignore")

        # Extract key info
        info_lines = []
        for line in output.split("\n"):
            line = line.strip()
            for field in ["Domain Name:", "Registrar:", "Creation Date:", "Updated Date:",
                          "Registry Expiry Date:", "Name Server:", "Registrant Country:"]:
                if line.upper().startswith(field.upper()):
                    info_lines.append(line)
                    break

        if info_lines:
            result = "\n".join(info_lines[:15])
            await bot.send_message(
                chat_id=chat_id,
                text=f'{tg_emoji(Emoji.LINK, "🔍")} <b>WHOIS {domain}:</b>\n\n<code>{result}</code>',
                parse_mode="HTML",
                business_connection_id=biz_id,
            )
        else:
            await bot.send_message(
                chat_id=chat_id,
                text=f'{tg_emoji(Emoji.CROSS, "❌")} нет данных для <b>{domain}</b>',
                parse_mode="HTML",
                business_connection_id=biz_id,
            )
    except Exception:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=f'{tg_emoji(Emoji.CROSS, "❌")} ошибка при запросе WHOIS',
                parse_mode="HTML",
                business_connection_id=biz_id,
            )
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════
# .short — URL shortener
# ══════════════════════════════════════════════════════════════════


async def _cmd_short(bot: Bot, biz_id: str, chat_id: int, url: str) -> None:
    import aiohttp

    if not re.match(r'https?://', url, re.IGNORECASE):
        url = "https://" + url

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://is.gd/create.php?format=simple&url={url}",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                short_url = await resp.text()

        if short_url.startswith("http"):
            await bot.send_message(
                chat_id=chat_id,
                text=f'{tg_emoji(Emoji.LINK, "🔗")} <b>Короткая ссылка:</b>\n\n{short_url}',
                parse_mode="HTML",
                business_connection_id=biz_id,
            )
        else:
            raise ValueError("bad response")
    except Exception:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=f'{tg_emoji(Emoji.CROSS, "❌")} не получилось сократить ссылку',
                parse_mode="HTML",
                business_connection_id=biz_id,
            )
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════
# Callback handlers
# ══════════════════════════════════════════════════════════════════


@router.callback_query(lambda c: c.data and c.data.startswith("sc:"))
async def on_sc_callback(callback: CallbackQuery, bot: Bot) -> None:
    """Handle SoundCloud pick/cancel inline button presses."""
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


@router.callback_query(lambda c: c.data and c.data.startswith("gift:"))
async def on_gift_callback(callback: CallbackQuery, bot: Bot) -> None:
    """Handle gift selection callback."""
    parts = callback.data.split(":")

    if parts[1] == "cancel":
        await callback.answer("отменено")
        try:
            await callback.message.delete()
        except Exception:
            pass
        return

    username = parts[1]
    gift_id = parts[2]

    try:
        await bot.send_gift(
            gift_id=gift_id,
            user_id=callback.from_user.id,
        )
        await callback.answer("подарок отправлен!")
        try:
            await callback.message.edit_text(
                f'{tg_emoji(Emoji.CHECK, "✅")} подарок отправлен @{username}!',
                parse_mode="HTML",
            )
        except Exception:
            pass
    except Exception as e:
        error_msg = str(e)
        if "chat not found" in error_msg.lower() or "user not found" in error_msg.lower():
            await callback.answer("пользователь не найден или бот не может отправить подарок")
        elif "not enough" in error_msg.lower() or "balance" in error_msg.lower():
            await callback.answer("недостаточно звёзд для отправки подарка")
        else:
            logger.exception("Failed to send gift")
            await callback.answer(f"ошибка: {error_msg[:80]}")


@router.callback_query(lambda c: c.data and c.data.startswith("calc:"))
async def on_calc_callback(callback: CallbackQuery, bot: Bot) -> None:
    """Handle calculator mode selection."""
    parts = callback.data.split(":")
    action = parts[1]

    if action == "cancel":
        owner_id = int(parts[2])
        chat_id = int(parts[3])
        key = (owner_id, chat_id)
        _cmd_state.pop(key, None)
        await callback.answer("отменено")
        try:
            await callback.message.delete()
        except Exception:
            pass
        return

    if action == "math":
        owner_id = int(parts[2])
        chat_id = int(parts[3])
        key = (owner_id, chat_id)
        state = _cmd_state.get(key)
        biz_id = state["data"]["biz_id"] if state else ""

        # Delete the menu message
        try:
            await callback.message.delete()
        except Exception:
            pass

        try:
            msg = await bot.send_message(
                chat_id=chat_id,
                text=(
                    f'{tg_emoji(Emoji.CODE, "🔢")} <b>Математический калькулятор</b>\n\n'
                    f'напиши выражение\n'
                    f'<i>например: 2+2, 100*15, (50+30)/2</i>'
                ),
                parse_mode="HTML",
                business_connection_id=biz_id,
            )
            _cmd_state[key] = {"step": "calc_math_waiting", "data": {"biz_id": biz_id, "prompt_msg_id": msg.message_id}}
        except Exception:
            _cmd_state.pop(key, None)
        await callback.answer()
        return

    if action == "currency":
        owner_id = int(parts[2])
        chat_id = int(parts[3])
        key = (owner_id, chat_id)
        state = _cmd_state.get(key)
        biz_id = state["data"]["biz_id"] if state else ""

        try:
            await callback.message.delete()
        except Exception:
            pass

        # Show currency category buttons for "FROM" currency
        buttons = _currency_category_buttons(owner_id, chat_id, "from")
        try:
            msg = await bot.send_message(
                chat_id=chat_id,
                text=(
                    f'<b>{tg_emoji(Emoji.MONEY, "💱")} Конвертер валют</b>\n\n'
                    f'из какой валюты конвертируем'
                ),
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
                business_connection_id=biz_id,
            )
            _cmd_state[key] = {"step": "calc_currency_from", "data": {"biz_id": biz_id, "menu_msg_id": msg.message_id}}
        except Exception:
            _cmd_state.pop(key, None)
        await callback.answer()
        return


@router.callback_query(lambda c: c.data and c.data.startswith("cur:"))
async def on_currency_callback(callback: CallbackQuery, bot: Bot) -> None:
    """Handle currency converter inline button navigation."""
    parts = callback.data.split(":")
    if len(parts) < 5:
        await callback.answer()
        return

    prefix = parts[1]  # "from", "to", or "cancel"
    value = parts[2]
    owner_id = int(parts[3])
    chat_id = int(parts[4])
    key = (owner_id, chat_id)

    state = _cmd_state.get(key)
    biz_id = state["data"]["biz_id"] if state else ""

    if prefix == "cancel":
        _cmd_state.pop(key, None)
        await callback.answer("отменено")
        try:
            await callback.message.delete()
        except Exception:
            pass
        return

    # Category selection (main/crypto/other) -> show currencies
    if value in ("main", "crypto", "other"):
        currencies = CATEGORY_MAP[value]
        buttons = _currency_buttons(currencies, owner_id, chat_id, prefix)

        direction = "из какой валюты" if prefix == "from" else "в какую валюту"
        extra = ""
        if prefix == "to" and state:
            from_cur = state["data"].get("from_cur", "")
            amount = state["data"].get("amount", 0)
            extra = f"\n<code>{amount:g} {from_cur}</code> → ..."

        try:
            await callback.message.edit_text(
                text=f'<b>{tg_emoji(Emoji.MONEY, "💱")} {direction}</b>{extra}',
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            )
        except Exception:
            pass
        await callback.answer()
        return

    # "back" -> go back to category selection
    if value == "back":
        buttons = _currency_category_buttons(owner_id, chat_id, prefix)
        direction = "из какой валюты конвертируем" if prefix == "from" else "в какую валюту конвертируем"
        extra = ""
        if prefix == "to" and state:
            from_cur = state["data"].get("from_cur", "")
            amount = state["data"].get("amount", 0)
            extra = f"\n<code>{amount:g} {from_cur}</code> → ..."

        try:
            await callback.message.edit_text(
                text=f'<b>{tg_emoji(Emoji.MONEY, "💱")} Конвертер валют</b>\n\n{direction}{extra}',
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            )
        except Exception:
            pass
        await callback.answer()
        return

    # Currency selected
    currency = value.upper()

    if prefix == "from":
        # FROM currency selected -> ask for amount
        try:
            await callback.message.edit_text(
                text=(
                    f'<b>{tg_emoji(Emoji.MONEY, "💱")} Выбрано: {currency}</b>\n\n'
                    f'напиши сумму\n'
                    f'<i>например: 100, 0.5, 1500</i>'
                ),
                parse_mode="HTML",
            )
        except Exception:
            pass
        _cmd_state[key] = {
            "step": "calc_currency_amount",
            "data": {"biz_id": biz_id, "from_cur": currency, "prompt_msg_id": callback.message.message_id},
        }
        await callback.answer(f"выбрано: {currency}")
        return

    if prefix == "to":
        # TO currency selected -> do the conversion
        if not state:
            await callback.answer("истекло")
            return
        from_cur = state["data"].get("from_cur", "USD")
        amount = state["data"].get("amount", 0)
        _cmd_state.pop(key, None)

        try:
            await callback.message.edit_text(
                text=f'{tg_emoji(Emoji.LOADING, "🔄")} считаю курс...',
                parse_mode="HTML",
            )
        except Exception:
            pass

        await _do_currency_convert(bot, biz_id, chat_id, from_cur, currency, amount, callback.message.message_id)
        await callback.answer()
        return
