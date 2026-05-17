"""End-to-end tests for the Linear connector using respx.

Linear is a GraphQL connector — single endpoint (``POST /graphql``) with
typed `$variables`. The tests mirror the per-connector playbook used in
test_notion.py / test_slack.py / test_github.py but adapt to the
GraphQL-specific surface:

  - **Single endpoint**: every action hits ``POST /graphql``. We assert on
    the request body's ``query`` + ``variables`` fields, not on URL paths.
  - **Variables are the security boundary**: every action that takes user
    input MUST pass it via ``variables=`` to ``_graphql()``, NOT inline
    it into the query string. Pre-fix 14 of 19 actions inlined IDs/names/
    text via f-strings — this file pins that the rewrite to variables
    stayed in place.
  - **Status-based error mapping** (via the shared ``raise_typed_for_status``
    helper): 401 → InvalidCredentialsError, 404 → NotFoundError, 429 →
    RateLimitError, etc. We verify a representative slice — full matrix
    coverage lives in tests/unit/test_http_errors_helper.py.
  - **GraphQL ``errors[]``** field with HTTP 200: Linear returns business
    errors with HTTP 200 + ``{"errors": [...]}``. _graphql raises
    ValueError for those (NOT a typed TC error — they're per-action
    semantic failures the action method handles).
  - **Connection-style pagination**: ``first`` / ``after`` variables in,
    ``pageInfo { endCursor, hasNextPage }`` out. We pin the cursor
    handoff for one representative paginated action.

Coverage philosophy (five categories, in priority order):
    1. **Happy path** on a representative action (list_issues + create_issue
       + get_issue) — verify GraphQL query shape, variables, and parser.
    2. **Injection regression** — adversarial team_id / title / body /
       cursor inputs DO NOT change the GraphQL query string. They travel
       as variables, untouched by the connector. Without this, a 14-action
       rewrite regression would not be caught at unit-test time.
    3. **Error mapping** — vendor 401/404/429 responses translate to
       typed exceptions via raise_typed_for_status.
    4. **Pagination** — first/after handoff through PageState.cursor +
       has_more on a 2-page sequence.
    5. **Spec metadata** — dangerous flags are correctly declared.
"""

from __future__ import annotations

import json
from typing import Optional

import httpx
import pytest
import pytest_asyncio
import respx

from toolsconnector.connectors.linear import Linear
from toolsconnector.errors import (
    InvalidCredentialsError,
    NotFoundError,
    RateLimitError,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def linear() -> Linear:
    """Linear connector with a fake API key.

    Token never reaches api.linear.app because respx intercepts at the
    httpx transport layer. Tests `await` the `a`-prefixed async methods
    (e.g. `acreate_issue`); BaseConnector installs both sync and async
    entry points for every @action.
    """
    connector = Linear(credentials="lin_api_fake_test_token_xxxxxxxxxxxxxxxxxxxx")
    await connector._setup()
    yield connector
    await connector._teardown()


def _body_of(call: respx.models.Call) -> dict:
    """Decode the JSON request body of a captured respx call."""
    raw = call.request.read()
    return json.loads(raw)


# ---------------------------------------------------------------------------
# 1. Happy path — read action
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_issues_happy_path(linear: Linear) -> None:
    """list_issues: POST /graphql with first/after/filter via variables.

    Pre-fix: team_id was inlined as f'team: {{ id: {{ eq: "{team_id}" }} }}'.
    Post-fix: team_id travels in variables under the IssueFilter shape.
    """
    page = {
        "data": {
            "issues": {
                "nodes": [
                    {
                        "id": "issue-001",
                        "identifier": "ENG-1",
                        "title": "First",
                        "priority": 0,
                        "priorityLabel": "No priority",
                        "team": {"id": "team-abc"},
                        "labels": {"nodes": []},
                    }
                ],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }
        }
    }
    with respx.mock(base_url="https://api.linear.app", assert_all_called=True) as mock:
        route = mock.post("/graphql").mock(return_value=httpx.Response(200, json=page))

        result = await linear.alist_issues(team_id="team-abc", limit=10)

        # Response parsed into typed model
        assert len(result.items) == 1
        assert result.items[0].id == "issue-001"
        assert result.items[0].identifier == "ENG-1"
        assert result.page_state.has_more is False
        assert result.page_state.cursor is None

        # GraphQL request shape
        body = _body_of(route.calls.last)
        assert "query" in body
        # Query MUST declare $first/$after/$filter — not inline them
        assert "$first: Int!" in body["query"]
        assert "$filter: IssueFilter" in body["query"]
        # Variables carry the typed values
        assert body["variables"]["first"] == 10
        assert body["variables"]["filter"] == {"team": {"id": {"eq": "team-abc"}}}
        # Auth header: Linear API keys are sent raw (no "Bearer " prefix)
        assert (
            route.calls.last.request.headers["authorization"]
            == "lin_api_fake_test_token_xxxxxxxxxxxxxxxxxxxx"
        )


@pytest.mark.asyncio
async def test_create_issue_uses_input_variable(linear: Linear) -> None:
    """create_issue: input dict travels in $input, never interpolated.

    Pre-fix: title/teamId/description were inlined as f'title: "{title}"'
    with hand-rolled JSON-style escaping that didn't cover all GraphQL
    string-literal edge cases. Post-fix: the entire input dict travels
    as a variable and the GraphQL server handles type validation +
    escaping.
    """
    resp = {
        "data": {
            "issueCreate": {
                "success": True,
                "issue": {
                    "id": "new-issue-001",
                    "identifier": "ENG-99",
                    "title": "Live test",
                    "priority": 3,
                    "priorityLabel": "Medium",
                    "team": {"id": "team-abc"},
                    "labels": {"nodes": []},
                },
            }
        }
    }
    with respx.mock(base_url="https://api.linear.app") as mock:
        route = mock.post("/graphql").mock(return_value=httpx.Response(200, json=resp))

        issue = await linear.acreate_issue(
            team_id="team-abc",
            title="Live test",
            description="A new\nissue with\nlinebreaks",
            priority=3,
            assignee_id="user-001",
        )

        assert issue.id == "new-issue-001"
        body = _body_of(route.calls.last)
        # Mutation MUST use $input variable
        assert "$input: IssueCreateInput!" in body["query"]
        assert "issueCreate(input: $input)" in body["query"]
        # Input dict carries the values as native Python types — no GraphQL
        # string escaping needed because the server handles it
        assert body["variables"]["input"] == {
            "teamId": "team-abc",
            "title": "Live test",
            "description": "A new\nissue with\nlinebreaks",
            "priority": 3,
            "assigneeId": "user-001",
        }


@pytest.mark.asyncio
async def test_get_issue_uses_id_variable(linear: Linear) -> None:
    """get_issue was already safe pre-rewrite. This test pins that fact
    so a future refactor can't accidentally regress it.
    """
    resp = {
        "data": {
            "issue": {
                "id": "issue-001",
                "identifier": "ENG-1",
                "title": "T",
                "priority": 0,
                "priorityLabel": "No priority",
                "team": {"id": "team-abc"},
                "labels": {"nodes": []},
            }
        }
    }
    with respx.mock(base_url="https://api.linear.app") as mock:
        route = mock.post("/graphql").mock(return_value=httpx.Response(200, json=resp))

        issue = await linear.aget_issue("issue-001")

        assert issue.id == "issue-001"
        body = _body_of(route.calls.last)
        assert "$id: String!" in body["query"]
        assert body["variables"] == {"id": "issue-001"}


# ---------------------------------------------------------------------------
# 2. Injection regression — adversarial input must travel as a variable
# ---------------------------------------------------------------------------
#
# These tests are the load-bearing security regression. Pre-rewrite, every
# input below would have appeared in the GraphQL query string itself. If a
# future refactor ever puts user-input back into the query body, these
# tests fail and force a deliberate decision.


@pytest.mark.asyncio
async def test_injection_team_id_in_list_issues_stays_in_variables(linear: Linear) -> None:
    """A team_id containing GraphQL syntax must NOT alter the query text."""
    adversarial = 'abc"} }) { issueLabels { nodes { id name } } #'
    empty = {
        "data": {"issues": {"nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}}}
    }
    with respx.mock(base_url="https://api.linear.app") as mock:
        route = mock.post("/graphql").mock(return_value=httpx.Response(200, json=empty))
        await linear.alist_issues(team_id=adversarial)

        body = _body_of(route.calls.last)
        # Adversarial string MUST appear only inside the variables JSON, never
        # as raw text in the query string
        assert adversarial not in body["query"]
        assert body["variables"]["filter"] == {"team": {"id": {"eq": adversarial}}}


@pytest.mark.asyncio
async def test_injection_title_in_create_issue_stays_in_variables(linear: Linear) -> None:
    """A title containing GraphQL syntax must not be inlined."""
    adversarial = 'Hello"} input2: \\"x'
    resp = {
        "data": {
            "issueCreate": {
                "success": True,
                "issue": {
                    "id": "x",
                    "identifier": "X-1",
                    "title": adversarial,
                    "priority": 0,
                    "priorityLabel": "None",
                    "team": {"id": "t"},
                    "labels": {"nodes": []},
                },
            }
        }
    }
    with respx.mock(base_url="https://api.linear.app") as mock:
        route = mock.post("/graphql").mock(return_value=httpx.Response(200, json=resp))
        await linear.acreate_issue(team_id="team-abc", title=adversarial)

        body = _body_of(route.calls.last)
        assert adversarial not in body["query"]
        assert body["variables"]["input"]["title"] == adversarial


@pytest.mark.asyncio
async def test_injection_comment_body_stays_in_variables(linear: Linear) -> None:
    """add_comment was previously interpolating the body with hand-rolled
    JSON-style escaping. The variables rewrite removes that surface entirely.
    """
    adversarial = '") { __schema { types { name } } } #'
    resp = {
        "data": {
            "commentCreate": {
                "success": True,
                "comment": {
                    "id": "c-1",
                    "body": adversarial,
                    "createdAt": "2026-05-18T00:00:00Z",
                    "user": None,
                    "issue": {"id": "i-1"},
                },
            }
        }
    }
    with respx.mock(base_url="https://api.linear.app") as mock:
        route = mock.post("/graphql").mock(return_value=httpx.Response(200, json=resp))
        await linear.aadd_comment(issue_id="i-1", body=adversarial)

        body = _body_of(route.calls.last)
        assert adversarial not in body["query"]
        assert body["variables"]["input"]["body"] == adversarial


@pytest.mark.asyncio
async def test_injection_search_query_stays_in_variables(linear: Linear) -> None:
    """search_issues previously inlined the query text — pin the new path."""
    adversarial = '"} ) { teams { nodes { key } } } #'
    empty = {
        "data": {
            "issueSearch": {"nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}}
        }
    }
    with respx.mock(base_url="https://api.linear.app") as mock:
        route = mock.post("/graphql").mock(return_value=httpx.Response(200, json=empty))
        await linear.asearch_issues(query=adversarial)

        body = _body_of(route.calls.last)
        assert adversarial not in body["query"]
        assert body["variables"]["q"] == adversarial


@pytest.mark.asyncio
async def test_injection_cursor_stays_in_variables(linear: Linear) -> None:
    """Pagination cursors come from Linear itself, but a hostile MITM (or
    a buggy caller passing user-controlled cursors) could try to inject.
    Variables eliminate the surface.
    """
    adversarial_cursor = '"; } } #'
    empty = {
        "data": {"users": {"nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}}}
    }
    with respx.mock(base_url="https://api.linear.app") as mock:
        route = mock.post("/graphql").mock(return_value=httpx.Response(200, json=empty))
        await linear.alist_users(cursor=adversarial_cursor)

        body = _body_of(route.calls.last)
        assert adversarial_cursor not in body["query"]
        assert body["variables"]["after"] == adversarial_cursor


@pytest.mark.asyncio
async def test_no_action_inlines_id_into_query(linear: Linear) -> None:
    """Sweep: every ID-taking action receives an adversarial UUID and
    we verify the query never contains it.

    If a new @action ships that inlines an ID, this test catches it at
    unit-test time before the security-review stage.
    """
    adversarial = 'abc"; DROP TABLE issues; #'
    # Generic empty response that satisfies every action's parser well
    # enough that we don't hit ValueError before we can inspect the call.
    generic_response = {
        "data": {
            "issue": {
                "id": "x",
                "identifier": "X-1",
                "title": "t",
                "priority": 0,
                "priorityLabel": "None",
                "team": {"id": "t"},
                "labels": {"nodes": []},
            },
            "cycle": {
                "id": "x",
                "number": 1,
                "name": "N",
                "team": {"id": "t"},
            },
            "user": {"id": "x", "name": "N", "active": True},
            "issueUpdate": {
                "success": True,
                "issue": {
                    "id": "x",
                    "identifier": "X-1",
                    "title": "t",
                    "priority": 0,
                    "priorityLabel": "None",
                    "team": {"id": "t"},
                    "labels": {"nodes": []},
                },
            },
            "issueDelete": {"success": True},
            "projectDelete": {"success": True},
            "workflowStates": {"nodes": []},
        }
    }
    actions: list = [
        ("aget_issue", {"issue_id": adversarial}),
        ("aget_cycle", {"cycle_id": adversarial}),
        ("aget_user", {"user_id": adversarial}),
        ("aupdate_issue", {"issue_id": adversarial, "title": "t"}),
        ("adelete_issue", {"issue_id": adversarial}),
        ("adelete_project", {"project_id": adversarial}),
        ("aget_workflow_states", {"team_id": adversarial}),
    ]
    for action_name, kwargs in actions:
        with respx.mock(base_url="https://api.linear.app") as mock:
            route = mock.post("/graphql").mock(
                return_value=httpx.Response(200, json=generic_response)
            )
            try:
                await getattr(linear, action_name)(**kwargs)
            except Exception:
                # Some actions may fail on the generic mock (e.g. parser
                # mismatches) — that's fine, we only care the request was
                # constructed safely.
                pass
            assert route.call_count >= 1, f"{action_name}: no request issued"
            body = _body_of(route.calls.last)
            assert adversarial not in body["query"], (
                f"{action_name}: ID injected into query — variables rewrite regressed"
            )

            # And the variables MUST contain the value verbatim somewhere
            # in the parsed dict (not the serialized JSON, which escapes
            # quotes; we want to know the raw value reached the variables).
            def _contains(node: object, needle: str) -> bool:
                if isinstance(node, str):
                    return needle in node
                if isinstance(node, dict):
                    return any(_contains(v, needle) for v in node.values())
                if isinstance(node, list):
                    return any(_contains(item, needle) for item in node)
                return False

            assert _contains(body.get("variables", {}), adversarial), (
                f"{action_name}: adversarial value not found in variables — "
                "may have been silently dropped"
            )


# ---------------------------------------------------------------------------
# 3. Error mapping — vendor responses → typed exceptions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unauthorized_raises_invalid_credentials_error(linear: Linear) -> None:
    """401 from Linear → InvalidCredentialsError via the shared helper."""
    with respx.mock(base_url="https://api.linear.app") as mock:
        mock.post("/graphql").mock(return_value=httpx.Response(401, json={"error": "unauthorized"}))

        with pytest.raises(InvalidCredentialsError) as exc_info:
            await linear.aget_issue("issue-001")

        err = exc_info.value
        assert err.connector == "linear"
        assert err.upstream_status == 401


@pytest.mark.asyncio
async def test_not_found_raises_not_found_error(linear: Linear) -> None:
    """404 from Linear → NotFoundError."""
    with respx.mock(base_url="https://api.linear.app") as mock:
        mock.post("/graphql").mock(return_value=httpx.Response(404, json={"error": "not found"}))

        with pytest.raises(NotFoundError) as exc_info:
            await linear.aget_issue("issue-does-not-exist")

        assert exc_info.value.connector == "linear"


@pytest.mark.asyncio
async def test_rate_limited_raises_rate_limit_error(linear: Linear) -> None:
    """Linear rate-limit envelope: HTTP 400 + GraphQL errors[] with
    extensions.code == "RATELIMITED" + X-RateLimit-Requests-Reset header
    (epoch ms when the window resets).

    This is THE Linear-specific quirk — unlike most REST APIs that use
    HTTP 429, Linear returns 400 and signals rate-limiting through the
    GraphQL errors[] envelope. The raw 400 would otherwise be mapped to
    ValidationError by the shared helper; Linear-aware detection in
    _graphql inspects the body BEFORE the status-code mapping fires.

    Source: https://linear.app/developers/rate-limiting
    """
    # Simulate reset at "now + 30 seconds" so retry_after lands near 30.
    import time as _time

    reset_epoch_ms = int((_time.time() + 30) * 1000)
    with respx.mock(base_url="https://api.linear.app") as mock:
        mock.post("/graphql").mock(
            return_value=httpx.Response(
                400,
                headers={"X-RateLimit-Requests-Reset": str(reset_epoch_ms)},
                json={
                    "errors": [
                        {
                            "message": "Rate limit exceeded",
                            "extensions": {"code": "RATELIMITED"},
                        }
                    ]
                },
            )
        )

        with pytest.raises(RateLimitError) as exc_info:
            await linear.alist_issues()

        err = exc_info.value
        assert err.connector == "linear"
        assert err.upstream_status == 400
        assert err.details["linear_code"] == "RATELIMITED"
        # retry_after should be ~30s (allow generous tolerance for clock drift)
        assert err.retry_after_seconds is not None
        assert 0 < err.retry_after_seconds <= 35


@pytest.mark.asyncio
async def test_rate_limit_uses_endpoint_reset_header_when_present(linear: Linear) -> None:
    """When both X-RateLimit-Requests-Reset and the more specific
    X-RateLimit-Endpoint-Requests-Reset are present, prefer the endpoint
    one — it reflects the per-action quota the caller actually hit.
    """
    import time as _time

    endpoint_reset = int((_time.time() + 10) * 1000)
    overall_reset = int((_time.time() + 120) * 1000)
    with respx.mock(base_url="https://api.linear.app") as mock:
        mock.post("/graphql").mock(
            return_value=httpx.Response(
                400,
                headers={
                    "X-RateLimit-Endpoint-Requests-Reset": str(endpoint_reset),
                    "X-RateLimit-Requests-Reset": str(overall_reset),
                },
                json={
                    "errors": [
                        {
                            "message": "Endpoint quota exceeded",
                            "extensions": {"code": "RATELIMITED"},
                        }
                    ]
                },
            )
        )

        with pytest.raises(RateLimitError) as exc_info:
            await linear.aget_issue("issue-001")
        # Endpoint reset is closer (~10s) than overall (~120s) — connector
        # picks the more-specific one.
        assert exc_info.value.retry_after_seconds is not None
        assert exc_info.value.retry_after_seconds <= 15


@pytest.mark.asyncio
async def test_400_without_ratelimited_falls_through_to_validation_error(linear: Linear) -> None:
    """A normal HTTP 400 (e.g. malformed query) must still map to
    ValidationError. Only the RATELIMITED envelope diverts to
    RateLimitError; everything else uses the standard mapping.
    """
    from toolsconnector.errors import ValidationError

    with respx.mock(base_url="https://api.linear.app") as mock:
        mock.post("/graphql").mock(
            return_value=httpx.Response(
                400,
                json={
                    "errors": [
                        {
                            "message": "Field 'fake' not found",
                            "extensions": {"code": "INVALID_INPUT"},
                        }
                    ]
                },
            )
        )

        with pytest.raises(ValidationError):
            await linear.aget_issue("issue-001")


@pytest.mark.asyncio
async def test_graphql_errors_at_200_raise_value_error(linear: Linear) -> None:
    """Linear returns HTTP 200 with ``{"errors": [...]}`` for business
    errors (invalid field, missing required arg, etc.). _graphql raises
    ValueError carrying every error message — NOT a typed TC error,
    since these are per-action semantic failures the caller handles.
    """
    with respx.mock(base_url="https://api.linear.app") as mock:
        mock.post("/graphql").mock(
            return_value=httpx.Response(
                200,
                json={
                    "errors": [
                        {"message": "Field 'fake_field' not found"},
                        {"message": "Argument 'bogus' is required"},
                    ]
                },
            )
        )

        with pytest.raises(ValueError) as exc_info:
            await linear.aget_issue("issue-001")

        assert "fake_field" in str(exc_info.value)
        assert "bogus" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 4. Pagination — first/after flow through PageState
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_issues_pagination_first_after_cycle(linear: Linear) -> None:
    """Two-page sequence: first page returns endCursor + hasNextPage=true;
    second page returns hasNextPage=false. Caller passes the cursor
    back via the `cursor=` kwarg, which travels as `$after`.
    """
    page1 = {
        "data": {
            "issues": {
                "nodes": [
                    {
                        "id": f"issue-{i}",
                        "identifier": f"ENG-{i}",
                        "title": "T",
                        "priority": 0,
                        "priorityLabel": "No priority",
                        "team": {"id": "t"},
                        "labels": {"nodes": []},
                    }
                    for i in range(2)
                ],
                "pageInfo": {"hasNextPage": True, "endCursor": "cursor-page-2"},
            }
        }
    }
    page2 = {
        "data": {
            "issues": {
                "nodes": [
                    {
                        "id": "issue-2",
                        "identifier": "ENG-2",
                        "title": "T",
                        "priority": 0,
                        "priorityLabel": "No priority",
                        "team": {"id": "t"},
                        "labels": {"nodes": []},
                    }
                ],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }
        }
    }
    with respx.mock(base_url="https://api.linear.app") as mock:
        route = mock.post("/graphql").mock(
            side_effect=[
                httpx.Response(200, json=page1),
                httpx.Response(200, json=page2),
            ]
        )

        # Page 1
        r1 = await linear.alist_issues()
        assert len(r1.items) == 2
        assert r1.page_state.has_more is True
        assert r1.page_state.cursor == "cursor-page-2"

        # Page 2 — cursor flows back as $after
        r2 = await linear.alist_issues(cursor=r1.page_state.cursor)
        assert len(r2.items) == 1
        assert r2.page_state.has_more is False

        # Verify $after carried the cursor verbatim
        body2 = _body_of(route.calls[1])
        assert body2["variables"]["after"] == "cursor-page-2"


# ---------------------------------------------------------------------------
# 5. Limit clamping (round-6 Notion-style fix applied to Linear)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_limit_none_coerces_to_action_default(linear: Linear) -> None:
    """MCP's synthetic handler defaults optional params to None. Pre-fix
    that hit ``min(None, 250)`` and crashed. The new ``_clamp_page_size``
    helper coerces None → action default (50 for most paginated actions).
    """
    empty = {
        "data": {"issues": {"nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}}}
    }
    with respx.mock(base_url="https://api.linear.app") as mock:
        route = mock.post("/graphql").mock(return_value=httpx.Response(200, json=empty))
        # Explicit None — simulates MCP dispatch
        await linear.alist_issues(limit=None)
        body = _body_of(route.calls.last)
        assert body["variables"]["first"] == 50  # action default


@pytest.mark.asyncio
async def test_limit_over_250_clamped_to_250(linear: Linear) -> None:
    """Linear's documented max page size is 250. Larger values get clamped."""
    empty = {
        "data": {"issues": {"nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}}}
    }
    with respx.mock(base_url="https://api.linear.app") as mock:
        route = mock.post("/graphql").mock(return_value=httpx.Response(200, json=empty))
        await linear.alist_issues(limit=10_000)
        body = _body_of(route.calls.last)
        assert body["variables"]["first"] == 250


@pytest.mark.asyncio
async def test_limit_zero_or_negative_clamped_to_one(linear: Linear) -> None:
    """Defensive clamp: limit <= 0 → 1 (never let invalid values reach the API)."""
    empty = {
        "data": {"issues": {"nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}}}
    }
    with respx.mock(base_url="https://api.linear.app") as mock:
        route = mock.post("/graphql").mock(return_value=httpx.Response(200, json=empty))
        await linear.alist_issues(limit=-5)
        body = _body_of(route.calls.last)
        assert body["variables"]["first"] == 1

        await linear.alist_issues(limit=0)
        body = _body_of(route.calls.last)
        assert body["variables"]["first"] == 1


# ---------------------------------------------------------------------------
# 6. Spec metadata — dangerous flag is correctly declared
# ---------------------------------------------------------------------------


def test_dangerous_actions_are_flagged() -> None:
    """Write/destructive actions must be dangerous=True; reads must be False.

    Under the default ToolKit config (``exclude_dangerous=True``), an
    accidentally-dropped flag would auto-expose a destructive action
    to AI agents. This test is the tripwire.
    """
    spec = Linear.get_spec()

    # Writes / destructive
    for write_action in (
        "create_issue",
        "add_comment",
        "delete_issue",
        "create_label",
        "update_project",
        "delete_project",
    ):
        assert spec.actions[write_action].dangerous is True, (
            f"{write_action} must be dangerous=True"
        )

    # Reads
    for read_action in (
        "list_issues",
        "get_issue",
        "search_issues",
        "list_teams",
        "list_users",
        "get_user",
        "list_labels",
        "get_workflow_states",
        "list_cycles",
        "get_cycle",
        "list_issue_comments",
    ):
        assert spec.actions[read_action].dangerous is False, (
            f"{read_action} must be dangerous=False"
        )


# ---------------------------------------------------------------------------
# 7. Transport-error mapping — typed exceptions instead of raw httpx
# ---------------------------------------------------------------------------
#
# Audit-round finding: pre-fix httpx.ConnectError / ReadTimeout / TransportError
# leaked through _graphql as raw httpx exceptions. Callers catching
# ToolsConnectorError were blind to network failures. Mirrors the Notion
# fix from 0.3.7 — the regression tests pin the typed mapping.


@pytest.mark.asyncio
async def test_connect_error_maps_to_typed_connection_error(linear: Linear) -> None:
    """httpx.ConnectError → toolsconnector.errors.ConnectionError."""
    from toolsconnector.errors import ConnectionError as TCConnectionError
    from toolsconnector.errors import ToolsConnectorError

    with respx.mock(base_url="https://api.linear.app") as mock:
        mock.post("/graphql").mock(side_effect=httpx.ConnectError("DNS down"))
        with pytest.raises(TCConnectionError) as exc_info:
            await linear.aget_issue("issue-001")
        err = exc_info.value
        assert isinstance(err, ToolsConnectorError)
        assert err.connector == "linear"
        assert err.details["url"].endswith("/graphql")
        assert isinstance(err.__cause__, httpx.ConnectError)


@pytest.mark.asyncio
async def test_read_timeout_maps_to_typed_timeout_error(linear: Linear) -> None:
    """httpx.ReadTimeout → toolsconnector.errors.TimeoutError."""
    from toolsconnector.errors import TimeoutError as TCTimeoutError

    with respx.mock(base_url="https://api.linear.app") as mock:
        mock.post("/graphql").mock(side_effect=httpx.ReadTimeout("slow"))
        with pytest.raises(TCTimeoutError) as exc_info:
            await linear.aget_issue("issue-001")
        err = exc_info.value
        assert err.details["underlying"] == "ReadTimeout"


@pytest.mark.asyncio
async def test_generic_transport_error_maps_to_transport_error(linear: Linear) -> None:
    """Other httpx.TransportError subclasses → TransportError."""
    from toolsconnector.errors import TransportError as TCTransportError

    with respx.mock(base_url="https://api.linear.app") as mock:
        mock.post("/graphql").mock(side_effect=httpx.ReadError("connection reset"))
        with pytest.raises(TCTransportError):
            await linear.aget_issue("issue-001")


# ---------------------------------------------------------------------------
# 8. Defensive response parsing — non-JSON body, null body
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_json_response_body_maps_to_transport_error(linear: Linear) -> None:
    """Linear's CDN can return 502/503 with HTML body. Surface as TransportError
    instead of letting json.JSONDecodeError bubble through.
    """
    from toolsconnector.errors import TransportError as TCTransportError

    with respx.mock(base_url="https://api.linear.app") as mock:
        mock.post("/graphql").mock(
            return_value=httpx.Response(
                200,
                content=b"<html><body>Service Unavailable</body></html>",
                headers={"content-type": "text/html"},
            )
        )
        with pytest.raises(TCTransportError) as exc_info:
            await linear.aget_issue("issue-001")
        # Body preview is captured for debugging
        assert "<html>" in exc_info.value.details["body_preview"]


@pytest.mark.asyncio
async def test_null_json_body_coalesces_to_empty(linear: Linear) -> None:
    """Linear shouldn't ever return literal JSON `null`, but if it did
    (or a buggy proxy injects it), _graphql treats it as empty success
    so downstream callers' `.get()` calls don't AttributeError.

    This mirrors the Notion null-body fix from 0.3.7.
    """
    with respx.mock(base_url="https://api.linear.app") as mock:
        mock.post("/graphql").mock(
            return_value=httpx.Response(
                200, content=b"null", headers={"content-type": "application/json"}
            )
        )
        # list_teams returns []; should not raise. _graphql returns {} for null.
        teams = await linear.alist_teams()
        assert teams == []


# ---------------------------------------------------------------------------
# 9. Pydantic extra='ignore' — unknown response fields don't crash parse
# ---------------------------------------------------------------------------
#
# Audit finding: all 8 Linear models lacked extra="ignore". Linear adds
# fields without major-version bumps; pre-fix a new field would crash
# every parse. Post-fix unknown fields are silently dropped.


@pytest.mark.asyncio
async def test_parse_tolerates_unknown_fields_in_response(linear: Linear) -> None:
    """Future Linear schema additions (e.g. new field on Issue or User)
    must not crash existing parsers. Sweep across the main shapes.
    """
    resp = {
        "data": {
            "issue": {
                "id": "issue-future",
                "identifier": "X-1",
                "title": "Has unknown fields",
                "priority": 0,
                "priorityLabel": "No priority",
                "team": {"id": "t", "futureField": "ignored"},
                "labels": {"nodes": []},
                "unknownTopLevelField": "from a future Linear release",
                "assignee": {
                    "id": "u-1",
                    "name": "Alice",
                    "active": True,
                    "anotherUnknown": 42,
                },
            }
        }
    }
    with respx.mock(base_url="https://api.linear.app") as mock:
        mock.post("/graphql").mock(return_value=httpx.Response(200, json=resp))
        issue = await linear.aget_issue("issue-future")
        assert issue.id == "issue-future"
        assert issue.title == "Has unknown fields"
        assert issue.assignee is not None
        assert issue.assignee.name == "Alice"


# ---------------------------------------------------------------------------
# 10. Happy-path coverage for actions only swept by injection tests
# ---------------------------------------------------------------------------
#
# Pre-audit, several actions (list_labels, create_label, get_workflow_states,
# list_cycles, get_cycle, list_issue_comments, list_teams, list_projects,
# list_users, get_user, update_project, delete_project) were exercised only
# by the injection-regression sweep with throwaway responses. Adding direct
# happy-path tests lifts coverage into the 90%+ band and pins the parser +
# query shape for each action.


@pytest.mark.asyncio
async def test_list_teams_returns_typed_teams(linear: Linear) -> None:
    """list_teams: no user input, returns list[LinearTeam]."""
    resp = {
        "data": {
            "teams": {
                "nodes": [
                    {
                        "id": "team-eng",
                        "name": "Engineering",
                        "key": "ENG",
                        "description": "Build stuff",
                        "icon": None,
                        "color": "#000",
                        "private": False,
                    }
                ]
            }
        }
    }
    with respx.mock(base_url="https://api.linear.app") as mock:
        mock.post("/graphql").mock(return_value=httpx.Response(200, json=resp))
        teams = await linear.alist_teams()
        assert len(teams) == 1
        assert teams[0].id == "team-eng"
        assert teams[0].key == "ENG"


@pytest.mark.asyncio
async def test_list_labels_with_team_filter(linear: Linear) -> None:
    """list_labels: team_id filter travels as IssueLabelFilter variable."""
    resp = {"data": {"issueLabels": {"nodes": [{"id": "l-1", "name": "bug", "color": "#f00"}]}}}
    with respx.mock(base_url="https://api.linear.app") as mock:
        route = mock.post("/graphql").mock(return_value=httpx.Response(200, json=resp))
        labels = await linear.alist_labels(team_id="team-eng")
        assert len(labels) == 1
        assert labels[0].name == "bug"

        body = _body_of(route.calls.last)
        assert "$filter: IssueLabelFilter" in body["query"]
        assert body["variables"]["filter"] == {"team": {"id": {"eq": "team-eng"}}}


@pytest.mark.asyncio
async def test_create_label_with_color(linear: Linear) -> None:
    """create_label: input dict carries teamId/name/color via $input."""
    resp = {
        "data": {
            "issueLabelCreate": {
                "success": True,
                "issueLabel": {"id": "l-new", "name": "p0", "color": "#ff0000"},
            }
        }
    }
    with respx.mock(base_url="https://api.linear.app") as mock:
        route = mock.post("/graphql").mock(return_value=httpx.Response(200, json=resp))
        label = await linear.acreate_label(team_id="team-eng", name="p0", color="#ff0000")
        assert label.id == "l-new"
        body = _body_of(route.calls.last)
        assert body["variables"]["input"] == {
            "teamId": "team-eng",
            "name": "p0",
            "color": "#ff0000",
        }


@pytest.mark.asyncio
async def test_create_label_raises_on_unsuccessful_mutation(linear: Linear) -> None:
    """If issueLabelCreate.success is False, surface as ValueError so
    callers don't silently get an empty/partial result.
    """
    resp = {"data": {"issueLabelCreate": {"success": False, "issueLabel": None}}}
    with respx.mock(base_url="https://api.linear.app") as mock:
        mock.post("/graphql").mock(return_value=httpx.Response(200, json=resp))
        with pytest.raises(ValueError) as exc_info:
            await linear.acreate_label(team_id="team-eng", name="dup")
        assert "label creation failed" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_get_workflow_states_filters_by_team(linear: Linear) -> None:
    """get_workflow_states: team_id is required and travels in $filter."""
    resp = {
        "data": {
            "workflowStates": {
                "nodes": [
                    {
                        "id": "s-1",
                        "name": "Todo",
                        "type": "unstarted",
                        "color": "#888",
                        "position": 0,
                    }
                ]
            }
        }
    }
    with respx.mock(base_url="https://api.linear.app") as mock:
        route = mock.post("/graphql").mock(return_value=httpx.Response(200, json=resp))
        states = await linear.aget_workflow_states(team_id="team-eng")
        assert len(states) == 1
        assert states[0].name == "Todo"
        body = _body_of(route.calls.last)
        assert "$filter: WorkflowStateFilter!" in body["query"]
        assert body["variables"]["filter"] == {"team": {"id": {"eq": "team-eng"}}}


@pytest.mark.asyncio
async def test_list_cycles_with_team_filter(linear: Linear) -> None:
    """list_cycles: team_id filter travels as CycleFilter variable."""
    resp = {
        "data": {
            "cycles": {
                "nodes": [
                    {
                        "id": "c-1",
                        "number": 1,
                        "name": "Sprint 1",
                        "team": {"id": "team-eng"},
                    }
                ],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }
        }
    }
    with respx.mock(base_url="https://api.linear.app") as mock:
        route = mock.post("/graphql").mock(return_value=httpx.Response(200, json=resp))
        result = await linear.alist_cycles(team_id="team-eng")
        assert len(result.items) == 1
        body = _body_of(route.calls.last)
        assert "$filter: CycleFilter" in body["query"]


@pytest.mark.asyncio
async def test_list_issue_comments_uses_id_variable(linear: Linear) -> None:
    """list_issue_comments: issue id travels via $id."""
    resp = {
        "data": {
            "issue": {
                "comments": {
                    "nodes": [
                        {
                            "id": "c-1",
                            "body": "First comment",
                            "createdAt": "2026-05-18T00:00:00Z",
                            "user": {"id": "u-1", "name": "A", "active": True},
                            "issue": {"id": "i-1"},
                        }
                    ]
                }
            }
        }
    }
    with respx.mock(base_url="https://api.linear.app") as mock:
        route = mock.post("/graphql").mock(return_value=httpx.Response(200, json=resp))
        comments = await linear.alist_issue_comments(issue_id="i-1")
        assert len(comments) == 1
        body = _body_of(route.calls.last)
        assert body["variables"] == {"id": "i-1"}


@pytest.mark.asyncio
async def test_list_users_paginated(linear: Linear) -> None:
    """list_users: paginated cursor flow via $first/$after."""
    resp = {
        "data": {
            "users": {
                "nodes": [
                    {"id": "u-1", "name": "Alice", "active": True},
                    {"id": "u-2", "name": "Bob", "active": True},
                ],
                "pageInfo": {"hasNextPage": True, "endCursor": "cursor-page-2"},
            }
        }
    }
    with respx.mock(base_url="https://api.linear.app") as mock:
        mock.post("/graphql").mock(return_value=httpx.Response(200, json=resp))
        result = await linear.alist_users()
        assert len(result.items) == 2
        assert result.page_state.has_more is True
        assert result.page_state.cursor == "cursor-page-2"


@pytest.mark.asyncio
async def test_update_project_partial_fields(linear: Linear) -> None:
    """update_project: only sets fields that the caller supplied."""
    resp = {
        "data": {
            "projectUpdate": {
                "success": True,
                "project": {
                    "id": "p-1",
                    "name": "New name",
                    "state": "started",
                    "progress": 0.5,
                },
            }
        }
    }
    with respx.mock(base_url="https://api.linear.app") as mock:
        route = mock.post("/graphql").mock(return_value=httpx.Response(200, json=resp))
        project = await linear.aupdate_project(project_id="p-1", name="New name")
        assert project.id == "p-1"
        body = _body_of(route.calls.last)
        # ID + input variables — no inlining
        assert body["variables"]["id"] == "p-1"
        assert body["variables"]["input"] == {"name": "New name"}


@pytest.mark.asyncio
async def test_update_project_with_no_fields_raises_value_error(linear: Linear) -> None:
    """update_project with no fields to update should fail fast, not send
    an empty mutation that the server would reject anyway.
    """
    with respx.mock(base_url="https://api.linear.app", assert_all_called=False):
        with pytest.raises(ValueError) as exc_info:
            await linear.aupdate_project(project_id="p-1")
        assert "at least one field" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_delete_project_returns_success_bool(linear: Linear) -> None:
    """delete_project: returns the mutation's success boolean."""
    resp = {"data": {"projectDelete": {"success": True}}}
    with respx.mock(base_url="https://api.linear.app") as mock:
        route = mock.post("/graphql").mock(return_value=httpx.Response(200, json=resp))
        result = await linear.adelete_project(project_id="p-1")
        assert result is True
        body = _body_of(route.calls.last)
        assert body["variables"] == {"id": "p-1"}


@pytest.mark.asyncio
async def test_get_cycle_uses_id_variable(linear: Linear) -> None:
    """get_cycle: was already safe pre-rewrite. Pin the contract."""
    resp = {
        "data": {
            "cycle": {
                "id": "c-1",
                "number": 1,
                "name": "Sprint 1",
                "team": {"id": "team-eng"},
            }
        }
    }
    with respx.mock(base_url="https://api.linear.app") as mock:
        route = mock.post("/graphql").mock(return_value=httpx.Response(200, json=resp))
        cycle = await linear.aget_cycle(cycle_id="c-1")
        assert cycle.id == "c-1"
        body = _body_of(route.calls.last)
        assert body["variables"] == {"id": "c-1"}


# ---------------------------------------------------------------------------
# 11. Round-4: GraphQL syntax validation across all 19 actions
# ---------------------------------------------------------------------------
#
# Audit-round-4 finding: any typo in OUR query strings would surface as
# HTTP 400 from Linear in production — silently if respx mocks always
# return canned 200s. Parsing every emitted query with graphql-core
# catches structural errors at unit-test time.


@pytest.mark.asyncio
async def test_every_action_emits_syntactically_valid_graphql(linear: Linear) -> None:
    """Sweep: invoke every @action with a generic mock, capture the
    emitted query, parse with graphql-core. Any GraphQLSyntaxError
    means a typo / unbalanced brace / unknown directive in OUR query
    template — failure to construct valid GraphQL would 400 from Linear.
    """
    try:
        from graphql import GraphQLSyntaxError, parse  # type: ignore[import-not-found]
    except ImportError:
        pytest.skip("graphql-core not installed — install with `pip install graphql-core`")

    # Generic response covering every action's expected data shape so
    # the connector parser doesn't reject before we capture the request.
    generic_response = {
        "data": {
            "issues": {"nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}},
            "issue": {
                "id": "i",
                "identifier": "X",
                "title": "t",
                "priority": 0,
                "priorityLabel": "n",
                "team": {"id": "t"},
                "labels": {"nodes": []},
                "comments": {"nodes": []},
            },
            "issueCreate": {
                "success": True,
                "issue": {
                    "id": "i",
                    "identifier": "X",
                    "title": "t",
                    "priority": 0,
                    "priorityLabel": "n",
                    "team": {"id": "t"},
                    "labels": {"nodes": []},
                },
            },
            "issueUpdate": {
                "success": True,
                "issue": {
                    "id": "i",
                    "identifier": "X",
                    "title": "t",
                    "priority": 0,
                    "priorityLabel": "n",
                    "team": {"id": "t"},
                    "labels": {"nodes": []},
                },
            },
            "issueDelete": {"success": True},
            "issueSearch": {"nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}},
            "teams": {"nodes": []},
            "projects": {"nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}},
            "projectUpdate": {"success": True, "project": {"id": "p", "name": "n"}},
            "projectDelete": {"success": True},
            "users": {"nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}},
            "user": {"id": "u", "name": "n", "active": True},
            "issueLabels": {"nodes": []},
            "issueLabelCreate": {
                "success": True,
                "issueLabel": {"id": "l", "name": "n", "color": "#000"},
            },
            "workflowStates": {"nodes": []},
            "cycles": {"nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}},
            "cycle": {"id": "c", "number": 1, "name": "n", "team": {"id": "t"}},
            "commentCreate": {
                "success": True,
                "comment": {
                    "id": "c",
                    "body": "b",
                    "createdAt": "x",
                    "user": None,
                    "issue": {"id": "i"},
                },
            },
        }
    }
    action_calls = [
        (
            "list_issues",
            "alist_issues",
            {"team_id": "t", "state": "Open", "limit": 10, "cursor": "c"},
        ),
        ("get_issue", "aget_issue", {"issue_id": "i"}),
        (
            "create_issue",
            "acreate_issue",
            {"team_id": "t", "title": "x", "description": "d", "priority": 1, "assignee_id": "u"},
        ),
        (
            "update_issue",
            "aupdate_issue",
            {"issue_id": "i", "title": "x", "description": "d", "state_id": "s", "priority": 2},
        ),
        ("delete_issue", "adelete_issue", {"issue_id": "i"}),
        ("search_issues", "asearch_issues", {"query": "q", "limit": 10, "cursor": "c"}),
        ("list_teams", "alist_teams", {}),
        ("list_projects", "alist_projects", {"limit": 10, "cursor": "c"}),
        (
            "update_project",
            "aupdate_project",
            {"project_id": "p", "name": "n", "description": "d", "state": "started"},
        ),
        ("delete_project", "adelete_project", {"project_id": "p"}),
        ("list_users", "alist_users", {"limit": 10, "cursor": "c"}),
        ("get_user", "aget_user", {"user_id": "u"}),
        ("list_labels", "alist_labels", {"team_id": "t"}),
        ("create_label", "acreate_label", {"team_id": "t", "name": "n", "color": "#000"}),
        ("get_workflow_states", "aget_workflow_states", {"team_id": "t"}),
        ("list_cycles", "alist_cycles", {"team_id": "t", "limit": 10, "cursor": "c"}),
        ("get_cycle", "aget_cycle", {"cycle_id": "c"}),
        ("add_comment", "aadd_comment", {"issue_id": "i", "body": "b"}),
        ("list_issue_comments", "alist_issue_comments", {"issue_id": "i"}),
    ]
    syntax_errors: list[str] = []
    for action_name, method_name, kwargs in action_calls:
        with respx.mock(base_url="https://api.linear.app") as mock:
            route = mock.post("/graphql").mock(
                return_value=httpx.Response(200, json=generic_response)
            )
            try:
                await getattr(linear, method_name)(**kwargs)
            except Exception:
                # Parser shape mismatches OK — we only care about the emitted query
                pass
            assert route.calls, f"{action_name}: no request emitted"
            body = json.loads(route.calls.last.request.read())
            query = body.get("query", "")
            try:
                parse(query)
            except GraphQLSyntaxError as e:
                syntax_errors.append(f"{action_name}: {e}")
    assert syntax_errors == [], (
        f"GraphQL syntax errors in connector-emitted queries: {syntax_errors}"
    )


# ---------------------------------------------------------------------------
# 12. Round-4: full HTTP error-matrix mapping
# ---------------------------------------------------------------------------
#
# Pre-audit-round-4 only 401/404/429-mapped-to-RATELIMITED were tested.
# Filling in 403/409/422/500/503 to confirm raise_typed_for_status passes
# them through correctly.


@pytest.mark.asyncio
async def test_403_maps_to_permission_denied_error(linear: Linear) -> None:
    """HTTP 403 (e.g. integration lacks workspace access) → PermissionDeniedError."""
    from toolsconnector.errors import PermissionDeniedError

    with respx.mock(base_url="https://api.linear.app") as mock:
        mock.post("/graphql").mock(return_value=httpx.Response(403, json={"error": "forbidden"}))
        with pytest.raises(PermissionDeniedError) as exc_info:
            await linear.aget_issue("i-1")
        assert exc_info.value.connector == "linear"


@pytest.mark.asyncio
async def test_409_maps_to_conflict_error(linear: Linear) -> None:
    """HTTP 409 (e.g. concurrent-update conflict) → ConflictError."""
    from toolsconnector.errors import ConflictError

    with respx.mock(base_url="https://api.linear.app") as mock:
        mock.post("/graphql").mock(return_value=httpx.Response(409, json={"error": "conflict"}))
        with pytest.raises(ConflictError):
            await linear.aupdate_issue("i-1", title="x")


@pytest.mark.asyncio
async def test_422_maps_to_validation_error(linear: Linear) -> None:
    """HTTP 422 → ValidationError (some Linear endpoints return 422 for
    schema violations, distinct from the 400 + RATELIMITED quirk).
    """
    from toolsconnector.errors import ValidationError

    with respx.mock(base_url="https://api.linear.app") as mock:
        mock.post("/graphql").mock(
            return_value=httpx.Response(422, json={"error": "unprocessable"})
        )
        with pytest.raises(ValidationError):
            await linear.aget_issue("i-1")


@pytest.mark.asyncio
async def test_500_maps_to_server_error(linear: Linear) -> None:
    """HTTP 500 → ServerError (caller-retry-eligible)."""
    from toolsconnector.errors import ServerError

    with respx.mock(base_url="https://api.linear.app") as mock:
        mock.post("/graphql").mock(return_value=httpx.Response(500, json={"error": "internal"}))
        with pytest.raises(ServerError) as exc_info:
            await linear.aget_issue("i-1")
        assert exc_info.value.retry_eligible is True


@pytest.mark.asyncio
async def test_503_maps_to_server_error(linear: Linear) -> None:
    """HTTP 503 → ServerError (Linear downstream maintenance / overload)."""
    from toolsconnector.errors import ServerError

    with respx.mock(base_url="https://api.linear.app") as mock:
        mock.post("/graphql").mock(return_value=httpx.Response(503, json={"error": "unavailable"}))
        with pytest.raises(ServerError):
            await linear.aget_issue("i-1")


# ---------------------------------------------------------------------------
# 13. Round-4: GraphQL errors[] discrimination
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_graphql_errors_with_unknown_extension_code_raises_value_error(
    linear: Linear,
) -> None:
    """GraphQL errors[] at HTTP 200 with a non-RATELIMITED extension code
    must still raise ValueError (NOT RateLimitError). Pin the rate-limit
    detection's precision.
    """
    with respx.mock(base_url="https://api.linear.app") as mock:
        mock.post("/graphql").mock(
            return_value=httpx.Response(
                200,
                json={
                    "errors": [
                        {
                            "message": "Field unknown",
                            "extensions": {"code": "GRAPHQL_VALIDATION_FAILED"},
                        }
                    ]
                },
            )
        )
        with pytest.raises(ValueError) as exc_info:
            await linear.aget_issue("i-1")
        # Must NOT be a RateLimitError — pin the rate-limit detector's precision
        assert not isinstance(exc_info.value, RateLimitError)
        assert "Field unknown" in str(exc_info.value)


@pytest.mark.asyncio
async def test_graphql_errors_with_malformed_extensions_doesnt_crash(linear: Linear) -> None:
    """Linear's errors[].extensions is normally a dict, but defensive:
    if a buggy proxy strips/replaces it, _maybe_raise_linear_rate_limit
    must not crash. Falls through to ValueError as for any other error.
    """
    with respx.mock(base_url="https://api.linear.app") as mock:
        mock.post("/graphql").mock(
            return_value=httpx.Response(
                400,
                json={
                    "errors": [
                        # Malformed: extensions is a list, not a dict
                        {"message": "Bad", "extensions": ["RATELIMITED"]},
                        # Malformed: no extensions field at all
                        {"message": "Other"},
                    ]
                },
            )
        )
        # No RATELIMITED in any well-formed extension → falls through to
        # raise_typed_for_status, which maps 400 → ValidationError.
        from toolsconnector.errors import ValidationError

        with pytest.raises(ValidationError):
            await linear.aget_issue("i-1")


# ---------------------------------------------------------------------------
# 14. Round-4: sync wrappers + ToolKit dispatch + exclude_dangerous filter
# ---------------------------------------------------------------------------


def test_sync_wrapper_get_issue_works() -> None:
    """Linear's @action methods get both `aget_issue` (async) and
    `get_issue` (sync) auto-installed by BaseConnector. Pin the
    sync path explicitly.
    """
    resp = {
        "data": {
            "issue": {
                "id": "i-1",
                "identifier": "X-1",
                "title": "T",
                "priority": 0,
                "priorityLabel": "No priority",
                "team": {"id": "t"},
                "labels": {"nodes": []},
            }
        }
    }
    with respx.mock(base_url="https://api.linear.app") as mock:
        mock.post("/graphql").mock(return_value=httpx.Response(200, json=resp))
        n = Linear(credentials="lin_api_fake_test_token_xxxxxxxxxxxxxxxxxxxx")
        # No await — sync wrapper path
        issue = n.get_issue("i-1")
        assert issue.id == "i-1"


def test_toolkit_execute_round_trip_for_linear() -> None:
    """kit.execute(\"linear_get_issue\", ...) returns parseable JSON.
    Pins the ToolKit serialization layer for Linear like we did for Notion.
    """
    from toolsconnector.serve import ToolKit

    kit = ToolKit(["linear"], credentials={"linear": "lin_api_x"})
    resp = {
        "data": {
            "issue": {
                "id": "i-1",
                "identifier": "X-1",
                "title": "T",
                "priority": 0,
                "priorityLabel": "No priority",
                "team": {"id": "t"},
                "labels": {"nodes": []},
            }
        }
    }
    with respx.mock(base_url="https://api.linear.app") as mock:
        mock.post("/graphql").mock(return_value=httpx.Response(200, json=resp))
        raw = kit.execute("linear_get_issue", {"issue_id": "i-1"})
    parsed = json.loads(raw)
    assert parsed["id"] == "i-1"
    assert parsed["identifier"] == "X-1"


def test_exclude_dangerous_blocks_linear_write_actions() -> None:
    """ToolKit(exclude_dangerous=True) must filter out Linear's 6
    dangerous actions: create_issue, add_comment, delete_issue,
    create_label, update_project, delete_project.
    """
    from toolsconnector.errors import ConnectorNotConfiguredError
    from toolsconnector.serve import ToolKit

    safe = ToolKit(["linear"], credentials={"linear": "x"}, exclude_dangerous=True)
    full = ToolKit(["linear"], credentials={"linear": "x"}, exclude_dangerous=False)

    safe_names = {t["name"] for t in safe.list_tools() if t["name"].startswith("linear_")}
    full_names = {t["name"] for t in full.list_tools() if t["name"].startswith("linear_")}

    assert len(full_names) == 19
    assert len(safe_names) == 13  # 19 − 6 dangerous
    assert full_names - safe_names == {
        "linear_add_comment",
        "linear_create_issue",
        "linear_create_label",
        "linear_delete_issue",
        "linear_delete_project",
        "linear_update_project",
    }
    # And: a safe ToolKit refuses to EXECUTE a dangerous action
    with pytest.raises(ConnectorNotConfiguredError):
        safe.execute("linear_create_issue", {"team_id": "t", "title": "x"})


# ---------------------------------------------------------------------------
# 15. Round-4: concurrency + cancellation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_calls_on_same_instance_succeed(linear: Linear) -> None:
    """10 concurrent aget_issue calls on the same instance must all
    succeed — verifies no shared mutable state in the connector layer.
    """
    import asyncio as _aio

    resp = {
        "data": {
            "issue": {
                "id": "i-1",
                "identifier": "X-1",
                "title": "T",
                "priority": 0,
                "priorityLabel": "No priority",
                "team": {"id": "t"},
                "labels": {"nodes": []},
            }
        }
    }
    with respx.mock(base_url="https://api.linear.app") as mock:
        mock.post("/graphql").mock(return_value=httpx.Response(200, json=resp))
        results = await _aio.gather(*(linear.aget_issue("i-1") for _ in range(10)))
    assert len(results) == 10
    assert all(r.id == "i-1" for r in results)


@pytest.mark.asyncio
async def test_cancellation_mid_request_propagates_cleanly(linear: Linear) -> None:
    """asyncio.CancelledError mid-request must propagate without orphaning
    the httpx client or swallowing the cancellation.
    """
    import asyncio as _aio

    with respx.mock(base_url="https://api.linear.app", assert_all_called=False) as mock:

        async def slow_handler(request: httpx.Request) -> httpx.Response:
            await _aio.sleep(2)
            return httpx.Response(
                200,
                json={
                    "data": {
                        "issue": {
                            "id": "i",
                            "identifier": "X",
                            "title": "T",
                            "priority": 0,
                            "priorityLabel": "n",
                            "team": {"id": "t"},
                            "labels": {"nodes": []},
                        }
                    }
                },
            )

        mock.post("/graphql").mock(side_effect=slow_handler)
        task = _aio.create_task(linear.aget_issue("i-1"))
        await _aio.sleep(0.05)
        task.cancel()
        with pytest.raises(_aio.CancelledError):
            await task


# ---------------------------------------------------------------------------
# 16. Round-4: action edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_issue_with_no_fields_delegates_to_get_issue(linear: Linear) -> None:
    """update_issue with no input fields should fall through to the
    get_issue path (return current state) instead of sending an empty
    mutation. Pre-fix the previous version of the code had the same
    pattern but was untested.
    """
    resp = {
        "data": {
            "issue": {
                "id": "i-1",
                "identifier": "X-1",
                "title": "Unchanged",
                "priority": 0,
                "priorityLabel": "No priority",
                "team": {"id": "t"},
                "labels": {"nodes": []},
            }
        }
    }
    with respx.mock(base_url="https://api.linear.app") as mock:
        route = mock.post("/graphql").mock(return_value=httpx.Response(200, json=resp))
        issue = await linear.aupdate_issue("i-1")
        assert issue.title == "Unchanged"
        # Verify the emitted query was the GET, not an issueUpdate mutation
        body = json.loads(route.calls.last.request.read())
        assert "issueUpdate" not in body["query"]
        assert "issue(id: $id)" in body["query"]


@pytest.mark.asyncio
async def test_delete_issue_returns_bool(linear: Linear) -> None:
    """delete_issue: returns the mutation's success boolean."""
    resp = {"data": {"issueDelete": {"success": True}}}
    with respx.mock(base_url="https://api.linear.app") as mock:
        route = mock.post("/graphql").mock(return_value=httpx.Response(200, json=resp))
        result = await linear.adelete_issue(issue_id="i-1")
        assert result is True
        body = json.loads(route.calls.last.request.read())
        assert body["variables"] == {"id": "i-1"}
        # Verify the failure path too
    with respx.mock(base_url="https://api.linear.app") as mock:
        mock.post("/graphql").mock(
            return_value=httpx.Response(200, json={"data": {"issueDelete": {"success": False}}})
        )
        assert (await linear.adelete_issue(issue_id="missing")) is False


@pytest.mark.asyncio
async def test_list_issues_with_multiple_filters(linear: Linear) -> None:
    """team_id AND state filters together produce a compound IssueFilter."""
    empty = {
        "data": {"issues": {"nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}}}
    }
    with respx.mock(base_url="https://api.linear.app") as mock:
        route = mock.post("/graphql").mock(return_value=httpx.Response(200, json=empty))
        await linear.alist_issues(team_id="team-eng", state="In Progress")
        body = json.loads(route.calls.last.request.read())
        assert body["variables"]["filter"] == {
            "team": {"id": {"eq": "team-eng"}},
            "state": {"name": {"eq": "In Progress"}},
        }


@pytest.mark.asyncio
async def test_empty_paginated_result_has_clean_page_state(linear: Linear) -> None:
    """Empty results page → has_more=False, cursor=None, items=[]."""
    empty = {
        "data": {"issues": {"nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}}}
    }
    with respx.mock(base_url="https://api.linear.app") as mock:
        mock.post("/graphql").mock(return_value=httpx.Response(200, json=empty))
        result = await linear.alist_issues()
        assert result.items == []
        assert result.page_state.has_more is False
        assert result.page_state.cursor is None


# ---------------------------------------------------------------------------
# Spec audit (kept at the bottom)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 17. Round-5: OpenAI tools schema sweep — every action's JSON Schema validates
# ---------------------------------------------------------------------------


def test_all_linear_tool_schemas_validate_as_json_schema_draft7() -> None:
    """kit.to_openai_tools() exposes 19 Linear actions; every action's
    parameters block must be a valid JSON Schema (Draft 7). Catches
    schema-generation drift at unit-test time before LLM clients see it.
    """
    try:
        import jsonschema  # noqa: F401
    except ImportError:
        pytest.skip("jsonschema not installed")
    import jsonschema as _jsonschema

    from toolsconnector.serve import ToolKit

    kit = ToolKit(["linear"], credentials={"linear": "x"})
    tools = kit.to_openai_tools()
    linear_tools = [t for t in tools if t["function"]["name"].startswith("linear_")]
    assert len(linear_tools) == 19, f"expected 19 Linear tools, got {len(linear_tools)}"

    failures: list[str] = []
    for tool in linear_tools:
        fn = tool["function"]
        try:
            _jsonschema.Draft7Validator.check_schema(fn["parameters"])
        except Exception as e:
            failures.append(f"{fn['name']}: {e}")
    assert failures == [], f"Invalid schemas: {failures}"


# ---------------------------------------------------------------------------
# 18. Round-5: nullable nested objects (real-world Linear data shapes)
# ---------------------------------------------------------------------------
#
# Linear's GraphQL returns null for many nested objects in practice:
# unassigned issues have assignee=null; deleted users still appear in
# audit data with no name; comments by deactivated users have user=null;
# issues archived with their team gone have team=null. Pre-fix parsers
# may have assumed these are always present.


@pytest.mark.asyncio
async def test_get_issue_with_null_assignee_and_creator_and_project(linear: Linear) -> None:
    """Unassigned issue with no project — common in practice for triage.
    All three nullable nested objects (assignee, creator, project) come
    back as JSON null and must parse to None without raising.
    """
    resp = {
        "data": {
            "issue": {
                "id": "issue-unassigned",
                "identifier": "ENG-100",
                "title": "Triage me",
                "priority": 0,
                "priorityLabel": "No priority",
                "team": {"id": "team-eng"},
                "assignee": None,
                "creator": None,
                "project": None,
                "state": None,
                "labels": {"nodes": []},
            }
        }
    }
    with respx.mock(base_url="https://api.linear.app") as mock:
        mock.post("/graphql").mock(return_value=httpx.Response(200, json=resp))
        issue = await linear.aget_issue("issue-unassigned")
        assert issue.assignee is None
        assert issue.creator is None
        assert issue.project_id is None
        assert issue.state is None


@pytest.mark.asyncio
async def test_comment_with_null_user(linear: Linear) -> None:
    """A comment authored by a deactivated user / bot may return user=null."""
    resp = {
        "data": {
            "issue": {
                "comments": {
                    "nodes": [
                        {
                            "id": "c-orphan",
                            "body": "Comment from a deactivated account",
                            "createdAt": "2026-01-01T00:00:00Z",
                            "user": None,
                            "issue": {"id": "i-1"},
                        }
                    ]
                }
            }
        }
    }
    with respx.mock(base_url="https://api.linear.app") as mock:
        mock.post("/graphql").mock(return_value=httpx.Response(200, json=resp))
        comments = await linear.alist_issue_comments(issue_id="i-1")
        assert len(comments) == 1
        assert comments[0].user is None
        assert comments[0].body.startswith("Comment from")


@pytest.mark.asyncio
async def test_cycle_with_null_team(linear: Linear) -> None:
    """A cycle in an archived team may have team=null."""
    resp = {
        "data": {
            "cycle": {
                "id": "cycle-orphan",
                "number": 99,
                "name": "Old sprint",
                "team": None,
            }
        }
    }
    with respx.mock(base_url="https://api.linear.app") as mock:
        mock.post("/graphql").mock(return_value=httpx.Response(200, json=resp))
        cycle = await linear.aget_cycle("cycle-orphan")
        assert cycle.team_id is None


# ---------------------------------------------------------------------------
# 19. Round-5: 3-page pagination chain
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_issues_three_page_chain(linear: Linear) -> None:
    """Three-page sequence with cursor handoffs at each step. Round-4
    only verified 2-page; this pins that the chain continues correctly.
    """
    pages = [
        {
            "data": {
                "issues": {
                    "nodes": [
                        {
                            "id": f"p1-i{i}",
                            "identifier": f"ENG-{i}",
                            "title": "t",
                            "priority": 0,
                            "priorityLabel": "n",
                            "team": {"id": "t"},
                            "labels": {"nodes": []},
                        }
                        for i in range(3)
                    ],
                    "pageInfo": {"hasNextPage": True, "endCursor": "cursor-p2"},
                }
            }
        },
        {
            "data": {
                "issues": {
                    "nodes": [
                        {
                            "id": f"p2-i{i}",
                            "identifier": f"ENG-{i}",
                            "title": "t",
                            "priority": 0,
                            "priorityLabel": "n",
                            "team": {"id": "t"},
                            "labels": {"nodes": []},
                        }
                        for i in range(3)
                    ],
                    "pageInfo": {"hasNextPage": True, "endCursor": "cursor-p3"},
                }
            }
        },
        {
            "data": {
                "issues": {
                    "nodes": [
                        {
                            "id": "p3-i0",
                            "identifier": "ENG-0",
                            "title": "t",
                            "priority": 0,
                            "priorityLabel": "n",
                            "team": {"id": "t"},
                            "labels": {"nodes": []},
                        }
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        },
    ]
    with respx.mock(base_url="https://api.linear.app") as mock:
        route = mock.post("/graphql").mock(side_effect=[httpx.Response(200, json=p) for p in pages])
        all_items = []
        cursor: Optional[str] = None
        for _ in range(5):  # safety bound
            result = await linear.alist_issues(cursor=cursor)
            all_items.extend(result.items)
            if not result.page_state.has_more:
                break
            cursor = result.page_state.cursor
        assert len(all_items) == 7  # 3 + 3 + 1
        assert route.call_count == 3
        # Verify cursor flowed correctly: page 2 sent after="cursor-p2",
        # page 3 sent after="cursor-p3"
        assert json.loads(route.calls[1].request.read())["variables"]["after"] == "cursor-p2"
        assert json.loads(route.calls[2].request.read())["variables"]["after"] == "cursor-p3"


# ---------------------------------------------------------------------------
# 20. Round-5: Unicode + long-text round-trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unicode_emoji_and_long_text_round_trip_through_variables(linear: Linear) -> None:
    """create_issue with emoji + CJK + control chars + a long description.
    Variables-based transport must preserve every byte; the old f-string
    interpolation with hand-rolled escaping would have mangled NULL bytes
    and CJK at minimum.
    """
    title_unicode = "日本語🚀ñoño — issue with mixed CJK + emoji + accents"
    description_long = "This is line one.\nLine two — with em-dash.\n" + "x" * 4000
    resp = {
        "data": {
            "issueCreate": {
                "success": True,
                "issue": {
                    "id": "i-unicode",
                    "identifier": "ENG-1",
                    "title": title_unicode,
                    "priority": 0,
                    "priorityLabel": "No priority",
                    "team": {"id": "t"},
                    "labels": {"nodes": []},
                },
            }
        }
    }
    with respx.mock(base_url="https://api.linear.app") as mock:
        route = mock.post("/graphql").mock(return_value=httpx.Response(200, json=resp))
        await linear.acreate_issue(
            team_id="team-eng",
            title=title_unicode,
            description=description_long,
        )
        body = json.loads(route.calls.last.request.read())
        # Title + description must round-trip byte-for-byte through variables
        assert body["variables"]["input"]["title"] == title_unicode
        assert body["variables"]["input"]["description"] == description_long
        # And they MUST NOT have leaked into the query text
        assert title_unicode not in body["query"]
        assert "x" * 4000 not in body["query"]


# ---------------------------------------------------------------------------
# 21. Round-5: lifecycle + multi-instance isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_setup_and_teardown_are_idempotent_no_ops(linear: Linear) -> None:
    """Linear doesn't override _setup/_teardown — verify the BaseConnector
    defaults are no-ops that can be called multiple times safely (callers
    might invoke them via context-manager + manual paths).
    """
    # Already _setup once via fixture. Calling again must not raise.
    await linear._setup()
    await linear._setup()
    await linear._teardown()
    await linear._teardown()
    # And the instance is still usable
    resp = {"data": {"teams": {"nodes": []}}}
    with respx.mock(base_url="https://api.linear.app") as mock:
        mock.post("/graphql").mock(return_value=httpx.Response(200, json=resp))
        teams = await linear.alist_teams()
        assert teams == []


def test_multi_instance_isolation() -> None:
    """Two Linear connectors with different credentials must produce
    independent state — pins the multi-tenant SaaS pattern documented
    in docs/guides/credentials.md.
    """
    a = Linear(credentials="lin_api_aaaa" + "A" * 28)
    b = Linear(credentials="lin_api_bbbb" + "B" * 28)
    assert a is not b
    assert a._credentials != b._credentials


# ---------------------------------------------------------------------------
# 22. Round-5: credential edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_credentials_produces_unauth_at_api(linear: Linear) -> None:
    """Empty string credential is allowed at construction (BYOK pattern),
    fails at the API as 401 → InvalidCredentialsError. Tests the auth
    flow's defensive boundary.
    """
    n = Linear(credentials="")
    await n._setup()
    with respx.mock(base_url="https://api.linear.app") as mock:
        mock.post("/graphql").mock(return_value=httpx.Response(401, json={"error": "unauthorized"}))
        with pytest.raises(InvalidCredentialsError):
            await n.aget_issue("i-1")
    await n._teardown()


@pytest.mark.asyncio
async def test_credentials_with_leading_trailing_whitespace_passed_through(linear: Linear) -> None:
    """If the caller passes a credential with whitespace, the connector
    sends it verbatim. Linear's API will reject the token; the connector
    does not silently strip (BYOK + zero magic principle).
    """
    bad_token = "  lin_api_with_padding  "
    n = Linear(credentials=bad_token)
    await n._setup()
    with respx.mock(base_url="https://api.linear.app") as mock:
        route = mock.post("/graphql").mock(
            return_value=httpx.Response(401, json={"error": "unauthorized"})
        )
        try:
            await n.aget_issue("i-1")
        except InvalidCredentialsError:
            pass
        # Auth header carries the value as-is — connector does no munging
        assert route.calls.last.request.headers["authorization"] == bad_token
    await n._teardown()


# ---------------------------------------------------------------------------
# 23. Round-5: mutation success-True but result=None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mutation_success_true_but_issue_null_raises(linear: Linear) -> None:
    """Linear normally returns success=True alongside the created issue,
    but a rare race (or buggy proxy) could produce success=True + issue=None.
    The connector should fail loudly rather than silently returning a
    half-initialized model.
    """
    resp = {"data": {"issueCreate": {"success": True, "issue": None}}}
    with respx.mock(base_url="https://api.linear.app") as mock:
        mock.post("/graphql").mock(return_value=httpx.Response(200, json=resp))
        # _parse_issue requires issue["id"] — raises clearly. The pre-fix
        # behavior would AttributeError on `result["issue"]["id"]`; today it
        # raises a TypeError because we pass None to _parse_issue. Either
        # way the failure is loud and traceable, not silent corruption.
        with pytest.raises((TypeError, KeyError, AttributeError)):
            await linear.acreate_issue(team_id="t", title="x")


# ---------------------------------------------------------------------------
# 24. Round-5: hardcoded page-size in list_labels / get_workflow_states
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_labels_uses_max_page_size(linear: Linear) -> None:
    """list_labels doesn't expose pagination — it requests the max
    (250) and returns whatever fits. Pin that we send first=250 so a
    refactor that drops the explicit value would be caught.
    """
    empty = {"data": {"issueLabels": {"nodes": []}}}
    with respx.mock(base_url="https://api.linear.app") as mock:
        route = mock.post("/graphql").mock(return_value=httpx.Response(200, json=empty))
        await linear.alist_labels()
        body = json.loads(route.calls.last.request.read())
        assert body["variables"]["first"] == 250  # _MAX_PAGE_SIZE


@pytest.mark.asyncio
async def test_get_workflow_states_uses_first_100(linear: Linear) -> None:
    """get_workflow_states uses first: 100 (workflow states per team
    are rarely >25 in practice; 100 is generous). Pin the value so a
    refactor doesn't accidentally drop it.
    """
    empty = {"data": {"workflowStates": {"nodes": []}}}
    with respx.mock(base_url="https://api.linear.app") as mock:
        route = mock.post("/graphql").mock(return_value=httpx.Response(200, json=empty))
        await linear.aget_workflow_states(team_id="t")
        body = json.loads(route.calls.last.request.read())
        assert body["variables"]["first"] == 100


# ---------------------------------------------------------------------------
# 25. Round-5: schema-drift tolerance — extra unknown fields at any depth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deep_unknown_fields_dont_crash_parse(linear: Linear) -> None:
    """Linear adds fields without major-version bumps. Test that extra
    fields at multiple nesting depths (top-level, nested object, list
    item) are all silently ignored — the extra='ignore' guarantee holds
    at every level.
    """
    resp = {
        "data": {
            "issue": {
                "id": "i-1",
                "identifier": "X-1",
                "title": "T",
                "priority": 0,
                "priorityLabel": "n",
                "futureTopLevelField": {"nested": "value", "another": 42},
                "team": {"id": "t", "futureTeamField": "x"},
                "assignee": {
                    "id": "u-1",
                    "name": "Alice",
                    "active": True,
                    "futureUserField": "added-next-quarter",
                },
                "labels": {
                    "nodes": [
                        {
                            "id": "l-1",
                            "name": "bug",
                            "color": "#f00",
                            "futureLabelField": ["new", "values"],
                        }
                    ]
                },
            }
        }
    }
    with respx.mock(base_url="https://api.linear.app") as mock:
        mock.post("/graphql").mock(return_value=httpx.Response(200, json=resp))
        issue = await linear.aget_issue("i-1")
        # Modeled fields still populated despite extra fields everywhere
        assert issue.id == "i-1"
        assert issue.assignee is not None
        assert issue.assignee.name == "Alice"
        assert len(issue.labels) == 1
        assert issue.labels[0].name == "bug"


# ---------------------------------------------------------------------------
# 26. Round-5: defensive — orderBy hardcoded value matches docs enum
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_issues_orderby_updated_at_is_emitted(linear: Linear) -> None:
    """Per Linear's pagination docs, orderBy accepts only `createdAt`
    or `updatedAt`. Our list_issues + list_cycles hardcode `updatedAt`
    (most useful for AI agents — surfaces recently-changed work first).
    Pin the value so a future "modernize" can't silently default-back to
    createdAt.
    """
    empty = {
        "data": {"issues": {"nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}}}
    }
    with respx.mock(base_url="https://api.linear.app") as mock:
        route = mock.post("/graphql").mock(return_value=httpx.Response(200, json=empty))
        await linear.alist_issues()
        body = json.loads(route.calls.last.request.read())
        assert "orderBy: updatedAt" in body["query"]


# ---------------------------------------------------------------------------
# 27. Round-5: MCP handler dispatch for Linear (without FastMCP dependency)
# ---------------------------------------------------------------------------
#
# Mirrors the Notion MCP-handler tests. _make_tool_handler is what
# `kit.serve_mcp()` uses internally — verifying its dispatch contract
# closes the MCP integration gap without requiring the `mcp` extra
# (which needs Python 3.10+).


def test_mcp_handler_signature_matches_every_linear_action() -> None:
    """Every Linear action's MCP handler must have a synthetic signature
    where required params have no default and optional params default to
    None. FastMCP introspects this signature to build the per-tool JSON
    Schema for LLM clients.
    """
    import inspect as _inspect

    from toolsconnector.serve import ToolKit
    from toolsconnector.serve.mcp import _make_tool_handler

    kit = ToolKit(["linear"], credentials={"linear": "x"})
    entries = [e for e in kit.list_tools() if e["name"].startswith("linear_")]
    assert len(entries) == 19

    problems = []
    for entry in entries:
        handler = _make_tool_handler(kit, entry["name"], entry["input_schema"])
        sig = _inspect.signature(handler)
        required = set(entry["input_schema"].get("required", []))
        for pname, param in sig.parameters.items():
            if pname in required and param.default is not _inspect.Parameter.empty:
                problems.append(f"{entry['name']}.{pname}: required but has default")
            if pname not in required and param.default is _inspect.Parameter.empty:
                problems.append(f"{entry['name']}.{pname}: optional but no default")
    assert problems == [], f"signature problems: {problems}"


def test_mcp_handler_round_trip_for_get_issue() -> None:
    """End-to-end: build the MCP handler for linear_get_issue, invoke it,
    get back a JSON string — same contract FastMCP relies on.
    """
    import asyncio as _aio

    from toolsconnector.serve import ToolKit
    from toolsconnector.serve.mcp import _make_tool_handler

    kit = ToolKit(["linear"], credentials={"linear": "x"})
    entry = next(e for e in kit.list_tools() if e["name"] == "linear_get_issue")
    handler = _make_tool_handler(kit, "linear_get_issue", entry["input_schema"])

    resp = {
        "data": {
            "issue": {
                "id": "i-1",
                "identifier": "ENG-1",
                "title": "T",
                "priority": 0,
                "priorityLabel": "No priority",
                "team": {"id": "t"},
                "labels": {"nodes": []},
            }
        }
    }
    with respx.mock(base_url="https://api.linear.app") as mock:
        mock.post("/graphql").mock(return_value=httpx.Response(200, json=resp))
        result = _aio.run(handler(issue_id="i-1"))

    assert isinstance(result, str)
    parsed = json.loads(result)
    assert parsed["id"] == "i-1"


def test_mcp_handler_propagates_typed_transport_error() -> None:
    """The round-2 typed transport-error mapping must surface through
    the MCP handler too (FastMCP serializes the exception to JSON-RPC
    error for the client).
    """
    import asyncio as _aio

    from toolsconnector.errors import ConnectionError as TCConnectionError
    from toolsconnector.serve import ToolKit
    from toolsconnector.serve.mcp import _make_tool_handler

    kit = ToolKit(["linear"], credentials={"linear": "x"})
    entry = next(e for e in kit.list_tools() if e["name"] == "linear_get_issue")
    handler = _make_tool_handler(kit, "linear_get_issue", entry["input_schema"])

    with respx.mock(base_url="https://api.linear.app") as mock:
        mock.post("/graphql").mock(side_effect=httpx.ConnectError("down"))
        with pytest.raises(TCConnectionError):
            _aio.run(handler(issue_id="i-1"))


def test_mcp_handler_propagates_rate_limit() -> None:
    """Linear's HTTP-400 + RATELIMITED envelope (round-3 fix) surfaces
    through the MCP handler as typed RateLimitError. The MCP handler
    path goes through ToolKit's retry middleware, which may retry the
    request several times before propagating the error — by the final
    raise, ``retry_after_seconds`` may have ticked to 0. We only assert
    the typed-error class makes it through; the precise retry_after
    timing is verified by ``test_rate_limited_raises_rate_limit_error``
    which exercises the raw connector path without middleware.
    """
    import asyncio as _aio

    from toolsconnector.serve import ToolKit
    from toolsconnector.serve.mcp import _make_tool_handler

    kit = ToolKit(["linear"], credentials={"linear": "x"})
    entry = next(e for e in kit.list_tools() if e["name"] == "linear_get_issue")
    handler = _make_tool_handler(kit, "linear_get_issue", entry["input_schema"])

    with respx.mock(base_url="https://api.linear.app") as mock:
        mock.post("/graphql").mock(
            return_value=httpx.Response(
                400,
                headers={"X-RateLimit-Requests-Reset": "9999999999999"},
                json={
                    "errors": [
                        {
                            "message": "Rate limit exceeded",
                            "extensions": {"code": "RATELIMITED"},
                        }
                    ]
                },
            )
        )
        with pytest.raises(RateLimitError) as exc_info:
            _aio.run(handler(issue_id="i-1"))
        # Verify the typed exception details survived the middleware pipeline
        assert exc_info.value.connector == "linear"
        assert exc_info.value.upstream_status == 400


def test_get_spec_exposes_all_19_actions_with_descriptions() -> None:
    """ConnectorSpec includes every @action, each with a non-empty
    description. Drift in either count or description detected by this
    test the same way the dangerous-flag test catches missing flags.
    """
    spec = Linear.get_spec()
    assert len(spec.actions) == 19
    for action_name, action in spec.actions.items():
        assert action.description, f"action {action_name} has empty description"
