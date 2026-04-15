# AWS Lambda

> Run code without provisioning or managing servers

| | |
|---|---|
| **Company** | Amazon Web Services |
| **Category** | Compute |
| **Protocol** | REST |
| **Website** | [aws.amazon.com/lambda](https://aws.amazon.com/lambda/) |
| **API Docs** | [docs.aws.amazon.com](https://docs.aws.amazon.com/lambda/latest/api/) |
| **Auth** | AWS SigV4 |
| **Rate Limit** | 100 requests/sec |
| **Pricing** | Free tier: 1M requests/month, then $0.20/1M |

---

## Overview



## Installation

```bash
pip install "toolsconnector[lambda_connector]"
```

Set your credentials:

```bash
export TC_LAMBDA_CONNECTOR_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["lambda_connector"], credentials={"lambda_connector": "your-token"})

# Get a function alias
result = kit.execute("lambda_connector_get_alias", {"function_name": "your-function_name", "name": "my-name"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["lambda_connector"], credentials={"lambda_connector": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["lambda_connector"], credentials={"lambda_connector": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### AWS SigV4

1. Create an account at [AWS Lambda](https://aws.amazon.com/lambda/)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://console.aws.amazon.com/iam/home#/security_credentials)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("lambda_connector_get_alias", {})
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
- Actions marked as destructive (`create_function`, `delete_function`) cannot be undone — use with caution

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
