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
| **Verification** | ✅ Tier 1 — Live verified (12/20 happy-path + 8/20 envelope-verified, 2026-06-12; 4 caching actions are paid-tier-gated, 4 tuning actions discontinued upstream) |

---

## Overview

The Google Gemini API provides access to Gemini models for content generation — with **function calling**, **streaming** (`stream_generate_content`), and structured **JSON output** — plus token counting, text embeddings, the Files API, context caching, and tuned models, via the `generativelanguage.googleapis.com` REST API (v1beta). The API key is sent in the `x-goog-api-key` header (never in the URL).

> **Live-verification coverage (2026-06-12).** Verified end to end against the real API via the serve path: model discovery (`list_models`, `get_model`), `count_tokens`, `generate_content` (plain, **function calling** with a real `functionCall` round trip, **JSON mode** via `responseSchema`/`responseMimeType`, `safety_settings`, and `thinkingConfig`), `stream_generate_content` (real SSE), single + batch embeddings (3072-dim), the **full Files lifecycle** (resumable upload → get → list → delete), and `list_caches` — **12/20 actions**. The other 8 are **envelope-verified live** (every action was individually exercised against the real API; Google accepted each request envelope and returned the expected upstream constraint as a clean typed error) — they are environment-gated, not connector defects: the 4 **caching** mutations (`create/get/update/delete_cache`) require a **paid tier** — free-tier cached-content storage quota is 0 on every model probed (2.5-flash, 2.0-flash, 2.5-pro), `get`/`update`/`delete` envelopes were accepted through to Google's existence check (HTTP 403 "CachedContent not found"), and the 400 too-small + 429 quota error paths were both verified; the 4 **tuned-model** actions (including a real `create_tuned_model` attempt) each return **HTTP 501 UNIMPLEMENTED** — Google has discontinued tuning on the public Gemini API (it moved to Vertex AI).

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
- **Thinking models** (Gemini 2.5 family) spend output tokens on internal reasoning first — check `usage.thoughts_token_count`, and either raise `max_output_tokens` well above your expected text length or disable thinking with `generation_config={"thinkingConfig": {"thinkingBudget": 0}}`.
- Free-tier keys may have per-model `generateContent` quotas (429) and **cannot store context caches** (storage quota is 0) — caching needs a paid tier.
- Rate limit is Varies by model and tier — use caching to minimize API calls.

## Related Connectors

- [Openai](../openai_connector/) — GPT models
- [Anthropic](../anthropic_connector/) — Claude models
- [Pinecone](../pinecone/) — Vector database

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
