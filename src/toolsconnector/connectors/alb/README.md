# AWS ALB

> Distribute traffic across targets with application-layer routing

| | |
|---|---|
| **Company** | Amazon Web Services |
| **Category** | Networking |
| **Protocol** | REST |
| **Website** | [aws.amazon.com/elasticloadbalancing](https://aws.amazon.com/elasticloadbalancing/) |
| **API Docs** | [docs.aws.amazon.com](https://docs.aws.amazon.com/elasticloadbalancing/latest/APIReference/) |
| **Auth** | AWS SigV4 |
| **Rate Limit** | 100 requests/sec |
| **Pricing** | Pay-per-use ($0.0225/ALB-hour + LCU) |

---

## Overview



## Installation

```bash
pip install "toolsconnector[alb]"
```

Set your credentials:

```bash
export TC_ALB_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["alb"], credentials={"alb": "your-token"})

# Create a listener on a load balancer
result = kit.execute("alb_create_listener", {"load_balancer_arn": "your-load_balancer_arn", "port": 80, "protocol": "HTTP"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["alb"], credentials={"alb": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["alb"], credentials={"alb": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### AWS SigV4

1. Create an account at [AWS ALB](https://aws.amazon.com/elasticloadbalancing/)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://console.aws.amazon.com/iam/home#/security_credentials)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("alb_create_listener", {})
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

- Rate limit is 100 requests/sec — use pagination and caching to minimize API calls
- Actions marked as destructive (`delete_listener`, `delete_load_balancer`, `delete_rule`) cannot be undone — use with caution

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
