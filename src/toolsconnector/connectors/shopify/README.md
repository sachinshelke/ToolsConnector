# Shopify

> E-commerce platform for online stores

| | |
|---|---|
| **Company** | Shopify Inc. |
| **Category** | Ecommerce |
| **Protocol** | REST |
| **Website** | [shopify.com](https://shopify.com) |
| **API Docs** | [shopify.dev](https://shopify.dev/docs/api/admin-rest) |
| **Auth** | API Key (Admin API Access Token) |
| **Rate Limit** | 40 requests/second (Plus: 80/sec) |
| **Pricing** | Basic from $39/month |

---

## Overview

The Shopify Admin API provides access to products, orders, customers, inventory, and fulfillments. Manage your online store, process orders, track inventory, handle refunds, and build custom e-commerce integrations.

## Use Cases

- Product catalog management
- Order processing
- Inventory tracking
- Customer management
- Fulfillment automation

## Installation

```bash
pip install toolsconnector[shopify]
```

Set your credentials:

```bash
export TC_SHOPIFY_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["shopify"], credentials={"shopify": "your-token"})

# List products from your Shopify store
result = kit.execute("shopify_list_products", {"limit": 50, "since_id": "your-since_id"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["shopify"], credentials={"shopify": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["shopify"], credentials={"shopify": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### API Key (Admin API Access Token)

1. Create an account at [Shopify](https://shopify.com)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://shopify.dev/docs/apps/build/authentication/access-tokens)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("shopify_list_products", {})
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

- Rate limit is 40 requests/second (Plus: 80/sec) — use pagination and caching to minimize API calls
- Actions marked as destructive (`cancel_order`, `complete_draft_order`, `create_customer`) cannot be undone — use with caution
- This connector has 27 actions — use `ToolKit(include_actions=[...])` to expose only what your agent needs

## Related Connectors

- [Stripe](../stripe/) — Payments

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
