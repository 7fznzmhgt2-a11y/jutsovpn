from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.emoji import Emoji


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Предложение",
            callback_data="menu:prompt",
            icon_custom_emoji_id=Emoji.WRITE,
        )],
        [InlineKeyboardButton(
            text="API ключ",
            callback_data="menu:apikey",
            icon_custom_emoji_id=Emoji.LOCK_CLOSED,
        )],
        [InlineKeyboardButton(
            text="История",
            callback_data="menu:history",
            icon_custom_emoji_id=Emoji.STATS,
        )],
        [InlineKeyboardButton(
            text="Чаты",
            callback_data="menu:chats",
            icon_custom_emoji_id=Emoji.EYE,
        )],
        [InlineKeyboardButton(
            text="Что узнал",
            callback_data="menu:knowledge",
            icon_custom_emoji_id=Emoji.GROWTH,
        )],
        [InlineKeyboardButton(
            text="Настройки",
            callback_data="menu:settings",
            icon_custom_emoji_id=Emoji.SETTINGS,
        )],
    ])


def back_to_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="◁ Назад",
            callback_data="menu:main",
        )],
    ])


# ── Prompt ─────────────────────────────────────────────────────────

def prompt_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Изменить",
            callback_data="prompt:edit",
            icon_custom_emoji_id=Emoji.PENCIL,
        )],
        [InlineKeyboardButton(
            text="Сбросить",
            callback_data="prompt:reset",
            icon_custom_emoji_id=Emoji.TRASH,
        )],
        [InlineKeyboardButton(
            text="◁ Назад",
            callback_data="menu:main",
        )],
    ])


def prompt_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Отмена",
            callback_data="prompt:cancel",
            icon_custom_emoji_id=Emoji.CROSS,
        )],
    ])


# ── API key ────────────────────────────────────────────────────────

def apikey_kb(has_key: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(
            text="Установить" if not has_key else "Изменить",
            callback_data="apikey:set",
            icon_custom_emoji_id=Emoji.PENCIL,
        )],
    ]
    if has_key:
        rows.append([InlineKeyboardButton(
            text="Удалить",
            callback_data="apikey:delete",
            icon_custom_emoji_id=Emoji.TRASH,
        )])
    rows.append([InlineKeyboardButton(
        text="◁ Назад",
        callback_data="menu:main",
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def apikey_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Отмена",
            callback_data="apikey:cancel",
            icon_custom_emoji_id=Emoji.CROSS,
        )],
    ])


# ── History ────────────────────────────────────────────────────────

def history_kb(chats: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for chat in chats:
        chat_id = chat["chat_id"]
        count = chat.get("msg_count", 0)
        label = f"Чат {chat_id} ({count} сообщ.)"
        rows.append([InlineKeyboardButton(
            text=label,
            callback_data=f"history:chat:{chat_id}",
            icon_custom_emoji_id=Emoji.FILE,
        )])
    rows.append([InlineKeyboardButton(
        text="Очистить всё",
        callback_data="history:clear_all",
        icon_custom_emoji_id=Emoji.TRASH,
    )])
    rows.append([InlineKeyboardButton(
        text="◁ Назад",
        callback_data="menu:main",
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def history_chat_kb(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Очистить историю чата",
            callback_data=f"history:clear:{chat_id}",
            icon_custom_emoji_id=Emoji.TRASH,
        )],
        [InlineKeyboardButton(
            text="◁ Назад",
            callback_data="menu:history",
        )],
    ])


# ── Chats ──────────────────────────────────────────────────────────

def chats_kb(chats: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for chat in chats:
        chat_id = chat["chat_id"]
        name = chat.get("chat_name") or str(chat_id)
        auto = chat.get("auto_reply", 0)
        status_icon = Emoji.CHECK if auto else Emoji.CROSS
        rows.append([
            InlineKeyboardButton(
                text=name,
                callback_data=f"chats:info:{chat_id}",
                icon_custom_emoji_id=Emoji.PROFILE,
            ),
            InlineKeyboardButton(
                text="Авто" if auto else "Выкл",
                callback_data=f"chats:toggle:{chat_id}",
                icon_custom_emoji_id=status_icon,
            ),
        ])
    rows.append([InlineKeyboardButton(
        text="Добавить чат",
        callback_data="chats:add",
        icon_custom_emoji_id=Emoji.ADD_TEXT,
    )])
    rows.append([InlineKeyboardButton(
        text="◁ Назад",
        callback_data="menu:main",
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def chats_add_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Отмена",
            callback_data="chats:cancel",
            icon_custom_emoji_id=Emoji.CROSS,
        )],
    ])


def chat_info_kb(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Что узнал из чата",
            callback_data=f"chats:learned:{chat_id}",
            icon_custom_emoji_id=Emoji.GROWTH,
        )],
        [InlineKeyboardButton(
            text="Статистика",
            callback_data=f"chats:stats:{chat_id}",
            icon_custom_emoji_id=Emoji.STATS_CHART,
        )],
        [InlineKeyboardButton(
            text="Удалить",
            callback_data=f"chats:remove:{chat_id}",
            icon_custom_emoji_id=Emoji.TRASH,
        )],
        [InlineKeyboardButton(
            text="◁ Назад",
            callback_data="menu:chats",
        )],
    ])


# ── Knowledge (Что узнал) ─────────────────────────────────────────

def knowledge_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Анализ всех чатов",
            callback_data="knowledge:analyze_all",
            icon_custom_emoji_id=Emoji.BOT,
        )],
        [InlineKeyboardButton(
            text="Статистика",
            callback_data="knowledge:stats",
            icon_custom_emoji_id=Emoji.STATS_CHART,
        )],
        [InlineKeyboardButton(
            text="Стиль общения",
            callback_data="knowledge:style",
            icon_custom_emoji_id=Emoji.WRITE,
        )],
        [InlineKeyboardButton(
            text="◁ Назад",
            callback_data="menu:main",
        )],
    ])


# ── Settings ───────────────────────────────────────────────────────

def settings_kb(auto_reply: bool) -> InlineKeyboardMarkup:
    toggle_text = "Авто-ответ: ВКЛ" if auto_reply else "Авто-ответ: ВЫКЛ"
    toggle_icon = Emoji.CHECK if auto_reply else Emoji.CROSS
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=toggle_text,
            callback_data="settings:toggle_reply",
            icon_custom_emoji_id=toggle_icon,
        )],
        [InlineKeyboardButton(
            text="Модель AI",
            callback_data="settings:model",
            icon_custom_emoji_id=Emoji.BOT,
        )],
        [InlineKeyboardButton(
            text="API URL",
            callback_data="settings:api_url",
            icon_custom_emoji_id=Emoji.LINK,
        )],
        [InlineKeyboardButton(
            text="Отключить бизнес",
            callback_data="settings:disconnect",
            icon_custom_emoji_id=Emoji.PERSON_CROSS,
        )],
        [InlineKeyboardButton(
            text="◁ Назад",
            callback_data="menu:main",
        )],
    ])


def settings_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Отмена",
            callback_data="settings:cancel",
            icon_custom_emoji_id=Emoji.CROSS,
        )],
    ])


# ── Model picker ───────────────────────────────────────────────────

def model_picker_kb(
    models: list[dict], page: int = 0, per_page: int = 8
) -> InlineKeyboardMarkup:
    start = page * per_page
    end = start + per_page
    page_models = models[start:end]

    rows: list[list[InlineKeyboardButton]] = []
    for m in page_models:
        model_id = m["id"]
        name = m.get("name", model_id)
        short = name[:35] + "…" if len(name) > 35 else name
        rows.append([InlineKeyboardButton(
            text=short,
            callback_data=f"model:pick:{model_id[:50]}",
            icon_custom_emoji_id=Emoji.BOT,
        )])

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(
            text="◁ Назад",
            callback_data=f"model:page:{page - 1}",
        ))
    if end < len(models):
        nav.append(InlineKeyboardButton(
            text="Далее ▷",
            callback_data=f"model:page:{page + 1}",
        ))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(
        text="Поиск модели",
        callback_data="model:search",
        icon_custom_emoji_id=Emoji.SEARCH if hasattr(Emoji, "SEARCH") else Emoji.EYE,
    )])
    rows.append([InlineKeyboardButton(
        text="◁ Настройки",
        callback_data="menu:settings",
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def model_search_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Отмена",
            callback_data="settings:model",
            icon_custom_emoji_id=Emoji.CROSS,
        )],
    ])
