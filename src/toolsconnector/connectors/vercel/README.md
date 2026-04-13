# Vercel

> Frontend deployment and serverless platform

| | |
|---|---|
| **Company** | Vercel Inc. |
| **Category** | Devops |
| **Protocol** | REST |
| **Website** | [vercel.com](https://vercel.com) |
| **API Docs** | [vercel.com](https://vercel.com/docs/rest-api) |
| **Auth** | Bearer Token |
| **Rate Limit** | Varies by endpoint |
| **Pricing** | Free tier (Hobby), Pro from $20/user/month |

---

## Overview

The Vercel API provides access to projects, deployments, domains, and environment variables. Deploy applications, manage domains, configure environment settings, and automate your frontend CI/CD pipeline.

## Use Cases

- Deployment automation
- Domain management
- Environment variable management
- Project configuration
- Build monitoring

## Installation

```bash
pip install toolsconnector[vercel]
```

Set your credentials:

```bash
export TC_VERCEL_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["vercel"], credentials={"vercel": "your-token"})

# List Vercel projects
result = kit.execute("vercel_list_projects", {"limit": 20, "page": "your-page"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["vercel"], credentials={"vercel": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["vercel"], credentials={"vercel": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### Bearer Token

1. Create an account at [Vercel](https://vercel.com)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://vercel.com/account/tokens)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("vercel_list_projects", {})
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

- Rate limit is Varies by endpoint — use pagination and caching to minimize API calls
- Actions marked as destructive (`add_domain`, `create_env_var`, `delete_deployment`) cannot be undone — use with caution

## Related Connectors

- [Cloudflare](../cloudflare/) — CDN and security
- [Datadog](../datadog/) — Monitoring
- [Pagerduty](../pagerduty/) — Incident management
- [Dockerhub](../dockerhub/) — Container registry

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
