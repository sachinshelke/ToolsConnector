# Cohere

> Chat, embeddings, rerank, and classification models

| | |
|---|---|
| **Company** | Cohere |
| **Category** | Ai Ml |
| **Protocol** | REST |
| **Website** | [cohere.com](https://cohere.com) |
| **API Docs** | [docs.cohere.com](https://docs.cohere.com/reference/about) |
| **Auth** | API Key |
| **Rate Limit** | Varies by endpoint and tier |
| **Pricing** | Pay-per-token (varies by model) |

---

## Overview

The Cohere API provides enterprise-grade language models: chat with the Command
family, multilingual text embeddings, document reranking for retrieval, and
few-shot text classification. Cohere mixes v1 and v2 endpoints, so this
connector carries the API version in each request path.

## Use Cases

- Chat and text generation (`command-r-plus`)
- Semantic search with embeddings (`embed-english-v3.0`)
- Retrieval reranking (`rerank-english-v3.0`)
- Few-shot text classification
- Tokenization and detokenization

## Installation

```bash
pip install "toolsconnector[cohere]"
```

Set your credentials:

```bash
export TC_COHERE_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["cohere"], credentials={"cohere": "your-token"})

# Generate a chat response
result = kit.execute(
    "cohere_chat",
    {
        "model": "command-r-plus",
        "messages": [{"role": "user", "content": "Say hi"}],
    },
)
print(result)
```

### MCP Server

```python
kit = ToolKit(["cohere"], credentials={"cohere": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["cohere"], credentials={"cohere": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### API Key

1. Dashboard
2. API Keys
3. Create New

[Get credentials &rarr;](https://dashboard.cohere.com/api-keys)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("cohere_list_models", {})
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

- Embeddings require an `input_type` (`search_document`, `search_query`, `classification`, or `clustering`) — pick the one matching your downstream task
- `rerank` returns document indices ordered by `relevance_score`, not the documents themselves — index back into your original list
- Rate limit varies by endpoint and tier — batch `texts` into a single `embed` call where possible

## Related Connectors

- [OpenAI](../openai_connector/) — GPT models and embeddings
- [Anthropic](../anthropic_connector/) — Claude models
- [Pinecone](../pinecone/) — Vector database

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
