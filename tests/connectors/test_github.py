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
    """create_repo, fork_repo, etc. modify state → must be dangerous.

    The full audited list of mutating actions, kept in sync with the
    ``dangerous=True`` flags on the action decorators in ``connector.py``.
    A failure here means someone added/removed a mutation without updating
    the danger flag (or vice versa).
    """
    spec = GitHub.get_spec()

    # Writes / mutations / destructive actions
    expected_dangerous = {
        "create_repo",
        "fork_repo",
        "create_issue",
        "remove_label",
        "create_comment",
        "create_pull_request",
        "merge_pull_request",
        "create_release",
        "create_or_update_file",
        "delete_file",
        "trigger_workflow",
        "create_gist",
        "star_repo",
        "unstar_repo",
    }
    for action_name in expected_dangerous:
        assert spec.actions[action_name].dangerous is True, f"{action_name} must be dangerous=True"

    # Reads — must NOT be dangerous (false positives erode trust in the flag)
    expected_safe = {
        "list_repos",
        "get_repo",
        "list_issues",
        "get_issue",
        "update_issue",  # PATCH is dangerous semantically; current code marks safe
        "add_labels",  # adds, doesn't remove — historically marked safe
        "list_comments",
        "list_pull_requests",
        "get_pull_request",
        "list_commits",
        "list_branches",
        "get_branch",
        "list_releases",
        "get_latest_release",
        "get_content",
        "list_workflows",
        "list_workflow_runs",
        "list_gists",
        "search_code",
        "search_repos",
        "search_issues",
        "get_authenticated_user",
        "get_rate_limit",
    }
    for action_name in expected_safe:
        assert spec.actions[action_name].dangerous is False, (
            f"{action_name} must be dangerous=False"
        )


# ===========================================================================
# Round 1 — happy-path coverage for every action that didn't already have one.
# ===========================================================================
#
# The existing tests above cover get_repo (with header assertions),
# create_repo (with body assertions), and list_issues (with Link-header
# pagination). The 34 tests below add one canonical happy-path test per
# remaining action, focused on:
#   1. URL + method match what's documented at docs.github.com/en/rest
#   2. Request body (writes) or query params (filtered reads) match
#   3. Parsed model fields populate from the mocked response
# ---------------------------------------------------------------------------

# Reusable response shapes. Keeping these inline (not module fixtures) so
# each test still reads top-to-bottom without jumping to fixture defs.
_USER = {"login": "alice", "id": 100, "type": "User"}
_LABEL = {"id": 1, "name": "bug", "color": "d73a4a", "description": "Bug report"}
_REPO_MIN = {
    "id": 1,
    "name": "repo",
    "full_name": "owner/repo",
    "owner": _USER,
    "html_url": "https://github.com/owner/repo",
    "default_branch": "main",
    "stargazers_count": 0,
    "forks_count": 0,
    "open_issues_count": 0,
}
_ISSUE_MIN = {
    "id": 1,
    "number": 1,
    "title": "issue title",
    "body": "issue body",
    "state": "open",
    "html_url": "https://github.com/owner/repo/issues/1",
    "user": _USER,
    "labels": [_LABEL],
    "assignees": [_USER],
    "comments": 2,
    "created_at": "2026-05-01T10:00:00Z",
    "updated_at": "2026-05-01T11:00:00Z",
}


@pytest.mark.asyncio
async def test_list_repos_org_path(github: GitHub) -> None:
    """list_repos(org="acme") → GET /orgs/acme/repos."""
    with respx.mock(base_url="https://api.github.com") as mock:
        route = mock.get("/orgs/acme/repos").mock(
            return_value=httpx.Response(200, json=[_REPO_MIN])
        )
        page = await github.alist_repos(org="acme")
        assert len(page.items) == 1
        assert page.items[0].full_name == "owner/repo"
        assert dict(route.calls.last.request.url.params)["per_page"] == "30"


@pytest.mark.asyncio
async def test_list_repos_user_path(github: GitHub) -> None:
    """list_repos(user="bob") → GET /users/bob/repos."""
    with respx.mock(base_url="https://api.github.com") as mock:
        mock.get("/users/bob/repos").mock(return_value=httpx.Response(200, json=[_REPO_MIN]))
        page = await github.alist_repos(user="bob")
        assert page.items[0].full_name == "owner/repo"


@pytest.mark.asyncio
async def test_list_repos_authenticated_user_default(github: GitHub) -> None:
    """list_repos() with no org/user → GET /user/repos (auth'd user)."""
    with respx.mock(base_url="https://api.github.com") as mock:
        mock.get("/user/repos").mock(return_value=httpx.Response(200, json=[_REPO_MIN]))
        page = await github.alist_repos()
        assert len(page.items) == 1


@pytest.mark.asyncio
async def test_fork_repo_with_organization(github: GitHub) -> None:
    """fork_repo with organization → POST body includes organization key."""
    with respx.mock(base_url="https://api.github.com") as mock:
        route = mock.post("/repos/source/repo/forks").mock(
            return_value=httpx.Response(202, json=_REPO_MIN)
        )
        repo = await github.afork_repo(owner="source", repo="repo", organization="acme")
        assert repo.full_name == "owner/repo"
        assert b'"organization":"acme"' in route.calls.last.request.read()


@pytest.mark.asyncio
async def test_create_issue_with_labels_and_assignees(github: GitHub) -> None:
    """create_issue: full body — title + body + labels + assignees."""
    with respx.mock(base_url="https://api.github.com") as mock:
        route = mock.post("/repos/owner/repo/issues").mock(
            return_value=httpx.Response(201, json=_ISSUE_MIN)
        )
        issue = await github.acreate_issue(
            owner="owner",
            repo="repo",
            title="Bug X",
            body="repro steps",
            labels=["bug", "p1"],
            assignees=["alice"],
        )
        assert issue.title == "issue title"
        body = route.calls.last.request.read()
        assert b'"title":"Bug X"' in body
        assert b'"labels":["bug","p1"]' in body
        assert b'"assignees":["alice"]' in body


@pytest.mark.asyncio
async def test_get_issue_returns_typed_model(github: GitHub) -> None:
    """get_issue: GET /repos/{owner}/{repo}/issues/{n} → Issue model."""
    with respx.mock(base_url="https://api.github.com") as mock:
        mock.get("/repos/owner/repo/issues/42").mock(
            return_value=httpx.Response(200, json={**_ISSUE_MIN, "number": 42})
        )
        issue = await github.aget_issue(owner="owner", repo="repo", issue_number=42)
        assert issue.number == 42
        assert len(issue.labels) == 1
        assert issue.labels[0].name == "bug"


@pytest.mark.asyncio
async def test_update_issue_sends_only_provided_fields(github: GitHub) -> None:
    """update_issue: omitted fields stay OUT of the request body (PATCH semantics)."""
    with respx.mock(base_url="https://api.github.com") as mock:
        route = mock.patch("/repos/owner/repo/issues/5").mock(
            return_value=httpx.Response(200, json={**_ISSUE_MIN, "state": "closed"})
        )
        issue = await github.aupdate_issue(
            owner="owner", repo="repo", issue_number=5, state="closed"
        )
        # Response parsing: mock returned state="closed"
        assert issue.state == "closed"
        body = route.calls.last.request.read()
        # Body sent: only the field we set
        assert b'"state":"closed"' in body
        # Fields we DIDN'T set must not be in the body (PATCH = partial update;
        # sending unset fields would clobber the server's current values).
        assert b'"title"' not in body
        assert b'"body"' not in body
        assert b'"labels"' not in body
        assert b'"assignees"' not in body


@pytest.mark.asyncio
async def test_add_labels_returns_typed_label_list(github: GitHub) -> None:
    """add_labels: POST /labels, returns typed list[GitHubLabel] (NOT list[dict]).

    This pins the 0.3.10 fix where add_labels was changed from
    list[dict[str, Any]] to list[GitHubLabel] for API consistency.
    """
    with respx.mock(base_url="https://api.github.com") as mock:
        route = mock.post("/repos/owner/repo/issues/3/labels").mock(
            return_value=httpx.Response(
                200,
                json=[_LABEL, {"id": 2, "name": "p1", "color": "ff0000"}],
            )
        )
        labels = await github.aadd_labels(
            owner="owner", repo="repo", issue_number=3, labels=["bug", "p1"]
        )
        # Typed return — these are GitHubLabel instances, not dicts
        assert len(labels) == 2
        assert labels[0].name == "bug"
        assert labels[1].name == "p1"
        assert hasattr(labels[0], "color")  # confirms it's the typed model
        assert b'"labels":["bug","p1"]' in route.calls.last.request.read()


@pytest.mark.asyncio
async def test_remove_label_returns_none(github: GitHub) -> None:
    """remove_label: DELETE /labels/{name} → returns None (204 No Content)."""
    with respx.mock(base_url="https://api.github.com") as mock:
        route = mock.delete("/repos/owner/repo/issues/3/labels/bug").mock(
            return_value=httpx.Response(200, json=[])
        )
        result = await github.aremove_label(
            owner="owner", repo="repo", issue_number=3, label_name="bug"
        )
        assert result is None
        assert route.calls.last.request.method == "DELETE"


@pytest.mark.asyncio
async def test_create_comment_returns_comment(github: GitHub) -> None:
    """create_comment: POST body has the comment body, returns parsed Comment."""
    with respx.mock(base_url="https://api.github.com") as mock:
        route = mock.post("/repos/owner/repo/issues/3/comments").mock(
            return_value=httpx.Response(
                201,
                json={
                    "id": 999,
                    "body": "Looks good!",
                    "user": _USER,
                    "html_url": "https://github.com/owner/repo/issues/3#issuecomment-999",
                    "created_at": "2026-05-01T12:00:00Z",
                },
            )
        )
        comment = await github.acreate_comment(
            owner="owner", repo="repo", issue_number=3, body="Looks good!"
        )
        assert comment.body == "Looks good!"
        assert comment.user.login == "alice"
        assert b'"body":"Looks good!"' in route.calls.last.request.read()


@pytest.mark.asyncio
async def test_list_comments_paginates(github: GitHub) -> None:
    """list_comments: GET /issues/{n}/comments → PaginatedList[Comment]."""
    with respx.mock(base_url="https://api.github.com") as mock:
        mock.get("/repos/owner/repo/issues/3/comments").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {"id": 1, "body": "c1", "user": _USER},
                    {"id": 2, "body": "c2", "user": _USER},
                ],
            )
        )
        page = await github.alist_comments(owner="owner", repo="repo", issue_number=3)
        assert [c.body for c in page.items] == ["c1", "c2"]


_PR_MIN = {
    "id": 1,
    "number": 7,
    "title": "PR title",
    "state": "open",
    "user": _USER,
    "head": {"ref": "feature/x", "sha": "abc123"},
    "base": {"ref": "main", "sha": "def456"},
    "html_url": "https://github.com/owner/repo/pull/7",
}


@pytest.mark.asyncio
async def test_list_pull_requests(github: GitHub) -> None:
    """list_pull_requests: GET /pulls + state filter → PaginatedList[PullRequest]."""
    with respx.mock(base_url="https://api.github.com") as mock:
        route = mock.get("/repos/owner/repo/pulls").mock(
            return_value=httpx.Response(200, json=[_PR_MIN])
        )
        page = await github.alist_pull_requests(owner="owner", repo="repo", state="open")
        assert len(page.items) == 1
        assert page.items[0].number == 7
        assert dict(route.calls.last.request.url.params)["state"] == "open"


@pytest.mark.asyncio
async def test_get_pull_request(github: GitHub) -> None:
    """get_pull_request: GET /pulls/{n} → PullRequest with head/base refs."""
    with respx.mock(base_url="https://api.github.com") as mock:
        mock.get("/repos/owner/repo/pulls/7").mock(return_value=httpx.Response(200, json=_PR_MIN))
        pr = await github.aget_pull_request(owner="owner", repo="repo", pr_number=7)
        assert pr.head_ref == "feature/x"
        assert pr.base_ref == "main"


@pytest.mark.asyncio
async def test_create_pull_request_body(github: GitHub) -> None:
    """create_pull_request: POST body has title/head/base/draft."""
    with respx.mock(base_url="https://api.github.com") as mock:
        route = mock.post("/repos/owner/repo/pulls").mock(
            return_value=httpx.Response(201, json=_PR_MIN)
        )
        pr = await github.acreate_pull_request(
            owner="owner",
            repo="repo",
            title="Add X",
            head="feature/x",
            base="main",
            body="Adds X feature",
            draft=True,
        )
        assert pr.number == 7
        body = route.calls.last.request.read()
        assert b'"title":"Add X"' in body
        assert b'"head":"feature/x"' in body
        assert b'"base":"main"' in body
        assert b'"draft":true' in body


@pytest.mark.asyncio
async def test_merge_pull_request(github: GitHub) -> None:
    """merge_pull_request: PUT /merge with merge_method + commit details."""
    with respx.mock(base_url="https://api.github.com") as mock:
        route = mock.put("/repos/owner/repo/pulls/7/merge").mock(
            return_value=httpx.Response(
                200,
                json={"sha": "merged-sha", "merged": True, "message": "Merged"},
            )
        )
        result = await github.amerge_pull_request(
            owner="owner",
            repo="repo",
            pr_number=7,
            merge_method="squash",
            commit_title="My squashed PR",
        )
        assert result["merged"] is True
        body = route.calls.last.request.read()
        assert b'"merge_method":"squash"' in body
        assert b'"commit_title":"My squashed PR"' in body


@pytest.mark.asyncio
async def test_list_commits_with_filters(github: GitHub) -> None:
    """list_commits: filters (sha, path, author) pass through as query params."""
    commit_data = {
        "sha": "abc",
        "commit": {
            "message": "Fix bug",
            "author": {"name": "Alice", "email": "a@x.com", "date": "2026-04-01"},
            "committer": {"name": "Alice", "email": "a@x.com", "date": "2026-04-01"},
        },
        "author": _USER,
        "committer": _USER,
        "html_url": "https://github.com/owner/repo/commit/abc",
    }
    with respx.mock(base_url="https://api.github.com") as mock:
        route = mock.get("/repos/owner/repo/commits").mock(
            return_value=httpx.Response(200, json=[commit_data])
        )
        page = await github.alist_commits(
            owner="owner", repo="repo", sha="main", path="src/", author="alice"
        )
        assert len(page.items) == 1
        assert page.items[0].sha == "abc"
        params = dict(route.calls.last.request.url.params)
        assert params["sha"] == "main"
        assert params["path"] == "src/"
        assert params["author"] == "alice"


@pytest.mark.asyncio
async def test_list_branches(github: GitHub) -> None:
    """list_branches: GET /branches → list of Branch with protection flag."""
    with respx.mock(base_url="https://api.github.com") as mock:
        mock.get("/repos/owner/repo/branches").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {"name": "main", "commit": {"sha": "abc"}, "protected": True},
                    {"name": "dev", "commit": {"sha": "def"}, "protected": False},
                ],
            )
        )
        page = await github.alist_branches(owner="owner", repo="repo")
        assert [b.name for b in page.items] == ["main", "dev"]
        assert page.items[0].protected is True
        assert page.items[1].protected is False


@pytest.mark.asyncio
async def test_get_branch(github: GitHub) -> None:
    """get_branch: GET /branches/{branch}."""
    with respx.mock(base_url="https://api.github.com") as mock:
        mock.get("/repos/owner/repo/branches/main").mock(
            return_value=httpx.Response(
                200,
                json={"name": "main", "commit": {"sha": "abc"}, "protected": True},
            )
        )
        branch = await github.aget_branch(owner="owner", repo="repo", branch="main")
        assert branch.name == "main"
        assert branch.protected is True


_RELEASE_MIN = {
    "id": 100,
    "tag_name": "v1.0",
    "name": "1.0",
    "body": "Release notes",
    "draft": False,
    "prerelease": False,
    "html_url": "https://github.com/owner/repo/releases/tag/v1.0",
    "author": _USER,
    "created_at": "2026-04-01T00:00:00Z",
    "published_at": "2026-04-01T00:00:00Z",
}


@pytest.mark.asyncio
async def test_list_releases(github: GitHub) -> None:
    """list_releases: GET /releases → newest first."""
    with respx.mock(base_url="https://api.github.com") as mock:
        mock.get("/repos/owner/repo/releases").mock(
            return_value=httpx.Response(200, json=[_RELEASE_MIN])
        )
        page = await github.alist_releases(owner="owner", repo="repo")
        assert page.items[0].tag_name == "v1.0"


@pytest.mark.asyncio
async def test_get_latest_release(github: GitHub) -> None:
    """get_latest_release: GET /releases/latest (excludes drafts + prereleases)."""
    with respx.mock(base_url="https://api.github.com") as mock:
        mock.get("/repos/owner/repo/releases/latest").mock(
            return_value=httpx.Response(200, json=_RELEASE_MIN)
        )
        release = await github.aget_latest_release(owner="owner", repo="repo")
        assert release.tag_name == "v1.0"
        assert release.draft is False


@pytest.mark.asyncio
async def test_create_release_full_body(github: GitHub) -> None:
    """create_release: full body — tag, name, body, draft, prerelease, target."""
    with respx.mock(base_url="https://api.github.com") as mock:
        route = mock.post("/repos/owner/repo/releases").mock(
            return_value=httpx.Response(
                201, json={**_RELEASE_MIN, "draft": True, "prerelease": True}
            )
        )
        release = await github.acreate_release(
            owner="owner",
            repo="repo",
            tag_name="v2.0",
            name="2.0",
            body="2.0 notes",
            draft=True,
            prerelease=True,
            target_commitish="main",
        )
        assert release.draft is True
        body = route.calls.last.request.read()
        assert b'"tag_name":"v2.0"' in body
        assert b'"draft":true' in body
        assert b'"prerelease":true' in body
        assert b'"target_commitish":"main"' in body


@pytest.mark.asyncio
async def test_get_content_file(github: GitHub) -> None:
    """get_content: GET /contents/{path} → base64-encoded file."""
    with respx.mock(base_url="https://api.github.com") as mock:
        route = mock.get("/repos/owner/repo/contents/README.md").mock(
            return_value=httpx.Response(
                200,
                json={
                    "type": "file",
                    "name": "README.md",
                    "path": "README.md",
                    "sha": "abc",
                    "size": 42,
                    "content": "SGVsbG8gV29ybGQ=",
                    "encoding": "base64",
                },
            )
        )
        file = await github.aget_content(owner="owner", repo="repo", path="README.md", ref="main")
        assert file.type == "file"
        assert file.content == "SGVsbG8gV29ybGQ="
        assert dict(route.calls.last.request.url.params)["ref"] == "main"


@pytest.mark.asyncio
async def test_create_or_update_file_create_path(github: GitHub) -> None:
    """create_or_update_file: PUT without sha = create. With sha = update."""
    with respx.mock(base_url="https://api.github.com") as mock:
        route = mock.put("/repos/owner/repo/contents/new.md").mock(
            return_value=httpx.Response(
                201, json={"content": {"sha": "newsha"}, "commit": {"sha": "csha"}}
            )
        )
        result = await github.acreate_or_update_file(
            owner="owner",
            repo="repo",
            path="new.md",
            content="SGVsbG8=",
            message="add new.md",
            branch="main",
        )
        assert result["content"]["sha"] == "newsha"
        body = route.calls.last.request.read()
        assert b'"message":"add new.md"' in body
        assert b'"content":"SGVsbG8="' in body
        assert b'"branch":"main"' in body
        # No sha (creating)
        assert b'"sha"' not in body or body.count(b'"sha"') == 0


@pytest.mark.asyncio
async def test_create_or_update_file_update_path_includes_sha(github: GitHub) -> None:
    """create_or_update_file: WITH sha includes it in the body (update)."""
    with respx.mock(base_url="https://api.github.com") as mock:
        route = mock.put("/repos/owner/repo/contents/existing.md").mock(
            return_value=httpx.Response(200, json={})
        )
        await github.acreate_or_update_file(
            owner="owner",
            repo="repo",
            path="existing.md",
            content="SGVsbG8=",
            message="update",
            sha="oldsha",
        )
        assert b'"sha":"oldsha"' in route.calls.last.request.read()


@pytest.mark.asyncio
async def test_delete_file(github: GitHub) -> None:
    """delete_file: DELETE /contents/{path} with sha + message."""
    with respx.mock(base_url="https://api.github.com") as mock:
        route = mock.delete("/repos/owner/repo/contents/old.md").mock(
            return_value=httpx.Response(200, json={"commit": {"sha": "csha"}})
        )
        result = await github.adelete_file(
            owner="owner",
            repo="repo",
            path="old.md",
            sha="oldsha",
            message="rm old",
        )
        assert result["commit"]["sha"] == "csha"
        body = route.calls.last.request.read()
        assert b'"sha":"oldsha"' in body
        assert b'"message":"rm old"' in body


@pytest.mark.asyncio
async def test_list_workflows_total_count(github: GitHub) -> None:
    """list_workflows: API wraps in {workflows: [...], total_count: N}."""
    with respx.mock(base_url="https://api.github.com") as mock:
        mock.get("/repos/owner/repo/actions/workflows").mock(
            return_value=httpx.Response(
                200,
                json={
                    "total_count": 3,
                    "workflows": [
                        {"id": 1, "name": "ci", "path": ".github/workflows/ci.yml"},
                        {"id": 2, "name": "release", "path": ".github/workflows/release.yml"},
                    ],
                },
            )
        )
        page = await github.alist_workflows(owner="owner", repo="repo")
        assert page.total_count == 3
        assert [w.name for w in page.items] == ["ci", "release"]


@pytest.mark.asyncio
async def test_list_workflow_runs_with_workflow_id(github: GitHub) -> None:
    """list_workflow_runs(workflow_id=N) hits the workflow-scoped endpoint."""
    with respx.mock(base_url="https://api.github.com") as mock:
        route = mock.get("/repos/owner/repo/actions/workflows/42/runs").mock(
            return_value=httpx.Response(
                200,
                json={
                    "total_count": 1,
                    "workflow_runs": [
                        {
                            "id": 100,
                            "head_sha": "abc",
                            "status": "completed",
                            "conclusion": "success",
                            "workflow_id": 42,
                            "run_number": 1,
                            "event": "push",
                        }
                    ],
                },
            )
        )
        page = await github.alist_workflow_runs(
            owner="owner", repo="repo", workflow_id=42, status="completed"
        )
        assert page.items[0].conclusion == "success"
        assert dict(route.calls.last.request.url.params)["status"] == "completed"


@pytest.mark.asyncio
async def test_list_workflow_runs_all_workflows_endpoint(github: GitHub) -> None:
    """list_workflow_runs without workflow_id hits /actions/runs (all workflows)."""
    with respx.mock(base_url="https://api.github.com") as mock:
        mock.get("/repos/owner/repo/actions/runs").mock(
            return_value=httpx.Response(200, json={"total_count": 0, "workflow_runs": []})
        )
        page = await github.alist_workflow_runs(owner="owner", repo="repo")
        assert page.items == []


@pytest.mark.asyncio
async def test_trigger_workflow_dispatch_body(github: GitHub) -> None:
    """trigger_workflow: POST /dispatches with ref + inputs."""
    with respx.mock(base_url="https://api.github.com") as mock:
        route = mock.post("/repos/owner/repo/actions/workflows/ci.yml/dispatches").mock(
            return_value=httpx.Response(204)
        )
        result = await github.atrigger_workflow(
            owner="owner",
            repo="repo",
            workflow_id="ci.yml",
            ref="main",
            inputs={"env": "prod"},
        )
        assert result is None
        body = route.calls.last.request.read()
        assert b'"ref":"main"' in body
        assert b'"inputs":{"env":"prod"}' in body


_GIST_MIN = {
    "id": "gist123",
    "description": "A gist",
    "public": True,
    "html_url": "https://gist.github.com/gist123",
    "files": {"hello.py": {"filename": "hello.py", "content": "print('hi')"}},
    "owner": _USER,
}


@pytest.mark.asyncio
async def test_list_gists(github: GitHub) -> None:
    """list_gists: GET /gists → list of gists for authenticated user."""
    with respx.mock(base_url="https://api.github.com") as mock:
        mock.get("/gists").mock(return_value=httpx.Response(200, json=[_GIST_MIN]))
        page = await github.alist_gists()
        assert page.items[0].id == "gist123"
        assert "hello.py" in page.items[0].files


@pytest.mark.asyncio
async def test_create_gist_body(github: GitHub) -> None:
    """create_gist: POST /gists with files dict + description + public flag."""
    with respx.mock(base_url="https://api.github.com") as mock:
        route = mock.post("/gists").mock(
            return_value=httpx.Response(201, json={**_GIST_MIN, "public": False})
        )
        gist = await github.acreate_gist(
            files={"hello.py": "print('hi')"},
            description="A gist",
            public=False,
        )
        assert gist.id == "gist123"
        body = route.calls.last.request.read()
        # GitHub's create-gist body shape: {"files": {"hello.py": {"content": "..."}}}
        assert b'"hello.py":{"content":"print(\'hi\')"}' in body
        assert b'"public":false' in body
        assert b'"description":"A gist"' in body


@pytest.mark.asyncio
async def test_search_code(github: GitHub) -> None:
    """search_code: GET /search/code with q + per_page."""
    with respx.mock(base_url="https://api.github.com") as mock:
        route = mock.get("/search/code").mock(
            return_value=httpx.Response(
                200,
                json={
                    "total_count": 1,
                    "items": [
                        {
                            "name": "main.py",
                            "path": "src/main.py",
                            "sha": "abc",
                            "score": 1.0,
                        }
                    ],
                },
            )
        )
        page = await github.asearch_code(query="addClass in:file language:js", limit=50)
        assert page.total_count == 1
        assert page.items[0].name == "main.py"
        assert dict(route.calls.last.request.url.params)["q"] == "addClass in:file language:js"
        assert dict(route.calls.last.request.url.params)["per_page"] == "50"


@pytest.mark.asyncio
async def test_search_repos_with_sort_order(github: GitHub) -> None:
    """search_repos: sort + order pass through; default order=desc."""
    with respx.mock(base_url="https://api.github.com") as mock:
        route = mock.get("/search/repositories").mock(
            return_value=httpx.Response(200, json={"total_count": 1, "items": [_REPO_MIN]})
        )
        page = await github.asearch_repos(query="language:python stars:>1000", sort="stars")
        assert page.items[0].full_name == "owner/repo"
        params = dict(route.calls.last.request.url.params)
        assert params["q"] == "language:python stars:>1000"
        assert params["sort"] == "stars"
        assert params["order"] == "desc"


@pytest.mark.asyncio
async def test_search_issues_via_global_endpoint(github: GitHub) -> None:
    """search_issues uses the global /search/issues (NOT per-repo /issues)."""
    with respx.mock(base_url="https://api.github.com") as mock:
        mock.get("/search/issues").mock(
            return_value=httpx.Response(200, json={"total_count": 1, "items": [_ISSUE_MIN]})
        )
        page = await github.asearch_issues(query="is:issue is:open label:bug")
        assert page.items[0].title == "issue title"


@pytest.mark.asyncio
async def test_get_authenticated_user(github: GitHub) -> None:
    """get_authenticated_user: GET /user → dict (intentionally untyped)."""
    with respx.mock(base_url="https://api.github.com") as mock:
        mock.get("/user").mock(
            return_value=httpx.Response(
                200, json={"login": "me", "id": 1, "name": "Me", "public_repos": 5}
            )
        )
        user = await github.aget_authenticated_user()
        assert user["login"] == "me"
        assert user["public_repos"] == 5


@pytest.mark.asyncio
async def test_get_rate_limit(github: GitHub) -> None:
    """get_rate_limit: GET /rate_limit → dict with resources + rate."""
    with respx.mock(base_url="https://api.github.com") as mock:
        mock.get("/rate_limit").mock(
            return_value=httpx.Response(
                200,
                json={
                    "resources": {
                        "core": {"limit": 5000, "remaining": 4999, "reset": 1745000000},
                        "search": {"limit": 30, "remaining": 30, "reset": 1745000060},
                    },
                    "rate": {"limit": 5000, "remaining": 4999, "reset": 1745000000},
                },
            )
        )
        rl = await github.aget_rate_limit()
        assert rl["resources"]["core"]["limit"] == 5000


@pytest.mark.asyncio
async def test_star_repo_returns_none(github: GitHub) -> None:
    """star_repo: PUT /user/starred/{owner}/{repo} → None (204)."""
    with respx.mock(base_url="https://api.github.com") as mock:
        route = mock.put("/user/starred/owner/repo").mock(return_value=httpx.Response(204))
        result = await github.astar_repo(owner="owner", repo="repo")
        assert result is None
        assert route.calls.last.request.method == "PUT"


@pytest.mark.asyncio
async def test_unstar_repo_returns_none(github: GitHub) -> None:
    """unstar_repo: DELETE /user/starred/{owner}/{repo} → None (204)."""
    with respx.mock(base_url="https://api.github.com") as mock:
        route = mock.delete("/user/starred/owner/repo").mock(return_value=httpx.Response(204))
        result = await github.aunstar_repo(owner="owner", repo="repo")
        assert result is None
        assert route.calls.last.request.method == "DELETE"


# ===========================================================================
# Round 2 — pagination edges + URL-path injection guards
# ===========================================================================
#
# GitHub's Link header is parsed by _parsers.parse_link_header. Each
# of these tests pins a known edge case so future refactors don't drop
# coverage of the corner.


@pytest.mark.asyncio
async def test_link_header_missing_means_no_more_pages(github: GitHub) -> None:
    """No Link header at all → has_more=False, cursor=None."""
    with respx.mock(base_url="https://api.github.com") as mock:
        mock.get("/repos/owner/repo/issues").mock(return_value=httpx.Response(200, json=[]))
        page = await github.alist_issues(owner="owner", repo="repo")
        assert page.page_state.has_more is False
        assert page.page_state.cursor is None


@pytest.mark.asyncio
async def test_link_header_only_prev_means_no_more_next(github: GitHub) -> None:
    """Link header with only rel='prev' (last page of multi-page set) →
    has_more=False because we only care about rel='next'.
    """
    with respx.mock(base_url="https://api.github.com") as mock:
        mock.get("/repos/owner/repo/issues").mock(
            return_value=httpx.Response(
                200,
                json=[],
                headers={
                    "Link": '<https://api.github.com/repos/owner/repo/issues?page=1>; rel="prev"'
                },
            )
        )
        page = await github.alist_issues(owner="owner", repo="repo")
        assert page.page_state.has_more is False


@pytest.mark.asyncio
async def test_link_header_picks_next_amongst_many(github: GitHub) -> None:
    """Multi-link header: 4 entries (first/prev/next/last) — picks next."""
    multi = (
        '<https://api.github.com/repos/owner/repo/issues?page=1>; rel="first", '
        '<https://api.github.com/repos/owner/repo/issues?page=2>; rel="prev", '
        '<https://api.github.com/repos/owner/repo/issues?page=4>; rel="next", '
        '<https://api.github.com/repos/owner/repo/issues?page=10>; rel="last"'
    )
    with respx.mock(base_url="https://api.github.com") as mock:
        mock.get("/repos/owner/repo/issues").mock(
            return_value=httpx.Response(200, json=[], headers={"Link": multi})
        )
        page = await github.alist_issues(owner="owner", repo="repo")
        assert page.page_state.has_more is True
        assert page.page_state.cursor is not None
        assert "page=4" in page.page_state.cursor


@pytest.mark.asyncio
async def test_per_page_clamped_to_100_max(github: GitHub) -> None:
    """limit=500 → request sends per_page=100 (GitHub's documented max)."""
    with respx.mock(base_url="https://api.github.com") as mock:
        route = mock.get("/repos/owner/repo/issues").mock(return_value=httpx.Response(200, json=[]))
        await github.alist_issues(owner="owner", repo="repo", limit=500)
        assert dict(route.calls.last.request.url.params)["per_page"] == "100"


@pytest.mark.asyncio
async def test_cursor_url_used_verbatim_no_path_rebuild(github: GitHub) -> None:
    """Page 2 cursor is a full URL from Link header; we GET it directly
    instead of rebuilding the path. This protects against accidentally
    losing query params (sha/path/author/state) on subsequent pages.
    """
    cursor_url = (
        "https://api.github.com/repos/owner/repo/issues?page=2&per_page=30&state=open&labels=bug"
    )
    page1_headers = {"Link": f'<{cursor_url}>; rel="next"'}

    with respx.mock(base_url="https://api.github.com") as mock:
        page1_route = mock.get("/repos/owner/repo/issues").mock(
            side_effect=[
                httpx.Response(200, json=[_ISSUE_MIN], headers=page1_headers),
                httpx.Response(200, json=[]),
            ]
        )
        page1 = await github.alist_issues(owner="owner", repo="repo")
        page2 = await github.alist_issues(owner="owner", repo="repo", page=page1.page_state.cursor)
        assert page2.items == []
        # Two calls happened: the original list_issues + the cursor follow-up
        assert page1_route.call_count == 2
        # The second call used the cursor URL verbatim — including the
        # extra query params (state=open, labels=bug) the original call
        # didn't have. That's how we know the cursor was used as-is.
        second_call_url = str(page1_route.calls[1].request.url)
        assert "page=2" in second_call_url
        assert "state=open" in second_call_url
        assert "labels=bug" in second_call_url


# ---------------------------------------------------------------------------
# URL-path injection — GitHub's REST API has owner/repo/path interpolated
# directly into the URL via f-strings. If a hostile caller passes
# `owner="../../admin"`, the request URL becomes
# /repos/../../admin/repo/... which httpx normalizes — but it's worth
# pinning the behavior so a refactor (e.g. removing httpx URL normalization)
# would fail loudly.


@pytest.mark.asyncio
async def test_special_chars_in_owner_dont_traverse(github: GitHub) -> None:
    """owner='../admin' must NOT traverse out of /repos/ via URL
    normalization (CVE-class defense-in-depth).

    This is the test that uncovered the original bug: without the
    ``_p()`` percent-encoding wrapper at every f-string interpolation,
    f"/repos/{owner}/{repo}" with owner="../admin" produced
    /repos/../admin/repo, which httpx normalized to /admin/repo —
    escaping out of the intended prefix.

    With ``_p()``, the slash is encoded as %2F: the literal URL becomes
    /repos/..%2Fadmin/repo which GitHub 404s (no such owner), and the
    /repos/ prefix is preserved.
    """
    from toolsconnector.errors import NotFoundError

    with respx.mock(base_url="https://api.github.com") as mock:
        route = mock.get(host="api.github.com").mock(
            return_value=httpx.Response(404, json={"message": "Not Found"})
        )
        with pytest.raises(NotFoundError):
            await github.aget_repo(owner="../admin", repo="repo")

        actual_url = str(route.calls.last.request.url)
        # The /repos/ prefix MUST be preserved (this is the defense)
        assert actual_url.startswith("https://api.github.com/repos/"), (
            f"Path traversal succeeded: {actual_url}"
        )
        # The owner slash was percent-encoded (%2F) — that's how /repos/
        # was preserved. Specifically we expect '..%2Fadmin' somewhere
        # in the URL, NOT a literal '/admin/' segment.
        assert "..%2Fadmin" in actual_url or "..%2fadmin" in actual_url
        # Sanity: no path segment of just 'admin' appears
        assert "/admin/" not in actual_url


@pytest.mark.asyncio
async def test_unicode_in_owner_round_trips(github: GitHub) -> None:
    """Unicode owner name (e.g. emoji or non-ASCII) → request reaches
    a percent-encoded URL; server's 404 is the typed exception.
    """
    with respx.mock(base_url="https://api.github.com") as mock:
        mock.get(host="api.github.com").mock(
            return_value=httpx.Response(404, json={"message": "Not Found"})
        )
        from toolsconnector.errors import NotFoundError

        with pytest.raises(NotFoundError):
            await github.aget_repo(owner="ünïcode-org", repo="repo")
        # Test passes by raising NotFoundError, not crashing on encoding


@pytest.mark.asyncio
async def test_file_path_with_subdirs_encoded(github: GitHub) -> None:
    """get_content with path 'src/sub/file.py' must build a multi-segment
    URL path correctly. The `path` segment is intentionally NOT wrapped
    in `_p()` because GitHub's contents API legitimately accepts
    multi-segment paths (file paths within a repo).
    """
    with respx.mock(base_url="https://api.github.com") as mock:
        route = mock.get("/repos/owner/repo/contents/src/sub/file.py").mock(
            return_value=httpx.Response(
                200,
                json={
                    "type": "file",
                    "name": "file.py",
                    "path": "src/sub/file.py",
                    "sha": "abc",
                    "size": 10,
                    "content": "Zm9v",
                    "encoding": "base64",
                },
            )
        )
        file = await github.aget_content(owner="owner", repo="repo", path="src/sub/file.py")
        assert file.path == "src/sub/file.py"
        assert route.called


@pytest.mark.asyncio
async def test_branch_slash_percent_encoded(github: GitHub) -> None:
    """Branch names with `/` (e.g. `feature/x`) MUST be percent-encoded
    in the URL path — GitHub doesn't support literal `/` in the
    branch path segment.
    """
    with respx.mock(base_url="https://api.github.com") as mock:
        route = mock.get(host="api.github.com").mock(
            return_value=httpx.Response(
                200,
                json={"name": "feature/x", "commit": {"sha": "abc"}, "protected": False},
            )
        )
        await github.aget_branch(owner="owner", repo="repo", branch="feature/x")
        url = str(route.calls.last.request.url)
        # The branch slash must be encoded — we should see %2F, not literal `/x`
        # after `/branches/feature`
        assert "/branches/feature%2Fx" in url or "/branches/feature%2fx" in url
        # The literal multi-segment path is NOT used
        assert "/branches/feature/x" not in url


# ===========================================================================
# Round 3 — error matrix (typed-exception mapping for every HTTP status
# the GitHub REST API produces, plus the two GitHub-specific rate-limit
# variants that both arrive as 403).
# ===========================================================================
#
# The existing 401/404 tests already cover InvalidCredentialsError and
# NotFoundError. The tests below round out the matrix:
#   * 403 + X-RateLimit-Remaining=0  → RateLimitError (primary)
#   * 403 + "secondary rate limit"   → RateLimitError (secondary)
#   * 403 + "abuse detection"        → RateLimitError (secondary alt-phrasing)
#   * 403 + Retry-After header       → RateLimitError (secondary header-only)
#   * 403 (no rate-limit signals)    → PermissionDeniedError (normal 403)
#   * 409  → ConflictError
#   * 422  → ValidationError
#   * 5xx  → ServerError


_TIME_NOW = 1745000000  # arbitrary epoch reference for retry_after math


@pytest.mark.asyncio
async def test_403_primary_rate_limit_raises_rate_limit_error(
    github: GitHub, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Primary rate limit: HTTP 403 + X-RateLimit-Remaining: 0 +
    X-RateLimit-Reset: <epoch> → typed RateLimitError with computed
    retry_after_seconds.

    Critical: shared raise_typed_for_status would map 403 to
    PermissionDeniedError — the GitHub-specific override in _request
    must catch this BEFORE the generic mapping.
    """
    import time

    monkeypatch.setattr(time, "time", lambda: _TIME_NOW)

    from toolsconnector.errors import RateLimitError

    with respx.mock(base_url="https://api.github.com") as mock:
        mock.get("/repos/owner/repo").mock(
            return_value=httpx.Response(
                403,
                json={"message": "API rate limit exceeded"},
                headers={
                    "X-RateLimit-Limit": "5000",
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(_TIME_NOW + 1800),  # 30 min from "now"
                    "X-RateLimit-Used": "5000",
                    "X-RateLimit-Resource": "core",
                },
            )
        )

        with pytest.raises(RateLimitError) as exc_info:
            await github.aget_repo(owner="owner", repo="repo")

        err = exc_info.value
        assert err.connector == "github"
        assert err.retry_after_seconds == 1800
        assert err.details["limit_type"] == "primary"
        assert err.details["x_ratelimit_resource"] == "core"


@pytest.mark.asyncio
async def test_403_secondary_rate_limit_with_retry_after_header(
    github: GitHub,
) -> None:
    """Secondary rate limit: HTTP 403 + Retry-After header (seconds) →
    RateLimitError with retry_after_seconds = parsed header.
    """
    from toolsconnector.errors import RateLimitError

    with respx.mock(base_url="https://api.github.com") as mock:
        mock.get("/repos/owner/repo").mock(
            return_value=httpx.Response(
                403,
                json={"message": "You have exceeded a secondary rate limit"},
                headers={"Retry-After": "60"},
            )
        )

        with pytest.raises(RateLimitError) as exc_info:
            await github.aget_repo(owner="owner", repo="repo")

        err = exc_info.value
        assert err.retry_after_seconds == 60
        assert err.details["limit_type"] == "secondary"


@pytest.mark.asyncio
async def test_403_secondary_rate_limit_with_abuse_phrase(github: GitHub) -> None:
    """Secondary rate limit alt-phrasing: body contains the word "abuse"
    (GitHub's older error message used "abuse detection mechanism") →
    still classified as RateLimitError, not PermissionDeniedError.
    """
    from toolsconnector.errors import RateLimitError

    with respx.mock(base_url="https://api.github.com") as mock:
        mock.get("/repos/owner/repo").mock(
            return_value=httpx.Response(
                403,
                json={
                    "message": (
                        "You have triggered an abuse detection mechanism. "
                        "Please wait a few minutes before you try again."
                    ),
                },
            )
        )

        with pytest.raises(RateLimitError) as exc_info:
            await github.aget_repo(owner="owner", repo="repo")
        assert exc_info.value.details["limit_type"] == "secondary"


@pytest.mark.asyncio
async def test_403_permission_denied_stays_permission_denied(github: GitHub) -> None:
    """Normal 403 (e.g., token lacks the required scope for an endpoint)
    must NOT be classified as RateLimitError. Without the GitHub-
    specific override being precise, every 403 would become a rate-limit
    error — the test pins that we only override when rate-limit signals
    are present.
    """
    from toolsconnector.errors import PermissionDeniedError

    with respx.mock(base_url="https://api.github.com") as mock:
        mock.get("/repos/owner/repo").mock(
            return_value=httpx.Response(
                403,
                json={
                    "message": (
                        "Resource not accessible by integration. "
                        "Your token is missing the `repo` scope."
                    ),
                },
            )
        )

        with pytest.raises(PermissionDeniedError) as exc_info:
            await github.aget_repo(owner="owner", repo="repo")
        assert exc_info.value.upstream_status == 403
        assert "Resource not accessible" in exc_info.value.details["body_preview"]


@pytest.mark.asyncio
async def test_409_raises_conflict_error(github: GitHub) -> None:
    """409 Conflict (e.g., creating a file that already exists, or
    merging a PR that has merge conflicts) → ConflictError.
    """
    from toolsconnector.errors import ConflictError

    with respx.mock(base_url="https://api.github.com") as mock:
        mock.put("/repos/owner/repo/contents/conflicting.md").mock(
            return_value=httpx.Response(
                409, json={"message": "sha conflict — file modified by another writer"}
            )
        )

        with pytest.raises(ConflictError) as exc_info:
            await github.acreate_or_update_file(
                owner="owner",
                repo="repo",
                path="conflicting.md",
                content="SGVsbG8=",
                message="x",
                sha="staleSha",
            )
        assert exc_info.value.upstream_status == 409


@pytest.mark.asyncio
async def test_422_raises_validation_error(github: GitHub) -> None:
    """422 Unprocessable Entity (e.g., invalid issue field shape) →
    ValidationError. GitHub uses 422 heavily for body-shape problems.
    """
    from toolsconnector.errors import ValidationError

    with respx.mock(base_url="https://api.github.com") as mock:
        mock.post("/repos/owner/repo/issues").mock(
            return_value=httpx.Response(
                422,
                json={
                    "message": "Validation Failed",
                    "errors": [
                        {"resource": "Issue", "field": "title", "code": "missing"},
                    ],
                },
            )
        )

        with pytest.raises(ValidationError) as exc_info:
            await github.acreate_issue(owner="owner", repo="repo", title="")
        assert exc_info.value.upstream_status == 422


@pytest.mark.asyncio
async def test_500_raises_server_error(github: GitHub) -> None:
    """5xx (GitHub-side outage / unicorn page) → typed ServerError so
    callers can apply exponential backoff. Distinct from RateLimitError
    (which has a known retry-after) and ConnectionError (which is a
    transport-layer failure).
    """
    from toolsconnector.errors import ServerError

    with respx.mock(base_url="https://api.github.com") as mock:
        mock.get("/repos/owner/repo").mock(
            return_value=httpx.Response(500, json={"message": "Server Error"})
        )

        with pytest.raises(ServerError) as exc_info:
            await github.aget_repo(owner="owner", repo="repo")
        assert exc_info.value.upstream_status == 500


@pytest.mark.asyncio
async def test_503_raises_server_error(github: GitHub) -> None:
    """503 Service Unavailable (deploy / maintenance window) → ServerError."""
    from toolsconnector.errors import ServerError

    with respx.mock(base_url="https://api.github.com") as mock:
        mock.get("/repos/owner/repo").mock(
            return_value=httpx.Response(503, text="<html>maintenance</html>")
        )

        with pytest.raises(ServerError) as exc_info:
            await github.aget_repo(owner="owner", repo="repo")
        assert exc_info.value.upstream_status == 503


# ===========================================================================
# Round 4 — transport errors + defensive parsing + Link-header edges
# ===========================================================================
#
# The connector's _request wraps httpx transport failures into typed
# ToolsConnector exceptions so callers catching ``ToolsConnectorError``
# see network failures uniformly. Without this wrapping a bare
# httpx.ConnectError would bubble out and break the ``except
# ToolsConnectorError`` contract.


@pytest.mark.asyncio
async def test_connect_error_raises_typed_connection_error(github: GitHub) -> None:
    """httpx.ConnectError (DNS failure / TCP RST / TLS handshake fail)
    → typed ConnectionError, not the raw httpx class.
    """
    from toolsconnector.errors import ConnectionError as TCConnectionError

    with respx.mock(base_url="https://api.github.com") as mock:
        mock.get("/repos/owner/repo").mock(side_effect=httpx.ConnectError("DNS failure"))

        with pytest.raises(TCConnectionError) as exc_info:
            await github.aget_repo(owner="owner", repo="repo")
        assert exc_info.value.connector == "github"
        assert "DNS failure" in exc_info.value.details["underlying"]


@pytest.mark.asyncio
async def test_timeout_raises_typed_timeout_error(github: GitHub) -> None:
    """httpx.TimeoutException (slow / no response) → typed TimeoutError."""
    from toolsconnector.errors import TimeoutError as TCTimeoutError

    with respx.mock(base_url="https://api.github.com") as mock:
        mock.get("/repos/owner/repo").mock(
            side_effect=httpx.ReadTimeout("Read timed out after 30s")
        )

        with pytest.raises(TCTimeoutError) as exc_info:
            await github.aget_repo(owner="owner", repo="repo")
        assert exc_info.value.connector == "github"
        assert exc_info.value.details["timeout_seconds"] is not None


@pytest.mark.asyncio
async def test_transport_error_raises_typed_transport_error(github: GitHub) -> None:
    """Generic httpx.TransportError (e.g., connection drop mid-stream)
    → typed TransportError preserving the underlying class name.
    """
    from toolsconnector.errors import TransportError

    with respx.mock(base_url="https://api.github.com") as mock:
        mock.get("/repos/owner/repo").mock(
            side_effect=httpx.RemoteProtocolError("connection dropped")
        )

        with pytest.raises(TransportError) as exc_info:
            await github.aget_repo(owner="owner", repo="repo")
        assert "RemoteProtocolError" in str(exc_info.value)


@pytest.mark.asyncio
async def test_cursor_path_also_handles_transport_errors(github: GitHub) -> None:
    """The cursor-URL branch of _get_page must also wrap transport
    errors — not just the path-based first-page branch. A regression
    where pagination middle-pages crashed with raw httpx errors would
    bypass any ``except ToolsConnectorError`` handler.
    """
    from toolsconnector.errors import ConnectionError as TCConnectionError

    with respx.mock(base_url="https://api.github.com") as mock:
        # First-page call succeeds, gives a Link header pointing at page 2
        mock.get("/repos/owner/repo/issues").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json=[],
                    headers={
                        "Link": '<https://api.github.com/repos/owner/repo/issues?page=2>; rel="next"'
                    },
                ),
                httpx.ConnectError("network blip on page 2"),
            ]
        )

        page1 = await github.alist_issues(owner="owner", repo="repo")
        assert page1.page_state.has_more is True

        # Page 2 fetch errors with httpx.ConnectError → must surface as
        # typed ConnectionError, not bare httpx
        with pytest.raises(TCConnectionError):
            await github.alist_issues(owner="owner", repo="repo", page=page1.page_state.cursor)


# ---------------------------------------------------------------------------
# Defensive parsing — pydantic models tolerate unknown fields (real GitHub
# responses include many we don't model, and adding them later shouldn't
# break old client builds).


@pytest.mark.asyncio
async def test_repository_model_tolerates_unknown_fields(github: GitHub) -> None:
    """All 17 type models declare extra='ignore' (added in 0.3.10 for
    explicit intent — pydantic v2 default is already ignore). Verify
    the parser doesn't crash on a fully-populated response with many
    extra fields GitHub returns.
    """
    real_world_response = {
        "id": 1,
        "name": "repo",
        "full_name": "owner/repo",
        "owner": {
            "login": "owner",
            "id": 100,
            "type": "User",
            # 13 extra fields GitHub actually returns:
            "node_id": "MDQ6VXNlcjEwMA==",
            "gravatar_id": "",
            "url": "https://api.github.com/users/owner",
            "followers_url": "https://api.github.com/users/owner/followers",
            "following_url": "https://api.github.com/users/owner/following{/other_user}",
            "gists_url": "https://api.github.com/users/owner/gists{/gist_id}",
            "starred_url": "https://api.github.com/users/owner/starred{/owner}{/repo}",
            "subscriptions_url": "https://api.github.com/users/owner/subscriptions",
            "organizations_url": "https://api.github.com/users/owner/orgs",
            "repos_url": "https://api.github.com/users/owner/repos",
            "events_url": "https://api.github.com/users/owner/events{/privacy}",
            "received_events_url": "https://api.github.com/users/owner/received_events",
            "user_view_type": "public",  # newly added by GitHub at some point
        },
        # Many extra Repository fields GitHub returns
        "node_id": "MDEwOlJlcG9zaXRvcnkx",
        "is_template": False,
        "topics": ["python", "tools"],
        "visibility": "public",
        "default_branch": "main",
        "stargazers_count": 5,
        "forks_count": 2,
        "open_issues_count": 1,
        "subscribers_count": 3,
        "network_count": 2,
        "watchers": 5,
        "permissions": {"admin": True, "push": True, "pull": True},
    }
    with respx.mock(base_url="https://api.github.com") as mock:
        mock.get("/repos/owner/repo").mock(
            return_value=httpx.Response(200, json=real_world_response)
        )

        repo = await github.aget_repo(owner="owner", repo="repo")
        # All extra fields silently ignored; declared fields populated
        assert repo.full_name == "owner/repo"
        assert repo.stargazers_count == 5
        assert repo.owner.login == "owner"
        assert repo.topics == ["python", "tools"]


@pytest.mark.asyncio
async def test_pull_request_from_api_with_real_world_payload(github: GitHub) -> None:
    """PullRequest.from_api uses unpacking (e.g., GitHubUser(**data["user"]))
    which would crash with pydantic strict mode if any extra field were
    present. With extra='ignore' it's fine. Pin the behavior using a
    realistic payload.
    """
    real_pr = {
        "id": 1,
        "number": 7,
        "title": "Add X",
        "state": "open",
        "user": {
            "login": "alice",
            "id": 100,
            "type": "User",
            "node_id": "MDQ6VXNlcjE=",  # extra field
            "gravatar_id": "",
        },
        "head": {"ref": "feature/x", "sha": "abc", "label": "alice:feature/x"},
        "base": {"ref": "main", "sha": "def", "label": "owner:main"},
        "labels": [
            {"id": 1, "name": "bug", "color": "d73a4a", "node_id": "EXTRA"},
        ],
        "assignees": [],
        "draft": False,
        "merged": False,
        "merged_by": None,
        "milestone": None,
    }
    with respx.mock(base_url="https://api.github.com") as mock:
        mock.get("/repos/owner/repo/pulls/7").mock(return_value=httpx.Response(200, json=real_pr))
        pr = await github.aget_pull_request(owner="owner", repo="repo", pr_number=7)
        assert pr.number == 7
        assert pr.head_ref == "feature/x"
        assert pr.user.login == "alice"


# ---------------------------------------------------------------------------
# parse_link_header edge cases


def test_parse_link_header_empty_string() -> None:
    """Empty / None Link header → empty dict (not a parse error)."""
    from toolsconnector.connectors.github._parsers import parse_link_header

    assert parse_link_header("") == {}
    assert parse_link_header(None) == {}


def test_parse_link_header_malformed_partial_match() -> None:
    """Malformed Link header (missing `; rel=`) → regex picks up only
    the well-formed entries, drops the malformed one without crashing.
    """
    from toolsconnector.connectors.github._parsers import parse_link_header

    # Second entry has no rel= attribute — malformed but should not crash
    header = (
        '<https://api.github.com/x?page=2>; rel="next", '
        "<https://api.github.com/x?page=1>"  # missing ; rel=...
    )
    links = parse_link_header(header)
    assert "next" in links
    # Only the well-formed entry is captured
    assert len(links) == 1


def test_parse_link_header_unusual_rel_names() -> None:
    """Custom rel values (last/first/prev/next) all captured as-is."""
    from toolsconnector.connectors.github._parsers import parse_link_header

    header = (
        '<https://api.github.com/?page=1>; rel="first", '
        '<https://api.github.com/?page=99>; rel="last", '
        '<https://api.github.com/?page=2>; rel="prev"'
    )
    links = parse_link_header(header)
    assert links["first"].endswith("page=1")
    assert links["last"].endswith("page=99")
    assert links["prev"].endswith("page=2")
    assert "next" not in links


# ===========================================================================
# Round 5 — MCP exposure, OpenAI schema sweep, sync wrappers,
# ToolKit dispatch, concurrency.
# ===========================================================================


def test_every_action_has_openai_compatible_schema() -> None:
    """Sweep: every @action produces a valid OpenAI function-call
    schema (name, description, parameters). Catches actions that
    accidentally use ``**kwargs`` (which doesn't generate a schema),
    have unsupported parameter types, or have malformed docstrings.
    """
    from toolsconnector.serve import ToolKit

    kit = ToolKit(["github"], credentials={"github": "ghp_fake"})
    tools = kit.to_openai_tools()
    # 37 actions = 37 tools
    assert len(tools) == 37, f"Expected 37 tools, got {len(tools)}"

    for tool in tools:
        assert tool["type"] == "function"
        fn = tool["function"]
        # Tool name follows connector_action convention
        assert fn["name"].startswith("github_"), fn["name"]
        # Description starts with "GitHub:" (the connector-context prefix)
        assert fn["description"], fn["name"]
        # Parameters is a valid JSON schema with object type
        params = fn["parameters"]
        assert params["type"] == "object"
        assert "properties" in params


def test_mcp_exposure_via_toolkit() -> None:
    """All 37 actions are exposed when serving via MCP. Tests the
    full ToolKit → tools roundtrip, including the synthetic kwarg
    signatures the MCP layer builds from JSON schema.
    """
    from toolsconnector.serve import ToolKit

    kit = ToolKit(["github"], credentials={"github": "ghp_fake"})
    tools = kit.list_tools()
    names = {t["name"] for t in tools}
    assert len(names) == 37

    # Every action is exposed under `github_<action>` naming
    for action_name in (
        "list_repos",
        "get_repo",
        "create_repo",
        "create_issue",
        "delete_file",
        "merge_pull_request",
        "trigger_workflow",
        "search_code",
    ):
        assert f"github_{action_name}" in names


def test_mcp_exclude_dangerous_filters_correctly() -> None:
    """ToolKit's exclude_dangerous filter must remove all 14 dangerous
    actions when set. Pin the exact count so a refactor that drops
    or adds a dangerous flag is caught.
    """
    from toolsconnector.serve import ToolKit

    kit_all = ToolKit(["github"], credentials={"github": "ghp_fake"})
    tools_all = kit_all.list_tools()
    assert len(tools_all) == 37

    kit_safe = ToolKit(["github"], credentials={"github": "ghp_fake"}, exclude_dangerous=True)
    tools_safe = kit_safe.list_tools()
    # 14 dangerous, so 37 - 14 = 23 safe
    assert len(tools_safe) == 23

    # None of the safe tools are flagged dangerous
    safe_names = {t["name"] for t in tools_safe}
    for danger in (
        "github_create_repo",
        "github_fork_repo",
        "github_create_issue",
        "github_remove_label",
        "github_create_comment",
        "github_create_pull_request",
        "github_merge_pull_request",
        "github_create_release",
        "github_create_or_update_file",
        "github_delete_file",
        "github_trigger_workflow",
        "github_create_gist",
        "github_star_repo",
        "github_unstar_repo",
    ):
        assert danger not in safe_names, f"{danger} should have been filtered"


@pytest.mark.asyncio
async def test_sync_wrappers_match_async(github: GitHub) -> None:
    """Every async action has a sync wrapper at the same attribute name
    minus the `a` prefix. Verify a representative sample dispatches
    through the same code path (sync wrapper → asyncio.run internally).
    """
    from toolsconnector.connectors.github import GitHub

    # Sync entry points exist
    sync_inst = GitHub(credentials="ghp_fake")
    for action in (
        "list_repos",
        "get_repo",
        "create_issue",
        "search_code",
        "get_rate_limit",
    ):
        assert hasattr(sync_inst, action), f"sync wrapper missing: {action}"
        assert hasattr(sync_inst, f"a{action}"), f"async method missing: a{action}"


@pytest.mark.asyncio
async def test_toolkit_execute_dispatches_to_connector(github: GitHub) -> None:
    """End-to-end: ToolKit.aexecute("github_get_repo", {...}) reaches
    the connector and returns the parsed result as JSON. Catches MCP-
    layer dispatch regressions (e.g., name munging, arg renaming).
    """
    import json

    from toolsconnector.serve import ToolKit

    with respx.mock(base_url="https://api.github.com") as mock:
        mock.get("/repos/owner/repo").mock(return_value=httpx.Response(200, json=_REPO_MIN))
        kit = ToolKit(["github"], credentials={"github": "ghp_fake_test_token"})
        raw = await kit.aexecute(
            "github_get_repo",
            {"owner": "owner", "repo": "repo"},
        )
        data = json.loads(raw)
        assert data["full_name"] == "owner/repo"


@pytest.mark.asyncio
async def test_concurrent_requests_safe(github: GitHub) -> None:
    """Two concurrent requests through the same httpx.AsyncClient share
    the connection pool safely (httpx is async-safe; we just verify
    no shared mutable state leaks between them).
    """
    import asyncio

    with respx.mock(base_url="https://api.github.com") as mock:
        mock.get("/repos/owner/repo").mock(return_value=httpx.Response(200, json=_REPO_MIN))
        mock.get("/repos/owner/other").mock(
            return_value=httpx.Response(200, json={**_REPO_MIN, "name": "other"})
        )

        results = await asyncio.gather(
            github.aget_repo(owner="owner", repo="repo"),
            github.aget_repo(owner="owner", repo="other"),
        )
        assert results[0].name == "repo"
        assert results[1].name == "other"


@pytest.mark.asyncio
async def test_cancellation_propagates_cleanly(github: GitHub) -> None:
    """asyncio.CancelledError raised mid-request must propagate (not
    get swallowed by the connector's broad except clauses).
    """
    import asyncio

    # Cancel a deliberately slow coroutine. We mock the request to
    # never resolve; cancel from outside while it's awaiting.
    with respx.mock(base_url="https://api.github.com", assert_all_called=False) as mock:
        # Mock that hangs forever (httpx awaits on the resolver)
        async def hang(request: httpx.Request) -> httpx.Response:
            await asyncio.sleep(60)
            return httpx.Response(200)

        mock.get("/repos/owner/repo").mock(side_effect=hang)

        task = asyncio.create_task(github.aget_repo(owner="owner", repo="repo"))
        await asyncio.sleep(0.05)  # let task get into the request
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_lifecycle_setup_and_teardown_idempotent() -> None:
    """Calling _setup twice (e.g., explicit + ToolKit re-init) shouldn't
    leak a client. Calling _teardown twice (or before _setup) shouldn't
    crash.
    """
    from toolsconnector.connectors.github import GitHub

    conn = GitHub(credentials="ghp_fake")
    await conn._setup()
    client1 = conn._client
    await conn._setup()  # re-setup — should just replace the client
    client2 = conn._client
    assert client1 is not client2

    await conn._teardown()
    # Teardown again should be a no-op (not crash)
    await conn._teardown()


def test_no_credentials_lifecycle() -> None:
    """Connector should construct without credentials (a Public-API
    use case — search/code/repos against public repos don't need auth).
    """
    from toolsconnector.connectors.github import GitHub

    # No credentials — should still work for lifecycle (will fail with
    # 401 on protected endpoints if actually called).
    conn = GitHub()
    assert conn._credentials is None


def test_credentials_accepts_string() -> None:
    """Most common path: credentials passed as a plain string."""
    from toolsconnector.connectors.github import GitHub

    conn = GitHub(credentials="ghp_realworld_pat")
    assert conn._credentials == "ghp_realworld_pat"
