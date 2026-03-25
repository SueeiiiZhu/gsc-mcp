"""Google Search Console Sitemaps API."""

from urllib.parse import quote

from src.config import Brand
from src.credentials import load_service_account
from src.google_auth import get_google_access_token
from src.proxy_router import get_client, safe_json

_SCOPE_READONLY = "https://www.googleapis.com/auth/webmasters.readonly"
_SCOPE_READWRITE = "https://www.googleapis.com/auth/webmasters"
_GSC_BASE = "https://www.googleapis.com/webmasters/v3"


async def list_sitemaps(brand: Brand, site_url: str) -> dict:
    """List all sitemaps submitted for a site."""
    sa_info = load_service_account(brand)
    token = await get_google_access_token(brand, sa_info, _SCOPE_READONLY)

    encoded_site = quote(site_url, safe="")
    url = f"{_GSC_BASE}/sites/{encoded_site}/sitemaps"
    headers = {"Authorization": f"Bearer {token}"}

    async with get_client(brand, timeout=30) as client:
        r = await client.get(url, headers=headers)
        r.raise_for_status()
        raw = safe_json(r)

    sitemaps = []
    for sm in raw.get("sitemap", []):
        entry = {
            "path": sm.get("path", ""),
            "lastSubmitted": sm.get("lastSubmitted", ""),
            "lastDownloaded": sm.get("lastDownloaded", ""),
            "isPending": sm.get("isPending", False),
            "isSitemapsIndex": sm.get("isSitemapsIndex", False),
            "type": sm.get("type", ""),
            "warnings": sm.get("warnings", 0),
            "errors": sm.get("errors", 0),
        }
        contents = []
        for c in sm.get("contents", []):
            contents.append({
                "type": c.get("type", ""),
                "submitted": c.get("submitted", 0),
                "indexed": c.get("indexed", 0),
            })
        entry["contents"] = contents
        sitemaps.append(entry)

    return {"siteUrl": site_url, "sitemapCount": len(sitemaps), "sitemaps": sitemaps}


async def submit_sitemap(brand: Brand, site_url: str, sitemap_url: str) -> dict:
    """Submit a sitemap for a site. Requires read-write scope."""
    sa_info = load_service_account(brand)
    token = await get_google_access_token(brand, sa_info, _SCOPE_READWRITE)

    encoded_site = quote(site_url, safe="")
    encoded_sitemap = quote(sitemap_url, safe="")
    url = f"{_GSC_BASE}/sites/{encoded_site}/sitemaps/{encoded_sitemap}"
    headers = {"Authorization": f"Bearer {token}"}

    async with get_client(brand, timeout=30) as client:
        r = await client.put(url, headers=headers)
        r.raise_for_status()

    return {
        "siteUrl": site_url,
        "sitemapUrl": sitemap_url,
        "status": "submitted",
    }
