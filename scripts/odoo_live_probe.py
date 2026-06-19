"""Live verification probe for the Odoo connector.

Drives the real connector against a real Odoo instance to promote it from the
"pattern" tier to "live". Credentials are read from ``/tmp/odoo-creds.json``
(kept out of the repo) or ``TC_ODOO_*`` environment variables -- never hardcoded.

Default run is **read-only** (version, count, schema introspection, a tiny
search). Pass ``--write`` to additionally exercise a create -> write -> unlink
round-trip on a clearly-labelled throwaway ``res.partner`` (it deletes what it
creates). Only use ``--write`` on an instance where that is safe.

Usage::

    # 1) create /tmp/odoo-creds.json:
    #    {"url": "...", "db": "...", "username": "...", "api_key": "..."}
    .venv/bin/python scripts/odoo_live_probe.py            # read-only
    .venv/bin/python scripts/odoo_live_probe.py --write    # + write round-trip
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import Awaitable
from pathlib import Path
from typing import Any

from toolsconnector.connectors.odoo import Odoo

CREDS_PATH = Path("/tmp/odoo-creds.json")
GREEN, RED, DIM, RST = "\033[32m", "\033[31m", "\033[2m", "\033[0m"


def load_creds() -> dict[str, Any]:
    """Load Odoo credentials from the /tmp JSON file or TC_ODOO_* env vars."""
    if CREDS_PATH.exists():
        return json.loads(CREDS_PATH.read_text())
    env = {k: os.environ.get(f"TC_ODOO_{k.upper()}") for k in ("url", "db", "username", "api_key")}
    if all(env.values()):
        return env  # type: ignore[return-value]
    raise SystemExit(
        f"No credentials found. Create {CREDS_PATH} with "
        '{"url","db","username","api_key"} or set TC_ODOO_* env vars.'
    )


class Probe:
    """Runs labelled probes, tallying pass/fail without aborting on one failure."""

    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0

    async def run(self, label: str, coro: Awaitable[Any]) -> Any:
        try:
            result = await coro
            print(f"  {GREEN}PASS{RST}  {label}")
            self.passed += 1
            return result
        except Exception as e:  # noqa: BLE001 -- probe reports, never crashes
            print(f"  {RED}FAIL{RST}  {label}\n        {type(e).__name__}: {e}")
            self.failed += 1
            return None


async def read_only(odoo: Odoo, p: Probe) -> None:
    print("\n  -- read-only probes --")
    version = await p.run("get_version", odoo.aget_version())
    if version:
        print(f"        {DIM}server {version.server_version} (serie {version.server_serie}){RST}")

    count = await p.run("search_count res.partner", odoo.asearch_count("res.partner"))
    if count is not None:
        print(f"        {DIM}{count} contacts{RST}")

    fields = await p.run(
        "fields_get res.partner", odoo.afields_get("res.partner", ["string", "type"])
    )
    if fields:
        print(f"        {DIM}{len(fields)} fields; sample:{RST}")
        for fname, meta in list(fields.items())[:5]:
            print(f"        {DIM}  - {fname}: {meta.get('type')} ({meta.get('string')}){RST}")

    page = await p.run(
        "search_read res.partner (limit 3)",
        odoo.asearch_read("res.partner", fields=["name", "email"], limit=3),
    )
    if page is not None:
        print(f"        {DIM}names: {[r.get('name') for r in page.items]}{RST}")
        print(f"        {DIM}page_state: offset={page.page_state.offset} has_more={page.page_state.has_more}{RST}")


async def write_round_trip(odoo: Odoo, p: Probe) -> None:
    print("\n  -- write round-trip (create -> write -> unlink) --")
    name = "ToolsConnector probe (safe to delete)"
    new_id = await p.run("create res.partner", odoo.acreate("res.partner", {"name": name}))
    if not new_id:
        return
    print(f"        {DIM}created id={new_id}{RST}")
    await p.run(
        "write res.partner", odoo.awrite("res.partner", [new_id], {"comment": "probe"})
    )
    back = await p.run("read res.partner", odoo.aread("res.partner", [new_id], ["name", "comment"]))
    if back:
        print(f"        {DIM}readback: {back[0]}{RST}")
    await p.run("unlink res.partner (cleanup)", odoo.aunlink("res.partner", [new_id]))


async def main() -> int:
    creds = load_creds()
    do_write = "--write" in sys.argv[1:]
    odoo = Odoo(credentials=creds)
    await odoo._setup()
    print(f"  instance: {odoo._instance_url}  db: {odoo._db}  user: {odoo._login}")
    p = Probe()
    try:
        await read_only(odoo, p)
        if do_write:
            await write_round_trip(odoo, p)
    finally:
        await odoo._teardown()
    print(f"\n  {p.passed} passed, {p.failed} failed")
    return 0 if p.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
