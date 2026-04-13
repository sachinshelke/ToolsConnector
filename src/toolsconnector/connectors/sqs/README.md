# AWS SQS

> Fully managed message queuing service

| | |
|---|---|
| **Company** | Amazon Web Services |
| **Category** | Message Queue |
| **Protocol** | REST |
| **Website** | [aws.amazon.com/sqs](https://aws.amazon.com/sqs/) |
| **API Docs** | [docs.aws.amazon.com](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/APIReference/) |
| **Auth** | AWS SigV4 (Access Key + Secret Key) |
| **Rate Limit** | Unlimited (Standard), 300 msg/sec (FIFO) |
| **Pricing** | Free tier (1M requests/month), then $0.40/million |

---

## Overview

The AWS SQS API provides message queuing operations for decoupling distributed systems. Send, receive, and delete messages. Manage queues, configure dead-letter queues, and build reliable event-driven architectures.

## Use Cases

- Microservice decoupling
- Task queuing
- Event-driven architectures
- Batch processing
- Dead-letter queue management

## Installation

```bash
pip install toolsconnector[sqs]
```

Set your credentials:

```bash
export TC_SQS_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["sqs"], credentials={"sqs": "your-token"})

# List SQS queues in the account
result = kit.execute("sqs_list_queues", {"prefix": "your-prefix"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["sqs"], credentials={"sqs": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["sqs"], credentials={"sqs": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### AWS SigV4 (Access Key + Secret Key)

1. Create an account at [AWS SQS](https://aws.amazon.com/sqs/)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://console.aws.amazon.com/iam/home#/security_credentials)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("sqs_list_queues", {})
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

- Use batch operations (`send_message_batch`) for bulk operations instead of individual calls
- Rate limit is Unlimited (Standard), 300 msg/sec (FIFO) — use pagination and caching to minimize API calls
- Actions marked as destructive (`add_permission`, `delete_message`, `delete_queue`) cannot be undone — use with caution

## Related Connectors

- [Rabbitmq](../rabbitmq/) — Message broker

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
