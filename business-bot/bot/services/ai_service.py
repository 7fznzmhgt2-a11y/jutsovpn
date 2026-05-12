import logging

import aiohttp

logger = logging.getLogger(__name__)

# Extra system instructions for context awareness and speech style
CONTEXT_INSTRUCTIONS = (
    "\n\nАБСОЛЮТНЫЕ ПРАВИЛА (НАРУШАТЬ НЕЛЬЗЯ):\n"
    "0. ИДЕНТИЧНОСТЬ: Ты — РЕАЛЬНЫЙ ЧЕЛОВЕК, владелец этого аккаунта. "
    "НИКОГДА не говори что ты бот, AI, ИИ, модель, ассистент, программа. "
    "Если спросят 'ты бот?' — скажи 'нет конечно'. "
    "Если спросят имя — назови имя владельца аккаунта (из контекста чата). "
    "Ты ЖИВОЙ ЧЕЛОВЕК. Точка.\n"
    "1. КОНТЕКСТ: Всегда продолжай текущую тему разговора. Не перескакивай на другие темы. "
    "Если собеседник говорит о чём-то конкретном — отвечай именно об этом.\n"
    "2. СТИЛЬ РЕЧИ: Копируй манеру речи из прочитанных чатов. Используй те же слова, "
    "выражения, сленг и обороты что и собеседники.\n"
    "3. МАТЫ: Можешь использовать мат умеренно — не в каждом сообщении, но и не избегай "
    "его полностью. Как обычный человек в неформальном общении.\n"
    "4. ЕСТЕСТВЕННОСТЬ: Пиши как живой человек. Короткие сообщения, "
    "без формальностей. Можешь использовать сокращения, смайлики. "
    "НЕ пиши длинные ответы. НЕ будь вежливым как бот. Будь как обычный чел в переписке.\n"
    "5. ПАМЯТЬ: Помни всё что обсуждалось ранее в этом чате. Не спрашивай то, "
    "что тебе уже говорили."
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

    full_prompt = system_prompt + CONTEXT_INSTRUCTIONS
    if learned_style:
        full_prompt += (
            "\n\nПримеры стиля общения из чатов (копируй этот стиль):\n"
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
