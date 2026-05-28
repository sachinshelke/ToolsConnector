"""Google Workspace cross-connector workflow — compose gdocs + gsheets +
gcalendar + gdrive in a single end-to-end agent-style pipeline.

This example demonstrates that the Tier 1 Google Workspace connectors compose
cleanly in one ``ToolKit``. The scenario is "agent prepares a recurring weekly
review meeting":

    1. Create a Google Doc — the agenda.
    2. Insert agenda items into the doc.
    3. Create a Google Sheet — the action-item tracker.
    4. Seed the sheet with column headers + a sample row.
    5. Round-trip read the seeded values (proves writes landed).
    6. Share the Doc with a real email (or skip if SHARE_WITH not set).
    7. Schedule a Google Calendar event 10 minutes from now that links to the Doc.
    8. Round-trip read the event (proves it was created with the right metadata).
    9. CLEANUP: delete the event, the sheet (via Drive), the doc (via Drive).

Each step prints ``[step N/9] action → summary`` and continues on failure
so you see which actions worked. The cleanup steps run unconditionally at
the end so we don't leave artifacts even if the middle of the flow blew up.

This is a real-API smoke test. It will create + delete real artifacts in
the authenticated account.

Prerequisites
-------------
    pip install "toolsconnector[gdocs,gsheets,gcalendar,gdrive]"

    # One OAuth bearer token with ALL of these scopes (use OAuth Playground):
    #   https://www.googleapis.com/auth/documents
    #   https://www.googleapis.com/auth/spreadsheets
    #   https://www.googleapis.com/auth/calendar
    #   https://www.googleapis.com/auth/drive
    export TC_GW_TOKEN='ya29.your-access-token'

    # Optional — if set, step 6 actually shares the Doc with this address.
    # If unset, step 6 is skipped (doc stays private to the authed user).
    export TC_GW_SHARE_WITH='someone@example.com'

    # Optional — calendar to create the event in. Defaults to 'primary'.
    export TC_GW_CALENDAR_ID='primary'

How to get the token
--------------------
ToolsConnector is BYOK. Fastest path for testing:
    https://developers.google.com/oauthplayground/
    Step 1: paste the four scopes above into the custom-scope box
    Step 1: Authorize APIs (sign in with your Google account)
    Step 2: Exchange authorization code for tokens
    Copy the `access_token` value (starts with `ya29.`) — expires in 1 hour.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from typing import Any

from toolsconnector.serve import ToolKit

TOKEN = os.environ.get("TC_GW_TOKEN", "")
SHARE_WITH = os.environ.get("TC_GW_SHARE_WITH", "")
CALENDAR_ID = os.environ.get("TC_GW_CALENDAR_ID", "primary")

if not TOKEN:
    raise SystemExit(
        "set TC_GW_TOKEN env var first (one OAuth bearer token with "
        "documents + spreadsheets + calendar + drive scopes)"
    )

# All four GW connectors authenticate with the same token. ToolKit accepts
# per-connector credentials, so we install the same token four times.
kit = ToolKit(
    connectors=["gdocs", "gsheets", "gcalendar", "gdrive"],
    credentials={
        "gdocs": TOKEN,
        "gsheets": TOKEN,
        "gcalendar": TOKEN,
        "gdrive": TOKEN,
    },
)


def call(tool_name: str, args: dict) -> Any:
    """Call a tool and return its result as a parsed dict / list.

    ``ToolKit.execute()`` returns the JSON-serialised string the MCP/HTTP
    transport would emit. For Python-native callers we want the parsed
    object back, so we ``json.loads()`` it. Returns an empty dict for
    tools whose result is None / empty (e.g. delete actions).
    """
    raw = kit.execute(tool_name, args)
    if not raw:
        return {}
    return json.loads(raw)


# Artifact IDs we create — collected for cleanup.
created: dict[str, str] = {}
results: list[tuple[int, str, str]] = []  # (step, tool, summary)


def step(n: int, tool: str, args: dict, *, on_success=None) -> Any:
    """Run one step, log result, and continue on failure.

    ``on_success`` is an optional callback invoked with the parsed result
    when the call succeeds. Use it to extract IDs into ``created`` for
    cleanup, or to record summary text for the run log.
    """
    label = f"[step {n}/9] {tool}"
    try:
        out = call(tool, args)
        summary = on_success(out) if on_success else "ok"
        print(f"{label} → {summary}")
        results.append((n, tool, "PASS"))
        return out
    except Exception as e:  # noqa: BLE001 — partial-failure tolerated by design
        print(f"{label} → FAIL: {type(e).__name__}: {str(e)[:160]}")
        results.append((n, tool, f"FAIL: {type(e).__name__}"))
        return None


print("=" * 70)
print("Google Workspace cross-connector workflow")
print(f"  share_with = {SHARE_WITH or '(skipped — set TC_GW_SHARE_WITH to test)'}")
print(f"  calendar   = {CALENDAR_ID}")
print("=" * 70)

# 1. Create a Doc — the agenda.
doc = step(
    1,
    "gdocs_create_document",
    {"title": "[ToolsConnector test] Weekly review agenda"},
    on_success=lambda r: f"document_id={r.get('document_id')}",
)
if doc:
    created["doc_id"] = doc["document_id"]

# 2. Insert agenda content.
if doc:
    step(
        2,
        "gdocs_insert_text",
        {
            "document_id": doc["document_id"],
            "text": (
                "Agenda\n"
                "1. Last week recap\n"
                "2. Blockers\n"
                "3. Action items — track in linked sheet\n"
                "4. Next steps\n"
            ),
            "index": 1,
        },
        on_success=lambda r: "inserted 4 agenda items",
    )

# 3. Create a Sheet — the action-item tracker.
sheet = step(
    3,
    "gsheets_create_spreadsheet",
    {
        "title": "[ToolsConnector test] Action items",
        "sheet_titles": ["Items"],
    },
    on_success=lambda r: f"spreadsheet_id={r.get('spreadsheet_id')}",
)
if sheet:
    created["sheet_id"] = sheet["spreadsheet_id"]

# 4. Seed the sheet with headers + a sample row.
if sheet:
    step(
        4,
        "gsheets_update_values",
        {
            "spreadsheet_id": sheet["spreadsheet_id"],
            "range": "Items!A1:D2",
            "values": [
                ["Owner", "Item", "Due", "Status"],
                ["alice", "Ship 0.3.11", "2026-06-01", "in-progress"],
            ],
            "value_input_option": "USER_ENTERED",
        },
        on_success=lambda r: f"wrote {r.get('updated_cells')} cells",
    )

# 5. Round-trip read — proves the writes landed.
if sheet:
    step(
        5,
        "gsheets_get_values",
        {"spreadsheet_id": sheet["spreadsheet_id"], "range": "Items!A1:D2"},
        on_success=lambda r: f"read back {len(r.get('values', []))} rows",
    )

# 6. Share the Doc — only if SHARE_WITH was provided.
if doc and SHARE_WITH:
    step(
        6,
        "gdrive_share_file",
        {
            "file_id": doc["document_id"],
            "type": "user",
            "role": "reader",
            "email": SHARE_WITH,
            "send_notification_email": False,
        },
        on_success=lambda r: f"shared with {SHARE_WITH} as reader",
    )
elif doc:
    print("[step 6/9] gdrive_share_file → SKIP (set TC_GW_SHARE_WITH to enable)")
    results.append((6, "gdrive_share_file", "SKIP"))

# 7. Schedule a Calendar event — 10 min from now, 30 min long.
start = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=10)
end = start + dt.timedelta(minutes=30)
doc_url = (
    f"https://docs.google.com/document/d/{doc['document_id']}/edit"
    if doc
    else "(no doc — step 1 failed)"
)
event = step(
    7,
    "gcalendar_create_event",
    {
        "calendar_id": CALENDAR_ID,
        "summary": "[ToolsConnector test] Weekly review",
        "description": f"Agenda: {doc_url}",
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": end.isoformat()},
    },
    on_success=lambda r: f"event_id={r.get('id')} (starts {start.isoformat()})",
)
if event:
    created["event_id"] = event["id"]

# 8. Round-trip read the event.
if event:
    step(
        8,
        "gcalendar_get_event",
        {"calendar_id": CALENDAR_ID, "event_id": event["id"]},
        on_success=lambda r: f"summary={r.get('summary')!r}, status={r.get('status')}",
    )

# 9. CLEANUP — always runs, even if the middle blew up.
print("-" * 70)
print("[cleanup] removing created artifacts")
print("-" * 70)

if "event_id" in created:
    try:
        kit.execute(
            "gcalendar_delete_event",
            {"calendar_id": CALENDAR_ID, "event_id": created["event_id"]},
        )
        print(f"  ✓ deleted event {created['event_id']}")
    except Exception as e:  # noqa: BLE001
        print(f"  ✗ FAILED to delete event: {e}")

# Sheets + Docs are both stored on Drive; the canonical destructive path
# is gdrive_delete_file. This also exercises Drive's universal-DELETE
# primitive across two different MIME types.
for label, key in (("sheet", "sheet_id"), ("doc", "doc_id")):
    if key in created:
        try:
            kit.execute("gdrive_delete_file", {"file_id": created[key]})
            print(f"  ✓ deleted {label} {created[key]}")
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ FAILED to delete {label} {created[key]}: {e}")

print()
print("=" * 70)
print("Summary")
print("=" * 70)
passed = sum(1 for _, _, status in results if status == "PASS")
skipped = sum(1 for _, _, status in results if status == "SKIP")
failed = sum(1 for _, _, status in results if status.startswith("FAIL"))
for n, tool, status in results:
    mark = "✓" if status == "PASS" else ("○" if status == "SKIP" else "✗")
    print(f"  {mark} step {n}: {tool} — {status}")
print(f"\nTotal: {passed} passed, {skipped} skipped, {failed} failed of {len(results)}")
