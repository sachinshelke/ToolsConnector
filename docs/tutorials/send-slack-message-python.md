# How to Send a Slack Message in Python (2026)

A complete, copy-paste guide to sending Slack messages from Python — with a bot
token, no Slack SDK, and the same one-line interface you'd use for any other API.

ToolsConnector wraps the Slack Web API behind a single `execute()` call, so the
code looks identical whether you're writing a script, a Django view, or an AI
agent tool.

## TL;DR

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["slack"], credentials={"slack": "xoxb-your-bot-token"})
kit.execute("slack_send_message", {"channel": "#general", "text": "Hello from Python 👋"})
```

That's the whole thing. The rest of this guide covers getting the token, the
options, and the errors you'll hit.

## 1. Install

```bash
pip install "toolsconnector[slack]"
```

Core dependencies are just `pydantic`, `httpx`, and `docstring-parser` — no heavy
Slack SDK pulled in.

## 2. Get a bot token

1. Go to **api.slack.com/apps** → **Create New App** → *From scratch*.
2. Under **OAuth & Permissions**, add the bot scope **`chat:write`** (and
   `chat:write.public` if you want to post to channels the bot hasn't joined).
3. **Install to Workspace** → copy the **Bot User OAuth Token**. It starts with
   `xoxb-`.
4. Invite the bot to the target channel: in Slack, type `/invite @YourBot` in the
   channel (or post to a public channel with `chat:write.public`).

ToolsConnector is **BYOK** (bring your own key) — it never stores or proxies your
token. Pass it at the call site or via the `TC_SLACK_CREDENTIALS` env var.

## 3. Send a message

```python
import json
from toolsconnector.serve import ToolKit

kit = ToolKit(["slack"], credentials={"slack": "xoxb-your-bot-token"})

result = json.loads(kit.execute("slack_send_message", {
    "channel": "#general",      # channel name or ID (C0123…)
    "text": "Deploy finished ✅",
}))
print(result["ts"])  # message timestamp — keep it to reply in-thread later
```

### Reply in a thread

Pass the parent message's `ts` as `thread_ts`:

```python
kit.execute("slack_send_message", {
    "channel": "#general",
    "text": "…and tests passed too.",
    "thread_ts": result["ts"],
})
```

### Rich formatting with Block Kit

`text` supports Slack `mrkdwn` (`*bold*`, `` `code` ``, `<url|link>`). For richer
layouts, pass `blocks` (a list of Block Kit dicts) alongside a `text` fallback.

## 4. Async (for agents and high-throughput apps)

The same connector is dual-use. In async code, use the `a`-prefixed method:

```python
import asyncio
from toolsconnector.connectors.slack import Slack

async def main():
    slack = Slack(credentials="xoxb-your-bot-token")
    await slack._setup()
    await slack.asend_message(channel="#general", text="async hello")

asyncio.run(main())
```

## 5. Use it as an AI agent tool

Because the schema is auto-generated, you can hand `slack_send_message` to an LLM
with one call:

```python
kit = ToolKit(["slack"], credentials={"slack": "xoxb-…"})
tools = kit.to_openai_tools()        # OpenAI function-calling schema
# tools = kit.to_anthropic_tools()   # Anthropic tool-use schema
# kit.serve_mcp()                    # or expose over MCP to Claude Desktop / Cursor
```

The model decides when to call it; `kit.execute()` runs it.

## Common errors

| Error | Cause | Fix |
|---|---|---|
| `not_in_channel` | Bot isn't a member of the channel | `/invite @YourBot` in the channel, or add the `chat:write.public` scope |
| `channel_not_found` | Wrong channel name/ID, or a private channel the bot can't see | Use the channel ID (`C0123…`); invite the bot to private channels |
| `invalid_auth` / `InvalidCredentialsError` | Token is wrong, revoked, or not a bot token | Reinstall the app; confirm it's the `xoxb-` bot token, not `xoxp-` |
| `missing_scope` | Token lacks `chat:write` | Add the scope under OAuth & Permissions, then **reinstall** the app |
| `RateLimitError` | Hit Slack's Tier-2 (~1 msg/sec) limit | Back off using `e.retry_after_seconds`; batch where possible |

ToolsConnector maps these to typed exceptions (`InvalidCredentialsError`,
`PermissionDeniedError`, `RateLimitError`, …) so you can branch on them instead
of parsing strings.

## Next steps

- [Slack connector reference](https://toolsconnector.github.io/#/connectors/slack) — all actions (channels, files, reactions, users)
- [MCP server guide](https://toolsconnector.github.io/#/docs/mcp-server) — expose Slack to Claude Desktop / Cursor
- [AI frameworks guide](https://toolsconnector.github.io/#/docs/ai-frameworks) — OpenAI / Anthropic / Gemini / LangChain

---

*Part of [ToolsConnector](https://toolsconnector.github.io) — one open-source Python interface to 74 APIs, for AI agents and apps.*
