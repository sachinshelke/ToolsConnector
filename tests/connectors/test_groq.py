"""End-to-end tests for the Groq connector using respx.

Same pattern as test_openai.py. Groq's API is OpenAI-compatible, so the
shapes mirror OpenAI's; these tests exercise Groq's specifics:

  - **Per-request httpx.AsyncClient** — connector creates a fresh client
    inside ``_request()`` rather than reusing a long-lived one. respx
    still intercepts because it patches the transport globally.
  - **Bearer + JSON content-type** auth.
  - **Optional params** (``temperature`` / ``max_tokens`` / ``top_p``) must
    NOT appear in the request body when left as ``None``.
  - **Multipart audio** — ``transcribe_audio`` / ``translate_audio`` post
    ``multipart/form-data`` to the Whisper endpoints and parse ``{text}``.

The connector class is ``Groq`` and the async entry points are exposed as
``a{action}`` (e.g. ``achat_completion``) by ``BaseConnector``.
"""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
import respx

from toolsconnector.connectors.groq import Groq
from toolsconnector.errors import (
    InvalidCredentialsError,
    NotFoundError,
    RateLimitError,
)

GROQ_BASE = "https://api.groq.com/openai/v1"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def groq() -> Groq:
    """Groq connector with a fake API key.

    Key never hits api.groq.com because respx patches httpx.
    """
    connector = Groq(credentials="gsk-fake-test-key")
    await connector._setup()
    yield connector
    await connector._teardown()


# ---------------------------------------------------------------------------
# 1. Happy path — chat completion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_completion_happy_path(groq: Groq) -> None:
    """chat_completion: POST /chat/completions → ChatCompletion model.

    Verifies request shape (model + messages in body), auth header,
    and response parsing (choices + usage).
    """
    with respx.mock(base_url=GROQ_BASE, assert_all_called=True) as respx_mock:
        route = respx_mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "chatcmpl-abc123",
                    "object": "chat.completion",
                    "created": 1700000000,
                    "model": "llama-3.3-70b-versatile",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "Hi there!"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 7,
                        "completion_tokens": 4,
                        "total_tokens": 11,
                    },
                },
            )
        )

        result = await groq.achat_completion(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": "Say hi"}],
        )

        # Top-level fields parsed correctly
        assert result.id == "chatcmpl-abc123"
        assert result.model == "llama-3.3-70b-versatile"

        # Choices structure parsed
        assert len(result.choices) == 1
        assert result.choices[0].message.content == "Hi there!"
        assert result.choices[0].finish_reason == "stop"

        # Usage parsed
        assert result.usage is not None
        assert result.usage.total_tokens == 11

        # Auth header
        request = route.calls.last.request
        assert request.headers["authorization"] == "Bearer gsk-fake-test-key"
        assert request.headers["content-type"] == "application/json"

        # Body has model + messages
        body = request.read()
        assert b'"model":"llama-3.3-70b-versatile"' in body
        assert b'"messages"' in body


@pytest.mark.asyncio
async def test_chat_completion_optional_params(groq: Groq) -> None:
    """Optional params are omitted when None and included when provided.

    Vendor APIs treat ``null`` differently from a missing key, so the
    connector must drop None-valued optionals from the request body.
    """
    with respx.mock(base_url=GROQ_BASE) as respx_mock:
        route = respx_mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "x",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "llama-3.1-8b-instant",
                    "choices": [],
                    "usage": None,
                },
            )
        )

        # All optionals None → omitted.
        await groq.achat_completion(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": "hi"}],
        )
        body = route.calls.last.request.read()
        assert b'"model"' in body
        assert b'"messages"' in body
        assert b'"temperature"' not in body
        assert b'"max_tokens"' not in body
        assert b'"top_p"' not in body

        # Optionals provided → included.
        await groq.achat_completion(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.5,
            max_tokens=128,
            top_p=0.9,
        )
        body = route.calls.last.request.read()
        assert b'"temperature"' in body
        assert b'"max_tokens"' in body
        assert b'"top_p"' in body


# ---------------------------------------------------------------------------
# 2. Models
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_models(groq: Groq) -> None:
    """list_models: GET /models → list[GroqModel] from the ``data`` array."""
    with respx.mock(base_url=GROQ_BASE, assert_all_called=True) as respx_mock:
        respx_mock.get("/models").mock(
            return_value=httpx.Response(
                200,
                json={
                    "object": "list",
                    "data": [
                        {
                            "id": "llama-3.3-70b-versatile",
                            "object": "model",
                            "created": 1700000000,
                            "owned_by": "Meta",
                            "active": True,
                            "context_window": 131072,
                        },
                        {
                            "id": "whisper-large-v3",
                            "object": "model",
                            "created": 1700000001,
                            "owned_by": "OpenAI",
                        },
                    ],
                },
            )
        )

        models = await groq.alist_models()

        assert len(models) == 2
        assert models[0].id == "llama-3.3-70b-versatile"
        assert models[0].owned_by == "Meta"
        assert models[0].context_window == 131072
        assert models[0].active is True
        # Missing optionals default cleanly.
        assert models[1].active is None
        assert models[1].context_window is None


@pytest.mark.asyncio
async def test_get_model(groq: Groq) -> None:
    """get_model: GET /models/{model} → single GroqModel."""
    with respx.mock(base_url=GROQ_BASE, assert_all_called=True) as respx_mock:
        route = respx_mock.get("/models/llama-3.3-70b-versatile").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "llama-3.3-70b-versatile",
                    "object": "model",
                    "created": 1700000000,
                    "owned_by": "Meta",
                    "active": True,
                    "context_window": 131072,
                },
            )
        )

        model = await groq.aget_model(model="llama-3.3-70b-versatile")

        assert model.id == "llama-3.3-70b-versatile"
        assert model.owned_by == "Meta"
        assert model.context_window == 131072
        # Path interpolation is correct.
        assert route.calls.last.request.url.path.endswith("/models/llama-3.3-70b-versatile")


# ---------------------------------------------------------------------------
# 3. Audio — multipart transcription / translation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transcribe_audio_from_bytes(groq: Groq) -> None:
    """transcribe_audio: POST /audio/transcriptions as multipart → {text}.

    Passing raw bytes skips any download; the model + language land in the
    form, and the file part is attached.
    """
    with respx.mock(base_url=GROQ_BASE, assert_all_called=True) as respx_mock:
        route = respx_mock.post("/audio/transcriptions").mock(
            return_value=httpx.Response(
                200,
                json={"text": "hello world", "language": "en", "duration": 1.5},
            )
        )

        result = await groq.atranscribe_audio(
            model="whisper-large-v3",
            file_url_or_bytes=b"\x00\x01fake-audio-bytes",
            language="en",
            response_format="verbose_json",
        )

        assert result.text == "hello world"
        assert result.language == "en"
        assert result.duration == 1.5

        request = route.calls.last.request
        # Multipart form, Bearer auth, no JSON content-type override.
        assert request.headers["authorization"] == "Bearer gsk-fake-test-key"
        assert "multipart/form-data" in request.headers["content-type"]
        body = request.read()
        assert b"whisper-large-v3" in body
        assert b"fake-audio-bytes" in body
        assert b'name="language"' in body
        assert b'name="response_format"' in body


@pytest.mark.asyncio
async def test_transcribe_audio_from_url_downloads_first(groq: Groq) -> None:
    """An http(s) URL is downloaded, then forwarded as the multipart file."""
    audio_url = "https://example.com/clip.mp3"
    with respx.mock(assert_all_called=True) as respx_mock:
        download = respx_mock.get(audio_url).mock(
            return_value=httpx.Response(200, content=b"downloaded-audio")
        )
        transcribe = respx_mock.post(f"{GROQ_BASE}/audio/transcriptions").mock(
            return_value=httpx.Response(200, json={"text": "from url"})
        )

        result = await groq.atranscribe_audio(
            model="whisper-large-v3",
            file_url_or_bytes=audio_url,
        )

        assert result.text == "from url"
        assert download.called
        body = transcribe.calls.last.request.read()
        assert b"downloaded-audio" in body
        # Filename derived from the URL.
        assert b"clip.mp3" in body


@pytest.mark.asyncio
async def test_translate_audio(groq: Groq) -> None:
    """translate_audio: POST /audio/translations as multipart → {text}."""
    with respx.mock(base_url=GROQ_BASE, assert_all_called=True) as respx_mock:
        route = respx_mock.post("/audio/translations").mock(
            return_value=httpx.Response(200, json={"text": "translated text"})
        )

        result = await groq.atranslate_audio(
            model="whisper-large-v3",
            file_url_or_bytes=b"some-audio",
        )

        assert result.text == "translated text"
        body = route.calls.last.request.read()
        assert b"whisper-large-v3" in body
        assert b"some-audio" in body
        # translate has no language param.
        assert b'name="language"' not in body


# ---------------------------------------------------------------------------
# 3b. Audio — text-to-speech returns raw bytes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_speech_returns_audio_bytes(groq: Groq) -> None:
    """create_speech: POST /audio/speech (JSON) → raw audio bytes.

    Required params (model/input/voice) land in the JSON body, and the
    binary response content is passed straight back to the caller.
    """
    fake_audio = b"RIFF\x00\x00\x00\x00WAVEfake-pcm"
    with respx.mock(base_url=GROQ_BASE, assert_all_called=True) as respx_mock:
        route = respx_mock.post("/audio/speech").mock(
            return_value=httpx.Response(
                200,
                content=fake_audio,
                headers={"content-type": "audio/wav"},
            )
        )

        audio = await groq.acreate_speech(
            model="playai-tts",
            input="Hello from Groq",
            voice="Fritz-PlayAI",
            response_format="wav",
            sample_rate=24000,
            speed=1.25,
        )

        # Raw bytes flow straight through.
        assert audio == fake_audio
        assert isinstance(audio, bytes)

        request = route.calls.last.request
        assert request.headers["authorization"] == "Bearer gsk-fake-test-key"
        assert request.headers["content-type"] == "application/json"

        body = request.read()
        assert b'"model":"playai-tts"' in body
        assert b'"voice":"Fritz-PlayAI"' in body
        assert b'"input":"Hello from Groq"' in body
        assert b'"response_format":"wav"' in body
        assert b'"sample_rate":24000' in body
        assert b'"speed":1.25' in body


@pytest.mark.asyncio
async def test_create_speech_omits_optional_params(groq: Groq) -> None:
    """Optional speech params are omitted from the body when left as None."""
    with respx.mock(base_url=GROQ_BASE) as respx_mock:
        route = respx_mock.post("/audio/speech").mock(
            return_value=httpx.Response(200, content=b"audio")
        )

        await groq.acreate_speech(
            model="playai-tts",
            input="hi",
            voice="Arista-PlayAI",
        )

        body = route.calls.last.request.read()
        assert b'"model"' in body
        assert b'"voice"' in body
        assert b'"response_format"' not in body
        assert b'"sample_rate"' not in body
        assert b'"speed"' not in body


# ---------------------------------------------------------------------------
# 3c. Files — upload / list / get / content / delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_file_multipart(groq: Groq) -> None:
    """upload_file: POST /files as multipart → GroqFile.

    The raw bytes attach as the file part, the purpose lands in the form,
    and the parsed metadata is returned.
    """
    with respx.mock(base_url=GROQ_BASE, assert_all_called=True) as respx_mock:
        route = respx_mock.post("/files").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "file_01abc",
                    "object": "file",
                    "bytes": 42,
                    "created_at": 1700000000,
                    "filename": "batch.jsonl",
                    "purpose": "batch",
                },
            )
        )

        result = await groq.aupload_file(
            file_content=b'{"custom_id":"r1"}\n',
            purpose="batch",
            filename="batch.jsonl",
        )

        assert result.id == "file_01abc"
        assert result.bytes == 42
        assert result.purpose == "batch"
        assert result.filename == "batch.jsonl"

        request = route.calls.last.request
        assert request.headers["authorization"] == "Bearer gsk-fake-test-key"
        assert "multipart/form-data" in request.headers["content-type"]
        body = request.read()
        assert b"batch.jsonl" in body
        assert b'"custom_id":"r1"' in body
        assert b'name="purpose"' in body


@pytest.mark.asyncio
async def test_list_files(groq: Groq) -> None:
    """list_files: GET /files → list[GroqFile]; purpose filter is forwarded."""
    with respx.mock(base_url=GROQ_BASE, assert_all_called=True) as respx_mock:
        route = respx_mock.get("/files").mock(
            return_value=httpx.Response(
                200,
                json={
                    "object": "list",
                    "data": [
                        {
                            "id": "file_01abc",
                            "object": "file",
                            "bytes": 42,
                            "created_at": 1700000000,
                            "filename": "batch.jsonl",
                            "purpose": "batch",
                        }
                    ],
                },
            )
        )

        files = await groq.alist_files(purpose="batch")

        assert len(files) == 1
        assert files[0].id == "file_01abc"
        assert files[0].purpose == "batch"
        # Purpose filter forwarded as a query param.
        assert route.calls.last.request.url.params["purpose"] == "batch"


@pytest.mark.asyncio
async def test_get_file(groq: Groq) -> None:
    """get_file: GET /files/{file_id} → single GroqFile."""
    with respx.mock(base_url=GROQ_BASE, assert_all_called=True) as respx_mock:
        route = respx_mock.get("/files/file_01abc").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "file_01abc",
                    "object": "file",
                    "bytes": 42,
                    "created_at": 1700000000,
                    "filename": "batch.jsonl",
                    "purpose": "batch",
                },
            )
        )

        result = await groq.aget_file(file_id="file_01abc")

        assert result.id == "file_01abc"
        assert route.calls.last.request.url.path.endswith("/files/file_01abc")


@pytest.mark.asyncio
async def test_get_file_content_returns_bytes(groq: Groq) -> None:
    """get_file_content: GET /files/{file_id}/content → raw bytes (JSONL)."""
    jsonl = b'{"custom_id":"r1","response":{"status_code":200}}\n'
    with respx.mock(base_url=GROQ_BASE, assert_all_called=True) as respx_mock:
        route = respx_mock.get("/files/file_01abc/content").mock(
            return_value=httpx.Response(200, content=jsonl)
        )

        content = await groq.aget_file_content(file_id="file_01abc")

        assert content == jsonl
        assert isinstance(content, bytes)
        assert route.calls.last.request.url.path.endswith("/files/file_01abc/content")


@pytest.mark.asyncio
async def test_delete_file(groq: Groq) -> None:
    """delete_file: DELETE /files/{file_id} → bool from ``deleted`` field."""
    with respx.mock(base_url=GROQ_BASE, assert_all_called=True) as respx_mock:
        route = respx_mock.delete("/files/file_01abc").mock(
            return_value=httpx.Response(
                200,
                json={"id": "file_01abc", "object": "file", "deleted": True},
            )
        )

        deleted = await groq.adelete_file(file_id="file_01abc")

        assert deleted is True
        assert route.calls.last.request.method == "DELETE"


# ---------------------------------------------------------------------------
# 3d. Batches — create / list / get / cancel
# ---------------------------------------------------------------------------


_BATCH_OBJ = {
    "id": "batch_01xyz",
    "object": "batch",
    "endpoint": "/v1/chat/completions",
    "input_file_id": "file_01abc",
    "completion_window": "24h",
    "status": "validating",
    "output_file_id": None,
    "error_file_id": None,
    "created_at": 1700000000,
    "request_counts": {"total": 3, "completed": 0, "failed": 0},
    "metadata": {"job": "nightly"},
}


@pytest.mark.asyncio
async def test_create_batch(groq: Groq) -> None:
    """create_batch: POST /batches (JSON) → Batch with request counts.

    Required fields and defaulted ``completion_window`` land in the body;
    nested ``request_counts`` is parsed into the typed model.
    """
    with respx.mock(base_url=GROQ_BASE, assert_all_called=True) as respx_mock:
        route = respx_mock.post("/batches").mock(return_value=httpx.Response(200, json=_BATCH_OBJ))

        batch = await groq.acreate_batch(
            input_file_id="file_01abc",
            endpoint="/v1/chat/completions",
            metadata={"job": "nightly"},
        )

        assert batch.id == "batch_01xyz"
        assert batch.status == "validating"
        assert batch.input_file_id == "file_01abc"
        assert batch.request_counts is not None
        assert batch.request_counts.total == 3
        assert batch.metadata == {"job": "nightly"}

        body = route.calls.last.request.read()
        assert b'"input_file_id":"file_01abc"' in body
        assert b'"endpoint":"/v1/chat/completions"' in body
        # completion_window defaults to 24h when not supplied.
        assert b'"completion_window":"24h"' in body
        assert b'"metadata"' in body


@pytest.mark.asyncio
async def test_list_batches(groq: Groq) -> None:
    """list_batches: GET /batches → list[Batch]; limit forwarded as a param."""
    with respx.mock(base_url=GROQ_BASE, assert_all_called=True) as respx_mock:
        route = respx_mock.get("/batches").mock(
            return_value=httpx.Response(
                200,
                json={"object": "list", "data": [_BATCH_OBJ]},
            )
        )

        batches = await groq.alist_batches(limit=10)

        assert len(batches) == 1
        assert batches[0].id == "batch_01xyz"
        assert route.calls.last.request.url.params["limit"] == "10"


@pytest.mark.asyncio
async def test_get_batch(groq: Groq) -> None:
    """get_batch: GET /batches/{batch_id} → Batch with completed file IDs."""
    completed = {
        **_BATCH_OBJ,
        "status": "completed",
        "output_file_id": "file_out01",
        "completed_at": 1700000500,
        "request_counts": {"total": 3, "completed": 3, "failed": 0},
    }
    with respx.mock(base_url=GROQ_BASE, assert_all_called=True) as respx_mock:
        route = respx_mock.get("/batches/batch_01xyz").mock(
            return_value=httpx.Response(200, json=completed)
        )

        batch = await groq.aget_batch(batch_id="batch_01xyz")

        assert batch.status == "completed"
        assert batch.output_file_id == "file_out01"
        assert batch.completed_at == 1700000500
        assert batch.request_counts is not None
        assert batch.request_counts.completed == 3
        assert route.calls.last.request.url.path.endswith("/batches/batch_01xyz")


@pytest.mark.asyncio
async def test_cancel_batch(groq: Groq) -> None:
    """cancel_batch: POST /batches/{batch_id}/cancel → Batch (cancelling)."""
    cancelling = {**_BATCH_OBJ, "status": "cancelling", "cancelling_at": 1700000600}
    with respx.mock(base_url=GROQ_BASE, assert_all_called=True) as respx_mock:
        route = respx_mock.post("/batches/batch_01xyz/cancel").mock(
            return_value=httpx.Response(200, json=cancelling)
        )

        batch = await groq.acancel_batch(batch_id="batch_01xyz")

        assert batch.status == "cancelling"
        assert batch.cancelling_at == 1700000600
        request = route.calls.last.request
        assert request.method == "POST"
        assert request.url.path.endswith("/batches/batch_01xyz/cancel")


# ---------------------------------------------------------------------------
# 4. Error mapping — HTTP errors surface as typed errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_api_key_raises_invalid_credentials_error(groq: Groq) -> None:
    """Groq 401 → typed :class:`InvalidCredentialsError` via raise_typed_for_status."""
    with respx.mock(base_url=GROQ_BASE) as respx_mock:
        respx_mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                401,
                json={
                    "error": {
                        "message": "Invalid API Key",
                        "type": "invalid_request_error",
                        "code": "invalid_api_key",
                    }
                },
            )
        )

        with pytest.raises(InvalidCredentialsError) as exc_info:
            await groq.achat_completion(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": "hi"}],
            )

        assert exc_info.value.connector == "groq"
        assert exc_info.value.upstream_status == 401


@pytest.mark.asyncio
async def test_rate_limit_raises_rate_limit_error(groq: Groq) -> None:
    """Groq 429 → typed :class:`RateLimitError` with Retry-After parsed."""
    with respx.mock(base_url=GROQ_BASE) as respx_mock:
        respx_mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                429,
                headers={"Retry-After": "20"},
                json={"error": {"message": "Rate limit reached"}},
            )
        )

        with pytest.raises(RateLimitError) as exc_info:
            await groq.achat_completion(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": "hi"}],
            )

        assert exc_info.value.connector == "groq"
        assert exc_info.value.upstream_status == 429
        assert exc_info.value.retry_after_seconds == 20.0


@pytest.mark.asyncio
async def test_get_batch_not_found_raises_not_found_error(groq: Groq) -> None:
    """Groq 404 on an unknown batch → typed :class:`NotFoundError`.

    Covers the error path through a GET endpoint added in this expansion.
    """
    with respx.mock(base_url=GROQ_BASE) as respx_mock:
        respx_mock.get("/batches/batch_missing").mock(
            return_value=httpx.Response(
                404,
                json={
                    "error": {
                        "message": "No such batch: batch_missing",
                        "type": "invalid_request_error",
                        "code": "not_found",
                    }
                },
            )
        )

        with pytest.raises(NotFoundError) as exc_info:
            await groq.aget_batch(batch_id="batch_missing")

        assert exc_info.value.connector == "groq"
        assert exc_info.value.upstream_status == 404


# ---------------------------------------------------------------------------
# 5. Spec metadata
# ---------------------------------------------------------------------------


def test_spec_metadata() -> None:
    """Spec exposes the expected name, category, and action flags.

    Read-only model lookups are idempotent; chat/audio generation is not
    dangerous (it spends money but doesn't destroy state).
    """
    spec = Groq.get_spec()

    assert spec.name == "groq"
    assert spec.display_name == "Groq"
    assert spec.category.value == "ai_ml"
    assert spec.protocol.value == "rest"
    assert spec.verification_status == "pattern"
    assert spec.base_url == GROQ_BASE

    # Expected action surface.
    assert set(spec.actions) == {
        "chat_completion",
        "list_models",
        "get_model",
        "transcribe_audio",
        "translate_audio",
        "create_speech",
        "upload_file",
        "list_files",
        "get_file",
        "get_file_content",
        "delete_file",
        "create_batch",
        "list_batches",
        "get_batch",
        "cancel_batch",
    }

    assert spec.actions["list_models"].idempotent is True
    assert spec.actions["get_model"].idempotent is True
    assert spec.actions["chat_completion"].dangerous is False
    assert spec.actions["transcribe_audio"].dangerous is False

    # Read-only lookups are idempotent.
    assert spec.actions["list_files"].idempotent is True
    assert spec.actions["get_file"].idempotent is True
    assert spec.actions["get_file_content"].idempotent is True
    assert spec.actions["list_batches"].idempotent is True
    assert spec.actions["get_batch"].idempotent is True

    # Destructive / state-changing ops are flagged dangerous.
    assert spec.actions["delete_file"].dangerous is True
    assert spec.actions["cancel_batch"].dangerous is True

    # Generation / creation ops spend money but do not destroy state.
    assert spec.actions["create_speech"].dangerous is False
    assert spec.actions["upload_file"].dangerous is False
    assert spec.actions["create_batch"].dangerous is False
