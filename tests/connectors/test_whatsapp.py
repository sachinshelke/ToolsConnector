"""Tests for the offline WhatsApp link connector.

Pure functions — no HTTP, no mocking. Link rules pinned to WhatsApp's
official click-to-chat documentation (verified 2026-07-22, wire register
§Link schemes).
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from toolsconnector.connectors.whatsapp import WhatsApp
from toolsconnector.errors import ValidationError
from toolsconnector.spec.connector import ConnectorCategory, ProtocolType


@pytest_asyncio.fixture
async def wa() -> WhatsApp:
    connector = WhatsApp()
    await connector._setup()
    yield connector
    await connector._teardown()


# ---------------------------------------------------------------------------
# normalize_phone
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+1 (415) 555-2671", "14155552671"),
        ("14155552671", "14155552671"),
        ("0044 20 7946 0958", "442079460958"),
        ("+91-98765-43210", "919876543210"),
        ("55 11 91234.5678", "5511912345678"),
    ],
)
async def test_normalize_phone_formats(wa: WhatsApp, raw: str, expected: str) -> None:
    assert await wa.anormalize_phone(raw) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad",
    [
        "",  # empty
        "call-me-maybe",  # letters
        "+1 555 CALL",  # mixed
        "0415552671",  # leading trunk zero
        "123456",  # too short
        "1234567890123456",  # 16 digits, too long
    ],
)
async def test_normalize_phone_rejects(wa: WhatsApp, bad: str) -> None:
    with pytest.raises(ValidationError):
        await wa.anormalize_phone(bad)


def test_normalize_phone_sync_wrapper() -> None:
    connector = WhatsApp()
    assert connector.normalize_phone("+1 415 555 2671") == "14155552671"


# ---------------------------------------------------------------------------
# Link builders (official wa.me format: digits only, urlencoded text)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_chat_link(wa: WhatsApp) -> None:
    link = await wa.abuild_chat_link("+1 (415) 555-2671")
    assert link.url == "https://wa.me/14155552671"
    assert link.phone == "14155552671"

    link = await wa.abuild_chat_link("14155552671", text="hello world & more")
    assert link.url == "https://wa.me/14155552671?text=hello%20world%20%26%20more"


@pytest.mark.asyncio
async def test_build_chat_link_encodes_unicode(wa: WhatsApp) -> None:
    link = await wa.abuild_chat_link("14155552671", text="café \U0001f525")
    assert "caf%C3%A9%20%F0%9F%94%A5" in link.url


@pytest.mark.asyncio
async def test_build_text_link(wa: WhatsApp) -> None:
    link = await wa.abuild_text_link("share this")
    assert link.url == "https://wa.me/?text=share%20this"
    with pytest.raises(ValidationError):
        await wa.abuild_text_link("")


@pytest.mark.asyncio
async def test_build_app_link(wa: WhatsApp) -> None:
    link = await wa.abuild_app_link(phone="+1 415 555 2671", text="hi")
    assert link.url == "whatsapp://send?phone=14155552671&text=hi"
    link = await wa.abuild_app_link(text="just text")
    assert link.url == "whatsapp://send?text=just%20text"
    with pytest.raises(ValidationError):
        await wa.abuild_app_link()


# ---------------------------------------------------------------------------
# parse_link (round-trips + every documented scheme)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("url", "kind", "phone", "text", "code"),
    [
        ("https://wa.me/14155552671", "chat", "14155552671", "", ""),
        (
            "https://wa.me/14155552671?text=hello%20world",
            "chat",
            "14155552671",
            "hello world",
            "",
        ),
        ("https://wa.me/?text=pick%20one", "text_only", "", "pick one", ""),
        ("https://wa.me/message/ABCD1234", "short_link", "", "", "ABCD1234"),
        (
            "https://api.whatsapp.com/send/?phone=14155552671&text=hi",
            "chat",
            "14155552671",
            "hi",
            "",
        ),
        (
            "https://web.whatsapp.com/send?phone=%2B14155552671",
            "chat",
            "14155552671",
            "",
            "",
        ),
        ("whatsapp://send?phone=14155552671&text=yo", "chat", "14155552671", "yo", ""),
        (
            "https://chat.whatsapp.com/K5eJx8AbCdEf123",
            "group_invite",
            "",
            "",
            "K5eJx8AbCdEf123",
        ),
    ],
)
async def test_parse_link_schemes(
    wa: WhatsApp, url: str, kind: str, phone: str, text: str, code: str
) -> None:
    parsed = await wa.aparse_link(url)
    assert parsed.valid is True
    assert parsed.kind == kind
    assert parsed.phone == phone
    assert parsed.text == text
    assert parsed.code == code


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/wa.me/14155552671",
        "https://wa.me/notanumber",
        "https://chat.whatsapp.com/",
        "ftp://wa.me/123",
        "",
    ],
)
async def test_parse_link_rejects(wa: WhatsApp, url: str) -> None:
    parsed = await wa.aparse_link(url)
    assert parsed.valid is False


@pytest.mark.asyncio
async def test_builder_parse_roundtrip(wa: WhatsApp) -> None:
    built = await wa.abuild_chat_link("+1 415 555 2671", text="round trip?")
    parsed = await wa.aparse_link(built.url)
    assert parsed.kind == "chat"
    assert parsed.phone == built.phone
    assert parsed.text == "round trip?"


@pytest.mark.asyncio
async def test_validate_group_invite_link(wa: WhatsApp) -> None:
    ok = await wa.avalidate_group_invite_link("https://chat.whatsapp.com/AbC123")
    assert ok.valid is True
    assert ok.code == "AbC123"
    bad = await wa.avalidate_group_invite_link("https://wa.me/14155552671")
    assert bad.valid is False


# ---------------------------------------------------------------------------
# QR rendering (segno optional dep)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_render_qr_svg(wa: WhatsApp) -> None:
    pytest.importorskip("segno")
    result = await wa.arender_qr_svg(phone="+1 415 555 2671", text="scan me")
    assert result.url.startswith("https://wa.me/14155552671?text=")
    assert result.svg.startswith("<svg")
    assert "</svg>" in result.svg


@pytest.mark.asyncio
async def test_render_qr_requires_target(wa: WhatsApp) -> None:
    pytest.importorskip("segno")
    with pytest.raises(ValidationError):
        await wa.arender_qr_svg()


# ---------------------------------------------------------------------------
# Spec governance
# ---------------------------------------------------------------------------


def test_spec_metadata() -> None:
    assert WhatsApp.name == "whatsapp"
    assert WhatsApp.protocol is ProtocolType.CUSTOM
    assert WhatsApp.category is ConnectorCategory.COMMUNICATION
    assert WhatsApp.verification_status == "doc"
    assert len(WhatsApp.get_actions()) == 7


def test_registered_in_discovery() -> None:
    from toolsconnector.serve._discovery import _KNOWN_CONNECTORS

    assert _KNOWN_CONNECTORS["whatsapp"] == "toolsconnector.connectors.whatsapp:WhatsApp"


def test_descriptions_cross_reference_each_other() -> None:
    from toolsconnector.connectors.whatsapp_business import WhatsAppBusiness

    # Agents searching either name must be routed to the right surface.
    assert "whatsapp_business" in WhatsApp.description
    assert "whatsapp" in WhatsAppBusiness.description


def test_auth_spec_declares_no_credentials() -> None:
    from toolsconnector.spec.auth import AuthType

    auth = WhatsApp.get_spec().auth
    assert auth.default is AuthType.CUSTOM
    provider = auth.supported[0]
    # An offline connector says so explicitly, so a connect UI can skip
    # the credential step instead of guessing.
    assert provider.extra["credential_format"] == "none"
    assert provider.extra["fields"] == []


@pytest.mark.asyncio
async def test_health_check_always_healthy(wa: WhatsApp) -> None:
    health = await wa._health_check()
    assert health.healthy is True
    assert "no credentials" in health.message.lower()
