# SendGrid

> Transactional and marketing email delivery

| | |
|---|---|
| **Company** | Twilio (SendGrid) |
| **Category** | Marketing |
| **Protocol** | REST |
| **Website** | [sendgrid.com](https://sendgrid.com) |
| **API Docs** | [docs.sendgrid.com](https://docs.sendgrid.com/api-reference) |
| **Auth** | API Key |
| **Rate Limit** | Varies by plan |
| **Pricing** | Free up to 100 emails/day, Essentials from $19.95/month |

---

## Overview

The SendGrid API provides email sending, template management, contact lists, and analytics. Send transactional and marketing emails at scale, manage dynamic templates, track opens and clicks, and maintain sender reputation.

## Use Cases

- Transactional email
- Marketing campaigns
- Email template management
- Delivery analytics
- Sender reputation management

## Installation

```bash
pip install "toolsconnector[sendgrid]"
```

Set your credentials:

```bash
export TC_SENDGRID_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["sendgrid"], credentials={"sendgrid": "your-token"})

# List marketing contacts from SendGrid
result = kit.execute("sendgrid_list_contacts", {"limit": 50})
print(result)
```

### MCP Server

```python
kit = ToolKit(["sendgrid"], credentials={"sendgrid": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["sendgrid"], credentials={"sendgrid": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### API Key

1. Create an account at [SendGrid](https://sendgrid.com)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://app.sendgrid.com/settings/api_keys)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("sendgrid_list_contacts", {})
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

- Use `search_contacts` for filtered queries and `list_contacts` for paginated browsing
- Rate limit is Varies by plan — use pagination and caching to minimize API calls
- Actions marked as destructive (`add_contacts`, `add_to_suppression`, `create_list`) cannot be undone — use with caution

## Related Connectors

- [Mailchimp](../mailchimp/) — Email marketing

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
