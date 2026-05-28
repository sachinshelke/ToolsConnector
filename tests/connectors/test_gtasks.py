"""End-to-end tests for the Google Tasks connector using respx.

Pinned to Tasks API v1 at ``tasks.googleapis.com/tasks/v1``. Auth is
OAuth 2.0 bearer (`Authorization: Bearer ya29.…`).

Structure (5 rounds):
  Round 1 — happy path for all 13 actions
  Round 2 — defensive parsing + URL-path guards
  Round 3 — error matrix (401/403/404/429/500)
  Round 4 — transport errors
  Round 5 — MCP + OpenAI schema + dangerous flag + sync wrappers
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
import pytest_asyncio
import respx

from toolsconnector.connectors.gtasks import GoogleTasks
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


@pytest_asyncio.fixture
async def gt() -> GoogleTasks:
    yield GoogleTasks(credentials="ya29.fake_test_token")


_LIST = {"id": "list-abc", "title": "My Tasks", "updated": "2026-05-28T12:00:00Z"}
_TASK = {
    "id": "task-1",
    "title": "Buy groceries",
    "notes": "Milk, bread, eggs",
    "status": "needsAction",
    "due": "2026-06-01T00:00:00Z",
    "position": "00000000000000000000",
    "links": [],
}


# ===========================================================================
# Round 1 — happy path × 13 actions
# ===========================================================================


@pytest.mark.asyncio
async def test_list_task_lists(gt: GoogleTasks) -> None:
    """list_task_lists: GET /users/@me/lists → PaginatedList[TaskList]."""
    with respx.mock(base_url="https://tasks.googleapis.com/tasks/v1") as mock:
        mock.get("/users/@me/lists").mock(
            return_value=httpx.Response(200, json={"items": [_LIST], "nextPageToken": "tok-2"})
        )
        page = await gt.alist_task_lists(limit=10)
        assert len(page.items) == 1
        assert page.items[0].id == "list-abc"
        assert page.page_state.cursor == "tok-2"


@pytest.mark.asyncio
async def test_get_task_list(gt: GoogleTasks) -> None:
    """get_task_list: GET /users/@me/lists/{id}."""
    with respx.mock(base_url="https://tasks.googleapis.com/tasks/v1") as mock:
        route = mock.get("/users/@me/lists/list-abc").mock(
            return_value=httpx.Response(200, json=_LIST)
        )
        tl = await gt.aget_task_list(task_list_id="list-abc")
        assert tl.id == "list-abc"
        assert tl.title == "My Tasks"
        # Bearer auth applied
        assert route.calls.last.request.headers["authorization"] == "Bearer ya29.fake_test_token"


@pytest.mark.asyncio
async def test_create_task_list(gt: GoogleTasks) -> None:
    """create_task_list: POST /users/@me/lists with title."""
    with respx.mock(base_url="https://tasks.googleapis.com/tasks/v1") as mock:
        route = mock.post("/users/@me/lists").mock(
            return_value=httpx.Response(200, json={**_LIST, "title": "New"})
        )
        tl = await gt.acreate_task_list(title="New")
        assert tl.title == "New"
        body = route.calls.last.request.read()
        assert b'"title":"New"' in body


@pytest.mark.asyncio
async def test_delete_task_list(gt: GoogleTasks) -> None:
    """delete_task_list: DELETE /users/@me/lists/{id} → None."""
    with respx.mock(base_url="https://tasks.googleapis.com/tasks/v1") as mock:
        mock.delete("/users/@me/lists/list-abc").mock(return_value=httpx.Response(204))
        result = await gt.adelete_task_list(task_list_id="list-abc")
        assert result is None


@pytest.mark.asyncio
async def test_update_task_list(gt: GoogleTasks) -> None:
    """update_task_list: PUT /users/@me/lists/{id} with new title.

    Note: PUT semantics, not PATCH — the Tasks API expects a full resource
    body even though title is the only mutable field on a task list.
    """
    with respx.mock(base_url="https://tasks.googleapis.com/tasks/v1") as mock:
        route = mock.put("/users/@me/lists/list-abc").mock(
            return_value=httpx.Response(200, json={**_LIST, "title": "Renamed"})
        )
        tl = await gt.aupdate_task_list(task_list_id="list-abc", title="Renamed")
        assert tl.title == "Renamed"
        body = route.calls.last.request.read()
        assert b'"title":"Renamed"' in body


@pytest.mark.asyncio
async def test_list_tasks_with_filters(gt: GoogleTasks) -> None:
    """list_tasks: GET /lists/{id}/tasks with completed/dueMin/dueMax/showHidden filters."""
    with respx.mock(base_url="https://tasks.googleapis.com/tasks/v1") as mock:
        route = mock.get("/lists/list-abc/tasks").mock(
            return_value=httpx.Response(200, json={"items": [_TASK]})
        )
        page = await gt.alist_tasks(
            task_list_id="list-abc",
            completed=False,
            due_min="2026-06-01T00:00:00Z",
            due_max="2026-06-30T23:59:59Z",
            show_hidden=False,
        )
        assert len(page.items) == 1
        params = dict(route.calls.last.request.url.params)
        assert params["showCompleted"] == "false"
        assert params["dueMin"] == "2026-06-01T00:00:00Z"
        assert params["showHidden"] == "false"


@pytest.mark.asyncio
async def test_get_task(gt: GoogleTasks) -> None:
    """get_task: GET /lists/{listId}/tasks/{taskId}."""
    with respx.mock(base_url="https://tasks.googleapis.com/tasks/v1") as mock:
        mock.get("/lists/list-abc/tasks/task-1").mock(return_value=httpx.Response(200, json=_TASK))
        t = await gt.aget_task(task_list_id="list-abc", task_id="task-1")
        assert t.id == "task-1"
        assert t.title == "Buy groceries"
        assert t.status == "needsAction"


@pytest.mark.asyncio
async def test_create_task(gt: GoogleTasks) -> None:
    """create_task: POST /lists/{id}/tasks with title/notes/due."""
    with respx.mock(base_url="https://tasks.googleapis.com/tasks/v1") as mock:
        route = mock.post("/lists/list-abc/tasks").mock(
            return_value=httpx.Response(200, json=_TASK)
        )
        t = await gt.acreate_task(
            task_list_id="list-abc",
            title="New task with unicode 你好",
            notes="Detailed notes",
            due="2026-06-01T00:00:00Z",
        )
        assert t.id == "task-1"
        body = route.calls.last.request.read()
        assert "你好".encode() in body
        assert b'"notes":"Detailed notes"' in body
        assert b'"due":"2026-06-01T00:00:00Z"' in body


@pytest.mark.asyncio
async def test_update_task_patch_semantics(gt: GoogleTasks) -> None:
    """update_task uses PATCH; only provided fields appear in body."""
    with respx.mock(base_url="https://tasks.googleapis.com/tasks/v1") as mock:
        route = mock.patch("/lists/list-abc/tasks/task-1").mock(
            return_value=httpx.Response(200, json={**_TASK, "title": "Updated"})
        )
        await gt.aupdate_task(
            task_list_id="list-abc",
            task_id="task-1",
            title="Updated",
        )
        body = route.calls.last.request.read()
        assert b'"title":"Updated"' in body
        # Unchanged fields don't appear
        assert b'"notes"' not in body
        assert b'"status"' not in body


@pytest.mark.asyncio
async def test_delete_task(gt: GoogleTasks) -> None:
    """delete_task: DELETE /lists/{id}/tasks/{taskId} → None."""
    with respx.mock(base_url="https://tasks.googleapis.com/tasks/v1") as mock:
        mock.delete("/lists/list-abc/tasks/task-1").mock(return_value=httpx.Response(204))
        result = await gt.adelete_task(task_list_id="list-abc", task_id="task-1")
        assert result is None


@pytest.mark.asyncio
async def test_complete_task(gt: GoogleTasks) -> None:
    """complete_task: PATCH .../tasks/{id} with status=completed."""
    with respx.mock(base_url="https://tasks.googleapis.com/tasks/v1") as mock:
        route = mock.patch("/lists/list-abc/tasks/task-1").mock(
            return_value=httpx.Response(
                200, json={**_TASK, "status": "completed", "completed": "2026-05-28T12:00:00Z"}
            )
        )
        t = await gt.acomplete_task(task_list_id="list-abc", task_id="task-1")
        assert t.status == "completed"
        body = route.calls.last.request.read()
        assert b'"status":"completed"' in body


@pytest.mark.asyncio
async def test_move_task(gt: GoogleTasks) -> None:
    """move_task: POST /lists/{id}/tasks/{taskId}/move with parent/previous."""
    with respx.mock(base_url="https://tasks.googleapis.com/tasks/v1") as mock:
        route = mock.post("/lists/list-abc/tasks/task-1/move").mock(
            return_value=httpx.Response(200, json=_TASK)
        )
        t = await gt.amove_task(
            task_list_id="list-abc",
            task_id="task-1",
            parent="task-parent",
            previous="task-prev",
        )
        assert t.id == "task-1"
        params = dict(route.calls.last.request.url.params)
        assert params["parent"] == "task-parent"
        assert params["previous"] == "task-prev"


@pytest.mark.asyncio
async def test_clear_completed(gt: GoogleTasks) -> None:
    """clear_completed: POST /lists/{id}/clear → None.

    Hides all completed tasks from view (they remain accessible via showHidden=True).
    """
    with respx.mock(base_url="https://tasks.googleapis.com/tasks/v1") as mock:
        mock.post("/lists/list-abc/clear").mock(return_value=httpx.Response(204))
        result = await gt.aclear_completed(task_list_id="list-abc")
        assert result is None


# ===========================================================================
# Round 2 — defensive parsing + URL-path guards
# ===========================================================================


@pytest.mark.asyncio
async def test_task_list_id_with_slash_percent_encoded(gt: GoogleTasks) -> None:
    """Adversarial task_list_id must NOT escape the prefix."""
    with respx.mock(base_url="https://tasks.googleapis.com/tasks/v1") as mock:
        route = mock.get(host="tasks.googleapis.com").mock(
            return_value=httpx.Response(404, json={"error": {"code": 404, "message": "Not found"}})
        )
        with pytest.raises(NotFoundError):
            await gt.aget_task_list(task_list_id="../admin")
        url = str(route.calls.last.request.url)
        assert "..%2Fadmin" in url or "..%2fadmin" in url
        assert "/admin/" not in url


@pytest.mark.asyncio
async def test_task_model_tolerates_unknown_fields(gt: GoogleTasks) -> None:
    """Real Tasks API responses have many fields we don't model.
    extra='ignore' on models silently drops them."""
    fat = {
        **_TASK,
        "kind": "tasks#task",
        "etag": "etag-1",
        "selfLink": "https://www.googleapis.com/tasks/v1/lists/list-abc/tasks/task-1",
        "updated": "2026-05-28T12:00:00Z",
        "hidden": False,
        "deleted": False,
    }
    with respx.mock(base_url="https://tasks.googleapis.com/tasks/v1") as mock:
        mock.get("/lists/list-abc/tasks/task-1").mock(return_value=httpx.Response(200, json=fat))
        t = await gt.aget_task(task_list_id="list-abc", task_id="task-1")
        assert t.id == "task-1"


# ===========================================================================
# Round 3 — error matrix
# ===========================================================================


@pytest.mark.asyncio
async def test_401_invalid_credentials(gt: GoogleTasks) -> None:
    with respx.mock(base_url="https://tasks.googleapis.com/tasks/v1") as mock:
        mock.get("/users/@me/lists/d").mock(
            return_value=httpx.Response(
                401, json={"error": {"code": 401, "message": "Invalid Credentials"}}
            )
        )
        with pytest.raises(InvalidCredentialsError) as exc_info:
            await gt.aget_task_list(task_list_id="d")
        assert exc_info.value.connector == "gtasks"


@pytest.mark.asyncio
async def test_403_permission_denied(gt: GoogleTasks) -> None:
    with respx.mock(base_url="https://tasks.googleapis.com/tasks/v1") as mock:
        mock.get("/users/@me/lists/d").mock(
            return_value=httpx.Response(
                403, json={"error": {"code": 403, "message": "Insufficient Permission"}}
            )
        )
        with pytest.raises(PermissionDeniedError):
            await gt.aget_task_list(task_list_id="d")


@pytest.mark.asyncio
async def test_404_not_found(gt: GoogleTasks) -> None:
    with respx.mock(base_url="https://tasks.googleapis.com/tasks/v1") as mock:
        mock.get("/users/@me/lists/missing").mock(
            return_value=httpx.Response(404, json={"error": {"code": 404}})
        )
        with pytest.raises(NotFoundError):
            await gt.aget_task_list(task_list_id="missing")


@pytest.mark.asyncio
async def test_429_rate_limit(gt: GoogleTasks) -> None:
    with respx.mock(base_url="https://tasks.googleapis.com/tasks/v1") as mock:
        mock.get("/users/@me/lists/d").mock(
            return_value=httpx.Response(429, json={"error": {"code": 429}})
        )
        with pytest.raises(RateLimitError):
            await gt.aget_task_list(task_list_id="d")


@pytest.mark.asyncio
async def test_500_server_error(gt: GoogleTasks) -> None:
    with respx.mock(base_url="https://tasks.googleapis.com/tasks/v1") as mock:
        mock.get("/users/@me/lists/d").mock(
            return_value=httpx.Response(500, json={"error": {"code": 500}})
        )
        with pytest.raises(ServerError):
            await gt.aget_task_list(task_list_id="d")


# ===========================================================================
# Round 4 — transport errors
# ===========================================================================


@pytest.mark.asyncio
async def test_connect_error_typed(gt: GoogleTasks) -> None:
    with respx.mock(base_url="https://tasks.googleapis.com/tasks/v1") as mock:
        mock.get("/users/@me/lists/d").mock(side_effect=httpx.ConnectError("DNS"))
        with pytest.raises(TCConnectionError):
            await gt.aget_task_list(task_list_id="d")


@pytest.mark.asyncio
async def test_timeout_typed(gt: GoogleTasks) -> None:
    with respx.mock(base_url="https://tasks.googleapis.com/tasks/v1") as mock:
        mock.get("/users/@me/lists/d").mock(side_effect=httpx.ReadTimeout("slow"))
        with pytest.raises(TCTimeoutError):
            await gt.aget_task_list(task_list_id="d")


@pytest.mark.asyncio
async def test_transport_error_typed(gt: GoogleTasks) -> None:
    with respx.mock(base_url="https://tasks.googleapis.com/tasks/v1") as mock:
        mock.get("/users/@me/lists/d").mock(side_effect=httpx.RemoteProtocolError("dropped"))
        with pytest.raises(TCTransportError):
            await gt.aget_task_list(task_list_id="d")


# ===========================================================================
# Round 5 — MCP + schema + dangerous + sync wrappers + concurrency
# ===========================================================================


def test_dangerous_actions_flagged() -> None:
    """All writes are dangerous; reads are not."""
    spec = GoogleTasks.get_spec()
    expected_dangerous = {
        "create_task_list",
        "delete_task_list",
        "create_task",
        "update_task",
        "delete_task",
        "complete_task",
    }
    for a in expected_dangerous:
        assert spec.actions[a].dangerous is True, f"{a} must be dangerous"
    # Reads + non-destructive structural ops
    for a in ("list_task_lists", "get_task_list", "list_tasks", "get_task"):
        assert spec.actions[a].dangerous is False, f"{a} must be safe"


def test_openai_schema_sweep() -> None:
    from toolsconnector.serve import ToolKit

    kit = ToolKit(["gtasks"], credentials={"gtasks": "ya29.fake"})
    tools = kit.to_openai_tools()
    assert len(tools) == 13
    for tool in tools:
        assert tool["function"]["name"].startswith("gtasks_")


def test_mcp_exposure_all_13_actions() -> None:
    from toolsconnector.serve import ToolKit

    kit = ToolKit(["gtasks"], credentials={"gtasks": "ya29.fake"})
    names = {t["name"] for t in kit.list_tools()}
    assert len(names) == 13


def test_sync_wrappers_exist() -> None:
    inst = GoogleTasks(credentials="ya29.fake")
    for action_name in ("list_task_lists", "create_task", "complete_task", "delete_task"):
        assert hasattr(inst, action_name)
        assert hasattr(inst, f"a{action_name}")


def test_verification_status_doc() -> None:
    """Pinned at 'doc' until live verification with `tasks`-scope token."""
    assert GoogleTasks.verification_status == "doc"
    assert GoogleTasks.get_spec().verification_status == "doc"


@pytest.mark.asyncio
async def test_concurrent_requests_safe(gt: GoogleTasks) -> None:
    with respx.mock(base_url="https://tasks.googleapis.com/tasks/v1") as mock:
        mock.get("/users/@me/lists/a").mock(
            return_value=httpx.Response(200, json={**_LIST, "id": "a"})
        )
        mock.get("/users/@me/lists/b").mock(
            return_value=httpx.Response(200, json={**_LIST, "id": "b"})
        )
        results = await asyncio.gather(
            gt.aget_task_list(task_list_id="a"),
            gt.aget_task_list(task_list_id="b"),
        )
        assert results[0].id == "a"
        assert results[1].id == "b"
