#!/usr/bin/env python3
"""
AgentPay Feed MCP Server
========================
Gives agents access to the AgentPay agentic newsfeed.
Poll for new tools, capabilities, and market events in real time.

Tools:
  feed_get_events   — poll for events since a cursor
  feed_publish      — register a tool or capability (requires PUBLISH_KEY)
  feed_stats        — current ring buffer stats

Env:
  FEED_URL          — CF Worker URL (default: https://agentpay-feed.rajiv-9c7.workers.dev)
  PUBLISH_KEY       — Bearer token for publishing (optional, read-only without it)
"""

from __future__ import annotations

import json
import os
import time
import httpx
from mcp.server.lowlevel import Server
from mcp.types import Tool, TextContent
import anyio

FEED_URL = os.getenv("FEED_URL", "https://agentpay-feed.apaybeta.workers.dev")
PUBLISH_KEY = os.getenv("PUBLISH_KEY", "")

server = Server("agentpay-feed-mcp")


def _get(path: str, params: dict | None = None) -> dict:
    resp = httpx.get(f"{FEED_URL}{path}", params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _post(path: str, body: dict) -> dict:
    if not PUBLISH_KEY:
        raise ValueError("PUBLISH_KEY env var is required to publish events")
    resp = httpx.post(
        f"{FEED_URL}{path}",
        json=body,
        headers={"Authorization": f"Bearer {PUBLISH_KEY}"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="feed_get_events",
            description=(
                "Poll the AgentPay feed for new tool registrations, capabilities, and market events. "
                "Pass since_ms from the previous response cursor to get only new events. "
                "Omit since_ms to get the last 100 events."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "since_ms": {
                        "type": "integer",
                        "description": "Unix timestamp in milliseconds — return only events after this. "
                        "Use cursor.since_ms from a previous response.",
                    },
                    "categories": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "tool_registration",
                                "market_update",
                                "capability",
                                "runtime",
                                "system",
                            ],
                        },
                        "description": "Filter to specific event categories.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max events to return (1-200, default 100).",
                        "default": 100,
                    },
                },
            },
        ),
        Tool(
            name="feed_publish",
            description=(
                "Publish a tool registration, capability announcement, or market update to the AgentPay feed. "
                "Requires PUBLISH_KEY env var. Other agents polling the feed will see this event."
            ),
            inputSchema={
                "type": "object",
                "required": ["category", "action", "source", "payload"],
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": [
                            "tool_registration",
                            "market_update",
                            "capability",
                            "runtime",
                            "system",
                        ],
                    },
                    "action": {
                        "type": "string",
                        "enum": [
                            "register",
                            "update",
                            "deprecate",
                            "announce",
                            "heartbeat",
                            "price_change",
                            "availability",
                        ],
                    },
                    "source": {
                        "type": "string",
                        "description": "Publisher identifier, e.g. 'agentpay-labs' or 'my-org'.",
                    },
                    "payload": {
                        "type": "object",
                        "description": "Event payload. For tool_registration include tool_name, description, endpoint, pricing.",
                        "properties": {
                            "tool_name": {"type": "string"},
                            "description": {"type": "string"},
                            "endpoint": {"type": "string"},
                            "install_command": {"type": "string"},
                            "pricing": {
                                "type": "object",
                                "properties": {
                                    "per_call": {"type": "number"},
                                    "monthly": {"type": "number"},
                                    "currency": {"type": "string"},
                                    "model": {
                                        "type": "string",
                                        "enum": ["per_call", "subscription", "free"],
                                    },
                                },
                            },
                            "tags": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                },
            },
        ),
        Tool(
            name="feed_stats",
            description="Get AgentPay feed statistics: total events published, current ring buffer size.",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "feed_get_events":
            params: dict = {}
            if "since_ms" in arguments:
                params["since"] = arguments["since_ms"]
            if "categories" in arguments and arguments["categories"]:
                params["categories"] = ",".join(arguments["categories"])
            if "limit" in arguments:
                params["limit"] = arguments["limit"]

            result = _get("/v1/feed/events", params)
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "feed_publish":
            result = _post("/v1/feed/publish", arguments)
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "feed_stats":
            result = _get("/v1/feed/stats")
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except httpx.HTTPStatusError as e:
        return [TextContent(type="text", text=f"HTTP {e.response.status_code}: {e.response.text}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {e}")]


async def main():
    from mcp.server.stdio import stdio_server
    async with stdio_server() as (r, w):
        await server.run(r, w, server.create_initialization_options())


if __name__ == "__main__":
    anyio.run(main)
