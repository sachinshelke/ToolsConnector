# Google Tasks

> Manage task lists and to-do items

| | |
|---|---|
| **Company** | Google |
| **Category** | Productivity |
| **Protocol** | REST |
| **Website** | [tasks.google.com](https://tasks.google.com) |
| **API Docs** | [developers.google.com](https://developers.google.com/tasks/reference/rest) |
| **Auth** | OAuth 2.0 Bearer (BYOK) |
| **Rate Limit** | 50,000 requests/day (default project quota) |
| **Pricing** | Free with Google account |
| **Verification** | ✅ Tier 1 — Live verified (13/13 actions, 2026-05-29) |

---

## Overview

The Google Tasks API provides access to task lists and individual tasks. Create, update, complete, and organize tasks programmatically. Tasks support parent/child nesting and ordered positions within a list, and integrate naturally with Google Calendar and Gmail for productivity workflows.

## Use Cases

- To-do list sync across personal devices
- Project tracking with parent/child task hierarchies
- Workflow triggers on task completion (poll + react)
- Doc-driven task creation (parse action items from a Google Doc)
- Calendar-integrated daily-planning pipelines

## Installation

```bash
pip install "toolsconnector[gtasks]"
```

Set your credentials:

```bash
export TC_GTASKS_CREDENTIALS=ya29.your-access-token
```

## Quick Start

```python
import json
from toolsconnector.serve import ToolKit

kit = ToolKit(["gtasks"], credentials={"gtasks": "ya29.your-access-token"})

# Find the default task list, then add a task to it
lists = json.loads(kit.execute("gtasks_list_task_lists", {}))
default_list = lists["items"][0]["id"]
kit.execute("gtasks_create_task", {"task_list_id": default_list, "title": "Ship 0.3.11"})
```

### MCP Server

```python
kit = ToolKit(["gtasks"], credentials={"gtasks": "ya29.your-access-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

Or from the CLI: `tc serve mcp gtasks --transport stdio` (exposes 13 `gtasks_*` tools).

### OpenAI Function Calling

```python
kit = ToolKit(["gtasks"], credentials={"gtasks": "ya29.your-access-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

Same paths as the other Google Workspace connectors:

### Path 1 — OAuth Playground (fastest)

1. https://developers.google.com/oauthplayground
2. Step 1: paste `https://www.googleapis.com/auth/tasks` → **Authorize APIs**
3. Sign in + consent → Step 2: **Exchange authorization code for tokens** → copy `access_token`

### Path 2 — gcloud CLI

```bash
gcloud auth application-default login --scopes=https://www.googleapis.com/auth/tasks
gcloud auth application-default print-access-token
```

ToolsConnector is **BYOK** — supply your own OAuth access token (`ya29.*`) or a service-account access token obtained externally. The library never runs the OAuth flow or stores tokens.

## Required scope

| Action group | Minimum scope |
|---|---|
| All 5 reads (`list_task_lists`, `get_task_list`, `list_tasks`, `get_task`, `move_task`) | `https://www.googleapis.com/auth/tasks.readonly` (note: `move_task` reorders and needs write) |
| All 8 mutating actions | `https://www.googleapis.com/auth/tasks` |

## Error Handling

| Typed exception | HTTP | When |
|---|---|---|
| `InvalidCredentialsError` | 401 | Access token expired/revoked |
| `PermissionDeniedError` | 403 | Token lacks the `tasks` scope |
| `NotFoundError` | 404 | `task_list_id` / `task_id` doesn't exist |
| `ValidationError` | 400 | Malformed body — e.g. sending PUT-style full-resource where PATCH partial is required |
| `RateLimitError` | 429 | Per-project daily quota exhausted |
| `ServerError` | 5xx | Google-side outage |
| `ConnectionError` / `TimeoutError` / `TransportError` | n/a | Network-layer failures (typed wrappers) |

```python
from toolsconnector.errors import RateLimitError, InvalidCredentialsError

try:
    result = kit.execute("gtasks_list_tasks", {"task_list_id": "..."})
except RateLimitError as e:
    print(f"Rate limited. Retry in {e.retry_after_seconds}s")
except InvalidCredentialsError as e:
    print(f"Auth failed: {e.suggestion}")
```

### Path-traversal protection

`task_list_id` and `task_id` are percent-encoded via the `_p()` helper before URL interpolation, so a hostile or malformed ID can't escape the intended path prefix.

## Verification Status

All 13 actions **Live verified** against `tasks.googleapis.com/tasks/v1` on **2026-05-29** with a real OAuth 2.0 access token (`tasks` scope).

End-to-end live run on a throwaway task list: `list_task_lists` (baseline — left the user's existing lists untouched) → `create_task_list` (throwaway) → `get_task_list` round-trip → `update_task_list` rename → `list_tasks` → `create_task` ×2 (with notes + due date) → `get_task` round-trip → `update_task` (extend due) → `move_task` (reparent a sub-task) → `complete_task` → `clear_completed` → `delete_task` → `delete_task_list` (cleanup). Throwaway list deleted; **zero leftover artifacts** on the account. MCP stdio dispatch also verified end-to-end (initialize + tools/list with 13 tools + a real `tools/call list_task_lists`).

**Live testing surfaced + fixed 1 production bug** respx alone had silently accepted: `update_task_list` was using HTTP `PUT` with a title-only body, but Google's `tasklists.update` endpoint requires a **complete** TaskList resource and rejects the partial body with HTTP 400. Fixed by switching to HTTP `PATCH` (`tasklists.patch`), which accepts partial updates — matching the connector's rename-only intent. Pinned by `test_update_task_list_uses_patch_not_put`.

**30 respx unit tests** pin request/response shapes across 5 rounds (happy path × 13 actions, defensive parsing, URL-path injection guards, error matrix, transport errors, MCP exposure, OpenAI schema, dangerous-flag audit, sync wrappers).

| Action | Endpoint | Status |
|---|---|---|
| `list_task_lists` | `GET /users/@me/lists` | ✅ Live verified |
| `get_task_list` | `GET /users/@me/lists/{id}` | ✅ Live verified |
| `create_task_list` | `POST /users/@me/lists` | ✅ Live verified |
| `update_task_list` | `PATCH /users/@me/lists/{id}` | ✅ Live verified (PATCH, not PUT) |
| `delete_task_list` | `DELETE /users/@me/lists/{id}` | ✅ Live verified |
| `list_tasks` | `GET /lists/{id}/tasks` | ✅ Live verified |
| `get_task` | `GET /lists/{listId}/tasks/{taskId}` | ✅ Live verified |
| `create_task` | `POST /lists/{id}/tasks` | ✅ Live verified |
| `update_task` | `PATCH /lists/{listId}/tasks/{taskId}` | ✅ Live verified |
| `complete_task` | `PATCH /lists/{listId}/tasks/{taskId}` (status=completed) | ✅ Live verified |
| `move_task` | `POST /lists/{listId}/tasks/{taskId}/move` | ✅ Live verified |
| `delete_task` | `DELETE /lists/{listId}/tasks/{taskId}` | ✅ Live verified |
| `clear_completed` | `POST /lists/{id}/clear` | ✅ Live verified |

## Actions

<!-- ACTIONS_START -->
<!-- This section is auto-generated from the connector spec. Do not edit manually. -->
<!-- ACTIONS_END -->

## Tips

- **PATCH, not PUT, for updates** — `update_task_list` and `update_task` use partial-update PATCH semantics. Only the fields you pass are changed; everything else is preserved. (Google rejects PUT with a partial body — see Verification Status.)
- **Task hierarchy** — `move_task(parent=...)` reparents a task under another; `move_task(previous=...)` reorders within the same level. `move_task` is **not** dangerous-flagged (it relocates, doesn't destroy).
- **`clear_completed` is bulk + irreversible** — it permanently removes every completed task in the list. There's no undo.
- **Dangerous actions**: 8 of 13 (`create_task_list`, `update_task_list`, `delete_task_list`, `create_task`, `update_task`, `complete_task`, `delete_task`, `clear_completed`). Use `ToolKit(["gtasks"], exclude_dangerous=True)` for agent-safe read-only mode (leaves the 5 read/move actions).
- **Due dates are RFC 3339** — pass `due="2026-06-01T00:00:00.000Z"`. Google only stores the date portion for tasks (time is ignored by the Tasks UI).
- **One default list per user** — every account starts with one task list you can't delete; create additional lists with `create_task_list`.

## Related Connectors

- [Google Calendar](../gcalendar/) — events + scheduling
- [Google Docs](../gdocs/) — document CRUD
- [Google Sheets](../gsheets/) — spreadsheet CRUD
- [Google Drive](../gdrive/) — file management

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
