"""
AgentPay Feed — Python client for any agent or framework.

Quick start:
    from client import FeedClient
    feed = FeedClient()
    for event in feed.poll(categories=['tool_registration'], trust=['agentpay_verified']):
        print(event['payload']['tool_name'], event['payload']['endpoint'])
"""

from __future__ import annotations

import time
from typing import Generator, Iterator
import httpx

DEFAULT_FEED_URL = "https://agentpay-feed.apaybeta.workers.dev"


class FeedClient:
    def __init__(self, feed_url: str = DEFAULT_FEED_URL, publish_key: str | None = None):
        self.url = feed_url.rstrip("/")
        self._publish_key = publish_key
        self._http = httpx.Client(timeout=15)

    # ── Read ─────────────────────────────────────────────────────────────────

    def get_events(
        self,
        since: int | None = None,
        categories: list[str] | None = None,
        trust: list[str] | None = None,
        limit: int = 100,
    ) -> dict:
        """Single poll — returns {events, cursor, has_more, count}."""
        params: dict = {"limit": limit}
        if since is not None:
            params["since"] = since
        if categories:
            params["categories"] = ",".join(categories)
        if trust:
            params["trust"] = ",".join(trust)
        resp = self._http.get(f"{self.url}/v1/feed/events", params=params)
        resp.raise_for_status()
        return resp.json()

    def get_event(self, event_id: str) -> dict:
        """Fetch a single event by ID."""
        resp = self._http.get(f"{self.url}/v1/feed/events/{event_id}")
        resp.raise_for_status()
        return resp.json()

    def stats(self) -> dict:
        resp = self._http.get(f"{self.url}/v1/feed/stats")
        resp.raise_for_status()
        return resp.json()

    def agent_card(self) -> dict:
        resp = self._http.get(f"{self.url}/.well-known/agent-card.json")
        resp.raise_for_status()
        return resp.json()

    def poll(
        self,
        interval_ms: int = 10_000,
        categories: list[str] | None = None,
        trust: list[str] | None = None,
        start_from: int = 0,
    ) -> Generator[dict, None, None]:
        """
        Infinite generator — yields FeedEvent dicts as they arrive.
        Handles cursor tracking and reconnect automatically.

        Example:
            for event in feed.poll(categories=['tool_registration']):
                install(event['payload']['install_command'])
        """
        cursor = start_from
        while True:
            try:
                result = self.get_events(since=cursor, categories=categories, trust=trust)
                for event in result.get("events", []):
                    yield event
                cursor = result.get("cursor", {}).get("since_ms", cursor)
            except httpx.HTTPError as e:
                # Back off on transient errors rather than crashing
                print(f"[feed] HTTP error: {e}. Retrying in 30s...")
                time.sleep(30)
                continue
            time.sleep(interval_ms / 1000)

    # ── Write ─────────────────────────────────────────────────────────────────

    def publish(
        self,
        category: str,
        action: str,
        source: str,
        payload: dict,
    ) -> dict:
        """Publish an event. Requires publish_key."""
        if not self._publish_key:
            raise ValueError("publish_key is required for publishing")
        resp = self._http.post(
            f"{self.url}/v1/feed/publish",
            json={"category": category, "action": action, "source": source, "payload": payload},
            headers={"Authorization": f"Bearer {self._publish_key}"},
        )
        resp.raise_for_status()
        return resp.json()

    def register_tool(
        self,
        source: str,
        tool_name: str,
        description: str,
        endpoint: str,
        install_command: str | None = None,
        pricing: dict | None = None,
        tags: list[str] | None = None,
        test_cases: list[dict] | None = None,
    ) -> dict:
        """
        Convenience wrapper — register a tool as a tool_registration event.

        test_cases format (agent-side sandbox protocol):
            [{"name": "basic", "input": {...}, "expected_output_schema": {...}}]
        Consuming agents will run these locally before granting the tool permissions.
        """
        payload: dict = {
            "tool_name": tool_name,
            "description": description,
            "endpoint": endpoint,
        }
        if install_command:
            payload["install_command"] = install_command
        if pricing:
            payload["pricing"] = pricing
        if tags:
            payload["tags"] = tags
        if test_cases:
            payload["test_cases"] = test_cases

        return self.publish("tool_registration", "register", source, payload)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "FeedClient":
        return self

    def __exit__(self, *_) -> None:
        self.close()


# ── Sandbox runner (agent-side) ───────────────────────────────────────────────

def run_sandbox(event: dict, call_fn) -> dict:
    """
    Run an event's test_cases against call_fn (your MCP/tool executor).
    Returns {passed, failed, results} — grant tool access only if failed == 0.

    call_fn signature: call_fn(tool_name: str, input: dict) -> dict

    Example:
        result = run_sandbox(event, my_mcp_client.call_tool)
        if result['failed'] == 0:
            grant_permissions(event['payload']['tool_name'])
    """
    test_cases = event.get("payload", {}).get("test_cases", [])
    if not test_cases:
        return {"passed": 0, "failed": 0, "skipped": True, "results": []}

    tool_name = event["payload"].get("tool_name", "unknown")
    results = []
    passed = failed = 0

    for tc in test_cases:
        name = tc.get("name", "unnamed")
        try:
            output = call_fn(tool_name, tc["input"])
            schema = tc.get("expected_output_schema")
            ok = True
            schema_match = None

            if schema:
                try:
                    import jsonschema  # optional dep
                    jsonschema.validate(output, schema)
                    schema_match = True
                except Exception as e:
                    schema_match = False
                    ok = False

            results.append({"name": name, "ok": ok, "schema_match": schema_match, "output": output})
            if ok:
                passed += 1
            else:
                failed += 1

        except Exception as e:
            results.append({"name": name, "ok": False, "error": str(e)})
            failed += 1

    return {"passed": passed, "failed": failed, "skipped": False, "results": results}
