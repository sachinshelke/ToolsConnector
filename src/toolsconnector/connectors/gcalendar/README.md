# Google Calendar

> Events + calendars + ACLs + free/busy via the Calendar API v3

| | |
|---|---|
| **Company** | Google LLC |
| **Category** | Productivity |
| **Protocol** | REST |
| **API Version** | v3 |
| **Website** | [calendar.google.com](https://calendar.google.com) |
| **API Docs** | [developers.google.com/calendar/api](https://developers.google.com/calendar/api/v3/reference) |
| **Auth** | OAuth 2.0 bearer token (`ya29.…`) |
| **Rate Limit** | 600 req/min per project — connector throttle: 600/min |
| **Pricing** | Free with Google account |

---

## Overview

20 actions covering: event lifecycle (CRUD + quick-add + recurring instances + move-between-calendars), calendar management (create / update / delete / clear / subscribe / unsubscribe), ACL rules (list / add / remove for granting calendar access to other users), free/busy queries across calendars, and color enumeration.

## Use Cases

- Meeting scheduling automation
- Calendar sync (external system → Google Calendar)
- Free/busy lookup for scheduling assistants
- Shared calendar provisioning
- Event reminders and notifications

## Installation

```bash
pip install "toolsconnector[gcalendar]"
```

## Credentials

```python
# Programmatic
kit = ToolKit(["gcalendar"], credentials={"gcalendar": "ya29.your_token"})

# Env (any one wins)
# export TC_GCALENDAR_CREDENTIALS=ya29.…
# export TC_GCALENDAR_TOKEN=ya29.…
kit = ToolKit(["gcalendar"])
```

Access token needs at least `https://www.googleapis.com/auth/calendar` scope. See [Credentials Guide](../../../docs/guides/credentials.md).

## Quick Start

```python
from toolsconnector.serve import ToolKit
from datetime import datetime, timedelta, timezone

kit = ToolKit(["gcalendar"], credentials={"gcalendar": "ya29.…"})

# Create an event 7 days from now
start = (datetime.now(timezone.utc) + timedelta(days=7)).replace(microsecond=0)
evt = kit.execute("gcalendar_create_event", {
    "summary": "Quarterly review",
    "start": start.isoformat(),
    "end": (start + timedelta(hours=1)).isoformat(),
    "calendar_id": "primary",
    "description": "Agenda…",
    "attendees": ["alice@example.com"],
    "send_updates": "all",  # email invites
})
print(evt["id"], evt["html_link"])

# Free/busy lookup
busy = kit.execute("gcalendar_get_free_busy", {
    "calendar_ids": ["primary"],
    "time_min": start.isoformat(),
    "time_max": (start + timedelta(days=1)).isoformat(),
})
```

### MCP Server

```python
kit.serve_mcp()
```

## Authentication

Same paths as the other Google Workspace connectors:

### Path 1 — OAuth Playground (fastest)

1. https://developers.google.com/oauthplayground
2. Step 1: paste `https://www.googleapis.com/auth/calendar` → **Authorize APIs**
3. Sign in + consent → Step 2: **Exchange authorization code for tokens** → copy `access_token`

### Path 2 — gcloud CLI

```bash
gcloud auth application-default login --scopes=https://www.googleapis.com/auth/calendar
gcloud auth application-default print-access-token
```

## Required scope

| Action group | Minimum scope |
|---|---|
| All reads (8: `list_events` / `get_event` / `list_event_instances` / `list_calendars` / `list_calendar_acl` / `get_free_busy` / `get_colors` / `move_event`) | `https://www.googleapis.com/auth/calendar.readonly` (note: `move_event` actually requires write on both calendars) |
| All 12 mutating actions | `https://www.googleapis.com/auth/calendar` |

## Error Handling

| Typed exception | HTTP | When |
|---|---|---|
| `InvalidCredentialsError` | 401 | Access token expired/revoked |
| `PermissionDeniedError` | 403 | Token lacks `calendar` scope OR not invited to the calendar |
| `NotFoundError` | 404 | event_id / calendar_id doesn't exist |
| `APIError` | 410 | Event was deleted (Google returns 410 Gone for already-deleted events) |
| `ValidationError` | 400/422 | Bad RRULE, bad date/time, malformed body |
| `RateLimitError` | 429 | Per-project quota exhausted |
| `ServerError` | 5xx | Google-side outage |
| `ConnectionError` / `TimeoutError` / `TransportError` | n/a | Network-layer failures (typed wrappers) |

### Path-traversal protection

Calendar IDs (commonly email addresses like `alice@example.com` and the synthetic `c_…@group.calendar.google.com` for secondary calendars) + event IDs + ACL rule IDs are percent-encoded via the `_p()` helper before URL interpolation. Pinned by `test_calendar_id_with_slash_percent_encoded` + `test_event_with_email_calendar_id`.

## Verification Status

All 20 actions verified — **17 Live verified** + **3 Probe-skipped intentionally** (would mutate the user's persistent `calendarList` or require touching the primary calendar destructively):

| Live verified (17) | Probe-skipped (3) |
|---|---|
| `list_calendars`, `create_calendar`, `update_calendar`, `delete_calendar`, `list_events`, `get_event`, `create_event`, `update_event`, `delete_event`, `quick_add_event`, `list_event_instances` (real recurring event with `RRULE:FREQ=WEEKLY;COUNT=3`), `move_event`, `get_free_busy`, `list_calendar_acl`, `add_calendar_acl`, `remove_calendar_acl`, `get_colors` | `subscribe_calendar` / `unsubscribe_calendar` (would alter user's persistent calendarList view), `clear_calendar` (only valid on the primary calendar — would erase user's real events) |

End-to-end live run on 2026-05-28 against `www.googleapis.com/calendar/v3` with a real OAuth 2.0 access token: created throwaway secondary calendar → created/updated/got/deleted events (with unicode + emoji round-trip `你好 🚀`) → seeded a recurring event and verified 3 instances → exercised ACL CRUD → moved an event between calendars → cleaned up (throwaway calendar deleted via Calendar API DELETE, HTTP 204). Zero leftover artifacts.

**42 respx unit tests** pin request/response shapes across 5 rounds (happy path × 20 actions, defensive parsing, URL-path injection guards including the email-calendar-id round-trip and recurring-event RRULE parsing, error matrix including 410 Gone, transport errors, MCP exposure, OpenAI schema sweep, dangerous-flag audit, sync wrappers, concurrency).

| Action | Endpoint | Status |
|---|---|---|
| `list_events` | `GET /v3/calendars/{id}/events` | ✅ Live verified |
| `get_event` | `GET /v3/calendars/{id}/events/{eventId}` | ✅ Live verified |
| `create_event` | `POST /v3/calendars/{id}/events` | ✅ Live verified |
| `update_event` | `PATCH /v3/calendars/{id}/events/{eventId}` | ✅ Live verified |
| `delete_event` | `DELETE /v3/calendars/{id}/events/{eventId}` | ✅ Live verified |
| `quick_add_event` | `POST /v3/calendars/{id}/events/quickAdd?text=…` | ✅ Live verified |
| `list_event_instances` | `GET /v3/calendars/{id}/events/{eventId}/instances` | ✅ Live verified (RRULE) |
| `move_event` | `POST /v3/calendars/{src}/events/{eventId}/move?destination=…` | ✅ Live verified |
| `list_calendars` | `GET /v3/users/me/calendarList` | ✅ Live verified |
| `create_calendar` | `POST /v3/calendars` | ✅ Live verified |
| `update_calendar` | `GET + PUT /v3/calendars/{id}` (PUT requires full body) | ✅ Live verified |
| `delete_calendar` | `DELETE /v3/calendars/{id}` | ✅ Live verified |
| `clear_calendar` | `POST /v3/calendars/{id}/clear` | Probe-skipped |
| `subscribe_calendar` | `POST /v3/users/me/calendarList` | Probe-skipped |
| `unsubscribe_calendar` | `DELETE /v3/users/me/calendarList/{id}` | Probe-skipped |
| `list_calendar_acl` | `GET /v3/calendars/{id}/acl` | ✅ Live verified |
| `add_calendar_acl` | `POST /v3/calendars/{id}/acl` | ✅ Live verified |
| `remove_calendar_acl` | `DELETE /v3/calendars/{id}/acl/{ruleId}` | ✅ Live verified |
| `get_free_busy` | `POST /v3/freeBusy` | ✅ Live verified |
| `get_colors` | `GET /v3/colors` | ✅ Live verified |

## Actions

<!-- ACTIONS_START -->
<!-- This section is auto-generated from the connector spec. Do not edit manually. -->
<!-- ACTIONS_END -->

## Tips

- **Date vs DateTime**: `create_event(start="2026-06-01")` (10-char date) creates an all-day event; `create_event(start="2026-06-01T10:00:00-07:00")` creates a timed event. The connector detects the format automatically.
- **Recurring events**: `recurrence` is a list of RFC 5545 RRULE strings (e.g. `"RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR;COUNT=10"`). Set via `batch_update` payload — the connector's `create_event` doesn't expose `recurrence` directly; use direct PATCH if you need it (the live verification covers this path).
- **`send_updates` notification policy**: `"all"` emails everyone, `"externalOnly"` emails only non-organization attendees, `"none"` sends nothing. Default is `"none"` — safe for bulk operations.
- **Time zones**: pass IANA timezone strings (e.g. `"America/New_York"`, `"UTC"`). If omitted, defaults to the calendar's timezone setting.
- **`move_event` is NOT dangerous-flagged** — it relocates rather than destroys data. Available in `exclude_dangerous=True` mode.
- **`clear_calendar` only works on the primary calendar** — and it deletes ALL events in your primary. Use with extreme care.
- **Secondary calendar IDs look like `c_<long hash>@group.calendar.google.com`**, returned from `create_calendar`. Save the ID; it's the only way to reference the calendar afterward (the summary is mutable).
- **Dangerous actions**: 12 of 20. Use `kit = ToolKit(["gcalendar"], exclude_dangerous=True)` for agent-safe read-only mode (leaves 8 actions including `move_event`).

## Related Connectors

- [Google Docs](../gdocs/) — document CRUD
- [Google Sheets](../gsheets/) — spreadsheet CRUD
- [Google Drive](../gdrive/) — file management

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
