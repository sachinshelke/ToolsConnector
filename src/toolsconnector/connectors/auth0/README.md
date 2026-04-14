# Auth0

> Identity platform for authentication and authorization

| | |
|---|---|
| **Company** | Okta (Auth0) |
| **Category** | Security |
| **Protocol** | REST |
| **Website** | [auth0.com](https://auth0.com) |
| **API Docs** | [auth0.com](https://auth0.com/docs/api/management/v2) |
| **Auth** | Bearer Token (Management API Token) |
| **Rate Limit** | Varies by endpoint (typically 50-100/sec) |
| **Pricing** | Free up to 7,500 MAUs, Professional from $240/month |

---

## Overview

The Auth0 Management API lets you manage users, connections, roles, and applications in your Auth0 tenant. Configure authentication flows, manage user profiles, assign permissions, and monitor security events.

## Use Cases

- User management
- Role-based access control
- SSO configuration
- Passwordless authentication
- Security auditing

## Installation

```bash
pip install "toolsconnector[auth0]"
```

Set your credentials:

```bash
export TC_AUTH0_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["auth0"], credentials={"auth0": "your-token"})

# List users in the Auth0 tenant
result = kit.execute("auth0_list_users", {"search": "your-search", "limit": 50})
print(result)
```

### MCP Server

```python
kit = ToolKit(["auth0"], credentials={"auth0": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["auth0"], credentials={"auth0": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### Bearer Token (Management API Token)

1. Create an account at [Auth0](https://auth0.com)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://manage.auth0.com/#/apis/management/explorer)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("auth0_list_users", {})
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

- Rate limit is Varies by endpoint (typically 50-100/sec) — use pagination and caching to minimize API calls
- Actions marked as destructive (`assign_permissions`, `block_user`, `create_connection`) cannot be undone — use with caution
- This connector has 27 actions — use `ToolKit(include_actions=[...])` to expose only what your agent needs

## Related Connectors

- [Okta](../okta/) — Identity management

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
