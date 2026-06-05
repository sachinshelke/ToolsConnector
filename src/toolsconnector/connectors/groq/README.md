# Groq

> Ultra-fast inference for open models with an OpenAI-compatible API

| | |
|---|---|
| **Company** | Groq |
| **Category** | Ai Ml |
| **Protocol** | REST |
| **Website** | [groq.com](https://groq.com) |
| **API Docs** | [console.groq.com/docs](https://console.groq.com/docs/api-reference) |
| **Auth** | API Key |
| **Rate Limit** | Varies by model and tier |
| **Pricing** | Pay-per-token (varies by model) |

---

## Overview

Groq runs open models (Llama, Mixtral, Whisper) on its LPU inference engine
behind an OpenAI-compatible REST API. Point your existing OpenAI-style code at
`https://api.groq.com/openai/v1` and get very low latency chat completions,
plus Whisper audio transcription and translation.

## Use Cases

- Low-latency chat and text generation
- Model discovery
- Audio transcription (speech-to-text)
- Audio translation to English

## Installation

```bash
pip install "toolsconnector[groq]"
```

Set your credentials:

```bash
export TC_GROQ_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["groq"], credentials={"groq": "your-token"})

result = kit.execute(
    "groq_chat_completion",
    {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": "Say hi"}],
    },
)
print(result)
```

### MCP Server

```python
kit = ToolKit(["groq"], credentials={"groq": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

## Authentication

### API Key

1. Console
2. API Keys
3. Create New

[Get credentials &rarr;](https://console.groq.com/keys)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("groq_list_models", {})
except RateLimitError as e:
    print(f"Rate limited. Retry in {e.retry_after_seconds}s")
except AuthError as e:
    print(f"Auth failed: {e.suggestion}")
```

## Actions

<!-- ACTIONS_START -->
<!-- This section is auto-generated from the connector spec. Do not edit manually. -->
<!-- ACTIONS_END -->

## Related Connectors

- [OpenAI](../openai_connector/) — GPT models, embeddings, audio
- [Anthropic](../anthropic/) — Claude models

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
