# OpenAI

> GPT models, embeddings, and AI capabilities

| | |
|---|---|
| **Company** | OpenAI |
| **Category** | Ai Ml |
| **Protocol** | REST |
| **Website** | [openai.com](https://openai.com) |
| **API Docs** | [platform.openai.com](https://platform.openai.com/docs/api-reference) |
| **Auth** | API Key |
| **Rate Limit** | Varies by model and tier |
| **Pricing** | Pay-per-token (varies by model) |

---

## Overview

The OpenAI API provides access to GPT models for text generation, embeddings for semantic search, image generation with DALL-E, audio transcription with Whisper, and fine-tuning capabilities. Build AI-powered features into any application.

## Use Cases

- Text generation and chat
- Semantic search with embeddings
- Image generation
- Audio transcription
- Content moderation

## Installation

```bash
pip install "toolsconnector[openai]"
```

Set your credentials:

```bash
export TC_OPENAI_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["openai"], credentials={"openai": "your-token"})

# List uploaded files
result = kit.execute("openai_list_files", {"purpose": "your-purpose"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["openai"], credentials={"openai": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["openai"], credentials={"openai": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### API Key

1. Platform
2. API Keys
3. Create New

[Get credentials &rarr;](https://platform.openai.com/api-keys)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("openai_list_files", {})
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

- Rate limit is Varies by model and tier — use pagination and caching to minimize API calls
- Actions marked as destructive (`create_fine_tuning_job`, `delete_assistant`, `delete_file`) cannot be undone — use with caution
- This connector has 26 actions — use `ToolKit(include_actions=[...])` to expose only what your agent needs

## Related Connectors

- [Anthropic](../anthropic/) — Claude models
- [Pinecone](../pinecone/) — Vector database

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
