# GitHub Automation in Python: Issues, PRs & Files (2026)

Automate GitHub from Python — create issues, comment, manage files, and open
pull requests — through one standardized interface, no `PyGithub` required. The
GitHub connector is **Tier 1 live-verified** (33+ actions tested end-to-end
against `api.github.com`), so the request shapes are confirmed correct.

## TL;DR

```python
import json
from toolsconnector.serve import ToolKit

kit = ToolKit(["github"], credentials={"github": "ghp_your-token"})

issue = json.loads(kit.execute("github_create_issue", {
    "owner": "your-org", "repo": "your-repo",
    "title": "Flaky test in CI", "body": "Fails ~1 in 5 runs on Python 3.11.",
    "labels": ["bug"],
}))
print(issue["number"], issue["html_url"])
```

## 1. Install

```bash
pip install "toolsconnector[github]"
```

## 2. Get a token

1. **github.com → Settings → Developer settings → Personal access tokens**.
2. **Tokens (classic)** → *Generate new token* → select scopes: `repo`
   (private repos), `workflow` (Actions), `gist`, `read:user`.
3. Copy the `ghp_…` value (shown once). Fine-grained PATs (`github_pat_…`),
   OAuth tokens (`gho_…`), and GitHub App installation tokens (`ghs_…`) all work too.

ToolsConnector is **BYOK** — pass the token at the call site or via
`TC_GITHUB_CREDENTIALS`. It's never stored or proxied.

## 3. Common automations

### Create an issue and comment on it

```python
issue = json.loads(kit.execute("github_create_issue", {
    "owner": "octocat", "repo": "hello-world",
    "title": "Add retry to the uploader", "body": "Transient 502s need a backoff.",
    "labels": ["enhancement"], "assignees": ["octocat"],
}))

kit.execute("github_create_comment", {
    "owner": "octocat", "repo": "hello-world",
    "issue_number": issue["number"], "body": "Picking this up 👍",
})
```

### List open issues

```python
issues = json.loads(kit.execute("github_list_issues", {
    "owner": "octocat", "repo": "hello-world", "state": "open", "limit": 20,
}))
for it in issues["items"]:
    print(it["number"], it["title"])
```

### Create or update a file (commit via the API)

```python
import base64

kit.execute("github_create_or_update_file", {
    "owner": "octocat", "repo": "hello-world",
    "path": "docs/CHANGELOG.md",
    "message": "docs: add changelog",
    "content": base64.b64encode(b"# Changelog\n").decode(),
    "branch": "main",
})
```

Unicode and binary round-trip correctly — base64 in, base64 out.

### Who am I?

```python
me = json.loads(kit.execute("github_get_authenticated_user", {}))
print(me["login"])
```

## 4. As an AI agent tool

```python
kit = ToolKit(["github"], credentials={"github": "ghp_…"})
tools = kit.to_openai_tools()     # or to_anthropic_tools()
# kit.serve_mcp()                 # expose all 37 GitHub tools to Claude Desktop / Cursor
```

Run `kit = ToolKit(["github"], exclude_dangerous=True)` for a read-mostly,
agent-safe mode (filters out create/delete/merge actions).

## Common errors

| Error | Cause | Fix |
|---|---|---|
| `InvalidCredentialsError` (401) | Bad/revoked token | Regenerate at github.com/settings/tokens |
| `PermissionDeniedError` (403) | Token missing a scope, or no write access to the repo | Add the `repo` scope; confirm you can write to the repo |
| `RateLimitError` | Hit the 5,000/hr primary limit **or** secondary abuse-detection throttle | Honor `e.retry_after_seconds` and back off |
| `NotFoundError` (404) | Wrong `owner`/`repo`, or a private repo your token can't see | Check the slug; ensure the token has `repo` scope |
| `ValidationError` (422) | Bad field (e.g. a label that doesn't exist, or `sha` mismatch on file update) | For file updates, fetch the current `sha` first via `github_get_content` |

GitHub returns **403** for both primary and secondary rate limits — ToolsConnector
detects both and raises a typed `RateLimitError` with a computed `retry_after_seconds`,
so you don't mistake throttling for a permissions problem.

## Next steps

- [GitHub connector reference](https://toolsconnector.github.io/#/connectors/github) — all 37 actions (branches, commits, releases, gists, search)
- [Resilience & error handling](https://toolsconnector.github.io/#/docs/resilience) — retries, rate limits, typed errors
- [AI frameworks guide](https://toolsconnector.github.io/#/docs/ai-frameworks)

---

*Part of [ToolsConnector](https://toolsconnector.github.io) — one open-source Python interface to 73 APIs, for AI agents and apps.*
