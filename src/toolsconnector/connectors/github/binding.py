"""Declarative HTTP binding for the GitHub connector.

Extracted from experiments/sdk_spike/specs.py. This is the production binding
that makes the GitHub connector load-bearing in Python (Phase 1 migration).
37 actions: 36 declarative + 1 escape hatch (create_gist transforms its
files map per-value: {name: {"content": v}} — imperative, not declarative).
Exercises conditional path_variants (list_repos 3-way, create_repo,
list_workflow_runs) and LINK_FOLLOW pagination (GET the rel=next URL from
the Link header directly).
"""

from __future__ import annotations

from toolsconnector.spec.binding import (
    ActionBinding,
    AuthKind,
    ConnectorBinding,
    EndpointBinding,
    Location,
    PaginationBinding,
    PaginationKind,
    ParamBinding,
    PathVariant,
)


def _p(name, wire, loc, **kw):
    return ParamBinding(name=name, wire=wire, location=loc, **kw)


def _gq(name, wire=None, **kw):  # query param
    return _p(name, wire or name, Location.QUERY, **kw)


def _gb(name, wire=None, **kw):  # JSON body param
    return _p(name, wire or name, Location.BODY, **kw)


def _gpath(name):  # path param
    return _p(name, name, Location.PATH)


def _glimit():  # limit -> per_page=min(limit,100), always sent
    return _p("limit", "per_page", Location.QUERY, max=100, default=30)


def _gpg(items=None):  # GitHub Link-header follow-url pagination
    return PaginationBinding(kind=PaginationKind.LINK_FOLLOW, link_rel="next", items_field=items)


def _ga(name, method, path, params=None, path_variants=None, unwrap=None, pagination=None):
    return ActionBinding(
        name=name,
        method=method,
        endpoint="main",
        path=path,
        params=params or [],
        path_variants=path_variants or [],
        unwrap=unwrap,
        pagination=pagination or PaginationBinding(),
    )


_OR = lambda: [_gpath("owner"), _gpath("repo")]  # noqa: E731 — common owner/repo path pair

_GH = [
    # Repositories
    _ga(
        "list_repos",
        "GET",
        "/user/repos",
        params=[_gpath("org"), _gpath("user"), _glimit()],
        path_variants=[
            PathVariant(when_present="org", path="/orgs/{org}/repos"),
            PathVariant(when_present="user", path="/users/{user}/repos"),
        ],
        pagination=_gpg(),
    ),
    _ga("get_repo", "GET", "/repos/{owner}/{repo}", params=_OR()),
    _ga(
        "create_repo",
        "POST",
        "/user/repos",
        params=[
            _gpath("org"),
            _gb("name", required=True),
            _gb("private", default=False),
            _gb("auto_init", default=False),
            _gb("description"),
        ],
        path_variants=[PathVariant(when_present="org", path="/orgs/{org}/repos")],
    ),
    _ga("fork_repo", "POST", "/repos/{owner}/{repo}/forks", params=[*_OR(), _gb("organization")]),
    # Issues
    _ga(
        "list_issues",
        "GET",
        "/repos/{owner}/{repo}/issues",
        params=[*_OR(), _gq("state"), _gq("labels"), _gq("assignee"), _glimit()],
        pagination=_gpg(),
    ),
    _ga(
        "create_issue",
        "POST",
        "/repos/{owner}/{repo}/issues",
        params=[
            *_OR(),
            _gb("title", required=True),
            _gb("body"),
            _gb("labels", ty="string[]"),
            _gb("assignees", ty="string[]"),
        ],
    ),
    _ga(
        "get_issue",
        "GET",
        "/repos/{owner}/{repo}/issues/{issue_number}",
        params=[*_OR(), _gpath("issue_number")],
    ),
    _ga(
        "update_issue",
        "PATCH",
        "/repos/{owner}/{repo}/issues/{issue_number}",
        params=[
            *_OR(),
            _gpath("issue_number"),
            _gb("title"),
            _gb("body"),
            _gb("state"),
            _gb("labels", ty="string[]"),
            _gb("assignees", ty="string[]"),
        ],
    ),
    _ga(
        "add_labels",
        "POST",
        "/repos/{owner}/{repo}/issues/{issue_number}/labels",
        params=[*_OR(), _gpath("issue_number"), _gb("labels", ty="string[]", required=True)],
    ),
    _ga(
        "remove_label",
        "DELETE",
        "/repos/{owner}/{repo}/issues/{issue_number}/labels/{label_name}",
        params=[*_OR(), _gpath("issue_number"), _gpath("label_name")],
    ),
    _ga(
        "create_comment",
        "POST",
        "/repos/{owner}/{repo}/issues/{issue_number}/comments",
        params=[*_OR(), _gpath("issue_number"), _gb("body", required=True)],
    ),
    _ga(
        "list_comments",
        "GET",
        "/repos/{owner}/{repo}/issues/{issue_number}/comments",
        params=[*_OR(), _gpath("issue_number"), _glimit()],
        pagination=_gpg(),
    ),
    # Pull requests
    _ga(
        "list_pull_requests",
        "GET",
        "/repos/{owner}/{repo}/pulls",
        params=[*_OR(), _gq("state"), _glimit()],
        pagination=_gpg(),
    ),
    _ga(
        "get_pull_request",
        "GET",
        "/repos/{owner}/{repo}/pulls/{pr_number}",
        params=[*_OR(), _gpath("pr_number")],
    ),
    _ga(
        "create_pull_request",
        "POST",
        "/repos/{owner}/{repo}/pulls",
        params=[
            *_OR(),
            _gb("title", required=True),
            _gb("head", required=True),
            _gb("base", required=True),
            _gb("body"),
            _gb("draft", default=False),
        ],
    ),
    _ga(
        "merge_pull_request",
        "PUT",
        "/repos/{owner}/{repo}/pulls/{pr_number}/merge",
        params=[
            *_OR(),
            _gpath("pr_number"),
            _gb("merge_method", default="merge"),
            _gb("commit_title"),
            _gb("commit_message"),
        ],
    ),
    # Commits / branches
    _ga(
        "list_commits",
        "GET",
        "/repos/{owner}/{repo}/commits",
        params=[*_OR(), _gq("sha"), _gq("path"), _gq("author"), _glimit()],
        pagination=_gpg(),
    ),
    _ga(
        "list_branches",
        "GET",
        "/repos/{owner}/{repo}/branches",
        params=[*_OR(), _glimit()],
        pagination=_gpg(),
    ),
    _ga(
        "get_branch",
        "GET",
        "/repos/{owner}/{repo}/branches/{branch}",
        params=[*_OR(), _gpath("branch")],
    ),
    # Releases
    _ga(
        "list_releases",
        "GET",
        "/repos/{owner}/{repo}/releases",
        params=[*_OR(), _glimit()],
        pagination=_gpg(),
    ),
    _ga("get_latest_release", "GET", "/repos/{owner}/{repo}/releases/latest", params=_OR()),
    _ga(
        "create_release",
        "POST",
        "/repos/{owner}/{repo}/releases",
        params=[
            *_OR(),
            _gb("tag_name", required=True),
            _gb("draft", default=False),
            _gb("prerelease", default=False),
            _gb("name"),
            _gb("body"),
            _gb("target_commitish"),
        ],
    ),
    # Contents (note: {path} is interpolated raw in the connector, like our executor)
    _ga(
        "get_content",
        "GET",
        "/repos/{owner}/{repo}/contents/{path}",
        params=[*_OR(), _gpath("path"), _gq("ref")],
    ),
    _ga(
        "create_or_update_file",
        "PUT",
        "/repos/{owner}/{repo}/contents/{path}",
        params=[
            *_OR(),
            _gpath("path"),
            _gb("message", required=True),
            _gb("content", required=True),
            _gb("sha"),
            _gb("branch"),
        ],
    ),
    _ga(
        "delete_file",
        "DELETE",
        "/repos/{owner}/{repo}/contents/{path}",
        params=[
            *_OR(),
            _gpath("path"),
            _gb("message", required=True),
            _gb("sha", required=True),
            _gb("branch"),
        ],
    ),
    # Workflows
    _ga(
        "list_workflows",
        "GET",
        "/repos/{owner}/{repo}/actions/workflows",
        params=[*_OR(), _glimit()],
        unwrap="workflows",
        pagination=_gpg("workflows"),
    ),
    _ga(
        "list_workflow_runs",
        "GET",
        "/repos/{owner}/{repo}/actions/runs",
        params=[*_OR(), _gpath("workflow_id"), _gq("branch"), _gq("status"), _glimit()],
        path_variants=[
            PathVariant(
                when_present="workflow_id",
                path="/repos/{owner}/{repo}/actions/workflows/{workflow_id}/runs",
            )
        ],
        unwrap="workflow_runs",
        pagination=_gpg("workflow_runs"),
    ),
    _ga(
        "trigger_workflow",
        "POST",
        "/repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches",
        params=[
            *_OR(),
            _gpath("workflow_id"),
            _gb("ref", default="main"),
            _gb("inputs", ty="object"),
        ],
    ),
    # Gists (create_gist is an escape hatch — files map is transformed per-value)
    _ga("list_gists", "GET", "/gists", params=[_glimit()], pagination=_gpg()),
    # Search (arg `query` -> wire `q`; order always sent, default desc)
    _ga(
        "search_code",
        "GET",
        "/search/code",
        params=[_gq("query", "q", required=True), _glimit()],
        unwrap="items",
        pagination=_gpg("items"),
    ),
    _ga(
        "search_repos",
        "GET",
        "/search/repositories",
        params=[
            _gq("query", "q", required=True),
            _gq("order", default="desc"),
            _gq("sort"),
            _glimit(),
        ],
        unwrap="items",
        pagination=_gpg("items"),
    ),
    _ga(
        "search_issues",
        "GET",
        "/search/issues",
        params=[
            _gq("query", "q", required=True),
            _gq("order", default="desc"),
            _gq("sort"),
            _glimit(),
        ],
        unwrap="items",
        pagination=_gpg("items"),
    ),
    # Users / misc
    _ga("get_authenticated_user", "GET", "/user"),
    _ga("get_rate_limit", "GET", "/rate_limit"),
    _ga("star_repo", "PUT", "/user/starred/{owner}/{repo}", params=_OR()),
    _ga("unstar_repo", "DELETE", "/user/starred/{owner}/{repo}", params=_OR()),
]

GITHUB = ConnectorBinding(
    name="github",
    default_endpoint="main",
    endpoints={
        "main": EndpointBinding(
            id="main",
            base_url="https://api.github.com",
            encoding="json",
            auth_kind=AuthKind.BEARER,
            auth_header="Authorization",
            extra_headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        ),
    },
    actions={a.name: a for a in _GH},
    escape_hatches=["create_gist"],
)

GITHUB_BINDING = GITHUB
