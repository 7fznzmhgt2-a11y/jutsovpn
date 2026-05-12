from aiogram import Dispatcher

from bot.handlers import apikey, business, chats, history, knowledge, menu, prompt, settings, start


def register_all_handlers(dp: Dispatcher) -> None:
    dp.include_router(start.router)
    dp.include_router(menu.router)
    dp.include_router(prompt.router)
    dp.include_router(apikey.router)
    dp.include_router(history.router)
    dp.include_router(chats.router)
    dp.include_router(knowledge.router)
    dp.include_router(settings.router)
    # business router must be last — it catches all business_message events
    dp.include_router(business.router)
