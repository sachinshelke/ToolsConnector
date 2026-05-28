"""End-to-end tests for the Google Docs connector using respx.

Same shape as test_github.py / test_linear.py / test_notion.py. Pinned
to Docs API v1 at ``docs.googleapis.com/v1``. Auth is OAuth 2.0 bearer
(`Authorization: Bearer ya29.…`).

Structure:
  Round 1 — happy path for all 5 actions
  Round 2 — defensive parsing (table walk, empty body) + path guards
  Round 3 — error matrix (401/403/404/429/500)
  Round 4 — transport errors + token redaction
  Round 5 — MCP exposure + OpenAI schema + dangerous flag + sync wrappers
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
import pytest_asyncio
import respx

from toolsconnector.connectors.gdocs import GoogleDocs
from toolsconnector.errors import ConnectionError as TCConnectionError
from toolsconnector.errors import (
    InvalidCredentialsError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
)
from toolsconnector.errors import TimeoutError as TCTimeoutError
from toolsconnector.errors import TransportError as TCTransportError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def gdocs() -> GoogleDocs:
    """Google Docs connector with a fake OAuth access token.

    Token never reaches docs.googleapis.com because respx intercepts at
    the httpx transport layer.
    """
    connector = GoogleDocs(credentials="ya29.fake_test_token")
    yield connector
    # No teardown — gdocs spins a fresh AsyncClient per _request call.


# Canonical Docs API response shapes — kept minimal but valid.
_DOC_META = {
    "documentId": "doc-abc-123",
    "title": "Test Document",
    "revisionId": "ALm37BU...",
}

_DOC_WITH_BODY = {
    **_DOC_META,
    "body": {
        "content": [
            # First element is always the section break — emit nothing
            {"endIndex": 1, "sectionBreak": {}},
            # Then paragraphs with text runs
            {
                "startIndex": 1,
                "endIndex": 12,
                "paragraph": {
                    "elements": [
                        {
                            "startIndex": 1,
                            "endIndex": 12,
                            "textRun": {"content": "Hello world\n"},
                        }
                    ]
                },
            },
        ]
    },
}


# ===========================================================================
# Round 1 — happy path for every action
# ===========================================================================


@pytest.mark.asyncio
async def test_get_document_happy_path(gdocs: GoogleDocs) -> None:
    """get_document: GET /documents/{id} → Document model with metadata only."""
    with respx.mock(base_url="https://docs.googleapis.com/v1") as mock:
        route = mock.get("/documents/doc-abc-123").mock(
            return_value=httpx.Response(200, json=_DOC_META)
        )
        doc = await gdocs.aget_document(document_id="doc-abc-123")
        assert doc.id == "doc-abc-123"
        assert doc.title == "Test Document"
        assert doc.body_text is None  # metadata-only path

        # Bearer auth applied
        request = route.calls.last.request
        assert request.headers["authorization"] == "Bearer ya29.fake_test_token"


@pytest.mark.asyncio
async def test_create_document_sends_title_in_body(gdocs: GoogleDocs) -> None:
    """create_document: POST /documents with {title} body → new Document."""
    with respx.mock(base_url="https://docs.googleapis.com/v1") as mock:
        route = mock.post("/documents").mock(
            return_value=httpx.Response(
                200,
                json={**_DOC_META, "title": "New Doc", "documentId": "doc-new"},
            )
        )
        doc = await gdocs.acreate_document(title="New Doc")
        assert doc.id == "doc-new"
        assert doc.title == "New Doc"

        body = route.calls.last.request.read()
        assert b'"title":"New Doc"' in body


@pytest.mark.asyncio
async def test_batch_update_sends_requests_array(gdocs: GoogleDocs) -> None:
    """batch_update: POST /documents/{id}:batchUpdate with {requests: [...]}.

    Returns BatchUpdateResponse carrying the replies list from the API.
    """
    requests = [
        {"insertText": {"location": {"index": 1}, "text": "Hello"}},
    ]
    api_replies = [{"insertText": {}}]

    with respx.mock(base_url="https://docs.googleapis.com/v1") as mock:
        route = mock.post("/documents/doc-abc-123:batchUpdate").mock(
            return_value=httpx.Response(
                200, json={"documentId": "doc-abc-123", "replies": api_replies}
            )
        )
        resp = await gdocs.abatch_update(document_id="doc-abc-123", requests=requests)
        assert resp.document_id == "doc-abc-123"
        assert resp.replies == api_replies

        body = route.calls.last.request.read()
        assert b'"requests"' in body
        assert b'"insertText"' in body
        assert b'"Hello"' in body


@pytest.mark.asyncio
async def test_insert_text_constructs_correct_batch_request(gdocs: GoogleDocs) -> None:
    """insert_text: convenience wrapper that constructs the insertText
    request envelope and delegates to batch_update.

    Default index is 1 (start of body, after the implicit section break).
    """
    with respx.mock(base_url="https://docs.googleapis.com/v1") as mock:
        route = mock.post("/documents/doc-abc-123:batchUpdate").mock(
            return_value=httpx.Response(200, json={"documentId": "doc-abc-123", "replies": []})
        )
        await gdocs.ainsert_text(document_id="doc-abc-123", text="Hello world")

        body = route.calls.last.request.read()
        # Confirms the convenience wrapper constructs the right shape
        assert b'"insertText"' in body
        assert b'"location":{"index":1}' in body
        assert b'"text":"Hello world"' in body


@pytest.mark.asyncio
async def test_insert_text_with_custom_index(gdocs: GoogleDocs) -> None:
    """insert_text accepts an explicit index that overrides the default 1."""
    with respx.mock(base_url="https://docs.googleapis.com/v1") as mock:
        route = mock.post("/documents/d:batchUpdate").mock(
            return_value=httpx.Response(200, json={"documentId": "d", "replies": []})
        )
        await gdocs.ainsert_text(document_id="d", text="X", index=42)
        body = route.calls.last.request.read()
        assert b'"location":{"index":42}' in body


@pytest.mark.asyncio
async def test_insert_text_uses_async_batch_update_not_sync_wrapper(
    gdocs: GoogleDocs,
) -> None:
    """Regression test for the production bug fixed in 0.3.11.

    Before the fix, ``insert_text`` called ``self.batch_update(...)``.
    But after instance ``__init__``, that attribute name is rebound
    to the auto-installed SYNC wrapper (which runs asyncio.run
    internally and returns the result directly). Awaiting that
    wrapper's return value raised:

      TypeError: object BatchUpdateResponse can't be used in 'await' expression

    Every async caller of insert_text crashed before this fix.

    Fix: call ``self.abatch_update(...)`` (the async variant).
    This test pins that insert_text actually completes when called
    from an async context — if a refactor switches back to
    self.batch_update, this test fires immediately.
    """
    with respx.mock(base_url="https://docs.googleapis.com/v1") as mock:
        mock.post("/documents/d:batchUpdate").mock(
            return_value=httpx.Response(200, json={"documentId": "d", "replies": []})
        )
        # The act of `await`-ing without TypeError IS the regression check.
        result = await gdocs.ainsert_text(document_id="d", text="hi")
        # If the bug were reintroduced, await would raise TypeError above
        # and the assertion below would never execute.
        assert result is not None
        assert result.document_id == "d"


@pytest.mark.asyncio
async def test_get_document_text_extracts_plain_text(gdocs: GoogleDocs) -> None:
    """get_document_text: walks the body structure, returns concatenated text."""
    with respx.mock(base_url="https://docs.googleapis.com/v1") as mock:
        mock.get("/documents/doc-abc-123").mock(
            return_value=httpx.Response(200, json=_DOC_WITH_BODY)
        )
        text = await gdocs.aget_document_text(document_id="doc-abc-123")
        assert text == "Hello world\n"


# ===========================================================================
# Round 2 — defensive parsing + URL-path injection guards
# ===========================================================================


@pytest.mark.asyncio
async def test_get_document_text_walks_tables(gdocs: GoogleDocs) -> None:
    """Tables are nested structural elements. The parser must walk
    paragraphs INSIDE table cells, not just top-level paragraphs.
    """
    doc_with_table = {
        "documentId": "d",
        "title": "T",
        "body": {
            "content": [
                {"sectionBreak": {}},
                {
                    "table": {
                        "tableRows": [
                            {
                                "tableCells": [
                                    {
                                        "content": [
                                            {
                                                "paragraph": {
                                                    "elements": [
                                                        {"textRun": {"content": "cell-1\n"}}
                                                    ]
                                                }
                                            }
                                        ]
                                    },
                                    {
                                        "content": [
                                            {
                                                "paragraph": {
                                                    "elements": [
                                                        {"textRun": {"content": "cell-2\n"}}
                                                    ]
                                                }
                                            }
                                        ]
                                    },
                                ]
                            }
                        ]
                    }
                },
            ]
        },
    }
    with respx.mock(base_url="https://docs.googleapis.com/v1") as mock:
        mock.get("/documents/d").mock(return_value=httpx.Response(200, json=doc_with_table))
        text = await gdocs.aget_document_text(document_id="d")
        assert "cell-1" in text
        assert "cell-2" in text


@pytest.mark.asyncio
async def test_get_document_text_handles_empty_body(gdocs: GoogleDocs) -> None:
    """Empty body or missing body field → empty string, not a crash."""
    with respx.mock(base_url="https://docs.googleapis.com/v1") as mock:
        mock.get("/documents/d").mock(
            return_value=httpx.Response(200, json={"documentId": "d", "title": "T"})
        )
        text = await gdocs.aget_document_text(document_id="d")
        assert text == ""


@pytest.mark.asyncio
async def test_document_model_tolerates_unknown_api_fields(
    gdocs: GoogleDocs,
) -> None:
    """Real Docs API responses include many fields we don't model
    (documentStyle, namedStyles, lists, headers, footers, footnotes,
    inlineObjects, etc.). With extra='ignore' on the model, those are
    silently dropped and the declared fields populate correctly.
    """
    fat_response = {
        "documentId": "d",
        "title": "T",
        "revisionId": "rev",
        # Unknown fields a real response carries
        "documentStyle": {"background": {"color": {}}, "pageNumberStart": 1},
        "namedStyles": {"styles": [{"namedStyleType": "NORMAL_TEXT"}]},
        "lists": {},
        "inlineObjects": {},
        "footnotes": {},
        "documentId_was_already_above_so_extra": "extra-string",  # noqa: E501
    }
    with respx.mock(base_url="https://docs.googleapis.com/v1") as mock:
        mock.get("/documents/d").mock(return_value=httpx.Response(200, json=fat_response))
        doc = await gdocs.aget_document(document_id="d")
        assert doc.id == "d"
        assert doc.revision_id == "rev"


@pytest.mark.asyncio
async def test_document_id_with_slash_percent_encoded(gdocs: GoogleDocs) -> None:
    """Document IDs are normally URL-safe, but a hostile or buggy caller
    passing `"../admin"` as the document_id MUST NOT escape out of the
    /documents/ prefix via httpx URL normalization.

    The connector's ``_p()`` helper percent-encodes the slash so the
    request URL stays under /documents/. Mirrors the GitHub
    test_special_chars_in_owner_dont_traverse pattern.
    """
    with respx.mock(base_url="https://docs.googleapis.com/v1") as mock:
        route = mock.get(host="docs.googleapis.com").mock(
            return_value=httpx.Response(404, json={"error": {"message": "Not found"}})
        )
        with pytest.raises(NotFoundError):
            await gdocs.aget_document(document_id="../admin")

        actual_url = str(route.calls.last.request.url)
        # /documents/ prefix MUST be preserved
        assert "/documents/" in actual_url
        # The owner-style slash was percent-encoded
        assert "..%2Fadmin" in actual_url or "..%2fadmin" in actual_url
        # No traversed segment
        assert "/admin/" not in actual_url


# ===========================================================================
# Round 3 — error matrix
# ===========================================================================


@pytest.mark.asyncio
async def test_401_raises_invalid_credentials_error(gdocs: GoogleDocs) -> None:
    """Expired or invalid OAuth access token → 401 → InvalidCredentialsError."""
    with respx.mock(base_url="https://docs.googleapis.com/v1") as mock:
        mock.get("/documents/d").mock(
            return_value=httpx.Response(
                401, json={"error": {"code": 401, "message": "Invalid Credentials"}}
            )
        )
        with pytest.raises(InvalidCredentialsError) as exc_info:
            await gdocs.aget_document(document_id="d")
        assert exc_info.value.connector == "gdocs"
        assert exc_info.value.upstream_status == 401


@pytest.mark.asyncio
async def test_403_raises_permission_denied_error(gdocs: GoogleDocs) -> None:
    """Token lacks the required scope (e.g. no 'documents' scope) → 403."""
    with respx.mock(base_url="https://docs.googleapis.com/v1") as mock:
        mock.get("/documents/d").mock(
            return_value=httpx.Response(
                403,
                json={"error": {"code": 403, "message": "Insufficient Permission"}},
            )
        )
        with pytest.raises(PermissionDeniedError):
            await gdocs.aget_document(document_id="d")


@pytest.mark.asyncio
async def test_404_raises_not_found_error(gdocs: GoogleDocs) -> None:
    """Nonexistent document ID → 404 → NotFoundError."""
    with respx.mock(base_url="https://docs.googleapis.com/v1") as mock:
        mock.get("/documents/missing").mock(
            return_value=httpx.Response(404, json={"error": {"code": 404, "message": "Not found"}})
        )
        with pytest.raises(NotFoundError):
            await gdocs.aget_document(document_id="missing")


@pytest.mark.asyncio
async def test_429_raises_rate_limit_error(gdocs: GoogleDocs) -> None:
    """Quota exceeded → 429 → RateLimitError. Google sends Retry-After
    in seconds when available.
    """
    with respx.mock(base_url="https://docs.googleapis.com/v1") as mock:
        mock.get("/documents/d").mock(
            return_value=httpx.Response(
                429,
                json={"error": {"code": 429, "message": "Quota exceeded"}},
                headers={"Retry-After": "30"},
            )
        )
        with pytest.raises(RateLimitError):
            await gdocs.aget_document(document_id="d")


@pytest.mark.asyncio
async def test_500_raises_server_error(gdocs: GoogleDocs) -> None:
    """Google-side outage → 5xx → ServerError (eligible for backoff retry)."""
    with respx.mock(base_url="https://docs.googleapis.com/v1") as mock:
        mock.get("/documents/d").mock(
            return_value=httpx.Response(
                500, json={"error": {"code": 500, "message": "Server Error"}}
            )
        )
        with pytest.raises(ServerError):
            await gdocs.aget_document(document_id="d")


# ===========================================================================
# Round 4 — transport errors + 204 No Content handling
# ===========================================================================


@pytest.mark.asyncio
async def test_connect_error_raises_typed_connection_error(
    gdocs: GoogleDocs,
) -> None:
    """httpx.ConnectError → typed ConnectionError, not raw httpx class."""
    with respx.mock(base_url="https://docs.googleapis.com/v1") as mock:
        mock.get("/documents/d").mock(side_effect=httpx.ConnectError("DNS failure"))
        with pytest.raises(TCConnectionError) as exc_info:
            await gdocs.aget_document(document_id="d")
        assert exc_info.value.connector == "gdocs"
        assert "DNS failure" in exc_info.value.details["underlying"]


@pytest.mark.asyncio
async def test_timeout_raises_typed_timeout_error(gdocs: GoogleDocs) -> None:
    """httpx.TimeoutException → typed TimeoutError."""
    with respx.mock(base_url="https://docs.googleapis.com/v1") as mock:
        mock.get("/documents/d").mock(side_effect=httpx.ReadTimeout("Read timed out after 30s"))
        with pytest.raises(TCTimeoutError) as exc_info:
            await gdocs.aget_document(document_id="d")
        assert exc_info.value.connector == "gdocs"


@pytest.mark.asyncio
async def test_transport_error_raises_typed(gdocs: GoogleDocs) -> None:
    """httpx.TransportError (e.g. mid-stream drop) → typed TransportError."""
    with respx.mock(base_url="https://docs.googleapis.com/v1") as mock:
        mock.get("/documents/d").mock(side_effect=httpx.RemoteProtocolError("connection dropped"))
        with pytest.raises(TCTransportError) as exc_info:
            await gdocs.aget_document(document_id="d")
        assert "RemoteProtocolError" in str(exc_info.value)


@pytest.mark.asyncio
async def test_204_no_content_returns_empty_dict(gdocs: GoogleDocs) -> None:
    """Some endpoints (DELETE etc) return 204 with no body. The connector
    parses {} instead of crashing on empty JSON. Verified by inducing a
    204 on the GET path even though normal docs GET returns 200.
    """
    # Use batch_update which goes through the same _request path
    with respx.mock(base_url="https://docs.googleapis.com/v1") as mock:
        mock.post("/documents/d:batchUpdate").mock(return_value=httpx.Response(204))
        resp = await gdocs.abatch_update(document_id="d", requests=[])
        # 204 → {} → BatchUpdateResponse with defaults
        assert resp.document_id == "d"
        assert resp.replies == []


# ===========================================================================
# Round 5 — MCP exposure, OpenAI schema, dangerous flag, sync wrappers,
# lifecycle, concurrency
# ===========================================================================


def test_dangerous_actions_are_flagged() -> None:
    """create_document, batch_update, insert_text mutate state → dangerous.

    Reads (get_document, get_document_text) must NOT be dangerous.
    """
    spec = GoogleDocs.get_spec()
    assert spec.actions["create_document"].dangerous is True
    assert spec.actions["batch_update"].dangerous is True
    assert spec.actions["insert_text"].dangerous is True
    assert spec.actions["get_document"].dangerous is False
    assert spec.actions["get_document_text"].dangerous is False


def test_every_action_has_openai_compatible_schema() -> None:
    """Sweep: every @action produces a valid OpenAI function-call schema."""
    from toolsconnector.serve import ToolKit

    kit = ToolKit(["gdocs"], credentials={"gdocs": "ya29.fake"})
    tools = kit.to_openai_tools()
    assert len(tools) == 5
    for tool in tools:
        assert tool["type"] == "function"
        fn = tool["function"]
        assert fn["name"].startswith("gdocs_")
        assert fn["description"], fn["name"]
        params = fn["parameters"]
        assert params["type"] == "object"
        assert "properties" in params


def test_mcp_exposure_via_toolkit() -> None:
    """All 5 actions are exposed when serving via MCP."""
    from toolsconnector.serve import ToolKit

    kit = ToolKit(["gdocs"], credentials={"gdocs": "ya29.fake"})
    tools = kit.list_tools()
    names = {t["name"] for t in tools}
    assert len(names) == 5
    for action_name in (
        "get_document",
        "create_document",
        "batch_update",
        "insert_text",
        "get_document_text",
    ):
        assert f"gdocs_{action_name}" in names


def test_mcp_exclude_dangerous_keeps_only_reads() -> None:
    """exclude_dangerous filters out 3 dangerous → leaves 2 read-only."""
    from toolsconnector.serve import ToolKit

    kit_safe = ToolKit(["gdocs"], credentials={"gdocs": "ya29.fake"}, exclude_dangerous=True)
    tools_safe = kit_safe.list_tools()
    assert len(tools_safe) == 2
    safe_names = {t["name"] for t in tools_safe}
    assert "gdocs_get_document" in safe_names
    assert "gdocs_get_document_text" in safe_names
    # All 3 dangerous filtered
    for dangerous in (
        "gdocs_create_document",
        "gdocs_batch_update",
        "gdocs_insert_text",
    ):
        assert dangerous not in safe_names


def test_sync_wrappers_exist() -> None:
    """Each async @action has a sync wrapper at the bare name + an `a`-prefixed async name."""
    inst = GoogleDocs(credentials="ya29.fake")
    for action_name in (
        "get_document",
        "create_document",
        "batch_update",
        "insert_text",
        "get_document_text",
    ):
        assert hasattr(inst, action_name), f"sync wrapper missing: {action_name}"
        assert hasattr(inst, f"a{action_name}"), f"async missing: a{action_name}"


def test_verification_status_marked_live_post_tier_1_promotion() -> None:
    """gdocs was promoted to Tier 1 on 2026-05-28 — verification_status="live".

    All 5 actions live-verified against docs.googleapis.com end-to-end:
    create_document, get_document, get_document_text, insert_text, batch_update.
    Plus a real 404 → typed NotFoundError probe. MCP end-to-end smoke clean.
    """
    assert GoogleDocs.verification_status == "live"
    assert GoogleDocs.get_spec().verification_status == "live"


@pytest.mark.asyncio
async def test_concurrent_requests_safe(gdocs: GoogleDocs) -> None:
    """Two concurrent get_document calls don't share mutable state."""
    with respx.mock(base_url="https://docs.googleapis.com/v1") as mock:
        mock.get("/documents/a").mock(
            return_value=httpx.Response(200, json={**_DOC_META, "documentId": "a"})
        )
        mock.get("/documents/b").mock(
            return_value=httpx.Response(200, json={**_DOC_META, "documentId": "b"})
        )
        results = await asyncio.gather(
            gdocs.aget_document(document_id="a"),
            gdocs.aget_document(document_id="b"),
        )
        assert results[0].id == "a"
        assert results[1].id == "b"
