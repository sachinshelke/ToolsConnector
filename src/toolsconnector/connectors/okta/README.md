# Okta

> Enterprise identity and access management

| | |
|---|---|
| **Company** | Okta Inc. |
| **Category** | Security |
| **Protocol** | REST |
| **Website** | [okta.com](https://okta.com) |
| **API Docs** | [developer.okta.com](https://developer.okta.com/docs/reference/) |
| **Auth** | API Token, OAuth 2.0 |
| **Rate Limit** | Varies by endpoint (typically 600/min) |
| **Pricing** | Contact sales (SSO from $2/user/month) |

---

## Overview

The Okta API provides access to users, groups, applications, and system logs. Manage enterprise identity lifecycle, configure SSO, enforce MFA, audit security events, and automate user provisioning.

## Use Cases

- User lifecycle management
- SSO configuration
- Group and role management
- Security audit logging
- Application provisioning

## Installation

```bash
pip install toolsconnector[okta]
```

Set your credentials:

```bash
export TC_OKTA_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["okta"], credentials={"okta": "your-token"})

# List users in the Okta organization
result = kit.execute("okta_list_users", {"search": "your-search", "filter": "your-filter"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["okta"], credentials={"okta": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["okta"], credentials={"okta": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### API Token

1. Create an account at [Okta](https://okta.com)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://developer.okta.com/docs/guides/create-an-api-token/main/)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("okta_list_users", {})
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

- Rate limit is Varies by endpoint (typically 600/min) — use pagination and caching to minimize API calls
- Actions marked as destructive (`deactivate_user`, `delete_group`, `suspend_user`) cannot be undone — use with caution
- This connector has 21 actions — use `ToolKit(include_actions=[...])` to expose only what your agent needs

## Related Connectors

- [Auth0](../auth0/) — Authentication

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
