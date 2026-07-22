"""Tests for the WhatsApp Business (Cloud API) connector.

Envelopes are pinned to the wire shapes verified against official Meta
docs on 2026-07-22 (.agent/artifacts/whatsapp-wire-register.md) and
live-verified 2026-07-22/23 against a real test WABA (Tier 1,
contract-scoped: 18/25 actions round-tripped, all 11 message types
device-confirmed).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any

import httpx
import pytest
import pytest_asyncio
import respx

from toolsconnector.connectors.whatsapp_business import (
    WhatsAppBusiness,
    handle_verification,
    parse_events,
    verify_signature,
)
from toolsconnector.errors import (
    APIError,
    InvalidCredentialsError,
    MissingConfigError,
    RateLimitError,
    ServerError,
    ValidationError,
)
from toolsconnector.errors import ConnectionError as TCConnectionError
from toolsconnector.spec.connector import ConnectorCategory, ProtocolType

BASE = "https://graph.facebook.com/v25.0"
TOKEN = "fake-whatsapp-system-user-token"
PHONE_ID = "111111111111111"
WABA_ID = "222222222222222"
APP_SECRET = "fake-app-secret"

CREDS = {
    "access_token": TOKEN,
    "phone_number_id": PHONE_ID,
    "waba_id": WABA_ID,
    "app_secret": APP_SECRET,
}

SEND_ENVELOPE = {
    "messaging_product": "whatsapp",
    "contacts": [{"input": "+15550001111", "wa_id": "15550001111"}],
    "messages": [{"id": "wamid.HBgLMTU1NTAwMDExMTEVAgARGBI5", "message_status": "accepted"}],
}


def json_body(route: respx.Route) -> dict[str, Any]:
    return json.loads(route.calls.last.request.content)


@pytest_asyncio.fixture
async def wa() -> WhatsAppBusiness:
    connector = WhatsAppBusiness(credentials=CREDS)
    await connector._setup()
    yield connector
    await connector._teardown()


# ---------------------------------------------------------------------------
# Credential parsing
# ---------------------------------------------------------------------------


def test_credentials_accept_json_string() -> None:
    connector = WhatsAppBusiness(credentials=json.dumps(CREDS))
    assert connector._creds.access_token == TOKEN
    assert connector._creds.phone_number_id == PHONE_ID


def test_credentials_bare_token_allowed_but_phone_actions_fail() -> None:
    connector = WhatsAppBusiness(credentials=TOKEN)
    assert connector._creds.access_token == TOKEN
    with pytest.raises(MissingConfigError):
        connector._phone_path()


@pytest.mark.asyncio
async def test_missing_token_instantiates_but_fails_at_setup() -> None:
    # Repo contract: connectors instantiate without credentials;
    # the token requirement surfaces at first use.
    connector = WhatsAppBusiness(credentials={"phone_number_id": PHONE_ID})
    with pytest.raises(MissingConfigError):
        await connector._setup()


# ---------------------------------------------------------------------------
# Sends
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_text_pins_body_and_auth_header(wa: WhatsAppBusiness) -> None:
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        route = mock.post(f"/{PHONE_ID}/messages").mock(
            return_value=httpx.Response(200, json=SEND_ENVELOPE)
        )
        result = await wa.asend_text(
            "15550001111",
            "hello world",
            preview_url=True,
            reply_to="wamid.PREV",
            tracking_data="order-42",
        )
    request = route.calls.last.request
    assert request.headers["authorization"] == f"Bearer {TOKEN}"
    assert json_body(route) == {
        "messaging_product": "whatsapp",
        "to": "15550001111",
        "type": "text",
        "text": {"body": "hello world", "preview_url": True},
        "context": {"message_id": "wamid.PREV"},
        "biz_opaque_callback_data": "order-42",
    }
    assert result.message_id == "wamid.HBgLMTU1NTAwMDExMTEVAgARGBI5"
    assert result.contacts[0].wa_id == "15550001111"


@pytest.mark.asyncio
async def test_send_text_rejects_oversized_body(wa: WhatsAppBusiness) -> None:
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        route = mock.post(f"/{PHONE_ID}/messages")
        with pytest.raises(ValidationError):
            await wa.asend_text("15550001111", "x" * 4097)
    assert not route.called


@pytest.mark.asyncio
async def test_send_image_requires_exactly_one_source(wa: WhatsAppBusiness) -> None:
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        route = mock.post(f"/{PHONE_ID}/messages")
        with pytest.raises(ValidationError):
            await wa.asend_image("15550001111")
        with pytest.raises(ValidationError):
            await wa.asend_image("15550001111", image_id="123", image_url="https://x.test/i.jpg")
    assert not route.called


@pytest.mark.asyncio
async def test_send_document_payload(wa: WhatsAppBusiness) -> None:
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        route = mock.post(f"/{PHONE_ID}/messages").mock(
            return_value=httpx.Response(200, json=SEND_ENVELOPE)
        )
        await wa.asend_document(
            "15550001111",
            document_id="media-9",
            caption="Invoice",
            filename="invoice.pdf",
        )
    assert json_body(route)["document"] == {
        "id": "media-9",
        "caption": "Invoice",
        "filename": "invoice.pdf",
    }


@pytest.mark.asyncio
async def test_send_reaction_payload(wa: WhatsAppBusiness) -> None:
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        route = mock.post(f"/{PHONE_ID}/messages").mock(
            return_value=httpx.Response(200, json=SEND_ENVELOPE)
        )
        await wa.asend_reaction("15550001111", "wamid.TARGET", "\U0001f44d")
    body = json_body(route)
    assert body["type"] == "reaction"
    assert body["reaction"] == {"message_id": "wamid.TARGET", "emoji": "\U0001f44d"}


@pytest.mark.asyncio
async def test_send_template_payload(wa: WhatsAppBusiness) -> None:
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        route = mock.post(f"/{PHONE_ID}/messages").mock(
            return_value=httpx.Response(200, json=SEND_ENVELOPE)
        )
        await wa.asend_template(
            "15550001111",
            "order_update",
            language_code="en",
            components=[
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": "Ada"}],
                }
            ],
        )
    assert json_body(route)["template"] == {
        "name": "order_update",
        "language": {"code": "en"},
        "components": [{"type": "body", "parameters": [{"type": "text", "text": "Ada"}]}],
    }


@pytest.mark.asyncio
async def test_interactive_buttons_payload_and_cap(wa: WhatsAppBusiness) -> None:
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        route = mock.post(f"/{PHONE_ID}/messages").mock(
            return_value=httpx.Response(200, json=SEND_ENVELOPE)
        )
        await wa.asend_interactive_buttons(
            "15550001111",
            "Pick one",
            [{"id": "yes", "title": "Yes"}, {"id": "no", "title": "No"}],
            footer_text="Powered by TC",
        )
    interactive = json_body(route)["interactive"]
    assert interactive["type"] == "button"
    assert interactive["action"]["buttons"][0] == {
        "type": "reply",
        "reply": {"id": "yes", "title": "Yes"},
    }
    assert interactive["footer"] == {"text": "Powered by TC"}

    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        route = mock.post(f"/{PHONE_ID}/messages")
        with pytest.raises(ValidationError):
            await wa.asend_interactive_buttons(
                "15550001111",
                "Too many",
                [{"id": str(i), "title": str(i)} for i in range(4)],
            )
    assert not route.called


@pytest.mark.asyncio
async def test_interactive_list_row_cap(wa: WhatsAppBusiness) -> None:
    sections = [
        {
            "title": "S1",
            "rows": [{"id": str(i), "title": f"Row {i}"} for i in range(11)],
        }
    ]
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        route = mock.post(f"/{PHONE_ID}/messages")
        with pytest.raises(ValidationError):
            await wa.asend_interactive_list("15550001111", "Menu", "Open", sections)
    assert not route.called


@pytest.mark.asyncio
async def test_send_raw_interactive_needs_type(wa: WhatsAppBusiness) -> None:
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        route = mock.post(f"/{PHONE_ID}/messages")
        with pytest.raises(ValidationError):
            await wa.asend_interactive("15550001111", {"body": {"text": "x"}})
    assert not route.called


@pytest.mark.asyncio
async def test_mark_as_read_and_typing_payloads(wa: WhatsAppBusiness) -> None:
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        route = mock.post(f"/{PHONE_ID}/messages").mock(
            return_value=httpx.Response(200, json={"success": True})
        )
        res = await wa.amark_as_read("wamid.IN")
        assert res.success is True
        assert json_body(route) == {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": "wamid.IN",
        }
        await wa.asend_typing_indicator("wamid.IN")
        assert json_body(route)["typing_indicator"] == {"type": "text"}


# ---------------------------------------------------------------------------
# Media
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_media_multipart(wa: WhatsAppBusiness) -> None:
    blob = b"\x89PNG fake"
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        route = mock.post(f"/{PHONE_ID}/media").mock(
            return_value=httpx.Response(200, json={"id": "media-123"})
        )
        result = await wa.aupload_media(
            base64.b64encode(blob).decode(), "image/png", filename="pixel.png"
        )
    assert result.id == "media-123"
    request = route.calls.last.request
    assert request.headers["content-type"].startswith("multipart/form-data")
    assert b"messaging_product" in request.content
    assert b"pixel.png" in request.content


@pytest.mark.asyncio
async def test_upload_media_rejects_bad_base64(wa: WhatsAppBusiness) -> None:
    with pytest.raises(ValidationError):
        await wa.aupload_media("not-base64!!!", "image/png")


@pytest.mark.asyncio
async def test_download_media_two_step(wa: WhatsAppBusiness) -> None:
    lookaside = "https://lookaside.fbsbx.com/whatsapp_business/attachments/m1"
    blob = b"media-bytes"
    with respx.mock(assert_all_called=True) as mock:
        mock.get(f"{BASE}/media-1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "media-1",
                    "url": lookaside,
                    "mime_type": "audio/ogg",
                    "sha256": "abc123",
                    "file_size": len(blob),
                    "messaging_product": "whatsapp",
                },
            )
        )
        mock.get(lookaside).mock(return_value=httpx.Response(200, content=blob))
        result = await wa.adownload_media("media-1")
    assert base64.b64decode(result.content_base64) == blob
    assert result.mime_type == "audio/ogg"
    assert result.byte_size == len(blob)


@pytest.mark.asyncio
async def test_delete_media(wa: WhatsAppBusiness) -> None:
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        mock.delete("/media-1").mock(return_value=httpx.Response(200, json={"success": True}))
        result = await wa.adelete_media("media-1")
    assert result.success is True


# ---------------------------------------------------------------------------
# Profile + phone numbers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_business_profile_unwraps_data(wa: WhatsAppBusiness) -> None:
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        mock.get(f"/{PHONE_ID}/whatsapp_business_profile").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "about": "We ship fast",
                            "email": "hi@shop.test",
                            "websites": ["https://shop.test"],
                            "vertical": "RETAIL",
                            "messaging_product": "whatsapp",
                        }
                    ]
                },
            )
        )
        profile = await wa.aget_business_profile()
    assert profile.about == "We ship fast"
    assert profile.websites == ["https://shop.test"]


@pytest.mark.asyncio
async def test_update_business_profile_requires_a_field(
    wa: WhatsAppBusiness,
) -> None:
    with pytest.raises(ValidationError):
        await wa.aupdate_business_profile()


@pytest.mark.asyncio
async def test_get_phone_number(wa: WhatsAppBusiness) -> None:
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        mock.get(f"/{PHONE_ID}").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": PHONE_ID,
                    "display_phone_number": "+1 555-000-1111",
                    "verified_name": "Test Shop",
                    "quality_rating": "GREEN",
                    "throughput": {"level": "STANDARD"},
                    "whatsapp_business_manager_messaging_limit": "TIER_250",
                },
            )
        )
        number = await wa.aget_phone_number()
    assert number.quality_rating == "GREEN"
    assert number.throughput is not None
    assert number.throughput.level == "STANDARD"
    assert number.messaging_limit == "TIER_250"


@pytest.mark.asyncio
async def test_list_phone_numbers_cursor_walk(wa: WhatsAppBusiness) -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        after = httpx.QueryParams(request.url.query).get("after")
        if after is None:
            return httpx.Response(
                200,
                json={
                    "data": [{"id": "p1", "display_phone_number": "+1"}],
                    "paging": {
                        "cursors": {"before": "b1", "after": "c2"},
                        "next": "https://graph.facebook.com/next",
                    },
                },
            )
        assert after == "c2"
        return httpx.Response(
            200,
            json={
                "data": [{"id": "p2", "display_phone_number": "+2"}],
                "paging": {"cursors": {"before": "b2", "after": "c3"}},
            },
        )

    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        mock.get(f"/{WABA_ID}/phone_numbers").mock(side_effect=responder)
        page = await wa.alist_phone_numbers(limit=1)
        items = await page.collect()
    assert [n.id for n in items] == ["p1", "p2"]


# ---------------------------------------------------------------------------
# Error mapping (Graph puts the real code in the 400 body)
# ---------------------------------------------------------------------------


def _graph_error(status: int, code: int, message: str = "boom") -> httpx.Response:
    return httpx.Response(
        status,
        json={
            "error": {
                "message": message,
                "type": "OAuthException",
                "code": code,
                "fbtrace_id": "tr4ce",
            }
        },
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "code", "expected"),
    [
        (401, 190, InvalidCredentialsError),
        (400, 130429, RateLimitError),  # throughput
        (400, 131056, RateLimitError),  # pair rate limit
        (400, 133016, RateLimitError),  # registration limit
        (400, 100, ValidationError),
        (400, 130501, ValidationError),  # group-unsupported type
        (400, 131026, APIError),  # undeliverable
        (500, 131000, ServerError),
    ],
)
async def test_graph_error_mapping(
    wa: WhatsAppBusiness, status: int, code: int, expected: type[Exception]
) -> None:
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        mock.post(f"/{PHONE_ID}/messages").mock(return_value=_graph_error(status, code))
        with pytest.raises(expected) as excinfo:
            await wa.asend_text("15550001111", "hi")
    assert TOKEN not in str(excinfo.value)


@pytest.mark.asyncio
async def test_connect_error_maps_to_connection_error(
    wa: WhatsAppBusiness,
) -> None:
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        mock.post(f"/{PHONE_ID}/messages").mock(side_effect=httpx.ConnectError("boom"))
        with pytest.raises(TCConnectionError):
            await wa.asend_text("15550001111", "hi")


# ---------------------------------------------------------------------------
# Webhook primitives
# ---------------------------------------------------------------------------


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(APP_SECRET.encode(), body, hashlib.sha256).hexdigest()


def test_verify_signature_roundtrip() -> None:
    body = json.dumps({"object": "whatsapp_business_account"}).encode()
    assert verify_signature(body, _sign(body), APP_SECRET) is True
    assert verify_signature(body, "sha256=" + "0" * 64, APP_SECRET) is False
    assert verify_signature(body, None, APP_SECRET) is False
    with pytest.raises(ValidationError):
        verify_signature(body, _sign(body), "")


def test_handle_verification() -> None:
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": "my-token",
        "hub.challenge": "1158201444",
    }
    assert handle_verification(params, "my-token") == "1158201444"
    with pytest.raises(ValidationError):
        handle_verification(params, "other-token")
    with pytest.raises(ValidationError):
        handle_verification({"hub.mode": "unsubscribe"}, "my-token")


def _envelope(field: str, value: dict[str, Any]) -> dict[str, Any]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": WABA_ID,
                "time": 1748454394,
                "changes": [{"field": field, "value": value}],
            }
        ],
    }


_METADATA = {"display_phone_number": "+1 555", "phone_number_id": PHONE_ID}


def test_parse_events_text_message() -> None:
    value = {
        "messaging_product": "whatsapp",
        "metadata": _METADATA,
        "contacts": [{"profile": {"name": "Ada"}, "wa_id": "15550002222"}],
        "messages": [
            {
                "from": "15550002222",
                "id": "wamid.IN1",
                "timestamp": "1748454394",
                "type": "text",
                "text": {"body": "hi there"},
            }
        ],
    }
    [event] = parse_events(json.dumps(_envelope("messages", value)).encode())
    assert event.waba_id == WABA_ID
    assert event.field == "messages"
    assert event.phone_number_id == PHONE_ID
    message = event.messages_value.messages[0]
    assert message.from_ == "15550002222"
    assert message.text.body == "hi there"


@pytest.mark.parametrize(
    ("message", "check"),
    [
        (  # media with the new direct-download url field
            {
                "type": "image",
                "image": {
                    "id": "m1",
                    "mime_type": "image/jpeg",
                    "sha256": "s",
                    "caption": "pic",
                    "url": "https://cdn.test/m1",
                },
            },
            lambda m: m.image.url == "https://cdn.test/m1" and m.image.caption == "pic",
        ),
        (  # voice note flag
            {"type": "audio", "audio": {"id": "m2", "voice": True}},
            lambda m: m.audio.voice is True,
        ),
        (  # interactive button reply
            {
                "type": "interactive",
                "interactive": {
                    "type": "button_reply",
                    "button_reply": {"id": "yes", "title": "Yes"},
                },
            },
            lambda m: m.interactive.button_reply["id"] == "yes",
        ),
        (  # list reply
            {
                "type": "interactive",
                "interactive": {
                    "type": "list_reply",
                    "list_reply": {"id": "r1", "title": "Row", "description": "d"},
                },
            },
            lambda m: m.interactive.list_reply["title"] == "Row",
        ),
        (  # template quick-reply button tap
            {"type": "button", "button": {"payload": "STOP", "text": "Stop"}},
            lambda m: m.button.payload == "STOP",
        ),
        (  # catalog order
            {
                "type": "order",
                "order": {
                    "catalog_id": "c1",
                    "text": "note",
                    "product_items": [
                        {
                            "product_retailer_id": "sku-1",
                            "quantity": 2,
                            "item_price": 9.5,
                            "currency": "USD",
                        }
                    ],
                },
            },
            lambda m: m.order.product_items[0]["quantity"] == 2,
        ),
        (  # location share
            {
                "type": "location",
                "location": {
                    "latitude": 51.5,
                    "longitude": -0.1,
                    "name": "London",
                },
            },
            lambda m: m.location.latitude == 51.5,
        ),
        (  # reaction
            {
                "type": "reaction",
                "reaction": {
                    "message_id": "wamid.X",
                    "emoji": "\U0001f525",
                },
            },
            lambda m: m.reaction.message_id == "wamid.X",
        ),
        (  # system: user changed number
            {
                "type": "system",
                "system": {
                    "body": "changed",
                    "type": "user_changed_number",
                    "wa_id": "1555",
                    "new_wa_id": "1666",
                },
            },
            lambda m: m.system.new_wa_id == "1666",
        ),
        (  # CTWA ad referral + reply context
            {
                "type": "text",
                "text": {"body": "saw your ad"},
                "referral": {
                    "source_type": "ad",
                    "source_id": "ad-1",
                    "ctwa_clid": "clid-1",
                    "headline": "Sale",
                },
                "context": {"from": "1555", "id": "wamid.PREV"},
            },
            lambda m: m.referral.ctwa_clid == "clid-1" and m.context.id == "wamid.PREV",
        ),
        (  # unsupported type with nested errors
            {
                "type": "unsupported",
                "errors": [
                    {
                        "code": 131051,
                        "title": "Unsupported message type",
                        "message": "Unsupported message type",
                    }
                ],
            },
            lambda m: m.errors[0].code == 131051,
        ),
        (  # group message carries group_id
            {"type": "text", "text": {"body": "in group"}, "group_id": "Y2FwaV9ncm91cDox"},
            lambda m: m.group_id == "Y2FwaV9ncm91cDox",
        ),
    ],
)
def test_parse_events_message_taxonomy(message: dict[str, Any], check: Any) -> None:
    base = {"from": "15550002222", "id": "wamid.IN", "timestamp": "1", **message}
    value = {
        "messaging_product": "whatsapp",
        "metadata": _METADATA,
        "messages": [base],
    }
    [event] = parse_events(_envelope("messages", value))
    assert check(event.messages_value.messages[0])


def test_parse_events_status_with_pricing() -> None:
    value = {
        "messaging_product": "whatsapp",
        "metadata": _METADATA,
        "statuses": [
            {
                "id": "wamid.OUT1",
                "status": "delivered",
                "timestamp": "1748454400",
                "recipient_id": "15550002222",
                "biz_opaque_callback_data": "order-42",
                "pricing": {
                    "billable": True,
                    "pricing_model": "PMP",
                    "category": "utility",
                    "type": "regular",
                },
            }
        ],
    }
    [event] = parse_events(_envelope("messages", value))
    status = event.messages_value.statuses[0]
    assert status.status == "delivered"
    assert status.pricing.pricing_model == "PMP"
    assert status.biz_opaque_callback_data == "order-42"


def test_parse_events_failed_status_errors() -> None:
    value = {
        "messaging_product": "whatsapp",
        "metadata": _METADATA,
        "statuses": [
            {
                "id": "wamid.OUT2",
                "status": "failed",
                "timestamp": "2",
                "recipient_id": "1555",
                "errors": [{"code": 131047, "title": "Re-engagement message"}],
            }
        ],
    }
    [event] = parse_events(_envelope("messages", value))
    assert event.messages_value.statuses[0].errors[0].code == 131047


@pytest.mark.parametrize(
    "field",
    [
        "message_template_status_update",
        "smb_message_echoes",
        "calls",
        "group_lifecycle_update",
        "account_update",
        "user_preferences",
    ],
)
def test_parse_events_other_fields_kept_raw(field: str) -> None:
    value = {"some": "payload", "metadata": _METADATA}
    [event] = parse_events(_envelope(field, value))
    assert event.field == field
    assert event.messages_value is None
    assert event.raw_value == value
    assert event.phone_number_id == PHONE_ID


def test_parse_events_batched_entries() -> None:
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "w1",
                "time": 1,
                "changes": [
                    {"field": "messages", "value": {"messages": []}},
                    {"field": "account_update", "value": {"event": "DISABLED_UPDATE"}},
                ],
            },
            {
                "id": "w2",
                "time": 2,
                "changes": [
                    {"field": "messages", "value": {"messages": []}},
                ],
            },
        ],
    }
    events = parse_events(payload)
    assert [e.waba_id for e in events] == ["w1", "w1", "w2"]


def test_parse_events_rejects_garbage() -> None:
    with pytest.raises(ValidationError):
        parse_events(b"not json")
    with pytest.raises(ValidationError):
        parse_events({"object": "page", "entry": []})


# ---------------------------------------------------------------------------
# Spec governance
# ---------------------------------------------------------------------------


def test_spec_metadata() -> None:
    assert WhatsAppBusiness.name == "whatsapp_business"
    assert WhatsAppBusiness.protocol is ProtocolType.REST
    assert WhatsAppBusiness.category is ConnectorCategory.COMMUNICATION
    assert WhatsAppBusiness.verification_status == "live"
    assert len(WhatsAppBusiness.get_actions()) == 52


def test_registered_in_discovery() -> None:
    from toolsconnector.serve._discovery import _KNOWN_CONNECTORS

    assert (
        _KNOWN_CONNECTORS["whatsapp_business"]
        == "toolsconnector.connectors.whatsapp_business:WhatsAppBusiness"
    )


# ---------------------------------------------------------------------------
# Review-hardening regressions (W1 adversarial review + Whatomate cross-check)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_codeless_400_html_body_maps_to_validation(wa: WhatsAppBusiness) -> None:
    # Proxy/CDN error pages carry no Graph code — must NOT read as bad token.
    with respx.mock(base_url=BASE) as mock:
        mock.post(f"/{PHONE_ID}/messages").mock(
            return_value=httpx.Response(400, text="<html>Bad Request</html>")
        )
        with pytest.raises(ValidationError):
            await wa.asend_text("15550001111", "hi")


@pytest.mark.asyncio
async def test_codeless_graph_error_not_auth_even_if_expired_text(
    wa: WhatsAppBusiness,
) -> None:
    with respx.mock(base_url=BASE) as mock:
        mock.post(f"/{PHONE_ID}/messages").mock(
            return_value=httpx.Response(400, json={"error": {"message": "something expired maybe"}})
        )
        with pytest.raises(ValidationError):
            await wa.asend_text("15550001111", "hi")


@pytest.mark.asyncio
async def test_real_code_zero_on_401_still_auth_error(wa: WhatsAppBusiness) -> None:
    with respx.mock(base_url=BASE) as mock:
        mock.post(f"/{PHONE_ID}/messages").mock(return_value=_graph_error(401, 0, "AuthException"))
        with pytest.raises(InvalidCredentialsError):
            await wa.asend_text("15550001111", "hi")


@pytest.mark.asyncio
async def test_download_error_path_scrubs_token(wa: WhatsAppBusiness) -> None:
    lookaside = "https://lookaside.fbsbx.com/whatsapp_business/attachments/m9"
    with respx.mock(assert_all_called=False) as mock:
        mock.get(f"{BASE}/media-9").mock(
            return_value=httpx.Response(
                200, json={"id": "media-9", "url": lookaside, "mime_type": "image/png"}
            )
        )
        mock.get(lookaside).mock(
            return_value=httpx.Response(
                403,
                json={"error": {"message": f"denied for {TOKEN}", "code": 10}},
            )
        )
        with pytest.raises(Exception) as excinfo:
            await wa.adownload_media("media-9")
    assert TOKEN not in str(excinfo.value)


@pytest.mark.asyncio
async def test_misshapen_200_body_returns_graceful_default(
    wa: WhatsAppBusiness,
) -> None:
    with respx.mock(base_url=BASE) as mock:
        mock.post(f"/{PHONE_ID}/messages").mock(
            return_value=httpx.Response(200, json={"messages": "oops", "contacts": 5})
        )
        result = await wa.asend_text("15550001111", "hi")
    assert result.messages == []
    assert result.message_id == ""


@pytest.mark.asyncio
async def test_action_before_setup_raises_typed_connection_error() -> None:
    connector = WhatsAppBusiness(credentials=CREDS)
    with pytest.raises(TCConnectionError):
        await connector.asend_text("15550001111", "hi")


@pytest.mark.asyncio
async def test_send_location_rejects_non_numeric(wa: WhatsAppBusiness) -> None:
    with pytest.raises(ValidationError):
        await wa.asend_location("15550001111", "north", "west")  # type: ignore[arg-type]


def test_verify_signature_hostile_headers_never_raise() -> None:
    body = b'{"object": "whatsapp_business_account"}'
    good = _sign(body)
    assert verify_signature(body, good.encode("ascii"), APP_SECRET) is True
    assert verify_signature(body, "sha256=\u00fcber-hostile", APP_SECRET) is False
    assert verify_signature(body, b"\xff\xfe not ascii", APP_SECRET) is False
    assert verify_signature(body, "sha256=zzzz", APP_SECRET) is False


def test_handle_verification_non_ascii_tokens() -> None:
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": "\u00fcber-token",
        "hub.challenge": "42",
    }
    assert handle_verification(params, "\u00fcber-token") == "42"
    with pytest.raises(ValidationError):
        handle_verification(params, "ascii-token")


def test_parse_events_malformed_messages_value_kept_raw() -> None:
    value = {"messaging_product": "whatsapp", "messages": "not-a-list"}
    [event] = parse_events(_envelope("messages", value))
    assert event.messages_value is None
    assert event.raw_value == value


def test_parse_events_non_numeric_entry_time() -> None:
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": WABA_ID,
                "time": "abc",
                "changes": [{"field": "messages", "value": {"messages": []}}],
            }
        ],
    }
    [event] = parse_events(payload)
    assert event.entry_time == 0


def test_parse_events_status_group_and_identity_fields() -> None:
    value = {
        "messaging_product": "whatsapp",
        "metadata": _METADATA,
        "statuses": [
            {
                "id": "wamid.G1",
                "status": "delivered",
                "recipient_id": "1555",
                "recipient_type": "group",
                "recipient_participant_id": "1666",
                "recipient_identity_key_hash": "hash==",
            }
        ],
        "contacts": [{"wa_id": "1555", "identity_key_hash": "chash=="}],
    }
    [event] = parse_events(_envelope("messages", value))
    status = event.messages_value.statuses[0]
    assert status.recipient_type == "group"
    assert status.recipient_identity_key_hash == "hash=="
    assert event.messages_value.contacts[0].identity_key_hash == "chash=="


def test_parse_events_bsuid_and_call_permission_reply() -> None:
    value = {
        "messaging_product": "whatsapp",
        "metadata": _METADATA,
        "messages": [
            {
                "from": "",
                "from_user_id": "bsuid-123",
                "id": "wamid.U1",
                "timestamp": "1",
                "type": "interactive",
                "interactive": {
                    "type": "call_permission_reply",
                    "call_permission_reply": {
                        "response": "accept",
                        "is_permanent": False,
                        "expiration_timestamp": 1753000000,
                    },
                },
            }
        ],
    }
    [event] = parse_events(_envelope("messages", value))
    message = event.messages_value.messages[0]
    assert message.from_user_id == "bsuid-123"
    assert message.interactive.call_permission_reply["response"] == "accept"


# ---------------------------------------------------------------------------
# W2 management actions (wire shapes per the register + Whatomate cross-check)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_template_body_pin(wa: WhatsAppBusiness) -> None:
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        route = mock.post(f"/{WABA_ID}/message_templates").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "1407680676729941",
                    "status": "PENDING",
                    "category": "UTILITY",
                },
            )
        )
        result = await wa.acreate_template(
            "order_update",
            "en_US",
            "UTILITY",
            [{"type": "BODY", "text": "Order {{1}} shipped", "example": {"body_text": [["1234"]]}}],
            parameter_format=None,
        )
    body = json_body(route)
    assert body["name"] == "order_update"
    assert body["category"] == "UTILITY"
    assert "parameter_format" not in body
    assert result.id == "1407680676729941"
    assert result.status == "PENDING"


@pytest.mark.asyncio
async def test_list_templates_follows_cursor(wa: WhatsAppBusiness) -> None:
    # Whatomate lesson: >100 templates truncate silently if paging ignored.
    def responder(request: httpx.Request) -> httpx.Response:
        after = httpx.QueryParams(request.url.query).get("after")
        if after is None:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "1",
                            "name": "t1",
                            "status": "APPROVED",
                            "quality_score": {"score": "GREEN"},
                        }
                    ],
                    "paging": {"cursors": {"after": "c2"}, "next": "https://next"},
                },
            )
        return httpx.Response(
            200,
            json={
                "data": [{"id": "2", "name": "t2", "status": "PAUSED", "quality_rating": "RED"}],
                "paging": {"cursors": {"after": "c3"}},
            },
        )

    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        mock.get(f"/{WABA_ID}/message_templates").mock(side_effect=responder)
        page = await wa.alist_templates(limit=1)
        items = await page.collect()
    assert [t.name for t in items] == ["t1", "t2"]
    assert items[0].quality_score == {"score": "GREEN"}
    assert items[1].quality_rating == "RED"


@pytest.mark.asyncio
async def test_edit_and_delete_template(wa: WhatsAppBusiness) -> None:
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        edit = mock.post("/140768").mock(return_value=httpx.Response(200, json={"success": True}))
        delete = mock.delete(f"/{WABA_ID}/message_templates").mock(
            return_value=httpx.Response(200, json={"success": True})
        )
        await wa.aedit_template("140768", components=[{"type": "BODY", "text": "x"}])
        await wa.adelete_template("order_update", template_id="140768")
    assert json_body(edit) == {"components": [{"type": "BODY", "text": "x"}]}
    params = httpx.QueryParams(delete.calls.last.request.url.query)
    assert params.get("name") == "order_update"
    assert params.get("hsm_id") == "140768"

    with pytest.raises(ValidationError):
        await wa.aedit_template("140768")  # nothing to change


@pytest.mark.asyncio
async def test_qr_code_lifecycle(wa: WhatsAppBusiness) -> None:
    qr = {
        "code": "ABC1",
        "prefilled_message": "hi",
        "deep_link_url": "https://wa.me/message/ABC1",
        "qr_image_url": "https://x/qr.svg",
    }
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        create = mock.post(f"/{PHONE_ID}/message_qrdls").mock(
            return_value=httpx.Response(200, json=qr)
        )
        listing = mock.get(f"/{PHONE_ID}/message_qrdls").mock(
            return_value=httpx.Response(200, json={"data": [qr]})
        )
        delete = mock.delete(f"/{PHONE_ID}/message_qrdls/ABC1").mock(
            return_value=httpx.Response(200, json={"success": True})
        )
        created = await wa.acreate_qr_code("hi", image_format="SVG")
        codes = await wa.alist_qr_codes()
        deleted = await wa.adelete_qr_code("ABC1")
    assert json_body(create) == {"prefilled_message": "hi", "generate_qr_image": "SVG"}
    assert created.deep_link_url.endswith("/message/ABC1")
    assert codes[0].code == "ABC1"
    assert deleted.success is True
    assert listing.called and delete.called

    with pytest.raises(ValidationError):
        await wa.acreate_qr_code("x" * 141)


@pytest.mark.asyncio
async def test_block_unblock_payloads(wa: WhatsAppBusiness) -> None:
    envelope = {
        "block_users": {
            "added_users": [{"input": "1555", "wa_id": "1555"}],
            "failed_users": [],
        }
    }
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        block = mock.post(f"/{PHONE_ID}/block_users").mock(
            return_value=httpx.Response(200, json=envelope)
        )
        await wa.ablock_users(["1555"])
    assert json_body(block) == {
        "messaging_product": "whatsapp",
        "block_users": [{"user": "1555"}],
    }
    with pytest.raises(ValidationError):
        await wa.ablock_users([])
    with pytest.raises(ValidationError):
        await wa.aunblock_users([str(i) for i in range(1001)])


@pytest.mark.asyncio
async def test_registration_and_pin_payloads(wa: WhatsAppBusiness) -> None:
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        request_code = mock.post(f"/{PHONE_ID}/request_code").mock(
            return_value=httpx.Response(200, json={"success": True})
        )
        register = mock.post(f"/{PHONE_ID}/register").mock(
            return_value=httpx.Response(200, json={"success": True})
        )
        pin = mock.post(f"/{PHONE_ID}").mock(
            return_value=httpx.Response(200, json={"success": True})
        )
        await wa.arequest_verification_code(code_method="VOICE", language="en_US")
        await wa.aregister_phone("123456", data_localization_region="IN")
        await wa.aset_two_step_pin("654321")
    assert json_body(request_code) == {"code_method": "VOICE", "language": "en_US"}
    assert json_body(register) == {
        "messaging_product": "whatsapp",
        "pin": "123456",
        "data_localization_region": "IN",
    }
    assert json_body(pin) == {"pin": "654321"}
    with pytest.raises(ValidationError):
        await wa.aset_two_step_pin("12ab56")


@pytest.mark.asyncio
async def test_analytics_field_syntax(wa: WhatsAppBusiness) -> None:
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        route = mock.get(f"/{WABA_ID}").mock(
            return_value=httpx.Response(200, json={"analytics": {"data": []}})
        )
        await wa.aget_messaging_analytics(
            1750000000,
            1750600000,
            granularity="DAY",
            phone_numbers=["+15550001111"],
        )
    fields = httpx.QueryParams(route.calls.last.request.url.query).get("fields")
    assert fields == (
        "analytics.start(1750000000).end(1750600000).granularity(DAY)"
        '.phone_numbers(["+15550001111"])'
    )

    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        route = mock.get(f"/{WABA_ID}").mock(
            return_value=httpx.Response(200, json={"pricing_analytics": {}})
        )
        await wa.aget_pricing_analytics(
            1750000000,
            1750600000,
            granularity="DAILY",
            metric_types=["COST"],
            dimensions=["PRICING_CATEGORY", "TIER"],
        )
    fields = httpx.QueryParams(route.calls.last.request.url.query).get("fields")
    assert ".granularity(DAILY)" in fields
    # Quoted values — live-verified 2026-07-23 (unquoted -> Graph code 100).
    assert '.metric_types(["COST"])' in fields
    assert '.dimensions(["PRICING_CATEGORY","TIER"])' in fields


@pytest.mark.asyncio
async def test_template_analytics_numeric_unquoted_ids(wa: WhatsAppBusiness) -> None:
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        route = mock.get(f"/{WABA_ID}/template_analytics").mock(
            return_value=httpx.Response(200, json={"data": []})
        )
        await wa.aget_template_analytics(["140768", "999001"], 1750000000, 1750600000)
    params = httpx.QueryParams(route.calls.last.request.url.query)
    assert params.get("template_ids") == "[140768,999001]"  # numeric, unquoted
    assert params.get("granularity") == "DAILY"
    with pytest.raises(ValidationError):
        await wa.aget_template_analytics([], 1, 2)


@pytest.mark.asyncio
async def test_subscribe_app_and_override_rules(wa: WhatsAppBusiness) -> None:
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        route = mock.post(f"/{WABA_ID}/subscribed_apps").mock(
            return_value=httpx.Response(200, json={"success": True})
        )
        await wa.asubscribe_app()
        await wa.asubscribe_app(
            override_callback_uri="https://cb.test/webhook",
            verify_token="tok",
        )
    assert json_body(route) == {
        "override_callback_uri": "https://cb.test/webhook",
        "verify_token": "tok",
    }
    with pytest.raises(ValidationError):
        await wa.asubscribe_app(override_callback_uri="https://cb.test/webhook")


@pytest.mark.asyncio
async def test_set_app_webhook_uses_app_token(wa: WhatsAppBusiness) -> None:
    # Live-verified 2026-07-23: app-level subscription authenticates with
    # the app token (app_id|app_secret), NOT the System User token.
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        route = mock.post("/1234567890123456/subscriptions").mock(
            return_value=httpx.Response(200, json={"success": True})
        )
        await wa.aset_app_webhook(
            "1234567890123456",
            "https://cb.test/webhook",
            "tok",
        )
    request = route.calls.last.request
    assert request.headers["authorization"] == (f"Bearer 1234567890123456|{APP_SECRET}")
    params = httpx.QueryParams(request.url.query)
    assert params.get("object") == "whatsapp_business_account"
    assert params.get("fields") == "messages"
    assert TOKEN not in str(request.url)


@pytest.mark.asyncio
async def test_get_waba_fields(wa: WhatsAppBusiness) -> None:
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        mock.get(f"/{WABA_ID}").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": WABA_ID,
                    "name": "Test WABA",
                    "currency": "USD",
                    "business_verification_status": "not_verified",
                },
            )
        )
        waba = await wa.aget_waba()
    assert waba.name == "Test WABA"
    assert waba.business_verification_status == "not_verified"


# ---------------------------------------------------------------------------
# Embedded Signup onboarding (the "Connect WhatsApp" button, platform side)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exchange_code_wire_shape(wa: WhatsAppBusiness) -> None:
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        route = mock.get("/oauth/access_token").mock(
            return_value=httpx.Response(200, json={"access_token": "EAAcustomer123"})
        )
        result = await wa.aexchange_code("ES_CODE", app_id="1234567890123456")
    params = httpx.QueryParams(route.calls.last.request.url.query)
    # GET with exactly these three params — no redirect_uri, no grant_type.
    assert params.get("client_id") == "1234567890123456"
    assert params.get("client_secret") == APP_SECRET
    assert params.get("code") == "ES_CODE"
    assert "grant_type" not in params
    assert "redirect_uri" not in params
    assert result.access_token == "EAAcustomer123"
    assert result.token_type == ""  # not documented — must not be required


@pytest.mark.asyncio
async def test_exchange_code_requires_code_and_app_id(wa: WhatsAppBusiness) -> None:
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        route = mock.get("/oauth/access_token")
        with pytest.raises(ValidationError):
            await wa.aexchange_code("")
        with pytest.raises(MissingConfigError):
            await wa.aexchange_code("ES_CODE")  # no app_id anywhere
    assert not route.called


@pytest.mark.asyncio
async def test_exchange_code_works_without_user_token() -> None:
    # A platform bootstrapping ES has only app credentials.
    connector = WhatsAppBusiness(
        credentials={
            "app_id": "1234567890123456",
            "app_secret": APP_SECRET,
        }
    )
    await connector._setup()
    try:
        with respx.mock(base_url=BASE, assert_all_called=True) as mock:
            mock.get("/oauth/access_token").mock(
                return_value=httpx.Response(200, json={"access_token": "EAAnew"})
            )
            result = await connector.aexchange_code("ES_CODE")
        assert result.access_token == "EAAnew"
        # ...but a user-token action must still fail loudly.
        with pytest.raises(MissingConfigError):
            await connector.aget_phone_number()
    finally:
        await connector._teardown()


@pytest.mark.asyncio
async def test_debug_token_extracts_waba_ids(wa: WhatsAppBusiness) -> None:
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        route = mock.get("/debug_token").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "app_id": "1234567890123456",
                        "application": "Liminahub",
                        "type": "SYSTEM_USER",
                        "is_valid": True,
                        "expires_at": 0,
                        "scopes": ["whatsapp_business_management", "whatsapp_business_messaging"],
                        "granular_scopes": [
                            {
                                "scope": "whatsapp_business_management",
                                "target_ids": ["102289599326934"],
                            },
                            # Meta's reference types these int[] — real ES sends str.
                            {
                                "scope": "whatsapp_business_messaging",
                                "target_ids": [102289599326934, 887654321098765],
                            },
                            {"scope": "public_profile"},
                        ],
                    }
                },
            )
        )
        info = await wa.adebug_token("EAAcustomer123", app_id="1234567890123456")
    request = route.calls.last.request
    # App token auth — NOT the System User token.
    assert request.headers["authorization"] == (f"Bearer 1234567890123456|{APP_SECRET}")
    assert TOKEN not in str(request.url) and TOKEN not in str(request.headers)
    assert httpx.QueryParams(request.url.query).get("input_token") == "EAAcustomer123"
    assert info.is_valid is True
    assert info.type == "SYSTEM_USER"
    # Deduped, order preserved, ints coerced to str.
    assert info.waba_ids == ["102289599326934", "887654321098765"]


@pytest.mark.asyncio
async def test_debug_token_tolerates_scope_drift(wa: WhatsAppBusiness) -> None:
    # chatwoot#14690: scope naming drifts in the wild; missing target_ids
    # must not hard-fail.
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        mock.get("/debug_token").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "is_valid": True,
                        "granular_scopes": [
                            {"scope": "business_management", "target_ids": ["999"]},
                            {"scope": "whatsapp_business_messaging"},
                        ],
                    }
                },
            )
        )
        info = await wa.adebug_token("EAAx", app_id="123")
    assert info.waba_ids == []  # non-whatsapp scope ignored, absent ids tolerated
    assert info.is_valid is True


@pytest.mark.asyncio
async def test_debug_token_defaults_to_own_token(wa: WhatsAppBusiness) -> None:
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        route = mock.get("/debug_token").mock(
            return_value=httpx.Response(200, json={"data": {"is_valid": True}})
        )
        await wa.adebug_token(app_id="123")
    assert httpx.QueryParams(route.calls.last.request.url.query).get("input_token") == TOKEN


@pytest.mark.asyncio
async def test_app_secret_scrubbed_from_errors(wa: WhatsAppBusiness) -> None:
    with respx.mock(base_url=BASE) as mock:
        mock.get("/oauth/access_token").mock(
            return_value=httpx.Response(
                400,
                json={
                    "error": {
                        "message": f"bad secret {APP_SECRET}",
                        "code": 100,
                    }
                },
            )
        )
        with pytest.raises(ValidationError) as excinfo:
            await wa.aexchange_code("ES_CODE", app_id="123")
    assert APP_SECRET not in str(excinfo.value)
