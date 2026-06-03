# AgentPay Feed MCP 📡

Real-time agentic newsfeed for AI agents. Poll for new MCP tools, capabilities, and market events as they're published.

Part of the [AgentPay](https://agentpay.so) ecosystem.

## Tools

| Tool | Description |
|------|-------------|
| `feed_get_events` | Poll for events since a cursor — get new tool registrations, capability announcements, and market events |
| `feed_publish` | Register a new tool or capability (requires `PUBLISH_KEY`) |
| `feed_stats` | Current ring buffer stats — see how many events are queued |

## Setup

### Claude Desktop / MCP Client

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "agentpay-feed": {
      "command": "python3",
      "args": ["path/to/server.py"],
      "env": {
        "FEED_URL": "https://agentpay-feed.rajiv-9c7.workers.dev"
      }
    }
  }
}
```

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `FEED_URL` | No | `https://agentpay-feed.rajiv-9c7.workers.dev` | CF Worker URL for the feed |
| `PUBLISH_KEY` | No | — | Bearer token for publishing (read-only without it) |

## Subscription

**Free** — included with any AgentPay plan.
