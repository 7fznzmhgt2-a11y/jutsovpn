from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.database import Database
from bot.emoji import Emoji, tg_emoji
from bot.keyboards import apikey_cancel_kb, apikey_kb, main_menu_kb

router = Router()


class ApiKeyStates(StatesGroup):
    waiting_for_key = State()


@router.callback_query(F.data == "menu:apikey")
async def show_apikey(callback: CallbackQuery, db: Database) -> None:
    user_id = callback.from_user.id
    key = str(await db.get_user_field(user_id, "api_key", ""))
    has_key = bool(key.strip())

    if has_key:
        masked = key[:8] + "..." + key[-4:]
        status = f"{tg_emoji(Emoji.CHECK, '✅')} Ключ установлен: <code>{masked}</code>"
    else:
        status = f"{tg_emoji(Emoji.CROSS, '❌')} Ключ не установлен"

    await callback.message.edit_text(
        f"<b>{tg_emoji(Emoji.LOCK_CLOSED, '🔒')} API ключ</b>\n\n"
        f"{status}\n\n"
        f"{tg_emoji(Emoji.INFO, 'ℹ')} API ключ нужен для подключения к AI "
        f"(OpenAI или совместимый сервис).",
        parse_mode="HTML",
        reply_markup=apikey_kb(has_key),
    )
    await callback.answer()


@router.callback_query(F.data == "apikey:set")
async def apikey_set(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text(
        f"<b>{tg_emoji(Emoji.LOCK_OPEN, '🔓')} Отправьте API ключ:</b>\n\n"
        f"{tg_emoji(Emoji.INFO, 'ℹ')} Ключ будет сохранён и использован "
        f"для AI ответов.",
        parse_mode="HTML",
        reply_markup=apikey_cancel_kb(),
    )
    await state.set_state(ApiKeyStates.waiting_for_key)
    await callback.answer()


@router.message(ApiKeyStates.waiting_for_key)
async def apikey_received(message: Message, state: FSMContext, db: Database) -> None:
    key = (message.text or "").strip()
    if not key:
        await message.answer(
            f"{tg_emoji(Emoji.CROSS, '❌')} Ключ не может быть пустым.",
            parse_mode="HTML",
            reply_markup=apikey_cancel_kb(),
        )
        return

    await db.set_user_field(message.from_user.id, "api_key", key)
    await state.clear()

    # Delete user's message with the key for security
    try:
        await message.delete()
    except Exception:
        pass

    masked = key[:8] + "..." + key[-4:]
    await message.answer(
        f"{tg_emoji(Emoji.CHECK, '✅')} API ключ сохранён!\n\n"
        f"<code>{masked}</code>",
        parse_mode="HTML",
        reply_markup=main_menu_kb(),
    )


@router.callback_query(F.data == "apikey:delete")
async def apikey_delete(callback: CallbackQuery, db: Database) -> None:
    await db.set_user_field(callback.from_user.id, "api_key", "")
    await callback.message.edit_text(
        f"{tg_emoji(Emoji.TRASH, '🗑')} API ключ удалён.",
        parse_mode="HTML",
        reply_markup=main_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "apikey:cancel")
async def apikey_cancel(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await state.clear()
    key = str(await db.get_user_field(callback.from_user.id, "api_key", ""))
    has_key = bool(key.strip())
    if has_key:
        masked = key[:8] + "..." + key[-4:]
        status = f"{tg_emoji(Emoji.CHECK, '✅')} Ключ установлен: <code>{masked}</code>"
    else:
        status = f"{tg_emoji(Emoji.CROSS, '❌')} Ключ не установлен"

    await callback.message.edit_text(
        f"<b>{tg_emoji(Emoji.LOCK_CLOSED, '🔒')} API ключ</b>\n\n{status}",
        parse_mode="HTML",
        reply_markup=apikey_kb(has_key),
    )
    await callback.answer()
