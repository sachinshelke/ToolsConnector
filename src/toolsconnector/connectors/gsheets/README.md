# Google Sheets

> Full CRUD on spreadsheets + cell values + sheet tabs + structural mutations

| | |
|---|---|
| **Company** | Google LLC |
| **Category** | Productivity |
| **Protocol** | REST |
| **API Version** | v4 |
| **Website** | [sheets.google.com](https://sheets.google.com) |
| **API Docs** | [developers.google.com/sheets/api](https://developers.google.com/sheets/api/reference/rest) |
| **Auth** | OAuth 2.0 bearer token (`ya29.…`) |
| **Rate Limit** | 300 write requests/minute · 3,000 read requests/minute (per project) — connector throttle: 300 req/min |
| **Pricing** | Free with Google account |

---

## Overview

16 actions covering: spreadsheet metadata + creation, cell-value CRUD with batch read/write/clear/append, sheet (tab) management (add/delete/copy/rename), structural mutations (merge/auto-resize/etc) via the generic `batch_update_spreadsheet`. Pairs naturally with the Drive connector for file management (move/share/delete — gsheets handles content, gdrive handles containers).

## Use Cases

- Automated data exports (analytics reports, CRM sync)
- Spreadsheet-based dashboards
- Live data pipelines (write to a sheet shared with stakeholders)
- Bulk cell formatting + structural changes
- Configuration-as-spreadsheet workflows
- Cross-tool data sync (Slack → Sheet, Sheet → Notion, etc.)

## Installation

```bash
pip install "toolsconnector[gsheets]"
```

## Credentials

```python
# Programmatic
kit = ToolKit(["gsheets"], credentials={"gsheets": "ya29.your_access_token"})

# Environment variable
# export TC_GSHEETS_CREDENTIALS=ya29.…  # preferred
# export TC_GSHEETS_API_KEY=ya29.…
# export TC_GSHEETS_TOKEN=ya29.…
kit = ToolKit(["gsheets"])
```

Access token must carry at least `https://www.googleapis.com/auth/spreadsheets` scope. See [Credentials Guide](../../../docs/guides/credentials.md) for refresh patterns + multi-account.

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["gsheets"], credentials={"gsheets": "ya29.your_token"})

# Create a spreadsheet with multiple tabs
ss = kit.execute("gsheets_create_spreadsheet", {
    "title": "Q1 Report",
    "sheet_names": ["Revenue", "Expenses", "Summary"],
})
print(ss["id"], ss["url"])

# Write values to a range
kit.execute("gsheets_update_values", {
    "spreadsheet_id": ss["id"],
    "range": "Revenue!A1:C2",
    "values": [["Region", "Q1", "Q2"], ["North", 12500, 14200]],
})

# Read them back
vals = kit.execute("gsheets_get_values", {
    "spreadsheet_id": ss["id"],
    "range": "Revenue!A1:C2",
})
print(vals["values"])
```

### MCP Server

```python
kit = ToolKit(["gsheets"], credentials={"gsheets": "ya29.…"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["gsheets"], credentials={"gsheets": "ya29.…"})
tools = kit.to_openai_tools()
```

## Authentication

### Authenticate with ToolsConnector

Skip manual token handling — ToolsConnector runs the OAuth flow and returns tokens,
reading this connector's declared scopes automatically:

```python
import asyncio
from toolsconnector.connectors.gsheets import GoogleSheets
from toolsconnector.runtime.auth import login_for

# Desktop / CLI: opens the browser, catches the redirect on 127.0.0.1, returns tokens.
creds = asyncio.run(login_for(GoogleSheets, client_id="...apps.googleusercontent.com"))
# creds.access_token / creds.refresh_token
```

**Different permissions.** Request a subset now, or add more later without losing the
existing grant (Google incremental auth):

```python
from toolsconnector.connectors.gdrive import GoogleDrive
from toolsconnector.runtime.auth import scopes_for

# only what you need now
creds = asyncio.run(login_for(GoogleSheets, client_id="...",
    scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]))

# add GoogleDrive later, keeping the existing grant
creds = asyncio.run(login_for(GoogleSheets, client_id="...",
    scopes=scopes_for(GoogleSheets, GoogleDrive), incremental=True))
```

**Web apps:** use `begin_for(GoogleSheets, client_id=..., redirect_uri=...)` then
`complete(pending, code=..., state=...)` from your own callback route.

Same paths as Google Docs — Google OAuth 2.0 access tokens. Easiest options:

### Path 1 — OAuth 2.0 Playground (fastest, no install)

1. https://developers.google.com/oauthplayground
2. Step 1: paste `https://www.googleapis.com/auth/spreadsheets` into "Input your own scopes" → **Authorize APIs**
3. Sign in + consent
4. Step 2: **Exchange authorization code for tokens** → copy `access_token`

### Path 2 — gcloud CLI

```bash
gcloud auth application-default login --scopes=https://www.googleapis.com/auth/spreadsheets
gcloud auth application-default print-access-token
```

### Path 3 — Your own OAuth flow or service account

Production deployments should run their own OAuth 2.0 authorization-code flow with `client_id` + `client_secret` from Google Cloud Console, or use a service-account JSON key. The connector accepts any access token format (the `ya29.…` prefix).

## Required scope

| Action group | Minimum scope |
|---|---|
| Reads (`get_spreadsheet`, `get_sheet_metadata`, `get_values`, `batch_get_values`) | `https://www.googleapis.com/auth/spreadsheets.readonly` |
| All 12 mutations | `https://www.googleapis.com/auth/spreadsheets` |

`spreadsheets` (read+write) covers all 16 actions. `drive.file` is recommended additionally if you want to delete spreadsheets you created — the Sheets API itself has no delete endpoint; use the Drive API's `DELETE /drive/v3/files/{id}`.

## Error Handling

```python
from toolsconnector.errors import (
    InvalidCredentialsError, PermissionDeniedError, NotFoundError,
    RateLimitError, ValidationError, ServerError,
    ConnectionError, TimeoutError, TransportError,
)

try:
    vals = kit.execute("gsheets_get_values", {"spreadsheet_id": "…", "range": "A1:B2"})
except InvalidCredentialsError:
    # Access token expired (1-hour lifetime) or revoked. Refresh.
    pass
except RateLimitError as e:
    print(f"Retry after {e.retry_after_seconds}s")
```

| Typed exception | HTTP | When |
|---|---|---|
| `InvalidCredentialsError` | 401 | Access token expired or revoked |
| `PermissionDeniedError` | 403 | Token lacks `spreadsheets` scope OR sheet not shared with the OAuth user |
| `NotFoundError` | 404 | spreadsheet_id doesn't exist OR you don't have read access |
| `ValidationError` | 400/422 | Bad range, malformed values, invalid request shape |
| `RateLimitError` | 429 | Per-project quota exhausted |
| `ServerError` | 5xx | Google-side outage |
| `ConnectionError` / `TimeoutError` / `TransportError` | n/a | Network-layer failures (typed wrappers) |

## Path-traversal + range encoding

Spreadsheet IDs and ranges (e.g. `Sheet1!A1:B2`) are percent-encoded via the `_p()` helper before f-string URL interpolation. Adversarial `spreadsheet_id="../admin"` becomes `..%2Fadmin`, preserving the `/spreadsheets/` prefix. The `!` and `:` in range strings get encoded as `%21` and `%3A`; Google's API accepts both literal and percent-encoded forms. Pinned by `test_spreadsheet_id_with_slash_percent_encoded` and `test_range_with_unicode_passes_through`.

## Verification Status

All 16 actions are **Live verified** — exercised end-to-end against `sheets.googleapis.com` with a real OAuth 2.0 access token on 2026-05-28. The verification covered the full lifecycle on a throwaway spreadsheet:

| Phase | Actions exercised |
|---|---|
| Setup | `create_spreadsheet` (multi-tab) |
| Metadata | `get_spreadsheet`, `get_sheet_metadata` |
| Values CRUD | `update_values`, `get_values` (unicode round-trip: 你好 🚀), `batch_get_values`, `append_values`, `batch_update_values`, `clear_values` |
| Tab management | `add_sheet`, `rename_sheet`, `merge_cells`, `auto_resize_columns`, `copy_sheet` |
| Generic structural | `batch_update_spreadsheet` (updateSpreadsheetProperties) |
| Cleanup | `delete_sheet` (per added tab) + Drive API `DELETE /files/{id}` (whole spreadsheet) |

**36 respx unit tests** pin the request/response shapes across 5 rounds (happy path × 16 actions, defensive parsing + URL-path guards, error matrix, transport errors, MCP exposure, OpenAI schema sweep, dangerous-flag audit, sync wrappers, concurrency).

**MCP end-to-end verified**: subprocess `tc serve mcp gsheets --transport stdio` over JSON-RPC, real `create_spreadsheet` + `update_values` + `get_values` dispatched via MCP tool calls, MCP-created spreadsheet cleanly deleted via Drive API.

| Action | REST Endpoint | Status |
|---|---|---|
| `get_spreadsheet` | `GET /v4/spreadsheets/{id}` | ✅ Live verified |
| `create_spreadsheet` | `POST /v4/spreadsheets` | ✅ Live verified |
| `get_sheet_metadata` | `GET /v4/spreadsheets/{id}?fields=sheets.properties` | ✅ Live verified |
| `get_values` | `GET /v4/spreadsheets/{id}/values/{range}` | ✅ Live verified |
| `batch_get_values` | `GET /v4/spreadsheets/{id}/values:batchGet` | ✅ Live verified |
| `update_values` | `PUT /v4/spreadsheets/{id}/values/{range}` | ✅ Live verified |
| `append_values` | `POST /v4/spreadsheets/{id}/values/{range}:append` | ✅ Live verified |
| `clear_values` | `POST /v4/spreadsheets/{id}/values/{range}:clear` | ✅ Live verified |
| `batch_update_values` | `POST /v4/spreadsheets/{id}/values:batchUpdate` | ✅ Live verified |
| `add_sheet` | `POST /v4/spreadsheets/{id}:batchUpdate` (addSheet) | ✅ Live verified |
| `delete_sheet` | `POST /v4/spreadsheets/{id}:batchUpdate` (deleteSheet) | ✅ Live verified |
| `copy_sheet` | `POST /v4/spreadsheets/{id}/sheets/{sheetId}:copyTo` | ✅ Live verified |
| `batch_update_spreadsheet` | `POST /v4/spreadsheets/{id}:batchUpdate` | ✅ Live verified |
| `rename_sheet` | wrapper → batchUpdate (updateSheetProperties) | ✅ Live verified |
| `merge_cells` | wrapper → batchUpdate (mergeCells) | ✅ Live verified |
| `auto_resize_columns` | wrapper → batchUpdate (autoResizeDimensions) | ✅ Live verified |

## Actions

<!-- ACTIONS_START -->
<!-- This section is auto-generated from the connector spec. Do not edit manually. -->
<!-- ACTIONS_END -->

## Tips

- **First call**: `create_spreadsheet` with a unique title is the cheapest sanity check that the token has the `spreadsheets` scope.
- **Spreadsheet deletion**: Sheets API has no `DELETE /spreadsheets/{id}`. Use the Drive API: `DELETE /drive/v3/files/{id}` (requires `drive.file` or `drive` scope).
- **A1 notation for ranges**: `"Sheet1!A1:C10"`. Sheet name + `!` + cell range. Quote sheet names with spaces: `"'My Sheet'!A1:C10"`.
- **`USER_ENTERED` vs `RAW`**: `USER_ENTERED` parses input as if typed in the UI (formulas, dates, numbers auto-detected). `RAW` writes literal strings. Default is `USER_ENTERED`.
- **`batch_get_values` is cheaper than N separate `get_values`**: one HTTP round-trip + one quota-unit cost vs N. Same for `batch_update_values`.
- **`sheet_id` vs sheet title**: `add_sheet` returns the numeric `sheet_id`; structural ops like `rename_sheet`, `merge_cells`, `delete_sheet` take that numeric id, not the title.
- **`auto_resize_columns` default range**: `start_column=0`, `end_column=26` → columns A-Z. Pass explicit values for wider sheets.
- **Dangerous actions**: 10 of 16 mutate state. Use `kit = ToolKit(["gsheets"], exclude_dangerous=True)` for agent-safe read-only mode (leaves 6 read tools).

## Related Connectors

- [Google Docs](../gdocs/) — document CRUD via Docs API
- [Google Drive](../gdrive/) — file management + sharing (paired with gsheets/gdocs for delete)
- [Airtable](../airtable/) — alternative table/database platform

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
