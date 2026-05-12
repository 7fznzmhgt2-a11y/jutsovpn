from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.config import DEFAULT_API_URL, DEFAULT_MODEL, FEATURED_MODELS
from bot.database import Database
from bot.emoji import Emoji, tg_emoji
from bot.keyboards import (
    main_menu_kb,
    model_picker_kb,
    model_search_cancel_kb,
    settings_cancel_kb,
    settings_kb,
)
from bot.services.openrouter import fetch_models, get_featured_models, search_models

router = Router()


class SettingsStates(StatesGroup):
    waiting_for_model = State()
    waiting_for_model_search = State()
    waiting_for_api_url = State()


@router.callback_query(F.data == "menu:settings")
async def show_settings(callback: CallbackQuery, db: Database) -> None:
    user_id = callback.from_user.id
    user = await db.get_user(user_id)
    if not user:
        await db.upsert_user(user_id)
        user = await db.get_user(user_id)

    auto_reply = bool(user["auto_reply"])
    model = user["model"] or DEFAULT_MODEL
    api_url = user["api_url"] or DEFAULT_API_URL
    connected = bool(user["is_connected"])

    conn_status = (
        f"{tg_emoji(Emoji.CHECK, '✅')} Подключён"
        if connected
        else f"{tg_emoji(Emoji.CROSS, '❌')} Не подключён"
    )

    await callback.message.edit_text(
        f"<b>{tg_emoji(Emoji.SETTINGS, '⚙')} Настройки</b>\n\n"
        f"{tg_emoji(Emoji.BOT, '🤖')} Модель: <code>{model}</code>\n"
        f"{tg_emoji(Emoji.LINK, '🔗')} API URL: <code>{api_url}</code>\n"
        f"{tg_emoji(Emoji.PERSON_CHECK, '👤')} Бизнес: {conn_status}",
        parse_mode="HTML",
        reply_markup=settings_kb(auto_reply),
    )
    await callback.answer()


@router.callback_query(F.data == "settings:toggle_reply")
async def toggle_reply(callback: CallbackQuery, db: Database) -> None:
    user_id = callback.from_user.id
    current = await db.get_user_field(user_id, "auto_reply", 1)
    new_val = 0 if current else 1
    await db.set_user_field(user_id, "auto_reply", new_val)

    status = "включён" if new_val else "выключен"
    await callback.answer(f"Авто-ответ {status}", show_alert=False)

    user = await db.get_user(user_id)
    model = user["model"] or DEFAULT_MODEL
    api_url = user["api_url"] or DEFAULT_API_URL
    connected = bool(user["is_connected"])
    conn_status = (
        f"{tg_emoji(Emoji.CHECK, '✅')} Подключён"
        if connected
        else f"{tg_emoji(Emoji.CROSS, '❌')} Не подключён"
    )

    await callback.message.edit_text(
        f"<b>{tg_emoji(Emoji.SETTINGS, '⚙')} Настройки</b>\n\n"
        f"{tg_emoji(Emoji.BOT, '🤖')} Модель: <code>{model}</code>\n"
        f"{tg_emoji(Emoji.LINK, '🔗')} API URL: <code>{api_url}</code>\n"
        f"{tg_emoji(Emoji.PERSON_CHECK, '👤')} Бизнес: {conn_status}",
        parse_mode="HTML",
        reply_markup=settings_kb(bool(new_val)),
    )


# ── Model picker (OpenRouter) ─────────────────────────────────────

@router.callback_query(F.data == "settings:model")
async def settings_model(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    user = await db.get_user(callback.from_user.id)
    api_key = (user["api_key"] if user else "") or ""

    if api_key:
        all_models = await fetch_models(api_key)
        if all_models:
            featured = get_featured_models(all_models, FEATURED_MODELS)
            display = featured + [m for m in all_models if m not in featured]
            await state.update_data(models=[m["id"] for m in display], all_models=display)
            await callback.message.edit_text(
                f"<b>{tg_emoji(Emoji.BOT, '🤖')} Выберите модель AI</b>\n\n"
                f"{tg_emoji(Emoji.INFO, 'ℹ')} Всего доступно: <b>{len(all_models)}</b> моделей\n"
                f"Текущая: <code>{user['model'] or DEFAULT_MODEL}</code>",
                parse_mode="HTML",
                reply_markup=model_picker_kb(display, page=0),
            )
            await callback.answer()
            return

    # Fallback: manual input
    await callback.message.edit_text(
        f"<b>{tg_emoji(Emoji.BOT, '🤖')} Модель AI</b>\n\n"
        f"{tg_emoji(Emoji.INFO, 'ℹ')} Отправьте название модели.\n\n"
        f"<blockquote>Примеры: <code>google/gemini-2.5-flash</code>, "
        f"<code>openai/gpt-4o</code>, <code>anthropic/claude-sonnet-4</code></blockquote>",
        parse_mode="HTML",
        reply_markup=settings_cancel_kb(),
    )
    await state.set_state(SettingsStates.waiting_for_model)
    await callback.answer()


@router.callback_query(F.data.startswith("model:page:"))
async def model_page(callback: CallbackQuery, state: FSMContext) -> None:
    page = int(callback.data.split(":")[-1])
    data = await state.get_data()
    all_models = data.get("all_models", [])

    if not all_models:
        await callback.answer("Модели не загружены")
        return

    await callback.message.edit_reply_markup(
        reply_markup=model_picker_kb(all_models, page=page),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("model:pick:"))
async def model_pick(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    model_id = callback.data.replace("model:pick:", "")
    await db.set_user_field(callback.from_user.id, "model", model_id)
    await state.clear()
    await callback.message.edit_text(
        f"{tg_emoji(Emoji.CHECK, '✅')} Модель изменена на <code>{model_id}</code>",
        parse_mode="HTML",
        reply_markup=main_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "model:search")
async def model_search_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text(
        f"<b>{tg_emoji(Emoji.EYE, '🔍')} Поиск модели</b>\n\n"
        f"{tg_emoji(Emoji.INFO, 'ℹ')} Отправьте часть названия модели для поиска.\n\n"
        f"<blockquote>Примеры: <code>gemini</code>, <code>gpt</code>, "
        f"<code>claude</code>, <code>llama</code></blockquote>",
        parse_mode="HTML",
        reply_markup=model_search_cancel_kb(),
    )
    await state.set_state(SettingsStates.waiting_for_model_search)
    await callback.answer()


@router.message(SettingsStates.waiting_for_model_search)
async def model_search_received(message: Message, state: FSMContext, db: Database) -> None:
    query = (message.text or "").strip()
    if not query:
        return

    user = await db.get_user(message.from_user.id)
    api_key = (user["api_key"] if user else "") or ""
    if not api_key:
        await message.answer(
            f"{tg_emoji(Emoji.CROSS, '❌')} Установите API ключ для поиска моделей.",
            parse_mode="HTML",
            reply_markup=main_menu_kb(),
        )
        await state.clear()
        return

    results = await search_models(api_key, query)
    if not results:
        await message.answer(
            f"{tg_emoji(Emoji.CROSS, '❌')} Моделей по запросу <code>{query}</code> не найдено.",
            parse_mode="HTML",
            reply_markup=model_search_cancel_kb(),
        )
        return

    await state.update_data(all_models=results)
    await state.set_state(None)
    await message.answer(
        f"<b>{tg_emoji(Emoji.CHECK, '✅')} Найдено: {len(results)} моделей</b>\n"
        f"Запрос: <code>{query}</code>",
        parse_mode="HTML",
        reply_markup=model_picker_kb(results, page=0),
    )


@router.message(SettingsStates.waiting_for_model)
async def model_received(message: Message, state: FSMContext, db: Database) -> None:
    model = (message.text or "").strip()
    if not model:
        await message.answer(
            f"{tg_emoji(Emoji.CROSS, '❌')} Название модели не может быть пустым.",
            parse_mode="HTML",
            reply_markup=settings_cancel_kb(),
        )
        return

    await db.set_user_field(message.from_user.id, "model", model)
    await state.clear()
    await message.answer(
        f"{tg_emoji(Emoji.CHECK, '✅')} Модель изменена на <code>{model}</code>",
        parse_mode="HTML",
        reply_markup=main_menu_kb(),
    )


# ── API URL ────────────────────────────────────────────────────────

@router.callback_query(F.data == "settings:api_url")
async def settings_api_url(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text(
        f"<b>{tg_emoji(Emoji.LINK, '🔗')} API URL</b>\n\n"
        f"{tg_emoji(Emoji.INFO, 'ℹ')} Отправьте URL API "
        f"(OpenAI-совместимый).\n\n"
        f"<blockquote>По умолчанию: <code>{DEFAULT_API_URL}</code></blockquote>",
        parse_mode="HTML",
        reply_markup=settings_cancel_kb(),
    )
    await state.set_state(SettingsStates.waiting_for_api_url)
    await callback.answer()


@router.message(SettingsStates.waiting_for_api_url)
async def api_url_received(message: Message, state: FSMContext, db: Database) -> None:
    url = (message.text or "").strip()
    if not url.startswith("http"):
        await message.answer(
            f"{tg_emoji(Emoji.CROSS, '❌')} URL должен начинаться с http:// или https://",
            parse_mode="HTML",
            reply_markup=settings_cancel_kb(),
        )
        return

    await db.set_user_field(message.from_user.id, "api_url", url)
    await state.clear()
    await message.answer(
        f"{tg_emoji(Emoji.CHECK, '✅')} API URL изменён на <code>{url}</code>",
        parse_mode="HTML",
        reply_markup=main_menu_kb(),
    )


# ── Disconnect ─────────────────────────────────────────────────────

@router.callback_query(F.data == "settings:disconnect")
async def settings_disconnect(callback: CallbackQuery, db: Database) -> None:
    await db.set_business_connected(callback.from_user.id, "", connected=False)
    await callback.message.edit_text(
        f"{tg_emoji(Emoji.PERSON_CROSS, '👤')} Бизнес-бот отключён.\n\n"
        f"{tg_emoji(Emoji.INFO, 'ℹ')} Для повторного подключения "
        f"добавьте бота в настройках Telegram Business.",
        parse_mode="HTML",
        reply_markup=main_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "settings:cancel")
async def settings_cancel(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await state.clear()
    user = await db.get_user(callback.from_user.id)
    auto_reply = bool(user["auto_reply"]) if user else True
    model = (user["model"] if user else "") or DEFAULT_MODEL
    api_url = (user["api_url"] if user else "") or DEFAULT_API_URL
    connected = bool(user["is_connected"]) if user else False
    conn_status = (
        f"{tg_emoji(Emoji.CHECK, '✅')} Подключён"
        if connected
        else f"{tg_emoji(Emoji.CROSS, '❌')} Не подключён"
    )

    await callback.message.edit_text(
        f"<b>{tg_emoji(Emoji.SETTINGS, '⚙')} Настройки</b>\n\n"
        f"{tg_emoji(Emoji.BOT, '🤖')} Модель: <code>{model}</code>\n"
        f"{tg_emoji(Emoji.LINK, '🔗')} API URL: <code>{api_url}</code>\n"
        f"{tg_emoji(Emoji.PERSON_CHECK, '👤')} Бизнес: {conn_status}",
        parse_mode="HTML",
        reply_markup=settings_kb(auto_reply),
    )
    await callback.answer()
