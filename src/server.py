"""GSC MCP Server — stdio transport entry point."""

import asyncio
import json
import logging

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from src.config import BRANDS, Brand, settings
from src.proxy_router import get_exit_ip
from src.tools import search_analytics, sitemaps, url_inspection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = Server("gsc-mcp")

_BRAND_ENUM = list(BRANDS)

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOLS: list[Tool] = [
    Tool(
        name="gsc_health_check",
        description=(
            "Check proxy connectivity and reveal the exit IP for a brand. "
            "If no proxy is configured, returns the local machine's public IP. "
            "Use this to verify that traffic exits from the expected VPS IP."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "brand": {
                    "type": "string",
                    "enum": _BRAND_ENUM,
                    "description": "Brand identifier. Omit to use default.",
                },
            },
            "required": [],
        },
    ),
    Tool(
        name="gsc_search_analytics",
        description=(
            "Query Google Search Console search analytics. "
            "Returns clicks, impressions, CTR, and average position "
            "broken down by dimensions (query, page, date, country, device). "
            "Supports filtering by dimension values and search type "
            "(web, image, video, discover, news). "
            "Paginates automatically; use rowLimit to cap results."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "brand": {
                    "type": "string",
                    "enum": _BRAND_ENUM,
                    "description": (
                        "Brand identifier. "
                        "Omit to use GSC_DEFAULT_BRAND."
                    ),
                },
                "siteUrl": {
                    "type": "string",
                    "description": (
                        "GSC site URL, e.g. 'sc-domain:example.com'. "
                        "Omit to use the brand's configured default."
                    ),
                },
                "startDate": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format (Pacific Time).",
                },
                "endDate": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format (Pacific Time).",
                },
                "dimensions": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "query",
                            "page",
                            "country",
                            "device",
                            "date",
                            "searchAppearance",
                        ],
                    },
                    "description": (
                        "Dimensions to group by. "
                        "Defaults to ['query', 'page', 'date']."
                    ),
                },
                "searchType": {
                    "type": "string",
                    "enum": ["web", "image", "video", "discover", "googleNews", "news"],
                    "description": "Search type filter. Defaults to 'web'.",
                },
                "dimensionFilterGroups": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "groupType": {
                                "type": "string",
                                "enum": ["and"],
                            },
                            "filters": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "dimension": {"type": "string"},
                                        "operator": {
                                            "type": "string",
                                            "enum": [
                                                "contains",
                                                "equals",
                                                "notContains",
                                                "notEquals",
                                                "includingRegex",
                                                "excludingRegex",
                                            ],
                                        },
                                        "expression": {"type": "string"},
                                    },
                                    "required": [
                                        "dimension",
                                        "operator",
                                        "expression",
                                    ],
                                },
                            },
                        },
                    },
                    "description": (
                        "Filter results by dimension values. "
                        "Example: filter pages containing '/blog/'."
                    ),
                },
                "aggregationType": {
                    "type": "string",
                    "enum": ["auto", "byPage", "byProperty"],
                    "description": "How to aggregate results.",
                },
                "dataState": {
                    "type": "string",
                    "enum": ["all", "final"],
                    "description": (
                        "'all' includes fresh data (may change), "
                        "'final' only confirmed data."
                    ),
                },
                "rowLimit": {
                    "type": "integer",
                    "description": "Max total rows. Omit to fetch all.",
                },
            },
            "required": ["startDate", "endDate"],
        },
    ),
    Tool(
        name="gsc_inspect_url",
        description=(
            "Inspect a URL's Google Search index status. "
            "Returns indexing state, crawl info, mobile usability, "
            "rich results, canonical URL, and referring pages. "
            "Rate limit: 2,000 inspections/day per site."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "brand": {
                    "type": "string",
                    "enum": _BRAND_ENUM,
                    "description": "Brand identifier. Omit to use default.",
                },
                "inspectionUrl": {
                    "type": "string",
                    "description": "The full URL to inspect.",
                },
                "siteUrl": {
                    "type": "string",
                    "description": (
                        "GSC site URL. Omit to use brand default."
                    ),
                },
                "languageCode": {
                    "type": "string",
                    "description": "IETF BCP-47 language code. Defaults to 'en'.",
                },
            },
            "required": ["inspectionUrl"],
        },
    ),
    Tool(
        name="gsc_list_sitemaps",
        description=(
            "List all sitemaps submitted for a site in Google Search Console. "
            "Returns path, type, submission date, indexed/submitted counts, "
            "warnings, and errors for each sitemap."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "brand": {
                    "type": "string",
                    "enum": _BRAND_ENUM,
                    "description": "Brand identifier. Omit to use default.",
                },
                "siteUrl": {
                    "type": "string",
                    "description": "GSC site URL. Omit to use brand default.",
                },
            },
            "required": [],
        },
    ),
    Tool(
        name="gsc_submit_sitemap",
        description=(
            "Submit a sitemap URL to Google Search Console for a site. "
            "Google will schedule it for crawling."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "brand": {
                    "type": "string",
                    "enum": _BRAND_ENUM,
                    "description": "Brand identifier. Omit to use default.",
                },
                "siteUrl": {
                    "type": "string",
                    "description": "GSC site URL. Omit to use brand default.",
                },
                "sitemapUrl": {
                    "type": "string",
                    "description": (
                        "Full URL of the sitemap to submit, "
                        "e.g. 'https://example.com/sitemap.xml'."
                    ),
                },
            },
            "required": ["sitemapUrl"],
        },
    ),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_brand(arguments: dict) -> Brand:
    """Resolve brand from arguments or default config."""
    brand = arguments.get("brand", "")
    if not brand:
        brand = settings.gsc_default_brand
    if brand not in BRANDS:
        raise ValueError(
            f"Unknown brand {brand!r}. Must be one of {BRANDS}. "
            f"Set 'brand' parameter or GSC_DEFAULT_BRAND env var."
        )
    return brand  # type: ignore[return-value]


def _resolve_site_url(brand: Brand, arguments: dict) -> str:
    """Resolve site URL from arguments or brand default."""
    site_url = arguments.get("siteUrl", "")
    if not site_url:
        site_url = settings.site_url_for(brand)
    if not site_url:
        raise ValueError(
            f"No site URL provided and no default configured for {brand!r}. "
            f"Set 'siteUrl' parameter or SITE_URL_{brand.upper()} env var."
        )
    return site_url


# ---------------------------------------------------------------------------
# MCP handlers
# ---------------------------------------------------------------------------


@mcp.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@mcp.call_tool()
async def call_tool(name: str, arguments: dict):
    try:
        brand = _resolve_brand(arguments)
        exit_ip = await get_exit_ip(brand)
        logger.info("[%s] exit IP: %s", brand, exit_ip)

        if name == "gsc_health_check":
            from src.proxy_router import get_client

            proxy_url = settings.proxy_for(brand)
            async with get_client(brand, timeout=10) as client:
                r = await client.get("https://httpbin.org/ip")
                r.raise_for_status()
                exit_ip = r.json().get("origin", "unknown")
            result = {
                "brand": brand,
                "proxyConfigured": bool(proxy_url),
                "proxyUrl": proxy_url[:proxy_url.index("@") + 1] + "***" if proxy_url and "@" in proxy_url else proxy_url or "none",
                "exitIp": exit_ip,
            }
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        site_url = _resolve_site_url(brand, arguments)

        if name == "gsc_search_analytics":
            result = await search_analytics.search_analytics(
                brand=brand,
                site_url=site_url,
                start_date=arguments["startDate"],
                end_date=arguments["endDate"],
                dimensions=arguments.get("dimensions"),
                search_type=arguments.get("searchType", "web"),
                dimension_filter_groups=arguments.get("dimensionFilterGroups"),
                aggregation_type=arguments.get("aggregationType"),
                data_state=arguments.get("dataState"),
                row_limit=arguments.get("rowLimit"),
            )
        elif name == "gsc_inspect_url":
            result = await url_inspection.inspect_url(
                brand=brand,
                inspection_url=arguments["inspectionUrl"],
                site_url=site_url,
                language_code=arguments.get("languageCode", "en"),
            )
        elif name == "gsc_list_sitemaps":
            result = await sitemaps.list_sitemaps(
                brand=brand,
                site_url=site_url,
            )
        elif name == "gsc_submit_sitemap":
            result = await sitemaps.submit_sitemap(
                brand=brand,
                site_url=site_url,
                sitemap_url=arguments["sitemapUrl"],
            )
        else:
            result = {"error": f"Tool {name!r} not found"}

        output = {"_exitIp": exit_ip, **result} if isinstance(result, dict) else result
        return [TextContent(type="text", text=json.dumps(output, indent=2))]

    except Exception as e:
        logger.exception("Tool %r failed", name)
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def _main_async():
    async with stdio_server() as (read_stream, write_stream):
        await mcp.run(
            read_stream,
            write_stream,
            mcp.create_initialization_options(),
        )


def main():
    asyncio.run(_main_async())


if __name__ == "__main__":
    main()
