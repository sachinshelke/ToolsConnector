# Code Platforms

Connectors for source code hosting and collaboration platforms. 2 connectors, 85 actions.

---

### GitHub

**Category:** Code Platforms | **Auth:** Bearer token (PAT, OAuth, GitHub App) | **Actions:** 37 | **Status:** ✅ Tier 1 (33/37 live-verified)

Connect to GitHub via the REST API at `api.github.com`. Full coverage of repositories, issues, pull requests, commits, branches, releases, file content (read + write + delete), labels, comments, workflows (GitHub Actions), gists, code/repo/issue search, and user/rate-limit endpoints. Pinned to API version `2022-11-28`. Supports every GitHub token family — `ghp_*`, `github_pat_*`, `gho_*`, `ghs_*`, `ghu_*`, `ghr_*`.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| list_repos | List repositories for the user, an org, or another user | No |
| get_repo | Get details of a single repository | No |
| create_repo | Create a new repository (user or org) | Yes |
| fork_repo | Fork a repository to your account or an org | Yes |
| list_issues | List issues in a repository | No |
| create_issue | Create a new issue | Yes |
| get_issue | Get details of a single issue | No |
| update_issue | Update an existing issue | No |
| add_labels | Add labels to an issue | No |
| remove_label | Remove a label from an issue | Yes |
| create_comment | Create a comment on an issue or PR | Yes |
| list_comments | List comments on an issue | No |
| list_pull_requests | List pull requests in a repository | No |
| get_pull_request | Get details of a single PR | No |
| create_pull_request | Create a new PR | Yes |
| merge_pull_request | Merge a PR (`merge`/`squash`/`rebase`) | Yes |
| list_commits | List commits in a repository | No |
| list_branches | List branches in a repository | No |
| get_branch | Get a single branch with protection status | No |
| list_releases | List releases (newest first) | No |
| get_latest_release | Get the latest published release | No |
| create_release | Create a new release | Yes |
| get_content | Get a file or directory listing | No |
| create_or_update_file | Create or update a file (base64-encoded content) | Yes |
| delete_file | Delete a file | Yes |
| list_workflows | List GitHub Actions workflows | No |
| list_workflow_runs | List workflow runs (overall or per-workflow) | No |
| trigger_workflow | Trigger a workflow via `workflow_dispatch` | Yes |
| list_gists | List gists for the authenticated user | No |
| create_gist | Create a new gist | Yes |
| search_code | Search code across GitHub | No |
| search_repos | Search repositories | No |
| search_issues | Search issues and PRs | No |
| get_authenticated_user | Get the authenticated user's profile | No |
| get_rate_limit | Check the current API rate limit status | No |
| star_repo | Star a repository | Yes |
| unstar_repo | Unstar a repository | Yes |

**Quick start:**

```python
kit = ToolKit(["github"], credentials={"github": "ghp_your-personal-access-token"})
result = kit.execute("github_list_issues", {"owner": "anthropics", "repo": "toolsconnector", "state": "open"})
```

**Rate-limit handling (GitHub-specific):** GitHub uses HTTP 403 (not 429) for both primary (5,000/hour authenticated) and secondary (abuse detection) rate limits. The connector detects both via `X-RateLimit-Remaining: 0` headers or `"secondary rate limit"` / `"abuse"` body text and raises typed `RateLimitError` with computed `retry_after_seconds` — instead of the generic 403 → `PermissionDeniedError` mapping that would lose the rate-limit semantics. See the connector README for the full error matrix.

**Path-traversal protection:** Every URL path segment built from caller input passes through a `_p()` percent-encoding helper that escapes `/` and URL-unsafe characters. Adversarial `owner="../admin"` becomes `..%2Fadmin`, preserving the `/repos/` prefix.

---

### GitLab

**Category:** Code Platforms | **Auth:** Personal Access Token | **Actions:** 8

Connect to GitLab to manage projects, issues, merge requests, and CI/CD pipelines.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| list_projects | List projects accessible to the user | No |
| get_project | Get details of a specific project | No |
| list_issues | List issues in a project | No |
| create_issue | Create a new issue | Yes |
| list_merge_requests | List merge requests in a project | No |
| create_merge_request | Create a new merge request | Yes |
| list_pipelines | List CI/CD pipelines in a project | No |
| get_pipeline | Get details of a specific pipeline | No |

**Quick start:**

```python
kit = ToolKit(["gitlab"], credentials={"gitlab": "glpat-your-access-token"})
result = kit.execute("gitlab_list_projects", {"owned": True})
```
