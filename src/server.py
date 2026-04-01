"""GSC MCP Server — supports stdio, SSE, and Streamable HTTP transports."""

import argparse
import asyncio
import json
import logging
import uuid

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from src.config import settings
from src.proxy_router import get_exit_ip
from src.tools import search_analytics, sitemaps, url_inspection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = Server("gsc-mcp")

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOLS: list[Tool] = [
    Tool(
        name="gsc_health_check",
        description=(
            "Check proxy connectivity and reveal the exit IP. "
            "If no proxy is configured, returns the local machine's public IP."
        ),
        inputSchema={
            "type": "object",
            "properties": {},
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
                "siteUrl": {
                    "type": "string",
                    "description": (
                        "GSC site URL, e.g. 'sc-domain:example.com'. "
                        "Omit to use SITE_URL from env."
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
                "inspectionUrl": {
                    "type": "string",
                    "description": "The full URL to inspect.",
                },
                "siteUrl": {
                    "type": "string",
                    "description": "GSC site URL. Omit to use SITE_URL from env.",
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
                "siteUrl": {
                    "type": "string",
                    "description": "GSC site URL. Omit to use SITE_URL from env.",
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
                "siteUrl": {
                    "type": "string",
                    "description": "GSC site URL. Omit to use SITE_URL from env.",
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


def _resolve_site_url(arguments: dict) -> str:
    """Resolve site URL from arguments or env config."""
    site_url = arguments.get("siteUrl", "")
    if not site_url:
        site_url = settings.site_url
    if not site_url:
        raise ValueError(
            "No site URL provided. "
            "Set 'siteUrl' parameter or SITE_URL env var."
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
        exit_ip = await get_exit_ip()
        logger.info("exit IP: %s", exit_ip)

        if name == "gsc_health_check":
            from src.proxy_router import get_client

            proxy_url = settings.proxy_url
            async with get_client(timeout=10) as client:
                r = await client.get("https://httpbin.org/ip")
                r.raise_for_status()
                exit_ip = r.json().get("origin", "unknown")
            result = {
                "proxyConfigured": bool(proxy_url),
                "proxyUrl": proxy_url[:proxy_url.index("@") + 1] + "***" if proxy_url and "@" in proxy_url else proxy_url or "none",
                "exitIp": exit_ip,
            }
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        site_url = _resolve_site_url(arguments)

        if name == "gsc_search_analytics":
            result = await search_analytics.search_analytics(
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
                inspection_url=arguments["inspectionUrl"],
                site_url=site_url,
                language_code=arguments.get("languageCode", "en"),
            )
        elif name == "gsc_list_sitemaps":
            result = await sitemaps.list_sitemaps(
                site_url=site_url,
            )
        elif name == "gsc_submit_sitemap":
            result = await sitemaps.submit_sitemap(
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
# Transport helpers
# ---------------------------------------------------------------------------


async def _run_stdio():
    async with stdio_server() as (read_stream, write_stream):
        await mcp.run(
            read_stream,
            write_stream,
            mcp.create_initialization_options(),
        )


def _build_sse_app(mcp_path: str = "/sse"):
    """Build a Starlette app with SSE transport."""
    from starlette.applications import Starlette
    from starlette.routing import Mount, Route

    from mcp.server.sse import SseServerTransport

    sse_transport = SseServerTransport(f"{mcp_path}/messages/")

    async def handle_sse(request):
        async with sse_transport.connect_sse(
            request.scope, request.receive, request._send
        ) as (read_stream, write_stream):
            await mcp.run(
                read_stream,
                write_stream,
                mcp.create_initialization_options(),
            )

    return Starlette(
        routes=[
            Route(mcp_path, endpoint=handle_sse),
            Mount(f"{mcp_path}/messages/", app=sse_transport.handle_post_message),
        ],
    )


def _build_streamable_http_app(mcp_path: str = "/mcp"):
    """Build a raw ASGI app with Streamable HTTP transport.

    Uses a raw ASGI handler instead of Starlette's endpoint pattern because
    ``transport.handle_request`` sends responses directly via the ASGI ``send``
    callable, which is incompatible with Starlette's ``request_response``
    wrapper that expects a ``Response`` return value.
    """
    from starlette.requests import Request
    from starlette.responses import Response

    from mcp.server.streamable_http import StreamableHTTPServerTransport

    # Session management: transport + background mcp.run task per session
    _sessions: dict[str, StreamableHTTPServerTransport] = {}
    _tasks: dict[str, asyncio.Task] = {}

    async def _run_mcp_session(
        transport: StreamableHTTPServerTransport,
        session_id: str,
        ready_event: asyncio.Event,
    ):
        """Run mcp.run in background for the lifetime of a session."""
        try:
            async with transport.connect() as (read_stream, write_stream):
                ready_event.set()
                await mcp.run(
                    read_stream,
                    write_stream,
                    mcp.create_initialization_options(),
                )
        except Exception:
            logger.exception("MCP session %s crashed", session_id)
        finally:
            ready_event.set()  # unblock waiters even on failure
            _sessions.pop(session_id, None)
            _tasks.pop(session_id, None)

    async def app(scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                msg = await receive()
                if msg["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif msg["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
            return

        if scope["type"] != "http":
            return

        request = Request(scope, receive, send)

        if scope["path"] != mcp_path:
            resp = Response("Not Found", status_code=404)
            await resp(scope, receive, send)
            return

        if request.method not in ("GET", "POST", "DELETE"):
            resp = Response("Method Not Allowed", status_code=405)
            await resp(scope, receive, send)
            return

        session_id = request.headers.get("mcp-session-id")

        if request.method == "GET":
            if session_id and session_id in _sessions:
                transport = _sessions[session_id]
                await transport.handle_request(scope, receive, send)
                return

        if request.method == "POST":
            if session_id and session_id in _sessions:
                transport = _sessions[session_id]
                await transport.handle_request(scope, receive, send)
                return

            # New session: create transport, start mcp.run in background
            new_session_id = str(uuid.uuid4())
            transport = StreamableHTTPServerTransport(
                mcp_session_id=new_session_id,
                is_json_response_enabled=True,
            )
            _sessions[new_session_id] = transport
            ready_event = asyncio.Event()
            _tasks[new_session_id] = asyncio.create_task(
                _run_mcp_session(transport, new_session_id, ready_event)
            )

            # Wait for transport.connect() to finish before handling the request
            await ready_event.wait()
            await transport.handle_request(scope, receive, send)
            return

        if request.method == "DELETE":
            if session_id and session_id in _sessions:
                transport = _sessions.pop(session_id, None)
                task = _tasks.pop(session_id, None)
                if transport:
                    transport.terminate()
                    await transport.handle_request(scope, receive, send)
                if task:
                    task.cancel()
                return

        resp = Response("Bad Request", status_code=400)
        await resp(scope, receive, send)

    return app


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _parse_args():
    parser = argparse.ArgumentParser(description="GSC MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="Transport protocol (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind for HTTP transports (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind for HTTP transports (default: 8000)",
    )
    parser.add_argument(
        "--path",
        default=None,
        help="URL path prefix (default: /sse for SSE, /mcp for Streamable HTTP)",
    )
    return parser.parse_args()


def main():
    args = _parse_args()

    if args.transport == "stdio":
        asyncio.run(_run_stdio())
    elif args.transport == "sse":
        import uvicorn

        path = args.path or "/sse"
        app = _build_sse_app(mcp_path=path)
        logger.info("Starting SSE transport on %s:%d%s", args.host, args.port, path)
        uvicorn.run(app, host=args.host, port=args.port)
    elif args.transport == "streamable-http":
        import uvicorn

        path = args.path or "/mcp"
        app = _build_streamable_http_app(mcp_path=path)
        logger.info(
            "Starting Streamable HTTP transport on %s:%d%s",
            args.host,
            args.port,
            path,
        )
        uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
