# Productivity

Connectors for office productivity, scheduling, and design tools. 6 connectors, 96 actions.

This category covers the **Google Workspace** family (Calendar, Docs, Sheets, Tasks), plus **Calendly** for scheduling and **Figma** for design files.

**Verification status** (see [Verification tiers](../../ROADMAP.md#verification-tiers) for what each tier means):

| Connector | Tier | Live-verified actions |
|---|---|---|
| Google Calendar | **Tier 1 — Live verified** | 17 of 20 + 3 envelope-verified (2026-05-29) |
| Google Docs | **Tier 1 — Live verified** | 5 of 5 (2026-05-28) |
| Google Sheets | **Tier 1 — Live verified** | 16 of 16 (2026-05-28) |
| Google Tasks | **Tier 1 — Live verified** | 13 of 13 (2026-05-29) |
| Calendly | Tier 3 — Pattern correct | — |
| Figma | Tier 3 — Pattern correct | — |

---

### Google Calendar

**Category:** Productivity | **Auth:** OAuth 2.0 Bearer Token | **Actions:** 20 | **Status:** ✅ Tier 1 — Live verified

Connect to Google Calendar to manage events, calendars, ACL rules, and free/busy lookups. Supports recurring events with RFC 5545 `RRULE`, natural-language quick-add, event moves between calendars, full ACL CRUD, and the `colors` enumeration.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| list_calendars | List calendars | No |
| create_calendar | Create a new calendar | Yes |
| update_calendar | Update a calendar | Yes |
| delete_calendar | Delete a calendar | Yes |
| subscribe_calendar | Subscribe to an external calendar | Yes |
| unsubscribe_calendar | Unsubscribe from a calendar | Yes |
| clear_calendar | Clear all events from the **primary** calendar | Yes |
| list_events | List calendar events | No |
| get_event | Get a single event by ID | No |
| create_event | Create a calendar event | Yes |
| update_event | Update a calendar event | Yes |
| delete_event | Delete a calendar event | Yes |
| move_event | Move an event to a different calendar | No |
| quick_add_event | Quick-add an event using natural language | Yes |
| list_event_instances | List instances of a recurring event | No |
| list_calendar_acl | List access-control rules for a calendar | No |
| add_calendar_acl | Add an access-control rule to a calendar | Yes |
| remove_calendar_acl | Remove an access-control rule from a calendar | Yes |
| get_free_busy | Query free/busy information for calendars | No |
| get_colors | Get available calendar and event colors | No |

**Quick start:**

```python
kit = ToolKit(["gcalendar"], credentials={"gcalendar": "ya29.your-access-token"})
event_json = kit.execute(
    "gcalendar_create_event",
    {
        "calendar_id": "primary",
        "summary": "Review meeting",
        "start": {"dateTime": "2026-06-01T10:00:00-07:00"},
        "end": {"dateTime": "2026-06-01T11:00:00-07:00"},
    },
)  # JSON string — parse with json.loads(event_json) to get the dict
```

**Extras required:** `pip install "toolsconnector[gcalendar]"`

**Live verification:** End-to-end run on a throwaway secondary calendar covered create/get/update/delete with unicode round-trip, quick-add via natural language, recurring event with `FREQ=WEEKLY;COUNT=3`, move_event between calendars, full ACL CRUD, free/busy lookup, color enumeration. 3 actions probe-skipped intentionally: `subscribe_calendar` / `unsubscribe_calendar` (would alter user's persistent calendarList), `clear_calendar` (only valid on primary — would erase real events). See the [connector README](../../src/toolsconnector/connectors/gcalendar/README.md).

---

### Google Docs

**Category:** Productivity | **Auth:** OAuth 2.0 Bearer Token | **Actions:** 5 | **Status:** ✅ Tier 1 — Live verified

Connect to Google Docs to create documents, insert text, run batch update operations, and extract plain text. Backed by the Docs REST v1 API.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| create_document | Create a new document | Yes |
| get_document | Get a document by ID | No |
| get_document_text | Extract plain text from a document | No |
| insert_text | Insert text into a document | Yes |
| batch_update | Apply a batch of structural changes (insertText, deleteContentRange, etc.) | Yes |

**Quick start:**

```python
import json

kit = ToolKit(["gdocs"], credentials={"gdocs": "ya29.your-access-token"})
doc = json.loads(kit.execute("gdocs_create_document", {"title": "Meeting notes"}))
kit.execute("gdocs_insert_text", {"document_id": doc["document_id"], "text": "Agenda\n"})
```

**Extras required:** `pip install "toolsconnector[gdocs]"`

**Live verification:** End-to-end run on a throwaway document covered the full lifecycle: `create_document` → `get_document` (metadata round-trip) → `get_document_text` (empty body returns `"\n"`) → `insert_text` (with unicode `你好 🚀` round-trip) → `batch_update` (multi-request envelope) → real 404 → typed `NotFoundError`. Cleanup deleted the throwaway via Drive API, zero artifacts. Live testing also fixed a production bug: `insert_text` was awaiting the auto-installed sync wrapper instead of `abatch_update`. See the [connector README](../../src/toolsconnector/connectors/gdocs/README.md).

---

### Google Sheets

**Category:** Productivity | **Auth:** OAuth 2.0 Bearer Token | **Actions:** 16 | **Status:** ✅ Tier 1 — Live verified

Connect to Google Sheets for the full value + structural surface — values CRUD via A1 ranges, multi-tab management, batch operations, cell merging, auto-resize. Backed by the Sheets REST v4 API.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| create_spreadsheet | Create a new spreadsheet | Yes |
| get_spreadsheet | Get spreadsheet metadata and sheets | No |
| get_sheet_metadata | Get sheet metadata for all tabs | No |
| get_values | Get values from a range | No |
| batch_get_values | Batch get values from multiple ranges | No |
| update_values | Update values in a range | Yes |
| batch_update_values | Batch update values across multiple ranges | Yes |
| append_values | Append values after a range | Yes |
| clear_values | Clear values from a range | Yes |
| add_sheet | Add a new sheet tab | Yes |
| rename_sheet | Rename a sheet tab within a spreadsheet | Yes |
| copy_sheet | Copy a sheet to another spreadsheet | No |
| delete_sheet | Delete a sheet tab | Yes |
| merge_cells | Merge cells in a range | Yes |
| auto_resize_columns | Auto-resize columns to fit content | No |
| batch_update_spreadsheet | Apply structural changes to a spreadsheet (escape hatch) | Yes |

**Quick start:**

```python
import json

kit = ToolKit(["gsheets"], credentials={"gsheets": "ya29.your-access-token"})
sheet = json.loads(kit.execute(
    "gsheets_create_spreadsheet",
    {"title": "Budget", "sheet_titles": ["Q1", "Q2"]},
))
kit.execute(
    "gsheets_update_values",
    {
        "spreadsheet_id": sheet["spreadsheet_id"],
        "range": "Q1!A1:B2",
        "values": [["Item", "Cost"], ["Lunch", 12]],
    },
)
```

**Extras required:** `pip install "toolsconnector[gsheets]"`

**Live verification:** End-to-end run on a throwaway spreadsheet covered the full action surface, including unicode `你好 🚀` round-trip through `update_values`/`get_values`. Cleanup deleted the throwaway via Drive API, zero artifacts. See the [connector README](../../src/toolsconnector/connectors/gsheets/README.md).

---

### Google Tasks

**Category:** Productivity | **Auth:** OAuth 2.0 Bearer Token | **Actions:** 13 | **Status:** ✅ Tier 1 — Live verified

Connect to Google Tasks for to-do management. Each user has one default task list and can create more. Tasks support parent/child nesting and ordered positions within a list.

**Actions:**

| Action | Description | Dangerous |
|--------|-------------|-----------|
| list_task_lists | List all task lists | No |
| get_task_list | Get a task list by ID | No |
| create_task_list | Create a new task list | Yes |
| update_task_list | Update a task list title | Yes |
| delete_task_list | Delete a task list | Yes |
| list_tasks | List tasks in a task list | No |
| get_task | Get a task by ID | No |
| create_task | Create a new task | Yes |
| update_task | Update a task | Yes |
| complete_task | Complete a task | Yes |
| move_task | Move a task (reparent or reorder) | No |
| delete_task | Delete a task | Yes |
| clear_completed | Clear completed tasks from a list | Yes |

**Quick start:**

```python
import json

kit = ToolKit(["gtasks"], credentials={"gtasks": "ya29.your-access-token"})
lists = json.loads(kit.execute("gtasks_list_task_lists", {}))
default_list = lists["items"][0]
kit.execute(
    "gtasks_create_task",
    {"task_list_id": default_list["id"], "title": "Ship 0.3.11"},
)
```

**Extras required:** `pip install "toolsconnector[gtasks]"`

**Live verification:** End-to-end run on a throwaway task list covered every action: `list_task_lists` (baseline read), `create_task_list` (throwaway), `get_task_list` (round-trip), `update_task_list` (rename via PATCH), `list_tasks`, `create_task` (twice with due dates), `get_task` (round-trip), `update_task` (extend due), `move_task` (reparent), `complete_task`, `clear_completed`, `delete_task`, `delete_task_list` (cleanup). Throwaway cleanly deleted, zero artifacts on user's account. **Live testing surfaced + fixed 1 real production bug**: `update_task_list` was using HTTP PUT with a title-only body, which Google rejects with HTTP 400 because `tasklists.update` requires a complete TaskList resource. Fixed by switching to HTTP PATCH which accepts partial bodies. MCP stdio dispatch also verified end-to-end (initialize + tools/list + tools/call). See the [connector README](../../src/toolsconnector/connectors/gtasks/README.md).

---

### Calendly

**Category:** Productivity | **Auth:** OAuth 2.0 / Personal Access Token | **Actions:** 20 | **Status:** Tier 3 — Pattern correct

Connect to Calendly to manage event types, scheduled events, invitees, organization members, routing forms, availability schedules, and webhooks.

**Actions:** see the [connector README](../../src/toolsconnector/connectors/calendly/README.md) for the full action table.

**Quick start:**

```python
import json

kit = ToolKit(["calendly"], credentials={"calendly": "your-pat-or-oauth-token"})
me = json.loads(kit.execute("calendly_get_current_user", {}))
events = kit.execute("calendly_list_scheduled_events", {"user": me["uri"]})
```

**Extras required:** `pip install "toolsconnector[calendly]"`

---

### Figma

**Category:** Productivity | **Auth:** Personal Access Token | **Actions:** 22 | **Status:** Tier 3 — Pattern correct

Connect to Figma for read-only access to files, components, styles, variables, team libraries, and version history — plus comment threads and webhook subscriptions.

**Actions:** see the [connector README](../../src/toolsconnector/connectors/figma/README.md) for the full action table.

**Quick start:**

```python
kit = ToolKit(["figma"], credentials={"figma": "your-pat-token"})
file = kit.execute("figma_get_file", {"file_key": "abc123"})
```

**Extras required:** `pip install "toolsconnector[figma]"`

---

## When to pick which

- **Google Calendar** — meeting scheduling automation, availability checks, ACL-driven shared-calendar workflows, free/busy lookup before event creation.
- **Google Docs** — automated document generation, template-based reports, content extraction. Pair with Drive for permissions and folder placement.
- **Google Sheets** — spreadsheets as lightweight databases, ETL targets, automated reports, structured logging.
- **Google Tasks** — lightweight to-do sync; pair with Calendar / Gmail for productivity workflows.
- **Calendly** — outward-facing scheduling pages where invitees pick from your availability windows. Backend automation around the resulting `ScheduledEvent`.
- **Figma** — design-file metadata + content extraction for design-system tooling, brand-asset pipelines, or component analytics.

All are **BYOK** — you bring your own OAuth access token / PAT / API key.

## Cross-connector workflows

The Google Workspace connectors compose naturally:

- **Meeting prep**: `gcalendar.list_events` → for each event, `gdocs.create_document` → `gdrive.share_file` with the attendees.
- **Spreadsheet-driven calendar**: `gsheets.get_values` of a schedule sheet → `gcalendar.create_event` per row.
- **Doc → Tasks**: `gdocs.get_document_text` → parse action items → `gtasks.create_task` per item.

See [`examples/12_google_workspace.py`](../../examples/12_google_workspace.py) for a runnable end-to-end demonstration.

## See also

- [Google Calendar connector README](../../src/toolsconnector/connectors/gcalendar/README.md)
- [Google Docs connector README](../../src/toolsconnector/connectors/gdocs/README.md)
- [Google Sheets connector README](../../src/toolsconnector/connectors/gsheets/README.md)
- [Google Tasks connector README](../../src/toolsconnector/connectors/gtasks/README.md)
- [Storage category](storage.md) — Google Drive lives here (file storage, sharing)
- [Communication category](communication.md) — Gmail lives here
- [Credentials guide](../guides/credentials.md) — OAuth Playground walkthrough for Google Workspace tokens
- [MCP server guide](../guides/mcp-server.md) — exposing Google Workspace tools to MCP clients
