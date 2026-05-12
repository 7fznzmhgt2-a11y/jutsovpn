from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.config import DEFAULT_PROMPT
from bot.database import Database
from bot.emoji import Emoji, tg_emoji
from bot.keyboards import main_menu_kb, prompt_cancel_kb, prompt_kb

router = Router()


class PromptStates(StatesGroup):
    waiting_for_prompt = State()


@router.callback_query(F.data == "menu:prompt")
async def show_prompt(callback: CallbackQuery, db: Database) -> None:
    user_id = callback.from_user.id
    prompt = await db.get_user_field(user_id, "prompt", DEFAULT_PROMPT)

    await callback.message.edit_text(
        f"<b>{tg_emoji(Emoji.WRITE, '✍')} Предложение (системный промпт)</b>\n\n"
        f"<blockquote>{_escape(str(prompt))}</blockquote>\n\n"
        f"{tg_emoji(Emoji.INFO, 'ℹ')} Бот будет опираться на этот текст "
        f"при ответах в ваших чатах.",
        parse_mode="HTML",
        reply_markup=prompt_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "prompt:edit")
async def prompt_edit(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text(
        f"<b>{tg_emoji(Emoji.PENCIL, '🖋')} Введите новый промпт:</b>\n\n"
        f"{tg_emoji(Emoji.INFO, 'ℹ')} Отправьте текст, который будет "
        f"определять стиль ответов бота.",
        parse_mode="HTML",
        reply_markup=prompt_cancel_kb(),
    )
    await state.set_state(PromptStates.waiting_for_prompt)
    await callback.answer()


@router.message(PromptStates.waiting_for_prompt)
async def prompt_received(message: Message, state: FSMContext, db: Database) -> None:
    new_prompt = message.text or ""
    if not new_prompt.strip():
        await message.answer(
            f"{tg_emoji(Emoji.CROSS, '❌')} Промпт не может быть пустым. Попробуйте ещё раз.",
            parse_mode="HTML",
            reply_markup=prompt_cancel_kb(),
        )
        return

    await db.set_user_field(message.from_user.id, "prompt", new_prompt.strip())
    await state.clear()
    await message.answer(
        f"{tg_emoji(Emoji.CHECK, '✅')} Промпт обновлён!\n\n"
        f"<blockquote>{_escape(new_prompt.strip()[:500])}</blockquote>",
        parse_mode="HTML",
        reply_markup=main_menu_kb(),
    )


@router.callback_query(F.data == "prompt:reset")
async def prompt_reset(callback: CallbackQuery, db: Database) -> None:
    await db.set_user_field(callback.from_user.id, "prompt", DEFAULT_PROMPT)
    await callback.message.edit_text(
        f"{tg_emoji(Emoji.CHECK, '✅')} Промпт сброшен до стандартного.\n\n"
        f"<blockquote>{_escape(DEFAULT_PROMPT)}</blockquote>",
        parse_mode="HTML",
        reply_markup=main_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "prompt:cancel")
async def prompt_cancel(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await state.clear()
    prompt = await db.get_user_field(callback.from_user.id, "prompt", DEFAULT_PROMPT)
    await callback.message.edit_text(
        f"<b>{tg_emoji(Emoji.WRITE, '✍')} Предложение (системный промпт)</b>\n\n"
        f"<blockquote>{_escape(str(prompt))}</blockquote>",
        parse_mode="HTML",
        reply_markup=prompt_kb(),
    )
    await callback.answer()


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
