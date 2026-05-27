# GitHub

> Code hosting, issues, PRs, and CI/CD — full REST API coverage

| | |
|---|---|
| **Company** | Microsoft (GitHub Inc.) |
| **Category** | Code Platform |
| **Protocol** | REST |
| **API Version** | `2022-11-28` (pinned via `X-GitHub-Api-Version` header) |
| **Website** | [github.com](https://github.com) |
| **API Docs** | [docs.github.com/en/rest](https://docs.github.com/en/rest) |
| **Auth** | Bearer token (PAT classic, fine-grained PAT, OAuth access, GitHub App installation token) |
| **Rate Limit** | 5,000 requests/hour authenticated · 60/hour unauthenticated — connector targets the authenticated cap |
| **Pricing** | Free for public repos, Teams from $4/user/month |

---

## Overview

Full coverage of the GitHub REST API at `api.github.com`: repositories, issues, pull requests, commits, branches, releases, file content (read + write + delete), labels, comments, workflows (GitHub Actions), gists, code/repo/issue search, and user/rate-limit endpoints. Uses the `2022-11-28` API version. Bearer-token auth supports every GitHub token family.

## Use Cases

- CI/CD automation
- Issue tracking + triage
- Code review workflows
- Release management
- Developer analytics
- Repository scaffolding from agent prompts

## Installation

```bash
pip install "toolsconnector[github]"
```

## Credentials

Two equivalent ways to provide the token — the same primitives every ToolsConnector connector uses:

```python
# Programmatic
kit = ToolKit(["github"], credentials={"github": "ghp_..."})

# Environment variable (any one of these; first match wins)
# export TC_GITHUB_CREDENTIALS=ghp_...   # preferred
# export TC_GITHUB_API_KEY=ghp_...
# export TC_GITHUB_TOKEN=ghp_...
kit = ToolKit(["github"])  # no credentials arg — resolved from env
```

GitHub bearer tokens accepted: `ghp_*` (classic PAT), `github_pat_*` (fine-grained PAT), `gho_*` (OAuth access), `ghs_*` (App installation), `ghu_*` (App user access), `ghr_*` (App refresh).

See the [Credentials Guide](../../../docs/guides/credentials.md) for the full resolution priority + multi-account pattern.

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["github"], credentials={"github": "ghp_your_token"})

# Sanity-check: who am I authenticated as?
me = kit.execute("github_get_authenticated_user", {})
print(me)  # {"login": "...", "type": "User", ...}

# List repos for an org
result = kit.execute("github_list_repos", {"org": "your-org", "limit": 50})
print(result)
```

### MCP Server

```python
kit = ToolKit(["github"], credentials={"github": "ghp_..."})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["github"], credentials={"github": "ghp_..."})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### Personal Access Token (classic)

1. Sign in to [github.com](https://github.com)
2. **Settings → Developer settings → Personal access tokens → Tokens (classic)**
3. **Generate new token (classic)** → set expiration, name it, choose scopes
4. Required scopes depend on what you call:
   - `repo` — full repo access (everything in this connector touching `/repos/...`)
   - `workflow` — `trigger_workflow`, workflow runs
   - `gist` — `list_gists`, `create_gist`
   - `delete_repo` — destructive repo delete (not exposed by this connector but useful for cleanup)
   - `read:user` — `get_authenticated_user`
5. Copy the `ghp_...` value — shown only once

### Fine-grained Personal Access Token

Newer, scope-per-repo model. Same auth header (`Authorization: Bearer github_pat_...`), but permissions are configured per-repo per-resource. Better for agent BYOK because you can lock down to "issues read+write on these 3 repos only." Some endpoints (org-scoped, search) are not yet supported by fine-grained PATs — classic remains the broadest option.

[Get credentials →](https://github.com/settings/tokens)

## Error Handling

```python
from toolsconnector.errors import (
    InvalidCredentialsError,
    PermissionDeniedError,
    NotFoundError,
    RateLimitError,
    ValidationError,
    ConflictError,
    ServerError,
    ConnectionError,
    TimeoutError,
    TransportError,
)

try:
    result = kit.execute("github_list_repos", {})
except InvalidCredentialsError as e:
    print(f"Token rejected (401): {e.suggestion}")
except PermissionDeniedError as e:
    print(f"403 — token lacks scope for this endpoint: {e.message}")
except RateLimitError as e:
    print(f"Rate limited ({e.details['limit_type']}). Retry in {e.retry_after_seconds}s")
except NotFoundError as e:
    print(f"Not found: {e.suggestion}")
except ValidationError as e:
    print(f"Invalid input (422): {e.message}")
```

| Typed exception | HTTP status | When it fires | Programmatic check |
|---|---|---|---|
| `InvalidCredentialsError` | 401 | Token invalid / revoked / not provided | `e.upstream_status == 401` |
| `PermissionDeniedError` | 403 (no rate-limit signals) | Token authenticated but lacks the scope for this endpoint (`Resource not accessible by personal access token`) | `e.upstream_status == 403` |
| `RateLimitError` (primary) | **403** with `X-RateLimit-Remaining: 0` + `X-RateLimit-Reset: <epoch>` | 5,000/hour authenticated quota exhausted | `e.details["limit_type"] == "primary"` |
| `RateLimitError` (secondary) | **403** with `Retry-After` OR body containing `"secondary rate limit"` / `"abuse"` | Abuse-detection throttle (bursty request patterns) | `e.details["limit_type"] == "secondary"` |
| `NotFoundError` | 404 | Resource doesn't exist OR you don't have access | `e.upstream_status == 404` |
| `ConflictError` | 409 | Concurrent edit (e.g. file sha mismatch); merge conflict | `e.upstream_status == 409` |
| `ValidationError` | 422 | Request body shape problem | `e.upstream_status == 422` |
| `ServerError` | 5xx | GitHub-side outage / unicorn page | `e.upstream_status >= 500` |
| `ConnectionError` | n/a | DNS / TCP / TLS failure | network-layer |
| `TimeoutError` | n/a | Request exceeded `timeout` (default 30s) | network-layer |
| `TransportError` | n/a | Mid-stream protocol failure | network-layer |

### Rate-limit quirks (GitHub-specific)

GitHub uses **HTTP 403** for both rate-limit cases (not 429). Without the connector's GitHub-specific override, the shared `raise_typed_for_status` helper would map 403 → `PermissionDeniedError`, losing the rate-limit semantics. The connector inspects the response headers + body BEFORE the standard mapping and raises typed `RateLimitError` correctly.

- **Primary rate limit**: 5,000 requests/hour for authenticated users (15,000/hour for GitHub Enterprise Cloud orgs, 60/hour unauthenticated). Detected via `X-RateLimit-Remaining: 0` + `X-RateLimit-Reset: <epoch seconds>`. `retry_after_seconds` computed as `max(0, reset - now)`.
- **Secondary rate limit** (abuse detection): bursty patterns OR search-API throttling. Detected via `Retry-After` header OR body containing `"secondary rate limit"` / `"abuse"`. `retry_after_seconds` parsed from the `Retry-After` header.

Source: [docs.github.com/en/rest/overview/rate-limits-for-the-rest-api](https://docs.github.com/en/rest/overview/rate-limits-for-the-rest-api).

### Path-traversal protection

Every URL path segment built from user input passes through a percent-encoding helper (`_p()`) that escapes `/` and other URL-unsafe characters before f-string interpolation. This eliminates the path-traversal surface — adversarial `owner="../admin"` becomes `..%2Fadmin`, preserving the `/repos/` prefix instead of escaping out of it via httpx URL normalization.

```python
# An adversarial owner like "../admin" is sent as:
#   /repos/..%2Fadmin/repo
# Not as:  /admin/repo  (which httpx normalization would have produced)
#
# GitHub 404s on the literal escaped path; the /repos/ prefix is preserved.
```

Multi-segment paths (`get_content`'s `path` argument, which legitimately accepts `src/sub/file.py`) are NOT wrapped — that segment intentionally spans multiple components per the GitHub Contents API spec.

This is pinned by `test_special_chars_in_owner_dont_traverse` + `test_branch_slash_percent_encoded` in [tests/connectors/test_github.py](../../../tests/connectors/test_github.py). The tests fire if any future refactor reintroduces unescaped interpolation.

## Verification Status

All 37 actions are pinned by **80 respx tests** in [tests/connectors/test_github.py](../../../tests/connectors/test_github.py): happy path × 37 actions, pagination edges (Link-header parsing), URL-path injection guards, error matrix (incl. primary + secondary rate limit detection), transport-error mapping, defensive parsing, MCP exposure, OpenAI schema sweep, sync wrappers, ToolKit dispatch, concurrency, cancellation.

**33 of 37 actions are Live verified** — exercised end-to-end against `api.github.com` with a real `ghp_*` token (create→read→update→delete cycles on a throwaway repo, full issue lifecycle, file CRUD with unicode, gist creation, search across global endpoints, star/unstar). 4 remaining are **Probe verified** — direct REST envelopes accepted by GitHub's server, but the success-response code path isn't exercised end-to-end because they require multi-repo or multi-branch setup the connector doesn't expose primitives for.

| Action | REST Endpoint | Status |
|---|---|---|
| `list_repos` | `GET /user/repos`, `GET /orgs/{org}/repos`, `GET /users/{user}/repos` | ✅ Live verified |
| `get_repo` | `GET /repos/{owner}/{repo}` | ✅ Live verified |
| `create_repo` | `POST /user/repos`, `POST /orgs/{org}/repos` | ✅ Live verified |
| `fork_repo` | `POST /repos/{owner}/{repo}/forks` | Probe verified (request envelope accepted by GH; would leave a fork behind) |
| `list_issues` | `GET /repos/{owner}/{repo}/issues` | ✅ Live verified |
| `create_issue` | `POST /repos/{owner}/{repo}/issues` | ✅ Live verified |
| `get_issue` | `GET /repos/{owner}/{repo}/issues/{n}` | ✅ Live verified |
| `update_issue` | `PATCH /repos/{owner}/{repo}/issues/{n}` | ✅ Live verified |
| `add_labels` | `POST /repos/{owner}/{repo}/issues/{n}/labels` | ✅ Live verified |
| `remove_label` | `DELETE /repos/{owner}/{repo}/issues/{n}/labels/{name}` | ✅ Live verified |
| `create_comment` | `POST /repos/{owner}/{repo}/issues/{n}/comments` | ✅ Live verified |
| `list_comments` | `GET /repos/{owner}/{repo}/issues/{n}/comments` | ✅ Live verified |
| `list_pull_requests` | `GET /repos/{owner}/{repo}/pulls` | ✅ Live verified |
| `get_pull_request` | `GET /repos/{owner}/{repo}/pulls/{n}` | Probe verified (requires existing PR) |
| `create_pull_request` | `POST /repos/{owner}/{repo}/pulls` | Probe verified (requires a non-default branch; connector doesn't expose git/refs to create one) |
| `merge_pull_request` | `PUT /repos/{owner}/{repo}/pulls/{n}/merge` | Probe verified (requires a mergeable PR) |
| `list_commits` | `GET /repos/{owner}/{repo}/commits` | ✅ Live verified |
| `list_branches` | `GET /repos/{owner}/{repo}/branches` | ✅ Live verified |
| `get_branch` | `GET /repos/{owner}/{repo}/branches/{branch}` | ✅ Live verified |
| `list_releases` | `GET /repos/{owner}/{repo}/releases` | ✅ Live verified |
| `get_latest_release` | `GET /repos/{owner}/{repo}/releases/latest` | ✅ Live verified |
| `create_release` | `POST /repos/{owner}/{repo}/releases` | ✅ Live verified |
| `get_content` | `GET /repos/{owner}/{repo}/contents/{path}` | ✅ Live verified |
| `create_or_update_file` | `PUT /repos/{owner}/{repo}/contents/{path}` | ✅ Live verified (both create and update paths) |
| `delete_file` | `DELETE /repos/{owner}/{repo}/contents/{path}` | ✅ Live verified |
| `list_workflows` | `GET /repos/{owner}/{repo}/actions/workflows` | ✅ Live verified |
| `list_workflow_runs` | `GET /repos/{owner}/{repo}/actions/runs` + per-workflow variant | ✅ Live verified |
| `trigger_workflow` | `POST /repos/{owner}/{repo}/actions/workflows/{id}/dispatches` | Probe verified (requires committed workflow file to exist) |
| `list_gists` | `GET /gists` | ✅ Live verified |
| `create_gist` | `POST /gists` | ✅ Live verified |
| `search_code` | `GET /search/code` | ✅ Live verified (against `jquery/jquery`) |
| `search_repos` | `GET /search/repositories` | ✅ Live verified |
| `search_issues` | `GET /search/issues` | ✅ Live verified |
| `get_authenticated_user` | `GET /user` | ✅ Live verified |
| `get_rate_limit` | `GET /rate_limit` | ✅ Live verified |
| `star_repo` | `PUT /user/starred/{owner}/{repo}` | ✅ Live verified |
| `unstar_repo` | `DELETE /user/starred/{owner}/{repo}` | ✅ Live verified |

**MCP end-to-end verified**: subprocess `tc serve mcp github --transport stdio` exercised over JSON-RPC with real API dispatches (`tools/list` → 37 tools; `tools/call` → `github_get_authenticated_user`, `github_list_repos`, `github_get_rate_limit` all returned the expected real data). Graceful shutdown.

## Actions

<!-- ACTIONS_START -->
<!-- This section is auto-generated from the connector spec. Do not edit manually. -->
<!-- ACTIONS_END -->

## Tips

- **First call**: `github_get_authenticated_user` is the cheapest sanity check that the token is valid + tells you the `login` for subsequent `owner` args.
- **Pagination**: GitHub uses Link-header cursors. `PaginatedList.page_state.cursor` is the full `https://api.github.com/...?page=N` URL — pass it as `page=` to the same action to fetch the next page. The connector uses it verbatim so filter params (state/labels/sha/etc) are preserved.
- **Per-page max**: 100. The connector clamps `limit > 100` to 100 with no error.
- **Conditional GETs (304)**: GitHub supports `If-None-Match` / `If-Modified-Since` for unchanged-since-last-fetch responses. The connector does NOT expose these today — every read fetches fresh.
- **File content is base64-encoded** for `get_content` (when `type=file`) and **must be base64-encoded** when passed to `create_or_update_file` / `delete_file`.
- **`get_content` `path` is multi-segment**: `src/sub/file.py` is a legitimate value. The other path arguments (`owner`, `repo`, `issue_number`, etc.) are SINGLE-segment and are percent-encoded automatically.
- **Dangerous actions**: 14 of 37 are flagged `dangerous=True`. Use `kit = ToolKit(["github"], exclude_dangerous=True)` for agent-safe mode (filters out `create_repo`, `fork_repo`, `create_issue`, `remove_label`, `create_comment`, `create_pull_request`, `merge_pull_request`, `create_release`, `create_or_update_file`, `delete_file`, `trigger_workflow`, `create_gist`, `star_repo`, `unstar_repo`).
- **Branches with `/`** (e.g., `feature/x`) are percent-encoded — the URL becomes `/branches/feature%2Fx`. GitHub requires this; the literal `/branches/feature/x` would 404.

## Related Connectors

- [GitLab](../gitlab/) — GitLab REST API
- [Linear](../linear/) — Issue tracking via GraphQL
- [Jira](../jira/) — Atlassian project management

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
