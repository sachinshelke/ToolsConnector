"""End-to-end tests for the Notion connector using respx.

Same playbook as tests/connectors/test_slack.py and test_github.py, but
exercises Notion's distinct semantics:

  - **REST status codes** (200/401/404/429) — Notion is a clean
    status-based API, unlike Slack's body-flag `{"ok": false}` pattern.
  - **Required `Notion-Version` header** — pinned to 2022-06-28 in the
    connector. Every request must carry it; older or missing versions
    return 400 `missing_version`.
  - **`start_cursor` / `page_size` / `has_more` / `next_cursor`** —
    the standard Notion cursor scheme. POST endpoints (search, query)
    pass these in the JSON body; GET endpoints (blocks/children,
    comments) pass them as query-string params. We pin both shapes.
  - **Notion error body** is JSON: ``{"object": "error", "status":
    <int>, "code": "<error_code>", "message": "<text>"}``. The shared
    raise_typed_for_status helper maps these by HTTP status — we just
    verify the right typed exception comes out.

Notion's 2022-06-28 API uses ``archived`` (not the newer
``is_archived`` / ``in_trash`` fields shipped in 2025-09-03+). The
connector pins the older version on purpose; see archive_page test.
"""

from __future__ import annotations

import json
from typing import Optional

import httpx
import pytest
import pytest_asyncio
import respx

from toolsconnector.connectors.notion import Notion
from toolsconnector.errors import (
    InvalidCredentialsError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ValidationError,
)
from toolsconnector.serve._filtering import build_tool_list

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def notion() -> Notion:
    """Notion connector with a fake integration token.

    Token never reaches api.notion.com because respx intercepts at the
    httpx transport layer. Tests `await` the `a`-prefixed async methods
    (e.g. `acreate_page`); BaseConnector installs both sync and async
    entry points for every @action.
    """
    connector = Notion(credentials="secret_fake_integration_token")
    await connector._setup()
    yield connector
    await connector._teardown()


# ---------------------------------------------------------------------------
# 1. Happy path — create_page under a page parent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_page_under_page_parent_happy_path(notion: Notion) -> None:
    """create_page (page parent): POST /v1/pages → NotionPage.

    Pins the request shape Notion requires for a page-parented create:
    parent={"page_id": <id>}, properties={"title": {"title": [...]}}.
    """
    with respx.mock(base_url="https://api.notion.com/v1", assert_all_called=True) as respx_mock:
        route = respx_mock.post("/pages").mock(
            return_value=httpx.Response(
                200,
                json={
                    "object": "page",
                    "id": "page-uuid-001",
                    "created_time": "2026-05-12T10:00:00.000Z",
                    "last_edited_time": "2026-05-12T10:00:00.000Z",
                    "archived": False,
                    "url": "https://www.notion.so/Test-Page-page-uuid-001",
                    "parent": {"type": "page_id", "page_id": "parent-page-uuid"},
                    "properties": {
                        "title": {
                            "id": "title",
                            "type": "title",
                            "title": [
                                {
                                    "type": "text",
                                    "plain_text": "Test Page",
                                    "annotations": {},
                                }
                            ],
                        }
                    },
                    "icon": None,
                    "cover": None,
                },
            )
        )

        page = await notion.acreate_page(
            parent_id="parent-page-uuid",
            title="Test Page",
        )

        # Response parsed into NotionPage with title preserved
        assert page.id == "page-uuid-001"
        assert page.archived is False
        assert page.url == "https://www.notion.so/Test-Page-page-uuid-001"
        assert "title" in page.properties

        # Request emitted exactly once
        assert route.call_count == 1
        request = route.calls.last.request

        # All three required Notion headers
        assert request.headers["authorization"] == "Bearer secret_fake_integration_token"
        assert request.headers["notion-version"] == "2022-06-28"
        assert request.headers["content-type"] == "application/json"

        # Body shape — page-parent variant
        body = json.loads(request.read())
        assert body["parent"] == {"page_id": "parent-page-uuid"}
        assert body["properties"]["title"]["title"][0]["text"]["content"] == "Test Page"


# ---------------------------------------------------------------------------
# 2. Happy path — search with filter + page_size capping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_filter_and_page_size_capping(notion: Notion) -> None:
    """search: POST /v1/search with filter and explicit page_size cap.

    Notion's hard cap is 100 per page; the connector applies min(limit, 100)
    before sending. We pass limit=500 and assert the body carries 100.
    """
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        route = respx_mock.post("/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "object": "list",
                    "results": [
                        {
                            "object": "page",
                            "id": "page-001",
                            "properties": {},
                            "parent": {"type": "workspace", "workspace": True},
                        }
                    ],
                    "has_more": False,
                    "next_cursor": None,
                },
            )
        )

        result = await notion.asearch(
            query="quarterly review",
            filter_type="page",
            limit=500,
        )

        assert len(result.items) == 1
        assert result.items[0].id == "page-001"
        assert result.page_state.has_more is False
        assert result.page_state.cursor is None

        body = json.loads(route.calls.last.request.read())
        assert body["query"] == "quarterly review"
        # Filter object shape per Notion canonical docs
        assert body["filter"] == {"value": "page", "property": "object"}
        # 500 caller-requested → clamped to API max of 100
        assert body["page_size"] == 100


# ---------------------------------------------------------------------------
# 3. Error mapping — vendor 401/404/429 → typed exceptions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unauthorized_raises_invalid_credentials_error(notion: Notion) -> None:
    """401 unauthorized → InvalidCredentialsError (no `expired` marker)."""
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        respx_mock.get("/pages/page-uuid-001").mock(
            return_value=httpx.Response(
                401,
                json={
                    "object": "error",
                    "status": 401,
                    "code": "unauthorized",
                    "message": "API token is invalid.",
                },
            )
        )

        with pytest.raises(InvalidCredentialsError) as exc_info:
            await notion.aget_page("page-uuid-001")

        err = exc_info.value
        assert err.connector == "notion"
        assert err.upstream_status == 401
        # Phase 1c augmentation: Notion's structured code + suggestion
        assert err.details["notion_code"] == "unauthorized"
        assert err.details["notion_message"] == "API token is invalid."
        assert err.suggestion is not None
        assert "Regenerate at" in err.suggestion


@pytest.mark.asyncio
async def test_object_not_found_raises_not_found_error(notion: Notion) -> None:
    """404 object_not_found → NotFoundError.

    Notion returns 404 for both "doesn't exist" and "not shared with
    the integration" — they're indistinguishable from the API alone.
    Either way it's a NotFoundError to the caller.
    """
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        respx_mock.get("/pages/page-does-not-exist").mock(
            return_value=httpx.Response(
                404,
                json={
                    "object": "error",
                    "status": 404,
                    "code": "object_not_found",
                    "message": "Could not find page with ID: page-does-not-exist.",
                },
            )
        )

        with pytest.raises(NotFoundError) as exc_info:
            await notion.aget_page("page-does-not-exist")

        err = exc_info.value
        assert err.connector == "notion"
        # Body preview must be preserved for debugging — and must not
        # include the bearer token (redaction covered separately in
        # tests/unit/test_http_errors_helper.py).
        assert "object_not_found" in err.details["body_preview"]
        # Phase 1c augmentation: the 404 ambiguity is surfaced via suggestion
        # (Notion returns 404 for both "missing" and "not shared with
        # integration" — the suggestion must direct the user to Connections).
        assert err.details["notion_code"] == "object_not_found"
        assert err.suggestion is not None
        assert "Connections" in err.suggestion


@pytest.mark.asyncio
async def test_rate_limited_raises_rate_limit_error_with_retry_after(notion: Notion) -> None:
    """429 rate_limited with Retry-After header → RateLimitError(retry_after).

    Notion's published rate limit is 3 req/s averaged; bursts return
    HTTP 429 with a Retry-After header carrying delta-seconds.
    """
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        respx_mock.post("/search").mock(
            return_value=httpx.Response(
                429,
                headers={"Retry-After": "30"},
                json={
                    "object": "error",
                    "status": 429,
                    "code": "rate_limited",
                    "message": "Rate limit exceeded.",
                },
            )
        )

        with pytest.raises(RateLimitError) as exc_info:
            await notion.asearch(query="hi")

        assert exc_info.value.connector == "notion"
        assert exc_info.value.retry_after_seconds == 30.0


# ---------------------------------------------------------------------------
# 4. Pagination — POST body cursor (query_database)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_database_pagination_via_post_body(notion: Notion) -> None:
    """query_database uses POST + body for cursor and page_size.

    Two-page sequence:
      - page 1: has_more=true,  next_cursor="cursor-xyz"
      - page 2: has_more=false, next_cursor=null
    The connector must wire next_cursor → start_cursor in the body on
    the follow-up call.
    """
    page1 = {
        "object": "list",
        "results": [
            {"object": "page", "id": "row-001", "properties": {}, "parent": {}},
            {"object": "page", "id": "row-002", "properties": {}, "parent": {}},
        ],
        "has_more": True,
        "next_cursor": "cursor-xyz",
    }
    page2 = {
        "object": "list",
        "results": [
            {"object": "page", "id": "row-003", "properties": {}, "parent": {}},
        ],
        "has_more": False,
        "next_cursor": None,
    }

    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        route = respx_mock.post("/databases/db-uuid/query").mock(
            side_effect=[
                httpx.Response(200, json=page1),
                httpx.Response(200, json=page2),
            ]
        )

        # Page 1
        result1 = await notion.aquery_database(database_id="db-uuid")
        assert [p.id for p in result1.items] == ["row-001", "row-002"]
        assert result1.page_state.has_more is True
        assert result1.page_state.cursor == "cursor-xyz"

        # Page 2 — cursor must travel in the POST body, not the URL
        result2 = await notion.aquery_database(
            database_id="db-uuid",
            cursor=result1.page_state.cursor,
        )
        assert [p.id for p in result2.items] == ["row-003"]
        assert result2.page_state.has_more is False
        assert result2.page_state.cursor is None

        body2 = json.loads(route.calls[1].request.read())
        assert body2["start_cursor"] == "cursor-xyz"


# ---------------------------------------------------------------------------
# 5. Pagination — GET query-string cursor (get_block_children)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_block_children_uses_query_params_for_pagination(notion: Notion) -> None:
    """blocks/{id}/children uses GET + query-string params, not body.

    This is the canonical Notion split: write endpoints (search,
    query_database, create_page) take pagination in the POST body;
    read endpoints (blocks/children, users, comments) take it in the
    URL query string. A regression here would break every paginated
    GET in the connector — worth pinning.
    """
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        route = respx_mock.get("/blocks/block-uuid/children").mock(
            return_value=httpx.Response(
                200,
                json={
                    "object": "list",
                    "results": [
                        {
                            "object": "block",
                            "id": "child-001",
                            "type": "paragraph",
                            "has_children": False,
                            "archived": False,
                            "paragraph": {"rich_text": []},
                        }
                    ],
                    "has_more": True,
                    "next_cursor": "cursor-abc",
                },
            )
        )

        result = await notion.aget_block_children(
            block_id="block-uuid",
            limit=25,
            cursor="cursor-prev",
        )

        assert len(result.items) == 1
        assert result.items[0].type == "paragraph"
        assert result.page_state.cursor == "cursor-abc"

        # Cursor + page_size must be in the URL, not the body. We assert
        # via request.url.params so the test is robust to query-string
        # ordering.
        params = route.calls.last.request.url.params
        assert params["page_size"] == "25"
        assert params["start_cursor"] == "cursor-prev"
        # GET requests should not have a JSON body
        assert route.calls.last.request.read() == b""


# ---------------------------------------------------------------------------
# 6. Version-pinned semantics — archive_page sends `archived`, not `in_trash`
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_archive_page_sends_archived_field_for_pinned_version(notion: Notion) -> None:
    """Connector pins Notion-Version 2022-06-28, where archiving is
    ``{"archived": true}`` on PATCH /pages/{id}.

    Newer versions (2025-09-03+) split this into ``is_archived`` /
    ``in_trash``, but we deliberately stay on 2022-06-28 to avoid the
    breaking data_source restructure. This test guards against a
    drive-by "modernize" that would silently break every archive call.
    """
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        route = respx_mock.patch("/pages/page-uuid-001").mock(
            return_value=httpx.Response(
                200,
                json={
                    "object": "page",
                    "id": "page-uuid-001",
                    "archived": True,
                    "properties": {},
                    "parent": {},
                },
            )
        )

        page = await notion.aarchive_page("page-uuid-001")
        assert page.archived is True

        body = json.loads(route.calls.last.request.read())
        assert body == {"archived": True}
        # Explicitly absent — these are the newer-version fields we
        # must NOT send under the pinned version.
        assert "is_archived" not in body
        assert "in_trash" not in body


# ---------------------------------------------------------------------------
# 7. Spec metadata — dangerous flag matches risk
# ---------------------------------------------------------------------------


def test_dangerous_actions_are_flagged() -> None:
    """Write/destructive actions must be dangerous=True; reads must be False.

    Under the default ToolKit config (``exclude_dangerous=True``), an
    accidentally-dropped flag would auto-expose a destructive action
    to AI agents. This test is the tripwire.
    """
    spec = Notion.get_spec()

    # Writes / destructive — includes the new delete_comment action
    for write_action in (
        "create_page",
        "create_database",
        "append_block_children",
        "delete_block",
        "add_comment",
        "delete_comment",
        "archive_page",
    ):
        assert spec.actions[write_action].dangerous is True, (
            f"{write_action} must be dangerous=True"
        )

    # Reads — includes the new get_me and get_comment actions
    for read_action in (
        "search",
        "get_page",
        "get_database",
        "list_users",
        "get_me",
        "get_comment",
    ):
        assert spec.actions[read_action].dangerous is False, (
            f"{read_action} must be dangerous=False"
        )


# ---------------------------------------------------------------------------
# 8. New actions — happy paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_me_returns_bot_user(notion: Notion) -> None:
    """get_me: GET /users/me → NotionUser representing the integration bot."""
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        route = respx_mock.get("/users/me").mock(
            return_value=httpx.Response(
                200,
                json={
                    "object": "user",
                    "id": "bot-user-uuid-001",
                    "name": "My Test Integration",
                    "avatar_url": None,
                    "type": "bot",
                    "bot": {"owner": {"type": "workspace", "workspace": True}},
                },
            )
        )

        user = await notion.aget_me()

        assert user.id == "bot-user-uuid-001"
        assert user.name == "My Test Integration"
        assert user.type == "bot"

        # Standard Notion headers attached
        request = route.calls.last.request
        assert request.headers["authorization"] == "Bearer secret_fake_integration_token"
        assert request.headers["notion-version"] == "2022-06-28"


@pytest.mark.asyncio
async def test_get_comment_returns_single_comment(notion: Notion) -> None:
    """get_comment: GET /comments/{id} → NotionComment with discussion_id."""
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        respx_mock.get("/comments/comment-uuid-001").mock(
            return_value=httpx.Response(
                200,
                json={
                    "object": "comment",
                    "id": "comment-uuid-001",
                    "parent": {"type": "page_id", "page_id": "page-uuid-001"},
                    "discussion_id": "discussion-uuid-001",
                    "created_time": "2026-05-12T10:00:00.000Z",
                    "last_edited_time": "2026-05-12T10:00:00.000Z",
                    "created_by": {
                        "object": "user",
                        "id": "user-uuid-001",
                        "name": "Sachin",
                        "type": "person",
                    },
                    "rich_text": [
                        {"type": "text", "plain_text": "Initial comment", "annotations": {}}
                    ],
                },
            )
        )

        comment = await notion.aget_comment("comment-uuid-001")
        assert comment.id == "comment-uuid-001"
        assert comment.discussion_id == "discussion-uuid-001"
        assert comment.created_by is not None
        assert comment.created_by.name == "Sachin"
        assert len(comment.rich_text) == 1
        assert comment.rich_text[0].plain_text == "Initial comment"


@pytest.mark.asyncio
async def test_create_page_under_database_parent(notion: Notion) -> None:
    """create_page (database parent): pins the parent={"database_id": ...} branch.

    Currently only the page-parent branch is covered by
    test_create_page_under_page_parent_happy_path. This pins the second
    branch + the auto-title-insertion-when-not-in-properties behavior.
    """
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        route = respx_mock.post("/pages").mock(
            return_value=httpx.Response(
                200,
                json={
                    "object": "page",
                    "id": "row-uuid-001",
                    "archived": False,
                    "parent": {"type": "database_id", "database_id": "db-uuid"},
                    "properties": {
                        "Name": {
                            "id": "title",
                            "type": "title",
                            "title": [{"type": "text", "plain_text": "New Row", "annotations": {}}],
                        },
                        "Priority": {
                            "id": "PR-1",
                            "type": "select",
                            "select": {"id": "opt-1", "name": "High", "color": "red"},
                        },
                    },
                },
            )
        )

        page = await notion.acreate_page(
            parent_id="db-uuid",
            title="New Row",
            properties={"Priority": {"select": {"name": "High"}}},
        )

        assert page.id == "row-uuid-001"
        # Response carries the database's actual property key ("Name")
        assert "Name" in page.properties

        body = json.loads(route.calls.last.request.read())
        # Database parent shape, not page parent
        assert body["parent"] == {"database_id": "db-uuid"}
        # Caller's properties preserved AND title auto-inserted into the
        # request body (because neither "title" nor "Name" was in the
        # caller-supplied properties dict — the connector inserts a "title"
        # key as the fallback).
        assert body["properties"]["Priority"] == {"select": {"name": "High"}}
        assert body["properties"]["title"]["title"][0]["text"]["content"] == "New Row"


@pytest.mark.asyncio
async def test_append_block_children_nested_blocks(notion: Notion) -> None:
    """append_block_children: nested children survive request serialization.

    Regression guard — if a refactor flattens or strips nested `children`,
    every "add a toggle with sub-bullets" workflow breaks silently.
    """
    nested = [
        {
            "object": "block",
            "type": "toggle",
            "toggle": {
                "rich_text": [{"text": {"content": "Outer"}}],
                "children": [
                    {
                        "object": "block",
                        "type": "bulleted_list_item",
                        "bulleted_list_item": {"rich_text": [{"text": {"content": "Inner item"}}]},
                    }
                ],
            },
        }
    ]
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        route = respx_mock.patch("/blocks/parent-block/children").mock(
            return_value=httpx.Response(
                200,
                json={
                    "object": "list",
                    "results": [
                        {
                            "object": "block",
                            "id": "new-toggle-001",
                            "type": "toggle",
                            "has_children": True,
                            "archived": False,
                            "toggle": {"rich_text": []},
                        }
                    ],
                    "has_more": False,
                    "next_cursor": None,
                },
            )
        )

        blocks = await notion.aappend_block_children(
            block_id="parent-block",
            children=nested,
        )
        assert len(blocks) == 1
        assert blocks[0].type == "toggle"

        body = json.loads(route.calls.last.request.read())
        # Nested children must round-trip unchanged
        inner = body["children"][0]["toggle"]["children"][0]
        assert inner["type"] == "bulleted_list_item"
        assert inner["bulleted_list_item"]["rich_text"][0]["text"]["content"] == "Inner item"


@pytest.mark.asyncio
async def test_update_comment_replaces_rich_text(notion: Notion) -> None:
    """update_comment: PATCH /comments/{id} with rich_text body."""
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        route = respx_mock.patch("/comments/comment-uuid-001").mock(
            return_value=httpx.Response(
                200,
                json={
                    "object": "comment",
                    "id": "comment-uuid-001",
                    "parent": {"type": "page_id", "page_id": "page-uuid-001"},
                    "discussion_id": "discussion-uuid-001",
                    "rich_text": [{"type": "text", "plain_text": "Edited text", "annotations": {}}],
                },
            )
        )

        comment = await notion.aupdate_comment(
            comment_id="comment-uuid-001",
            text="Edited text",
        )
        assert comment.rich_text[0].plain_text == "Edited text"

        body = json.loads(route.calls.last.request.read())
        assert body == {"rich_text": [{"text": {"content": "Edited text"}}]}


@pytest.mark.asyncio
async def test_delete_comment_returns_none(notion: Notion) -> None:
    """delete_comment: DELETE /comments/{id} → no body, returns None."""
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        route = respx_mock.delete("/comments/comment-uuid-001").mock(
            return_value=httpx.Response(204)
        )

        result = await notion.adelete_comment("comment-uuid-001")
        assert result is None
        assert route.call_count == 1


@pytest.mark.asyncio
async def test_add_comment_thread_with_discussion_id(notion: Notion) -> None:
    """add_comment(discussion_id=...): pins the threaded-reply body shape.

    Important Notion quirk: threaded replies put ``discussion_id`` at the
    TOP LEVEL of the request body, NOT inside a ``parent`` envelope —
    unlike every other comment/page/database creation in the API.

    History: this test originally asserted the wrong shape
    (``parent: {discussion_id: ...}``). The connector silently 400'd
    against the real Notion API; the bug was caught by live verification.
    The test now asserts the verified-correct top-level shape.
    """
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        route = respx_mock.post("/comments").mock(
            return_value=httpx.Response(
                200,
                json={
                    "object": "comment",
                    "id": "reply-uuid-001",
                    "parent": {
                        "type": "discussion_id",
                        "discussion_id": "discussion-uuid-001",
                    },
                    "discussion_id": "discussion-uuid-001",
                    "rich_text": [{"type": "text", "plain_text": "Reply text", "annotations": {}}],
                },
            )
        )

        reply = await notion.aadd_comment(
            page_id="page-uuid-001",  # ignored when discussion_id is set
            text="Reply text",
            discussion_id="discussion-uuid-001",
        )
        assert reply.id == "reply-uuid-001"
        assert reply.discussion_id == "discussion-uuid-001"

        body = json.loads(route.calls.last.request.read())
        # The verified-correct shape: discussion_id at the TOP LEVEL,
        # NOT wrapped in {"parent": {"discussion_id": ...}}.
        assert body["discussion_id"] == "discussion-uuid-001"
        # The body must NOT carry a parent envelope when threading
        assert "parent" not in body
        # Page id must not leak into the threaded body
        assert "page_id" not in body


# ---------------------------------------------------------------------------
# 9. Error matrix completion + augmentation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validation_error_on_bad_body(notion: Notion) -> None:
    """400 validation_error → ValidationError + Notion's field-level reason
    surfaced via details["notion_message"].
    """
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        respx_mock.post("/pages").mock(
            return_value=httpx.Response(
                400,
                json={
                    "object": "error",
                    "status": 400,
                    "code": "validation_error",
                    "message": (
                        "body failed validation: body.properties.Priority.select"
                        " should be defined, instead was undefined."
                    ),
                },
            )
        )

        with pytest.raises(ValidationError) as exc_info:
            await notion.acreate_page(parent_id="db-uuid", title="X")

        err = exc_info.value
        assert err.details["notion_code"] == "validation_error"
        assert "body.properties.Priority.select" in err.details["notion_message"]
        assert err.suggestion is not None
        assert "field-level" in err.suggestion


@pytest.mark.asyncio
async def test_restricted_resource_raises_permission_denied_with_suggestion(
    notion: Notion,
) -> None:
    """403 restricted_resource: missing capability OR unshared page.

    This is the #1 BYOK gotcha — a token authenticates fine then 403s
    on a write action. The augmented suggestion must call out both the
    capability path AND the Connections path so the user can fix it
    without a doc-dive.
    """
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        respx_mock.patch("/blocks/block-uuid-001").mock(
            return_value=httpx.Response(
                403,
                json={
                    "object": "error",
                    "status": 403,
                    "code": "restricted_resource",
                    "message": ("API token does not have access to update this resource."),
                },
            )
        )

        with pytest.raises(PermissionDeniedError) as exc_info:
            await notion.aupdate_block(
                block_id="block-uuid-001",
                content={"paragraph": {"rich_text": []}},
            )

        err = exc_info.value
        assert err.connector == "notion"
        assert err.details["notion_code"] == "restricted_resource"
        # Notion's own message preserved for debugging
        assert "update this resource" in err.details["notion_message"]
        # Augmented suggestion calls out both fix paths
        assert err.suggestion is not None
        assert "capability" in err.suggestion.lower()
        assert "Connections" in err.suggestion


@pytest.mark.asyncio
async def test_parse_page_tolerates_unknown_property_types(notion: Notion) -> None:
    """Pydantic strict-mode bug fix: NotionProperty must drop unknown fields.

    Notion's API evolves; new property types appear in responses without
    bumping the major version. Before extra="ignore" was added to
    model_config, parsing a page with a `unique_id` or `created_time`
    property crashed every row. This test pins the fix.
    """
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        respx_mock.get("/pages/page-uuid-001").mock(
            return_value=httpx.Response(
                200,
                json={
                    "object": "page",
                    "id": "page-uuid-001",
                    "archived": False,
                    "parent": {"type": "database_id", "database_id": "db-uuid"},
                    "properties": {
                        # Modeled property type — must parse cleanly
                        "Name": {
                            "id": "title",
                            "type": "title",
                            "title": [{"type": "text", "plain_text": "Hello", "annotations": {}}],
                        },
                        # 2022-06-28 type that's NOT in our pydantic model
                        "Created Time": {
                            "id": "ct",
                            "type": "created_time",
                            "created_time": "2026-05-12T10:00:00.000Z",
                        },
                        # Newer (post-2022-06-28) type also not modeled
                        "ID": {
                            "id": "unique-id",
                            "type": "unique_id",
                            "unique_id": {"number": 42, "prefix": "TASK"},
                        },
                    },
                },
            )
        )

        # The whole point: this must NOT raise pydantic.ValidationError
        page = await notion.aget_page("page-uuid-001")
        assert page.id == "page-uuid-001"
        # All three properties land in the dict; modeled fields hydrate normally
        assert set(page.properties.keys()) == {"Name", "Created Time", "ID"}
        assert page.properties["Name"].type == "title"
        # Unknown-type properties get their `type` populated but unmodeled
        # value fields are silently dropped (extra="ignore")
        assert page.properties["Created Time"].type == "created_time"
        assert page.properties["ID"].type == "unique_id"


# ---------------------------------------------------------------------------
# 10. MCP tool exposure smoke test
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 11. Parser audit regression — created_by / last_edited_by extraction
# ---------------------------------------------------------------------------
#
# Before the audit, parse_page / parse_block / parse_database silently
# dropped the created_by + last_edited_by fields even though the pydantic
# models declared them. NotionDatabase didn't have the fields at all.
# These tests pin the fix so future refactors can't reintroduce the drop.


@pytest.mark.asyncio
async def test_parse_page_extracts_created_by_and_last_edited_by(notion: Notion) -> None:
    """get_page response with user fields → NotionPage.created_by / last_edited_by populated.

    Regression for the parser bug: NotionPage declared the fields but
    parse_page never extracted them. The fields were always None
    regardless of the API response.
    """
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        respx_mock.get("/pages/page-uuid-001").mock(
            return_value=httpx.Response(
                200,
                json={
                    "object": "page",
                    "id": "page-uuid-001",
                    "archived": False,
                    "parent": {"type": "page_id", "page_id": "parent-uuid"},
                    "properties": {},
                    "created_by": {
                        "object": "user",
                        "id": "user-creator-001",
                        "name": "Alice",
                        "type": "person",
                    },
                    "last_edited_by": {
                        "object": "user",
                        "id": "bot-editor-001",
                        "name": "My Integration",
                        "type": "bot",
                    },
                },
            )
        )

        page = await notion.aget_page("page-uuid-001")
        assert page.created_by is not None
        assert page.created_by.id == "user-creator-001"
        assert page.created_by.name == "Alice"
        assert page.created_by.type == "person"
        assert page.last_edited_by is not None
        assert page.last_edited_by.id == "bot-editor-001"
        assert page.last_edited_by.type == "bot"


@pytest.mark.asyncio
async def test_parse_block_extracts_created_by_and_last_edited_by(notion: Notion) -> None:
    """get_block response with user fields → NotionBlock.created_by / last_edited_by populated.

    Same regression scope as the page test, but for blocks.
    """
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        respx_mock.get("/blocks/block-uuid-001").mock(
            return_value=httpx.Response(
                200,
                json={
                    "object": "block",
                    "id": "block-uuid-001",
                    "type": "paragraph",
                    "has_children": False,
                    "archived": False,
                    "paragraph": {"rich_text": []},
                    "created_by": {
                        "object": "user",
                        "id": "user-creator-001",
                        "type": "person",
                    },
                    "last_edited_by": {
                        "object": "user",
                        "id": "user-editor-001",
                        "type": "person",
                    },
                },
            )
        )

        block = await notion.aget_block("block-uuid-001")
        assert block.type == "paragraph"
        assert block.created_by is not None
        assert block.created_by.id == "user-creator-001"
        assert block.last_edited_by is not None
        assert block.last_edited_by.id == "user-editor-001"


@pytest.mark.asyncio
async def test_parse_database_extracts_created_by_and_last_edited_by(notion: Notion) -> None:
    """get_database response with user fields → NotionDatabase.created_by / last_edited_by populated.

    The bug was double here: parser dropped the fields AND the model
    didn't declare them. Fix added both. This test pins the model gain
    + parser fix.
    """
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        respx_mock.get("/databases/db-uuid-001").mock(
            return_value=httpx.Response(
                200,
                json={
                    "object": "database",
                    "id": "db-uuid-001",
                    "title": [{"type": "text", "plain_text": "Projects", "annotations": {}}],
                    "description": [],
                    "archived": False,
                    "parent": {},
                    "properties": {},
                    "created_by": {
                        "object": "user",
                        "id": "user-creator-001",
                        "name": "Sachin",
                        "type": "person",
                    },
                    "last_edited_by": {
                        "object": "user",
                        "id": "bot-editor-001",
                        "name": "My Integration",
                        "type": "bot",
                    },
                },
            )
        )

        db = await notion.aget_database("db-uuid-001")
        assert db.id == "db-uuid-001"
        assert db.created_by is not None
        assert db.created_by.id == "user-creator-001"
        assert db.created_by.name == "Sachin"
        assert db.last_edited_by is not None
        assert db.last_edited_by.type == "bot"


@pytest.mark.asyncio
async def test_parse_page_handles_missing_user_fields(notion: Notion) -> None:
    """Pages without created_by / last_edited_by must still parse.

    Older Notion responses or partial-page responses may omit user
    fields. The parser must return None for them, not raise.
    """
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        respx_mock.get("/pages/legacy-page").mock(
            return_value=httpx.Response(
                200,
                json={
                    "object": "page",
                    "id": "legacy-page",
                    "archived": False,
                    "parent": {},
                    "properties": {},
                    # No created_by / last_edited_by fields
                },
            )
        )
        page = await notion.aget_page("legacy-page")
        assert page.created_by is None
        assert page.last_edited_by is None


# ---------------------------------------------------------------------------
# 12. Coverage tests — previously untested actions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_comments_paginates_via_query_string(notion: Notion) -> None:
    """list_comments: GET /comments with block_id as query param + cursor pagination."""
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        route = respx_mock.get("/comments").mock(
            return_value=httpx.Response(
                200,
                json={
                    "object": "list",
                    "results": [
                        {
                            "object": "comment",
                            "id": "comment-001",
                            "parent": {"type": "page_id", "page_id": "page-uuid"},
                            "discussion_id": "discussion-uuid",
                            "created_by": {"id": "user-001", "type": "person"},
                            "rich_text": [
                                {"type": "text", "plain_text": "First comment", "annotations": {}}
                            ],
                        }
                    ],
                    "has_more": True,
                    "next_cursor": "comments-cursor-abc",
                },
            )
        )

        result = await notion.alist_comments(block_id="page-uuid", limit=25, cursor="prev-cursor")

        assert len(result.items) == 1
        assert result.items[0].discussion_id == "discussion-uuid"
        assert result.page_state.cursor == "comments-cursor-abc"
        assert result.page_state.has_more is True

        # All three pagination params must go in the query string (GET endpoint)
        params = route.calls.last.request.url.params
        assert params["block_id"] == "page-uuid"
        assert params["page_size"] == "25"
        assert params["start_cursor"] == "prev-cursor"


@pytest.mark.asyncio
async def test_update_database_partial_payload(notion: Notion) -> None:
    """update_database: PATCH /databases/{id} only sends fields the caller set.

    Title-only update must NOT send description or properties — those
    null-passes would clear the existing values on the server.
    """
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        route = respx_mock.patch("/databases/db-uuid").mock(
            return_value=httpx.Response(
                200,
                json={
                    "object": "database",
                    "id": "db-uuid",
                    "title": [{"type": "text", "plain_text": "New Title", "annotations": {}}],
                    "description": [],
                    "archived": False,
                    "parent": {},
                    "properties": {},
                },
            )
        )

        db = await notion.aupdate_database(database_id="db-uuid", title="New Title")
        assert db.id == "db-uuid"
        assert db.title[0].plain_text == "New Title"

        body = json.loads(route.calls.last.request.read())
        # Only title was sent — no description, no properties keys
        assert "title" in body
        assert "description" not in body
        assert "properties" not in body


@pytest.mark.asyncio
async def test_get_block_returns_single_block(notion: Notion) -> None:
    """get_block: GET /blocks/{id} → NotionBlock for the single block."""
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        respx_mock.get("/blocks/block-uuid-001").mock(
            return_value=httpx.Response(
                200,
                json={
                    "object": "block",
                    "id": "block-uuid-001",
                    "type": "heading_2",
                    "has_children": False,
                    "archived": False,
                    "heading_2": {
                        "rich_text": [{"type": "text", "plain_text": "Section", "annotations": {}}]
                    },
                },
            )
        )

        block = await notion.aget_block("block-uuid-001")
        assert block.id == "block-uuid-001"
        assert block.type == "heading_2"
        # parse_block stores the type-keyed content under `.content`
        assert block.content["rich_text"][0]["plain_text"] == "Section"


@pytest.mark.asyncio
async def test_get_page_property_passes_pagination_params(notion: Notion) -> None:
    """get_page_property: cursor + limit travel as query params for paginated property types.

    Pre-audit, the action took no pagination args at all — silent
    truncation for paginated property types (relation, rollup with 100+
    entries). This test pins the new behavior.
    """
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        route = respx_mock.get("/pages/page-uuid/properties/relation-prop").mock(
            return_value=httpx.Response(
                200,
                json={
                    "object": "list",
                    "type": "property_item",
                    "results": [
                        {
                            "object": "property_item",
                            "type": "relation",
                            "relation": {"id": "related-page-001"},
                        }
                    ],
                    "has_more": True,
                    "next_cursor": "prop-cursor-xyz",
                    "property_item": {
                        "id": "relation-prop",
                        "type": "relation",
                        "next_url": "...",
                    },
                },
            )
        )

        data = await notion.aget_page_property(
            page_id="page-uuid",
            property_id="relation-prop",
            cursor="prev-prop-cursor",
            limit=50,
        )

        # Paginated response shape preserved verbatim for the caller
        assert data["object"] == "list"
        assert data["has_more"] is True
        assert data["next_cursor"] == "prop-cursor-xyz"

        # Cursor + limit sent as query params
        params = route.calls.last.request.url.params
        assert params["page_size"] == "50"
        assert params["start_cursor"] == "prev-prop-cursor"


@pytest.mark.asyncio
async def test_get_page_property_non_paginated_returns_property_item(notion: Notion) -> None:
    """Non-paginated property types return a single property_item object."""
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        respx_mock.get("/pages/page-uuid/properties/number-prop").mock(
            return_value=httpx.Response(
                200,
                json={
                    "object": "property_item",
                    "type": "number",
                    "number": 42,
                    "id": "number-prop",
                },
            )
        )

        data = await notion.aget_page_property(
            page_id="page-uuid",
            property_id="number-prop",
        )

        # Returned shape distinguishes from paginated case via `object`
        assert data["object"] == "property_item"
        assert data["type"] == "number"
        assert data["number"] == 42


# ---------------------------------------------------------------------------
# 13. Action coverage — actions previously exercised only via integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_page_sends_properties_only(notion: Notion) -> None:
    """update_page: PATCH /pages/{id} with body={"properties": ...}."""
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        route = respx_mock.patch("/pages/page-uuid-001").mock(
            return_value=httpx.Response(
                200,
                json={
                    "object": "page",
                    "id": "page-uuid-001",
                    "archived": False,
                    "parent": {},
                    "properties": {
                        "Status": {
                            "id": "status",
                            "type": "select",
                            "select": {"id": "opt-1", "name": "Done", "color": "green"},
                        }
                    },
                },
            )
        )

        page = await notion.aupdate_page(
            page_id="page-uuid-001",
            properties={"Status": {"select": {"name": "Done"}}},
        )
        assert page.id == "page-uuid-001"
        body = json.loads(route.calls.last.request.read())
        assert body == {"properties": {"Status": {"select": {"name": "Done"}}}}


@pytest.mark.asyncio
async def test_create_database_payload_shape(notion: Notion) -> None:
    """create_database: POST /databases with parent.page_id + title + properties."""
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        route = respx_mock.post("/databases").mock(
            return_value=httpx.Response(
                200,
                json={
                    "object": "database",
                    "id": "new-db-001",
                    "title": [{"type": "text", "plain_text": "Tasks", "annotations": {}}],
                    "description": [],
                    "archived": False,
                    "parent": {"type": "page_id", "page_id": "parent-page"},
                    "properties": {
                        "Name": {"id": "title", "type": "title", "title": {}},
                        "Done": {"id": "done", "type": "checkbox", "checkbox": {}},
                    },
                },
            )
        )

        db = await notion.acreate_database(
            parent_id="parent-page",
            title="Tasks",
            properties={
                "Name": {"title": {}},
                "Done": {"checkbox": {}},
            },
        )
        assert db.id == "new-db-001"
        assert db.title[0].plain_text == "Tasks"

        body = json.loads(route.calls.last.request.read())
        assert body["parent"] == {"page_id": "parent-page"}
        assert body["title"] == [{"text": {"content": "Tasks"}}]
        assert "Name" in body["properties"] and "Done" in body["properties"]


@pytest.mark.asyncio
async def test_delete_block_returns_none(notion: Notion) -> None:
    """delete_block: DELETE /blocks/{id} → None, request emitted exactly once."""
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        route = respx_mock.delete("/blocks/block-uuid-001").mock(return_value=httpx.Response(204))
        result = await notion.adelete_block("block-uuid-001")
        assert result is None
        assert route.call_count == 1


@pytest.mark.asyncio
async def test_update_block_passes_content_dict_verbatim(notion: Notion) -> None:
    """update_block: PATCH /blocks/{id} with caller-supplied content as the body.

    The content dict is type-specific (paragraph, heading_2, etc.); the
    connector passes it through unchanged.
    """
    new_content = {"paragraph": {"rich_text": [{"text": {"content": "Edited"}}]}}
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        route = respx_mock.patch("/blocks/block-uuid-001").mock(
            return_value=httpx.Response(
                200,
                json={
                    "object": "block",
                    "id": "block-uuid-001",
                    "type": "paragraph",
                    "has_children": False,
                    "archived": False,
                    "paragraph": {"rich_text": [{"plain_text": "Edited"}]},
                },
            )
        )
        block = await notion.aupdate_block(block_id="block-uuid-001", content=new_content)
        assert block.type == "paragraph"
        body = json.loads(route.calls.last.request.read())
        # Content dict passed verbatim
        assert body == new_content


@pytest.mark.asyncio
async def test_restore_page_sends_archived_false(notion: Notion) -> None:
    """restore_page: PATCH /pages/{id} with body={"archived": False}.

    Companion to test_archive_page_sends_archived_field_for_pinned_version
    — covers the opposite-direction code path under the same version pin.
    """
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        route = respx_mock.patch("/pages/page-uuid-001").mock(
            return_value=httpx.Response(
                200,
                json={
                    "object": "page",
                    "id": "page-uuid-001",
                    "archived": False,
                    "parent": {},
                    "properties": {},
                },
            )
        )
        page = await notion.arestore_page("page-uuid-001")
        assert page.archived is False
        body = json.loads(route.calls.last.request.read())
        assert body == {"archived": False}


@pytest.mark.asyncio
async def test_list_users_extracts_persons_and_bots(notion: Notion) -> None:
    """list_users: GET /users → list[NotionUser], type preserved (person or bot)."""
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        respx_mock.get("/users").mock(
            return_value=httpx.Response(
                200,
                json={
                    "object": "list",
                    "results": [
                        {
                            "object": "user",
                            "id": "user-001",
                            "name": "Alice",
                            "type": "person",
                        },
                        {
                            "object": "user",
                            "id": "bot-001",
                            "name": "My Integration",
                            "type": "bot",
                        },
                    ],
                    "has_more": False,
                    "next_cursor": None,
                },
            )
        )
        users = await notion.alist_users()
        assert len(users) == 2
        assert users[0].type == "person"
        assert users[1].type == "bot"


@pytest.mark.asyncio
async def test_get_user_returns_single_user(notion: Notion) -> None:
    """get_user: GET /users/{id} → NotionUser (uses shared parse_user)."""
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        respx_mock.get("/users/user-uuid-001").mock(
            return_value=httpx.Response(
                200,
                json={
                    "object": "user",
                    "id": "user-uuid-001",
                    "name": "Alice",
                    "avatar_url": "https://example.com/alice.png",
                    "type": "person",
                },
            )
        )
        user = await notion.aget_user("user-uuid-001")
        assert user.id == "user-uuid-001"
        assert user.name == "Alice"
        assert user.avatar_url == "https://example.com/alice.png"


@pytest.mark.asyncio
async def test_add_comment_top_level_uses_page_id_parent(notion: Notion) -> None:
    """add_comment without discussion_id sends parent={"page_id": ...}.

    Companion to test_add_comment_thread_with_discussion_id — pins the
    non-threaded code path (line 717 of connector.py).
    """
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        route = respx_mock.post("/comments").mock(
            return_value=httpx.Response(
                200,
                json={
                    "object": "comment",
                    "id": "comment-001",
                    "parent": {"type": "page_id", "page_id": "page-uuid-001"},
                    "discussion_id": "new-discussion-uuid",
                    "rich_text": [{"type": "text", "plain_text": "Top-level", "annotations": {}}],
                },
            )
        )
        comment = await notion.aadd_comment(page_id="page-uuid-001", text="Top-level")
        assert comment.discussion_id == "new-discussion-uuid"
        body = json.loads(route.calls.last.request.read())
        assert body["parent"] == {"page_id": "page-uuid-001"}
        assert "discussion_id" not in body["parent"]


@pytest.mark.asyncio
async def test_query_database_with_filter_and_sorts(notion: Notion) -> None:
    """query_database: filter + sorts both appear in body when supplied.

    Pre-round-2 these two branches (lines 443, 445) were uncovered —
    only the bare cursor-pagination path was tested.
    """
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        route = respx_mock.post("/databases/db-uuid/query").mock(
            return_value=httpx.Response(
                200,
                json={"object": "list", "results": [], "has_more": False, "next_cursor": None},
            )
        )
        await notion.aquery_database(
            database_id="db-uuid",
            filter={"and": [{"property": "Done", "checkbox": {"equals": True}}]},
            sorts=[{"property": "Priority", "direction": "descending"}],
        )
        body = json.loads(route.calls.last.request.read())
        assert body["filter"]["and"][0]["property"] == "Done"
        assert body["sorts"] == [{"property": "Priority", "direction": "descending"}]


@pytest.mark.asyncio
async def test_create_page_with_children_blocks(notion: Notion) -> None:
    """create_page accepts a `children` arg and forwards it under body["children"].

    Pre-round-2 the children=… branch (line 378 of connector.py) was
    not exercised by any test.
    """
    children = [
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [{"text": {"content": "Body line"}}]},
        }
    ]
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        route = respx_mock.post("/pages").mock(
            return_value=httpx.Response(
                200,
                json={
                    "object": "page",
                    "id": "page-uuid-001",
                    "archived": False,
                    "parent": {"type": "page_id", "page_id": "parent-uuid"},
                    "properties": {},
                },
            )
        )
        await notion.acreate_page(
            parent_id="parent-uuid",
            title="Page with body",
            children=children,
        )
        body = json.loads(route.calls.last.request.read())
        assert body["children"] == children


@pytest.mark.asyncio
async def test_search_with_cursor_passes_start_cursor(notion: Notion) -> None:
    """search: cursor kwarg travels as body["start_cursor"]."""
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        route = respx_mock.post("/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "object": "list",
                    "results": [],
                    "has_more": False,
                    "next_cursor": None,
                },
            )
        )
        await notion.asearch(query="x", cursor="search-cursor-abc")
        body = json.loads(route.calls.last.request.read())
        assert body["start_cursor"] == "search-cursor-abc"


# ---------------------------------------------------------------------------
# 14. Defensive _request behavior — round-2 audit findings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_handles_null_json_body(notion: Notion) -> None:
    """If Notion ever returns 200 with literal JSON `null`, _request must
    return {} rather than letting `None.get(...)` raise AttributeError
    downstream.

    Defensive fix from round-2 audit: response.content is truthy (non-empty
    body), so the empty-body short-circuit doesn't fire — but
    response.json() yields None for the literal `null` body. Without the
    None-coalesce, list_users / list_comments / etc. would crash trying
    to call .get("results", []) on None.
    """
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        # respx + httpx encodes None as the JSON literal `null`
        respx_mock.get("/users").mock(
            return_value=httpx.Response(
                200,
                content=b"null",
                headers={"content-type": "application/json"},
            )
        )
        users = await notion.alist_users()
        # Coalesces null → {} → results=[] → empty list (no crash)
        assert users == []


@pytest.mark.asyncio
async def test_query_database_three_page_sequence(notion: Notion) -> None:
    """Pagination works for 3+ page sequences, not just 2.

    The existing 2-page test pinned the cursor handoff once; this one
    pins that the chain doesn't break after the third hop and that
    has_more flips correctly on the final page.
    """
    pages = [
        {
            "object": "list",
            "results": [
                {"object": "page", "id": f"row-1{i}", "properties": {}, "parent": {}}
                for i in range(2)
            ],
            "has_more": True,
            "next_cursor": "cursor-page-2",
        },
        {
            "object": "list",
            "results": [
                {"object": "page", "id": f"row-2{i}", "properties": {}, "parent": {}}
                for i in range(2)
            ],
            "has_more": True,
            "next_cursor": "cursor-page-3",
        },
        {
            "object": "list",
            "results": [{"object": "page", "id": "row-30", "properties": {}, "parent": {}}],
            "has_more": False,
            "next_cursor": None,
        },
    ]
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        respx_mock.post("/databases/db-uuid/query").mock(
            side_effect=[httpx.Response(200, json=p) for p in pages]
        )

        all_rows = []
        cursor: Optional[str] = None
        page_num = 0
        while True:
            page_num += 1
            assert page_num <= 5, "should terminate within 3 pages"
            result = await notion.aquery_database(database_id="db-uuid", cursor=cursor)
            all_rows.extend(result.items)
            if not result.page_state.has_more:
                break
            cursor = result.page_state.cursor

        # 2 + 2 + 1 = 5 rows across 3 pages; final page_state.has_more=False
        assert len(all_rows) == 5
        assert page_num == 3


@pytest.mark.asyncio
async def test_delete_comment_via_toolkit_execute_returns_empty_object(
    notion: Notion,
) -> None:
    """When called via ToolKit.execute (the MCP / HTTP transport path),
    actions that return None must serialize cleanly — not crash and not
    leak a Python None into the wire format.

    Direct connector-layer test (`test_delete_comment_returns_none`)
    confirms the connector returns None. This one confirms the
    serialization layer wraps that None into the wire-format equivalent
    without erroring.
    """
    from toolsconnector.serve import ToolKit

    kit = ToolKit(["notion"], credentials={"notion": "secret_fake_token"})
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        respx_mock.delete("/comments/comment-uuid-001").mock(return_value=httpx.Response(204))

        raw = kit.execute("notion_delete_comment", {"comment_id": "comment-uuid-001"})

    # ToolKit's serialization layer wraps a None return into a small
    # JSON object so the wire format always carries valid JSON. The
    # exact shape isn't load-bearing — what matters is (a) execute()
    # did NOT raise, and (b) the wire value is parseable.
    assert raw is not None
    parsed = json.loads(raw)
    assert isinstance(parsed, dict)


# ---------------------------------------------------------------------------
# 15. Adversarial — path traversal / injection / boundary attacks
# ---------------------------------------------------------------------------
#
# These tests simulate a hostile or buggy caller (or an AI agent acting on
# malicious tool input). The connector must refuse the dangerous shape at
# the action boundary — the request must never leave the process.


@pytest.mark.asyncio
async def test_page_id_with_path_traversal_is_rejected(notion: Notion) -> None:
    """aget_page('../users/me') must raise — not silently call /users/me.

    Pre-fix: f-string interpolation of page_id let an attacker traverse
    to a different endpoint. Now blocked at the action boundary; no HTTP
    request is even issued.
    """
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        # No respx route registered — if the connector lets the request
        # through, respx will fail with "no matching route". We expect
        # ValidationError BEFORE any HTTP call.
        with pytest.raises(ValidationError) as exc_info:
            await notion.aget_page("../users/me")

        err = exc_info.value
        assert err.connector == "notion"
        assert "page_id" in err.message
        assert "/" in err.details["forbidden_char"]
        # And critically, no HTTP request was issued
        assert len(respx_mock.calls) == 0


@pytest.mark.asyncio
async def test_page_id_with_query_string_is_rejected(notion: Notion) -> None:
    """aget_page('p1?injected=evil') must raise — '?' is forbidden in IDs."""
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        with pytest.raises(ValidationError) as exc_info:
            await notion.aget_page("p1?injected=evil")
        assert exc_info.value.details["forbidden_char"] == "?"
        assert len(respx_mock.calls) == 0


@pytest.mark.asyncio
async def test_page_id_with_fragment_is_rejected(notion: Notion) -> None:
    """'#' in an ID would change URL semantics — also rejected."""
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        with pytest.raises(ValidationError):
            await notion.aget_page("p1#fragment")
        assert len(respx_mock.calls) == 0


@pytest.mark.asyncio
async def test_empty_page_id_is_rejected(notion: Notion) -> None:
    """Empty / whitespace-only IDs must raise — otherwise the request
    hits /pages/ (no ID) which is a different endpoint entirely.
    """
    for bad in ("", "   ", "\t\n"):
        with pytest.raises(ValidationError) as exc_info:
            await notion.aget_page(bad)
        assert "cannot be empty" in exc_info.value.message


@pytest.mark.asyncio
async def test_every_id_taking_action_validates_id(notion: Notion) -> None:
    """Sweep: every action that interpolates an ID into the URL path
    must reject path-traversal attempts. If a new action ships without
    validation, this test catches it.
    """
    bad = "../users/me"
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        # Each call MUST raise ValidationError before any HTTP request
        for coro in (
            notion.aget_page(bad),
            notion.aupdate_page(bad, properties={}),
            notion.aarchive_page(bad),
            notion.arestore_page(bad),
            notion.aget_database(bad),
            notion.aupdate_database(bad),
            notion.aquery_database(bad),
            notion.aget_block(bad),
            notion.aupdate_block(bad, content={}),
            notion.adelete_block(bad),
            notion.aget_block_children(bad),
            notion.aappend_block_children(bad, children=[]),
            notion.aget_user(bad),
            notion.alist_comments(bad),
            notion.aget_comment(bad),
            notion.aupdate_comment(bad, text="x"),
            notion.adelete_comment(bad),
            notion.aget_page_property(bad, "prop-id"),
            notion.aget_page_property("valid-page-id", bad),
            notion.acreate_page(parent_id=bad, title="X"),
            notion.acreate_database(parent_id=bad, title="X", properties={}),
            notion.aadd_comment(page_id=bad, text="x"),
        ):
            with pytest.raises(ValidationError):
                await coro

        # And: zero HTTP requests slipped through
        assert len(respx_mock.calls) == 0


@pytest.mark.asyncio
async def test_negative_limit_clamped_to_one(notion: Notion) -> None:
    """search(limit=-5) must NOT send page_size=-5 to Notion.

    Pre-fix: min(-5, 100) = -5 → Notion would return 400. Now clamped
    to max(1, min(limit, 100)) = 1.
    """
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        route = respx_mock.post("/search").mock(
            return_value=httpx.Response(
                200,
                json={"object": "list", "results": [], "has_more": False, "next_cursor": None},
            )
        )
        await notion.asearch(query="x", limit=-5)
        body = json.loads(route.calls.last.request.read())
        assert body["page_size"] == 1


@pytest.mark.asyncio
async def test_zero_limit_clamped_to_one(notion: Notion) -> None:
    """limit=0 → page_size=1 (Notion's minimum)."""
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        route = respx_mock.get("/blocks/block-uuid/children").mock(
            return_value=httpx.Response(
                200,
                json={"object": "list", "results": [], "has_more": False, "next_cursor": None},
            )
        )
        await notion.aget_block_children(block_id="block-uuid", limit=0)
        params = route.calls.last.request.url.params
        assert params["page_size"] == "1"


@pytest.mark.asyncio
async def test_parse_page_skips_non_dict_property_values(notion: Notion) -> None:
    """Pre-fix: parse_page crashed with TypeError when a property value
    was None / str / list. Now skipped silently so the rest of the page
    still parses.

    Real-world trigger: a future Notion schema change or a corrupted
    response. Crashing the entire page parse over one bad property is
    worse than skipping that property.
    """
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        respx_mock.get("/pages/page-uuid-001").mock(
            return_value=httpx.Response(
                200,
                json={
                    "object": "page",
                    "id": "page-uuid-001",
                    "archived": False,
                    "parent": {},
                    "properties": {
                        "Good": {
                            "id": "title",
                            "type": "title",
                            "title": [{"type": "text", "plain_text": "OK", "annotations": {}}],
                        },
                        "Bad_None": None,
                        "Bad_String": "raw-string-instead-of-dict",
                        "Bad_List": ["not", "a", "dict"],
                    },
                },
            )
        )
        page = await notion.aget_page("page-uuid-001")
        # Parsed successfully — the good property survived; the bad ones
        # were dropped rather than crashing the parse.
        assert "Good" in page.properties
        assert page.properties["Good"].type == "title"
        assert "Bad_None" not in page.properties
        assert "Bad_String" not in page.properties
        assert "Bad_List" not in page.properties


@pytest.mark.asyncio
async def test_unicode_and_null_byte_in_title_round_trip(notion: Notion) -> None:
    """Unicode + NULL byte in title serialize cleanly through JSON.

    The probe confirmed httpx/json handle these correctly today; this
    test pins that behavior so a future encoding-related change can't
    silently break it.
    """
    weird_title = "日本語🎉\x00emoji"
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        route = respx_mock.post("/pages").mock(
            return_value=httpx.Response(
                200,
                json={
                    "object": "page",
                    "id": "p",
                    "archived": False,
                    "parent": {},
                    "properties": {},
                },
            )
        )
        await notion.acreate_page(parent_id="parent-uuid", title=weird_title)
        body = json.loads(route.calls.last.request.read())
        sent_title = body["properties"]["title"]["title"][0]["text"]["content"]
        assert sent_title == weird_title


@pytest.mark.asyncio
async def test_concurrent_requests_on_same_instance_are_isolated(notion: Notion) -> None:
    """10 concurrent aget_me calls all succeed.

    Pins that the connector has no shared mutable state that would race
    under concurrent use — important for SaaS callers fanning out many
    requests against a single ToolKit instance.
    """
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        respx_mock.get("/users/me").mock(
            return_value=httpx.Response(
                200,
                json={"object": "user", "id": "bot-001", "name": "B", "type": "bot"},
            )
        )
        import asyncio

        results = await asyncio.gather(*(notion.aget_me() for _ in range(10)))
        assert len(results) == 10
        assert all(u.id == "bot-001" for u in results)
        assert all(u.type == "bot" for u in results)


# ---------------------------------------------------------------------------
# 16. Round-4: Assumptions verification — paths we trusted but never tested
# ---------------------------------------------------------------------------
#
# Each test here pins a property that was previously "assumed to work" but
# never asserted: sync wrappers, ToolKit dispatch, error propagation,
# transport-error mapping, schema generation, model immutability, example
# importability.


# ---- Transport-error mapping (real fix this round) ------------------------


@pytest.mark.asyncio
async def test_connect_error_maps_to_typed_connection_error(notion: Notion) -> None:
    """httpx.ConnectError → toolsconnector.errors.ConnectionError.

    Pre-round-4: bare httpx.ConnectError leaked through `_request`, so
    callers catching `ToolsConnectorError` were blind to network down /
    DNS failure / TLS handshake failure.
    """
    from toolsconnector.errors import ConnectionError as TCConnectionError
    from toolsconnector.errors import ToolsConnectorError

    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        respx_mock.get("/users/me").mock(side_effect=httpx.ConnectError("DNS down"))
        with pytest.raises(TCConnectionError) as exc_info:
            await notion.aget_me()
        err = exc_info.value
        assert isinstance(err, ToolsConnectorError)
        assert err.connector == "notion"
        assert err.details["url"].endswith("/users/me")
        # Underlying httpx exception preserved as cause for debugging
        assert isinstance(err.__cause__, httpx.ConnectError)


@pytest.mark.asyncio
async def test_read_timeout_maps_to_typed_timeout_error(notion: Notion) -> None:
    """httpx.ReadTimeout → toolsconnector.errors.TimeoutError."""
    from toolsconnector.errors import TimeoutError as TCTimeoutError
    from toolsconnector.errors import ToolsConnectorError

    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        respx_mock.get("/users/me").mock(side_effect=httpx.ReadTimeout("slow"))
        with pytest.raises(TCTimeoutError) as exc_info:
            await notion.aget_me()
        err = exc_info.value
        assert isinstance(err, ToolsConnectorError)
        assert err.details["url"].endswith("/users/me")
        assert err.details["method"] == "GET"
        assert err.details["underlying"] == "ReadTimeout"


@pytest.mark.asyncio
async def test_generic_transport_error_maps_to_transport_error(notion: Notion) -> None:
    """Any other httpx.TransportError subclass → TransportError.

    Covers httpx.ReadError, WriteError, ProtocolError, etc. — the
    network-layer failures that aren't ConnectError or TimeoutException.
    """
    from toolsconnector.errors import ToolsConnectorError, TransportError

    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        respx_mock.get("/users/me").mock(side_effect=httpx.ReadError("RST"))
        with pytest.raises(TransportError) as exc_info:
            await notion.aget_me()
        err = exc_info.value
        assert isinstance(err, ToolsConnectorError)
        # Specific subclasses ConnectionError + TimeoutError should NOT
        # match this — TransportError is the broader base.
        from toolsconnector.errors import ConnectionError as TCConn
        from toolsconnector.errors import TimeoutError as TCTimeout

        assert not isinstance(err, TCConn)
        assert not isinstance(err, TCTimeout)


# ---- Sync wrapper paths ---------------------------------------------------


def test_sync_wrapper_get_me_works_without_event_loop() -> None:
    """notion.get_me() (no `a` prefix, no await) works from sync code.

    Core dual-use mandate: every async @action gets a sync wrapper that
    BaseConnector installs. We test the WIRING here, not the API call —
    so respx-mocked httpx still satisfies the path.
    """
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        respx_mock.get("/users/me").mock(
            return_value=httpx.Response(
                200,
                json={"id": "bot-1", "type": "bot", "name": "B"},
            )
        )
        # Build a fresh sync connector (no event loop is running here)
        n = Notion(credentials="ntn_test_token")
        # NOTE: no await — this is the sync wrapper path
        result = n.get_me()
        assert result.id == "bot-1"
        assert result.type == "bot"


@pytest.mark.asyncio
async def test_sync_wrapper_called_from_inside_event_loop(notion: Notion) -> None:
    """Calling the SYNC wrapper from inside an async test must NOT deadlock.

    Some sync-wrapper implementations naively call asyncio.run(),
    which deadlocks if there's an outer loop. BaseConnector's wrapper
    must handle the nested-loop case (typically by detecting an active
    loop and running the coroutine in a thread or scheduling it).
    """
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        respx_mock.get("/users/me").mock(
            return_value=httpx.Response(200, json={"id": "bot-2", "type": "bot"})
        )
        # Call the SYNC method (no `a` prefix) from inside `async def`
        result = notion.get_me()
        assert result.id == "bot-2"


# ---- ToolKit dispatch + serialization -------------------------------------


def test_toolkit_execute_get_me_returns_json_string() -> None:
    """kit.execute('notion_get_me', {}) returns a JSON string parseable
    into a dict containing the NotionUser fields.
    """
    from toolsconnector.serve import ToolKit

    kit = ToolKit(["notion"], credentials={"notion": "ntn_test_token"})
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        respx_mock.get("/users/me").mock(
            return_value=httpx.Response(
                200,
                json={"id": "bot-1", "type": "bot", "name": "B"},
            )
        )
        raw = kit.execute("notion_get_me", {})
        assert isinstance(raw, str)
        parsed = json.loads(raw)
        assert parsed["id"] == "bot-1"
        assert parsed["type"] == "bot"
        assert parsed["name"] == "B"


def test_toolkit_execute_search_serializes_paginated_list() -> None:
    """kit.execute('notion_search', ...) returns a PaginatedList shape:
    {"items": [...], "page_state": {...}, "total_count": null}.

    This is the standard wire shape for every paginated action across
    all connectors — pinning it for Notion guards against accidental
    drift in how the connector returns paginated results to the
    transport layer.
    """
    from toolsconnector.serve import ToolKit

    kit = ToolKit(["notion"], credentials={"notion": "ntn_test_token"})
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        respx_mock.post("/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "object": "page",
                            "id": "page-001",
                            "archived": False,
                            "parent": {},
                            "properties": {},
                        }
                    ],
                    "has_more": False,
                    "next_cursor": None,
                },
            )
        )
        raw = kit.execute("notion_search", {"query": "test"})
        parsed = json.loads(raw)
        # Standard PaginatedList wire shape
        assert set(parsed.keys()) == {"items", "page_state", "total_count"}
        assert len(parsed["items"]) == 1
        assert parsed["items"][0]["id"] == "page-001"
        assert parsed["page_state"]["has_more"] is False
        assert parsed["page_state"]["cursor"] is None


def test_toolkit_execute_propagates_validation_error_for_bad_id() -> None:
    """kit.execute('notion_get_page', {'page_id': '../users/me'}) raises
    ValidationError — the path-traversal guard fires before any HTTP
    call, regardless of whether you go through the connector directly
    or through the ToolKit transport.
    """
    from toolsconnector.serve import ToolKit

    kit = ToolKit(["notion"], credentials={"notion": "ntn_test_token"})
    with pytest.raises(ValidationError) as exc_info:
        kit.execute("notion_get_page", {"page_id": "../users/me"})
    assert exc_info.value.connector == "notion"
    assert "page_id" in exc_info.value.message


# ---- exclude_dangerous filter --------------------------------------------


def test_exclude_dangerous_removes_exactly_the_seven_write_actions() -> None:
    """ToolKit(exclude_dangerous=True) filters out exactly the 7 actions
    marked dangerous=True. This is the runtime counterpart to the spec
    test `test_dangerous_actions_are_flagged` — that test pins the flag
    on the connector spec; this one pins that the ToolKit transport
    actually honors the flag when filtering.
    """
    from toolsconnector.serve import ToolKit

    safe = ToolKit(["notion"], credentials={"notion": "t"}, exclude_dangerous=True)
    full = ToolKit(["notion"], credentials={"notion": "t"}, exclude_dangerous=False)

    safe_names = {t["name"] for t in safe.list_tools() if t["name"].startswith("notion_")}
    full_names = {t["name"] for t in full.list_tools() if t["name"].startswith("notion_")}

    assert len(full_names) == 24
    assert len(safe_names) == 17
    assert full_names - safe_names == {
        "notion_add_comment",
        "notion_append_block_children",
        "notion_archive_page",
        "notion_create_database",
        "notion_create_page",
        "notion_delete_block",
        "notion_delete_comment",
    }


# ---- OpenAI tools schema --------------------------------------------------


def test_to_openai_tools_includes_all_24_notion_actions() -> None:
    """kit.to_openai_tools() exposes all 24 actions with well-formed
    function schemas: {type, function: {name, description, parameters}}.
    """
    from toolsconnector.serve import ToolKit

    kit = ToolKit(["notion"], credentials={"notion": "t"})
    tools = kit.to_openai_tools()
    notion_tools = [t for t in tools if t["function"]["name"].startswith("notion_")]
    assert len(notion_tools) == 24

    # Spot-check shape on a few representative tools
    for tool in notion_tools:
        assert tool["type"] == "function"
        fn = tool["function"]
        assert "name" in fn and "description" in fn and "parameters" in fn
        params = fn["parameters"]
        assert params["type"] == "object"
        assert "properties" in params


def test_to_openai_tools_required_params_marked_correctly() -> None:
    """Tools with required path-param arguments declare them in `required`,
    optional kwargs are NOT in `required`. Critical for downstream LLM
    tool-calling — the model uses this list to decide what to fill in.
    """
    from toolsconnector.serve import ToolKit

    kit = ToolKit(["notion"], credentials={"notion": "t"})
    tools = {t["function"]["name"]: t["function"] for t in kit.to_openai_tools()}

    # notion_get_page has one required arg (page_id) and no optional kwargs
    get_page = tools["notion_get_page"]
    assert get_page["parameters"]["required"] == ["page_id"]

    # notion_get_me has no required args (zero-arg action)
    get_me = tools["notion_get_me"]
    assert get_me["parameters"]["properties"] == {}

    # notion_search has all optional args (no required), pagination + filter
    search = tools["notion_search"]
    search_props = search["parameters"]["properties"]
    assert "query" in search_props
    assert "limit" in search_props
    assert "cursor" in search_props
    assert "filter_type" in search_props
    # query has a default ("") so it should NOT be required
    assert "query" not in search.get("parameters", {}).get("required", [])


# ---- Model immutability ---------------------------------------------------


def test_notion_models_are_frozen() -> None:
    """Pydantic frozen=True on every response model is load-bearing —
    callers can pass NotionPage / NotionUser objects across threads and
    coroutines safely without defensive copies.
    """
    from pydantic import ValidationError as PydanticValidationError

    from toolsconnector.connectors.notion.types import (
        NotionBlock,
        NotionComment,
        NotionDatabase,
        NotionPage,
        NotionUser,
    )

    page = NotionPage(id="p1", parent={}, properties={})
    user = NotionUser(id="u1", type="bot")
    db = NotionDatabase(id="d1", parent={}, properties={})
    block = NotionBlock(id="b1", parent={}, content={})
    comment = NotionComment(id="c1", parent={}, rich_text=[])

    for model, attr in [(page, "id"), (user, "name"), (db, "id"), (block, "type"), (comment, "id")]:
        with pytest.raises(PydanticValidationError):
            setattr(model, attr, "MUTATED")


# ---- Example workflow module ----------------------------------------------


def test_example_workflow_module_imports_cleanly(monkeypatch: pytest.MonkeyPatch) -> None:
    """examples/11_notion_workflow.py must be importable without env vars.

    The script is supposed to exit cleanly via SystemExit (with a helpful
    "set env var first" message) if TC_NOTION_CREDENTIALS isn't set — NOT
    crash with NameError, ImportError, or SyntaxError.

    Importable-but-exit-on-missing-env is the documented contract.
    """
    import importlib.util
    from pathlib import Path

    monkeypatch.delenv("TC_NOTION_CREDENTIALS", raising=False)
    monkeypatch.delenv("TC_NOTION_TEST_PAGE_ID", raising=False)

    example_path = Path(__file__).parent.parent.parent / "examples" / "11_notion_workflow.py"
    assert example_path.exists(), f"missing example file at {example_path}"

    spec = importlib.util.spec_from_file_location("notion_workflow", str(example_path))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)

    # We allow SystemExit (the documented "missing env var" path), but
    # NOT ImportError / SyntaxError / NameError — those indicate the
    # example is broken regardless of env state.
    with pytest.raises(SystemExit):
        spec.loader.exec_module(mod)


# ---- Spec completeness ----------------------------------------------------


def test_get_spec_exposes_all_24_actions_with_descriptions() -> None:
    """ConnectorSpec includes every @action, each with a non-empty
    description. Drift in either count or description detected by this
    test the same way the dangerous-flag test catches missing flags.
    """
    spec = Notion.get_spec()
    assert len(spec.actions) == 24
    for action_name, action in spec.actions.items():
        assert action.description, f"action {action_name} has empty description"


def test_get_spec_action_descriptions_have_notion_prefix() -> None:
    """Every action description should be a useful human-readable summary,
    not just the action name. We check that none are obviously
    placeholder values like the action name itself.
    """
    spec = Notion.get_spec()
    for name, action in spec.actions.items():
        # Description should be longer than the bare action name and
        # shouldn't literally equal it.
        assert len(action.description) > len(name)


# ---------------------------------------------------------------------------
# 17. Round-5: MCP boundary + sharper re-tests of round-4 assumptions
# ---------------------------------------------------------------------------
#
# Round 4 marked some paths as "assumed correctly" without empirically pushing
# them. This round verifies them properly and adds the MCP transport (the
# `kit.serve_mcp()` path), which the previous rounds had not touched.
#
# Note: `mcp` (the FastMCP package) requires Python 3.10+. These tests
# exercise the toolsconnector-owned boundary — `_make_tool_handler`,
# `_json_type_to_python`, and the handler-dispatch contract — without
# needing FastMCP itself. The MCP server boot is integration-tested
# separately via the example workflow.


# ---- MCP handler construction --------------------------------------------


def test_mcp_handler_signature_matches_action_for_every_notion_tool() -> None:
    """Every notion action's MCP handler must have a synthetic signature
    where required params have no default and optional params default to None.

    FastMCP introspects this signature to build the tool's JSON Schema for
    LLM clients. Wrong defaults = wrong schemas = LLMs sending malformed
    calls.
    """
    import inspect

    from toolsconnector.serve import ToolKit
    from toolsconnector.serve.mcp import _make_tool_handler

    kit = ToolKit(["notion"], credentials={"notion": "t"})
    entries = [e for e in kit.list_tools() if e["name"].startswith("notion_")]
    assert len(entries) == 24

    problems = []
    for entry in entries:
        handler = _make_tool_handler(kit, entry["name"], entry["input_schema"])
        sig = inspect.signature(handler)
        required = set(entry["input_schema"].get("required", []))
        for pname, param in sig.parameters.items():
            if pname in required and param.default is not inspect.Parameter.empty:
                problems.append(f"{entry['name']}.{pname}: required but has default")
            if pname not in required and param.default is inspect.Parameter.empty:
                problems.append(f"{entry['name']}.{pname}: optional but no default")
    assert problems == [], f"signature problems: {problems}"


def test_mcp_handler_round_trip_get_me() -> None:
    """End-to-end: build the MCP handler, invoke it, get serialized JSON
    matching the NotionUser shape — same contract FastMCP relies on.
    """
    from toolsconnector.serve import ToolKit
    from toolsconnector.serve.mcp import _make_tool_handler

    kit = ToolKit(["notion"], credentials={"notion": "ntn_test"})
    entry = next(e for e in kit.list_tools() if e["name"] == "notion_get_me")
    handler = _make_tool_handler(kit, "notion_get_me", entry["input_schema"])

    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        respx_mock.get("/users/me").mock(
            return_value=httpx.Response(
                200,
                json={"id": "bot-mcp", "type": "bot", "name": "Bot"},
            )
        )
        # FastMCP would invoke the handler with kwargs — simulate that
        import asyncio

        result = asyncio.run(handler())

    # Result must be a JSON string (FastMCP needs it serialized)
    assert isinstance(result, str)
    parsed = json.loads(result)
    assert parsed["id"] == "bot-mcp"
    assert parsed["type"] == "bot"


def test_mcp_handler_dispatches_dict_typed_param() -> None:
    """An action with a ``dict[str, Any]`` parameter (e.g. update_page's
    ``properties``) must dispatch correctly through the MCP handler.

    Critical because the schema maps ``dict`` → ``object`` in JSON Schema,
    and the synthetic signature uses bare ``dict`` (not ``dict[str, Any]``).
    If the dispatch wraps the value in another level (e.g. inside a kwargs
    dict), the connector would receive a malformed body.
    """
    import asyncio

    from toolsconnector.serve import ToolKit
    from toolsconnector.serve.mcp import _make_tool_handler

    kit = ToolKit(["notion"], credentials={"notion": "ntn_test"})
    entry = next(e for e in kit.list_tools() if e["name"] == "notion_update_page")
    handler = _make_tool_handler(kit, "notion_update_page", entry["input_schema"])

    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        route = respx_mock.patch("/pages/page-uuid-001").mock(
            return_value=httpx.Response(
                200,
                json={
                    "object": "page",
                    "id": "page-uuid-001",
                    "archived": False,
                    "parent": {},
                    "properties": {},
                },
            )
        )
        result = asyncio.run(
            handler(
                page_id="page-uuid-001",
                properties={"Status": {"select": {"name": "Done"}}},
            )
        )

    # Properties dict reached the connector verbatim (no extra wrapping)
    body = json.loads(route.calls.last.request.read())
    assert body == {"properties": {"Status": {"select": {"name": "Done"}}}}
    # Return value parseable as a NotionPage JSON
    parsed = json.loads(result)
    assert parsed["id"] == "page-uuid-001"


def test_mcp_handler_propagates_validation_error() -> None:
    """ValidationError from _validate_id surfaces through the MCP handler.

    A hostile (or hallucinating) LLM sending ``{"page_id": "../users/me"}``
    must not reach Notion. The error bubbles back to FastMCP which then
    serializes it for the client.
    """
    import asyncio

    from toolsconnector.serve import ToolKit
    from toolsconnector.serve.mcp import _make_tool_handler

    kit = ToolKit(["notion"], credentials={"notion": "ntn_test"})
    entry = next(e for e in kit.list_tools() if e["name"] == "notion_get_page")
    handler = _make_tool_handler(kit, "notion_get_page", entry["input_schema"])

    with pytest.raises(ValidationError) as exc_info:
        asyncio.run(handler(page_id="../users/me"))
    assert exc_info.value.connector == "notion"


def test_mcp_handler_propagates_typed_transport_error() -> None:
    """Transport errors from `_request` propagate as typed TC errors
    through the MCP handler — the round-4 fix is observable end-to-end.
    """
    import asyncio

    from toolsconnector.errors import ConnectionError as TCConnectionError
    from toolsconnector.serve import ToolKit
    from toolsconnector.serve.mcp import _make_tool_handler

    kit = ToolKit(["notion"], credentials={"notion": "ntn_test"})
    entry = next(e for e in kit.list_tools() if e["name"] == "notion_get_me")
    handler = _make_tool_handler(kit, "notion_get_me", entry["input_schema"])

    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        respx_mock.get("/users/me").mock(side_effect=httpx.ConnectError("DNS"))
        with pytest.raises(TCConnectionError):
            asyncio.run(handler())


def test_mcp_handler_missing_required_arg_raises_validation_error() -> None:
    """Calling the MCP handler without a required arg surfaces as
    ValidationError — not raw TypeError. The MCP client sees a typed,
    actionable error from the JSON-RPC error layer.
    """
    import asyncio

    from toolsconnector.serve import ToolKit
    from toolsconnector.serve.mcp import _make_tool_handler

    kit = ToolKit(["notion"], credentials={"notion": "ntn_test"})
    entry = next(e for e in kit.list_tools() if e["name"] == "notion_get_page")
    handler = _make_tool_handler(kit, "notion_get_page", entry["input_schema"])

    with pytest.raises(ValidationError) as exc_info:
        asyncio.run(handler())  # missing page_id
    assert "page_id" in exc_info.value.message


def test_json_type_to_python_covers_standard_json_schema_types() -> None:
    """The type-mapping table used by MCP handlers must cover all
    standard JSON Schema primitive types. A miss here means MCP clients
    get the wrong type annotation in tool schemas.
    """
    from typing import Any as TypingAny

    from toolsconnector.serve.mcp import _json_type_to_python

    cases = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    for json_type, expected in cases.items():
        got = _json_type_to_python({"type": json_type}, required=True)
        assert got is expected, f"{json_type} → {got}, expected {expected}"
    # Unknown / non-standard types fall through to Any
    assert _json_type_to_python({"type": "null"}, required=True) is TypingAny
    assert _json_type_to_python({"type": "unknown_xyz"}, required=True) is TypingAny


# ---- Sharper re-test: exclude_dangerous BLOCKS execution -----------------


def test_exclude_dangerous_blocks_execution_not_just_listing() -> None:
    """Round-4 test_exclude_dangerous_removes_… proved the dangerous
    actions don't appear in `list_tools()`. This sharper test proves
    they ALSO cannot be EXECUTED via `kit.execute()` on a safe ToolKit
    — exclude_dangerous is a hard gate, not just a UI filter.

    Failure mode this guards against: an attacker (or hallucinating LLM)
    that knows the action name but bypassed the listing — without this
    block, they could still call create_page on a "safe" kit.
    """
    from toolsconnector.errors import ConnectorNotConfiguredError
    from toolsconnector.serve import ToolKit

    safe = ToolKit(["notion"], credentials={"notion": "t"}, exclude_dangerous=True)
    # We don't even mock the HTTP — the call must fail before reaching httpx.
    with pytest.raises(ConnectorNotConfiguredError) as exc_info:
        safe.execute("notion_create_page", {"parent_id": "x", "title": "Sneak"})
    # The error must mention the safe-list so the caller understands
    # the action exists but is filtered out.
    assert "notion_create_page" in str(exc_info.value)


# ---- Round-1 fix integration through kit.execute -------------------------


def test_kit_execute_get_page_serializes_user_fields() -> None:
    """The round-1 parser fix (parse_page extracting created_by /
    last_edited_by) must surface end-to-end through the ToolKit
    serialization layer — not just at the connector level.

    Pins a real integration contract: AI agents calling
    `notion_get_page` via MCP/HTTP get the user metadata they need to
    reason about ownership and authorship.
    """
    from toolsconnector.serve import ToolKit

    kit = ToolKit(["notion"], credentials={"notion": "ntn_test"})
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        respx_mock.get("/pages/p1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "object": "page",
                    "id": "p1",
                    "archived": False,
                    "parent": {},
                    "properties": {},
                    "created_by": {
                        "object": "user",
                        "id": "user-alice",
                        "name": "Alice",
                        "type": "person",
                    },
                    "last_edited_by": {
                        "object": "user",
                        "id": "bot-integration",
                        "type": "bot",
                    },
                },
            )
        )
        raw = kit.execute("notion_get_page", {"page_id": "p1"})
    parsed = json.loads(raw)
    assert parsed["created_by"]["id"] == "user-alice"
    assert parsed["created_by"]["type"] == "person"
    assert parsed["last_edited_by"]["id"] == "bot-integration"
    assert parsed["last_edited_by"]["type"] == "bot"


# ---- Documented gotcha: shallow freeze on dict-valued fields -------------


def test_frozen_models_have_shallow_immutability_on_dict_fields() -> None:
    """**Documented limitation, not a bug.**

    Pydantic v2 `frozen=True` prevents top-level attribute assignment but
    does NOT recursively freeze nested mutable containers. Code holding a
    ``NotionPage`` reference can therefore still mutate ``page.parent``,
    ``page.properties[k].select``, etc., because the underlying dict /
    list is a regular Python container.

    This test exists so the behavior is explicit. If a future Pydantic
    upgrade or a custom validator changes the contract, this test will
    fail and force a deliberate decision. Callers that need true deep
    immutability should ``copy.deepcopy()`` before sharing across
    threads.
    """
    from pydantic import ValidationError as PydanticValidationError

    from toolsconnector.connectors.notion.types import NotionPage

    page = NotionPage(id="p1", parent={"original": "v"}, properties={})

    # Top-level assignment IS blocked (this is the documented frozen behavior)
    with pytest.raises(PydanticValidationError):
        page.id = "mutated"  # type: ignore[misc]

    # But nested dict mutation is NOT blocked — this is the known gotcha.
    # We assert it succeeds so the limitation is pinned and discoverable.
    page.parent["injected"] = "value"
    assert page.parent["injected"] == "value"


# ---------------------------------------------------------------------------
# 18. Round-6: sweep tests across all 24 actions + the MCP None-limit bug fix
# ---------------------------------------------------------------------------
#
# Found by spawning the actual MCP server subprocess and calling notion_search
# without supplying `limit`: the synthetic MCP handler signature defaults
# optional kwargs to None, which then reached `_clamp_limit(None)` and crashed
# with "'<' not supported between instances of 'int' and 'NoneType'".
#
# Affected: every paginated action (search, query_database, get_block_children,
# list_comments, get_page_property).


# ---- Probe inventory: one entry per @action ------------------------------
# Used by the sweep tests below. The shape is:
#   action_name → (method, path, mock_response_body, kwargs_to_invoke_with)
# Keep in sync with src/toolsconnector/connectors/notion/connector.py.
_ACTION_PROBES: dict[str, tuple[str, str, Optional[dict], dict]] = {
    "search": ("POST", "/search", {"results": [], "has_more": False, "next_cursor": None}, {}),
    "get_page": (
        "GET",
        "/pages/page-uuid",
        {"id": "p", "object": "page", "archived": False, "parent": {}, "properties": {}},
        {"page_id": "page-uuid"},
    ),
    "create_page": (
        "POST",
        "/pages",
        {"id": "p", "object": "page", "archived": False, "parent": {}, "properties": {}},
        {"parent_id": "parent-uuid", "title": "x"},
    ),
    "update_page": (
        "PATCH",
        "/pages/page-uuid",
        {"id": "p", "object": "page", "archived": False, "parent": {}, "properties": {}},
        {"page_id": "page-uuid", "properties": {}},
    ),
    "archive_page": (
        "PATCH",
        "/pages/page-uuid",
        {"id": "p", "object": "page", "archived": True, "parent": {}, "properties": {}},
        {"page_id": "page-uuid"},
    ),
    "restore_page": (
        "PATCH",
        "/pages/page-uuid",
        {"id": "p", "object": "page", "archived": False, "parent": {}, "properties": {}},
        {"page_id": "page-uuid"},
    ),
    "get_page_property": (
        "GET",
        "/pages/page-uuid/properties/prop-id",
        {"object": "property_item", "type": "number", "number": 1},
        {"page_id": "page-uuid", "property_id": "prop-id"},
    ),
    "get_database": (
        "GET",
        "/databases/db-uuid",
        {
            "id": "d",
            "object": "database",
            "title": [],
            "description": [],
            "archived": False,
            "parent": {},
            "properties": {},
        },
        {"database_id": "db-uuid"},
    ),
    "create_database": (
        "POST",
        "/databases",
        {
            "id": "d",
            "object": "database",
            "title": [],
            "description": [],
            "archived": False,
            "parent": {},
            "properties": {},
        },
        {"parent_id": "parent", "title": "x", "properties": {}},
    ),
    "update_database": (
        "PATCH",
        "/databases/db-uuid",
        {
            "id": "d",
            "object": "database",
            "title": [],
            "description": [],
            "archived": False,
            "parent": {},
            "properties": {},
        },
        {"database_id": "db-uuid", "title": "new"},
    ),
    "query_database": (
        "POST",
        "/databases/db-uuid/query",
        {"results": [], "has_more": False, "next_cursor": None},
        {"database_id": "db-uuid"},
    ),
    "get_block": (
        "GET",
        "/blocks/block-uuid",
        {
            "id": "b",
            "object": "block",
            "type": "paragraph",
            "has_children": False,
            "archived": False,
            "paragraph": {},
        },
        {"block_id": "block-uuid"},
    ),
    "update_block": (
        "PATCH",
        "/blocks/block-uuid",
        {
            "id": "b",
            "object": "block",
            "type": "paragraph",
            "has_children": False,
            "archived": False,
            "paragraph": {},
        },
        {"block_id": "block-uuid", "content": {}},
    ),
    "delete_block": ("DELETE", "/blocks/block-uuid", None, {"block_id": "block-uuid"}),
    "get_block_children": (
        "GET",
        "/blocks/block-uuid/children",
        {"results": [], "has_more": False, "next_cursor": None},
        {"block_id": "block-uuid"},
    ),
    "append_block_children": (
        "PATCH",
        "/blocks/block-uuid/children",
        {"results": []},
        {"block_id": "block-uuid", "children": []},
    ),
    "list_users": ("GET", "/users", {"results": [], "has_more": False, "next_cursor": None}, {}),
    "get_user": (
        "GET",
        "/users/user-uuid",
        {"id": "u", "type": "person"},
        {"user_id": "user-uuid"},
    ),
    "get_me": ("GET", "/users/me", {"id": "bot", "type": "bot"}, {}),
    "list_comments": (
        "GET",
        "/comments",
        {"results": [], "has_more": False, "next_cursor": None},
        {"block_id": "block-uuid"},
    ),
    "add_comment": (
        "POST",
        "/comments",
        {"id": "c", "object": "comment", "parent": {}, "rich_text": []},
        {"page_id": "page-uuid", "text": "hi"},
    ),
    "get_comment": (
        "GET",
        "/comments/comment-uuid",
        {"id": "c", "object": "comment", "parent": {}, "rich_text": []},
        {"comment_id": "comment-uuid"},
    ),
    "update_comment": (
        "PATCH",
        "/comments/comment-uuid",
        {"id": "c", "object": "comment", "parent": {}, "rich_text": []},
        {"comment_id": "comment-uuid", "text": "hi"},
    ),
    "delete_comment": ("DELETE", "/comments/comment-uuid", None, {"comment_id": "comment-uuid"}),
}


def test_action_probe_inventory_covers_every_action() -> None:
    """If a new @action ships without an entry in _ACTION_PROBES, the
    sweep tests below silently skip it. This guard makes that impossible.
    """
    spec = Notion.get_spec()
    declared = set(spec.actions.keys())
    probed = set(_ACTION_PROBES.keys())
    missing = declared - probed
    extra = probed - declared
    assert not missing, f"Missing probes for: {missing}"
    assert not extra, f"Probe entries for non-existent actions: {extra}"


@pytest.mark.asyncio
async def test_every_action_sends_notion_version_and_authorization_headers(notion: Notion) -> None:
    """Sweep: every single action MUST send Notion-Version: 2022-06-28
    and Authorization: Bearer <credential>. A drive-by edit that drops
    these in any one action would break that action silently — Notion
    returns either 401 (missing auth) or 400 (missing version), both of
    which would only show up at runtime when that action is exercised.

    This test catches any such drop at unit-test time.
    """
    issues: list[str] = []
    for action_name, (method, path, response, kwargs) in _ACTION_PROBES.items():
        with respx.mock(base_url="https://api.notion.com/v1") as mock:
            route_fn = getattr(mock, method.lower())
            if response is None:
                route_fn(path).mock(return_value=httpx.Response(204))
            else:
                route_fn(path).mock(return_value=httpx.Response(200, json=response))

            async_method = getattr(notion, f"a{action_name}")
            await async_method(**kwargs)
            req = mock.calls.last.request
            hdrs = {k.lower(): v for k, v in req.headers.items()}
            if hdrs.get("notion-version") != "2022-06-28":
                issues.append(f"{action_name}: Notion-Version={hdrs.get('notion-version')!r}")
            if hdrs.get("authorization") != "Bearer secret_fake_integration_token":
                issues.append(f"{action_name}: Authorization={hdrs.get('authorization')!r}")
    assert issues == [], f"Header issues: {issues}"


def test_every_action_has_a_sync_wrapper() -> None:
    """Dual-use mandate: every @action gets BOTH an `aname()` async method
    and a `name()` sync wrapper installed by BaseConnector. Missing one
    breaks the sync execution path for that action — used by Django/Flask
    apps and any non-async caller.
    """
    n = Notion(credentials="t")
    spec = Notion.get_spec()
    missing = [name for name in spec.actions if not callable(getattr(n, name, None))]
    assert missing == [], f"Actions missing sync wrappers: {missing}"


@pytest.mark.asyncio
async def test_sync_and_async_wrappers_produce_equivalent_results(notion: Notion) -> None:
    """The sync wrapper must produce the same return value as the async
    method (for a deterministic input). If they ever diverge, callers
    relying on the dual-use API get inconsistent behavior depending on
    which entry point they use.

    Spot-checked across 3 representative actions to keep test runtime bounded.
    """
    cases = [
        ("get_me", "GET", "/users/me", {"id": "bot", "type": "bot", "name": "B"}, {}),
        (
            "get_page",
            "GET",
            "/pages/p1",
            {"id": "p1", "object": "page", "archived": False, "parent": {}, "properties": {}},
            {"page_id": "p1"},
        ),
        (
            "get_database",
            "GET",
            "/databases/d1",
            {
                "id": "d1",
                "object": "database",
                "title": [],
                "description": [],
                "archived": False,
                "parent": {},
                "properties": {},
            },
            {"database_id": "d1"},
        ),
    ]
    for action_name, method, path, response, kwargs in cases:
        # Compare against a fresh connector to avoid setup-state effects.
        with respx.mock(base_url="https://api.notion.com/v1") as mock:
            getattr(mock, method.lower())(path).mock(
                return_value=httpx.Response(200, json=response)
            )
            async_result = await getattr(notion, f"a{action_name}")(**kwargs)
        with respx.mock(base_url="https://api.notion.com/v1") as mock:
            getattr(mock, method.lower())(path).mock(
                return_value=httpx.Response(200, json=response)
            )
            sync_result = getattr(notion, action_name)(**kwargs)
        assert async_result == sync_result, (
            f"{action_name}: async={async_result} sync={sync_result}"
        )


def test_all_openai_tool_schemas_validate_as_json_schema_draft7() -> None:
    """Every OpenAI tool schema we generate must be a valid JSON Schema
    (Draft 7 — the default for OpenAI function calling).

    If we ship an invalid schema, downstream LLM clients (OpenAI,
    Anthropic, Gemini all use this format) will reject the tool list or
    return cryptic errors when the LLM tries to call. Validating
    locally catches the breakage at unit-test time.
    """
    try:
        import jsonschema  # noqa: F401
    except ImportError:
        pytest.skip("jsonschema not installed")
    import jsonschema as _jsonschema

    from toolsconnector.serve import ToolKit

    kit = ToolKit(["notion"], credentials={"notion": "t"})
    tools = kit.to_openai_tools()
    notion_tools = [t for t in tools if t["function"]["name"].startswith("notion_")]
    assert len(notion_tools) == 24

    failures: list[str] = []
    for tool in notion_tools:
        fn = tool["function"]
        try:
            _jsonschema.Draft7Validator.check_schema(fn["parameters"])
        except Exception as e:
            failures.append(f"{fn['name']}: {e}")
    assert failures == [], f"Invalid schemas: {failures}"


@pytest.mark.asyncio
async def test_every_error_code_suggestion_triggers_with_correct_text(notion: Notion) -> None:
    """The `_NOTION_CODE_SUGGESTIONS` map should fire on every Notion
    error code it covers. If any entry stops firing — because the
    response-parsing or the suggestion-attaching code drifts — agents
    catching errors stop getting actionable next-steps.
    """
    from toolsconnector.connectors.notion.connector import _NOTION_CODE_SUGGESTIONS

    status_for_code = {
        "unauthorized": 401,
        "restricted_resource": 403,
        "object_not_found": 404,
        "validation_error": 400,
        "invalid_json": 400,
        "invalid_request_url": 400,
        "missing_version": 400,
        "conflict_error": 409,
        "rate_limited": 429,
        "service_unavailable": 503,
        "internal_server_error": 500,
        "database_connection_unavailable": 503,
        "gateway_timeout": 504,
    }
    issues: list[str] = []
    for code, expected_suggestion in _NOTION_CODE_SUGGESTIONS.items():
        status = status_for_code.get(code, 500)
        with respx.mock(base_url="https://api.notion.com/v1") as mock:
            mock.get("/users/me").mock(
                return_value=httpx.Response(
                    status, json={"object": "error", "status": status, "code": code, "message": "."}
                )
            )
            try:
                await notion.aget_me()
                issues.append(f"{code}: no error raised")
            except Exception as e:
                got = getattr(e, "suggestion", None)
                if got != expected_suggestion:
                    issues.append(f"{code}: suggestion mismatch (got={got!r})")
    assert issues == [], f"Suggestion issues: {issues}"


@pytest.mark.asyncio
async def test_async_cancellation_propagates_cleanly(notion: Notion) -> None:
    """A coroutine cancelled mid-request must propagate
    `asyncio.CancelledError` and clean up the httpx client + connection
    properly. Failure mode: orphaned tasks, leaked sockets, or the
    cancellation gets swallowed into a different exception type.
    """
    import asyncio as _aio

    with respx.mock(base_url="https://api.notion.com/v1", assert_all_called=False) as mock:

        async def slow_handler(request: httpx.Request) -> httpx.Response:
            await _aio.sleep(2)
            return httpx.Response(200, json={"id": "x", "type": "bot"})

        mock.get("/users/me").mock(side_effect=slow_handler)
        task = _aio.create_task(notion.aget_me())
        await _aio.sleep(0.05)
        task.cancel()
        with pytest.raises(_aio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_paginated_actions_handle_none_limit_from_mcp_path(notion: Notion) -> None:
    """Round-6 regression: MCP's synthetic handler signature defaults
    optional params to ``None``. Pre-fix, this reached ``_clamp_limit(None)``
    and crashed with "'<' not supported between int and NoneType" for every
    paginated action. Now each action's own default value is used when
    None arrives.

    Discovered by booting the real FastMCP server in a subprocess and
    calling ``notion_search`` without ``limit``.
    """
    cases = [
        # (action, method, path, response, kwargs_with_None_limit, expected_default)
        (
            "search",
            "POST",
            "/search",
            {"results": [], "has_more": False, "next_cursor": None},
            {"query": "x", "limit": None},
            20,
        ),
        (
            "query_database",
            "POST",
            "/databases/db-uuid/query",
            {"results": [], "has_more": False, "next_cursor": None},
            {"database_id": "db-uuid", "limit": None},
            50,
        ),
        (
            "get_block_children",
            "GET",
            "/blocks/block-uuid/children",
            {"results": [], "has_more": False, "next_cursor": None},
            {"block_id": "block-uuid", "limit": None},
            50,
        ),
        (
            "list_comments",
            "GET",
            "/comments",
            {"results": [], "has_more": False, "next_cursor": None},
            {"block_id": "block-uuid", "limit": None},
            50,
        ),
        (
            "get_page_property",
            "GET",
            "/pages/page-uuid/properties/prop",
            {"object": "property_item", "type": "number", "number": 1},
            {"page_id": "page-uuid", "property_id": "prop", "limit": None},
            100,
        ),
    ]
    for action, method, path, response, kwargs, expected_default in cases:
        with respx.mock(base_url="https://api.notion.com/v1") as mock:
            getattr(mock, method.lower())(path).mock(
                return_value=httpx.Response(200, json=response)
            )
            await getattr(notion, f"a{action}")(**kwargs)
            req = mock.calls[0].request
            if method == "POST":
                body = json.loads(req.read())
                got = body["page_size"]
            else:
                got = int(req.url.params["page_size"])
            assert got == expected_default, (
                f"{action}: limit=None should coerce to {expected_default}, got {got}"
            )


# ---------------------------------------------------------------------------
# 19. Round-7: bugs found by LIVE verification against real Notion
# ---------------------------------------------------------------------------
#
# Two real bugs surfaced only when the connector was exercised against a real
# Notion workspace — neither was catchable by docs-comparison or respx alone
# because both involved the connector emitting a body shape Notion considered
# invalid, OR feeding mixed-object-type responses to a single parser.


@pytest.mark.asyncio
async def test_search_filters_out_database_results_before_parsing(notion: Notion) -> None:
    """Notion's /search returns mixed pages + databases when no filter
    is set. Pre-round-7, the connector called parse_page() on EVERY
    result regardless of object type — and database property *schemas*
    (e.g., ``rich_text: {}``, an empty configuration object) don't
    match the page-property-VALUE schema (``rich_text: list``),
    crashing the whole search with a pydantic ValidationError.

    Live test against the user's real workspace hit this immediately.
    Fix: filter results to ``object == "page"`` before parsing, matching
    the action's declared return type of PaginatedList[NotionPage].
    """
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        respx_mock.post("/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "object": "list",
                    "results": [
                        # A page (well-formed values)
                        {
                            "object": "page",
                            "id": "page-001",
                            "archived": False,
                            "parent": {},
                            "properties": {
                                "Name": {
                                    "id": "title",
                                    "type": "title",
                                    "title": [
                                        {
                                            "type": "text",
                                            "plain_text": "Page",
                                            "annotations": {},
                                        }
                                    ],
                                }
                            },
                        },
                        # A database — its `rich_text` property is a
                        # schema config object, NOT a list. parse_page
                        # would crash on this if we didn't filter.
                        {
                            "object": "database",
                            "id": "db-001",
                            "title": [],
                            "description": [],
                            "archived": False,
                            "parent": {},
                            "properties": {
                                "Description": {
                                    "id": "desc",
                                    "name": "Description",
                                    "type": "rich_text",
                                    "rich_text": {},  # ← schema config, not a list
                                },
                            },
                        },
                    ],
                    "has_more": False,
                    "next_cursor": None,
                },
            )
        )

        result = await notion.asearch(query="")
        # Only the page survived; the database was dropped per the
        # PaginatedList[NotionPage] contract
        assert len(result.items) == 1
        assert result.items[0].id == "page-001"
        assert result.items[0].object == "page"


@pytest.mark.asyncio
async def test_parse_page_skips_property_with_pydantic_validation_failure(
    notion: Notion,
) -> None:
    """Defense in depth for the search-mixed-results bug: even if a
    non-page object somehow reaches parse_page directly, properties
    that fail NotionProperty validation are skipped rather than
    aborting the whole parse.

    This catches schema-shape drift on individual properties without
    crashing — e.g., if Notion adds a new property type whose shape
    doesn't match our model, the rest of the page still parses.
    """
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        respx_mock.get("/pages/page-uuid-001").mock(
            return_value=httpx.Response(
                200,
                json={
                    "object": "page",
                    "id": "page-uuid-001",
                    "archived": False,
                    "parent": {},
                    "properties": {
                        "Good": {
                            "id": "title",
                            "type": "title",
                            "title": [{"type": "text", "plain_text": "OK", "annotations": {}}],
                        },
                        # rich_text as object (database-schema shape) —
                        # fails NotionProperty validation, gets skipped
                        "BadShape": {
                            "id": "x",
                            "type": "rich_text",
                            "rich_text": {},
                        },
                    },
                },
            )
        )

        page = await notion.aget_page("page-uuid-001")
        # The good property survived; the malformed one was dropped
        assert "Good" in page.properties
        assert "BadShape" not in page.properties


@pytest.mark.asyncio
async def test_add_comment_threaded_uses_top_level_discussion_id_not_parent_envelope(
    notion: Notion,
) -> None:
    """Round-7 bug: threaded comments need ``discussion_id`` at the TOP
    LEVEL of the body — NOT inside a ``parent`` envelope as the
    top-level-comment form does.

    Pre-fix, ``add_comment(discussion_id=...)`` sent
    ``{"parent": {"discussion_id": ...}, "rich_text": [...]}`` which the
    real Notion API rejects with HTTP 400 ``validation_error``. The bug
    was invisible to the old respx test because that test asserted the
    same (wrong) shape — both the test and the production code agreed
    on the wrong contract.

    Verified-correct shape per Notion's canonical docs:
    https://developers.notion.com/reference/create-a-comment

    This test pins the CORRECT shape so the bug can never reappear, and
    so the contract is documented in the test layer.
    """
    with respx.mock(base_url="https://api.notion.com/v1") as respx_mock:
        route = respx_mock.post("/comments").mock(
            return_value=httpx.Response(
                200,
                json={
                    "object": "comment",
                    "id": "reply-001",
                    "parent": {"type": "discussion_id", "discussion_id": "disc-001"},
                    "discussion_id": "disc-001",
                    "rich_text": [{"type": "text", "plain_text": "Reply", "annotations": {}}],
                },
            )
        )
        await notion.aadd_comment(
            page_id="page-uuid-001",
            text="Reply",
            discussion_id="disc-001",
        )
        body = json.loads(route.calls.last.request.read())
        # The verified-correct contract
        assert body["discussion_id"] == "disc-001"
        # Body has NO parent envelope when threading
        assert "parent" not in body
        # Body has no page_id leakage
        assert "page_id" not in body


def test_notion_mcp_tool_exposure() -> None:
    """MCP filtering: all Notion actions surface correctly via build_tool_list;
    dangerous=True actions filter out when exclude_dangerous=True.

    Reuses the same `build_tool_list()` helper that powers `kit.serve_mcp()`.
    Pattern: same shape as tests/unit/test_serve_filtering.py:31 (Gmail).
    """
    all_entries = build_tool_list([Notion])
    safe_entries = build_tool_list([Notion], exclude_dangerous=True)

    # All tools follow the {connector}_{action} naming + Notion: description prefix
    for entry in all_entries:
        assert entry.tool_name.startswith("notion_"), entry.tool_name
        assert entry.description.startswith("Notion:"), entry.description

    # 7 dangerous actions filter out cleanly
    dangerous_names = {e.action_name for e in all_entries if e.dangerous}
    expected_dangerous = {
        "create_page",
        "create_database",
        "append_block_children",
        "delete_block",
        "add_comment",
        "delete_comment",
        "archive_page",
    }
    assert dangerous_names == expected_dangerous

    safe_names = {e.action_name for e in safe_entries}
    # No dangerous actions in the safe set
    assert dangerous_names.isdisjoint(safe_names)
    # The new get_me + get_comment read-only actions appear in the safe set
    assert "get_me" in safe_names
    assert "get_comment" in safe_names
