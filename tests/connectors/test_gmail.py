"""End-to-end tests for the Gmail connector using respx.

Focus: the multipart/alternative + attachments + custom-headers flow in
`send_email`, `create_draft`, and `update_draft`. These are the most
complex actions in the connector because they construct a full RFC 2822
message; every other action is a straightforward JSON passthrough.

Same respx pattern as tests/connectors/test_slack.py / test_github.py
/ test_openai.py — see CONTRIBUTING.md "Step 7: Write per-connector
tests" for the playbook.
"""

from __future__ import annotations

import base64
from email import message_from_bytes
from email.message import Message

import httpx
import pytest
import pytest_asyncio
import respx

from toolsconnector.connectors.gmail import Gmail
from toolsconnector.errors import InvalidCredentialsError

# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def gmail() -> Gmail:
    """Gmail connector with a fake OAuth token.

    Token never reaches gmail.googleapis.com because respx intercepts
    at the httpx transport layer.
    """
    connector = Gmail(credentials="ya29.fake-oauth-token")
    await connector._setup()
    yield connector
    await connector._teardown()


def _captured_raw_to_message(route: respx.routes.Route) -> Message:
    """Extract and decode the MIME message from a captured send request.

    Gmail expects ``{"raw": "<base64url>"}`` as the request body. This
    helper decodes it back to an email.message.Message so assertions
    can walk the parts.
    """
    import json as _json

    body = _json.loads(route.calls.last.request.read())
    # send_email posts {"raw": "..."}; create_draft posts {"message": {"raw": "..."}}
    raw_b64url = body.get("raw") or body["message"]["raw"]
    raw_bytes = base64.urlsafe_b64decode(raw_b64url)
    return message_from_bytes(raw_bytes)


# ---------------------------------------------------------------------------
# 1. Plain-text email (simplest path)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_plain_text(gmail: Gmail) -> None:
    """body is plain text + no html_body → single text/plain part.

    No multipart wrapper needed because there's only one body and no
    attachments.
    """
    with respx.mock(base_url="https://gmail.googleapis.com/gmail/v1") as respx_mock:
        route = respx_mock.post("/users/me/messages/send").mock(
            return_value=httpx.Response(200, json={"id": "msg-001", "threadId": "thread-001"})
        )

        result = await gmail.asend_email(
            to="recipient@example.com",
            subject="Plain test",
            body="Hello in plain text.",
        )
        assert result.id == "msg-001"
        assert result.thread_id == "thread-001"

        msg = _captured_raw_to_message(route)
        assert msg["To"] == "recipient@example.com"
        assert msg["Subject"] == "Plain test"
        # Single-part, text/plain only
        assert msg.get_content_type() == "text/plain"
        assert msg.is_multipart() is False
        assert "Hello in plain text." in msg.get_payload(decode=True).decode("utf-8")


# ---------------------------------------------------------------------------
# 2. HTML + auto-derived plain-text fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_html_with_auto_text_fallback(gmail: Gmail) -> None:
    """Passing only html_body produces multipart/alternative with both
    parts. The plain-text part is auto-derived from the HTML.
    """
    html = "<html><body><h1>Hello</h1><p>With <b>bold</b> text.</p></body></html>"

    with respx.mock(base_url="https://gmail.googleapis.com/gmail/v1") as respx_mock:
        route = respx_mock.post("/users/me/messages/send").mock(
            return_value=httpx.Response(200, json={"id": "msg-002", "threadId": "t-002"})
        )

        # body can be any short plain summary; html_body carries the real content
        await gmail.asend_email(
            to="recipient@example.com",
            subject="HTML test",
            body="(HTML summary fallback)",
            html_body=html,
        )

        msg = _captured_raw_to_message(route)
        # We passed BOTH body (plain text) and html_body, so the message
        # is multipart/alternative with both variants present.
        assert msg.is_multipart() is True
        assert msg.get_content_type() == "multipart/alternative"

        parts = msg.get_payload()
        assert len(parts) == 2
        content_types = {p.get_content_type() for p in parts}
        assert content_types == {"text/plain", "text/html"}

        # HTML part contains our tags verbatim
        html_part = next(p for p in parts if p.get_content_type() == "text/html")
        assert "<h1>Hello</h1>" in html_part.get_payload(decode=True).decode("utf-8")

        # Plain-text part is our explicit body (NOT auto-derived, because
        # we passed `body` explicitly)
        text_part = next(p for p in parts if p.get_content_type() == "text/plain")
        assert "(HTML summary fallback)" in text_part.get_payload(decode=True).decode("utf-8")


@pytest.mark.asyncio
async def test_send_html_auto_derives_text_when_body_is_html(gmail: Gmail) -> None:
    """Backward-compat path: passing HTML in `body` with no `html_body`
    auto-routes. The connector logs a debug message and treats body as
    HTML + generates a plain-text fallback via html_to_text.
    """
    html_in_body = "<html><body><h1>Old-style</h1><p>HTML directly in body param.</p></body></html>"

    with respx.mock(base_url="https://gmail.googleapis.com/gmail/v1") as respx_mock:
        route = respx_mock.post("/users/me/messages/send").mock(
            return_value=httpx.Response(200, json={"id": "msg-003", "threadId": "t-003"})
        )

        await gmail.asend_email(
            to="recipient@example.com",
            subject="Backward-compat",
            body=html_in_body,
            # no html_body — should auto-detect
        )

        msg = _captured_raw_to_message(route)
        # Still multipart/alternative (both parts present)
        assert msg.get_content_type() == "multipart/alternative"
        parts = msg.get_payload()
        assert {p.get_content_type() for p in parts} == {"text/plain", "text/html"}

        # HTML part is the original html_in_body
        html_part = next(p for p in parts if p.get_content_type() == "text/html")
        assert "Old-style" in html_part.get_payload(decode=True).decode("utf-8")

        # Plain-text part is auto-derived — should NOT contain tags
        text_part = next(p for p in parts if p.get_content_type() == "text/plain")
        text_content = text_part.get_payload(decode=True).decode("utf-8")
        assert "<h1>" not in text_content
        assert "<p>" not in text_content
        assert "Old-style" in text_content
        assert "HTML directly in body param." in text_content


# ---------------------------------------------------------------------------
# 3. Attachments
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_with_single_attachment(gmail: Gmail) -> None:
    """An attachment wraps the body in multipart/mixed."""
    pdf_bytes = b"%PDF-1.4\nfake pdf content for test\n"
    pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")

    with respx.mock(base_url="https://gmail.googleapis.com/gmail/v1") as respx_mock:
        route = respx_mock.post("/users/me/messages/send").mock(
            return_value=httpx.Response(200, json={"id": "msg-004", "threadId": "t-004"})
        )

        await gmail.asend_email(
            to="recipient@example.com",
            subject="With attachment",
            body="See attached report.",
            attachments=[{"filename": "report.pdf", "content": pdf_b64}],
        )

        msg = _captured_raw_to_message(route)
        assert msg.get_content_type() == "multipart/mixed"
        parts = msg.get_payload()
        assert len(parts) == 2  # body + attachment

        # Body part is text/plain (no html_body was given)
        body_part = parts[0]
        assert body_part.get_content_type() == "text/plain"

        # Attachment part is application/pdf (inferred from filename)
        att_part = parts[1]
        assert att_part.get_content_type() == "application/pdf"
        assert att_part.get_filename() == "report.pdf"
        assert att_part.get_payload(decode=True) == pdf_bytes


@pytest.mark.asyncio
async def test_send_with_attachment_and_explicit_content_type(gmail: Gmail) -> None:
    """Caller-provided content_type overrides the filename-inferred type."""
    content = base64.b64encode(b"line1,line2\nA,B\n").decode("ascii")

    with respx.mock(base_url="https://gmail.googleapis.com/gmail/v1") as respx_mock:
        route = respx_mock.post("/users/me/messages/send").mock(
            return_value=httpx.Response(200, json={"id": "m", "threadId": "t"})
        )

        await gmail.asend_email(
            to="x@y.com",
            subject="CSV",
            body="Data attached",
            attachments=[
                {
                    "filename": "data.csv",
                    "content": content,
                    "content_type": "text/csv",  # explicit override
                }
            ],
        )

        msg = _captured_raw_to_message(route)
        att = msg.get_payload()[1]
        assert att.get_content_type() == "text/csv"


@pytest.mark.asyncio
async def test_send_attachment_invalid_base64_raises_clearly(gmail: Gmail) -> None:
    """Bad base64 content should fail with a helpful ValueError, not
    after the HTTP request has gone out (which would leak server load).
    """
    # No mock needed here — the ValueError fires during MIME build,
    # before any HTTP request. Disable assert_all_called so an unused
    # route doesn't fail the teardown.
    with respx.mock(
        base_url="https://gmail.googleapis.com/gmail/v1", assert_all_called=False
    ) as respx_mock:
        respx_mock.post("/users/me/messages/send").mock(return_value=httpx.Response(200, json={}))

        with pytest.raises(ValueError, match="not valid base64"):
            await gmail.asend_email(
                to="x@y.com",
                subject="Bad attachment",
                body="test",
                attachments=[{"filename": "bad.bin", "content": "not-valid-base64!!!"}],
            )


# ---------------------------------------------------------------------------
# 4. Custom headers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_with_custom_headers(gmail: Gmail) -> None:
    """Custom headers land on the top-level message verbatim."""
    with respx.mock(base_url="https://gmail.googleapis.com/gmail/v1") as respx_mock:
        route = respx_mock.post("/users/me/messages/send").mock(
            return_value=httpx.Response(200, json={"id": "m", "threadId": "t"})
        )

        await gmail.asend_email(
            to="x@y.com",
            subject="Threaded reply",
            body="Reply content",
            headers={
                "In-Reply-To": "<original-msg-id@example.com>",
                "References": "<original-msg-id@example.com>",
                "List-Unsubscribe": "<mailto:unsub@example.com>",
            },
        )

        msg = _captured_raw_to_message(route)
        assert msg["In-Reply-To"] == "<original-msg-id@example.com>"
        assert msg["References"] == "<original-msg-id@example.com>"
        assert msg["List-Unsubscribe"] == "<mailto:unsub@example.com>"


# ---------------------------------------------------------------------------
# 5. Authentication header
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auth_header_sent(gmail: Gmail) -> None:
    """Bearer token must be sent in Authorization header on every request."""
    with respx.mock(base_url="https://gmail.googleapis.com/gmail/v1") as respx_mock:
        route = respx_mock.post("/users/me/messages/send").mock(
            return_value=httpx.Response(200, json={"id": "m", "threadId": "t"})
        )

        await gmail.asend_email(to="x@y.com", subject="Auth test", body="test")

        assert route.calls.last.request.headers["authorization"] == "Bearer ya29.fake-oauth-token"


# ---------------------------------------------------------------------------
# 6. Error mapping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_401_unauthorized_raises_invalid_credentials_error(gmail: Gmail) -> None:
    """Invalid token → 401 → typed :class:`InvalidCredentialsError`
    (was bare ``httpx.HTTPStatusError`` pre-0.3.5).

    Gmail's "Request had invalid authentication credentials" body
    doesn't contain an "expired" marker, so the helper picks
    ``InvalidCredentialsError`` rather than ``TokenExpiredError`` —
    correct because invalid-format tokens trigger this even when not
    expired. Tokens that ARE expired return Google's
    ``"invalid_grant"`` body in OAuth flows, not 401 on the API.
    """
    with respx.mock(base_url="https://gmail.googleapis.com/gmail/v1") as respx_mock:
        respx_mock.post("/users/me/messages/send").mock(
            return_value=httpx.Response(
                401,
                json={
                    "error": {
                        "code": 401,
                        "message": "Request had invalid authentication credentials.",
                    }
                },
            )
        )

        with pytest.raises(InvalidCredentialsError) as exc:
            await gmail.asend_email(to="x@y.com", subject="x", body="x")

        assert exc.value.connector == "gmail"
        assert exc.value.upstream_status == 401


# ---------------------------------------------------------------------------
# 7. Spec metadata
# ---------------------------------------------------------------------------


def test_send_email_is_flagged_dangerous() -> None:
    """Sending an email is a write action — must be dangerous=True so
    exclude_dangerous=True ToolKits don't expose it to agents by default.
    """
    spec = Gmail.get_spec()
    assert spec.actions["send_email"].dangerous is True
    # create_draft writes state but is recoverable (draft, not sent) —
    # still dangerous=False in the current spec. Keep it that way:
    assert spec.actions["create_draft"].dangerous is False
    # Read actions are not dangerous
    assert spec.actions["list_emails"].dangerous is False


def test_send_email_has_new_multipart_params() -> None:
    """Regression guard: after the 0.3.5 multipart refactor, these
    param names must exist on send_email. If a future refactor drops
    them, this test fails loudly.
    """
    props = Gmail.get_spec().actions["send_email"].input_schema["properties"]
    for expected in ("to", "subject", "body", "html_body", "attachments", "headers"):
        assert expected in props, f"send_email is missing parameter `{expected}`"

    # Only to/subject/body should be required — everything else optional
    required = Gmail.get_spec().actions["send_email"].input_schema["required"]
    assert set(required) == {"to", "subject", "body"}


# ---------------------------------------------------------------------------
# 8. Settings — Filters (smoke test: URL + body shape + parsing)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_filter_sends_correct_payload(gmail: Gmail) -> None:
    """create_filter: criteria + action serialize to the snake→camel
    shape Gmail expects (e.g. `from` not `from_address`).
    """
    from toolsconnector.connectors.gmail.types import FilterAction, FilterCriteria

    with respx.mock(base_url="https://gmail.googleapis.com/gmail/v1") as respx_mock:
        route = respx_mock.post("/users/me/settings/filters").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "filter-123",
                    "criteria": {"from": "boss@example.com", "hasAttachment": True},
                    "action": {"addLabelIds": ["IMPORTANT"]},
                },
            )
        )

        result = await gmail.acreate_filter(
            criteria=FilterCriteria(from_address="boss@example.com", has_attachment=True),
            action=FilterAction(add_label_ids=["IMPORTANT"]),
        )

        assert result.id == "filter-123"
        assert result.criteria.from_address == "boss@example.com"
        assert result.action.add_label_ids == ["IMPORTANT"]

        body = route.calls.last.request.read()
        # Critical: API expects `from`, not `from_address` or `fromAddress`
        assert b'"from":"boss@example.com"' in body
        assert b'"hasAttachment":true' in body
        assert b'"addLabelIds":["IMPORTANT"]' in body


# ---------------------------------------------------------------------------
# 9. Settings — SendAs (URL + parsing)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_send_as(gmail: Gmail) -> None:
    """list_send_as: GET /settings/sendAs → list[SendAs]."""
    with respx.mock(base_url="https://gmail.googleapis.com/gmail/v1") as respx_mock:
        respx_mock.get("/users/me/settings/sendAs").mock(
            return_value=httpx.Response(
                200,
                json={
                    "sendAs": [
                        {
                            "sendAsEmail": "primary@example.com",
                            "displayName": "Sachin",
                            "isPrimary": True,
                            "isDefault": True,
                            "verificationStatus": "accepted",
                        },
                        {
                            "sendAsEmail": "alias@example.com",
                            "displayName": "Sachin (alias)",
                            "verificationStatus": "pending",
                        },
                    ]
                },
            )
        )

        result = await gmail.alist_send_as()
        assert len(result) == 2
        assert result[0].is_primary is True
        assert result[1].verification_status == "pending"


# ---------------------------------------------------------------------------
# 10. Settings — AutoForwarding (PUT body shape)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_auto_forwarding_disabled(gmail: Gmail) -> None:
    """update_auto_forwarding(enabled=False): only sends `enabled`,
    not `emailAddress` or `disposition` (None values omitted).
    """
    with respx.mock(base_url="https://gmail.googleapis.com/gmail/v1") as respx_mock:
        route = respx_mock.put("/users/me/settings/autoForwarding").mock(
            return_value=httpx.Response(200, json={"enabled": False})
        )

        result = await gmail.aupdate_auto_forwarding(enabled=False)
        assert result.enabled is False
        body = route.calls.last.request.read()
        assert b'"enabled":false' in body
        assert b"emailAddress" not in body
        assert b"disposition" not in body


# ---------------------------------------------------------------------------
# 11. Push notifications — watch URL + body
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_watch_sends_topic_name(gmail: Gmail) -> None:
    """watch: POST /watch with topicName (and optional labelIds)."""
    with respx.mock(base_url="https://gmail.googleapis.com/gmail/v1") as respx_mock:
        route = respx_mock.post("/users/me/watch").mock(
            return_value=httpx.Response(
                200, json={"historyId": "12345", "expiration": "1700000000000"}
            )
        )

        result = await gmail.awatch(
            topic_name="projects/my-proj/topics/gmail-notifs",
            label_ids=["INBOX"],
            label_filter_behavior="include",
        )
        assert result["historyId"] == "12345"

        body = route.calls.last.request.read()
        assert b'"topicName":"projects/my-proj/topics/gmail-notifs"' in body
        assert b'"labelIds":["INBOX"]' in body
        assert b'"labelFilterBehavior":"include"' in body


# ---------------------------------------------------------------------------
# 12. Settings completeness — every new action is in the spec
# ---------------------------------------------------------------------------


def test_settings_completeness() -> None:
    """Regression guard: the 28 settings/push actions added in 0.3.5 all
    show up in the spec. If a future refactor removes one, this fires.
    """
    expected = {
        # Filters
        "list_filters",
        "get_filter",
        "create_filter",
        "delete_filter",
        # SendAs
        "list_send_as",
        "get_send_as",
        "create_send_as",
        "update_send_as",
        "delete_send_as",
        "verify_send_as",
        # Delegates
        "list_delegates",
        "get_delegate",
        "create_delegate",
        "delete_delegate",
        # ForwardingAddresses
        "list_forwarding_addresses",
        "get_forwarding_address",
        "create_forwarding_address",
        "delete_forwarding_address",
        # AutoForwarding / IMAP / POP / Language
        "get_auto_forwarding",
        "update_auto_forwarding",
        "get_imap_settings",
        "update_imap_settings",
        "get_pop_settings",
        "update_pop_settings",
        "get_language",
        "update_language",
        # Push
        "watch",
        "stop",
    }
    actions = set(Gmail.get_spec().actions.keys())
    missing = expected - actions
    assert not missing, f"Spec is missing settings actions: {sorted(missing)}"


def test_dangerous_flags_on_settings_actions() -> None:
    """Sanity: write/delete settings actions must carry dangerous=True.

    `exclude_dangerous=True` ToolKits should never accidentally let an
    agent delete the user's filters or remove a delegate.
    """
    spec = Gmail.get_spec()
    must_be_dangerous = [
        "create_filter",
        "delete_filter",
        "create_send_as",
        "delete_send_as",
        "create_delegate",
        "delete_delegate",
        "create_forwarding_address",
        "delete_forwarding_address",
        "update_auto_forwarding",
        "update_imap_settings",
        "update_pop_settings",
        "watch",
    ]
    for name in must_be_dangerous:
        assert spec.actions[name].dangerous is True, (
            f"{name} should be dangerous=True (modifies account settings)"
        )

    must_be_safe = [
        "list_filters",
        "get_filter",
        "list_send_as",
        "get_send_as",
        "verify_send_as",
        "list_delegates",
        "get_delegate",
        "list_forwarding_addresses",
        "get_forwarding_address",
        "get_auto_forwarding",
        "get_imap_settings",
        "get_pop_settings",
        "get_language",
        "update_language",
        "stop",
    ]
    for name in must_be_safe:
        assert spec.actions[name].dangerous is False, (
            f"{name} should be dangerous=False (read-only or low-impact)"
        )


# ---------------------------------------------------------------------------
# 13. HTML-to-text helper
# ---------------------------------------------------------------------------


def test_html_to_text_helper() -> None:
    """Unit test for the auto-fallback text generator. The quality of
    the fallback affects every HTML-only email we send, so we assert
    specific properties:

      - Tags are stripped
      - Block-level elements produce line breaks
      - Entities are unescaped
      - script/style blocks are skipped entirely
    """
    from toolsconnector.connectors.gmail._helpers import html_to_text

    html = """
    <html>
      <head><style>body { color: red; }</style></head>
      <body>
        <h1>Hello &amp; welcome</h1>
        <p>First paragraph.</p>
        <p>Second with a <a href="http://x">link</a>.</p>
        <script>alert('skipped');</script>
        <div>In a div</div>
      </body>
    </html>
    """

    text = html_to_text(html)

    # No tags remain
    assert "<" not in text
    # Entities unescaped
    assert "Hello & welcome" in text
    # Block elements produced line breaks
    assert "First paragraph." in text
    assert "Second with a link" in text
    # Script content is skipped
    assert "alert" not in text
    # Style content is skipped
    assert "color: red" not in text
