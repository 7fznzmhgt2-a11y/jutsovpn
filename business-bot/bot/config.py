import os

BOT_TOKEN: str = os.environ["BOT_TOKEN"].strip()

DATABASE_PATH: str = os.environ.get("DATABASE_PATH", "data/bot.db")

DEFAULT_API_URL: str = os.environ.get("DEFAULT_API_URL", "https://api.openai.com/v1")
DEFAULT_MODEL: str = os.environ.get("DEFAULT_MODEL", "gpt-4o-mini")

DEFAULT_PROMPT: str = (
    "Ты — мой личный помощник. Отвечай так, как будто ты — это я. "
    "Используй мой стиль общения, мои слова и выражения. "
    "Будь краток и по делу. Отвечай на том же языке, на котором пишет собеседник."
)

MAX_HISTORY_MESSAGES: int = 50
CONTEXT_MESSAGES: int = 20
