"""Google Service Account OAuth2 token exchange via VPS proxy.

Token exchange itself goes through the brand's VPS proxy so the auth
request also exits from the correct residential IP.
"""

import time

import jwt  # PyJWT

from src.config import Brand, settings
from src.proxy_router import get_client, safe_json
from src.ttl_cache import TTLCache

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_TOKEN_CACHE = TTLCache[str]()


async def get_google_access_token(brand: Brand, sa_info: dict, scope: str) -> str:
    """Exchange a Service Account JSON for a short-lived access token.

    Args:
        brand: Brand identifier — determines which VPS proxy is used.
        sa_info: Parsed Google Service Account JSON dict.
        scope: OAuth2 scope string.

    Returns:
        Bearer access token (valid ~1 hour).
    """
    cache_key = ("sa", brand, sa_info["client_email"], scope)
    return await _TOKEN_CACHE.get_or_set(
        cache_key,
        settings.google_access_token_ttl_seconds,
        lambda: _exchange_service_account_token(brand, sa_info, scope),
    )


async def _exchange_service_account_token(
    brand: Brand, sa_info: dict, scope: str
) -> str:
    now = int(time.time())
    assertion = jwt.encode(
        {
            "iss": sa_info["client_email"],
            "scope": scope,
            "aud": _TOKEN_URL,
            "iat": now,
            "exp": now + 3600,
        },
        sa_info["private_key"],
        algorithm="RS256",
        headers={"kid": sa_info["private_key_id"]},
    )
    async with get_client(brand, timeout=15) as client:
        r = await client.post(
            _TOKEN_URL,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            },
        )
        r.raise_for_status()
        return safe_json(r)["access_token"]
