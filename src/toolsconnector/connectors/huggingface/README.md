# Hugging Face

> Hosted model inference and Hub model/dataset search

| | |
|---|---|
| **Company** | Hugging Face |
| **Category** | Ai Ml |
| **Protocol** | REST |
| **Website** | [huggingface.co](https://huggingface.co) |
| **API Docs** | [huggingface.co/docs](https://huggingface.co/docs/inference-providers) |
| **Auth** | API Key (user access token) |
| **Rate Limit** | Varies by plan (free Inference API is throttled) |
| **Pricing** | Free tier + pay-as-you-go Inference |
| **Verification** | ✅ Tier 1 — Live verified (21/27 actions on `hf-inference`, 2026-06-05; 6 generative/audio actions are partner-provider-dependent) |

---

## Overview

The Hugging Face connector runs hosted model inference via the Inference Providers router (`router.huggingface.co`) — text generation, embeddings, summarization, translation, fill-mask, classification, zero-shot classification, question answering, table-QA, sentence similarity, and vision tasks — and browses model, dataset, and Space metadata via the Hub API (`huggingface.co/api`). Task inference posts to `/{provider}/models/{model}/pipeline/{task}`; the `provider` defaults to `hf-inference` (HF's serverless pool) and can be switched per call (e.g. `fal-ai`, `replicate`, `together`) to route heavier tasks elsewhere. Bring your own user access token (`hf_...`).

> **Provider coverage.** The default `hf-inference` provider serves the lighter "traditional ML" tasks (chat, summarize, translate, fill-mask, classification, NER, zero-shot, QA, table-QA, embeddings, sentence-similarity, and image classification/detection/segmentation) — all **live verified** below. The heavier generative + audio tasks (`text_generation` of large LLMs, `text_to_image`, `text_to_speech`, `image_to_text`, `automatic_speech_recognition`, `audio_classification`) route to **partner providers**: pass `provider=` pointing at a provider that hosts your chosen model. For chat-style generation, prefer `chat_completion` (it auto-routes). Always use a model's **canonical, org-prefixed** repo ID for inference (e.g. `google-bert/bert-base-uncased`, not `bert-base-uncased`) — the router does not resolve legacy aliases the way the Hub API does.

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

## Verification Status

All 27 actions are pinned by **38 respx tests** in [tests/connectors/test_huggingface.py](../../../tests/connectors/test_huggingface.py): happy path per action, two-host routing (router vs Hub), pipeline-path pinning, custom-provider routing, heterogeneous inference shapes (list-of-dicts, list-of-lists, single dict, raw bytes), base64 binary inputs, optional-param omission, the error matrix (auth / rate-limit / not-found / validation), and the MCP + OpenAI-schema sweeps. Two regression tests cover the live-confirmed quirks fixed during verification (the zero-shot router list shape and the Hub legacy-alias redirect).

**21 of 27 actions are Live verified** — exercised end-to-end against the real Hugging Face API on **2026-06-05** with a real user access token (`hf_...`), routed through the default `hf-inference` provider. The remaining **6 are partner-provider-dependent**: they route correctly (the router forwards the request and returns a clean provider-level response), but `hf-inference` does not serve them — they require a partner provider (e.g. `fal-ai`, `replicate`, `together`) that hosts the chosen model, supplied via `provider=`. This is Hugging Face's multi-provider architecture, not a connector limitation.

| Action | Task / Endpoint | Status |
|---|---|---|
| `whoami` | `GET /api/whoami-v2` | ✅ Live verified |
| `list_models` | `GET /api/models` | ✅ Live verified |
| `get_model` | `GET /api/models/{id}` (follows legacy-alias 307) | ✅ Live verified |
| `list_datasets` | `GET /api/datasets` | ✅ Live verified |
| `get_dataset` | `GET /api/datasets/{id}` (follows legacy-alias 307) | ✅ Live verified |
| `list_spaces` | `GET /api/spaces` | ✅ Live verified |
| `get_space` | `GET /api/spaces/{id}` | ✅ Live verified |
| `chat_completion` | `POST /v1/chat/completions` (auto-routes) | ✅ Live verified |
| `summarize` | `…/pipeline/summarization` | ✅ Live verified |
| `translate` | `…/pipeline/translation` | ✅ Live verified |
| `fill_mask` | `…/pipeline/fill-mask` | ✅ Live verified |
| `text_classification` | `…/pipeline/text-classification` | ✅ Live verified |
| `token_classification` | `…/pipeline/token-classification` | ✅ Live verified |
| `zero_shot_classification` | `…/pipeline/zero-shot-classification` | ✅ Live verified |
| `question_answering` | `…/pipeline/question-answering` | ✅ Live verified |
| `table_question_answering` | `…/pipeline/table-question-answering` | ✅ Live verified |
| `feature_extraction` | `…/pipeline/feature-extraction` | ✅ Live verified |
| `sentence_similarity` | `…/pipeline/sentence-similarity` | ✅ Live verified |
| `image_classification` | `…/pipeline/image-classification` | ✅ Live verified |
| `object_detection` | `…/pipeline/object-detection` | ✅ Live verified |
| `image_segmentation` | `…/pipeline/image-segmentation` | ✅ Live verified |
| `text_generation` | `…/pipeline/text-generation` | 🔌 Provider-dependent (large LLMs route to a partner; or use `chat_completion`) |
| `text_to_image` | `…/pipeline/text-to-image` | 🔌 Provider-dependent (`provider="fal-ai"`, etc.) |
| `text_to_speech` | `…/pipeline/text-to-speech` | 🔌 Provider-dependent |
| `image_to_text` | `…/pipeline/image-to-text` | 🔌 Provider-dependent |
| `automatic_speech_recognition` | `…/pipeline/automatic-speech-recognition` | 🔌 Provider-dependent |
| `audio_classification` | `…/pipeline/audio-classification` | 🔌 Provider-dependent |

Three gaps were found and fixed during the live verification + adversarial re-test sweep: (1) `zero_shot_classification` returned empty labels because the `hf-inference` router emits a score-sorted list of `{label, score}` rather than the classic `{sequence, labels, scores}` object — the parser now handles both; (2) `get_model`/`get_dataset` failed to parse because the Hub `307`-redirects legacy repo aliases (`bert-base-uncased` → `google-bert/bert-base-uncased`) and the client wasn't following redirects — it now does; (3) **batch embeddings** were impossible via the typed/MCP interface — `feature_extraction(inputs)` is now `Union[str, list[str]]`, and the schema generator renders multi-type unions as `anyOf` so a list passes validation instead of being rejected as "expects string" (a cross-cutting fix that also unblocked Mistral batch embeddings and Gemini structured `contents`).

## Actions

<!-- ACTIONS_START -->
<!-- This section is auto-generated from the connector spec. Do not edit manually. -->
<!-- ACTIONS_END -->

## Tips

- Inference outputs are heterogeneous per task — each action returns a typed model for its stable shape (e.g. `HFGeneratedText`, `HFClassification`); embeddings return raw `list[list[float]]`
- `feature_extraction` accepts a single string **or a list of strings** — pass a list to embed a batch in one request (one `list[float]` row per input, index-aligned), which is far cheaper than one call per text
- For model discovery, prefer `list_models(pipeline_tag="text-to-image")` over `filter=` — `pipeline_tag` matches a model's canonical task, while `filter` matches any tag (so e.g. text-ranking models tagged `text-classification` slip into a `filter` result). `library=` narrows by framework (`transformers`, `diffusers`, `sentence-transformers`)
- For inference, always pass a model's **canonical, org-prefixed** repo ID (e.g. `google-bert/bert-base-uncased`, `distilbert/distilbert-base-uncased-finetuned-sst-2-english`) — the router does not resolve legacy aliases, and a bare alias returns `Model not supported by provider`. The Hub metadata actions (`get_model`/`get_dataset`) *do* resolve aliases (the connector follows the Hub's `307` redirect)
- Pass `wait_for_model=True` on `text_generation` to block while a cold model warms up instead of getting a 503
- Serverless inference (the default `hf-inference` provider) is throttled — cache results and prefer batching where possible; route heavy/generative tasks to a partner provider via `provider=` (e.g. `"fal-ai"`, `"replicate"`, `"together"`)

## Related Connectors

- [OpenAI](../openai_connector/) — GPT models and embeddings
- [Anthropic](../anthropic_connector/) — Claude models

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
