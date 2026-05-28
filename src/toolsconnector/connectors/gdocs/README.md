# Google Docs

> Create + edit + extract text from Google Docs programmatically

| | |
|---|---|
| **Company** | Google LLC |
| **Category** | Productivity |
| **Protocol** | REST |
| **API Version** | v1 |
| **Website** | [docs.google.com](https://docs.google.com) |
| **API Docs** | [developers.google.com/docs/api](https://developers.google.com/docs/api/reference/rest) |
| **Auth** | OAuth 2.0 bearer token (`ya29.…`) |
| **Rate Limit** | 300 write requests/minute · 3,000 read requests/minute (per project) — connector throttle: 300 req/min |
| **Pricing** | Free with a Google account |

---

## Overview

Five focused actions covering document CRUD + content read/write via the Google Docs REST API v1 at `docs.googleapis.com/v1`. Pairs naturally with the Drive connector for file management (move/share/delete) — gdocs handles content, gdrive handles container operations.

## Use Cases

- Automated document generation (contracts, reports, invoices)
- Template-based content workflows
- Plain-text extraction from existing docs
- Content sync from external systems
- Agent-driven document editing

## Installation

```bash
pip install "toolsconnector[gdocs]"
```

## Credentials

Two equivalent ways to provide the token — same primitives every ToolsConnector connector uses:

```python
# Programmatic
kit = ToolKit(["gdocs"], credentials={"gdocs": "ya29.your_access_token"})

# Environment variable (any one of these; first match wins)
# export TC_GDOCS_CREDENTIALS=ya29.…  # preferred
# export TC_GDOCS_API_KEY=ya29.…
# export TC_GDOCS_TOKEN=ya29.…
kit = ToolKit(["gdocs"])  # no credentials arg — resolved from env
```

The token must be a Google OAuth 2.0 access token with at least the `https://www.googleapis.com/auth/documents` scope. Access tokens are short-lived (~1 hour) — see the [Credentials Guide](../../../docs/guides/credentials.md) for refresh patterns + multi-account.

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["gdocs"], credentials={"gdocs": "ya29.your_token"})

# Create a new document
doc = kit.execute("gdocs_create_document", {"title": "Q1 Report"})
print(doc)  # {"id": "1abc…", "title": "Q1 Report", ...}

# Insert text at the beginning
kit.execute("gdocs_insert_text", {
    "document_id": doc["id"],
    "text": "# Quarterly Highlights\n\n",
})

# Read it back as plain text
text = kit.execute("gdocs_get_document_text", {"document_id": doc["id"]})
print(text)
```

### MCP Server

```python
kit = ToolKit(["gdocs"], credentials={"gdocs": "ya29.…"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["gdocs"], credentials={"gdocs": "ya29.…"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

The connector accepts any Google OAuth 2.0 access token format (the `ya29.…` prefix). Several paths to obtain one:

### Path 1 — OAuth 2.0 Playground (fastest, no install)

1. Go to https://developers.google.com/oauthplayground
2. Step 1: scroll to the bottom, paste the scope `https://www.googleapis.com/auth/documents` into the "Input your own scopes" box, click **Authorize APIs**
3. Sign in with your Google account → grant consent
4. Step 2: click **Exchange authorization code for tokens**
5. Copy the `access_token` value (starts with `ya29.…`) — valid ~1 hour

### Path 2 — gcloud CLI

```bash
brew install --cask google-cloud-sdk  # or platform equivalent
gcloud auth application-default login --scopes=https://www.googleapis.com/auth/documents
gcloud auth application-default print-access-token
```

### Path 3 — Your own OAuth flow

For production deployments, run your own OAuth 2.0 authorization-code flow with `client_id` + `client_secret` from Google Cloud Console. Refresh tokens via `https://oauth2.googleapis.com/token`. See [docs/guides/credentials.md](../../../docs/guides/credentials.md) for patterns.

### Path 4 — Service account

For server-to-server (no end-user OAuth), use a service-account JSON key with domain-wide delegation. The connector accepts the resulting access token from the JWT-bearer flow. **Note**: service accounts can only access documents explicitly shared with them, or any document if domain-wide delegation is granted by a Workspace admin.

[Get credentials →](https://developers.google.com/docs/api/quickstart)

## Required scope

| Action | Minimum scope |
|---|---|
| `get_document`, `get_document_text` | `https://www.googleapis.com/auth/documents.readonly` |
| `create_document`, `batch_update`, `insert_text` | `https://www.googleapis.com/auth/documents` |

`documents` (read+write) covers all five actions. `drive.file` is recommended additionally if you want to delete docs you created (the Docs API itself has no delete; use `DELETE /drive/v3/files/{id}`).

## Error Handling

```python
from toolsconnector.errors import (
    InvalidCredentialsError,
    PermissionDeniedError,
    NotFoundError,
    RateLimitError,
    ValidationError,
    ServerError,
    ConnectionError,
    TimeoutError,
    TransportError,
)

try:
    text = kit.execute("gdocs_get_document_text", {"document_id": "..."})
except InvalidCredentialsError as e:
    print(f"Token expired or invalid (401): {e.suggestion}")
except PermissionDeniedError as e:
    print(f"Token lacks the documents scope (403)")
except NotFoundError:
    print("Document doesn't exist or isn't shared with this token")
except RateLimitError as e:
    print(f"Rate limited. Retry after {e.retry_after_seconds}s")
```

| Typed exception | HTTP status | When it fires |
|---|---|---|
| `InvalidCredentialsError` | 401 | Access token expired (1-hour lifetime) or revoked. Refresh via your OAuth flow. |
| `PermissionDeniedError` | 403 | Token doesn't carry the required `documents` scope, OR the document isn't shared with the OAuth user. |
| `NotFoundError` | 404 | Document ID doesn't exist OR you don't have read access (Google returns 404 for both — same ambiguity as Drive). |
| `ValidationError` | 400 / 422 | Bad request shape (e.g. malformed `requests` array in `batch_update`). |
| `RateLimitError` | 429 | Per-project quota exhausted. `Retry-After` header populated. |
| `ServerError` | 5xx | Google-side outage. Retry with backoff. |
| `ConnectionError` / `TimeoutError` / `TransportError` | n/a | Network-layer failures — typed wrappers of `httpx.ConnectError` / `TimeoutException` / `TransportError`. |

### Path-traversal protection

URL path segments (e.g. `{document_id}`) are percent-encoded via the `_p()` helper before f-string interpolation. Adversarial `document_id="../admin"` becomes `..%2Fadmin`, preserving the `/documents/` prefix. Pinned by `test_document_id_with_slash_percent_encoded`.

### Token redaction

Google OAuth 2.0 access tokens (`ya29.…`) and Google API keys (`AIza…`) are redacted from error-body previews via the shared `_CREDENTIAL_PATTERNS` regex. A misbehaving upstream that echoes your token back in an error body will never see it land in `details["body_preview"]`. Same redaction also enforced at CI secret-scan + pre-commit hook level.

## Verification Status

All 5 actions are **Live verified** — exercised end-to-end against `docs.googleapis.com` with a real OAuth 2.0 access token on 2026-05-28. The verification covered:

- Document creation + metadata round-trip
- Plain-text extraction (empty body → `"\n"`, populated body, unicode + emoji round-trip)
- Single-request `insert_text` via the convenience wrapper
- Multi-request `batch_update`
- Real 404 → typed `NotFoundError` against the live API

26 respx unit tests pin the request/response shapes across 5 rounds: happy path, defensive parsing (table walk, empty body, unknown fields), URL-path injection guard, error matrix (401/403/404/429/500), transport errors, MCP exposure, OpenAI schema sweep, dangerous-flag audit, sync wrappers, lifecycle, concurrency.

**MCP end-to-end verified**: subprocess `tc serve mcp gdocs --transport stdio` over JSON-RPC, real document created + read via MCP tool dispatch, clean shutdown.

| Action | REST Endpoint | Status |
|---|---|---|
| `get_document` | `GET /v1/documents/{id}` | ✅ Live verified |
| `create_document` | `POST /v1/documents` | ✅ Live verified |
| `batch_update` | `POST /v1/documents/{id}:batchUpdate` | ✅ Live verified |
| `insert_text` | `POST /v1/documents/{id}:batchUpdate` (insertText request) | ✅ Live verified |
| `get_document_text` | `GET /v1/documents/{id}` → walk body content | ✅ Live verified |

## Actions

<!-- ACTIONS_START -->
<!-- This section is auto-generated from the connector spec. Do not edit manually. -->
<!-- ACTIONS_END -->

## Tips

- **First call**: `create_document` with auto-generated title is the cheapest sanity check that the token has the `documents` scope.
- **Doc deletion**: Google Docs API has no `DELETE /documents/{id}`. Use the Drive API instead: `DELETE /drive/v3/files/{id}` (requires `drive.file` scope at minimum).
- **Body indexes**: Google Docs uses 1-based character indexes. Index `1` is the start of the body (after the implicit section break). Index `0` is invalid.
- **`get_document` vs `get_document_text`**: the former returns metadata only (one API call, fast). The latter also fetches + walks the body to extract plain text (one API call, slower parse). Calling both means **two API calls** to the same document — fetch once and parse twice locally if you need both.
- **Tables are walked**: `get_document_text` extracts text from inside table cells, not just top-level paragraphs.
- **Custom verb suffix**: `:batchUpdate` is a Google REST custom-verb idiom, not a sub-resource. The connector's `_p()` percent-encoding wraps only `{document_id}`, leaving the literal `:batchUpdate` suffix intact.
- **Dangerous actions**: `create_document`, `batch_update`, `insert_text` mutate state. Use `kit = ToolKit(["gdocs"], exclude_dangerous=True)` for agent-safe read-only mode.

## Related Connectors

- [Google Drive](../gdrive/) — file management + sharing
- [Google Sheets](../gsheets/) — spreadsheet CRUD
- [Notion](../notion/) — alternative document platform

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
