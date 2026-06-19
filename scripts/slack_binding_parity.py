"""Byte-parity oracle for the Slack binding.

Proves ``build_request(SLACK_BINDING, ...)`` reproduces the EXACT request the
hand-written Slack connector sends — method, URL, query (multi-valued), JSON
body (byte-for-byte), and the auth header — for all 50 bindable actions.
``upload_file`` (form ``data=``) is the documented escape hatch and is excluded.

    .venv/bin/python scripts/slack_binding_parity.py
"""

from __future__ import annotations

import asyncio
import sys

import httpx

from toolsconnector.connectors.slack.binding import SLACK_BINDING
from toolsconnector.connectors.slack.connector import Slack
from toolsconnector.spec.executor import build_request

CRED = "xoxb-fake-bot-token"

# (action, kwargs) — realistic args exercising renames, bools (query+body),
# optionals present/absent, hardcoded literals, nested set_status, cursors.
MATRIX = [
    ("send_message", dict(channel="C123", text="hé ☕", thread_ts="1.2", unfurl_links=False)),
    ("send_message", dict(channel="C123", text="plain")),  # bools default True
    ("update_message", dict(channel="C123", ts="1.2", text="edit")),
    ("delete_message", dict(channel="C123", ts="1.2")),
    ("schedule_message", dict(channel="C123", text="later", post_at=1893456000, thread_ts="1.2")),
    ("list_scheduled_messages", dict(limit=50, channel="C123", cursor="cur1")),
    ("list_scheduled_messages", dict()),  # bare: only limit default
    ("delete_scheduled_message", dict(channel="C123", scheduled_message_id="Q1")),
    ("get_permalink", dict(channel="C123", message_ts="1.2")),
    ("list_channels", dict(limit=5000, exclude_archived=True, cursor="cur1")),  # clamp 1000
    ("list_channels", dict()),  # defaults: types literal, limit 100, exclude_archived false
    ("get_channel", dict(channel_id="C123")),  # rename -> channel
    ("create_channel", dict(name="new", is_private=True)),
    ("archive_channel", dict(channel="C123")),
    ("unarchive_channel", dict(channel="C123")),
    ("rename_channel", dict(channel="C123", name="renamed")),
    ("set_channel_topic", dict(channel="C123", topic="topic")),
    ("set_channel_purpose", dict(channel="C123", purpose="purpose")),
    ("invite_to_channel", dict(channel="C123", users="U1,U2")),
    ("kick_from_channel", dict(channel="C123", user="U1")),
    ("join_channel", dict(channel="C123")),
    ("leave_channel", dict(channel="C123")),
    ("list_channel_members", dict(channel="C123", limit=25, cursor="cur1")),
    ("list_messages", dict(channel="C123", limit=25, cursor="cur1", oldest="1.0", latest="2.0")),
    ("list_messages", dict(channel="C123")),  # no optionals
    ("list_thread_replies", dict(channel="C123", thread_ts="1.2", limit=25, cursor="cur1")),
    ("add_reaction", dict(channel="C123", timestamp="1.2", emoji="thumbsup")),  # emoji -> name
    ("remove_reaction", dict(channel="C123", timestamp="1.2", emoji="thumbsup")),
    ("get_reactions", dict(channel="C123", timestamp="1.2")),  # full=true literal
    ("pin_message", dict(channel="C123", timestamp="1.2")),
    ("unpin_message", dict(channel="C123", timestamp="1.2")),
    ("list_pins", dict(channel="C123")),
    ("delete_file", dict(file_id="F1")),  # file_id -> file
    ("get_file_info", dict(file_id="F1")),  # file_id -> file
    ("list_users", dict(limit=25, cursor="cur1")),
    ("get_user", dict(user_id="U1")),  # user_id -> user
    ("lookup_user_by_email", dict(email="a@b.com")),
    ("get_user_presence", dict(user_id="U1")),  # user_id -> user
    ("get_user_profile", dict(user_id="U1")),  # user_id -> user
    ("set_presence", dict(presence="away")),
    ("search_messages", dict(query="hello", count=200, page=2)),  # count clamp 100
    ("search_messages", dict(query="hello")),  # defaults: sort, sort_dir, count 20, page 1
    ("set_status", dict(status_text="Lunch", status_emoji=":taco:", expiration=0)),  # nested + 0
    ("set_status", dict(status_text="Heads down")),  # only required
    ("add_bookmark", dict(channel_id="C1", title="Docs", link="https://x", emoji=":book:")),
    (
        "add_bookmark",
        dict(channel_id="C1", title="Docs", link="https://x"),
    ),  # no emoji; type literal
    ("list_bookmarks", dict(channel_id="C1")),
    ("remove_bookmark", dict(bookmark_id="Bk1", channel_id="C1")),
    ("add_reminder", dict(text="Standup", time="1893456000", user="U1")),
    ("add_reminder", dict(text="Standup", time="in 5 minutes")),  # no user
    ("list_reminders", dict()),
    ("delete_reminder", dict(reminder_id="Rm1")),  # reminder_id -> reminder
    ("list_emoji", dict()),
    ("auth_test", dict()),  # POST, no body
    ("get_team_info", dict()),
    ("create_usergroup", dict(name="Eng", handle="eng", description="d", channels="C1,C2")),
    ("create_usergroup", dict(name="Eng", handle="eng")),  # no optionals (is not None)
    ("list_usergroups", dict(include_users=True, include_disabled=True)),
    ("list_usergroups", dict()),  # defaults false/false
    ("update_usergroup", dict(usergroup_id="S1", name="Eng2", channels="C1")),  # partial
]

GREEN, RED, RST = "\033[32m", "\033[31m", "\033[0m"

_OK_BODY = {
    "ok": True,
    "response_metadata": {"next_cursor": ""},
    "channels": [],
    "members": [],
    "messages": [],
    "channel": {},
    "message": {},
    "user": {},
    "users": [],
    "profile": {},
    "team": {},
    "bookmark": {"date_created": 0, "date_updated": 0},
    "bookmarks": [],
    "reminder": {},
    "reminders": [],
    "usergroup": {"prefs": {"channels": []}},
    "usergroups": [],
    "emoji": {},
    "scheduled_messages": [],
    "items": [],
    "permalink": "x",
    "scheduled_message_id": "Q",
    "has_more": False,
    "file": {},
    "presence": "away",
}


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
        d.append(f"query\n      real={rq}\n      gen ={gq}")
    rb, gb = real.read(), gen.read()
    if rb != gb:  # BYTE-level body comparison
        d.append(f"body BYTES\n      real={rb!r}\n      gen ={gb!r}")
    if real.headers.get("authorization") != gen.headers.get("authorization"):
        d.append(
            f"auth {real.headers.get('authorization')!r} != {gen.headers.get('authorization')!r}"
        )
    return d


def _capture(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=_OK_BODY)


async def main() -> int:
    import respx

    connector = Slack(credentials=CRED)
    await connector._setup()

    rows: list[tuple[str, bool, list[str]]] = []
    for action, kwargs in MATRIX:
        with respx.mock(base_url="https://slack.com/api") as mock:
            mock.route().mock(side_effect=_capture)
            try:
                await getattr(connector, f"a{action}")(**kwargs)
            except Exception:  # noqa: BLE001 - response parse may fail; request is captured
                pass
            calls = mock.calls
            if not calls:
                rows.append((action, False, ["no request captured"]))
                continue
            real = calls.last.request
        gen = build_request(SLACK_BINDING, action, kwargs, CRED)
        rows.append((action, not _diffs(real, gen), _diffs(real, gen)))

    await connector._teardown()

    print("\n" + "=" * 72)
    print("  SLACK BINDING  vs  IMPERATIVE CONNECTOR   (byte-level request parity)")
    print("=" * 72)
    npass = 0
    for action, ok, diffs in rows:
        badge = f"{GREEN}PASS{RST}" if ok else f"{RED}FAIL{RST}"
        print(f"  {badge}  slack.{action}")
        npass += ok
        for line in diffs:
            print(f"        - {line}")
    print("-" * 72)
    print(f"  {npass}/{len(rows)} byte-identical")
    print("-" * 72 + "\n")
    return 0 if npass == len(rows) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
