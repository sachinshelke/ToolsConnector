# Mailchimp

> Email marketing and audience management

| | |
|---|---|
| **Company** | Intuit (Mailchimp) |
| **Category** | Marketing |
| **Protocol** | REST |
| **Website** | [mailchimp.com](https://mailchimp.com) |
| **API Docs** | [mailchimp.com](https://mailchimp.com/developer/marketing/api/) |
| **Auth** | API Key |
| **Rate Limit** | 10 concurrent connections |
| **Pricing** | Free up to 500 contacts, Essentials from $13/month |

---

## Overview

The Mailchimp Marketing API provides access to audiences, campaigns, templates, and automations. Manage subscriber lists, create and send email campaigns, set up automation workflows, and track engagement analytics.

## Use Cases

- Email campaign management
- Subscriber list management
- Marketing automation
- A/B testing
- Engagement analytics

## Installation

```bash
pip install "toolsconnector[mailchimp]"
```

Set your credentials:

```bash
export TC_MAILCHIMP_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["mailchimp"], credentials={"mailchimp": "your-token"})

# Get a single Mailchimp campaign by ID
result = kit.execute("mailchimp_get_campaign", {"campaign_id": "campaign-123"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["mailchimp"], credentials={"mailchimp": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["mailchimp"], credentials={"mailchimp": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### API Key

1. Create an account at [Mailchimp](https://mailchimp.com)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://mailchimp.com/help/about-api-keys/)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("mailchimp_get_campaign", {})
except RateLimitError as e:
    print(f"Rate limited. Retry in {e.retry_after_seconds}s")
except AuthError as e:
    print(f"Auth failed: {e.suggestion}")
```

## Actions

<!-- ACTIONS_START -->
<!-- This section is auto-generated from the connector spec. Do not edit manually. -->
<!-- ACTIONS_END -->

## Tips

- Rate limit is 10 concurrent connections — use pagination and caching to minimize API calls
- Actions marked as destructive (`add_member`, `create_campaign`, `create_segment`) cannot be undone — use with caution
- This connector has 23 actions — use `ToolKit(include_actions=[...])` to expose only what your agent needs

## Related Connectors

- [Sendgrid](../sendgrid/) — Email delivery

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
