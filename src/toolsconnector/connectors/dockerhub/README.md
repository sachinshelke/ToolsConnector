# Docker Hub

> Container registry and image management

| | |
|---|---|
| **Company** | Docker Inc. |
| **Category** | Devops |
| **Protocol** | REST |
| **Website** | [hub.docker.com](https://hub.docker.com) |
| **API Docs** | [docs.docker.com](https://docs.docker.com/docker-hub/api/latest/) |
| **Auth** | Personal Access Token |
| **Rate Limit** | 100 pulls/6 hours (anonymous), 200 (authenticated) |
| **Pricing** | Free tier, Pro from $5/month |

---

## Overview

The Docker Hub API provides access to repositories, images, tags, and organizations. Search for images, manage repository settings, check image vulnerabilities, and automate container image lifecycle management.

## Use Cases

- Image registry management
- Vulnerability scanning automation
- CI/CD image publishing
- Repository access control
- Image tag management

## Installation

```bash
pip install toolsconnector[dockerhub]
```

Set your credentials:

```bash
export TC_DOCKERHUB_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["dockerhub"], credentials={"dockerhub": "your-token"})

# List repositories for a Docker Hub namespace
result = kit.execute("dockerhub_list_repos", {"namespace": "default", "limit": 25, "page": "your-page"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["dockerhub"], credentials={"dockerhub": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["dockerhub"], credentials={"dockerhub": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### Personal Access Token

1. Create an account at [Docker Hub](https://hub.docker.com)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://hub.docker.com/settings/security)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("dockerhub_list_repos", {})
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

- Use `search_repos` for filtered queries and `list_build_triggers` for paginated browsing
- Rate limit is 100 pulls/6 hours (anonymous), 200 (authenticated) — use pagination and caching to minimize API calls
- Actions marked as destructive (`create_repo`, `delete_tag`) cannot be undone — use with caution

## Related Connectors

- [Cloudflare](../cloudflare/) — CDN and security
- [Datadog](../datadog/) — Monitoring
- [Pagerduty](../pagerduty/) — Incident management
- [Vercel](../vercel/) — Frontend deployment

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
