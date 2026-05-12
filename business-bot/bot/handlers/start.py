from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import BusinessConnection, Message

from bot.database import Database
from bot.emoji import Emoji, tg_emoji
from bot.keyboards import main_menu_kb

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, db: Database) -> None:
    user_id = message.from_user.id
    await db.upsert_user(user_id)
    user = await db.get_user(user_id)

    if user and user["is_connected"]:
        await _show_main_menu(message, connected=True)
    else:
        await message.answer(
            f"<b>{tg_emoji(Emoji.BOT, '🤖')} Бизнес-Помощник</b>\n\n"
            f"{tg_emoji(Emoji.INFO, 'ℹ')} Чтобы начать, добавьте бота "
            f"в <b>Telegram Business</b>:\n\n"
            f"<blockquote>"
            f"1. Откройте <b>Настройки Telegram</b>\n"
            f"2. Перейдите в <b>Telegram Business</b>\n"
            f"3. Найдите раздел <b>Чат-боты</b>\n"
            f"4. Добавьте этого бота"
            f"</blockquote>\n\n"
            f"{tg_emoji(Emoji.BELL, '🔔')} После подключения бот автоматически "
            f"откроет главное меню.",
            parse_mode="HTML",
        )


@router.business_connection()
async def on_business_connection(event: BusinessConnection, db: Database) -> None:
    user_id = event.user.id
    await db.upsert_user(user_id)

    if event.is_enabled and not event.is_deleted:
        await db.set_business_connected(user_id, event.id, connected=True)
        from aiogram import Bot
        bot: Bot = event.bot
        await bot.send_message(
            chat_id=event.user_chat_id,
            text=(
                f"<b>{tg_emoji(Emoji.PARTY, '🎉')} Бизнес-бот подключён!</b>\n\n"
                f"{tg_emoji(Emoji.CHECK, '✅')} Теперь я могу читать ваши чаты "
                f"и отвечать как вы.\n\n"
                f"{tg_emoji(Emoji.SETTINGS, '⚙')} Настройте бота через меню ниже."
            ),
            parse_mode="HTML",
            reply_markup=main_menu_kb(),
        )
    else:
        await db.set_business_connected(user_id, "", connected=False)


async def _show_main_menu(message: Message, connected: bool = True) -> None:
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
    await message.answer(text, parse_mode="HTML", reply_markup=main_menu_kb())
