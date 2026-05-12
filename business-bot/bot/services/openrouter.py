"""OpenRouter API client — fetch available models."""

import logging
import time

import aiohttp

logger = logging.getLogger(__name__)

_models_cache: list[dict] = []
_cache_ts: float = 0
_CACHE_TTL = 3600  # 1 hour


async def fetch_models(api_key: str) -> list[dict]:
    """Fetch all available models from OpenRouter. Cached for 1 hour."""
    global _models_cache, _cache_ts

    if _models_cache and (time.time() - _cache_ts) < _CACHE_TTL:
        return _models_cache

    url = "https://openrouter.ai/api/v1/models"
    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    logger.error("OpenRouter models API error: %s", resp.status)
                    return _models_cache
                data = await resp.json()
                models = data.get("data", [])
                _models_cache = [
                    {
                        "id": m["id"],
                        "name": m.get("name", m["id"]),
                        "context": m.get("context_length", 0),
                    }
                    for m in models
                    if not m["id"].startswith("~")  # skip aliases
                ]
                _cache_ts = time.time()
                logger.info("Fetched %d models from OpenRouter", len(_models_cache))
                return _models_cache
    except Exception:
        logger.exception("Failed to fetch OpenRouter models")
        return _models_cache


async def search_models(api_key: str, query: str) -> list[dict]:
    """Search models by name/id substring."""
    models = await fetch_models(api_key)
    q = query.lower()
    return [m for m in models if q in m["id"].lower() or q in m["name"].lower()]


def get_featured_models(all_models: list[dict], featured_ids: list[str]) -> list[dict]:
    """Return models matching featured IDs, preserving order."""
    model_map = {m["id"]: m for m in all_models}
    return [model_map[fid] for fid in featured_ids if fid in model_map]
