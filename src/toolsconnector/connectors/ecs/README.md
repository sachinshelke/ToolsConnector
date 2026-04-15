# AWS ECS

> Run and manage Docker containers at scale

| | |
|---|---|
| **Company** | Amazon Web Services |
| **Category** | Devops |
| **Protocol** | REST |
| **Website** | [aws.amazon.com/ecs](https://aws.amazon.com/ecs/) |
| **API Docs** | [docs.aws.amazon.com](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/) |
| **Auth** | AWS SigV4 |
| **Rate Limit** | 20 requests/sec |
| **Pricing** | Pay-per-use (Fargate: per vCPU/GB-hour) |

---

## Overview



## Installation

```bash
pip install "toolsconnector[ecs]"
```

Set your credentials:

```bash
export TC_ECS_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["ecs"], credentials={"ecs": "your-token"})

# List tasks in a cluster
result = kit.execute("ecs_list_tasks", {"cluster": "your-cluster", "service_name": "your-service_name", "desired_status": "RUNNING"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["ecs"], credentials={"ecs": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["ecs"], credentials={"ecs": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### AWS SigV4

1. Create an account at [AWS ECS](https://aws.amazon.com/ecs/)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://console.aws.amazon.com/iam/home#/security_credentials)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("ecs_list_tasks", {})
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

- Rate limit is 20 requests/sec — use pagination and caching to minimize API calls
- Actions marked as destructive (`delete_cluster`, `delete_service`, `stop_task`) cannot be undone — use with caution
- This connector has 25 actions — use `ToolKit(include_actions=[...])` to expose only what your agent needs

## Related Connectors

- [Cloudflare](../cloudflare/) — CDN and security
- [Datadog](../datadog/) — Monitoring
- [Pagerduty](../pagerduty/) — Incident management
- [Vercel](../vercel/) — Frontend deployment

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
