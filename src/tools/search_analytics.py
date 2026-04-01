"""Google Search Console Search Analytics API."""

from urllib.parse import quote

from src.credentials import load_service_account
from src.google_auth import get_google_access_token
from src.proxy_router import get_client, safe_json

_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
_GSC_BASE = "https://www.googleapis.com/webmasters/v3"
_MAX_ROWS_PER_PAGE = 25_000


async def search_analytics(
    site_url: str,
    start_date: str,
    end_date: str,
    dimensions: list[str] | None = None,
    search_type: str = "web",
    dimension_filter_groups: list[dict] | None = None,
    aggregation_type: str | None = None,
    data_state: str | None = None,
    row_limit: int | None = None,
) -> dict:
    """Query Search Console search analytics for a site.

    Returns clicks, impressions, CTR, and average position broken down
    by the requested dimensions. Paginates automatically.
    """
    if dimensions is None:
        dimensions = ["query", "page", "date"]

    sa_info = load_service_account()
    token = await get_google_access_token(sa_info, _SCOPE)

    encoded_site = quote(site_url, safe="")
    url = f"{_GSC_BASE}/sites/{encoded_site}/searchAnalytics/query"
    headers = {"Authorization": f"Bearer {token}"}

    all_rows: list[dict] = []
    start_row = 0

    async with get_client(timeout=60) as client:
        while True:
            fetch_count = (
                min(row_limit - len(all_rows), _MAX_ROWS_PER_PAGE)
                if row_limit is not None
                else _MAX_ROWS_PER_PAGE
            )

            body: dict = {
                "startDate": start_date,
                "endDate": end_date,
                "dimensions": dimensions,
                "type": search_type,
                "rowLimit": fetch_count,
                "startRow": start_row,
            }
            if dimension_filter_groups:
                body["dimensionFilterGroups"] = dimension_filter_groups
            if aggregation_type:
                body["aggregationType"] = aggregation_type
            if data_state:
                body["dataState"] = data_state

            r = await client.post(url, headers=headers, json=body)
            r.raise_for_status()
            rows = safe_json(r).get("rows", [])

            for row in rows:
                keys = row.get("keys", [])
                record: dict = dict(zip(dimensions, keys))
                record["clicks"] = row.get("clicks")
                record["impressions"] = row.get("impressions")
                record["ctr"] = round(row.get("ctr", 0), 6)
                record["position"] = round(row.get("position", 0), 2)
                all_rows.append(record)

            if len(rows) < fetch_count:
                break
            if row_limit is not None and len(all_rows) >= row_limit:
                break
            start_row += len(rows)

    return {
        "siteUrl": site_url,
        "dateRange": {"startDate": start_date, "endDate": end_date},
        "searchType": search_type,
        "dimensions": dimensions,
        "rowCount": len(all_rows),
        "data": all_rows,
    }
