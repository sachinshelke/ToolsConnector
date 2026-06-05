"""End-to-end tests for the Hugging Face connector using respx.

Same pattern as test_openai.py. Exercises Hugging Face's specifics:

  - **Three hosts** — the Inference API (``api-inference.huggingface.co``),
    the OpenAI-compatible router (``router.huggingface.co``) for chat
    completion, and the Hub API (``huggingface.co/api``). Each test mocks
    the host the action under test targets, asserting the request lands
    on the right base.
  - **Heterogeneous inference shapes** — text-to-text tasks return a
    ``list`` of dicts; classification returns a list-of-lists; zero-shot
    and QA return a single dict. The connector normalises each into a
    typed model.
  - **Binary tasks** — text-to-image and text-to-speech return raw bytes;
    vision/audio inputs are base64-encoded into the JSON body.
  - **Bearer auth** — ``Authorization: Bearer <hf_token>`` on every call.
  - **Optional params omitted when None** — ``parameters`` / query params
    must not carry null values when the caller leaves them unset.
"""

from __future__ import annotations

import base64

import httpx
import pytest
import pytest_asyncio
import respx

from toolsconnector.connectors.huggingface import HuggingFace
from toolsconnector.errors import (
    InvalidCredentialsError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)

_INFERENCE = "https://api-inference.huggingface.co"
_ROUTER = "https://router.huggingface.co"
_HUB = "https://huggingface.co/api"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def hf() -> HuggingFace:
    """Hugging Face connector with a fake token.

    Token never hits Hugging Face because respx patches httpx.
    """
    connector = HuggingFace(credentials="hf_fake_test_token")
    await connector._setup()
    yield connector
    await connector._teardown()


# ---------------------------------------------------------------------------
# 1. Inference — text generation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_text_generation_happy_path(hf: HuggingFace) -> None:
    """text_generation: POST /models/{model} → [HFGeneratedText].

    Verifies host, auth header, that inputs land in the body, and that
    the list-of-dicts response is parsed.
    """
    with respx.mock(base_url=_INFERENCE, assert_all_called=True) as mock:
        route = mock.post("/models/gpt2").mock(
            return_value=httpx.Response(
                200,
                json=[{"generated_text": "Hello, world! And then some."}],
            )
        )

        result = await hf.atext_generation(
            model="gpt2",
            inputs="Hello, world!",
            max_new_tokens=20,
            temperature=0.7,
        )

        assert len(result) == 1
        assert result[0].generated_text == "Hello, world! And then some."

        request = route.calls.last.request
        assert request.headers["authorization"] == "Bearer hf_fake_test_token"
        body = request.read()
        assert b'"inputs"' in body
        assert b'"max_new_tokens":20' in body
        assert b'"temperature"' in body


@pytest.mark.asyncio
async def test_text_generation_omits_optional_params_when_none(hf: HuggingFace) -> None:
    """When generation params are None, no ``parameters`` block is sent."""
    with respx.mock(base_url=_INFERENCE) as mock:
        route = mock.post("/models/gpt2").mock(
            return_value=httpx.Response(200, json=[{"generated_text": "x"}])
        )

        await hf.atext_generation(model="gpt2", inputs="hi")

        body = route.calls.last.request.read()
        assert b'"inputs"' in body
        # No params/options set → those keys must be absent entirely.
        assert b'"parameters"' not in body
        assert b'"options"' not in body
        assert b'"max_new_tokens"' not in body


# ---------------------------------------------------------------------------
# 2. Inference — summarize / translate (shared text-to-text shape)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summarize_happy_path(hf: HuggingFace) -> None:
    """summarize: parses ``summary_text`` from the response list."""
    with respx.mock(base_url=_INFERENCE) as mock:
        mock.post("/models/facebook/bart-large-cnn").mock(
            return_value=httpx.Response(200, json=[{"summary_text": "Short version."}])
        )

        result = await hf.asummarize(model="facebook/bart-large-cnn", inputs="long text...")

        assert result[0].summary_text == "Short version."


@pytest.mark.asyncio
async def test_translate_happy_path(hf: HuggingFace) -> None:
    """translate: parses ``translation_text`` from the response list."""
    with respx.mock(base_url=_INFERENCE) as mock:
        mock.post("/models/Helsinki-NLP/opus-mt-en-fr").mock(
            return_value=httpx.Response(200, json=[{"translation_text": "Bonjour"}])
        )

        result = await hf.atranslate(model="Helsinki-NLP/opus-mt-en-fr", inputs="Hello")

        assert result[0].translation_text == "Bonjour"


# ---------------------------------------------------------------------------
# 3. Inference — fill-mask
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fill_mask_happy_path(hf: HuggingFace) -> None:
    """fill_mask: parses a list of candidate tokens."""
    with respx.mock(base_url=_INFERENCE) as mock:
        mock.post("/models/bert-base-uncased").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "sequence": "the capital of france is paris.",
                        "score": 0.9,
                        "token": 3000,
                        "token_str": "paris",
                    }
                ],
            )
        )

        result = await hf.afill_mask(
            model="bert-base-uncased",
            inputs="The capital of France is [MASK].",
        )

        assert result[0].token_str == "paris"
        assert result[0].score == 0.9
        assert result[0].token == 3000


# ---------------------------------------------------------------------------
# 4. Inference — text classification (list-of-lists flattening)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_text_classification_flattens_nested_list(hf: HuggingFace) -> None:
    """text_classification: a [[{...}]] response is flattened to [HFClassification]."""
    with respx.mock(base_url=_INFERENCE) as mock:
        mock.post("/models/distilbert-base-uncased-finetuned-sst-2-english").mock(
            return_value=httpx.Response(
                200,
                json=[
                    [
                        {"label": "POSITIVE", "score": 0.99},
                        {"label": "NEGATIVE", "score": 0.01},
                    ]
                ],
            )
        )

        result = await hf.atext_classification(
            model="distilbert-base-uncased-finetuned-sst-2-english",
            inputs="I love this!",
        )

        assert len(result) == 2
        assert result[0].label == "POSITIVE"
        assert result[0].score == 0.99
        assert result[1].label == "NEGATIVE"


# ---------------------------------------------------------------------------
# 5. Inference — zero-shot classification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_zero_shot_classification_happy_path(hf: HuggingFace) -> None:
    """zero_shot_classification: candidate_labels land in body; result parsed."""
    with respx.mock(base_url=_INFERENCE) as mock:
        route = mock.post("/models/facebook/bart-large-mnli").mock(
            return_value=httpx.Response(
                200,
                json={
                    "sequence": "I need a refund",
                    "labels": ["billing", "tech support"],
                    "scores": [0.92, 0.08],
                },
            )
        )

        result = await hf.azero_shot_classification(
            model="facebook/bart-large-mnli",
            inputs="I need a refund",
            candidate_labels=["billing", "tech support"],
        )

        assert result.labels == ["billing", "tech support"]
        assert result.scores[0] == 0.92

        body = route.calls.last.request.read()
        assert b'"candidate_labels"' in body
        assert b"billing" in body


# ---------------------------------------------------------------------------
# 6. Inference — question answering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_question_answering_happy_path(hf: HuggingFace) -> None:
    """question_answering: question+context in body; answer span parsed."""
    with respx.mock(base_url=_INFERENCE) as mock:
        route = mock.post("/models/deepset/roberta-base-squad2").mock(
            return_value=httpx.Response(
                200,
                json={"answer": "Paris", "score": 0.98, "start": 17, "end": 22},
            )
        )

        result = await hf.aquestion_answering(
            model="deepset/roberta-base-squad2",
            question="What is the capital?",
            context="The capital is Paris.",
        )

        assert result.answer == "Paris"
        assert result.start == 17
        assert result.end == 22

        body = route.calls.last.request.read()
        assert b'"question"' in body
        assert b'"context"' in body


# ---------------------------------------------------------------------------
# 7. Inference — feature extraction (embeddings)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_feature_extraction_normalises_flat_vector(hf: HuggingFace) -> None:
    """A flat [float, ...] embedding is wrapped into [[float, ...]]."""
    with respx.mock(base_url=_INFERENCE) as mock:
        mock.post("/models/sentence-transformers/all-MiniLM-L6-v2").mock(
            return_value=httpx.Response(200, json=[0.1, 0.2, 0.3])
        )

        result = await hf.afeature_extraction(
            model="sentence-transformers/all-MiniLM-L6-v2",
            inputs="hello",
        )

        assert result == [[0.1, 0.2, 0.3]]


@pytest.mark.asyncio
async def test_feature_extraction_passes_nested_through(hf: HuggingFace) -> None:
    """An already-nested embedding response is returned unchanged."""
    with respx.mock(base_url=_INFERENCE) as mock:
        mock.post("/models/some/model").mock(
            return_value=httpx.Response(200, json=[[0.1, 0.2], [0.3, 0.4]])
        )

        result = await hf.afeature_extraction(model="some/model", inputs="hello")

        assert result == [[0.1, 0.2], [0.3, 0.4]]


# ---------------------------------------------------------------------------
# 8. Hub — list models / get model / list datasets / whoami
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_models_happy_path(hf: HuggingFace) -> None:
    """list_models: hits the Hub host, forwards query params, parses metadata."""
    with respx.mock(base_url=_HUB, assert_all_called=True) as mock:
        route = mock.get("/models").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "id": "bert-base-uncased",
                        "author": "google",
                        "downloads": 1000000,
                        "likes": 500,
                        "pipeline_tag": "fill-mask",
                        "tags": ["pytorch", "bert"],
                    }
                ],
            )
        )

        result = await hf.alist_models(filter="fill-mask", sort="downloads", limit=5)

        assert len(result) == 1
        assert result[0].id == "bert-base-uncased"
        assert result[0].downloads == 1000000
        assert result[0].pipeline_tag == "fill-mask"

        request = route.calls.last.request
        assert request.headers["authorization"] == "Bearer hf_fake_test_token"
        assert request.url.params["filter"] == "fill-mask"
        assert request.url.params["sort"] == "downloads"
        assert request.url.params["limit"] == "5"


@pytest.mark.asyncio
async def test_get_model_happy_path(hf: HuggingFace) -> None:
    """get_model: GET /models/{id} on the Hub → HFModelInfo."""
    with respx.mock(base_url=_HUB) as mock:
        mock.get("/models/gpt2").mock(
            return_value=httpx.Response(
                200,
                json={"id": "gpt2", "author": "openai-community", "likes": 1234},
            )
        )

        result = await hf.aget_model(model_id="gpt2")

        assert result.id == "gpt2"
        assert result.likes == 1234


@pytest.mark.asyncio
async def test_list_datasets_happy_path(hf: HuggingFace) -> None:
    """list_datasets: GET /datasets on the Hub → [HFDatasetInfo]."""
    with respx.mock(base_url=_HUB) as mock:
        mock.get("/datasets").mock(
            return_value=httpx.Response(
                200,
                json=[{"id": "squad", "downloads": 50000, "tags": ["question-answering"]}],
            )
        )

        result = await hf.alist_datasets(search="squad", limit=10)

        assert result[0].id == "squad"
        assert result[0].downloads == 50000


@pytest.mark.asyncio
async def test_whoami_happy_path(hf: HuggingFace) -> None:
    """whoami: GET /whoami-v2 on the Hub → HFWhoAmI."""
    with respx.mock(base_url=_HUB) as mock:
        mock.get("/whoami-v2").mock(
            return_value=httpx.Response(
                200,
                json={"name": "alice", "type": "user", "email": "alice@example.com", "orgs": []},
            )
        )

        result = await hf.awhoami()

        assert result.name == "alice"
        assert result.type == "user"
        assert result.email == "alice@example.com"


# ---------------------------------------------------------------------------
# 9. Error mapping — typed exceptions surface from both hosts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_token_raises_invalid_credentials_error(hf: HuggingFace) -> None:
    """Hub 401 → typed :class:`InvalidCredentialsError` carrying the connector."""
    with respx.mock(base_url=_HUB) as mock:
        mock.get("/whoami-v2").mock(
            return_value=httpx.Response(401, json={"error": "Invalid credentials"})
        )

        with pytest.raises(InvalidCredentialsError) as exc_info:
            await hf.awhoami()

        assert exc_info.value.connector == "huggingface"
        assert exc_info.value.upstream_status == 401


@pytest.mark.asyncio
async def test_rate_limit_raises_rate_limit_error(hf: HuggingFace) -> None:
    """Inference 429 → typed :class:`RateLimitError` with parsed Retry-After."""
    with respx.mock(base_url=_INFERENCE) as mock:
        mock.post("/models/gpt2").mock(
            return_value=httpx.Response(
                429,
                headers={"Retry-After": "30"},
                json={"error": "Rate limit reached"},
            )
        )

        with pytest.raises(RateLimitError) as exc_info:
            await hf.atext_generation(model="gpt2", inputs="hi")

        assert exc_info.value.connector == "huggingface"
        assert exc_info.value.upstream_status == 429
        assert exc_info.value.retry_after_seconds == 30.0


# ---------------------------------------------------------------------------
# 10. Chat completion — OpenAI-compatible router host
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_completion_happy_path(hf: HuggingFace) -> None:
    """chat_completion: POST /v1/chat/completions on the ROUTER host.

    Verifies the router base, that messages land in the body, stream is
    forced false, and the OpenAI-shaped response is parsed.
    """
    with respx.mock(base_url=_ROUTER, assert_all_called=True) as mock:
        route = mock.post("/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "chatcmpl-1",
                    "object": "chat.completion",
                    "created": 1700000000,
                    "model": "openai/gpt-oss-120b",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "Hi there!"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 9,
                        "completion_tokens": 3,
                        "total_tokens": 12,
                    },
                    "system_fingerprint": "fp_abc",
                },
            )
        )

        result = await hf.achat_completion(
            model="openai/gpt-oss-120b:fastest",
            messages=[{"role": "user", "content": "Hello!"}],
            temperature=0.7,
            max_tokens=64,
        )

        assert result.id == "chatcmpl-1"
        assert result.choices[0].message.content == "Hi there!"
        assert result.choices[0].finish_reason == "stop"
        assert result.usage is not None
        assert result.usage.total_tokens == 12
        assert result.system_fingerprint == "fp_abc"

        request = route.calls.last.request
        assert request.headers["authorization"] == "Bearer hf_fake_test_token"
        body = request.read()
        assert b'"messages"' in body
        assert b'"model":"openai/gpt-oss-120b:fastest"' in body
        # Streaming is never enabled by this action.
        assert b'"stream":false' in body
        assert b'"temperature"' in body
        # Unset optional params must not appear.
        assert b'"tools"' not in body
        assert b'"seed"' not in body


@pytest.mark.asyncio
async def test_chat_completion_passes_tools(hf: HuggingFace) -> None:
    """chat_completion: tool definitions and tool_choice land in the body."""
    with respx.mock(base_url=_ROUTER) as mock:
        route = mock.post("/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "chatcmpl-2",
                    "model": "m",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_1",
                                        "type": "function",
                                        "function": {"name": "get_weather", "arguments": "{}"},
                                    }
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ],
                },
            )
        )

        tools = [
            {
                "type": "function",
                "function": {"name": "get_weather", "parameters": {}},
            }
        ]
        result = await hf.achat_completion(
            model="m",
            messages=[{"role": "user", "content": "weather?"}],
            tools=tools,
            tool_choice="auto",
        )

        assert result.choices[0].message.tool_calls is not None
        assert result.choices[0].message.tool_calls[0]["function"]["name"] == "get_weather"

        body = route.calls.last.request.read()
        assert b'"tools"' in body
        assert b'"tool_choice":"auto"' in body


# ---------------------------------------------------------------------------
# 11. Inference — token classification (NER)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_token_classification_happy_path(hf: HuggingFace) -> None:
    """token_classification: parses entity spans; aggregation strategy in body."""
    with respx.mock(base_url=_INFERENCE) as mock:
        route = mock.post("/models/dslim/bert-base-NER").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "entity_group": "PER",
                        "score": 0.99,
                        "word": "Sarah",
                        "start": 0,
                        "end": 5,
                    },
                    {
                        "entity_group": "LOC",
                        "score": 0.98,
                        "word": "London",
                        "start": 15,
                        "end": 21,
                    },
                ],
            )
        )

        result = await hf.atoken_classification(
            model="dslim/bert-base-NER",
            inputs="Sarah lives in London",
            aggregation_strategy="simple",
        )

        assert len(result) == 2
        assert result[0].entity_group == "PER"
        assert result[0].word == "Sarah"
        assert result[1].entity_group == "LOC"
        assert result[1].end == 21

        body = route.calls.last.request.read()
        assert b'"aggregation_strategy":"simple"' in body


# ---------------------------------------------------------------------------
# 12. Inference — table question answering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_table_question_answering_happy_path(hf: HuggingFace) -> None:
    """table_question_answering: query+table in body; answer/cells parsed."""
    with respx.mock(base_url=_INFERENCE) as mock:
        route = mock.post("/models/google/tapas-base-finetuned-wtq").mock(
            return_value=httpx.Response(
                200,
                json={
                    "answer": "SUM > 950",
                    "coordinates": [[0, 1], [1, 1]],
                    "cells": ["500", "450"],
                    "aggregator": "SUM",
                },
            )
        )

        result = await hf.atable_question_answering(
            model="google/tapas-base-finetuned-wtq",
            query="What is the total revenue?",
            table={"City": ["Paris", "London"], "Revenue": ["500", "450"]},
        )

        assert result.answer == "SUM > 950"
        assert result.aggregator == "SUM"
        assert result.cells == ["500", "450"]
        assert result.coordinates == [[0, 1], [1, 1]]

        body = route.calls.last.request.read()
        assert b'"query"' in body
        assert b'"table"' in body
        assert b"Revenue" in body


# ---------------------------------------------------------------------------
# 13. Inference — sentence similarity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sentence_similarity_happy_path(hf: HuggingFace) -> None:
    """sentence_similarity: source+candidates in body; float scores returned."""
    with respx.mock(base_url=_INFERENCE) as mock:
        route = mock.post("/models/sentence-transformers/all-MiniLM-L6-v2").mock(
            return_value=httpx.Response(200, json=[0.91, 0.12, 0.55])
        )

        result = await hf.asentence_similarity(
            model="sentence-transformers/all-MiniLM-L6-v2",
            source_sentence="That is a happy dog",
            sentences=["That is a joyful puppy", "An apple a day", "The sky is blue"],
        )

        assert result == [0.91, 0.12, 0.55]

        body = route.calls.last.request.read()
        assert b'"source_sentence"' in body
        assert b'"sentences"' in body


# ---------------------------------------------------------------------------
# 14. Inference — vision: text-to-image (binary out) & captioning
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_text_to_image_returns_raw_bytes(hf: HuggingFace) -> None:
    """text_to_image: returns the raw image bytes from the response body."""
    png_bytes = b"\x89PNG\r\n\x1a\nfakeimage"
    with respx.mock(base_url=_INFERENCE) as mock:
        route = mock.post("/models/black-forest-labs/FLUX.1-schnell").mock(
            return_value=httpx.Response(
                200,
                content=png_bytes,
                headers={"Content-Type": "image/png"},
            )
        )

        result = await hf.atext_to_image(
            model="black-forest-labs/FLUX.1-schnell",
            inputs="a serene lake at sunset",
            guidance_scale=7.5,
            num_inference_steps=20,
            width=512,
            height=512,
        )

        assert result == png_bytes

        body = route.calls.last.request.read()
        assert b'"inputs"' in body
        assert b'"guidance_scale"' in body
        assert b'"num_inference_steps":20' in body


@pytest.mark.asyncio
async def test_image_to_text_happy_path(hf: HuggingFace) -> None:
    """image_to_text: base64-encodes bytes input; parses generated_text."""
    raw = b"\xff\xd8\xff\xe0jpegdata"
    with respx.mock(base_url=_INFERENCE) as mock:
        route = mock.post("/models/Salesforce/blip-image-captioning-large").mock(
            return_value=httpx.Response(200, json=[{"generated_text": "a cat sitting on a sofa"}])
        )

        result = await hf.aimage_to_text(
            model="Salesforce/blip-image-captioning-large",
            image=raw,
        )

        assert result[0].generated_text == "a cat sitting on a sofa"

        # Bytes input must be base64-encoded into the JSON body.
        body = route.calls.last.request.read()
        expected_b64 = base64.b64encode(raw).decode("ascii").encode()
        assert expected_b64 in body


@pytest.mark.asyncio
async def test_image_classification_passes_base64_string_through(hf: HuggingFace) -> None:
    """image_classification: an already-base64 str input is sent unchanged."""
    b64 = base64.b64encode(b"imgbytes").decode("ascii")
    with respx.mock(base_url=_INFERENCE) as mock:
        route = mock.post("/models/google/vit-base-patch16-224").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {"label": "Egyptian cat", "score": 0.94},
                    {"label": "tabby", "score": 0.04},
                ],
            )
        )

        result = await hf.aimage_classification(
            model="google/vit-base-patch16-224",
            image=b64,
            top_k=5,
        )

        assert result[0].label == "Egyptian cat"
        assert result[0].score == 0.94

        body = route.calls.last.request.read()
        assert b64.encode() in body
        assert b'"top_k":5' in body


@pytest.mark.asyncio
async def test_object_detection_happy_path(hf: HuggingFace) -> None:
    """object_detection: parses label/score/box rows."""
    with respx.mock(base_url=_INFERENCE) as mock:
        mock.post("/models/facebook/detr-resnet-50").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "label": "cat",
                        "score": 0.999,
                        "box": {"xmin": 10, "ymin": 20, "xmax": 200, "ymax": 300},
                    }
                ],
            )
        )

        result = await hf.aobject_detection(
            model="facebook/detr-resnet-50",
            image=b"imgbytes",
            threshold=0.9,
        )

        assert result[0].label == "cat"
        assert result[0].box["xmax"] == 200


@pytest.mark.asyncio
async def test_image_segmentation_happy_path(hf: HuggingFace) -> None:
    """image_segmentation: parses label/score and a base64 mask string."""
    with respx.mock(base_url=_INFERENCE) as mock:
        mock.post("/models/facebook/mask2former-swin-large-coco-panoptic").mock(
            return_value=httpx.Response(
                200,
                json=[{"label": "sky", "score": 0.97, "mask": "aW1hZ2VtYXNr"}],
            )
        )

        result = await hf.aimage_segmentation(
            model="facebook/mask2former-swin-large-coco-panoptic",
            image=b"imgbytes",
            subtask="panoptic",
        )

        assert result[0].label == "sky"
        assert result[0].mask == "aW1hZ2VtYXNr"


# ---------------------------------------------------------------------------
# 15. Inference — audio: ASR, classification, text-to-speech (binary out)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_automatic_speech_recognition_happy_path(hf: HuggingFace) -> None:
    """automatic_speech_recognition: base64-encodes audio; parses {text}."""
    raw = b"RIFFfakeaudio"
    with respx.mock(base_url=_INFERENCE) as mock:
        route = mock.post("/models/openai/whisper-large-v3").mock(
            return_value=httpx.Response(200, json={"text": "hello world"})
        )

        result = await hf.aautomatic_speech_recognition(
            model="openai/whisper-large-v3",
            audio=raw,
        )

        assert result.text == "hello world"

        body = route.calls.last.request.read()
        assert base64.b64encode(raw).decode("ascii").encode() in body


@pytest.mark.asyncio
async def test_audio_classification_happy_path(hf: HuggingFace) -> None:
    """audio_classification: parses label/score pairs."""
    with respx.mock(base_url=_INFERENCE) as mock:
        mock.post("/models/superb/hubert-large-superb-er").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {"label": "happy", "score": 0.7},
                    {"label": "neutral", "score": 0.3},
                ],
            )
        )

        result = await hf.aaudio_classification(
            model="superb/hubert-large-superb-er",
            audio=b"audiobytes",
        )

        assert result[0].label == "happy"
        assert result[0].score == 0.7


@pytest.mark.asyncio
async def test_text_to_speech_returns_raw_bytes(hf: HuggingFace) -> None:
    """text_to_speech: returns the raw synthesized audio bytes."""
    audio_bytes = b"fLaCfakeaudiopayload"
    with respx.mock(base_url=_INFERENCE) as mock:
        route = mock.post("/models/espnet/kan-bayashi_ljspeech_vits").mock(
            return_value=httpx.Response(
                200, content=audio_bytes, headers={"Content-Type": "audio/flac"}
            )
        )

        result = await hf.atext_to_speech(
            model="espnet/kan-bayashi_ljspeech_vits",
            inputs="Hello there",
        )

        assert result == audio_bytes
        body = route.calls.last.request.read()
        assert b'"inputs"' in body


# ---------------------------------------------------------------------------
# 16. Hub — datasets (get) and Spaces (list / get)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_dataset_happy_path(hf: HuggingFace) -> None:
    """get_dataset: GET /datasets/{id} on the Hub → HFDatasetInfo."""
    with respx.mock(base_url=_HUB) as mock:
        mock.get("/datasets/squad").mock(
            return_value=httpx.Response(
                200,
                json={"id": "squad", "author": "rajpurkar", "downloads": 50000, "likes": 300},
            )
        )

        result = await hf.aget_dataset(dataset_id="squad")

        assert result.id == "squad"
        assert result.author == "rajpurkar"
        assert result.likes == 300


@pytest.mark.asyncio
async def test_list_spaces_happy_path(hf: HuggingFace) -> None:
    """list_spaces: GET /spaces on the Hub, forwards params → [HFSpaceInfo]."""
    with respx.mock(base_url=_HUB, assert_all_called=True) as mock:
        route = mock.get("/spaces").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "id": "stabilityai/stable-diffusion",
                        "author": "stabilityai",
                        "sdk": "gradio",
                        "likes": 9000,
                        "tags": ["diffusion"],
                    }
                ],
            )
        )

        result = await hf.alist_spaces(sort="likes", direction=-1, limit=3)

        assert len(result) == 1
        assert result[0].id == "stabilityai/stable-diffusion"
        assert result[0].sdk == "gradio"
        assert result[0].likes == 9000

        request = route.calls.last.request
        assert request.url.params["sort"] == "likes"
        assert request.url.params["limit"] == "3"


@pytest.mark.asyncio
async def test_get_space_happy_path(hf: HuggingFace) -> None:
    """get_space: GET /spaces/{id} on the Hub → HFSpaceInfo."""
    with respx.mock(base_url=_HUB) as mock:
        mock.get("/spaces/huggingface/diffuse-the-rest").mock(
            return_value=httpx.Response(
                200,
                json={"id": "huggingface/diffuse-the-rest", "sdk": "static", "likes": 42},
            )
        )

        result = await hf.aget_space(space_id="huggingface/diffuse-the-rest")

        assert result.id == "huggingface/diffuse-the-rest"
        assert result.sdk == "static"


# ---------------------------------------------------------------------------
# 17. Error mapping — additional typed exceptions on new actions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_completion_validation_error(hf: HuggingFace) -> None:
    """Router 422 → typed :class:`ValidationError` carrying the connector."""
    with respx.mock(base_url=_ROUTER) as mock:
        mock.post("/v1/chat/completions").mock(
            return_value=httpx.Response(422, json={"error": "bad request"})
        )

        with pytest.raises(ValidationError) as exc_info:
            await hf.achat_completion(
                model="bad-model",
                messages=[{"role": "user", "content": "hi"}],
            )

        assert exc_info.value.connector == "huggingface"
        assert exc_info.value.upstream_status == 422


@pytest.mark.asyncio
async def test_get_model_not_found_raises(hf: HuggingFace) -> None:
    """Hub 404 → typed :class:`NotFoundError` carrying the connector."""
    with respx.mock(base_url=_HUB) as mock:
        mock.get("/models/does-not-exist").mock(
            return_value=httpx.Response(404, json={"error": "Repo not found"})
        )

        with pytest.raises(NotFoundError) as exc_info:
            await hf.aget_model(model_id="does-not-exist")

        assert exc_info.value.connector == "huggingface"
        assert exc_info.value.upstream_status == 404


# ---------------------------------------------------------------------------
# 18. Spec metadata
# ---------------------------------------------------------------------------


def test_spec_metadata() -> None:
    """Connector spec exposes the expected identity and a read action set."""
    spec = HuggingFace.get_spec()
    assert spec.name == "huggingface"
    assert spec.display_name == "Hugging Face"
    assert spec.verification_status == "pattern"
    # All actions are read/generate — none should be flagged dangerous.
    assert all(not a.dangerous for a in spec.actions.values())
    # Idempotent search/lookup actions are flagged as such.
    assert spec.actions["list_models"].idempotent is True
    assert spec.actions["whoami"].idempotent is True
    assert spec.actions["sentence_similarity"].idempotent is True
    # Comprehensive coverage: the full inference task set plus Hub metadata.
    assert len(spec.actions) >= 25
    for name in (
        "chat_completion",
        "text_to_image",
        "automatic_speech_recognition",
        "token_classification",
        "table_question_answering",
        "list_spaces",
        "get_dataset",
    ):
        assert name in spec.actions
