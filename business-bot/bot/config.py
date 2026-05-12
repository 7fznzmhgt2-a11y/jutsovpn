import os

BOT_TOKEN: str = os.environ["BOT_TOKEN"].strip()

DATABASE_PATH: str = os.environ.get("DATABASE_PATH", "data/bot.db")

DEFAULT_API_URL: str = os.environ.get(
    "DEFAULT_API_URL", "https://openrouter.ai/api/v1"
)
DEFAULT_API_KEY: str = os.environ.get("OPENROUTER_API_KEY", "")
DEFAULT_MODEL: str = os.environ.get("DEFAULT_MODEL", "google/gemini-2.5-flash")

DEFAULT_PROMPT: str = (
    "Ты — мой личный помощник. Отвечай так, как будто ты — это я. "
    "Используй мой стиль общения, мои слова и выражения. "
    "Будь краток и по делу. Отвечай на том же языке, на котором пишет собеседник. "
    "Учитывай контекст из прочитанных чатов и копируй стиль общения."
)

MAX_HISTORY_MESSAGES: int = 50
CONTEXT_MESSAGES: int = 30

# Popular models to show first in model picker
FEATURED_MODELS: list[str] = [
    "google/gemini-2.5-flash",
    "google/gemini-2.5-pro",
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "anthropic/claude-sonnet-4",
    "anthropic/claude-haiku-4",
    "x-ai/grok-3",
    "x-ai/grok-3-mini",
    "meta-llama/llama-4-maverick",
    "qwen/qwen3-235b-a22b",
    "deepseek/deepseek-chat-v3-0324",
    "mistralai/mistral-medium-3-5",
]
