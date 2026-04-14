# Stripe

> Payment processing, subscriptions, and billing

| | |
|---|---|
| **Company** | Stripe Inc. |
| **Category** | Finance |
| **Protocol** | REST |
| **Website** | [stripe.com](https://stripe.com) |
| **API Docs** | [docs.stripe.com](https://docs.stripe.com/api) |
| **Auth** | API Key (Secret Key) |
| **Rate Limit** | 100 read/sec, 100 write/sec |
| **Pricing** | 2.9% + 30c per transaction |

---

## Overview

The Stripe API provides a complete payment infrastructure. Process payments, manage subscriptions, handle invoices, issue refunds, and build checkout experiences. Supports cards, bank transfers, and 100+ payment methods worldwide.

## Use Cases

- Payment processing
- Subscription management
- Invoice generation
- Marketplace payments
- Revenue analytics

## Installation

```bash
pip install "toolsconnector[stripe]"
```

Set your credentials:

```bash
export TC_STRIPE_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["stripe"], credentials={"stripe": "your-token"})

# List events from your Stripe account
result = kit.execute("stripe_list_events", {"type": "your-type", "limit": 10})
print(result)
```

### MCP Server

```python
kit = ToolKit(["stripe"], credentials={"stripe": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["stripe"], credentials={"stripe": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### API Key (Secret Key)

1. Dashboard
2. Developers
3. API Keys

[Get credentials &rarr;](https://dashboard.stripe.com/apikeys)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("stripe_list_events", {})
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

- Rate limit is 100 read/sec, 100 write/sec — use pagination and caching to minimize API calls
- Actions marked as destructive (`cancel_subscription`, `capture_payment_intent`, `close_dispute`) cannot be undone — use with caution
- Use cursor-based pagination for large result sets — pass the `cursor` from previous responses
- This connector has 40 actions — use `ToolKit(include_actions=[...])` to expose only what your agent needs

## Related Connectors

- [Plaid](../plaid/) — Banking data

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
