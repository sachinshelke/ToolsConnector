"""End-to-end tests for the Mistral connector using respx.

Same pattern as test_openai.py / test_slack.py. Exercises Mistral's
specifics:

  - **Per-request httpx.AsyncClient** — connector creates a fresh
    client inside ``_request()`` rather than reusing a long-lived one.
    respx still intercepts because it patches the transport globally.
  - **OpenAI-compatible shapes** — chat/FIM/agents return ``choices`` +
    nested ``usage``; embeddings return ``data[*].embedding``; moderation
    returns ``results[0].categories`` / ``category_scores``.
  - **Mistral-native platform shapes** — files use ``size_bytes`` (not
    ``bytes``); fine-tuning jobs use ``training_files``/``validation_files``
    lists; batch jobs carry per-request counts; OCR returns ``pages[*]``.
  - **Bearer + JSON content-type** auth (no API-key-as-query-param).
  - **Optional params omitted when None** — ``temperature`` / ``top_p`` /
    ``max_tokens`` / ``suffix`` / pagination params must NOT appear in the
    body/query when None.
  - **Correct HTTP verbs/paths** — PATCH for model update, DELETE vs POST
    for (un)archive, ``/files/{id}/content`` download as raw bytes.
"""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
import respx

from toolsconnector.connectors.mistral import Mistral
from toolsconnector.errors import (
    InvalidCredentialsError,
    NotFoundError,
    RateLimitError,
)

BASE_URL = "https://api.mistral.ai/v1"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def mistral() -> Mistral:
    """Mistral connector with a fake API key.

    Key never hits api.mistral.ai because respx patches httpx.
    """
    connector = Mistral(credentials="fake-mistral-key")
    await connector._setup()
    yield connector
    await connector._teardown()


# ---------------------------------------------------------------------------
# 1. Happy path — chat completion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_completion_happy_path(mistral: Mistral) -> None:
    """chat_completion: POST /chat/completions → ChatCompletion model.

    Verifies request shape (model + messages in body), auth header,
    and response parsing (choices + usage).
    """
    with respx.mock(base_url=BASE_URL, assert_all_called=True) as respx_mock:
        route = respx_mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "cmpl-abc123",
                    "object": "chat.completion",
                    "created": 1700000000,
                    "model": "mistral-large-latest",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "Bonjour!"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 7,
                        "completion_tokens": 3,
                        "total_tokens": 10,
                    },
                },
            )
        )

        result = await mistral.achat_completion(
            model="mistral-large-latest",
            messages=[{"role": "user", "content": "Say hi"}],
        )

        # Top-level fields parsed correctly
        assert result.id == "cmpl-abc123"
        assert result.model == "mistral-large-latest"

        # Choices structure parsed
        assert len(result.choices) == 1
        assert result.choices[0].message.content == "Bonjour!"
        assert result.choices[0].finish_reason == "stop"

        # Usage parsed
        assert result.usage is not None
        assert result.usage.total_tokens == 10

        # Auth header
        request = route.calls.last.request
        assert request.headers["authorization"] == "Bearer fake-mistral-key"
        assert request.headers["content-type"] == "application/json"

        # Body has model + messages
        body = request.read()
        assert b'"model":"mistral-large-latest"' in body
        assert b'"messages"' in body


@pytest.mark.asyncio
async def test_chat_completion_optional_params(mistral: Mistral) -> None:
    """Optional params: omitted when None, included when provided.

    ``temperature`` / ``top_p`` / ``max_tokens`` must NOT appear in the
    body when None, but must appear (with correct values) when passed.
    """
    with respx.mock(base_url=BASE_URL) as respx_mock:
        route = respx_mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "x",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "mistral-small-latest",
                    "choices": [],
                    "usage": None,
                },
            )
        )

        # 1) Defaults — nothing optional in the body
        await mistral.achat_completion(
            model="mistral-small-latest",
            messages=[{"role": "user", "content": "hi"}],
        )
        body = route.calls.last.request.read()
        assert b'"model"' in body
        assert b'"messages"' in body
        assert b'"temperature"' not in body
        assert b'"top_p"' not in body
        assert b'"max_tokens"' not in body

        # 2) Explicit values land in the body
        await mistral.achat_completion(
            model="mistral-small-latest",
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.2,
            max_tokens=128,
            top_p=0.9,
        )
        body = route.calls.last.request.read()
        assert b'"temperature":0.2' in body
        assert b'"max_tokens":128' in body
        assert b'"top_p":0.9' in body


# ---------------------------------------------------------------------------
# 2. Embeddings — list input + data parsing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embeddings_list_input(mistral: Mistral) -> None:
    """embeddings: POST /embeddings with a list input → Embedding model.

    Verifies the input list is sent in the body and that each
    ``data[*].embedding`` vector is surfaced.
    """
    with respx.mock(base_url=BASE_URL) as respx_mock:
        route = respx_mock.post("/embeddings").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "emb-1",
                    "object": "list",
                    "model": "mistral-embed",
                    "data": [
                        {"object": "embedding", "index": 0, "embedding": [0.1, 0.2]},
                        {"object": "embedding", "index": 1, "embedding": [0.3, 0.4]},
                    ],
                    "usage": {"prompt_tokens": 5, "total_tokens": 5},
                },
            )
        )

        result = await mistral.aembeddings(
            model="mistral-embed",
            input=["hello", "world"],
        )

        assert result.model == "mistral-embed"
        assert len(result.data) == 2
        assert result.data[0].embedding == [0.1, 0.2]
        assert result.data[1].index == 1
        assert result.usage is not None
        assert result.usage.total_tokens == 5

        body = route.calls.last.request.read()
        assert b'"model":"mistral-embed"' in body
        assert b'"input"' in body
        assert b'"hello"' in body


# ---------------------------------------------------------------------------
# 3. List models
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_models(mistral: Mistral) -> None:
    """list_models: GET /models → list[MistralModel]."""
    with respx.mock(base_url=BASE_URL) as respx_mock:
        respx_mock.get("/models").mock(
            return_value=httpx.Response(
                200,
                json={
                    "object": "list",
                    "data": [
                        {
                            "id": "mistral-large-latest",
                            "object": "model",
                            "created": 1700000000,
                            "owned_by": "mistralai",
                        },
                        {
                            "id": "codestral-latest",
                            "object": "model",
                            "created": 1700000001,
                            "owned_by": "mistralai",
                        },
                    ],
                },
            )
        )

        models = await mistral.alist_models()

        assert len(models) == 2
        assert models[0].id == "mistral-large-latest"
        assert models[1].id == "codestral-latest"
        assert models[0].owned_by == "mistralai"


# ---------------------------------------------------------------------------
# 4. FIM completion — suffix omitted when None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fim_completion(mistral: Mistral) -> None:
    """fim_completion: POST /fim/completions → FIMCompletion model.

    Verifies prompt is sent, suffix appears only when provided, and the
    response (OpenAI-compatible choices) is parsed.
    """
    response_json = {
        "id": "fim-1",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "codestral-latest",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "    return a + b"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 6, "total_tokens": 18},
    }

    with respx.mock(base_url=BASE_URL) as respx_mock:
        route = respx_mock.post("/fim/completions").mock(
            return_value=httpx.Response(200, json=response_json)
        )

        # Without suffix — must not appear in body
        result = await mistral.afim_completion(
            model="codestral-latest",
            prompt="def add(a, b):\n",
        )
        body = route.calls.last.request.read()
        assert b'"prompt"' in body
        assert b'"suffix"' not in body
        assert result.choices[0].message.content == "    return a + b"

        # With suffix + max_tokens — both appear in body
        await mistral.afim_completion(
            model="codestral-latest",
            prompt="def add(a, b):\n",
            suffix="\n\nadd(1, 2)",
            max_tokens=64,
        )
        body = route.calls.last.request.read()
        assert b'"suffix"' in body
        assert b'"max_tokens":64' in body


# ---------------------------------------------------------------------------
# 5. Moderations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_moderations(mistral: Mistral) -> None:
    """moderations: POST /moderations → ModerationResult.

    Verifies categories + category_scores are pulled from results[0].
    """
    with respx.mock(base_url=BASE_URL) as respx_mock:
        route = respx_mock.post("/moderations").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "mod-1",
                    "model": "mistral-moderation-latest",
                    "results": [
                        {
                            "categories": {"hate": False, "violence": True},
                            "category_scores": {"hate": 0.01, "violence": 0.92},
                        }
                    ],
                },
            )
        )

        result = await mistral.amoderations(
            model="mistral-moderation-latest",
            input="some text",
        )

        assert result.id == "mod-1"
        assert result.model == "mistral-moderation-latest"
        assert result.categories["violence"] is True
        assert result.category_scores["violence"] == 0.92

        body = route.calls.last.request.read()
        assert b'"model":"mistral-moderation-latest"' in body
        assert b'"input":"some text"' in body


# ---------------------------------------------------------------------------
# 6. Error mapping — HTTP errors surface as typed exceptions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_api_key_raises_invalid_credentials_error(mistral: Mistral) -> None:
    """Mistral 401 → typed :class:`InvalidCredentialsError`.

    Mistral API keys are static, user-rotatable secrets (they don't
    expire), so a 401 stays as InvalidCredentialsError rather than
    promoting to TokenExpiredError.
    """
    with respx.mock(base_url=BASE_URL) as respx_mock:
        respx_mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                401,
                json={"message": "Unauthorized", "request_id": "abc"},
            )
        )

        with pytest.raises(InvalidCredentialsError) as exc_info:
            await mistral.achat_completion(
                model="mistral-large-latest",
                messages=[{"role": "user", "content": "hi"}],
            )

        assert exc_info.value.connector == "mistral"
        assert exc_info.value.upstream_status == 401


@pytest.mark.asyncio
async def test_rate_limit_raises_rate_limit_error(mistral: Mistral) -> None:
    """Mistral 429 → typed :class:`RateLimitError` with ``retry_after_seconds``
    parsed from the ``Retry-After`` header.
    """
    with respx.mock(base_url=BASE_URL) as respx_mock:
        respx_mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                429,
                headers={"Retry-After": "15"},
                json={"message": "Requests rate limit exceeded"},
            )
        )

        with pytest.raises(RateLimitError) as exc_info:
            await mistral.achat_completion(
                model="mistral-large-latest",
                messages=[{"role": "user", "content": "hi"}],
            )

        assert exc_info.value.connector == "mistral"
        assert exc_info.value.upstream_status == 429
        assert exc_info.value.retry_after_seconds == 15.0


# ---------------------------------------------------------------------------
# 7. Spec metadata
# ---------------------------------------------------------------------------


def test_spec_metadata() -> None:
    """get_spec exposes the expected name, category, and full action set.

    The connector now spans inference, content safety, OCR, and the
    platform-management surface (files, fine-tuning jobs, batch jobs,
    models). Deletes/cancels are flagged ``dangerous``; reads/lists are
    ``idempotent``.
    """
    spec = Mistral.get_spec()

    assert spec.name == "mistral"
    assert spec.display_name == "Mistral"
    assert spec.verification_status == "pattern"

    expected = {
        # Original inference surface (preserved).
        "chat_completion",
        "embeddings",
        "list_models",
        "fim_completion",
        "moderations",
        # Inference / safety additions.
        "agents_completion",
        "chat_moderations",
        "classifications",
        "ocr_process",
        # Model management.
        "get_model",
        "delete_model",
        "update_finetuned_model",
        "archive_model",
        "unarchive_model",
        # Files.
        "upload_file",
        "list_files",
        "get_file",
        "delete_file",
        "get_file_content",
        "get_file_signed_url",
        # Fine-tuning jobs.
        "create_finetuning_job",
        "list_finetuning_jobs",
        "get_finetuning_job",
        "start_finetuning_job",
        "cancel_finetuning_job",
        # Batch jobs.
        "create_batch_job",
        "list_batch_jobs",
        "get_batch_job",
        "cancel_batch_job",
        "delete_batch_job",
    }
    assert expected.issubset(set(spec.actions))

    # Destructive / state-changing-by-removal actions are flagged dangerous.
    dangerous = {name for name, a in spec.actions.items() if a.dangerous}
    assert {
        "delete_model",
        "delete_file",
        "delete_batch_job",
        "cancel_finetuning_job",
        "cancel_batch_job",
    } == dangerous

    # Read-only listings/gets are idempotent.
    for name in (
        "list_models",
        "get_model",
        "get_file",
        "list_files",
        "get_finetuning_job",
        "get_batch_job",
    ):
        assert spec.actions[name].idempotent is True

    # Generative actions stay non-dangerous (they spend money, not state).
    for name in ("chat_completion", "agents_completion", "ocr_process"):
        assert spec.actions[name].dangerous is False


# ---------------------------------------------------------------------------
# 8. Agents completion — agent_id required, optional params omitted when None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agents_completion(mistral: Mistral) -> None:
    """agents_completion: POST /agents/completions → AgentsCompletion.

    Verifies ``agent_id`` + ``messages`` are sent, optional params are
    omitted when None, and OpenAI-compatible choices/usage are parsed.
    """
    response_json = {
        "id": "cmpl-agent-1",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "mistral-large-latest",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Claude Monet."},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 11, "completion_tokens": 4, "total_tokens": 15},
    }

    with respx.mock(base_url=BASE_URL) as respx_mock:
        route = respx_mock.post("/agents/completions").mock(
            return_value=httpx.Response(200, json=response_json)
        )

        # Defaults: only agent_id + messages in the body.
        result = await mistral.aagents_completion(
            agent_id="ag-123",
            messages=[{"role": "user", "content": "Best French painter?"}],
        )
        body = route.calls.last.request.read()
        assert b'"agent_id":"ag-123"' in body
        assert b'"messages"' in body
        assert b'"max_tokens"' not in body
        assert b'"tools"' not in body
        assert b'"response_format"' not in body

        assert result.id == "cmpl-agent-1"
        assert result.choices[0].message.content == "Claude Monet."
        assert result.usage is not None
        assert result.usage.total_tokens == 15

        # Explicit optional params land in the body.
        await mistral.aagents_completion(
            agent_id="ag-123",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=32,
            response_format={"type": "json_object"},
        )
        body = route.calls.last.request.read()
        assert b'"max_tokens":32' in body
        assert b'"response_format"' in body


# ---------------------------------------------------------------------------
# 9. Chat moderations + classifications
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_moderations(mistral: Mistral) -> None:
    """chat_moderations: POST /chat/moderations → ModerationResult.

    Sends ``inputs`` (conversation list) and pulls categories/scores from
    ``results[0]``.
    """
    with respx.mock(base_url=BASE_URL) as respx_mock:
        route = respx_mock.post("/chat/moderations").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "mod-chat-1",
                    "model": "mistral-moderation-latest",
                    "results": [
                        {
                            "categories": {"hate": False, "violence": True},
                            "category_scores": {"hate": 0.02, "violence": 0.88},
                        }
                    ],
                },
            )
        )

        result = await mistral.achat_moderations(
            model="mistral-moderation-latest",
            inputs=[{"role": "user", "content": "some text"}],
        )

        assert result.id == "mod-chat-1"
        assert result.categories["violence"] is True
        assert result.category_scores["violence"] == 0.88

        body = route.calls.last.request.read()
        assert b'"inputs"' in body
        assert b'"input":' not in body  # chat variant uses inputs, not input


@pytest.mark.asyncio
async def test_classifications(mistral: Mistral) -> None:
    """classifications: POST /classifications → ClassificationResult.

    Preserves the per-input ``results`` maps verbatim.
    """
    with respx.mock(base_url=BASE_URL) as respx_mock:
        route = respx_mock.post("/classifications").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "cls-1",
                    "model": "mistral-moderation-latest",
                    "results": [{"sentiment": {"scores": {"positive": 0.9, "negative": 0.1}}}],
                },
            )
        )

        result = await mistral.aclassifications(
            model="mistral-moderation-latest",
            input="I love this!",
        )

        assert result.id == "cls-1"
        assert len(result.results) == 1
        assert result.results[0]["sentiment"]["scores"]["positive"] == 0.9

        body = route.calls.last.request.read()
        assert b'"model":"mistral-moderation-latest"' in body
        assert b'"input":"I love this!"' in body


# ---------------------------------------------------------------------------
# 10. OCR
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ocr_process(mistral: Mistral) -> None:
    """ocr_process: POST /ocr → OCRResult with parsed pages.

    Sends ``model`` + ``document``, omits optional params when None, and
    surfaces ``pages[*].markdown``.
    """
    with respx.mock(base_url=BASE_URL) as respx_mock:
        route = respx_mock.post("/ocr").mock(
            return_value=httpx.Response(
                200,
                json={
                    "model": "mistral-ocr-latest",
                    "pages": [
                        {
                            "index": 0,
                            "markdown": "# Title\n\nBody text.",
                            "images": [],
                            "dimensions": {"width": 800, "height": 1000, "dpi": 200},
                        }
                    ],
                    "usage_info": {"pages_processed": 1, "doc_size_bytes": 1234},
                },
            )
        )

        result = await mistral.aocr_process(
            model="mistral-ocr-latest",
            document={"type": "document_url", "document_url": "https://x/doc.pdf"},
        )

        assert result.model == "mistral-ocr-latest"
        assert len(result.pages) == 1
        assert result.pages[0].markdown.startswith("# Title")
        assert result.pages[0].dimensions == {"width": 800, "height": 1000, "dpi": 200}
        assert result.usage_info["pages_processed"] == 1

        body = route.calls.last.request.read()
        assert b'"model":"mistral-ocr-latest"' in body
        assert b'"document"' in body
        assert b'"pages"' not in body  # optional page selector omitted
        assert b'"include_image_base64"' not in body


# ---------------------------------------------------------------------------
# 11. Model management — get / delete / update (PATCH) / archive / unarchive
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_model(mistral: Mistral) -> None:
    """get_model: GET /models/{id} → MistralModel with rich metadata."""
    with respx.mock(base_url=BASE_URL) as respx_mock:
        respx_mock.get("/models/mistral-large-latest").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "mistral-large-latest",
                    "object": "model",
                    "created": 1700000000,
                    "owned_by": "mistralai",
                    "max_context_length": 131072,
                    "capabilities": {"completion_chat": True},
                    "type": "base",
                },
            )
        )

        model = await mistral.aget_model(model_id="mistral-large-latest")
        assert model.id == "mistral-large-latest"
        assert model.max_context_length == 131072
        assert model.capabilities["completion_chat"] is True
        assert model.type == "base"


@pytest.mark.asyncio
async def test_delete_model(mistral: Mistral) -> None:
    """delete_model: DELETE /models/{id} → ModelDeleted."""
    with respx.mock(base_url=BASE_URL) as respx_mock:
        route = respx_mock.delete("/models/ft:mistral-small:abc").mock(
            return_value=httpx.Response(
                200,
                json={"id": "ft:mistral-small:abc", "object": "model", "deleted": True},
            )
        )

        result = await mistral.adelete_model(model_id="ft:mistral-small:abc")
        assert result.deleted is True
        assert result.id == "ft:mistral-small:abc"
        assert route.calls.last.request.method == "DELETE"


@pytest.mark.asyncio
async def test_update_finetuned_model_uses_patch(mistral: Mistral) -> None:
    """update_finetuned_model: PATCH /fine_tuning/models/{id} → MistralModel.

    Verifies the correct verb (PATCH) and that only provided fields are
    sent in the body.
    """
    with respx.mock(base_url=BASE_URL) as respx_mock:
        route = respx_mock.patch("/fine_tuning/models/ft:m:1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "ft:m:1",
                    "object": "model",
                    "name": "renamed",
                    "description": "new desc",
                    "capabilities": {},
                },
            )
        )

        result = await mistral.aupdate_finetuned_model(
            model_id="ft:m:1",
            name="renamed",
        )
        assert result.name == "renamed"
        assert route.calls.last.request.method == "PATCH"

        body = route.calls.last.request.read()
        assert b'"name":"renamed"' in body
        assert b'"description"' not in body  # omitted when None


@pytest.mark.asyncio
async def test_archive_and_unarchive_model(mistral: Mistral) -> None:
    """archive (POST) vs unarchive (DELETE) hit the same path, different verbs."""
    with respx.mock(base_url=BASE_URL) as respx_mock:
        archive_route = respx_mock.post("/fine_tuning/models/ft:m:1/archive").mock(
            return_value=httpx.Response(
                200,
                json={"id": "ft:m:1", "object": "model", "archived": True},
            )
        )
        unarchive_route = respx_mock.delete("/fine_tuning/models/ft:m:1/archive").mock(
            return_value=httpx.Response(
                200,
                json={"id": "ft:m:1", "object": "model", "archived": False},
            )
        )

        archived = await mistral.aarchive_model(model_id="ft:m:1")
        assert archived.archived is True
        assert archive_route.calls.last.request.method == "POST"

        unarchived = await mistral.aunarchive_model(model_id="ft:m:1")
        assert unarchived.archived is False
        assert unarchive_route.calls.last.request.method == "DELETE"


# ---------------------------------------------------------------------------
# 12. Files — upload (multipart) / list (pagination) / get / delete / content
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_file_multipart(mistral: Mistral) -> None:
    """upload_file: POST /files as multipart → MistralFile.

    Verifies the request is multipart (not JSON), carries the purpose and
    file, and that ``size_bytes`` (Mistral's field) is surfaced.
    """
    with respx.mock(base_url=BASE_URL) as respx_mock:
        route = respx_mock.post("/files").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "file-1",
                    "object": "file",
                    "size_bytes": 13000,
                    "created_at": 1716963433,
                    "filename": "train.jsonl",
                    "purpose": "fine-tune",
                    "sample_type": "instruct",
                    "source": "upload",
                },
            )
        )

        result = await mistral.aupload_file(
            file_content=b'{"x": 1}\n',
            purpose="fine-tune",
            filename="train.jsonl",
        )

        assert result.id == "file-1"
        assert result.size_bytes == 13000
        assert result.purpose == "fine-tune"
        assert result.sample_type == "instruct"

        request = route.calls.last.request
        assert request.headers["content-type"].startswith("multipart/form-data")
        body = request.read()
        assert b"fine-tune" in body
        assert b"train.jsonl" in body


@pytest.mark.asyncio
async def test_list_files_pagination_params(mistral: Mistral) -> None:
    """list_files: GET /files → list[MistralFile]; params omitted when None."""
    payload = {
        "data": [
            {
                "id": "file-1",
                "object": "file",
                "size_bytes": 100,
                "created_at": 1,
                "filename": "a.jsonl",
                "purpose": "batch",
            }
        ],
    }
    with respx.mock(base_url=BASE_URL) as respx_mock:
        route = respx_mock.get("/files").mock(return_value=httpx.Response(200, json=payload))

        # No params → clean query string.
        files = await mistral.alist_files()
        assert len(files) == 1
        assert files[0].filename == "a.jsonl"
        assert "page" not in route.calls.last.request.url.params
        assert "purpose" not in route.calls.last.request.url.params

        # Explicit params land in the query string.
        await mistral.alist_files(page=1, page_size=50, purpose="batch")
        params = route.calls.last.request.url.params
        assert params["page"] == "1"
        assert params["page_size"] == "50"
        assert params["purpose"] == "batch"


@pytest.mark.asyncio
async def test_get_and_delete_file(mistral: Mistral) -> None:
    """get_file (GET) and delete_file (DELETE) round-trip."""
    with respx.mock(base_url=BASE_URL) as respx_mock:
        respx_mock.get("/files/file-9").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "file-9",
                    "object": "file",
                    "size_bytes": 42,
                    "created_at": 5,
                    "filename": "f.jsonl",
                    "purpose": "ocr",
                },
            )
        )
        del_route = respx_mock.delete("/files/file-9").mock(
            return_value=httpx.Response(
                200,
                json={"id": "file-9", "object": "file", "deleted": True},
            )
        )

        got = await mistral.aget_file(file_id="file-9")
        assert got.id == "file-9"
        assert got.purpose == "ocr"

        deleted = await mistral.adelete_file(file_id="file-9")
        assert deleted.deleted is True
        assert del_route.calls.last.request.method == "DELETE"


@pytest.mark.asyncio
async def test_get_file_content_returns_bytes(mistral: Mistral) -> None:
    """get_file_content: GET /files/{id}/content → raw bytes."""
    with respx.mock(base_url=BASE_URL) as respx_mock:
        respx_mock.get("/files/file-7/content").mock(
            return_value=httpx.Response(200, content=b'{"line": 1}\n{"line": 2}\n')
        )

        content = await mistral.aget_file_content(file_id="file-7")
        assert isinstance(content, bytes)
        assert content == b'{"line": 1}\n{"line": 2}\n'


@pytest.mark.asyncio
async def test_get_file_signed_url(mistral: Mistral) -> None:
    """get_file_signed_url: GET /files/{id}/url → FileSignedURL; expiry passed."""
    with respx.mock(base_url=BASE_URL) as respx_mock:
        route = respx_mock.get("/files/file-3/url").mock(
            return_value=httpx.Response(200, json={"url": "https://signed/file-3"})
        )

        result = await mistral.aget_file_signed_url(file_id="file-3", expiry=48)
        assert result.url == "https://signed/file-3"
        assert route.calls.last.request.url.params["expiry"] == "48"


# ---------------------------------------------------------------------------
# 13. Fine-tuning jobs — create / list / get / start / cancel
# ---------------------------------------------------------------------------


def _ft_job_json(status: str = "QUEUED") -> dict:
    """Build a representative fine-tuning job payload."""
    return {
        "id": "ftjob-1",
        "object": "job",
        "model": "open-mistral-7b",
        "status": status,
        "job_type": "completion",
        "created_at": 1700000000,
        "modified_at": 1700000001,
        "training_files": ["file-train-1"],
        "validation_files": ["file-val-1"],
        "fine_tuned_model": None,
        "suffix": "my-model",
        "hyperparameters": {"learning_rate": 0.0001},
    }


@pytest.mark.asyncio
async def test_create_finetuning_job(mistral: Mistral) -> None:
    """create_finetuning_job: POST /fine_tuning/jobs → FineTuningJob.

    Verifies required ``model`` + ``hyperparameters`` plus optional
    ``training_files`` / ``suffix`` are sent and lists are parsed.
    """
    with respx.mock(base_url=BASE_URL) as respx_mock:
        route = respx_mock.post("/fine_tuning/jobs").mock(
            return_value=httpx.Response(200, json=_ft_job_json())
        )

        result = await mistral.acreate_finetuning_job(
            model="open-mistral-7b",
            hyperparameters={"learning_rate": 0.0001},
            training_files=[{"file_id": "file-train-1", "weight": 1.0}],
            suffix="my-model",
        )

        assert result.id == "ftjob-1"
        assert result.status == "QUEUED"
        assert result.training_files == ["file-train-1"]
        assert result.validation_files == ["file-val-1"]
        assert result.hyperparameters["learning_rate"] == 0.0001

        body = route.calls.last.request.read()
        assert b'"model":"open-mistral-7b"' in body
        assert b'"hyperparameters"' in body
        assert b'"training_files"' in body
        assert b'"suffix":"my-model"' in body
        assert b'"validation_files"' not in body  # omitted when None


@pytest.mark.asyncio
async def test_finetuning_job_lifecycle(mistral: Mistral) -> None:
    """list / get / start / cancel fine-tuning jobs hit the right verbs+paths."""
    with respx.mock(base_url=BASE_URL) as respx_mock:
        respx_mock.get("/fine_tuning/jobs").mock(
            return_value=httpx.Response(
                200,
                json={"object": "list", "total": 1, "data": [_ft_job_json("RUNNING")]},
            )
        )
        respx_mock.get("/fine_tuning/jobs/ftjob-1").mock(
            return_value=httpx.Response(200, json=_ft_job_json("RUNNING"))
        )
        start_route = respx_mock.post("/fine_tuning/jobs/ftjob-1/start").mock(
            return_value=httpx.Response(200, json=_ft_job_json("STARTED"))
        )
        cancel_route = respx_mock.post("/fine_tuning/jobs/ftjob-1/cancel").mock(
            return_value=httpx.Response(200, json=_ft_job_json("CANCELLED"))
        )

        jobs = await mistral.alist_finetuning_jobs(status="RUNNING")
        assert len(jobs) == 1
        assert jobs[0].status == "RUNNING"

        got = await mistral.aget_finetuning_job(job_id="ftjob-1")
        assert got.id == "ftjob-1"

        started = await mistral.astart_finetuning_job(job_id="ftjob-1")
        assert started.status == "STARTED"
        assert start_route.calls.last.request.method == "POST"

        cancelled = await mistral.acancel_finetuning_job(job_id="ftjob-1")
        assert cancelled.status == "CANCELLED"
        assert cancel_route.calls.last.request.method == "POST"


# ---------------------------------------------------------------------------
# 14. Batch jobs — create / list / get / cancel / delete
# ---------------------------------------------------------------------------


def _batch_job_json(status: str = "QUEUED") -> dict:
    """Build a representative batch job payload."""
    return {
        "id": "batch-1",
        "object": "batch",
        "endpoint": "/v1/chat/completions",
        "model": "mistral-small-latest",
        "input_files": ["file-in-1"],
        "output_file": None,
        "errors": [],
        "status": status,
        "created_at": 1700000000,
        "total_requests": 100,
        "completed_requests": 0,
        "succeeded_requests": 0,
        "failed_requests": 0,
    }


@pytest.mark.asyncio
async def test_create_batch_job(mistral: Mistral) -> None:
    """create_batch_job: POST /batch/jobs → BatchJob with per-request counts."""
    with respx.mock(base_url=BASE_URL) as respx_mock:
        route = respx_mock.post("/batch/jobs").mock(
            return_value=httpx.Response(200, json=_batch_job_json())
        )

        result = await mistral.acreate_batch_job(
            endpoint="/v1/chat/completions",
            input_files=["file-in-1"],
            model="mistral-small-latest",
            timeout_hours=24,
        )

        assert result.id == "batch-1"
        assert result.endpoint == "/v1/chat/completions"
        assert result.total_requests == 100
        assert result.input_files == ["file-in-1"]

        body = route.calls.last.request.read()
        assert b'"endpoint":"/v1/chat/completions"' in body
        assert b'"input_files"' in body
        assert b'"timeout_hours":24' in body
        assert b'"requests"' not in body  # omitted when None


@pytest.mark.asyncio
async def test_batch_job_lifecycle(mistral: Mistral) -> None:
    """list / get / cancel / delete batch jobs hit the right verbs+paths."""
    with respx.mock(base_url=BASE_URL) as respx_mock:
        respx_mock.get("/batch/jobs").mock(
            return_value=httpx.Response(
                200,
                json={"object": "list", "total": 1, "data": [_batch_job_json("RUNNING")]},
            )
        )
        respx_mock.get("/batch/jobs/batch-1").mock(
            return_value=httpx.Response(200, json=_batch_job_json("RUNNING"))
        )
        cancel_route = respx_mock.post("/batch/jobs/batch-1/cancel").mock(
            return_value=httpx.Response(200, json=_batch_job_json("CANCELLATION_REQUESTED"))
        )
        delete_route = respx_mock.delete("/batch/jobs/batch-1").mock(
            return_value=httpx.Response(
                200,
                json={"id": "batch-1", "object": "batch", "deleted": True},
            )
        )

        jobs = await mistral.alist_batch_jobs(model="mistral-small-latest")
        assert len(jobs) == 1
        assert jobs[0].status == "RUNNING"

        got = await mistral.aget_batch_job(job_id="batch-1")
        assert got.id == "batch-1"

        cancelled = await mistral.acancel_batch_job(job_id="batch-1")
        assert cancelled.status == "CANCELLATION_REQUESTED"
        assert cancel_route.calls.last.request.method == "POST"

        deleted = await mistral.adelete_batch_job(job_id="batch-1")
        assert deleted.deleted is True
        assert delete_route.calls.last.request.method == "DELETE"


# ---------------------------------------------------------------------------
# 15. Error path — 404 on a platform GET surfaces NotFoundError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_finetuning_job_not_found(mistral: Mistral) -> None:
    """Mistral 404 on GET /fine_tuning/jobs/{id} → typed NotFoundError.

    Exercises the typed-error mapping on a non-chat platform endpoint,
    complementing the 401/429 cases on /chat/completions.
    """
    with respx.mock(base_url=BASE_URL) as respx_mock:
        respx_mock.get("/fine_tuning/jobs/missing").mock(
            return_value=httpx.Response(
                404,
                json={"message": "Job not found", "request_id": "req-404"},
            )
        )

        with pytest.raises(NotFoundError) as exc_info:
            await mistral.aget_finetuning_job(job_id="missing")

        assert exc_info.value.connector == "mistral"
        assert exc_info.value.upstream_status == 404
