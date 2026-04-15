# AWS ACM

> Provision and manage SSL/TLS certificates

| | |
|---|---|
| **Company** | Amazon Web Services |
| **Category** | Security |
| **Protocol** | REST |
| **Website** | [aws.amazon.com/certificate-manager](https://aws.amazon.com/certificate-manager/) |
| **API Docs** | [docs.aws.amazon.com](https://docs.aws.amazon.com/acm/latest/APIReference/) |
| **Auth** | AWS SigV4 |
| **Rate Limit** | 20 requests/sec |
| **Pricing** | Free for public certificates |

---

## Overview



## Installation

```bash
pip install "toolsconnector[acm]"
```

Set your credentials:

```bash
export TC_ACM_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["acm"], credentials={"acm": "your-token"})

# Get the certificate PEM and chain
result = kit.execute("acm_get_certificate", {"certificate_arn": "your-certificate_arn"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["acm"], credentials={"acm": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["acm"], credentials={"acm": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### AWS SigV4

1. Create an account at [AWS ACM](https://aws.amazon.com/certificate-manager/)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://console.aws.amazon.com/iam/home#/security_credentials)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("acm_get_certificate", {})
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
- Actions marked as destructive (`delete_certificate`) cannot be undone — use with caution

## Related Connectors

- [Okta](../okta/) — Identity management
- [Auth0](../auth0/) — Authentication

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
