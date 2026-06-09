# Google Gemini

> Gemini models for content generation and embeddings

| | |
|---|---|
| **Company** | Google |
| **Category** | Ai Ml |
| **Protocol** | REST |
| **Website** | [ai.google.dev](https://ai.google.dev) |
| **API Docs** | [ai.google.dev/api](https://ai.google.dev/api/rest) |
| **Auth** | API Key |
| **Rate Limit** | Varies by model and tier |
| **Pricing** | Pay-per-token (varies by model) |

---

## Overview

The Google Gemini API provides access to Gemini models for content generation — with **function calling**, **streaming** (`stream_generate_content`), and structured **JSON output** — plus token counting, text embeddings, the Files API, context caching, and tuned models, via the `generativelanguage.googleapis.com` REST API (v1beta). The API key is sent in the `x-goog-api-key` header (never in the URL).

## Use Cases

- Text and content generation (synchronous or streaming)
- Agent tool use via Gemini **function calling** (`tools` / `tool_config`)
- Structured **JSON output** (response schema) and per-request safety controls
- Semantic search with embeddings
- Token counting and cost estimation
- Multi-turn conversations with system instructions

## Installation

```bash
pip install "toolsconnector[gemini]"
```

Set your credentials:

```bash
export TC_GEMINI_CREDENTIALS=your-api-key
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["gemini"], credentials={"gemini": "your-api-key"})

# Generate content
result = kit.execute(
    "gemini_generate_content",
    {"model": "gemini-2.0-flash", "contents": "Explain quantum computing in one sentence."},
)
print(result)
```

### MCP Server

```python
kit = ToolKit(["gemini"], credentials={"gemini": "your-api-key"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["gemini"], credentials={"gemini": "your-api-key"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### API Key

1. Open Google AI Studio
2. Click "Get API key"
3. Create an API key

[Get credentials &rarr;](https://aistudio.google.com/app/apikey)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("gemini_list_models", {})
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

- Pass `contents` as a plain string for a single prompt, or a list of content dicts for multi-turn conversations.
- A `model` id works with or without the `models/` prefix — both `gemini-2.0-flash` and `models/gemini-2.0-flash` are accepted.
- Drive **function calling** by passing `tools` (and optionally `tool_config`) to `generate_content` — the model can return a `functionCall` part.
- Use `stream_generate_content` for incremental output, or `generation_config={"responseMimeType": "application/json", "responseSchema": {...}}` for structured JSON.
- Inspect `safety_ratings` / `block_reason` on the response to detect and handle safety blocks.
- Rate limit is Varies by model and tier — use caching to minimize API calls.

## Related Connectors

- [Openai](../openai_connector/) — GPT models
- [Anthropic](../anthropic_connector/) — Claude models
- [Pinecone](../pinecone/) — Vector database

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
