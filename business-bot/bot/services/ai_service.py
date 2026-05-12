import logging

import aiohttp

logger = logging.getLogger(__name__)


async def get_ai_response(
    api_key: str,
    api_url: str,
    model: str,
    system_prompt: str,
    messages: list[dict[str, str]],
) -> str | None:
    """Call an OpenAI-compatible chat completions endpoint.

    Returns the assistant reply text, or None on failure.
    """
    if not api_key:
        return None

    url = f"{api_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            *messages,
        ],
        "max_tokens": 1024,
        "temperature": 0.7,
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
