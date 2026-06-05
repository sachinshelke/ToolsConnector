# Mistral

> Mistral AI models for chat, embeddings, and code

| | |
|---|---|
| **Company** | Mistral AI |
| **Category** | Ai Ml |
| **Protocol** | REST |
| **Website** | [mistral.ai](https://mistral.ai) |
| **API Docs** | [docs.mistral.ai](https://docs.mistral.ai/api/) |
| **Auth** | API Key |
| **Rate Limit** | Varies by model and tier |
| **Pricing** | Pay-per-token (varies by model) |

---

## Overview

The Mistral AI API provides access to Mistral models for chat completions, text embeddings, fill-in-the-middle (FIM) code completions with Codestral, and content moderation. The API is OpenAI-compatible and authenticated with a Bearer API key.

## Use Cases

- Chat and text generation
- Semantic search with embeddings
- Inline code completion (FIM)
- Content moderation

## Installation

```bash
pip install "toolsconnector[mistral]"
```

Set your credentials:

```bash
export TC_MISTRAL_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["mistral"], credentials={"mistral": "your-token"})

# Generate a chat completion
result = kit.execute(
    "mistral_chat_completion",
    {
        "model": "mistral-large-latest",
        "messages": [{"role": "user", "content": "Say hi"}],
    },
)
print(result)
```

### MCP Server

```python
kit = ToolKit(["mistral"], credentials={"mistral": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["mistral"], credentials={"mistral": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### API Key

1. Console
2. API Keys
3. Create New Key

[Get credentials &rarr;](https://console.mistral.ai/api-keys/)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("mistral_list_models", {})
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

- Rate limit is Varies by model and tier — use caching to minimize API calls
- Use `codestral-latest` with `mistral_fim_completion` for inline code generation
- This connector's API is OpenAI-compatible, so existing chat/embedding payloads port over directly

## Related Connectors

- [Openai](../openai_connector/) — GPT models
- [Anthropic](../anthropic_connector/) — Claude models
- [Pinecone](../pinecone/) — Vector database

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
