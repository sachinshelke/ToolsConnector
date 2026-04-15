# AWS EC2

> Resizable compute capacity in the cloud

| | |
|---|---|
| **Company** | Amazon Web Services |
| **Category** | Compute |
| **Protocol** | REST |
| **Website** | [aws.amazon.com/ec2](https://aws.amazon.com/ec2/) |
| **API Docs** | [docs.aws.amazon.com](https://docs.aws.amazon.com/AWSEC2/latest/APIReference/) |
| **Auth** | AWS SigV4 |
| **Rate Limit** | 100 requests/sec |
| **Pricing** | Pay-per-use (from $0.0116/hour for t3.micro) |

---

## Overview



## Installation

```bash
pip install "toolsconnector[ec2]"
```

Set your credentials:

```bash
export TC_EC2_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["ec2"], credentials={"ec2": "your-token"})

# Get instance console output
result = kit.execute("ec2_get_console_output", {"instance_id": "your-instance_id"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["ec2"], credentials={"ec2": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["ec2"], credentials={"ec2": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### AWS SigV4

1. Create an account at [AWS EC2](https://aws.amazon.com/ec2/)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://console.aws.amazon.com/iam/home#/security_credentials)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("ec2_get_console_output", {})
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
- Actions marked as destructive (`delete_key_pair`, `delete_security_group`, `release_address`) cannot be undone — use with caution
- This connector has 30 actions — use `ToolKit(include_actions=[...])` to expose only what your agent needs

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
