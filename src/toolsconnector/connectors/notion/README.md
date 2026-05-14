# Notion

> All-in-one workspace for notes, docs, and databases

| | |
|---|---|
| **Company** | Notion Labs Inc. |
| **Category** | Knowledge |
| **Protocol** | REST |
| **Website** | [notion.so](https://notion.so) |
| **API Docs** | [developers.notion.com](https://developers.notion.com/reference) |
| **Auth** | Bearer Token (Internal Integration) — BYOK |
| **Rate Limit** | 3 requests/second average |
| **Pricing** | Free for personal, Plus from $10/user/month |

---

## Overview

The Notion API provides access to pages, databases, blocks, comments, and users. Query and update databases, create and modify pages, append content blocks, manage comments and threaded replies, and build integrations that sync data with your Notion workspace.

This connector exposes **24 actions** spanning all of Notion's core resource families (search, pages, databases, blocks, users, comments). It is pinned to `Notion-Version: 2022-06-28` for stability — see [Versioned API](#versioned-api) below for the rationale.

## Use Cases

- Knowledge base management
- Content publishing & documentation automation
- Project tracking via database rows
- CRM in Notion databases
- Threaded comment workflows (review/approval flows)

## Installation

```bash
pip install "toolsconnector[notion]"
```

## Credentials

Two equivalent ways to provide the integration token — the same primitives every ToolsConnector connector uses. Pick whichever fits your code; the patterns compose freely.

```python
# Programmatic
kit = ToolKit(["notion"], credentials={"notion": "secret_or_ntn_token"})

# Environment variable (any one of these; first match wins)
# export TC_NOTION_CREDENTIALS=...     # preferred
# export TC_NOTION_API_KEY=...
# export TC_NOTION_TOKEN=...
kit = ToolKit(["notion"])  # no credentials arg — resolved from env
```

To use multiple Notion workspaces in the same process (one token per workspace), instantiate one ToolKit per credential set, or call the `Notion` class directly with `Notion(credentials=...)`. See [Credentials Guide → Multiple instances of the same tool](../../../docs/guides/credentials.md#multiple-instances-of-the-same-tool) for the full pattern reference.

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["notion"], credentials={"notion": "your-token"})

# Confirm the integration is authed and see the bot's identity
me = kit.execute("notion_get_me", {})
print(me)
```

### MCP Server

```python
kit = ToolKit(["notion"], credentials={"notion": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["notion"], credentials={"notion": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### Bearer Token (Internal Integration)

1. Go to https://www.notion.so/my-integrations
2. **+ New integration** → give it a name + select the workspace
3. Copy the **Internal Integration Token** (starts with `secret_` or `ntn_`)
4. Configure the integration's **capabilities** — by default Notion grants Read content + Update content + Insert content + Read comments + Insert comments. Enable **Read user info** if your workflow needs user details.
5. **Critical**: open each page or database the integration should access → `...` menu → **Connections** → add the integration. **Pages that are NOT shared with the integration return HTTP 404, not 403** — this is the most common onboarding bug. The connector surfaces the fix via the `e.suggestion` field on `NotFoundError`.

[Get credentials →](https://www.notion.so/my-integrations)

## Error Handling

Every typed exception carries a Notion-specific `e.details["notion_code"]` (the structured error code) plus an `e.suggestion` string with an actionable hint:

```python
from toolsconnector.errors import (
    InvalidCredentialsError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ValidationError,
)

try:
    result = kit.execute("notion_update_block", {"block_id": "...", "content": {...}})
except PermissionDeniedError as e:
    # The #1 BYOK gotcha — capability missing OR page not shared
    if e.details.get("notion_code") == "restricted_resource":
        print(f"Fix: {e.suggestion}")
        # → "Integration is missing a required capability OR the target
        #    page/database is not shared with this integration. Fix at
        #    https://www.notion.so/my-integrations or open the page in
        #    Notion → '...' menu → 'Connections' → add your integration."
except NotFoundError as e:
    # Notion 404 is ambiguous — page may not exist, OR may not be shared
    print(f"Fix: {e.suggestion}")
except RateLimitError as e:
    print(f"Rate limited. Retry in {e.retry_after_seconds}s")
except InvalidCredentialsError as e:
    print(f"Auth failed: {e.suggestion}")  # → regenerate at my-integrations
except ValidationError as e:
    # The field-level reason is in `e.details["notion_message"]`
    print(f"Bad request: {e.details.get('notion_message')}")
```

### Error matrix

| Typed exception | `notion_code` | Cause | Fix |
|---|---|---|---|
| `InvalidCredentialsError` | `unauthorized` | Token invalid or revoked | Regenerate at https://www.notion.so/my-integrations |
| `PermissionDeniedError` | `restricted_resource` | Capability not granted OR page not shared with integration | Edit integration capabilities OR add the page to Connections |
| `NotFoundError` | `object_not_found` | Page missing OR not shared (ambiguous — Notion's API doesn't distinguish) | Open page → `...` → Connections → add integration |
| `ValidationError` | `validation_error`, `invalid_json`, `missing_version` | Body shape mismatch | Inspect `e.details["notion_message"]` for the field-level reason |
| `ConflictError` | `conflict_error` | Concurrent edit collision | Fetch latest, retry |
| `RateLimitError` | `rate_limited` | Hit 3 req/s average | Sleep per `Retry-After`, then retry |
| `ServerError` | `service_unavailable`, `internal_server_error`, `database_connection_unavailable`, `gateway_timeout` | Notion-side | Exponential backoff retry |

## Verification Status

**All 24 actions are Tier 1 — Live verified (2026-05-14)** against a real Notion workspace. Every action was called against the actual Notion API, the response was parsed into the expected typed model, and the request shape (method, path, headers, body) was confirmed to match what the API accepts. The full typed-error matrix (`NotFoundError` from 404, `ValidationError` from 400, `InvalidCredentialsError` from 401, `PermissionDeniedError` from 403) was also exercised against real Notion error responses, not just mocks.

| Action | Endpoint | Required capability | Status |
|---|---|---|---|
| `get_me` | `GET /v1/users/me` | (none) | ✅ Live verified |
| `search` | `POST /v1/search` | Read content | ✅ Live verified |
| `get_page` | `GET /v1/pages/{id}` | Read content | ✅ Live verified |
| `create_page` | `POST /v1/pages` | Insert content | ✅ Live verified |
| `update_page` | `PATCH /v1/pages/{id}` | Update content | ✅ Live verified |
| `archive_page` | `PATCH /v1/pages/{id}` (archived=true) | Update content | ✅ Live verified |
| `restore_page` | `PATCH /v1/pages/{id}` (archived=false) | Update content | ✅ Live verified |
| `get_page_property` | `GET /v1/pages/{id}/properties/{prop_id}` | Read content | ✅ Live verified |
| `get_database` | `GET /v1/databases/{id}` | Read content | ✅ Live verified |
| `create_database` | `POST /v1/databases` | Insert content | ✅ Live verified |
| `update_database` | `PATCH /v1/databases/{id}` | Update content | ✅ Live verified |
| `query_database` | `POST /v1/databases/{id}/query` | Read content | ✅ Live verified (empty + filter+sort paths) |
| `get_block` | `GET /v1/blocks/{id}` | Read content | ✅ Live verified |
| `get_block_children` | `GET /v1/blocks/{id}/children` | Read content | ✅ Live verified |
| `append_block_children` | `PATCH /v1/blocks/{id}/children` | Insert content | ✅ Live verified |
| `update_block` | `PATCH /v1/blocks/{id}` | Update content | ✅ Live verified |
| `delete_block` | `DELETE /v1/blocks/{id}` | Update content | ✅ Live verified |
| `list_users` | `GET /v1/users` | Read user info | ✅ Live verified |
| `get_user` | `GET /v1/users/{id}` | Read user info | ✅ Live verified |
| `list_comments` | `GET /v1/comments?block_id=...` | Read comments | ✅ Live verified |
| `add_comment` (top-level) | `POST /v1/comments` | Insert comments | ✅ Live verified |
| `add_comment` (threaded via `discussion_id`) | `POST /v1/comments` | Insert comments | ✅ Live verified |
| `get_comment` | `GET /v1/comments/{id}` | Read comments | ✅ Live verified |
| `update_comment` | `PATCH /v1/comments/{id}` | Insert comments | ✅ Live verified |
| `delete_comment` | `DELETE /v1/comments/{id}` | Insert comments | ✅ Live verified |

### Real error responses verified live

| Trigger | Real response | Typed mapping | Verified |
|---|---|---|---|
| `get_page("00000000-0000-...")` (nonexistent UUID) | 404 `object_not_found` | `NotFoundError` | ✅ |
| `create_page(properties={...invalid...})` | 400 `validation_error` | `ValidationError` | ✅ |
| `aget_me()` with bogus token | 401 `unauthorized` | `InvalidCredentialsError` | ✅ |
| `get_user("00000000-0000-...")` (nonexistent UUID) | 404 `object_not_found` | `NotFoundError` | ✅ |

### Threaded-comment body shape

`add_comment(discussion_id=...)` sends `discussion_id` at the **top level** of the request body — NOT inside a `parent` envelope. This asymmetry vs the page-id form (which uses `{"parent": {"page_id": ...}}`) was caught and corrected during live verification.

## Required integration capabilities

Notion integration tokens carry a capability profile set when the integration was created. Default capabilities cover most workflows; **Read user info** is opt-in.

| Capability | Granted by default | Actions that need it |
|---|---|---|
| Read content | ✅ | `search`, `get_page`, `get_database`, `query_database`, `get_block`, `get_block_children`, `get_page_property` |
| Insert content | ✅ | `create_page`, `create_database`, `append_block_children` |
| Update content | ✅ | `update_page`, `update_database`, `update_block`, `delete_block`, `archive_page`, `restore_page` |
| Read comments | ✅ | `list_comments`, `get_comment` |
| Insert comments | ✅ | `add_comment`, `update_comment`, `delete_comment` |
| Read user info | ❌ | `list_users`, `get_user` |

Missing capabilities raise `PermissionDeniedError` with `e.details["notion_code"] == "restricted_resource"`. Note that `get_me` does NOT require Read user info — it always returns the bot's own identity.

## MCP usage

For AI agents using MCP (Claude Desktop, Cursor, custom clients), use `exclude_dangerous=True` to filter out destructive actions by default:

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["notion"], credentials={"notion": "your-token"})
kit.serve_mcp(exclude_dangerous=True)
```

This hides the 7 destructive actions (`create_page`, `create_database`, `append_block_children`, `delete_block`, `add_comment`, `delete_comment`, `archive_page`) — 17 read-only actions remain exposed to the agent. Re-enable explicitly when you trust the agent for writes.

### Claude Desktop configuration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "notion": {
      "command": "tc",
      "args": ["serve", "mcp", "notion", "--transport", "stdio"],
      "env": {
        "TC_NOTION_CREDENTIALS": "your-notion-integration-token"
      }
    }
  }
}
```

### Pagination caveat for agents

Notion list endpoints return up to 100 items per call. Serialized as JSON, large workspace queries can be >50KB and consume a lot of agent context. Recommend agents call with `limit=20–25` and follow the `cursor` returned in `page_state` rather than asking for "everything in one call":

```python
result = kit.execute("notion_query_database", {"database_id": "...", "limit": 20})
# Subsequent page:
result2 = kit.execute(
    "notion_query_database",
    {"database_id": "...", "limit": 20, "cursor": result["page_state"]["cursor"]},
)
```

See [docs/guides/mcp-server.md](../../../docs/guides/mcp-server.md) for the general MCP server guide.

## Out of Scope (Notion-Version: 2022-06-28 pin)

These capabilities are intentionally not implemented — each is blocked by a Notion-Version bump that would also break this connector's current actions:

| Capability | Why not implemented |
|---|---|
| **File uploads** (`/v1/files/*` 3-step flow) | Requires Notion-Version 2025-09-03+ |
| **Page moves** (`PUT /v1/pages/{id}/move`) | Requires Notion-Version 2025-09-03+ |
| **Markdown read/write** (`/v1/pages/{id}/markdown`) | Requires newer Notion-Version |
| **Data sources** (`/v1/data_sources/*`) | 2025-09-03 splits databases into containers + data sources — breaking change for `parse_database` |
| **Views** (`/v1/views/*`) | Requires Notion-Version 2025-09-03+ |
| **Webhooks** | UI-only subscription model — no programmatic create endpoint exists |
| **OAuth token exchange** (`/v1/oauth/*`) | Explicitly excluded by ToolsConnector's BYOK philosophy — users bring their own token |
| **Hard-delete pages** (`DELETE /v1/pages/{id}`) | `archive_page` is the safer path; the destructive endpoint is intentionally not exposed |
| **List all databases** (`GET /v1/databases`) | Redundant with `search(filter_type="database")` |
| **2026-03-11 schema** (`is_archived` / `in_trash` rename) | Would require a connector major-version bump |

If you need file uploads, page moves, or data sources, open an issue with your use case — these require committing to a Notion-Version bump and a corresponding connector major release.

## Versioned API

This connector pins the `Notion-Version` header to **`2022-06-28`**. Newer Notion API versions introduced breaking changes that would silently break this connector:

- **2025-09-03** — split `/v1/databases` into `/v1/databases` (containers) + `/v1/data_sources` (queryable schema). Would break every `query_database` call and `parse_database`.
- **2026-03-11** — renamed `archived` → `in_trash` across all endpoints. Would break `archive_page`, `restore_page`, and the `archived` field on every parsed `NotionPage` / `NotionBlock` / `NotionDatabase`.

Bumping the pinned version is a deliberate major release — the existing `test_archive_page_sends_archived_field_for_pinned_version` test is the tripwire that catches accidental bumps. See [changes by version](https://developers.notion.com/reference/changes-by-version) for the full migration matrix.

## Reference docs

Cross-checked during doc verification:

- [Search](https://developers.notion.com/reference/post-search)
- [Create a page](https://developers.notion.com/reference/post-page) · [Retrieve a page](https://developers.notion.com/reference/retrieve-a-page) · [Update page](https://developers.notion.com/reference/patch-page)
- [Query a database](https://developers.notion.com/reference/post-database-query)
- [Retrieve block children](https://developers.notion.com/reference/get-block-children)
- [Errors](https://developers.notion.com/reference/errors) · [Status codes](https://developers.notion.com/reference/status-codes)
- [Pagination](https://developers.notion.com/reference/intro#pagination) · [Changes by version](https://developers.notion.com/reference/changes-by-version)

## Actions

<!-- ACTIONS_START -->
<!-- This section is auto-generated from the connector spec. Do not edit manually. -->
<!-- ACTIONS_END -->

## Tips

- **Pages must be shared with the integration.** Open each page or database → `...` menu → **Connections** → add the integration. Unshared pages return HTTP 404, not 403 — this is the most common onboarding bug.
- **Rate limit is 3 requests/second average.** Bursts return `RateLimitError` with `retry_after_seconds` parsed from `Retry-After`. Use pagination + caching to minimize calls.
- **Max page_size is 100.** The connector clamps `limit` values above 100. For large workspaces, follow the `cursor` from `page_state` rather than requesting larger pages.
- **POST endpoints take pagination in the body, GET endpoints take it in the query string.** The connector handles both — but if you read raw responses, that's why the wire format differs.
- **`discussion_id` is sticky.** Once a comment is added to a thread, every reply must reference the same `discussion_id`. The first comment returns it; pass it back into `add_comment(discussion_id=...)` for replies.
- **Destructive actions** (`create_page`, `create_database`, `append_block_children`, `delete_block`, `add_comment`, `delete_comment`, `archive_page`) are flagged `dangerous=True`. Use `kit.serve_mcp(exclude_dangerous=True)` to hide them from agents by default.

## Related Connectors

- [Confluence](../confluence/) — Team wiki and documentation
- [Google Docs](../gdocs/) — Word-style documents
- [Google Drive](../gdrive/) — File storage

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
