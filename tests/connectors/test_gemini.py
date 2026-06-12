"""End-to-end tests for the Google Gemini connector using respx.

Same pattern as test_openai.py / test_anthropic.py. Exercises Gemini's
specifics:

  - **API key in the ``x-goog-api-key`` header** — never in the URL query
    string (project privacy rule forbids secrets in URLs).
  - **Per-request ``httpx.AsyncClient``** — the connector creates a fresh
    client inside ``_request()``; respx still intercepts because it patches
    the transport globally.
  - **Colon-suffixed RPC-style paths** — endpoints look like
    ``/models/{model}:generateContent``.
  - **``models/`` prefix normalisation** — a bare model id and one already
    carrying the ``models/`` prefix hit the same URL.
  - **Optional ``generationConfig`` / ``systemInstruction``** — must be absent
    from the request body when the corresponding args are ``None``.
"""

from __future__ import annotations

import json

import httpx
import pytest
import pytest_asyncio
import respx

from toolsconnector.connectors.gemini import Gemini
from toolsconnector.errors import (
    InvalidCredentialsError,
    NotFoundError,
    RateLimitError,
    ServerError,
    ValidationError,
)

_UPLOAD_URL = "https://generativelanguage.googleapis.com/upload/v1beta"

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def gemini() -> Gemini:
    """Gemini connector with a fake API key.

    Key never hits generativelanguage.googleapis.com because respx patches httpx.
    """
    connector = Gemini(credentials="AIza-fake-test-key")
    await connector._setup()
    yield connector
    await connector._teardown()


# ---------------------------------------------------------------------------
# 1. Happy path — generate_content
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_content_happy_path(gemini: Gemini) -> None:
    """generate_content: POST /models/{model}:generateContent → GeminiResponse.

    Verifies the API key rides in the header (not the URL), a string prompt is
    wrapped into a single content turn, and candidates/usage are parsed.
    """
    with respx.mock(base_url=_BASE_URL, assert_all_called=True) as respx_mock:
        route = respx_mock.post("/models/gemini-1.5-flash:generateContent").mock(
            return_value=httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "content": {
                                "role": "model",
                                "parts": [{"text": "Hello "}, {"text": "world!"}],
                            },
                            "finishReason": "STOP",
                        }
                    ],
                    "modelVersion": "gemini-1.5-flash-001",
                    "usageMetadata": {
                        "promptTokenCount": 5,
                        "candidatesTokenCount": 3,
                        "totalTokenCount": 8,
                    },
                },
            )
        )

        result = await gemini.agenerate_content(
            model="gemini-1.5-flash",
            contents="Say hello",
        )

        # Parts concatenated into a single text string
        assert result.text == "Hello world!"
        assert result.finish_reason == "STOP"
        assert result.model_version == "gemini-1.5-flash-001"

        # Usage parsed from usageMetadata
        assert result.usage is not None
        assert result.usage.total_token_count == 8
        assert result.usage.prompt_token_count == 5

        # Raw candidate list preserved
        assert len(result.candidates) == 1

        request = route.calls.last.request
        # Auth key in header, NOT in URL
        assert request.headers["x-goog-api-key"] == "AIza-fake-test-key"
        assert request.headers["content-type"] == "application/json"
        assert "key=" not in str(request.url)
        assert "AIza-fake-test-key" not in str(request.url)

        # String prompt wrapped into contents[].parts[].text
        body = request.read()
        assert b'"contents"' in body
        assert b'"Say hello"' in body


@pytest.mark.asyncio
async def test_generate_content_optional_params_omitted_when_none(gemini: Gemini) -> None:
    """When temperature/max_output_tokens/system_instruction are None, neither
    ``generationConfig`` nor ``systemInstruction`` may appear in the body.
    """
    with respx.mock(base_url=_BASE_URL) as respx_mock:
        route = respx_mock.post("/models/gemini-1.5-flash:generateContent").mock(
            return_value=httpx.Response(200, json={"candidates": []})
        )

        await gemini.agenerate_content(
            model="gemini-1.5-flash",
            contents="hi",
        )

        body = route.calls.last.request.read()
        assert b'"contents"' in body
        assert b'"generationConfig"' not in body
        assert b'"systemInstruction"' not in body


@pytest.mark.asyncio
async def test_generate_content_with_config_and_system_instruction(gemini: Gemini) -> None:
    """temperature + max_output_tokens land inside generationConfig, and
    system_instruction is wrapped into systemInstruction.parts[].text.
    """
    with respx.mock(base_url=_BASE_URL) as respx_mock:
        route = respx_mock.post("/models/gemini-1.5-pro:generateContent").mock(
            return_value=httpx.Response(
                200,
                json={
                    "candidates": [{"content": {"parts": [{"text": "ok"}]}, "finishReason": "STOP"}]
                },
            )
        )

        result = await gemini.agenerate_content(
            model="gemini-1.5-pro",
            contents="hi",
            system_instruction="You are terse.",
            temperature=0.2,
            max_output_tokens=64,
        )

        assert result.text == "ok"

        body = route.calls.last.request.read()
        assert b'"generationConfig"' in body
        assert b'"temperature"' in body
        assert b'"maxOutputTokens"' in body
        assert b'"systemInstruction"' in body
        assert b'"You are terse."' in body


@pytest.mark.asyncio
async def test_generate_content_accepts_prebuilt_contents_list(gemini: Gemini) -> None:
    """A pre-built list of content dicts is forwarded verbatim (not re-wrapped)."""
    with respx.mock(base_url=_BASE_URL) as respx_mock:
        route = respx_mock.post("/models/gemini-1.5-flash:generateContent").mock(
            return_value=httpx.Response(
                200,
                json={"candidates": [{"content": {"parts": [{"text": "hey"}]}}]},
            )
        )

        await gemini.agenerate_content(
            model="gemini-1.5-flash",
            contents=[{"role": "user", "parts": [{"text": "multi-turn"}]}],
        )

        body = route.calls.last.request.read()
        assert b'"role":"user"' in body
        assert b'"multi-turn"' in body


# ---------------------------------------------------------------------------
# 2. Happy path — count_tokens
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_count_tokens_happy_path(gemini: Gemini) -> None:
    """count_tokens: POST /models/{model}:countTokens → TokenCount."""
    with respx.mock(base_url=_BASE_URL) as respx_mock:
        route = respx_mock.post("/models/gemini-1.5-flash:countTokens").mock(
            return_value=httpx.Response(200, json={"totalTokens": 42})
        )

        result = await gemini.acount_tokens(model="gemini-1.5-flash", contents="count me")

        assert result.total_tokens == 42
        body = route.calls.last.request.read()
        assert b'"contents"' in body
        assert b'"count me"' in body


# ---------------------------------------------------------------------------
# 3. Happy path — embed_content + models/ prefix normalisation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_content_happy_path(gemini: Gemini) -> None:
    """embed_content: POST /models/{model}:embedContent → Embedding.

    Also asserts that passing the model id WITH the ``models/`` prefix hits the
    same canonical URL (no double ``models/models/``).
    """
    with respx.mock(base_url=_BASE_URL) as respx_mock:
        route = respx_mock.post("/models/text-embedding-004:embedContent").mock(
            return_value=httpx.Response(200, json={"embedding": {"values": [0.1, 0.2, 0.3]}})
        )

        result = await gemini.aembed_content(
            model="models/text-embedding-004",
            text="embed me",
            task_type="RETRIEVAL_DOCUMENT",
            title="Doc",
        )

        assert result.values == [0.1, 0.2, 0.3]

        body = route.calls.last.request.read()
        assert b'"content"' in body
        assert b'"embed me"' in body
        assert b'"taskType"' in body
        assert b'"RETRIEVAL_DOCUMENT"' in body
        assert b'"title"' in body


@pytest.mark.asyncio
async def test_embed_content_optional_params_omitted_when_none(gemini: Gemini) -> None:
    """taskType/title must be absent when task_type/title are None."""
    with respx.mock(base_url=_BASE_URL) as respx_mock:
        route = respx_mock.post("/models/text-embedding-004:embedContent").mock(
            return_value=httpx.Response(200, json={"embedding": {"values": [0.5]}})
        )

        await gemini.aembed_content(model="text-embedding-004", text="x")

        body = route.calls.last.request.read()
        assert b'"taskType"' not in body
        assert b'"title"' not in body


# ---------------------------------------------------------------------------
# 4. Happy path — batch_embed_contents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_batch_embed_contents_happy_path(gemini: Gemini) -> None:
    """batch_embed_contents: POST /models/{model}:batchEmbedContents → BatchEmbeddings."""
    with respx.mock(base_url=_BASE_URL) as respx_mock:
        route = respx_mock.post("/models/text-embedding-004:batchEmbedContents").mock(
            return_value=httpx.Response(
                200,
                json={"embeddings": [{"values": [0.1, 0.2]}, {"values": [0.3, 0.4]}]},
            )
        )

        result = await gemini.abatch_embed_contents(
            model="text-embedding-004",
            texts=["first", "second"],
        )

        assert len(result.embeddings) == 2
        assert result.embeddings[0].values == [0.1, 0.2]
        assert result.embeddings[1].values == [0.3, 0.4]

        body = route.calls.last.request.read()
        # Each request carries the fully-qualified model ref
        assert b'"requests"' in body
        assert b'"models/text-embedding-004"' in body
        assert b'"first"' in body
        assert b'"second"' in body


# ---------------------------------------------------------------------------
# 5. Happy path — list_models + get_model
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_models_happy_path(gemini: Gemini) -> None:
    """list_models: GET /models → list[GeminiModel]."""
    with respx.mock(base_url=_BASE_URL) as respx_mock:
        respx_mock.get("/models").mock(
            return_value=httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "name": "models/gemini-1.5-flash",
                            "version": "001",
                            "displayName": "Gemini 1.5 Flash",
                            "inputTokenLimit": 1000000,
                            "outputTokenLimit": 8192,
                            "supportedGenerationMethods": ["generateContent", "countTokens"],
                        }
                    ]
                },
            )
        )

        models = await gemini.alist_models()

        assert len(models) == 1
        assert models[0].name == "models/gemini-1.5-flash"
        assert models[0].display_name == "Gemini 1.5 Flash"
        assert models[0].input_token_limit == 1000000
        assert "generateContent" in models[0].supported_generation_methods


@pytest.mark.asyncio
async def test_get_model_happy_path(gemini: Gemini) -> None:
    """get_model: GET /models/{model} → GeminiModel."""
    with respx.mock(base_url=_BASE_URL) as respx_mock:
        respx_mock.get("/models/gemini-1.5-flash").mock(
            return_value=httpx.Response(
                200,
                json={
                    "name": "models/gemini-1.5-flash",
                    "version": "001",
                    "displayName": "Gemini 1.5 Flash",
                    "outputTokenLimit": 8192,
                },
            )
        )

        model = await gemini.aget_model(model="gemini-1.5-flash")

        assert model.name == "models/gemini-1.5-flash"
        assert model.output_token_limit == 8192


# ---------------------------------------------------------------------------
# 6. Error mapping — typed exceptions surface from raise_typed_for_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_api_key_raises_invalid_credentials_error(gemini: Gemini) -> None:
    """Gemini 401 → typed :class:`InvalidCredentialsError` carrying the
    connector name and upstream status.
    """
    with respx.mock(base_url=_BASE_URL) as respx_mock:
        respx_mock.post("/models/gemini-1.5-flash:generateContent").mock(
            return_value=httpx.Response(
                401,
                json={
                    "error": {
                        "code": 401,
                        "message": "API key not valid. Please pass a valid API key.",
                        "status": "UNAUTHENTICATED",
                    }
                },
            )
        )

        with pytest.raises(InvalidCredentialsError) as exc_info:
            await gemini.agenerate_content(model="gemini-1.5-flash", contents="hi")

        assert exc_info.value.connector == "gemini"
        assert exc_info.value.upstream_status == 401


@pytest.mark.asyncio
async def test_unknown_model_raises_not_found_error(gemini: Gemini) -> None:
    """Gemini 404 for an unknown model → typed :class:`NotFoundError`."""
    with respx.mock(base_url=_BASE_URL) as respx_mock:
        respx_mock.get("/models/does-not-exist").mock(
            return_value=httpx.Response(
                404,
                json={
                    "error": {
                        "code": 404,
                        "message": "models/does-not-exist is not found.",
                        "status": "NOT_FOUND",
                    }
                },
            )
        )

        with pytest.raises(NotFoundError) as exc_info:
            await gemini.aget_model(model="does-not-exist")

        assert exc_info.value.connector == "gemini"
        assert exc_info.value.upstream_status == 404


@pytest.mark.asyncio
async def test_rate_limit_raises_rate_limit_error(gemini: Gemini) -> None:
    """Gemini 429 → typed :class:`RateLimitError` with ``retry_after_seconds``
    parsed from the ``Retry-After`` header.
    """
    with respx.mock(base_url=_BASE_URL) as respx_mock:
        respx_mock.post("/models/gemini-1.5-flash:generateContent").mock(
            return_value=httpx.Response(
                429,
                headers={"Retry-After": "30"},
                json={"error": {"code": 429, "message": "Resource exhausted."}},
            )
        )

        with pytest.raises(RateLimitError) as exc_info:
            await gemini.agenerate_content(model="gemini-1.5-flash", contents="hi")

        assert exc_info.value.connector == "gemini"
        assert exc_info.value.upstream_status == 429
        assert exc_info.value.retry_after_seconds == 30.0


# ---------------------------------------------------------------------------
# 7. generate_content extras — cached_content reference
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_content_with_cached_content(gemini: Gemini) -> None:
    """A cached_content id is normalised to ``cachedContents/{id}`` and sent as
    the ``cachedContent`` body field.
    """
    with respx.mock(base_url=_BASE_URL) as respx_mock:
        route = respx_mock.post("/models/gemini-1.5-flash:generateContent").mock(
            return_value=httpx.Response(
                200,
                json={
                    "candidates": [{"content": {"parts": [{"text": "ok"}]}}],
                    "usageMetadata": {
                        "promptTokenCount": 10,
                        "totalTokenCount": 12,
                        "cachedContentTokenCount": 8,
                    },
                },
            )
        )

        result = await gemini.agenerate_content(
            model="gemini-1.5-flash",
            contents="hi",
            cached_content="abc123",
        )

        assert result.usage is not None
        assert result.usage.cached_content_token_count == 8

        body = route.calls.last.request.read()
        assert b'"cachedContent":"cachedContents/abc123"' in body


# ---------------------------------------------------------------------------
# 8. Files API — upload / get / list / delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_file_resumable_protocol(gemini: Gemini) -> None:
    """upload_file: a ``start`` request returns an upload URL, then bytes are
    POSTed with ``upload, finalize`` and the File resource is parsed.

    The API key rides in the ``x-goog-api-key`` header on both legs (never the
    URL), and the int64 ``sizeBytes`` string is coerced to an int.
    """
    with respx.mock(assert_all_called=True) as respx_mock:
        # Disambiguate the two POSTs to /files by the upload-command header:
        # respx matches routes in registration order, so the finalize leg
        # (which carries the same path plus a query) must not be captured by
        # the start route.
        start = respx_mock.post(
            f"{_UPLOAD_URL}/files",
            headers={"X-Goog-Upload-Command": "start"},
        ).mock(
            return_value=httpx.Response(
                200,
                headers={"x-goog-upload-url": f"{_UPLOAD_URL}/files?upload_id=xyz"},
            )
        )
        finalize = respx_mock.post(
            f"{_UPLOAD_URL}/files",
            params={"upload_id": "xyz"},
            headers={"X-Goog-Upload-Command": "upload, finalize"},
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "file": {
                        "name": "files/abc-123",
                        "displayName": "photo",
                        "mimeType": "image/png",
                        "sizeBytes": "2048",
                        "state": "ACTIVE",
                        "uri": "https://generativelanguage.googleapis.com/v1beta/files/abc-123",
                    }
                },
            )
        )

        result = await gemini.aupload_file(
            file_content=b"\x89PNG fake bytes",
            mime_type="image/png",
            display_name="photo",
        )

        assert result.name == "files/abc-123"
        assert result.mime_type == "image/png"
        assert result.size_bytes == 2048
        assert result.state == "ACTIVE"
        assert result.uri.endswith("/files/abc-123")

        # First leg announces the resumable upload with the content metadata.
        start_req = start.calls.last.request
        assert start_req.headers["x-goog-upload-protocol"] == "resumable"
        assert start_req.headers["x-goog-upload-command"] == "start"
        assert start_req.headers["x-goog-upload-header-content-type"] == "image/png"
        assert start_req.headers["x-goog-api-key"] == "AIza-fake-test-key"
        assert "AIza-fake-test-key" not in str(start_req.url)

        # Second leg uploads + finalizes the bytes to the returned URL.
        finalize_req = finalize.calls.last.request
        assert finalize_req.headers["x-goog-upload-command"] == "upload, finalize"
        assert finalize_req.headers["x-goog-upload-offset"] == "0"
        assert finalize_req.read() == b"\x89PNG fake bytes"
        assert "AIza-fake-test-key" not in str(finalize_req.url)


@pytest.mark.asyncio
async def test_get_file_happy_path(gemini: Gemini) -> None:
    """get_file: GET /files/{name} → GeminiFile (bare resource, no envelope)."""
    with respx.mock(base_url=_BASE_URL) as respx_mock:
        respx_mock.get("/files/abc-123").mock(
            return_value=httpx.Response(
                200,
                json={
                    "name": "files/abc-123",
                    "mimeType": "application/pdf",
                    "sizeBytes": "512",
                    "state": "ACTIVE",
                },
            )
        )

        # Bare id is normalised to files/{id}.
        result = await gemini.aget_file(name="abc-123")

        assert result.name == "files/abc-123"
        assert result.mime_type == "application/pdf"
        assert result.size_bytes == 512


@pytest.mark.asyncio
async def test_list_files_happy_path(gemini: Gemini) -> None:
    """list_files: GET /files → FileList with pagination params + next token."""
    with respx.mock(base_url=_BASE_URL) as respx_mock:
        route = respx_mock.get("/files").mock(
            return_value=httpx.Response(
                200,
                json={
                    "files": [
                        {"name": "files/one", "state": "ACTIVE"},
                        {"name": "files/two", "state": "PROCESSING"},
                    ],
                    "nextPageToken": "page-2",
                },
            )
        )

        result = await gemini.alist_files(page_size=2, page_token="page-1")

        assert len(result.files) == 2
        assert result.files[0].name == "files/one"
        assert result.next_page_token == "page-2"

        url = str(route.calls.last.request.url)
        assert "pageSize=2" in url
        assert "pageToken=page-1" in url
        assert "AIza-fake-test-key" not in url


@pytest.mark.asyncio
async def test_delete_file_returns_true(gemini: Gemini) -> None:
    """delete_file: DELETE /files/{name} → True on empty 200 body."""
    with respx.mock(base_url=_BASE_URL) as respx_mock:
        route = respx_mock.delete("/files/abc-123").mock(return_value=httpx.Response(200, json={}))

        result = await gemini.adelete_file(name="files/abc-123")

        assert result is True
        assert route.called


# ---------------------------------------------------------------------------
# 9. Context caching — create / get / list / update / delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_cache_happy_path(gemini: Gemini) -> None:
    """create_cache: POST /cachedContents → CachedContent.

    The model is normalised to ``models/{id}``, the system instruction is
    wrapped, and usageMetadata.totalTokenCount is parsed.
    """
    with respx.mock(base_url=_BASE_URL) as respx_mock:
        route = respx_mock.post("/cachedContents").mock(
            return_value=httpx.Response(
                200,
                json={
                    "name": "cachedContents/cache-1",
                    "model": "models/gemini-1.5-flash-001",
                    "displayName": "my-cache",
                    "expireTime": "2026-01-01T00:00:00Z",
                    "usageMetadata": {"totalTokenCount": 4096},
                },
            )
        )

        result = await gemini.acreate_cache(
            model="gemini-1.5-flash-001",
            contents=[{"role": "user", "parts": [{"text": "big context"}]}],
            system_instruction="Be concise.",
            ttl="600s",
            display_name="my-cache",
        )

        assert result.name == "cachedContents/cache-1"
        assert result.model == "models/gemini-1.5-flash-001"
        assert result.expire_time == "2026-01-01T00:00:00Z"
        assert result.usage is not None
        assert result.usage.total_token_count == 4096

        body = route.calls.last.request.read()
        assert b'"model":"models/gemini-1.5-flash-001"' in body
        assert b'"ttl":"600s"' in body
        assert b'"systemInstruction"' in body
        assert b'"Be concise."' in body


@pytest.mark.asyncio
async def test_get_cache_happy_path(gemini: Gemini) -> None:
    """get_cache: GET /cachedContents/{name} → CachedContent."""
    with respx.mock(base_url=_BASE_URL) as respx_mock:
        respx_mock.get("/cachedContents/cache-1").mock(
            return_value=httpx.Response(
                200,
                json={"name": "cachedContents/cache-1", "model": "models/gemini-1.5-flash"},
            )
        )

        # Bare id normalised to cachedContents/{id}.
        result = await gemini.aget_cache(name="cache-1")

        assert result.name == "cachedContents/cache-1"
        assert result.model == "models/gemini-1.5-flash"


@pytest.mark.asyncio
async def test_list_caches_happy_path(gemini: Gemini) -> None:
    """list_caches: GET /cachedContents → CachedContentList."""
    with respx.mock(base_url=_BASE_URL) as respx_mock:
        respx_mock.get("/cachedContents").mock(
            return_value=httpx.Response(
                200,
                json={
                    "cachedContents": [
                        {"name": "cachedContents/a"},
                        {"name": "cachedContents/b"},
                    ],
                    "nextPageToken": "next",
                },
            )
        )

        result = await gemini.alist_caches()

        assert len(result.cached_contents) == 2
        assert result.cached_contents[1].name == "cachedContents/b"
        assert result.next_page_token == "next"


@pytest.mark.asyncio
async def test_update_cache_sends_update_mask(gemini: Gemini) -> None:
    """update_cache: PATCH /cachedContents/{name} with ?updateMask=ttl."""
    with respx.mock(base_url=_BASE_URL) as respx_mock:
        route = respx_mock.patch("/cachedContents/cache-1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "name": "cachedContents/cache-1",
                    "expireTime": "2026-02-02T00:00:00Z",
                },
            )
        )

        result = await gemini.aupdate_cache(name="cache-1", ttl="900s")

        assert result.expire_time == "2026-02-02T00:00:00Z"

        request = route.calls.last.request
        assert "updateMask=ttl" in str(request.url)
        assert b'"ttl":"900s"' in request.read()


@pytest.mark.asyncio
async def test_delete_cache_returns_true(gemini: Gemini) -> None:
    """delete_cache: DELETE /cachedContents/{name} → True."""
    with respx.mock(base_url=_BASE_URL) as respx_mock:
        route = respx_mock.delete("/cachedContents/cache-1").mock(
            return_value=httpx.Response(200, json={})
        )

        result = await gemini.adelete_cache(name="cachedContents/cache-1")

        assert result is True
        assert route.called


# ---------------------------------------------------------------------------
# 10. Tuned models — list / get / create / delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_tuned_models_happy_path(gemini: Gemini) -> None:
    """list_tuned_models: GET /tunedModels → TunedModelList with filter param."""
    with respx.mock(base_url=_BASE_URL) as respx_mock:
        route = respx_mock.get("/tunedModels").mock(
            return_value=httpx.Response(
                200,
                json={
                    "tunedModels": [
                        {
                            "name": "tunedModels/my-model-1",
                            "displayName": "My Model",
                            "state": "ACTIVE",
                            "baseModel": "models/gemini-1.5-flash",
                        }
                    ],
                    "nextPageToken": "tm-next",
                },
            )
        )

        result = await gemini.alist_tuned_models(filter="owner:me")

        assert len(result.tuned_models) == 1
        assert result.tuned_models[0].name == "tunedModels/my-model-1"
        assert result.tuned_models[0].state == "ACTIVE"
        assert result.tuned_models[0].base_model == "models/gemini-1.5-flash"
        assert result.next_page_token == "tm-next"
        assert "filter=owner%3Ame" in str(route.calls.last.request.url)


@pytest.mark.asyncio
async def test_get_tuned_model_happy_path(gemini: Gemini) -> None:
    """get_tuned_model: GET /tunedModels/{name} → TunedModel."""
    with respx.mock(base_url=_BASE_URL) as respx_mock:
        respx_mock.get("/tunedModels/my-model-1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "name": "tunedModels/my-model-1",
                    "state": "CREATING",
                    "baseModel": "models/gemini-1.5-flash",
                    "temperature": 0.7,
                    "topK": 40,
                },
            )
        )

        # Bare id normalised to tunedModels/{id}.
        result = await gemini.aget_tuned_model(name="my-model-1")

        assert result.name == "tunedModels/my-model-1"
        assert result.state == "CREATING"
        assert result.temperature == 0.7
        assert result.top_k == 40


@pytest.mark.asyncio
async def test_create_tuned_model_builds_tuning_task(gemini: Gemini) -> None:
    """create_tuned_model: POST /tunedModels?tunedModelId=... builds the
    nested tuningTask body and unwraps the Operation metadata.
    """
    with respx.mock(base_url=_BASE_URL) as respx_mock:
        route = respx_mock.post("/tunedModels").mock(
            return_value=httpx.Response(
                200,
                json={
                    "name": "operations/op-1",
                    "metadata": {
                        "tunedModel": {
                            "name": "tunedModels/my-new-model",
                            "state": "CREATING",
                            "baseModel": "models/gemini-1.5-flash",
                        }
                    },
                },
            )
        )

        result = await gemini.acreate_tuned_model(
            base_model="gemini-1.5-flash",
            training_data=[{"text_input": "in", "output": "out"}],
            display_name="My New Model",
            tuned_model_id="my-new-model",
            epoch_count=3,
        )

        assert result.name == "tunedModels/my-new-model"
        assert result.state == "CREATING"

        request = route.calls.last.request
        assert "tunedModelId=my-new-model" in str(request.url)
        body = request.read()
        assert b'"baseModel":"models/gemini-1.5-flash"' in body
        assert b'"tuningTask"' in body
        assert b'"textInput":"in"' in body
        assert b'"epochCount":3' in body


@pytest.mark.asyncio
async def test_delete_tuned_model_returns_true(gemini: Gemini) -> None:
    """delete_tuned_model: DELETE /tunedModels/{name} → True."""
    with respx.mock(base_url=_BASE_URL) as respx_mock:
        route = respx_mock.delete("/tunedModels/my-model-1").mock(
            return_value=httpx.Response(200, json={})
        )

        result = await gemini.adelete_tuned_model(name="tunedModels/my-model-1")

        assert result is True
        assert route.called


# ---------------------------------------------------------------------------
# 11. Error path — caching validation error surfaces as ValidationError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_cache_invalid_request_raises_validation_error(gemini: Gemini) -> None:
    """Gemini 400 on create_cache → typed :class:`ValidationError` carrying the
    connector name and upstream status.
    """
    with respx.mock(base_url=_BASE_URL) as respx_mock:
        respx_mock.post("/cachedContents").mock(
            return_value=httpx.Response(
                400,
                json={
                    "error": {
                        "code": 400,
                        "message": "Cached content is too small to cache.",
                        "status": "INVALID_ARGUMENT",
                    }
                },
            )
        )

        with pytest.raises(ValidationError) as exc_info:
            await gemini.acreate_cache(model="gemini-1.5-flash", contents=[])

        assert exc_info.value.connector == "gemini"
        assert exc_info.value.upstream_status == 400


# ---------------------------------------------------------------------------
# 12. Spec metadata
# ---------------------------------------------------------------------------


def test_spec_metadata() -> None:
    """get_spec exposes the expected name, category, and action flags.

    Generation/embedding/read actions are non-destructive; the delete actions
    (files, caches, tuned models) and create_tuned_model are flagged
    ``dangerous``; read actions are flagged ``idempotent``.
    """
    spec = Gemini.get_spec()
    assert spec.name == "gemini"
    assert spec.actions["generate_content"].dangerous is False
    assert spec.actions["list_models"].idempotent is True
    assert spec.actions["get_model"].idempotent is True
    assert spec.actions["count_tokens"].idempotent is True

    # Deletes (and the long-running tuning create) are destructive.
    assert spec.actions["delete_file"].dangerous is True
    assert spec.actions["delete_cache"].dangerous is True
    assert spec.actions["delete_tuned_model"].dangerous is True
    assert spec.actions["create_tuned_model"].dangerous is True

    # New read actions are idempotent.
    assert spec.actions["get_file"].idempotent is True
    assert spec.actions["list_files"].idempotent is True
    assert spec.actions["get_cache"].idempotent is True
    assert spec.actions["list_caches"].idempotent is True
    assert spec.actions["list_tuned_models"].idempotent is True
    assert spec.actions["get_tuned_model"].idempotent is True

    # The tunedModels surface is discontinued on the public Gemini API
    # (HTTP 501, verified live 2026-06-12) — all four actions are flagged
    # deprecated with a pointer to Vertex AI. Non-tuning actions are not.
    for name in (
        "list_tuned_models",
        "get_tuned_model",
        "create_tuned_model",
        "delete_tuned_model",
    ):
        assert spec.actions[name].deprecated is True, name
        assert "Vertex AI" in (spec.actions[name].deprecation_message or ""), name
    assert spec.actions["generate_content"].deprecated is False
    assert spec.actions["generate_content"].deprecation_message is None


# ---------------------------------------------------------------------------
# Tier-1 prep: tools / generation_config / safety / streaming / errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_content_passes_tools_safety_and_generation_config(gemini: Gemini) -> None:
    """tools, tool_config, safety_settings and generation_config all reach the body.

    Function calling is the headline agent capability; the explicit
    ``temperature`` convenience must merge into ``generationConfig`` alongside
    the caller's extra keys, and a returned ``functionCall`` part survives in
    the raw candidate list.
    """
    with respx.mock(base_url=_BASE_URL) as respx_mock:
        route = respx_mock.post("/models/gemini-2.0-flash:generateContent").mock(
            return_value=httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "functionCall": {
                                            "name": "get_weather",
                                            "args": {"city": "SF"},
                                        }
                                    }
                                ]
                            },
                            "finishReason": "STOP",
                        }
                    ]
                },
            )
        )

        tools = [
            {"functionDeclarations": [{"name": "get_weather", "parameters": {"type": "object"}}]}
        ]
        result = await gemini.agenerate_content(
            model="gemini-2.0-flash",
            contents="weather in SF?",
            temperature=0.2,
            tools=tools,
            tool_config={"functionCallingConfig": {"mode": "ANY"}},
            safety_settings=[{"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"}],
            generation_config={
                "responseMimeType": "application/json",
                "stopSequences": ["END"],
                "topP": 0.9,
            },
        )

        body = json.loads(route.calls.last.request.read())
        assert body["tools"] == tools
        assert body["toolConfig"] == {"functionCallingConfig": {"mode": "ANY"}}
        assert body["safetySettings"][0]["category"] == "HARM_CATEGORY_HATE_SPEECH"
        gen_config = body["generationConfig"]
        assert gen_config["responseMimeType"] == "application/json"
        assert gen_config["stopSequences"] == ["END"]
        assert gen_config["topP"] == 0.9
        assert gen_config["temperature"] == 0.2  # convenience merged in

        # functionCall part preserved for the caller to dispatch.
        part = result.candidates[0]["content"]["parts"][0]
        assert part["functionCall"]["name"] == "get_weather"


@pytest.mark.asyncio
async def test_generate_content_surfaces_safety_block(gemini: Gemini) -> None:
    """A prompt-level safety block surfaces as a typed ``block_reason``.

    The API returns ``promptFeedback.blockReason`` with empty candidates; the
    connector must expose it on a typed field rather than a silently-empty
    result.
    """
    with respx.mock(base_url=_BASE_URL) as respx_mock:
        respx_mock.post("/models/gemini-2.0-flash:generateContent").mock(
            return_value=httpx.Response(
                200,
                json={
                    "promptFeedback": {
                        "blockReason": "SAFETY",
                        "safetyRatings": [
                            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "probability": "HIGH"}
                        ],
                    },
                    "candidates": [],
                },
            )
        )

        result = await gemini.agenerate_content(model="gemini-2.0-flash", contents="...")
        assert result.block_reason == "SAFETY"
        assert result.text == ""
        assert result.finish_reason is None
        assert result.prompt_feedback["blockReason"] == "SAFETY"


@pytest.mark.asyncio
async def test_generate_content_surfaces_safety_citation_thoughts(gemini: Gemini) -> None:
    """Candidate safety/citation + thinking-model token usage are typed."""
    with respx.mock(base_url=_BASE_URL) as respx_mock:
        respx_mock.post("/models/gemini-2.0-flash:generateContent").mock(
            return_value=httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "content": {"parts": [{"text": "ok"}]},
                            "finishReason": "STOP",
                            "safetyRatings": [
                                {
                                    "category": "HARM_CATEGORY_HARASSMENT",
                                    "probability": "NEGLIGIBLE",
                                }
                            ],
                            "citationMetadata": {
                                "citationSources": [{"uri": "https://example.com"}]
                            },
                        }
                    ],
                    "usageMetadata": {
                        "promptTokenCount": 4,
                        "candidatesTokenCount": 1,
                        "totalTokenCount": 12,
                        "thoughtsTokenCount": 7,
                    },
                    "responseId": "resp-xyz",
                    "modelVersion": "gemini-2.0-flash-001",
                },
            )
        )

        result = await gemini.agenerate_content(model="gemini-2.0-flash", contents="hi")
        assert result.safety_ratings[0]["category"] == "HARM_CATEGORY_HARASSMENT"
        assert result.citation_metadata["citationSources"][0]["uri"] == "https://example.com"
        assert result.usage.thoughts_token_count == 7
        assert result.response_id == "resp-xyz"
        assert result.block_reason is None


@pytest.mark.asyncio
async def test_stream_generate_content_assembles_sse_chunks(gemini: Gemini) -> None:
    """streamGenerateContent SSE chunks are assembled into one GeminiStreamResult.

    Verifies ``?alt=sse`` is used, the key stays in the header, text deltas are
    concatenated in order, and finish_reason/usage come from the final chunk.
    """
    sse_body = (
        'data: {"candidates":[{"content":{"parts":[{"text":"Hel"}]}}]}\n\n'
        'data: {"candidates":[{"content":{"parts":[{"text":"lo world"}]},'
        '"finishReason":"STOP"}],"usageMetadata":{"promptTokenCount":3,'
        '"candidatesTokenCount":2,"totalTokenCount":5},'
        '"modelVersion":"gemini-2.0-flash-001"}\n\n'
    )
    with respx.mock(base_url=_BASE_URL) as respx_mock:
        route = respx_mock.post("/models/gemini-2.0-flash:streamGenerateContent").mock(
            return_value=httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=sse_body.encode(),
            )
        )

        result = await gemini.astream_generate_content(
            model="gemini-2.0-flash", contents="say hello"
        )
        assert result.text == "Hello world"
        assert result.chunks == ["Hel", "lo world"]
        assert result.chunk_count == 2
        assert result.finish_reason == "STOP"
        assert result.usage is not None and result.usage.total_token_count == 5
        assert result.model_version == "gemini-2.0-flash-001"

        req = route.calls.last.request
        assert "alt=sse" in str(req.url)
        assert req.headers["x-goog-api-key"] == "AIza-fake-test-key"
        assert "AIza-fake-test-key" not in str(req.url)


@pytest.mark.asyncio
async def test_stream_generate_content_surfaces_block_reason(gemini: Gemini) -> None:
    """A safety block during streaming surfaces as ``block_reason``."""
    sse_body = 'data: {"promptFeedback":{"blockReason":"SAFETY"},"candidates":[]}\n\n'
    with respx.mock(base_url=_BASE_URL) as respx_mock:
        respx_mock.post("/models/gemini-2.0-flash:streamGenerateContent").mock(
            return_value=httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=sse_body.encode(),
            )
        )

        result = await gemini.astream_generate_content(model="gemini-2.0-flash", contents="...")
        assert result.block_reason == "SAFETY"
        assert result.text == ""
        assert result.chunk_count == 1


@pytest.mark.asyncio
async def test_generate_content_server_error(gemini: Gemini) -> None:
    """A 503 from generateContent maps to a (retry-eligible) ServerError."""
    with respx.mock(base_url=_BASE_URL) as respx_mock:
        respx_mock.post("/models/gemini-2.0-flash:generateContent").mock(
            return_value=httpx.Response(
                503,
                json={"error": {"code": 503, "message": "overloaded", "status": "UNAVAILABLE"}},
            )
        )
        with pytest.raises(ServerError):
            await gemini.agenerate_content(model="gemini-2.0-flash", contents="hi")


@pytest.mark.asyncio
async def test_stream_generate_content_server_error(gemini: Gemini) -> None:
    """The streaming path maps a 5xx to ServerError (error body materialised)."""
    with respx.mock(base_url=_BASE_URL) as respx_mock:
        respx_mock.post("/models/gemini-2.0-flash:streamGenerateContent").mock(
            return_value=httpx.Response(
                500,
                json={"error": {"code": 500, "message": "boom", "status": "INTERNAL"}},
            )
        )
        with pytest.raises(ServerError):
            await gemini.astream_generate_content(model="gemini-2.0-flash", contents="hi")


@pytest.mark.asyncio
async def test_embed_content_validation_error(gemini: Gemini) -> None:
    """Failure-path coverage for embeddings: 400 → ValidationError."""
    with respx.mock(base_url=_BASE_URL) as respx_mock:
        respx_mock.post("/models/gemini-embedding-001:embedContent").mock(
            return_value=httpx.Response(
                400,
                json={"error": {"code": 400, "message": "bad", "status": "INVALID_ARGUMENT"}},
            )
        )
        with pytest.raises(ValidationError):
            await gemini.aembed_content(model="gemini-embedding-001", text="hi")


@pytest.mark.asyncio
async def test_list_files_server_error(gemini: Gemini) -> None:
    """Failure-path coverage for the Files API: 5xx → ServerError."""
    with respx.mock(base_url=_BASE_URL) as respx_mock:
        respx_mock.get("/files").mock(
            return_value=httpx.Response(
                500,
                json={"error": {"code": 500, "message": "x", "status": "INTERNAL"}},
            )
        )
        with pytest.raises(ServerError):
            await gemini.alist_files()


def test_stream_generate_content_in_spec() -> None:
    """The new streaming action is registered and non-destructive."""
    spec = Gemini.get_spec()
    assert "stream_generate_content" in spec.actions
    assert spec.actions["stream_generate_content"].dangerous is False


@pytest.mark.asyncio
async def test_stream_generate_content_tolerates_malformed_and_array_lines(
    gemini: Gemini,
) -> None:
    """The SSE reader skips junk and unwraps array payloads instead of crashing.

    Covers: comment lines, non-JSON garbage, an OpenAI-style ``[DONE]``
    sentinel, empty ``data:`` lines, CRLF endings, and a JSON-ARRAY payload
    (Gemini's non-SSE response shape, seen if a proxy strips ``?alt=sse``) —
    the array's dict elements are unwrapped into chunks.
    """
    sse_body = (
        ": comment\r\n\r\n"
        'data: {"candidates":[{"content":{"parts":[{"text":"A"}]}}]}\r\n\r\n'
        "data: NOT-JSON\r\n\r\n"
        "data: [DONE]\r\n\r\n"
        'data: [{"candidates":[{"content":{"parts":[{"text":"B"}]},'
        '"finishReason":"STOP"}]}]\r\n\r\n'
        "data:\r\n\r\n"
    )
    with respx.mock(base_url=_BASE_URL) as respx_mock:
        respx_mock.post("/models/gemini-2.0-flash:streamGenerateContent").mock(
            return_value=httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=sse_body.encode(),
            )
        )

        result = await gemini.astream_generate_content(model="gemini-2.0-flash", contents="x")
        assert result.text == "AB"
        assert result.finish_reason == "STOP"
        assert result.chunk_count == 2  # junk lines skipped, array unwrapped
