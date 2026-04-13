# ToolsConnector

The universal tool-connection primitive for Python. Connect any AI agent or traditional application to 53+ external APIs through one standardized interface.

## What is ToolsConnector?

ToolsConnector is a foundational library that standardizes how applications connect to external tools -- Gmail, Slack, GitHub, Stripe, and 46 more. Whether you are building a Flask cron job, a Django webhook handler, or a Claude AI agent, ToolsConnector gives you a single, consistent interface to discover, validate, and execute tool calls across every supported service.

Every connector follows the same pattern: authenticate with BYOK (Bring Your Own Key), discover available actions, and execute them with typed parameters. The library handles retries, rate limiting, pagination, and schema generation so your code does not have to.

## Why ToolsConnector?

| Concern | Raw SDKs | Composio | ToolsConnector |
|---|---|---|---|
| Interface consistency | Each SDK is different | Proprietary abstraction | Standardized `ToolKit` with `@action` pattern |
| AI schema generation | Manual per provider | Built-in but locked to their platform | Native OpenAI, Anthropic, Gemini, and MCP output |
| Auth model | Varies wildly | Managed (vendor lock-in) | BYOK -- you own your tokens |
| Deployment | N/A | SaaS dependency | Self-hosted, zero external calls |
| Dangerous action safety | None | None | Built-in `dangerous` flag per action |
| Pricing | Free (per SDK) | Per-seat SaaS | Open source, free forever |

## Quick Example

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["gmail", "slack"], credentials={
    "gmail": "ya29.your-token",
    "slack": "xoxb-your-token",
})
result = kit.execute("gmail_list_emails", {"query": "is:unread", "max_results": 5})
```

## Key Features

- **53 connectors, 1,137 actions** across 17 categories -- communication, CRM, databases, DevOps, AI/ML, finance, and more.
- **One interface for everything.** `ToolKit.execute()` works the same whether you are sending a Slack message or querying MongoDB.
- **AI-native schema generation.** Export tool definitions for OpenAI, Anthropic, Gemini, or MCP with a single method call.
- **Built-in MCP server.** Serve any combination of connectors to Claude Desktop, Cursor, or any MCP-compatible client.
- **REST server.** Expose connectors as a REST API with one command.
- **Dangerous action safety.** Every mutating or side-effecting action is flagged with `dangerous=True` so agents can ask for confirmation.
- **Resilience built in.** Automatic retries with exponential backoff, circuit breakers, and rate-limit handling.
- **Async-first, sync-compatible.** Every action supports both `execute()` and `aexecute()`.
- **CLI included.** The `tc` command lets you list connectors, execute actions, and start servers from your terminal.
- **Zero vendor lock-in.** BYOK auth model, self-hosted, no external service dependencies.

## Architecture

ToolsConnector is structured in three layers:

1. **Connectors** -- individual API integrations that subclass `BaseConnector` and expose `@action` methods.
2. **Serve** -- the `ToolKit` orchestration layer that loads connectors, generates schemas, and dispatches calls.
3. **Protocol Adapters** -- MCP, REST, and AI-provider schema generators that translate the internal action model to external protocols.

## Getting Started

- [Quickstart](guides/quickstart.md) -- zero to a working tool call in under 5 minutes
- [Installation](guides/installation.md) -- detailed install options and extras
- [Credentials Guide](guides/credentials.md) -- authentication patterns for every connector
- [MCP Server](guides/mcp-server.md) -- serve connectors to Claude Desktop and Cursor
- [AI Frameworks](guides/ai-frameworks.md) -- integrate with OpenAI, Anthropic, Gemini, LangChain, and CrewAI
- [CLI Reference](guides/cli.md) -- full command reference for the `tc` command
- [All Connectors](connectors/README.md) -- browse every connector by category
