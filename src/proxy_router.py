"""Proxy routing for Google API requests.

If PROXY_URL is configured, all requests go through it.
Otherwise requests go direct.
"""

import json

import httpx

from src.config import settings
from src.ttl_cache import TTLCache

_IP_CACHE: TTLCache[str] = TTLCache()
_IP_TTL = 300  # 5 minutes


def safe_json(response: httpx.Response) -> dict | list:
    """Parse JSON from an httpx response with a clear error on non-JSON bodies."""
    try:
        return response.json()
    except (json.JSONDecodeError, ValueError) as e:
        raise RuntimeError(
            f"Expected JSON response from {response.request.url}, "
            f"got {response.headers.get('content-type', 'unknown')}: "
            f"{response.text[:200]}"
        ) from e


def get_client(**kwargs) -> httpx.AsyncClient:
    """Return an httpx.AsyncClient, optionally routed through the configured proxy."""
    if settings.proxy_url:
        return httpx.AsyncClient(proxy=settings.proxy_url, **kwargs)
    return httpx.AsyncClient(**kwargs)


async def get_exit_ip() -> str:
    """Return the exit IP, cached for 5 minutes."""
    async def _fetch() -> str:
        async with get_client(timeout=10) as client:
            try:
                r = await client.get("https://httpbin.org/ip")
                return r.json().get("origin", "unknown")
            except Exception:
                return "unknown"

    return await _IP_CACHE.get_or_set("exit_ip", _IP_TTL, _fetch)
