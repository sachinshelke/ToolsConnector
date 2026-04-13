# Plaid

> Financial data connectivity and banking APIs

| | |
|---|---|
| **Company** | Plaid Inc. |
| **Category** | Finance |
| **Protocol** | REST |
| **Website** | [plaid.com](https://plaid.com) |
| **API Docs** | [plaid.com](https://plaid.com/docs/api/) |
| **Auth** | API Key (Client ID + Secret) |
| **Rate Limit** | Varies by product |
| **Pricing** | Pay per connection (custom pricing) |

---

## Overview

The Plaid API provides access to financial account data, transactions, balances, and identity information. Connect to bank accounts, verify identity, check balances, categorize transactions, and power fintech applications.

## Use Cases

- Bank account linking
- Transaction history
- Balance verification
- Identity verification
- Financial data aggregation

## Installation

```bash
pip install toolsconnector[plaid]
```

Set your credentials:

```bash
export TC_PLAID_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["plaid"], credentials={"plaid": "your-token"})

# Get accounts linked to an access token
result = kit.execute("plaid_get_accounts", {"access_token": "your-access_token"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["plaid"], credentials={"plaid": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["plaid"], credentials={"plaid": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### API Key (Client ID + Secret)

1. Create an account at [Plaid](https://plaid.com)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://dashboard.plaid.com/team/keys)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("plaid_get_accounts", {})
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

- Rate limit is Varies by product — use pagination and caching to minimize API calls
- Actions marked as destructive (`remove_item`) cannot be undone — use with caution

## Related Connectors

- [Stripe](../stripe/) — Payments

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
