"""End-to-end tests for the Cohere connector using respx.

Same pattern as test_openai.py / test_anthropic.py. Exercises Cohere's
specifics:

  - **Per-request httpx.AsyncClient** — connector creates a fresh client
    inside ``_request()``; respx still intercepts because it patches the
    transport globally.
  - **Version-in-path routing** — ``base_url`` is bare ``https://api.cohere.com``
    and Cohere mixes v1/v2, so chat hits ``/v2/chat`` while tokenize hits
    ``/v1/tokenize`` and jobs/datasets/finetuning hit ``/v1/...``. Tests
    assert the version segment is correct.
  - **Flattened chat text** — the assistant reply is pulled out of
    ``message.content[0].text`` onto ``ChatResponse.text``.
  - **Optional params omitted when None** — ``temperature`` / ``max_tokens``
    must NOT appear in the body when unset (vendor APIs distinguish null
    from absent).
  - **Wrapped single-object responses** — get_dataset / finetuning unwrap a
    top-level ``"dataset"`` / ``"finetuned_model"`` key.
  - **Empty-body 200s** — cancel / delete endpoints return no body; the
    connector maps that to ``True``.
"""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
import respx

from toolsconnector.connectors.cohere import Cohere
from toolsconnector.errors import InvalidCredentialsError, NotFoundError, RateLimitError

BASE_URL = "https://api.cohere.com"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def cohere() -> Cohere:
    """Cohere connector with a fake API key.

    Key never hits api.cohere.com because respx patches httpx.
    """
    connector = Cohere(credentials="co-fake-test-key")
    await connector._setup()
    yield connector
    await connector._teardown()


# ---------------------------------------------------------------------------
# 1. Happy path — chat
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_happy_path(cohere: Cohere) -> None:
    """chat: POST /v2/chat → ChatResponse model.

    Verifies request shape (model + messages in body), Bearer auth,
    version-in-path (``/v2/chat``), and flattened text + usage parsing.
    """
    with respx.mock(base_url=BASE_URL, assert_all_called=True) as respx_mock:
        route = respx_mock.post("/v2/chat").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "chat-abc123",
                    "finish_reason": "COMPLETE",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "Hi there!"}],
                    },
                    "usage": {"tokens": {"input_tokens": 7, "output_tokens": 4}},
                },
            )
        )

        result = await cohere.achat(
            model="command-r-plus",
            messages=[{"role": "user", "content": "Say hi"}],
        )

        # Flattened text + top-level fields
        assert result.id == "chat-abc123"
        assert result.text == "Hi there!"
        assert result.role == "assistant"
        assert result.finish_reason == "COMPLETE"

        # Usage parsed from nested usage.tokens
        assert result.usage is not None
        assert result.usage.input_tokens == 7
        assert result.usage.output_tokens == 4

        # Auth header
        request = route.calls.last.request
        assert request.headers["authorization"] == "Bearer co-fake-test-key"
        assert request.headers["content-type"] == "application/json"

        # Body has model + messages
        body = request.read()
        assert b'"model":"command-r-plus"' in body
        assert b'"messages"' in body


@pytest.mark.asyncio
async def test_chat_optional_params_omitted_when_none(cohere: Cohere) -> None:
    """When ``temperature=None`` and ``max_tokens=None``, those keys must
    NOT appear in the request body — Cohere distinguishes null from absent.
    """
    with respx.mock(base_url=BASE_URL) as respx_mock:
        route = respx_mock.post("/v2/chat").mock(
            return_value=httpx.Response(
                200,
                json={"id": "x", "message": {"role": "assistant", "content": []}},
            )
        )

        await cohere.achat(
            model="command-r-plus",
            messages=[{"role": "user", "content": "hi"}],
        )

        body = route.calls.last.request.read()
        assert b'"model"' in body
        assert b'"messages"' in body
        assert b'"temperature"' not in body
        assert b'"max_tokens"' not in body
        assert b'"tools"' not in body
        assert b'"documents"' not in body


@pytest.mark.asyncio
async def test_chat_passes_tools_and_documents(cohere: Cohere) -> None:
    """chat: ``tools``, ``documents`` and ``response_format`` are forwarded
    into the body when supplied (RAG + tool-use + structured output)."""
    with respx.mock(base_url=BASE_URL) as respx_mock:
        route = respx_mock.post("/v2/chat").mock(
            return_value=httpx.Response(
                200,
                json={"id": "x", "message": {"role": "assistant", "content": []}},
            )
        )

        await cohere.achat(
            model="command-r-plus",
            messages=[{"role": "user", "content": "hi"}],
            tools=[{"type": "function", "function": {"name": "lookup"}}],
            documents=[{"id": "d1", "data": {"text": "ground truth"}}],
            response_format={"type": "json_object"},
        )

        body = route.calls.last.request.read()
        assert b'"tools"' in body
        assert b'"documents"' in body
        assert b'"response_format"' in body


# ---------------------------------------------------------------------------
# 2. Embeddings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_happy_path(cohere: Cohere) -> None:
    """embed: POST /v2/embed → EmbedResponse with embeddings keyed by type.

    Also asserts ``input_type`` lands in the body and ``embedding_types``
    defaults to ``['float']`` when omitted.
    """
    with respx.mock(base_url=BASE_URL) as respx_mock:
        route = respx_mock.post("/v2/embed").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "embed-1",
                    "embeddings": {"float": [[0.1, 0.2, 0.3]]},
                    "texts": ["hello world"],
                    "usage": {"tokens": {"input_tokens": 2, "output_tokens": 0}},
                },
            )
        )

        result = await cohere.aembed(
            model="embed-english-v3.0",
            texts=["hello world"],
            input_type="search_document",
        )

        assert result.embeddings["float"][0] == [0.1, 0.2, 0.3]
        assert result.texts == ["hello world"]
        assert result.usage is not None
        assert result.usage.input_tokens == 2

        body = route.calls.last.request.read()
        assert b'"input_type":"search_document"' in body
        # embedding_types defaults to ["float"] when omitted
        assert b'"embedding_types":["float"]' in body
        # truncate omitted when not supplied
        assert b'"truncate"' not in body


# ---------------------------------------------------------------------------
# 3. Rerank
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rerank_happy_path(cohere: Cohere) -> None:
    """rerank: POST /v2/rerank → results ordered by relevance_score.

    ``top_n`` is passed through to the body; results carry index +
    relevance_score so callers can index back into their document list.
    """
    with respx.mock(base_url=BASE_URL) as respx_mock:
        route = respx_mock.post("/v2/rerank").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "rerank-1",
                    "results": [
                        {"index": 2, "relevance_score": 0.98},
                        {"index": 0, "relevance_score": 0.42},
                    ],
                },
            )
        )

        result = await cohere.arerank(
            model="rerank-english-v3.0",
            query="capital of france",
            documents=["a", "b", "c"],
            top_n=2,
        )

        assert len(result.results) == 2
        assert result.results[0].index == 2
        assert result.results[0].relevance_score == 0.98

        body = route.calls.last.request.read()
        assert b'"top_n":2' in body
        assert b'"query":"capital of france"' in body


# ---------------------------------------------------------------------------
# 4. Classify
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_classify_happy_path(cohere: Cohere) -> None:
    """classify: POST /v1/classify → one ClassifyPrediction per input."""
    with respx.mock(base_url=BASE_URL, assert_all_called=True) as respx_mock:
        respx_mock.post("/v1/classify").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "classify-1",
                    "classifications": [
                        {
                            "input": "great product",
                            "prediction": "positive",
                            "confidence": 0.91,
                            "labels": {"positive": {"confidence": 0.91}},
                        }
                    ],
                },
            )
        )

        result = await cohere.aclassify(
            model="embed-english-v3.0",
            inputs=["great product"],
            examples=[{"text": "love it", "label": "positive"}],
        )

        assert len(result.classifications) == 1
        assert result.classifications[0].prediction == "positive"
        assert result.classifications[0].confidence == 0.91


# ---------------------------------------------------------------------------
# 5. Tokenize / detokenize — verify v1 path is used (not v2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tokenize_uses_v1_path(cohere: Cohere) -> None:
    """tokenize: POST /v1/tokenize → TokenizeResponse.

    Cohere mixes versions; tokenize is a v1 endpoint while chat/embed are
    v2. This pins the version segment so a refactor can't silently swap it.
    """
    with respx.mock(base_url=BASE_URL, assert_all_called=True) as respx_mock:
        respx_mock.post("/v1/tokenize").mock(
            return_value=httpx.Response(
                200,
                json={"tokens": [10002, 2261], "token_strings": ["hel", "lo"]},
            )
        )

        result = await cohere.atokenize(model="command-r-plus", text="hello")

        assert result.tokens == [10002, 2261]
        assert result.token_strings == ["hel", "lo"]


@pytest.mark.asyncio
async def test_detokenize_uses_v1_path(cohere: Cohere) -> None:
    """detokenize: POST /v1/detokenize → reconstructed text."""
    with respx.mock(base_url=BASE_URL, assert_all_called=True) as respx_mock:
        respx_mock.post("/v1/detokenize").mock(
            return_value=httpx.Response(200, json={"text": "hello"})
        )

        result = await cohere.adetokenize(model="command-r-plus", tokens=[10002, 2261])

        assert result.text == "hello"


# ---------------------------------------------------------------------------
# 6. Models — list + get
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_models_happy_path(cohere: Cohere) -> None:
    """list_models: GET /v1/models → list of CohereModel; filters forwarded."""
    with respx.mock(base_url=BASE_URL) as respx_mock:
        route = respx_mock.get("/v1/models").mock(
            return_value=httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "name": "command-r-plus",
                            "endpoints": ["chat"],
                            "context_length": 128000,
                            "finetuned": False,
                        }
                    ]
                },
            )
        )

        result = await cohere.alist_models(endpoint="chat")

        assert len(result) == 1
        assert result[0].name == "command-r-plus"
        assert result[0].context_length == 128000
        assert result[0].endpoints == ["chat"]
        assert "endpoint=chat" in str(route.calls.last.request.url)


@pytest.mark.asyncio
async def test_get_model_happy_path(cohere: Cohere) -> None:
    """get_model: GET /v1/models/{model} → single CohereModel."""
    with respx.mock(base_url=BASE_URL, assert_all_called=True) as respx_mock:
        respx_mock.get("/v1/models/command-r-plus").mock(
            return_value=httpx.Response(
                200,
                json={
                    "name": "command-r-plus",
                    "endpoints": ["chat"],
                    "context_length": 128000,
                    "tokenizer_url": "https://example.com/tok.json",
                },
            )
        )

        result = await cohere.aget_model(model="command-r-plus")

        assert result.name == "command-r-plus"
        assert result.tokenizer_url == "https://example.com/tok.json"


# ---------------------------------------------------------------------------
# 7. Embed jobs (batch embeddings) — v1
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_embed_job_happy_path(cohere: Cohere) -> None:
    """create_embed_job: POST /v1/embed-jobs → EmbedJob with job_id.

    Required fields land in the body; optional ``name`` is forwarded.
    """
    with respx.mock(base_url=BASE_URL, assert_all_called=True) as respx_mock:
        route = respx_mock.post("/v1/embed-jobs").mock(
            return_value=httpx.Response(
                200,
                json={"job_id": "job-xyz", "meta": {"api_version": {"version": "1"}}},
            )
        )

        result = await cohere.acreate_embed_job(
            model="embed-english-v3.0",
            dataset_id="ds-1",
            input_type="search_document",
            name="nightly",
        )

        assert result.job_id == "job-xyz"

        body = route.calls.last.request.read()
        assert b'"dataset_id":"ds-1"' in body
        assert b'"input_type":"search_document"' in body
        assert b'"name":"nightly"' in body


@pytest.mark.asyncio
async def test_list_embed_jobs_happy_path(cohere: Cohere) -> None:
    """list_embed_jobs: GET /v1/embed-jobs → unwraps ``embed_jobs`` array."""
    with respx.mock(base_url=BASE_URL) as respx_mock:
        respx_mock.get("/v1/embed-jobs").mock(
            return_value=httpx.Response(
                200,
                json={
                    "embed_jobs": [
                        {
                            "job_id": "job-1",
                            "status": "complete",
                            "input_dataset_id": "ds-1",
                            "output_dataset_id": "ds-1-out",
                            "model": "embed-english-v3.0",
                        }
                    ]
                },
            )
        )

        result = await cohere.alist_embed_jobs()

        assert len(result) == 1
        assert result[0].job_id == "job-1"
        assert result[0].status == "complete"
        assert result[0].output_dataset_id == "ds-1-out"


@pytest.mark.asyncio
async def test_get_embed_job_happy_path(cohere: Cohere) -> None:
    """get_embed_job: GET /v1/embed-jobs/{id} → EmbedJob (flat object)."""
    with respx.mock(base_url=BASE_URL, assert_all_called=True) as respx_mock:
        respx_mock.get("/v1/embed-jobs/job-1").mock(
            return_value=httpx.Response(
                200,
                json={"job_id": "job-1", "status": "processing", "truncate": "END"},
            )
        )

        result = await cohere.aget_embed_job(embed_job_id="job-1")

        assert result.job_id == "job-1"
        assert result.status == "processing"
        assert result.truncate == "END"


@pytest.mark.asyncio
async def test_cancel_embed_job_returns_true_on_empty_body(cohere: Cohere) -> None:
    """cancel_embed_job: POST /v1/embed-jobs/{id}/cancel → True.

    Cohere returns 200 with an empty body; the connector maps that to True.
    """
    with respx.mock(base_url=BASE_URL, assert_all_called=True) as respx_mock:
        route = respx_mock.post("/v1/embed-jobs/job-1/cancel").mock(
            return_value=httpx.Response(200)
        )

        result = await cohere.acancel_embed_job(embed_job_id="job-1")

        assert result is True
        assert route.calls.last.request.method == "POST"


# ---------------------------------------------------------------------------
# 8. Datasets — v1
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_dataset_multipart_then_fetches_full(cohere: Cohere) -> None:
    """create_dataset: POST /v1/datasets (multipart, name+type as query params).

    The create call returns only ``{"id": ...}``; the connector then GETs
    the dataset so the caller gets a populated model. Asserts both calls
    fire and the file rides as multipart form data.
    """
    with respx.mock(base_url=BASE_URL, assert_all_called=True) as respx_mock:
        create_route = respx_mock.post("/v1/datasets").mock(
            return_value=httpx.Response(200, json={"id": "ds-new"})
        )
        respx_mock.get("/v1/datasets/ds-new").mock(
            return_value=httpx.Response(
                200,
                json={
                    "dataset": {
                        "id": "ds-new",
                        "name": "my-data",
                        "dataset_type": "embed-input",
                        "validation_status": "validated",
                        "dataset_parts": [{"name": "part0", "num_rows": 100, "size_bytes": 2048}],
                    }
                },
            )
        )

        result = await cohere.acreate_dataset(
            name="my-data",
            type="embed-input",
            data=b'{"text": "hi"}\n',
        )

        assert result.id == "ds-new"
        assert result.name == "my-data"
        assert result.validation_status == "validated"
        assert result.dataset_parts[0].num_rows == 100

        # name/type are query params; file is multipart
        create_req = create_route.calls.last.request
        assert "name=my-data" in str(create_req.url)
        assert "type=embed-input" in str(create_req.url)
        assert create_req.headers["content-type"].startswith("multipart/form-data")


@pytest.mark.asyncio
async def test_list_datasets_happy_path(cohere: Cohere) -> None:
    """list_datasets: GET /v1/datasets → unwraps ``datasets`` array; filters
    forwarded as query params (``datasetType``)."""
    with respx.mock(base_url=BASE_URL) as respx_mock:
        route = respx_mock.get("/v1/datasets").mock(
            return_value=httpx.Response(
                200,
                json={
                    "datasets": [
                        {
                            "id": "ds-1",
                            "name": "first",
                            "dataset_type": "embed-input",
                            "validation_status": "validated",
                        }
                    ]
                },
            )
        )

        result = await cohere.alist_datasets(dataset_type="embed-input", limit=10)

        assert len(result) == 1
        assert result[0].id == "ds-1"
        assert result[0].dataset_type == "embed-input"

        url = str(route.calls.last.request.url)
        assert "datasetType=embed-input" in url
        assert "limit=10" in url


@pytest.mark.asyncio
async def test_get_dataset_unwraps_dataset_key(cohere: Cohere) -> None:
    """get_dataset: GET /v1/datasets/{id} → unwraps top-level ``dataset`` key.

    Also checks the ``schema`` field maps to the ``schema_`` alias attr.
    """
    with respx.mock(base_url=BASE_URL, assert_all_called=True) as respx_mock:
        respx_mock.get("/v1/datasets/ds-1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "dataset": {
                        "id": "ds-1",
                        "name": "first",
                        "schema": "avro-schema-string",
                        "required_fields": ["text"],
                    }
                },
            )
        )

        result = await cohere.aget_dataset(dataset_id="ds-1")

        assert result.id == "ds-1"
        assert result.schema_ == "avro-schema-string"
        assert result.required_fields == ["text"]


@pytest.mark.asyncio
async def test_delete_dataset_returns_true_on_empty_body(cohere: Cohere) -> None:
    """delete_dataset: DELETE /v1/datasets/{id} → True on empty body."""
    with respx.mock(base_url=BASE_URL, assert_all_called=True) as respx_mock:
        route = respx_mock.delete("/v1/datasets/ds-1").mock(
            return_value=httpx.Response(200, json={})
        )

        result = await cohere.adelete_dataset(dataset_id="ds-1")

        assert result is True
        assert route.calls.last.request.method == "DELETE"


@pytest.mark.asyncio
async def test_get_dataset_usage_happy_path(cohere: Cohere) -> None:
    """get_dataset_usage: GET /v1/datasets/usage → organization_usage bytes."""
    with respx.mock(base_url=BASE_URL, assert_all_called=True) as respx_mock:
        respx_mock.get("/v1/datasets/usage").mock(
            return_value=httpx.Response(200, json={"organization_usage": 123456})
        )

        result = await cohere.aget_dataset_usage()

        assert result.organization_usage == 123456


# ---------------------------------------------------------------------------
# 9. Fine-tuning — v1
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_finetuned_model_unwraps_key(cohere: Cohere) -> None:
    """create_finetuned_model: POST /v1/finetuning/finetuned-models.

    Body carries ``name`` + ``settings``; response unwraps the top-level
    ``finetuned_model`` object.
    """
    with respx.mock(base_url=BASE_URL, assert_all_called=True) as respx_mock:
        route = respx_mock.post("/v1/finetuning/finetuned-models").mock(
            return_value=httpx.Response(
                200,
                json={
                    "finetuned_model": {
                        "id": "ft-1",
                        "name": "my-ft",
                        "status": "STATUS_QUEUED",
                        "settings": {"dataset_id": "ds-1"},
                    }
                },
            )
        )

        result = await cohere.acreate_finetuned_model(
            name="my-ft",
            settings={
                "base_model": {"base_type": "BASE_TYPE_CHAT"},
                "dataset_id": "ds-1",
            },
        )

        assert result.id == "ft-1"
        assert result.status == "STATUS_QUEUED"
        assert result.settings["dataset_id"] == "ds-1"

        body = route.calls.last.request.read()
        assert b'"name":"my-ft"' in body
        assert b'"settings"' in body
        assert b'"base_type":"BASE_TYPE_CHAT"' in body


@pytest.mark.asyncio
async def test_list_finetuned_models_happy_path(cohere: Cohere) -> None:
    """list_finetuned_models: GET .../finetuned-models → unwraps array."""
    with respx.mock(base_url=BASE_URL) as respx_mock:
        respx_mock.get("/v1/finetuning/finetuned-models").mock(
            return_value=httpx.Response(
                200,
                json={
                    "finetuned_models": [
                        {"id": "ft-1", "name": "a", "status": "STATUS_READY"},
                        {"id": "ft-2", "name": "b", "status": "STATUS_FINETUNING"},
                    ]
                },
            )
        )

        result = await cohere.alist_finetuned_models()

        assert len(result) == 2
        assert result[0].id == "ft-1"
        assert result[1].status == "STATUS_FINETUNING"


@pytest.mark.asyncio
async def test_get_finetuned_model_happy_path(cohere: Cohere) -> None:
    """get_finetuned_model: GET .../finetuned-models/{id} → unwraps object."""
    with respx.mock(base_url=BASE_URL, assert_all_called=True) as respx_mock:
        respx_mock.get("/v1/finetuning/finetuned-models/ft-1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "finetuned_model": {
                        "id": "ft-1",
                        "name": "a",
                        "status": "STATUS_READY",
                        "creator_id": "user-1",
                    }
                },
            )
        )

        result = await cohere.aget_finetuned_model(finetuned_model_id="ft-1")

        assert result.id == "ft-1"
        assert result.creator_id == "user-1"


@pytest.mark.asyncio
async def test_delete_finetuned_model_returns_true(cohere: Cohere) -> None:
    """delete_finetuned_model: DELETE .../finetuned-models/{id} → True."""
    with respx.mock(base_url=BASE_URL, assert_all_called=True) as respx_mock:
        route = respx_mock.delete("/v1/finetuning/finetuned-models/ft-1").mock(
            return_value=httpx.Response(200, json={})
        )

        result = await cohere.adelete_finetuned_model(finetuned_model_id="ft-1")

        assert result is True
        assert route.calls.last.request.method == "DELETE"


# ---------------------------------------------------------------------------
# 10. Auth — check_api_key
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_api_key_happy_path(cohere: Cohere) -> None:
    """check_api_key: POST /v1/check-api-key → ApiKeyCheck."""
    with respx.mock(base_url=BASE_URL, assert_all_called=True) as respx_mock:
        respx_mock.post("/v1/check-api-key").mock(
            return_value=httpx.Response(
                200,
                json={"valid": True, "organization_id": "org-1", "owner_id": "owner-1"},
            )
        )

        result = await cohere.acheck_api_key()

        assert result.valid is True
        assert result.organization_id == "org-1"
        assert result.owner_id == "owner-1"


# ---------------------------------------------------------------------------
# 11. Error mapping — typed exceptions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_api_key_raises_invalid_credentials_error(cohere: Cohere) -> None:
    """Cohere 401 → typed :class:`InvalidCredentialsError` carrying the
    connector name and upstream status.
    """
    with respx.mock(base_url=BASE_URL) as respx_mock:
        respx_mock.post("/v2/chat").mock(
            return_value=httpx.Response(401, json={"message": "invalid api token"})
        )

        with pytest.raises(InvalidCredentialsError) as exc_info:
            await cohere.achat(
                model="command-r-plus",
                messages=[{"role": "user", "content": "hi"}],
            )

        assert exc_info.value.connector == "cohere"
        assert exc_info.value.upstream_status == 401


@pytest.mark.asyncio
async def test_rate_limit_raises_rate_limit_error(cohere: Cohere) -> None:
    """Cohere 429 → typed :class:`RateLimitError` with ``retry_after_seconds``
    parsed from the ``Retry-After`` header.
    """
    with respx.mock(base_url=BASE_URL) as respx_mock:
        respx_mock.post("/v2/chat").mock(
            return_value=httpx.Response(
                429,
                headers={"Retry-After": "15"},
                json={"message": "rate limit exceeded"},
            )
        )

        with pytest.raises(RateLimitError) as exc_info:
            await cohere.achat(
                model="command-r-plus",
                messages=[{"role": "user", "content": "hi"}],
            )

        assert exc_info.value.connector == "cohere"
        assert exc_info.value.upstream_status == 429
        assert exc_info.value.retry_after_seconds == 15.0


@pytest.mark.asyncio
async def test_get_dataset_not_found_raises_not_found_error(cohere: Cohere) -> None:
    """A 404 on a typed GET endpoint (get_dataset) → :class:`NotFoundError`.

    Covers the v1 dataset path's error surface, not just the v2 chat path.
    """
    with respx.mock(base_url=BASE_URL) as respx_mock:
        respx_mock.get("/v1/datasets/missing").mock(
            return_value=httpx.Response(404, json={"message": "dataset not found"})
        )

        with pytest.raises(NotFoundError) as exc_info:
            await cohere.aget_dataset(dataset_id="missing")

        assert exc_info.value.connector == "cohere"
        assert exc_info.value.upstream_status == 404


# ---------------------------------------------------------------------------
# 12. Spec metadata
# ---------------------------------------------------------------------------


def test_spec_metadata() -> None:
    """Spec exposes the expected name, category, and the full action set.

    Read/generate actions are not flagged dangerous; destructive
    delete/cancel actions are.
    """
    spec = Cohere.get_spec()
    assert spec.name == "cohere"
    assert spec.verification_status == "pattern"

    expected = {
        # inference
        "chat",
        "embed",
        "rerank",
        "classify",
        "tokenize",
        "detokenize",
        # models
        "list_models",
        "get_model",
        # embed jobs
        "create_embed_job",
        "list_embed_jobs",
        "get_embed_job",
        "cancel_embed_job",
        # datasets
        "create_dataset",
        "list_datasets",
        "get_dataset",
        "delete_dataset",
        "get_dataset_usage",
        # fine-tuning
        "create_finetuned_model",
        "list_finetuned_models",
        "get_finetuned_model",
        "delete_finetuned_model",
        # auth
        "check_api_key",
    }
    assert expected.issubset(set(spec.actions))
    assert len(spec.actions) == 22

    # Idempotent read actions flagged as such.
    assert spec.actions["list_models"].idempotent is True
    assert spec.actions["tokenize"].idempotent is True
    assert spec.actions["get_dataset"].idempotent is True
    assert spec.actions["check_api_key"].idempotent is True

    # Generate actions are not dangerous (spend money, don't destroy state).
    assert spec.actions["chat"].dangerous is False
    assert spec.actions["create_embed_job"].dangerous is False

    # Destructive deletes / cancels are flagged dangerous.
    assert spec.actions["delete_dataset"].dangerous is True
    assert spec.actions["delete_finetuned_model"].dangerous is True
    assert spec.actions["cancel_embed_job"].dangerous is True
