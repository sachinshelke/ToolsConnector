# Pinecone

> Vector database for AI and machine learning

| | |
|---|---|
| **Company** | Pinecone Systems Inc. |
| **Category** | Ai Ml |
| **Protocol** | REST |
| **Website** | [pinecone.io](https://pinecone.io) |
| **API Docs** | [docs.pinecone.io](https://docs.pinecone.io/reference/api/introduction) |
| **Auth** | API Key |
| **Rate Limit** | Varies by plan and pod type |
| **Pricing** | Free tier (Starter), Standard from $70/month |

---

## Overview

The Pinecone API provides vector database operations for AI applications. Upsert, query, and manage high-dimensional vector embeddings. Build semantic search, recommendation engines, RAG pipelines, and anomaly detection systems.

## Use Cases

- Semantic search
- RAG (Retrieval-Augmented Generation)
- Recommendation engines
- Anomaly detection
- Image similarity

## Installation

```bash
pip install "toolsconnector[pinecone]"
```

Set your credentials:

```bash
export TC_PINECONE_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["pinecone"], credentials={"pinecone": "your-token"})

# List vector IDs in the index
result = kit.execute("pinecone_list_vectors", {"prefix": "your-prefix", "namespace": "default"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["pinecone"], credentials={"pinecone": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["pinecone"], credentials={"pinecone": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### API Key

1. Create an account at [Pinecone](https://pinecone.io)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://app.pinecone.io/)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("pinecone_list_vectors", {})
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

- Rate limit is Varies by plan and pod type — use pagination and caching to minimize API calls
- Actions marked as destructive (`create_collection`, `create_index`, `delete`) cannot be undone — use with caution

## Related Connectors

- [Openai](../openai/) — GPT models
- [Anthropic](../anthropic/) — Claude models

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
