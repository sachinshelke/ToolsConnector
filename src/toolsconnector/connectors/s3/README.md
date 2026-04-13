# AWS S3

> Scalable object storage in the cloud

| | |
|---|---|
| **Company** | Amazon Web Services |
| **Category** | Storage |
| **Protocol** | REST |
| **Website** | [aws.amazon.com/s3](https://aws.amazon.com/s3/) |
| **API Docs** | [docs.aws.amazon.com](https://docs.aws.amazon.com/AmazonS3/latest/API/) |
| **Auth** | AWS SigV4 (Access Key + Secret Key) |
| **Rate Limit** | 5,500 GET/sec, 3,500 PUT/sec per prefix |
| **Pricing** | Pay-per-use (from $0.023/GB/month) |

---

## Overview

The AWS S3 API provides object storage operations for buckets and objects. Upload, download, list, and manage files. Configure lifecycle policies, access permissions, versioning, and static website hosting.

## Use Cases

- File storage and retrieval
- Static website hosting
- Data lake storage
- Backup and archival
- Content distribution

## Installation

```bash
pip install toolsconnector[s3]
```

Set your credentials:

```bash
export TC_S3_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["s3"], credentials={"s3": "your-token"})

# Get the region (location) of an S3 bucket
result = kit.execute("s3_get_bucket_location", {"bucket": "my-bucket"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["s3"], credentials={"s3": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["s3"], credentials={"s3": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### AWS SigV4 (Access Key + Secret Key)

1. Create an account at [AWS S3](https://aws.amazon.com/s3/)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://console.aws.amazon.com/iam/home#/security_credentials)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("s3_get_bucket_location", {})
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

- Rate limit is 5,500 GET/sec, 3,500 PUT/sec per prefix — use pagination and caching to minimize API calls
- Actions marked as destructive (`create_bucket`, `delete_bucket`, `delete_object`) cannot be undone — use with caution

## Related Connectors

- [Gdrive](../gdrive/) — Google storage

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
