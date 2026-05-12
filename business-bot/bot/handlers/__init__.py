from aiogram import Dispatcher

from bot.handlers import business, start


def register_all_handlers(dp: Dispatcher) -> None:
    dp.include_router(start.router)
    # business router catches all business_message events
    dp.include_router(business.router)
