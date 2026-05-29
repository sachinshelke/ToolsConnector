# Google Drive

> Files + folders + permissions + comments + revisions via the Drive API v3

| | |
|---|---|
| **Company** | Google LLC |
| **Category** | Storage |
| **Protocol** | REST |
| **API Version** | v3 |
| **Website** | [drive.google.com](https://drive.google.com) |
| **API Docs** | [developers.google.com/drive/api](https://developers.google.com/drive/api/v3/reference) |
| **Auth** | OAuth 2.0 bearer token (`ya29.…`) |
| **Rate Limit** | 1,000 req/100sec per user (read), 100 write req/sec per user — connector throttle: 600/min |
| **Pricing** | Free with Google account (15 GB), Google One from $1.99/month |

---

## Overview

22 actions covering: file CRUD (list / get / upload / download / create_folder / delete / search / update_file / copy / move / export), sharing + permissions (share / list_permissions / get_permission / delete_permission), comments (list / create / delete), revision history (list / get), storage quota, and empty_trash. Pairs naturally with gdocs / gsheets / gcalendar for cleanup (those connectors don't expose file delete; gdrive does).

## Use Cases

- File backup + archival pipelines
- Permission management for shared resources
- Document version history retrieval
- Public-link sharing for assets
- Storage quota monitoring
- Cross-tool sync (Slack files → Drive, Drive → S3, etc.)

## Installation

```bash
pip install "toolsconnector[gdrive]"
```

## Credentials

```python
kit = ToolKit(["gdrive"], credentials={"gdrive": "ya29.your_token"})
# Or via env: TC_GDRIVE_CREDENTIALS=ya29.… / TC_GDRIVE_TOKEN=ya29.…
```

Required minimum scope: `https://www.googleapis.com/auth/drive` for full access OR `https://www.googleapis.com/auth/drive.file` for files-this-app-created-only (narrower, safer for BYOK).

## Quick Start

```python
import base64
from toolsconnector.serve import ToolKit

kit = ToolKit(["gdrive"], credentials={"gdrive": "ya29.…"})

# Create a folder
folder = kit.execute("gdrive_create_folder", {"name": "Reports 2026"})

# Upload a file (content must be base64-encoded)
content = base64.b64encode(b"Hello, Drive!").decode()
uploaded = kit.execute("gdrive_upload_file", {
    "name": "hello.txt",
    "content_base64": content,
    "mime_type": "text/plain",
    "parent_folder_id": folder["id"],
})

# Download it back
dl = kit.execute("gdrive_download_file", {"file_id": uploaded["id"]})
print(base64.b64decode(dl["content_base64"]).decode())

# Share publicly (anyone with link can read)
kit.execute("gdrive_share_file", {
    "file_id": uploaded["id"],
    "email": "",  # ignored for type=anyone
    "role": "reader",
    "type": "anyone",
    "send_notification": False,
})
```

### MCP Server

```python
kit.serve_mcp()
```

## Authentication

Same paths as the other Google Workspace connectors. Easiest via OAuth Playground:

1. https://developers.google.com/oauthplayground
2. Step 1: paste `https://www.googleapis.com/auth/drive` (or `drive.file` for the narrower scope) → **Authorize APIs**
3. Step 2: **Exchange authorization code for tokens** → copy `access_token`

## Required scope

| Action group | Minimum scope |
|---|---|
| All reads (list_files / get_file / download_file / search_files / list_permissions / get_permission / list_comments / list_revisions / get_revision / export_file / get_storage_quota) | `drive.readonly` (note: get_storage_quota actually needs `drive` even though it reads) |
| All mutations + sharing | `drive` (full) or `drive.file` (limited to files this app created) |

## Error Handling

| Typed exception | HTTP | When |
|---|---|---|
| `InvalidCredentialsError` | 401 | Access token expired/revoked |
| `PermissionDeniedError` | 403 | Token lacks the right Drive scope |
| `NotFoundError` | 404 | file_id / permission_id / revision_id missing |
| `ValidationError` | 400/422 | Bad multipart body, conflicting permission shape, etc. |
| `RateLimitError` | 429 | Per-user / per-project quota exhausted |
| `ServerError` | 5xx | Google-side outage |
| `ConnectionError` / `TimeoutError` / `TransportError` | n/a | Network failures (typed wrappers) |

### Path-traversal protection

File IDs, comment IDs, revision IDs, and permission IDs are percent-encoded via `_p()` before f-string URL interpolation. Pinned by `test_file_id_with_slash_percent_encoded`.

## Verification Status

All 22 actions verified — **20 Live verified** + **2 Probe-skipped** (would touch user's actual trash or require a Google-Workspace native file to export):

| Live verified (20) | Probe-skipped (2) |
|---|---|
| `get_storage_quota`, `list_files`, `create_folder`, `upload_file` (binary + base64 round-trip + unicode in metadata), `get_file`, `download_file` (unicode round-trip `你好 🚀`), `search_files`, `share_file` (type=anyone public link), `list_permissions`, `get_permission`, `delete_permission`, `update_file` (rename + description), `copy_file`, `move_file` (between folders), `create_comment` (unicode), `list_comments`, `delete_comment`, `list_revisions` (Drive auto-creates revisions on writes), `get_revision`, `delete_file` | `export_file` (requires a Google Workspace file like a Doc/Sheet — our uploaded text file can't be exported), `empty_trash` (would permanently erase the user's real trashed files — destructive cleanup risk) |

End-to-end live run on 2026-05-28 against `www.googleapis.com/drive/v3` with a real OAuth 2.0 token: created throwaway folder → uploaded text file with unicode metadata → got/downloaded with unicode round-trip → searched, sharing CRUD (public-link), file mutations (rename/copy/move), comment CRUD (unicode), revision read-back → deleted the file, then the folder (Drive cascades to all contents). Zero leftover artifacts.

**38 respx unit tests** pin request/response shapes across 5 rounds.

### 🐛 Two real production bugs surfaced and fixed during live verification

**Bug 1: `upload_file` always failed with HTTP 400** — The multipart body declared `Content-Transfer-Encoding: base64` but actually sent the raw decoded bytes. Google's upload endpoint took the header literally — expecting the part to BE base64-encoded text and then decode it again — which failed. Fixed by removing the spurious encoding header; raw bytes now match the `Content-Type: <mime>` declaration. **Every prior upload via this connector failed.**

**Bug 2: `share_file` failed with HTTP 400 for `type="anyone"` and `type="domain"`** — The connector unconditionally included `emailAddress` in the permission body. Drive rejects that field when type=anyone (public link) or type=domain (G-Suite domain-wide). Fixed by including `emailAddress` only when type is `"user"` or `"group"`; for type=domain, the email arg is mapped to the `domain` field instead. **Public-link sharing was impossible before this fix.**

Both bugs caught by the live verification script's actual API responses — respx mocks alone had been silently accepting the broken request shapes.

| Action | Endpoint | Status |
|---|---|---|
| `list_files` | `GET /v3/files` | ✅ Live verified |
| `get_file` | `GET /v3/files/{id}` | ✅ Live verified |
| `upload_file` | `POST /upload/drive/v3/files?uploadType=multipart` | ✅ Live verified (after Bug 1 fix) |
| `download_file` | `GET /v3/files/{id}?alt=media` | ✅ Live verified (unicode round-trip) |
| `create_folder` | `POST /v3/files` (mimeType=…folder) | ✅ Live verified |
| `delete_file` | `DELETE /v3/files/{id}` | ✅ Live verified |
| `search_files` | `GET /v3/files?q=…` | ✅ Live verified |
| `share_file` | `POST /v3/files/{id}/permissions` | ✅ Live verified (after Bug 2 fix) |
| `move_file` | `GET parents + PATCH addParents/removeParents` | ✅ Live verified |
| `copy_file` | `POST /v3/files/{id}/copy` | ✅ Live verified |
| `list_permissions` | `GET /v3/files/{id}/permissions` | ✅ Live verified |
| `get_storage_quota` | `GET /v3/about?fields=storageQuota` | ✅ Live verified |
| `update_file` | `PATCH /v3/files/{id}` | ✅ Live verified |
| `export_file` | `GET /v3/files/{id}/export?mimeType=…` | Probe-skipped |
| `empty_trash` | `DELETE /v3/files/trash` | Probe-skipped |
| `list_comments` | `GET /v3/files/{id}/comments` | ✅ Live verified |
| `create_comment` | `POST /v3/files/{id}/comments` | ✅ Live verified (unicode) |
| `delete_comment` | `DELETE /v3/files/{id}/comments/{commentId}` | ✅ Live verified |
| `list_revisions` | `GET /v3/files/{id}/revisions` | ✅ Live verified |
| `get_revision` | `GET /v3/files/{id}/revisions/{revisionId}` | ✅ Live verified |
| `get_permission` | `GET /v3/files/{id}/permissions/{permissionId}` | ✅ Live verified |
| `delete_permission` | `DELETE /v3/files/{id}/permissions/{permissionId}` | ✅ Live verified |

## Actions

<!-- ACTIONS_START -->
<!-- This section is auto-generated from the connector spec. Do not edit manually. -->
<!-- ACTIONS_END -->

## Tips

- **`upload_file` content MUST be base64-encoded** — the connector decodes once internally, then sends raw bytes in the multipart body. Pass `base64.b64encode(bytes).decode()`.
- **`upload_file(convert_to_google_docs=True)`** — asks Drive to convert the upload to a native Google Workspace format during the write, based on the source `mime_type`: Word/text → Docs, Excel/CSV → Sheets, PowerPoint → Slides. The metadata `mimeType` becomes the Google-native type while the file part keeps its source `Content-Type` so Drive's converter can read the bytes. Raises `ValueError` if the source `mime_type` has no documented conversion target (e.g. PDF). Default is `False` (store as-is).
- **`type` parameter on `share_file`**: `"user"` / `"group"` need a real email; `"anyone"` creates a public link (no email); `"domain"` shares with a G-Suite domain (pass the domain as `email`). The connector handles the body-field mapping correctly per type.
- **Spreadsheet / Doc / Slide deletion**: gdocs / gsheets / gcalendar don't expose delete. Use `gdrive_delete_file(file_id=…)` to delete any Drive-backed file by ID — works uniformly across Google-native and plain MIME types (verified universal across `application/vnd.google-apps.document`, `…spreadsheet`, `…folder`, and `application/octet-stream`).
- **`list_files` vs `search_files`**: `list_files` takes a `folder_id` filter; `search_files` accepts a full Drive query DSL like `"mimeType='application/pdf' and modifiedTime > '2026-01-01'"`.
- **Revisions are auto-created on writes** for native Drive files (Docs, Sheets) and on every content update for binary files. `list_revisions` returns the version history without needing to opt in.
- **`empty_trash` is irreversible** — there's no undo. Listed as Probe-skipped in verification for safety. Use with extreme caution.
- **Dangerous actions**: 6 of 22 (delete_file, delete_comment, delete_permission, share_file, create_comment, empty_trash). Use `kit = ToolKit(["gdrive"], exclude_dangerous=True)` for an agent-safe read-mostly mode.

## Related Connectors

- [Google Docs](../gdocs/) — document CRUD (paired with gdrive for delete)
- [Google Sheets](../gsheets/) — spreadsheet CRUD (paired with gdrive for delete)
- [Google Calendar](../gcalendar/) — events + ACLs
- [S3](../s3/) — alternative object storage

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
