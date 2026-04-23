"""End-to-end tests for the Slack connector using respx.

Pattern reference for per-connector tests across the codebase. Anyone
adding a new connector should be able to copy this file's structure
verbatim.

Why respx (not real API calls):
    The Slack Web API requires real Bot tokens and a real workspace.
    We cannot exercise the live API in OSS CI without exposing a token
    or trusting external network reliability. respx mounts a transport
    adapter on the underlying httpx.AsyncClient and lets us assert on
    the requests our code emits + serve canned responses — no network,
    fully deterministic.

Coverage philosophy:
    Three categories per connector, in priority order:
      1. **Happy path on the most-common action.** Verifies request
         shape (method, URL, headers, body) and response parsing.
      2. **Error mapping.** Vendor's auth/notfound/ratelimit responses
         translate to our typed exception hierarchy.
      3. **Pagination.** If the connector exposes paginated listings,
         test that PageState.cursor + has_more wire through correctly
         on a 2-page sequence.

    Five tests per connector is the floor; ten the ceiling. Don't try
    to mirror every action — `tests/unit/test_connectors.py` already
    smoke-tests every action's get_spec(). This file is for behavioral
    correctness on representative actions.
"""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
import respx

from toolsconnector.connectors.slack import Slack
from toolsconnector.errors import APIError, NotFoundError, RateLimitError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def slack() -> Slack:
    """Slack connector with a fake token, ready to use.

    The token never reaches the real Slack API because respx intercepts
    every request the connector's httpx.AsyncClient emits.

    Uses @pytest_asyncio.fixture (not @pytest.fixture) because the
    project runs pytest-asyncio in strict mode — see pyproject.toml's
    [tool.pytest.ini_options].

    Tests `await` the `a*`-prefixed methods (e.g. `asend_message`)
    rather than the sync wrappers (`send_message`). BaseConnector
    auto-installs both: `name(...)` is a sync wrapper that internally
    runs the coroutine; `aname(...)` is the raw async method. respx
    intercepts at the httpx layer either way, but `await aname(...)`
    keeps the test in a single event-loop and integrates cleanly
    with pytest-asyncio's fixture lifecycle.
    """
    connector = Slack(credentials="xoxb-fake-test-token")
    await connector._setup()
    yield connector
    await connector._teardown()


# ---------------------------------------------------------------------------
# 1. Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_message_happy_path(slack: Slack) -> None:
    """send_message: verify request shape + response parsing."""
    with respx.mock(base_url="https://slack.com/api", assert_all_called=True) as respx_mock:
        route = respx_mock.post("/chat.postMessage").mock(
            return_value=httpx.Response(
                200,
                json={
                    "ok": True,
                    "channel": "C01234ABCDE",
                    "ts": "1700000000.000100",
                    "message": {
                        "type": "message",
                        "user": "U_BOT",
                        "text": "Deployed v2.1",
                        "ts": "1700000000.000100",
                        "bot_id": "B_BOT",
                    },
                },
            )
        )

        msg = await slack.asend_message(channel="C01234ABCDE", text="Deployed v2.1")

        # Response was parsed into the typed Message model
        assert msg.text == "Deployed v2.1"
        assert msg.channel == "C01234ABCDE"
        assert msg.ts == "1700000000.000100"

        # Request was emitted exactly once (assert_all_called)
        assert route.call_count == 1
        request = route.calls.last.request

        # Auth header carries the Bearer token verbatim
        assert request.headers["authorization"] == "Bearer xoxb-fake-test-token"

        # Body has the user-facing fields + Slack defaults
        body = request.read()
        assert b'"channel":"C01234ABCDE"' in body
        assert b'"text":"Deployed v2.1"' in body
        # Defaults: unfurl_links + unfurl_media should be true
        assert b'"unfurl_links":true' in body
        assert b'"unfurl_media":true' in body


# ---------------------------------------------------------------------------
# 2. Error mapping — vendor responses → typed exceptions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ratelimited_response_raises_rate_limit_error(slack: Slack) -> None:
    """Slack returns HTTP 200 with {"ok": false, "error": "ratelimited"}.

    Connector must translate this to our RateLimitError with the
    Retry-After value extracted from the response header.
    """
    with respx.mock(base_url="https://slack.com/api") as respx_mock:
        respx_mock.post("/chat.postMessage").mock(
            return_value=httpx.Response(
                200,
                json={"ok": False, "error": "ratelimited"},
                headers={"Retry-After": "42"},
            )
        )

        with pytest.raises(RateLimitError) as exc_info:
            await slack.asend_message(channel="C123", text="hi")

        err = exc_info.value
        assert err.connector == "slack"
        assert err.action == "chat.postMessage"
        assert err.retry_after_seconds == 42.0


@pytest.mark.asyncio
async def test_not_found_response_raises_not_found_error(slack: Slack) -> None:
    """channel_not_found, user_not_found, etc. → NotFoundError."""
    with respx.mock(base_url="https://slack.com/api") as respx_mock:
        respx_mock.post("/chat.postMessage").mock(
            return_value=httpx.Response(200, json={"ok": False, "error": "channel_not_found"})
        )

        with pytest.raises(NotFoundError) as exc_info:
            await slack.asend_message(channel="C_DOES_NOT_EXIST", text="hi")

        assert exc_info.value.connector == "slack"
        assert exc_info.value.details["slack_error"] == "channel_not_found"


@pytest.mark.asyncio
async def test_generic_error_raises_api_error(slack: Slack) -> None:
    """Unrecognised slack errors fall through to APIError."""
    with respx.mock(base_url="https://slack.com/api") as respx_mock:
        respx_mock.post("/chat.postMessage").mock(
            return_value=httpx.Response(200, json={"ok": False, "error": "invalid_auth"})
        )

        with pytest.raises(APIError) as exc_info:
            await slack.asend_message(channel="C123", text="hi")

        # invalid_auth isn't in the not-found / ratelimit lists, so it
        # bubbles up as a generic APIError with details preserved.
        assert exc_info.value.details["slack_error"] == "invalid_auth"


# ---------------------------------------------------------------------------
# 3. Pagination — cursor flows through PageState
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_channels_pagination(slack: Slack) -> None:
    """list_channels uses Slack's response_metadata.next_cursor pattern.

    First page returns next_cursor → has_more=True + cursor populated.
    Second page returns next_cursor="" → has_more=False + cursor=None.
    """
    page1 = {
        "ok": True,
        "channels": [
            {"id": "C001", "name": "general", "is_archived": False, "num_members": 5},
            {"id": "C002", "name": "random", "is_archived": False, "num_members": 3},
        ],
        "response_metadata": {"next_cursor": "dXNlcjpVMDYxTkZUVDI="},
    }
    page2 = {
        "ok": True,
        "channels": [
            {"id": "C003", "name": "dev", "is_archived": False, "num_members": 8},
        ],
        "response_metadata": {"next_cursor": ""},
    }

    with respx.mock(base_url="https://slack.com/api") as respx_mock:
        # Slack's conversations.list uses GET with query-string params.
        # (Some endpoints use POST + JSON body; this one doesn't.)
        respx_mock.get("/conversations.list").mock(
            side_effect=[
                httpx.Response(200, json=page1),
                httpx.Response(200, json=page2),
            ]
        )

        # First page
        result1 = await slack.alist_channels()
        assert len(result1.items) == 2
        assert result1.items[0].name == "general"
        assert result1.page_state.has_more is True
        assert result1.page_state.cursor == "dXNlcjpVMDYxTkZUVDI="

        # Second page using the returned cursor
        result2 = await slack.alist_channels(cursor=result1.page_state.cursor)
        assert len(result2.items) == 1
        assert result2.items[0].name == "dev"
        assert result2.page_state.has_more is False
        assert result2.page_state.cursor is None


# ---------------------------------------------------------------------------
# 4. Spec metadata — dangerous flag is correctly declared
# ---------------------------------------------------------------------------


def test_dangerous_actions_are_flagged() -> None:
    """send_message + delete_message should both be dangerous=True.

    This guards against an accidental edit that drops the flag — which
    would auto-expose the action to AI agents under the default
    `exclude_dangerous=True` ToolKit config.
    """
    spec = Slack.get_spec()
    assert spec.actions["send_message"].dangerous is True
    assert spec.actions["delete_message"].dangerous is True
    # And read-only actions should NOT be dangerous
    assert spec.actions["list_channels"].dangerous is False
    assert spec.actions["get_channel"].dangerous is False
