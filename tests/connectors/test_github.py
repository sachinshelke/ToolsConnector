"""End-to-end tests for the GitHub connector using respx.

Same pattern as tests/connectors/test_slack.py but exercises GitHub's
distinct semantics:

  - **REST status codes** (200/404/403) instead of always-200 +
    body-level `{"ok": false}`.
  - **Link-header pagination** (`<...?page=2>; rel="next"`) instead
    of `response_metadata.next_cursor`.
  - **Bearer token + custom Accept header** (`application/vnd.github+json`)
    + the `X-GitHub-Api-Version` header.

Together with test_slack.py, these two files cover the two dominant
patterns in this codebase: status-code-based auth (most REST APIs) and
body-flag-based auth (Slack-style).
"""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
import respx

from toolsconnector.connectors.github import GitHub
from toolsconnector.errors import InvalidCredentialsError, NotFoundError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def github() -> GitHub:
    """GitHub connector with a fake personal-access token.

    Token never reaches api.github.com because respx intercepts at the
    httpx transport layer.
    """
    connector = GitHub(credentials="ghp_fake_test_token")
    await connector._setup()
    yield connector
    await connector._teardown()


# ---------------------------------------------------------------------------
# 1. Happy path — read action
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_repo_happy_path(github: GitHub) -> None:
    """get_repo: GET /repos/{owner}/{repo} → Repository model."""
    with respx.mock(base_url="https://api.github.com", assert_all_called=True) as respx_mock:
        route = respx_mock.get("/repos/sachinshelke/ToolsConnector").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 12345,
                    "name": "ToolsConnector",
                    "full_name": "sachinshelke/ToolsConnector",
                    "owner": {"login": "sachinshelke", "id": 869601, "type": "User"},
                    "private": False,
                    "description": "Connect APIs the easy way",
                    "html_url": "https://github.com/sachinshelke/ToolsConnector",
                    "default_branch": "main",
                    "stargazers_count": 42,
                    "forks_count": 3,
                    "open_issues_count": 0,
                },
            )
        )

        repo = await github.aget_repo(owner="sachinshelke", repo="ToolsConnector")

        assert repo.full_name == "sachinshelke/ToolsConnector"
        assert repo.default_branch == "main"
        assert repo.stargazers_count == 42

        # Auth + GitHub-specific headers were applied
        request = route.calls.last.request
        assert request.headers["authorization"] == "Bearer ghp_fake_test_token"
        assert request.headers["accept"] == "application/vnd.github+json"
        assert request.headers["x-github-api-version"] == "2022-11-28"


# ---------------------------------------------------------------------------
# 2. Happy path — write action with body assertion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_repo_sends_correct_body(github: GitHub) -> None:
    """create_repo: POST /user/repos → request body includes the params we set.

    The actual created Repository is the canonical response. The test
    primarily asserts we POST the right body — that's what bugs out
    most when an API field gets renamed.
    """
    with respx.mock(base_url="https://api.github.com") as respx_mock:
        route = respx_mock.post("/user/repos").mock(
            return_value=httpx.Response(
                201,
                json={
                    "id": 99,
                    "name": "new-repo",
                    "full_name": "sachinshelke/new-repo",
                    "owner": {"login": "sachinshelke", "id": 869601, "type": "User"},
                    "private": True,
                    "description": "test",
                    "html_url": "https://github.com/sachinshelke/new-repo",
                    "default_branch": "main",
                    "stargazers_count": 0,
                    "forks_count": 0,
                    "open_issues_count": 0,
                },
            )
        )

        repo = await github.acreate_repo(
            name="new-repo", description="test", private=True, auto_init=True
        )

        assert repo.name == "new-repo"
        assert repo.private is True

        body = route.calls.last.request.read()
        # Required fields present in the request body
        assert b'"name":"new-repo"' in body
        assert b'"private":true' in body
        assert b'"auto_init":true' in body
        assert b'"description":"test"' in body


# ---------------------------------------------------------------------------
# 3. Error mapping — HTTP status → typed exceptions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_404_raises_not_found_error(github: GitHub) -> None:
    """GitHub 404 → typed :class:`NotFoundError` (was bare
    ``httpx.HTTPStatusError`` before the framework-wide error mapping
    landed in 0.3.5). Agents can now ``except NotFoundError`` instead
    of string-parsing the status code.
    """
    with respx.mock(base_url="https://api.github.com") as respx_mock:
        respx_mock.get("/repos/missing/missing").mock(
            return_value=httpx.Response(
                404, json={"message": "Not Found", "documentation_url": "..."}
            )
        )

        with pytest.raises(NotFoundError) as exc_info:
            await github.aget_repo(owner="missing", repo="missing")

        err = exc_info.value
        assert err.connector == "github"
        assert err.upstream_status == 404
        assert "Not Found" in err.details["body_preview"]


@pytest.mark.asyncio
async def test_401_raises_invalid_credentials_error(github: GitHub) -> None:
    """Invalid token → 401 → :class:`InvalidCredentialsError`.

    GitHub's "Bad credentials" body doesn't contain an "expired" marker,
    so the helper picks the more generic ``InvalidCredentialsError``
    rather than ``TokenExpiredError`` — correct because PATs don't
    expire silently the way OAuth access tokens do.
    """
    with respx.mock(base_url="https://api.github.com") as respx_mock:
        respx_mock.get("/repos/owner/repo").mock(
            return_value=httpx.Response(401, json={"message": "Bad credentials"})
        )

        with pytest.raises(InvalidCredentialsError) as exc_info:
            await github.aget_repo(owner="owner", repo="repo")

        assert exc_info.value.connector == "github"
        assert exc_info.value.upstream_status == 401


# ---------------------------------------------------------------------------
# 4. Pagination — Link-header cursor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_issues_link_header_pagination(github: GitHub) -> None:
    """GitHub paginates via the Link response header:

        Link: <https://api.github.com/repos/x/y/issues?page=2>; rel="next",
              <https://api.github.com/repos/x/y/issues?page=3>; rel="last"

    `_build_page_state` parses this and exposes the next URL as
    PageState.cursor. Page 2 of a 2-page response has no Link header
    → has_more=False, cursor=None.
    """
    issue_template = {
        "id": 1,
        "number": 1,
        "title": "first issue",
        "state": "open",
        "html_url": "https://github.com/owner/repo/issues/1",
        "user": {"login": "alice", "id": 100, "type": "User"},
        "labels": [],
        "assignees": [],
        "comments": 0,
        "created_at": "2026-04-23T10:00:00Z",
        "updated_at": "2026-04-23T10:00:00Z",
    }

    with respx.mock(base_url="https://api.github.com") as respx_mock:
        respx_mock.get("/repos/owner/repo/issues").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json=[issue_template, {**issue_template, "id": 2, "number": 2}],
                    headers={
                        "Link": (
                            '<https://api.github.com/repos/owner/repo/issues?page=2>; rel="next", '
                            '<https://api.github.com/repos/owner/repo/issues?page=2>; rel="last"'
                        )
                    },
                ),
                httpx.Response(
                    200,
                    json=[{**issue_template, "id": 3, "number": 3}],
                    # No Link header on the last page
                ),
            ]
        )

        page1 = await github.alist_issues(owner="owner", repo="repo")
        assert len(page1.items) == 2
        assert page1.page_state.has_more is True
        assert "page=2" in (page1.page_state.cursor or "")

        page2 = await github.alist_issues(owner="owner", repo="repo", page=page1.page_state.cursor)
        assert len(page2.items) == 1
        assert page2.page_state.has_more is False
        assert page2.page_state.cursor is None


# ---------------------------------------------------------------------------
# 5. Spec metadata — dangerous flag
# ---------------------------------------------------------------------------


def test_dangerous_actions_are_flagged() -> None:
    """create_repo, fork_repo, etc. modify state → must be dangerous."""
    spec = GitHub.get_spec()
    assert spec.actions["create_repo"].dangerous is True
    assert spec.actions["fork_repo"].dangerous is True
    assert spec.actions["create_issue"].dangerous is True
    # Read-only actions should NOT be dangerous
    assert spec.actions["get_repo"].dangerous is False
    assert spec.actions["list_issues"].dangerous is False
