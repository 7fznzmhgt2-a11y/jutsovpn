from aiogram import Router, F
from aiogram.types import CallbackQuery

from bot.database import Database
from bot.emoji import Emoji, tg_emoji
from bot.keyboards import main_menu_kb

router = Router()


@router.callback_query(F.data == "menu:main")
async def menu_main(callback: CallbackQuery, db: Database) -> None:
    user = await db.get_user(callback.from_user.id)
    connected = bool(user and user["is_connected"])

    if connected:
        text = (
            f"<b>{tg_emoji(Emoji.BOT, '🤖')} Бизнес-Помощник</b>\n\n"
            f"{tg_emoji(Emoji.CHECK, '✅')} Бизнес-бот подключён\n\n"
            f"{tg_emoji(Emoji.SETTINGS, '⚙')} Выберите раздел:"
        )
    else:
        text = (
            f"<b>{tg_emoji(Emoji.BOT, '🤖')} Бизнес-Помощник</b>\n\n"
            f"{tg_emoji(Emoji.CROSS, '❌')} Бизнес-бот не подключён\n\n"
            f"Подключите бота в настройках Telegram Business."
        )
    await callback.message.edit_text(
        text, parse_mode="HTML", reply_markup=main_menu_kb()
    )
    await callback.answer()
