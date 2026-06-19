"""Byte-parity oracle for the Notion binding.

Proves ``build_request(NOTION_BINDING, ...)`` reproduces the EXACT request the
hand-written Notion connector sends — method, URL, query (multi-valued), JSON
body (byte-for-byte), and auth + version headers — for all 21 bindable actions.

Run BEFORE migrating the connector (compares the still-imperative connector
against the binding) and again after (now both go through the binding — a
tautology, but it keeps the gate runnable as a regression check).

    .venv/bin/python scripts/notion_binding_parity.py
"""

from __future__ import annotations

import asyncio
import sys

import httpx

from toolsconnector.connectors.notion.binding import NOTION_BINDING
from toolsconnector.connectors.notion.connector import Notion
from toolsconnector.spec.executor import build_request

CRED = "secret_fake_integration_token"

# (action, kwargs) — realistic args, incl. non-ASCII to pin ensure_ascii=False.
MATRIX = [
    ("get_page", dict(page_id="page-uuid-001")),
    (
        "update_page",
        dict(page_id="page-uuid-001", properties={"Status": {"select": {"name": "Done"}}}),
    ),
    ("archive_page", dict(page_id="page-uuid-001")),
    ("restore_page", dict(page_id="page-uuid-001")),
    (
        "get_page_property",
        dict(page_id="page-uuid", property_id="relation-prop", cursor="prev-prop-cursor", limit=50),
    ),
    ("get_database", dict(database_id="db-uuid")),
    (
        "query_database",
        dict(
            database_id="db-uuid",
            filter={"and": [{"property": "Done", "checkbox": {"equals": True}}]},
            sorts=[{"property": "Priority", "direction": "descending"}],
            limit=50,
            cursor="cursor-xyz",
        ),
    ),
    ("query_database", dict(database_id="db-uuid")),  # bare: only page_size
    (
        "create_database",
        dict(
            parent_id="parent-page",
            title="Tâches ☕",
            properties={"Name": {"title": {}}, "Done": {"checkbox": {}}},
        ),
    ),
    ("update_database", dict(database_id="db-uuid", title="New Title")),
    (
        "update_database",
        dict(database_id="db-uuid", title="T", description="D", properties={"P": {"number": {}}}),
    ),
    ("get_block", dict(block_id="block-uuid-001")),
    ("get_block_children", dict(block_id="block-uuid", limit=25, cursor="cursor-prev")),
    (
        "append_block_children",
        dict(
            block_id="parent-block",
            children=[
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": [{"text": {"content": "x"}}]},
                }
            ],
        ),
    ),
    (
        "update_block",
        dict(
            block_id="block-uuid-001",
            content={"paragraph": {"rich_text": [{"text": {"content": "Edïted"}}]}},
        ),
    ),
    ("delete_block", dict(block_id="block-uuid-001")),
    ("list_users", dict()),
    ("get_user", dict(user_id="user-uuid-001")),
    ("get_me", dict()),
    ("list_comments", dict(block_id="page-uuid", limit=25, cursor="prev-cursor")),
    ("get_comment", dict(comment_id="comment-uuid-001")),
    ("update_comment", dict(comment_id="comment-uuid-001", text="Edited — café")),
    ("delete_comment", dict(comment_id="comment-uuid-001")),
]

GREEN, RED, RST = "\033[32m", "\033[31m", "\033[0m"


def _diffs(real: httpx.Request, gen: httpx.Request) -> list[str]:
    d: list[str] = []
    if real.method != gen.method:
        d.append(f"method {real.method!r} != {gen.method!r}")
    for part in ("scheme", "host", "path"):
        rv, gv = getattr(real.url, part), getattr(gen.url, part)
        if rv != gv:
            d.append(f"url.{part} {rv!r} != {gv!r}")
    rq, gq = sorted(real.url.params.multi_items()), sorted(gen.url.params.multi_items())
    if rq != gq:
        d.append(f"query real={rq} gen={gq}")
    rb, gb = real.read(), gen.read()
    if rb != gb:  # BYTE-level body comparison (separators + ensure_ascii)
        d.append(f"body BYTES\n      real={rb!r}\n      gen ={gb!r}")
    for h in ("authorization", "notion-version"):
        if real.headers.get(h) != gen.headers.get(h):
            d.append(f"header[{h}] {real.headers.get(h)!r} != {gen.headers.get(h)!r}")
    return d


def _capture(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "object": "list",
            "results": [],
            "has_more": False,
            "next_cursor": None,
            "id": "x",
            "object_": "x",
        },
    )


async def main() -> int:
    import respx

    connector = Notion(credentials=CRED)
    await connector._setup()

    rows: list[tuple[str, bool, list[str]]] = []
    for action, kwargs in MATRIX:
        with respx.mock(base_url="https://api.notion.com/v1") as mock:
            mock.route().mock(side_effect=_capture)
            try:
                await getattr(connector, f"a{action}")(**kwargs)
            except Exception:  # noqa: BLE001 - response parsing may fail; request is captured
                pass
            calls = mock.calls
            if not calls:
                rows.append((action, False, ["no request captured"]))
                continue
            real = calls.last.request
        gen = build_request(NOTION_BINDING, action, kwargs, CRED)
        diffs = _diffs(real, gen)
        rows.append((action, not diffs, diffs))

    await connector._teardown()

    print("\n" + "=" * 70)
    print("  NOTION BINDING  vs  IMPERATIVE CONNECTOR   (byte-level request parity)")
    print("=" * 70)
    npass = 0
    for action, ok, diffs in rows:
        badge = f"{GREEN}PASS{RST}" if ok else f"{RED}FAIL{RST}"
        print(f"  {badge}  notion.{action}")
        npass += ok
        for line in diffs:
            print(f"        - {line}")
    print("-" * 70)
    print(f"  {npass}/{len(rows)} byte-identical")
    print("-" * 70 + "\n")
    return 0 if npass == len(rows) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
