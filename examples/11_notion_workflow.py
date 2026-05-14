"""Notion end-to-end workflow — exercises 13 actions including the new
get_me, get_comment, update_comment, delete_comment, and threaded
add_comment(discussion_id=...).

This example demonstrates the Notion connector against a real Notion
workspace. It creates a child page under your test page, appends content,
starts a comment thread, replies in-thread, edits then deletes the reply,
optionally queries a test database, and archives the child page for
cleanup.

Each step prints `[step N/12] action → result` and continues on failure
so you see which actions worked. The final line maps directly to the
README's Verification Status table.

Prerequisites
-------------
    pip install "toolsconnector[notion]"
    export TC_NOTION_CREDENTIALS='secret_xxx-or-ntn_xxx'
    export TC_NOTION_TEST_PAGE_ID='<uuid of a page shared with the integration>'
    # Optional — if set, step 11 runs `query_database`:
    export TC_NOTION_TEST_DATABASE_ID='<uuid of a database shared with the integration>'

How to set up the test page
---------------------------
1. Create a new page in Notion (any name; we'll create children under it).
2. Open the page → click `...` (top right) → **Connections** → add your
   integration. Without this step, every call returns 404.
3. Copy the page UUID from the URL — the 32-hex-char string after the page
   title (with or without dashes).

ToolsConnector is BYOK — get your integration token from
https://www.notion.so/my-integrations.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from toolsconnector.serve import ToolKit

TOKEN = os.environ.get("TC_NOTION_CREDENTIALS", "")
PARENT_PAGE_ID = os.environ.get("TC_NOTION_TEST_PAGE_ID", "")
TEST_DATABASE_ID = os.environ.get("TC_NOTION_TEST_DATABASE_ID", "")

if not TOKEN:
    raise SystemExit("set TC_NOTION_CREDENTIALS env var first")
if not PARENT_PAGE_ID:
    raise SystemExit(
        "set TC_NOTION_TEST_PAGE_ID env var (UUID of a page shared with the integration)"
    )

kit = ToolKit(connectors=["notion"], credentials={"notion": TOKEN})


def call(tool_name: str, args: dict) -> dict:
    """Call a tool and return its result as a dict.

    ``ToolKit.execute()`` returns the JSON-serialised string the MCP/HTTP
    transport would emit on the wire. For Python-native callers we want
    the parsed dict back. Returns an empty dict for tools whose result is
    None / empty (e.g. delete_comment).
    """
    raw = kit.execute(tool_name, args)
    if not raw:
        return {}
    return json.loads(raw)


results: dict[str, bool] = {}
child_page_id: Optional[str] = None
thread_id: Optional[str] = None
reply_id: Optional[str] = None


def step(n: int, name: str, fn: Any) -> Optional[dict]:
    """Run one workflow step, capturing pass/fail without aborting."""
    label = f"[step {n}/12] {name}"
    try:
        result = fn()
        print(f"{label} → ok")
        results[name] = True
        return result
    except Exception as exc:
        print(f"{label} → FAILED: {type(exc).__name__}: {exc}")
        results[name] = False
        return None


# 1. Identity — confirm the integration is authed and show the bot user.
me = step(1, "get_me", lambda: call("notion_get_me", {}))
if me:
    print(f"      bot user: {me.get('name')} ({me.get('id')})")

# 2. Search — visibility check (the integration sees the test page).
step(
    2,
    "search",
    lambda: call("notion_search", {"query": "", "filter_type": "page", "limit": 5}),
)

# 3. Create a child page under the test page parent.
def _create() -> dict:
    return call(
        "notion_create_page",
        {
            "parent_id": PARENT_PAGE_ID,
            "title": "ToolsConnector verification — safe to delete",
        },
    )

new_page = step(3, "create_page", _create)
if new_page:
    child_page_id = new_page.get("id")
    print(f"      created child page: {child_page_id}")

# 4. Append a heading + paragraph block.
if child_page_id:
    def _append() -> dict:
        return call(
            "notion_append_block_children",
            {
                "block_id": child_page_id,
                "children": [
                    {
                        "object": "block",
                        "type": "heading_2",
                        "heading_2": {
                            "rich_text": [{"text": {"content": "Verification run"}}]
                        },
                    },
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [
                                {"text": {"content": "This page was created by the example script."}}
                            ]
                        },
                    },
                ],
            },
        )

    step(4, "append_block_children", _append)

# 5. Start a comment thread on the new page.
if child_page_id:
    thread = step(
        5,
        "add_comment",
        lambda: call(
            "notion_add_comment",
            {"page_id": child_page_id, "text": "Initial thread comment"},
        ),
    )
    if thread:
        thread_id = thread.get("discussion_id")
        print(f"      thread started: discussion_id={thread_id}")

# 6. Reply within the thread (covers the new discussion_id branch).
if thread_id and child_page_id:
    reply = step(
        6,
        "add_comment(discussion_id)",
        lambda: call(
            "notion_add_comment",
            {
                "page_id": child_page_id,
                "text": "Reply in-thread",
                "discussion_id": thread_id,
            },
        ),
    )
    if reply:
        reply_id = reply.get("id")

# 7. Get the reply back (covers new get_comment action).
if reply_id:
    step(7, "get_comment", lambda: call("notion_get_comment", {"comment_id": reply_id}))

# 8. Edit the reply (covers new update_comment action).
if reply_id:
    step(
        8,
        "update_comment",
        lambda: call(
            "notion_update_comment",
            {"comment_id": reply_id, "text": "Reply in-thread (edited)"},
        ),
    )

# 9. Delete the reply (covers new dangerous delete_comment action).
if reply_id:
    step(9, "delete_comment", lambda: call("notion_delete_comment", {"comment_id": reply_id}))

# 10. Query a test database if one was provided.
if TEST_DATABASE_ID:
    step(
        10,
        "query_database",
        lambda: call(
            "notion_query_database",
            {"database_id": TEST_DATABASE_ID, "limit": 5},
        ),
    )
else:
    print("[step 10/12] query_database → skipped (TC_NOTION_TEST_DATABASE_ID not set)")
    results["query_database"] = None  # type: ignore[assignment]

# 11. Cleanup — archive the child page so the workspace stays tidy.
if child_page_id:
    step(11, "archive_page", lambda: call("notion_archive_page", {"page_id": child_page_id}))

# 12. Summary.
print()
print("=" * 60)
print("Verification summary")
print("=" * 60)
succeeded = sum(1 for v in results.values() if v is True)
failed = sum(1 for v in results.values() if v is False)
skipped = sum(1 for v in results.values() if v is None)
total = len(results)
print(f"  Passed:  {succeeded}/{total}")
print(f"  Failed:  {failed}/{total}")
print(f"  Skipped: {skipped}/{total}")
print()
print("Actions verified ✅:")
for name, ok in results.items():
    if ok is True:
        print(f"  - notion_{name.split('(')[0]}")
if failed:
    print()
    print("Actions failed ❌ — check the logs above for the specific error:")
    for name, ok in results.items():
        if ok is False:
            print(f"  - notion_{name.split('(')[0]}")
