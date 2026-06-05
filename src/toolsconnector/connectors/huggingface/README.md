# Hugging Face

> Hosted model inference and Hub model/dataset search

| | |
|---|---|
| **Company** | Hugging Face |
| **Category** | Ai Ml |
| **Protocol** | REST |
| **Website** | [huggingface.co](https://huggingface.co) |
| **API Docs** | [huggingface.co/docs](https://huggingface.co/docs/api-inference) |
| **Auth** | API Key (user access token) |
| **Rate Limit** | Varies by plan (free Inference API is throttled) |
| **Pricing** | Free tier + pay-as-you-go Inference |

---

## Overview

The Hugging Face connector runs hosted model inference via the Inference API (`api-inference.huggingface.co`) — text generation, embeddings, summarization, translation, fill-mask, classification, zero-shot classification, and question answering — and browses model and dataset metadata via the Hub API (`huggingface.co/api`). Bring your own user access token (`hf_...`).

## Use Cases

- Text generation and summarization
- Sentence embeddings for semantic search
- Translation and fill-mask
- Text and zero-shot classification
- Model and dataset discovery on the Hub

## Installation

```bash
pip install "toolsconnector[huggingface]"
```

Set your credentials:

```bash
export TC_HUGGINGFACE_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["huggingface"], credentials={"huggingface": "your-token"})

# Search the Hub for text-classification models
result = kit.execute("huggingface_list_models", {"filter": "text-classification", "limit": 5})
print(result)
```

### MCP Server

```python
kit = ToolKit(["huggingface"], credentials={"huggingface": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["huggingface"], credentials={"huggingface": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### API Key

1. Settings
2. Access Tokens
3. New token (read scope is enough for inference + search)

[Get credentials &rarr;](https://huggingface.co/settings/tokens)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("huggingface_whoami", {})
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

- Inference outputs are heterogeneous per task — each action returns a typed model for its stable shape (e.g. `HFGeneratedText`, `HFClassification`); embeddings return raw `list[list[float]]`
- Pass `wait_for_model=True` on `text_generation` to block while a cold model warms up instead of getting a 503
- The free Inference API is throttled — cache results and prefer batching where possible

## Related Connectors

- [OpenAI](../openai_connector/) — GPT models and embeddings
- [Anthropic](../anthropic_connector/) — Claude models

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
