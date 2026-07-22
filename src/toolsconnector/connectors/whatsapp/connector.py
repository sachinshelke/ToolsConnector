"""WhatsApp link connector — offline click-to-chat primitives, zero API.

Personal WhatsApp accounts have NO official API, and every unofficial
"personal WhatsApp API" (reverse-engineered linked-device clients) violates
WhatsApp's Terms of Service and risks permanent number bans — this library
deliberately does not ship one. What personal WhatsApp DOES officially
offer is the click-to-chat URL scheme: this connector builds, parses, and
QR-renders those links entirely offline (zero network calls, zero auth,
zero ban risk). The human taps send — an agent composes, a person decides.

For actually SENDING and RECEIVING messages programmatically, use the
``whatsapp_business`` connector (Meta's official Cloud API).

Link rules verified against WhatsApp's official documentation 2026-07-22
(.agent/artifacts/whatsapp-wire-register.md §Link schemes): wa.me numbers
are full international format, digits only — no ``+``, brackets, dashes,
or leading zeros; prefilled text is URL-encoded; ``wa.me/message/<CODE>``
short links and consumer contact-QRs are NOT offline-generatable (the
former are minted by the Business API, the latter are proprietary).
"""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import parse_qs, quote, urlsplit

from toolsconnector.errors import MissingConfigError, ValidationError
from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import ConnectorCategory, ProtocolType, RateLimitSpec

from .types import WhatsAppLinkResult, WhatsAppParsedLink, WhatsAppQRResult

_STRIP_CHARS = re.compile(r"[\s\-(). ]")
_DIGITS = re.compile(r"^[0-9]+$")

# E.164: country code + subscriber number, 7..15 digits total, no leading 0.
_MIN_DIGITS = 7
_MAX_DIGITS = 15


def _normalize(number: str) -> str:
    """Normalize to wa.me digits or raise ValidationError."""
    raw = str(number).strip()
    if not raw:
        raise ValidationError("Phone number is empty.", connector="whatsapp")
    cleaned = _STRIP_CHARS.sub("", raw)
    if cleaned.startswith("+"):
        cleaned = cleaned[1:]
    elif cleaned.startswith("00"):
        cleaned = cleaned[2:]
    if not _DIGITS.match(cleaned):
        raise ValidationError(
            f"Phone number {raw!r} contains invalid characters — expected"
            " international format like '+14155552671'.",
            connector="whatsapp",
        )
    if cleaned.startswith("0"):
        raise ValidationError(
            f"Phone number {raw!r} keeps a leading zero after the country"
            " code — wa.me links need full international format without"
            " trunk zeros.",
            connector="whatsapp",
        )
    if not (_MIN_DIGITS <= len(cleaned) <= _MAX_DIGITS):
        raise ValidationError(
            f"Phone number {raw!r} has {len(cleaned)} digits — E.164 allows"
            f" {_MIN_DIGITS}..{_MAX_DIGITS}.",
            connector="whatsapp",
        )
    return cleaned


class WhatsApp(BaseConnector):
    """Offline WhatsApp click-to-chat link/QR primitives (personal-side).

    No credentials, no network: every action is a pure computation over
    WhatsApp's officially documented URL schemes. Programmatic messaging
    lives in ``whatsapp_business`` (the official Cloud API connector).
    """

    name = "whatsapp"
    display_name = "WhatsApp"
    category = ConnectorCategory.COMMUNICATION
    protocol = ProtocolType.CUSTOM
    base_url = "https://wa.me"
    # Tier 2 (doc): every scheme rule cross-checked against official
    # WhatsApp docs 2026-07-22 (wire register §Link schemes) and pinned in
    # tests; there is no vendor API for a live tier to verify against.
    verification_status = "doc"
    description = (
        "Offline WhatsApp click-to-chat primitives: build/parse wa.me and"
        " whatsapp:// links, normalize numbers to international format, and"
        " render QR codes — zero network calls, zero auth. Personal"
        " WhatsApp has no official API (unofficial clients get numbers"
        " banned); to SEND or RECEIVE messages programmatically use the"
        " 'whatsapp_business' connector."
    )
    _rate_limit_config = RateLimitSpec(rate=1000, period=1, burst=1000)

    async def _setup(self) -> None:
        # Offline connector: no HTTP client, nothing to initialize.
        return None

    async def _teardown(self) -> None:
        return None

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    @action("Normalize a phone number to wa.me international digits")
    async def normalize_phone(self, number: str) -> str:
        """Normalize a phone number for use in wa.me links.

        Strips spaces, dashes, brackets, dots, a leading ``+`` or ``00``,
        then validates E.164 shape (7-15 digits, no leading zero).

        Args:
            number: The number in any common format, e.g.
                ``'+1 (415) 555-2671'``.

        Returns:
            Digits-only international number, e.g. ``'14155552671'``.
        """
        return _normalize(number)

    @action("Build a wa.me click-to-chat link")
    async def build_chat_link(
        self,
        phone: str,
        text: Optional[str] = None,
    ) -> WhatsAppLinkResult:
        """Build ``https://wa.me/<number>`` with optional prefilled text.

        Opening the link starts a chat with the number in the user's own
        WhatsApp — the user still taps send (nothing is automated).

        Args:
            phone: Recipient number in any common format (normalized
                automatically; must have an active WhatsApp account).
            text: Optional message to prefill (URL-encoded automatically).
        """
        number = _normalize(phone)
        url = f"https://wa.me/{number}"
        if text:
            url += f"?text={quote(str(text), safe='')}"
        return WhatsAppLinkResult(url=url, phone=number, text=text or "", scheme="wa.me")

    @action("Build a text-only wa.me link (recipient picker)")
    async def build_text_link(self, text: str) -> WhatsAppLinkResult:
        """Build ``https://wa.me/?text=...`` — the user picks the recipient.

        Args:
            text: The message to prefill (URL-encoded automatically).
        """
        if not str(text):
            raise ValidationError("text is required.", connector=self.name)
        url = f"https://wa.me/?text={quote(str(text), safe='')}"
        return WhatsAppLinkResult(url=url, text=str(text), scheme="wa.me")

    @action("Build a native whatsapp:// deep link")
    async def build_app_link(
        self,
        phone: Optional[str] = None,
        text: Optional[str] = None,
    ) -> WhatsAppLinkResult:
        """Build a ``whatsapp://send`` deep link for native app contexts.

        ``text`` is officially documented; the ``phone`` parameter is
        de-facto (widely supported but absent from WhatsApp's official
        parameter table) — prefer ``build_chat_link`` (wa.me universal
        links, WhatsApp's stated preferred method) when in doubt.

        Args:
            phone: Optional recipient number (normalized automatically).
            text: Optional message to prefill.
        """
        if not phone and not text:
            raise ValidationError("Provide phone and/or text.", connector=self.name)
        params: list[str] = []
        number = ""
        if phone:
            number = _normalize(phone)
            params.append(f"phone={number}")
        if text:
            params.append(f"text={quote(str(text), safe='')}")
        url = "whatsapp://send?" + "&".join(params)
        return WhatsAppLinkResult(url=url, phone=number, text=text or "", scheme="whatsapp")

    @action("Parse and validate any WhatsApp link")
    async def parse_link(self, url: str) -> WhatsAppParsedLink:
        """Classify a WhatsApp URL and extract its parts.

        Recognizes ``wa.me/<number>``, ``wa.me/?text=``,
        ``wa.me/message/<CODE>`` (API-managed short links),
        ``api.whatsapp.com/send``, ``web.whatsapp.com/send`` (legacy),
        ``whatsapp://send``, and ``chat.whatsapp.com/<code>`` group
        invites.

        Args:
            url: The link to parse.

        Returns:
            Parsed link with ``valid``, ``kind``, and extracted
            ``phone``/``text``/``code``.
        """
        raw = str(url).strip()
        if not raw:
            return WhatsAppParsedLink(valid=False, kind="unknown")
        parts = urlsplit(raw)
        host = (parts.netloc or "").lower()
        path = parts.path or ""
        query = parse_qs(parts.query)

        def q(key: str) -> str:
            values = query.get(key, [])
            return values[0] if values else ""

        if parts.scheme == "whatsapp":
            # whatsapp://send?phone=&text= — netloc is 'send'
            if host == "send" or path.lstrip("/").startswith("send"):
                return WhatsAppParsedLink(
                    valid=True,
                    kind="chat" if q("phone") else "text_only",
                    phone=q("phone"),
                    text=q("text"),
                )
            return WhatsAppParsedLink(valid=False, kind="unknown")
        if parts.scheme not in ("http", "https"):
            return WhatsAppParsedLink(valid=False, kind="unknown")
        if host == "chat.whatsapp.com":
            code = path.strip("/")
            return WhatsAppParsedLink(valid=bool(code), kind="group_invite", code=code)
        if host == "wa.me":
            segments = [s for s in path.split("/") if s]
            if segments[:1] == ["message"]:
                code = segments[1] if len(segments) > 1 else ""
                return WhatsAppParsedLink(valid=bool(code), kind="short_link", code=code)
            if segments and _DIGITS.match(segments[0]):
                return WhatsAppParsedLink(
                    valid=True, kind="chat", phone=segments[0], text=q("text")
                )
            if not segments and q("text"):
                return WhatsAppParsedLink(valid=True, kind="text_only", text=q("text"))
            return WhatsAppParsedLink(valid=False, kind="unknown")
        if host in ("api.whatsapp.com", "web.whatsapp.com"):
            if path.rstrip("/").endswith("/send") or path.startswith("/send"):
                phone = q("phone").lstrip("+")
                return WhatsAppParsedLink(
                    valid=True,
                    kind="chat" if phone else "text_only",
                    phone=phone,
                    text=q("text"),
                )
            if host == "api.whatsapp.com" and path.startswith("/message/"):
                code = path.removeprefix("/message/").strip("/")
                return WhatsAppParsedLink(valid=bool(code), kind="short_link", code=code)
            return WhatsAppParsedLink(valid=False, kind="unknown")
        return WhatsAppParsedLink(valid=False, kind="unknown")

    @action("Validate a chat.whatsapp.com group invite link")
    async def validate_group_invite_link(self, url: str) -> WhatsAppParsedLink:
        """Validate a group invite link (``https://chat.whatsapp.com/<code>``).

        Only the documented prefix is checked — WhatsApp publishes no
        charset/length spec for the code, so no stricter validation is
        applied. Group invite links are created in the WhatsApp app (or by
        Official-Business-Account businesses via the Groups API), never
        offline.

        Args:
            url: The invite link to validate.
        """
        # `a`-prefixed siblings are bound at runtime by BaseConnector.
        parsed = await self.aparse_link(url)  # type: ignore[attr-defined]
        if parsed.kind != "group_invite":
            return WhatsAppParsedLink(valid=False, kind=parsed.kind)
        return parsed

    @action("Render a click-to-chat QR code as SVG (offline)")
    async def render_qr_svg(
        self,
        url: Optional[str] = None,
        phone: Optional[str] = None,
        text: Optional[str] = None,
        scale: int = 4,
        dark: str = "#000000",
    ) -> WhatsAppQRResult:
        """Render a QR code for a wa.me link, fully offline.

        Provide either a ready ``url`` or ``phone`` (+ optional ``text``)
        to build one. Per WhatsApp's guidance for print QR codes: keep the
        code readable — SVG output, no visual distortion (a light module
        color is deliberately not exposed).

        Requires the optional ``segno`` dependency
        (``pip install "toolsconnector[whatsapp]"``).

        Args:
            url: The exact URL to encode (takes precedence).
            phone: Recipient number — used to build a wa.me link if no url.
            text: Optional prefilled text for the built link.
            scale: SVG module scale factor (1..40).
            dark: Dark-module color (hex or CSS name).
        """
        try:
            import segno
        except ImportError as exc:
            raise MissingConfigError(
                "QR rendering needs the optional 'segno' dependency.",
                connector=self.name,
                suggestion='pip install "toolsconnector[whatsapp]"',
            ) from exc
        if url:
            target = str(url)
        elif phone:
            # `a`-prefixed sibling is bound at runtime by BaseConnector.
            link = await self.abuild_chat_link(phone, text)  # type: ignore[attr-defined]
            target = link.url
        else:
            raise ValidationError("Provide url or phone.", connector=self.name)
        clamped_scale = max(1, min(int(scale), 40))
        qr = segno.make(target, error="m")
        svg: Any = qr.svg_inline(scale=clamped_scale, dark=dark)
        return WhatsAppQRResult(url=target, svg=str(svg))
