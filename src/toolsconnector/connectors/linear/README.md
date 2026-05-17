# Linear

> Streamlined issue tracking for software teams

| | |
|---|---|
| **Company** | Linear Inc. |
| **Category** | Project Management |
| **Protocol** | GraphQL |
| **Website** | [linear.app](https://linear.app) |
| **API Docs** | [developers.linear.app](https://developers.linear.app/docs/graphql/working-with-the-graphql-api) |
| **Auth** | Personal API Key (raw, no `Bearer` prefix) |
| **Rate Limit** | 2,500 req/hour (personal key) · 5,000 req/hour (OAuth) — connector throttle: 40 req/min |
| **Pricing** | Free tier, Plus from $8/user/month |

---

## Overview

The Linear GraphQL API provides access to issues, projects, cycles, teams, and labels. Track bugs and features, manage sprints, automate workflows, and build integrations with Linear's modern project management platform.

## Use Cases

- Issue tracking
- Sprint management
- Bug triage automation
- Development workflow
- Cross-tool project sync

## Installation

```bash
pip install "toolsconnector[linear]"
```

## Credentials

Two equivalent ways to provide the API key — the same primitives every ToolsConnector connector uses:

```python
# Programmatic
kit = ToolKit(["linear"], credentials={"linear": "lin_api_..."})

# Environment variable (any one of these; first match wins)
# export TC_LINEAR_CREDENTIALS=...     # preferred
# export TC_LINEAR_API_KEY=...
# export TC_LINEAR_TOKEN=...
kit = ToolKit(["linear"])  # no credentials arg — resolved from env
```

Linear personal API keys (`lin_api_*`) are sent **raw** in the `Authorization` header — Linear does NOT use the `Bearer` prefix for personal keys. The connector handles this automatically.

See the [Credentials Guide](../../../docs/guides/credentials.md) for the full resolution priority + multi-workspace pattern.

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["linear"], credentials={"linear": "lin_api_your_key"})

# List issues with optional team and state filters
result = kit.execute("linear_list_issues", {"team_id": "team-uuid", "state": "In Progress"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["linear"], credentials={"linear": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["linear"], credentials={"linear": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### Personal API Key

1. Sign in to [Linear](https://linear.app)
2. Open **Settings → API → Personal API keys**
3. **+ New API key** → label it → copy the `lin_api_...` value
4. The key has the same permissions as the user who created it (read + write on every team they're a member of)

[Get credentials →](https://linear.app/settings/api)

## Error Handling

```python
from toolsconnector.errors import (
    InvalidCredentialsError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)

try:
    result = kit.execute("linear_list_issues", {})
except InvalidCredentialsError as e:
    print(f"Token rejected: {e.suggestion}")
except NotFoundError as e:
    print(f"Resource missing: {e.suggestion}")
except RateLimitError as e:
    print(f"Rate limited. Retry in {e.retry_after_seconds}s")
except ValidationError as e:
    # Linear returns business errors as HTTP 200 + {"errors": [...]} —
    # _graphql raises ValueError for those (not ValidationError). Catch
    # ValueError too if you need to handle malformed-input cases.
    print(f"Invalid input: {e.message}")
```

| Typed exception | HTTP status | Cause | Fix |
|---|---|---|---|
| `InvalidCredentialsError` | 401 | API key invalid or revoked | Regenerate at Settings → API → Personal API keys |
| `NotFoundError` | 404 | Issue/team/project/user UUID doesn't exist OR you don't have access | Verify the UUID; confirm your account is a member of the target team |
| `RateLimitError` | **400** with `errors[].extensions.code = "RATELIMITED"` | Hit Linear's 2,500 req/hour (personal-key) or 5,000 (OAuth) cap | Sleep per `e.retry_after_seconds` (computed from `X-RateLimit-*-Reset` epoch-ms headers), then retry |
| `ServerError` | 5xx | Linear-side outage | Exponential backoff retry |
| `ValueError` (NOT a typed TC error) | 200 with `errors[]` | Per-action GraphQL semantic error (bad field, missing arg, type mismatch) | Inspect `str(e)` for Linear's error messages |
| `TransportError` | n/a (network) | Connection drop, mid-stream read failure, non-JSON body (rare CDN 502s) | Retry with backoff; capture `e.details["body_preview"]` if non-JSON |
| `ConnectionError` | n/a (network) | DNS failure / TCP RST / TLS handshake failure reaching `api.linear.app` | Verify network; transient failures retry-eligible |
| `TimeoutError` | n/a (network) | Request exceeded `timeout` (default 30s) without a response | Increase timeout via `Linear(timeout=N)`, or retry |

### Filter operators

Linear's filter inputs support these comparators (per [Linear filtering docs](https://linear.app/developers/filtering)):

- **Universal**: `eq`, `neq`, `in`, `nin`
- **Numeric / date**: `lt`, `lte`, `gt`, `gte`
- **String**: `contains`, `notContains`, `containsIgnoreCase`, `notContainsIgnoreCase`, `startsWith`, `notStartsWith`, `endsWith`, `notEndsWith`, `eqIgnoreCase`, `neqIgnoreCase`
- **Optional fields**: `null` (existence check)

This connector uses only `eq` (the most common case). For advanced filtering, call `_graphql()` directly with your own query.

**Combinators**: multiple top-level filter fields are combined with **implicit AND** (e.g. `{team: {id: {eq: "..."}}, state: {name: {eq: "..."}}}` means "team X AND state Y"). For OR, Linear supports `{or: [...]}`. There is **no** `{and: [...]}` syntax — AND is always implicit.

**Case sensitivity**: `eq`, `contains`, and friends are **case-sensitive** by default. Use the `...IgnoreCase` variants for case-insensitive matching.

### Rate-limit quirks (Linear-specific)

Linear differs from most REST APIs on rate limiting:

- **Status code is HTTP 400, not 429.** Linear signals throttling through the GraphQL `errors[]` envelope with `extensions.code = "RATELIMITED"`. The shared `raise_typed_for_status` helper would otherwise map 400 → `ValidationError`. This connector inspects the body BEFORE the status mapping and raises `RateLimitError` correctly.
- **No `Retry-After` header.** Linear sends `X-RateLimit-Requests-Reset` (overall quota), `X-RateLimit-Endpoint-Requests-Reset` (per-endpoint), and `X-RateLimit-Complexity-Reset` (complexity quota) as **epoch-milliseconds** timestamps. The connector picks the most-specific header and computes `RateLimitError.retry_after_seconds = max(0, reset - now)`.
- **Published caps**: 2,500 req/hour per user (personal API key), 5,000 req/hour per user (OAuth app), 600 req/hour per IP (unauthenticated). The connector's local throttle is `RateLimitSpec(rate=40, period=60, burst=10)` ≈ 2,400 req/hour with a small burst — sits under the personal-key cap with 100 req/hour headroom.

Source: [linear.app/developers/rate-limiting](https://linear.app/developers/rate-limiting).

### Partial-success behavior

Linear's GraphQL API can return HTTP 200 with **both** a `data` field AND an `errors[]` field (per [Linear's docs](https://linear.app/developers/graphql) — "queries can partially succeed"). This connector takes the **fail-fast** path: any `errors[]` content raises `ValueError` with all error messages concatenated, even if partial `data` is also present. If your use case needs partial data, drop down to `httpx.AsyncClient` and call `/graphql` directly.

## GraphQL injection protection ✓

Every action that takes user input passes that input as a **typed GraphQL variable**, not as inline query text. This eliminates the entire GraphQL-injection surface — the server validates and escapes variables, and adversarial values cannot alter query structure.

```python
# An adversarial team_id like:
#   abc"} }) { issueLabels { nodes { id name } } } #
#
# Is sent as:  variables = {"filter": {"team": {"id": {"eq": "abc\"} ..."}}}
# Not as:      query = '... team: { id: { eq: "abc"} }) { ...injection... } ...'
#
# The GraphQL server rejects malformed values as type errors at the
# variable-resolution stage, BEFORE any query execution.
```

This is pinned by regression tests in [tests/connectors/test_linear.py](../../../tests/connectors/test_linear.py) — the `test_injection_*` and `test_no_action_inlines_id_into_query` cases fire if any future refactor reintroduces an inline interpolation.

## Verification Status

All 19 actions are **doc-verified** — every GraphQL query, variables shape, pagination flow, and error mapping has been cross-checked against the connector and pinned by respx mocks in [tests/connectors/test_linear.py](../../../tests/connectors/test_linear.py) (19 tests covering happy path, injection regression, error mapping, pagination, limit clamping, and dangerous-flag audit).

Live verification (Tier 1) is deferred until the `[auth]` extra ships (per [ROADMAP.md](../../../ROADMAP.md)) — at that point any `lin_api_*` key can be plugged in and the standard live-test harness will exercise all 19 actions end-to-end.

| Action | GraphQL Operation | Status |
|---|---|---|
| `list_issues` | `query issues(first, after, filter, orderBy)` | Doc verified |
| `get_issue` | `query issue(id: $id)` | Doc verified |
| `create_issue` | `mutation issueCreate(input: IssueCreateInput!)` | Doc verified |
| `update_issue` | `mutation issueUpdate(id, input: IssueUpdateInput!)` | Doc verified |
| `delete_issue` | `mutation issueDelete(id: $id)` | Doc verified |
| `search_issues` | `query issueSearch(query, first, after)` | Doc verified |
| `list_teams` | `query teams { nodes { ... } }` (no user input) | Doc verified |
| `list_projects` | `query projects(first, after)` | Doc verified |
| `update_project` | `mutation projectUpdate(id, input: ProjectUpdateInput!)` | Doc verified |
| `delete_project` | `mutation projectDelete(id: $id)` | Doc verified |
| `list_users` | `query users(first, after)` | Doc verified |
| `get_user` | `query user(id: $id)` | Doc verified |
| `list_labels` | `query issueLabels(filter, first)` | Doc verified |
| `create_label` | `mutation issueLabelCreate(input: IssueLabelCreateInput!)` | Doc verified |
| `get_workflow_states` | `query workflowStates(filter, first)` | Doc verified |
| `list_cycles` | `query cycles(first, after, filter, orderBy)` | Doc verified |
| `get_cycle` | `query cycle(id: $id)` | Doc verified |
| `add_comment` | `mutation commentCreate(input: CommentCreateInput!)` | Doc verified |
| `list_issue_comments` | `query issue(id) { comments { nodes } }` | Doc verified |

## Actions

<!-- ACTIONS_START -->
<!-- This section is auto-generated from the connector spec. Do not edit manually. -->
<!-- ACTIONS_END -->

## Tips

- Use `search_issues` for filtered queries and `list_cycles` for paginated browsing
- Rate limit is 400 requests/minute — use pagination and caching to minimize API calls
- Actions marked as destructive (`add_comment`, `create_issue`, `create_label`) cannot be undone — use with caution
- Use cursor-based pagination for large result sets — pass the `cursor` from previous responses

## Related Connectors

- [Jira](../jira/) — Issue tracking
- [Asana](../asana/) — Work management
- [Trello](../trello/) — Kanban boards

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
