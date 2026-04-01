"""Google Search Console URL Inspection API."""

from src.credentials import load_service_account
from src.google_auth import get_google_access_token
from src.proxy_router import get_client, safe_json

_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
_INSPECT_URL = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"


async def inspect_url(
    inspection_url: str,
    site_url: str,
    language_code: str = "en",
) -> dict:
    """Inspect a URL's index status, crawl info, mobile usability, and rich results.

    Rate limit: 2,000 inspections/day per site, 600/minute.
    """
    sa_info = load_service_account()
    token = await get_google_access_token(sa_info, _SCOPE)

    headers = {"Authorization": f"Bearer {token}"}

    async with get_client(timeout=30) as client:
        r = await client.post(
            _INSPECT_URL,
            headers=headers,
            json={
                "inspectionUrl": inspection_url,
                "siteUrl": site_url,
                "languageCode": language_code,
            },
        )
        r.raise_for_status()
        raw = safe_json(r)

    result = raw.get("inspectionResult", {})
    return _flatten_inspection_result(inspection_url, result)


def _flatten_inspection_result(url: str, result: dict) -> dict:
    """Flatten the deeply nested inspection result into a readable structure."""
    index_status = result.get("indexStatusResult", {})
    crawl = index_status  # crawl info is embedded in index status
    mobile = result.get("mobileUsabilityResult", {})
    rich = result.get("richResultsResult", {})

    out: dict = {
        "inspectionUrl": url,
        # Index status
        "verdict": index_status.get("verdict", "UNKNOWN"),
        "coverageState": index_status.get("coverageState", ""),
        "indexingState": index_status.get("indexingState", ""),
        "robotsTxtState": index_status.get("robotsTxtState", ""),
        "pageFetchState": index_status.get("pageFetchState", ""),
        "lastCrawlTime": crawl.get("lastCrawlTime", ""),
        "crawledAs": crawl.get("crawledAs", ""),
        "googleCanonical": crawl.get("googleCanonical", ""),
        "userCanonical": crawl.get("userCanonical", ""),
        # Referring
        "referringUrls": index_status.get("referringUrls", []),
        "sitemap": index_status.get("sitemap", []),
        # Mobile usability
        "mobileUsability": {
            "verdict": mobile.get("verdict", "UNKNOWN"),
            "issues": [
                issue.get("issueType", "")
                for issue in mobile.get("issues", [])
            ],
        },
        # Rich results
        "richResults": {
            "verdict": rich.get("verdict", "UNKNOWN"),
            "detectedItems": [
                {
                    "type": item.get("richResultType", ""),
                    "issues": [
                        {
                            "issueMessage": i.get("issueMessage", ""),
                            "severity": i.get("severity", ""),
                        }
                        for i in item.get("items", [{}])[0].get("issues", [])
                    ]
                    if item.get("items")
                    else [],
                }
                for item in rich.get("detectedItems", [])
            ],
        },
    }
    return out
