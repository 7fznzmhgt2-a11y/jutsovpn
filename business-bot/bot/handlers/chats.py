from aiogram import Bot, Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.database import Database
from bot.emoji import Emoji, tg_emoji
from bot.keyboards import chat_info_kb, chats_add_cancel_kb, chats_kb, main_menu_kb

router = Router()


class ChatStates(StatesGroup):
    waiting_for_chat_id = State()


@router.callback_query(F.data == "menu:chats")
async def show_chats(callback: CallbackQuery, db: Database) -> None:
    user_id = callback.from_user.id
    chats = await db.get_monitored_chats(user_id)

    if not chats:
        text = (
            f"<b>{tg_emoji(Emoji.EYE, '👁')} Чаты для чтения</b>\n\n"
            f"{tg_emoji(Emoji.INFO, 'ℹ')} Нет отслеживаемых чатов.\n\n"
            f"Добавьте чаты, которые бот будет читать и в которых "
            f"будет отвечать за вас."
        )
    else:
        text = (
            f"<b>{tg_emoji(Emoji.EYE, '👁')} Чаты для чтения</b>\n\n"
            f"{tg_emoji(Emoji.INFO, 'ℹ')} Список чатов ({len(chats)}):"
        )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=chats_kb(chats),
    )
    await callback.answer()


@router.callback_query(F.data == "chats:add")
async def chats_add(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text(
        f"<b>{tg_emoji(Emoji.ADD_TEXT, '🔡')} Добавить чат</b>\n\n"
        f"{tg_emoji(Emoji.INFO, 'ℹ')} Отправьте:\n"
        f"1. Перешлите любое сообщение из чата\n"
        f"2. Или ID чата и название через пробел\n"
        f"3. Или @username чата\n\n"
        f"<blockquote>Бот автоматически добавляет все бизнес-чаты. "
        f"Группы тоже будут читаться если добавить бота туда.</blockquote>",
        parse_mode="HTML",
        reply_markup=chats_add_cancel_kb(),
    )
    await state.set_state(ChatStates.waiting_for_chat_id)
    await callback.answer()


@router.message(ChatStates.waiting_for_chat_id)
async def chat_id_received(message: Message, state: FSMContext, db: Database, bot: Bot) -> None:
    # Handle forwarded messages
    if message.forward_from_chat:
        chat_id = message.forward_from_chat.id
        chat_name = message.forward_from_chat.title or message.forward_from_chat.first_name or str(chat_id)
        await db.add_monitored_chat(message.from_user.id, chat_id, chat_name)
        await state.clear()
        await message.answer(
            f"{tg_emoji(Emoji.CHECK, '✅')} Чат <b>{chat_name}</b> добавлен",
            parse_mode="HTML",
            reply_markup=main_menu_kb(),
        )
        return

    if message.forward_from:
        chat_id = message.forward_from.id
        chat_name = message.forward_from.first_name or str(chat_id)
        if message.forward_from.last_name:
            chat_name += " " + message.forward_from.last_name
        await db.add_monitored_chat(message.from_user.id, chat_id, chat_name)
        await state.clear()
        await message.answer(
            f"{tg_emoji(Emoji.CHECK, '✅')} Чат <b>{chat_name}</b> добавлен",
            parse_mode="HTML",
            reply_markup=main_menu_kb(),
        )
        return

    text = (message.text or "").strip()
    if not text:
        await message.answer(
            f"{tg_emoji(Emoji.CROSS, '❌')} Отправьте ID чата или перешлите сообщение",
            parse_mode="HTML",
            reply_markup=chats_add_cancel_kb(),
        )
        return

    # Handle @username
    if text.startswith("@"):
        try:
            chat_obj = await bot.get_chat(text)
            chat_id = chat_obj.id
            chat_name = chat_obj.title or chat_obj.first_name or text
            await db.add_monitored_chat(message.from_user.id, chat_id, chat_name)
            await state.clear()
            await message.answer(
                f"{tg_emoji(Emoji.CHECK, '✅')} Чат <b>{chat_name}</b> добавлен",
                parse_mode="HTML",
                reply_markup=main_menu_kb(),
            )
            return
        except Exception:
            await message.answer(
                f"{tg_emoji(Emoji.CROSS, '❌')} Не удалось найти чат {text}. "
                f"Попробуйте переслать сообщение из чата или отправить ID",
                parse_mode="HTML",
                reply_markup=chats_add_cancel_kb(),
            )
            return

    # Handle numeric ID
    parts = text.split(maxsplit=1)
    try:
        chat_id = int(parts[0])
    except ValueError:
        await message.answer(
            f"{tg_emoji(Emoji.CROSS, '❌')} ID чата должен быть числом или @username",
            parse_mode="HTML",
            reply_markup=chats_add_cancel_kb(),
        )
        return

    chat_name = parts[1] if len(parts) > 1 else str(chat_id)
    await db.add_monitored_chat(message.from_user.id, chat_id, chat_name)
    await state.clear()

    await message.answer(
        f"{tg_emoji(Emoji.CHECK, '✅')} Чат <b>{chat_name}</b> добавлен",
        parse_mode="HTML",
        reply_markup=main_menu_kb(),
    )


@router.callback_query(F.data.startswith("chats:toggle:"))
async def chats_toggle(callback: CallbackQuery, db: Database) -> None:
    chat_id = int(callback.data.split(":")[-1])
    new_state = await db.toggle_chat_auto_reply(callback.from_user.id, chat_id)
    status = "включён" if new_state else "выключен"
    await callback.answer(f"Авто-ответ {status}", show_alert=False)

    chats = await db.get_monitored_chats(callback.from_user.id)
    await callback.message.edit_reply_markup(reply_markup=chats_kb(chats))


@router.callback_query(F.data.startswith("chats:info:"))
async def chats_info(callback: CallbackQuery, db: Database) -> None:
    chat_id = int(callback.data.split(":")[-1])
    chats = await db.get_monitored_chats(callback.from_user.id)
    chat = next((c for c in chats if c["chat_id"] == chat_id), None)

    if chat:
        name = chat.get("chat_name") or str(chat_id)
        auto = "ВКЛ" if chat.get("auto_reply") else "ВЫКЛ"
        text = (
            f"<b>{tg_emoji(Emoji.PROFILE, '👤')} Чат: {name}</b>\n\n"
            f"ID: <code>{chat_id}</code>\n"
            f"Авто-ответ: {auto}"
        )
    else:
        text = f"{tg_emoji(Emoji.CROSS, '❌')} Чат не найден."

    await callback.message.edit_text(
        text, parse_mode="HTML", reply_markup=chat_info_kb(chat_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("chats:remove:"))
async def chats_remove(callback: CallbackQuery, db: Database) -> None:
    chat_id = int(callback.data.split(":")[-1])
    await db.remove_monitored_chat(callback.from_user.id, chat_id)
    await callback.message.edit_text(
        f"{tg_emoji(Emoji.TRASH, '🗑')} Чат {chat_id} удалён.",
        parse_mode="HTML",
        reply_markup=main_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "chats:cancel")
async def chats_cancel(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await state.clear()
    chats = await db.get_monitored_chats(callback.from_user.id)
    await callback.message.edit_text(
        f"<b>{tg_emoji(Emoji.EYE, '👁')} Чаты для чтения</b>",
        parse_mode="HTML",
        reply_markup=chats_kb(chats),
    )
    await callback.answer()
