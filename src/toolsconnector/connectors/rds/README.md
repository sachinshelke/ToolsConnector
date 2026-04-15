# AWS RDS

> Managed relational databases — PostgreSQL, MySQL, Aurora

| | |
|---|---|
| **Company** | Amazon Web Services |
| **Category** | Database |
| **Protocol** | REST |
| **Website** | [aws.amazon.com/rds](https://aws.amazon.com/rds/) |
| **API Docs** | [docs.aws.amazon.com](https://docs.aws.amazon.com/AmazonRDS/latest/APIReference/) |
| **Auth** | AWS SigV4 |
| **Rate Limit** | 25 requests/sec |
| **Pricing** | Pay-per-use (from $0.017/hour for db.t3.micro) |

---

## Overview



## Installation

```bash
pip install "toolsconnector[rds]"
```

Set your credentials:

```bash
export TC_RDS_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["rds"], credentials={"rds": "your-token"})

# List tags for a database resource
result = kit.execute("rds_list_tags_for_resource", {"resource_name": "your-resource_name"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["rds"], credentials={"rds": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["rds"], credentials={"rds": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### AWS SigV4

1. Create an account at [AWS RDS](https://aws.amazon.com/rds/)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://console.aws.amazon.com/iam/home#/security_credentials)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("rds_list_tags_for_resource", {})
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

- Rate limit is 25 requests/sec — use pagination and caching to minimize API calls
- Actions marked as destructive (`create_db_cluster`, `create_db_instance`, `delete_db_cluster`) cannot be undone — use with caution
- This connector has 25 actions — use `ToolKit(include_actions=[...])` to expose only what your agent needs

## Related Connectors

- [Airtable](../airtable/) — Spreadsheet database
- [Firestore](../firestore/) — Document database
- [Mongodb](../mongodb/) — NoSQL database
- [Redis](../redis/) — Key-value store

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
