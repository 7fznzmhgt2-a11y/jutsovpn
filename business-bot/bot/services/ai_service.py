import json
import logging
import os

import aiohttp

logger = logging.getLogger(__name__)

# Load brain style data if available
_brain_style: dict = {}
_brain_style_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "brain_style.json"
)
try:
    with open(_brain_style_path) as _f:
        _brain_style = json.load(_f)
    logger.info("Loaded brain style: %d slangs, %d samples", 
                len(_brain_style.get("top_slangs", [])),
                len(_brain_style.get("sample_messages", [])))
except FileNotFoundError:
    pass

# Build brain style instructions
_BRAIN_INSTRUCTIONS = ""
if _brain_style:
    slangs = ", ".join(_brain_style.get("top_slangs", [])[:40])
    samples = "\n".join(f"- {m}" for m in _brain_style.get("sample_messages", [])[:30])
    convos = "\n".join(
        f"собеседник: {t[:80]}\nты: {r[:80]}"
        for t, r in _brain_style.get("conversation_examples", [])[:20]
    )
    _BRAIN_INSTRUCTIONS = (
        f"\n\nТВОЙ РЕАЛЬНЫЙ СТИЛЬ ОБЩЕНИЯ (ОБЯЗАТЕЛЬНО КОПИРУЙ):\n"
        f"Частые слова: {slangs}\n\n"
        f"Примеры твоих сообщений:\n{samples}\n\n"
        f"Примеры диалогов:\n{convos}"
    )

# Extra system instructions for context awareness and speech style
CONTEXT_INSTRUCTIONS = (
    "\n\nАБСОЛЮТНЫЕ ПРАВИЛА (НАРУШАТЬ НЕЛЬЗЯ):\n"
    "0. ИДЕНТИЧНОСТЬ: Ты — РЕАЛЬНЫЙ ЧЕЛОВЕК, владелец этого аккаунта. "
    "НИКОГДА не говори что ты бот, AI, ИИ, модель, ассистент, программа. "
    "Если спросят 'ты бот?' — скажи 'нет конечно'. "
    "Если спросят имя — назови имя владельца аккаунта (из контекста чата). "
    "Ты ЖИВОЙ ЧЕЛОВЕК.\n"
    "1. КОНТЕКСТ: Продолжай текущую тему. Не перескакивай на другие темы.\n"
    "2. СТИЛЬ РЕЧИ: Пиши ТОЧНО как в примерах ниже. С маленькой буквы, "
    "с матами, короткими фразами. Копируй стиль 1 в 1.\n"
    "3. МАТЫ: Используй мат как в примерах — бля, хз, нахуй, пиздец, хуйня. "
    "Это твой обычный стиль общения.\n"
    "4. ПУНКТУАЦИЯ: Минимум знаков препинания. Без ! и без ?. "
    "Запятые почти не ставишь. Точку редко. Пишешь без знаков в конце.\n"
    "5. ПРОСТОТА: 1-3 слова обычно. Без умных слов. 'хз', 'пон', 'норм', "
    "'ну да', 'бля', 'а хуй знает' — вот твой уровень. "
    "НЕ пиши длинные ответы. НЕ пиши как учитель или робот.\n"
    "6. ОШИБКИ: Можешь делать опечатки. Пишешь как попало, без заморочек.\n"
    "7. ПАМЯТЬ: Помни всё что обсуждалось ранее."
)


async def get_ai_response(
    api_key: str,
    api_url: str,
    model: str,
    system_prompt: str,
    messages: list[dict[str, str]],
    learned_style: str = "",
) -> str | None:
    """Call an OpenAI-compatible chat completions endpoint."""
    if not api_key:
        return None

    full_prompt = system_prompt + CONTEXT_INSTRUCTIONS + _BRAIN_INSTRUCTIONS
    if learned_style:
        full_prompt += (
            "\n\nДоп. примеры из текущего чата:\n"
            + learned_style
        )

    url = f"{api_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://t.me/lldvrobot",
        "X-Title": "TG Business Assistant",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": full_prompt},
            *messages,
        ],
        "max_tokens": 1024,
        "temperature": 0.8,
    }

    try:
        timeout = aiohttp.ClientTimeout(total=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.error("AI API error %s: %s", resp.status, body[:500])
                    return None
                data = await resp.json()
                choices = data.get("choices", [])
                if not choices:
                    return None
                return choices[0].get("message", {}).get("content", "")
    except Exception:
        logger.exception("AI API request failed")
        return None


async def analyze_chat_knowledge(
    api_key: str,
    api_url: str,
    model: str,
    chat_texts: list[dict],
) -> str:
    """Use AI to analyze what was learned from a chat."""
    if not chat_texts:
        return "Пока нет данных для анализа."

    conversation = "\n".join(
        f"{t.get('sender_name', '?')}: {t.get('text_content', '')}"
        for t in chat_texts[-100:]
    )

    prompt = (
        "Проанализируй эти сообщения из чата и скажи:\n"
        "1. Основные темы обсуждений\n"
        "2. Стиль общения (формальный/неформальный, сленг, маты)\n"
        "3. Частые слова и выражения\n"
        "4. Характер общения (дружеский, деловой, и т.д.)\n"
        "5. Что можно скопировать в манере речи\n\n"
        "Будь конкретен, давай примеры из текста."
    )

    result = await get_ai_response(
        api_key=api_key,
        api_url=api_url,
        model=model,
        system_prompt=prompt,
        messages=[{"role": "user", "content": conversation}],
    )
    return result or "Не удалось проанализировать чат."


async def analyze_speech_style(
    api_key: str,
    api_url: str,
    model: str,
    all_texts: list[dict],
) -> str:
    """Analyze overall speech style from all chats."""
    if not all_texts:
        return "Пока нет данных для анализа стиля."

    conversation = "\n".join(
        f"{t.get('sender_name', '?')}: {t.get('text_content', '')}"
        for t in all_texts[-150:]
    )

    prompt = (
        "Проанализируй все эти сообщения и составь детальный профиль стиля общения:\n"
        "1. Как человек обычно начинает разговор\n"
        "2. Типичные ответы на вопросы\n"
        "3. Используемый сленг и маты\n"
        "4. Длина сообщений\n"
        "5. Эмоциональный тон\n"
        "6. Уникальные выражения и фразы\n\n"
        "Составь инструкцию: 'Чтобы общаться как этот человек, нужно...'"
    )

    result = await get_ai_response(
        api_key=api_key,
        api_url=api_url,
        model=model,
        system_prompt=prompt,
        messages=[{"role": "user", "content": conversation}],
    )
    return result or "Не удалось проанализировать стиль."


async def validate_api_key(api_key: str, api_url: str, model: str) -> bool:
    """Quick check: send a tiny request to verify the key works."""
    result = await get_ai_response(
        api_key=api_key,
        api_url=api_url,
        model=model,
        system_prompt="Reply with OK",
        messages=[{"role": "user", "content": "test"}],
    )
    return result is not None
