"""Webhook primitives for the WhatsApp Business Platform (Cloud API).

Receiving is push-only: Meta has NO polling endpoint, retries failed
deliveries with decreasing frequency for up to 7 days, and inbound
messages missed beyond that window are unrecoverable. These helpers are
deliberately pure functions — the HTTPS listener belongs to the caller
(FastAPI/Flask/Django/Lambda all work; see the connector README):

    GET  (verification) -> handle_verification(request.query_params, VERIFY_TOKEN)
    POST (events)       -> verify_signature(raw_body, sig_header, APP_SECRET)
                           then parse_events(raw_body)

Delivery caveats callers must handle (verified against Meta docs
2026-07-22): retries duplicate events — dedupe by ``wamid``; ordering is
NOT guaranteed — order by ``timestamp``, treat status transitions as
monotonic; one POST may batch multiple ``entry``/``changes`` items
(up to 3 MB).

``verify_signature`` computes HMAC-SHA256 with the **Meta app secret**
(app-level — one per Meta app), while API actions use the per-tenant
access token: multi-tenant platforms verify once at the edge, then route
each event by ``WhatsAppEvent.waba_id`` / ``metadata.phone_number_id``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from toolsconnector.connectors._helpers import safe_int, safe_validate
from toolsconnector.errors import ValidationError

_CFG = ConfigDict(frozen=True, populate_by_name=True, extra="ignore")

_CONNECTOR = "whatsapp_business"

# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------


def verify_signature(
    raw_body: bytes | str,
    signature_header: Optional[str | bytes],
    app_secret: str,
) -> bool:
    """Constant-time check of Meta's ``X-Hub-Signature-256`` header.

    Compute over the RAW request body bytes exactly as received —
    re-serializing the JSON breaks the signature (Meta signs the escaped
    form it sent, including ``\\uXXXX`` escapes for non-ASCII).

    Args:
        raw_body: Raw HTTP body bytes (or str, encoded as UTF-8).
        signature_header: Value of ``X-Hub-Signature-256`` (``sha256=<hex>``).
            ``None``/empty returns ``False``.
        app_secret: The Meta app secret (app-level, not the access token).

    Returns:
        ``True`` only if the signature matches.

    Raises:
        ValidationError: If ``app_secret`` is empty.
    """
    if not app_secret:
        raise ValidationError(
            "app_secret is required to verify webhook signatures.",
            connector=_CONNECTOR,
        )
    if not signature_header:
        return False
    if isinstance(signature_header, bytes):
        try:
            signature_header = signature_header.decode("ascii")
        except UnicodeDecodeError:
            return False
    expected = str(signature_header).removeprefix("sha256=").strip()
    body = raw_body.encode("utf-8") if isinstance(raw_body, str) else raw_body
    digest = hmac.new(app_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    # bytes/bytes compare_digest never raises on hostile header content.
    return hmac.compare_digest(digest.encode("ascii"), expected.encode("utf-8"))


def handle_verification(
    params: Mapping[str, Any],
    verify_token: str,
) -> str:
    """Answer Meta's GET verification handshake.

    Meta sends ``GET ?hub.mode=subscribe&hub.verify_token=...&hub.challenge=...``
    on webhook configuration (and periodically after). Respond HTTP 200 with
    the returned string as the raw body.

    Args:
        params: The request's query parameters.
        verify_token: The token you configured in the App Dashboard.

    Returns:
        The ``hub.challenge`` value to echo back.

    Raises:
        ValidationError: If the mode or token does not match (respond 403).
    """
    mode = str(params.get("hub.mode", ""))
    token = str(params.get("hub.verify_token", ""))
    challenge = params.get("hub.challenge")
    if mode != "subscribe" or challenge is None:
        raise ValidationError(
            "Not a valid webhook verification request (hub.mode/hub.challenge).",
            connector=_CONNECTOR,
        )
    if not hmac.compare_digest(token.encode("utf-8"), verify_token.encode("utf-8")):
        raise ValidationError(
            "hub.verify_token does not match the configured verify token.",
            connector=_CONNECTOR,
        )
    return str(challenge)


# ---------------------------------------------------------------------------
# Event models (field == "messages" is fully typed; everything else is
# delivered as a raw dict on WhatsAppEvent.raw_value)
# ---------------------------------------------------------------------------


class WhatsAppWebhookMetadata(BaseModel):
    """Which business number the event belongs to (tenant routing key)."""

    model_config = _CFG

    display_phone_number: str = ""
    phone_number_id: str = ""


class WhatsAppWebhookContact(BaseModel):
    """Sender identity attached to inbound messages."""

    model_config = _CFG

    wa_id: str = ""
    user_id: str = ""
    identity_key_hash: str = ""
    profile: dict[str, Any] = Field(default_factory=dict)


class WhatsAppText(BaseModel):
    model_config = _CFG

    body: str = ""


class WhatsAppMediaPayload(BaseModel):
    """Inbound media reference (image/audio/video/document/sticker)."""

    model_config = _CFG

    id: str = ""
    mime_type: str = ""
    sha256: str = ""
    caption: str = ""
    filename: str = ""
    voice: bool = False
    animated: bool = False
    # Direct CDN link, rolling out in media webhooks since Nov 2025.
    url: str = ""


class WhatsAppLocationPayload(BaseModel):
    model_config = _CFG

    latitude: float = 0.0
    longitude: float = 0.0
    name: str = ""
    address: str = ""


class WhatsAppReactionPayload(BaseModel):
    model_config = _CFG

    message_id: str = ""
    emoji: str = ""


class WhatsAppInteractiveReply(BaseModel):
    """Replies to interactive messages: buttons, lists, and Flows (nfm_reply)."""

    model_config = _CFG

    type: str = ""
    button_reply: dict[str, Any] = Field(default_factory=dict)
    list_reply: dict[str, Any] = Field(default_factory=dict)
    nfm_reply: dict[str, Any] = Field(default_factory=dict)
    call_permission_reply: dict[str, Any] = Field(default_factory=dict)


class WhatsAppTemplateButtonReply(BaseModel):
    """Tap on a template quick-reply button."""

    model_config = _CFG

    payload: str = ""
    text: str = ""


class WhatsAppOrderPayload(BaseModel):
    """Cart submitted from a product/product-list/catalog message."""

    model_config = _CFG

    catalog_id: str = ""
    text: str = ""
    product_items: list[dict[str, Any]] = Field(default_factory=list)


class WhatsAppSystemPayload(BaseModel):
    """System messages (e.g. ``user_changed_number``)."""

    model_config = _CFG

    body: str = ""
    type: str = ""
    wa_id: str = ""
    new_wa_id: str = ""


class WhatsAppContext(BaseModel):
    """Reply/forward context attached to an inbound message."""

    model_config = _CFG

    from_: str = Field("", alias="from")
    id: str = ""
    forwarded: bool = False
    frequently_forwarded: bool = False
    referred_product: dict[str, Any] = Field(default_factory=dict)


class WhatsAppReferral(BaseModel):
    """Click-to-WhatsApp ad/post attribution (``ctwa_clid`` is the ad key)."""

    model_config = _CFG

    source_url: str = ""
    source_id: str = ""
    source_type: str = ""
    headline: str = ""
    body: str = ""
    media_type: str = ""
    image_url: str = ""
    video_url: str = ""
    thumbnail_url: str = ""
    ctwa_clid: str = ""


class WhatsAppWebhookError(BaseModel):
    """Error object (appears on value, message, and status levels)."""

    model_config = _CFG

    code: int = 0
    title: str = ""
    message: str = ""
    error_data: dict[str, Any] = Field(default_factory=dict)
    href: str = ""


class WhatsAppInboundMessage(BaseModel):
    """One inbound message; ``type`` selects which payload field is set."""

    model_config = _CFG

    id: str = ""
    from_: str = Field("", alias="from")
    timestamp: str = ""
    type: str = ""
    text: Optional[WhatsAppText] = None
    image: Optional[WhatsAppMediaPayload] = None
    audio: Optional[WhatsAppMediaPayload] = None
    video: Optional[WhatsAppMediaPayload] = None
    document: Optional[WhatsAppMediaPayload] = None
    sticker: Optional[WhatsAppMediaPayload] = None
    location: Optional[WhatsAppLocationPayload] = None
    contacts: list[dict[str, Any]] = Field(default_factory=list)
    reaction: Optional[WhatsAppReactionPayload] = None
    interactive: Optional[WhatsAppInteractiveReply] = None
    button: Optional[WhatsAppTemplateButtonReply] = None
    order: Optional[WhatsAppOrderPayload] = None
    system: Optional[WhatsAppSystemPayload] = None
    context: Optional[WhatsAppContext] = None
    referral: Optional[WhatsAppReferral] = None
    errors: list[WhatsAppWebhookError] = Field(default_factory=list)
    # Groups API: set when the message was sent in a business group.
    group_id: str = ""
    # BSUID identity model (since Mar 2026). Meta docs say user_id; production
    # payloads (Whatomate cross-check) carry from_user_id — accept both.
    user_id: str = ""
    from_user_id: str = ""
    # Present on coexistence echo-shaped messages (business -> user).
    to: str = ""


class WhatsAppConversation(BaseModel):
    """Conversation object — omitted in v24+ except free-entry-point."""

    model_config = _CFG

    id: str = ""
    origin: dict[str, Any] = Field(default_factory=dict)
    expiration_timestamp: str = ""


class WhatsAppPricing(BaseModel):
    """Per-message pricing metadata on status events."""

    model_config = _CFG

    billable: bool = False
    pricing_model: str = ""
    category: str = ""
    type: str = ""


class WhatsAppStatus(BaseModel):
    """Outbound lifecycle: sent | delivered | read | played | failed."""

    model_config = _CFG

    id: str = ""
    status: str = ""
    timestamp: str = ""
    recipient_id: str = ""
    conversation: Optional[WhatsAppConversation] = None
    pricing: Optional[WhatsAppPricing] = None
    errors: list[WhatsAppWebhookError] = Field(default_factory=list)
    biz_opaque_callback_data: str = ""
    recipient_type: str = ""
    recipient_participant_id: str = ""
    recipient_identity_key_hash: str = ""


class WhatsAppMessagesValue(BaseModel):
    """Typed ``value`` for the ``messages`` webhook field."""

    model_config = _CFG

    messaging_product: str = ""
    metadata: WhatsAppWebhookMetadata = Field(default_factory=WhatsAppWebhookMetadata)
    contacts: list[WhatsAppWebhookContact] = Field(default_factory=list)
    messages: list[WhatsAppInboundMessage] = Field(default_factory=list)
    statuses: list[WhatsAppStatus] = Field(default_factory=list)
    errors: list[WhatsAppWebhookError] = Field(default_factory=list)


class WhatsAppEvent(BaseModel):
    """One webhook change, with tenant routing keys lifted to the top level.

    ``field`` names the subscription field (``messages``, ``smb_message_echoes``,
    ``message_template_status_update``, ``calls``, ``group_lifecycle_update``, …).
    For ``messages`` the parsed ``value`` is available as ``.messages_value``;
    every field's untouched payload is always in ``.raw_value``.
    """

    model_config = _CFG

    waba_id: str = ""
    field: str = ""
    entry_time: int = 0
    messages_value: Optional[WhatsAppMessagesValue] = None
    raw_value: dict[str, Any] = Field(default_factory=dict)

    @property
    def phone_number_id(self) -> str:
        """Routing key: the business number this event targets ('' if absent)."""
        meta = self.raw_value.get("metadata")
        if isinstance(meta, dict):
            return str(meta.get("phone_number_id", ""))
        return ""


def parse_events(payload: bytes | str | dict[str, Any]) -> list[WhatsAppEvent]:
    """Parse a webhook POST body into typed events (one per ``changes`` item).

    Accepts the raw body (bytes/str) or an already-decoded dict. A single
    POST can batch many entries; all are returned in payload order.

    Args:
        payload: Raw request body or decoded JSON object.

    Returns:
        List of :class:`WhatsAppEvent` (empty for well-formed non-event bodies).

    Raises:
        ValidationError: If the body is not valid JSON or not a webhook
            envelope for a WhatsApp Business Account object.
    """
    if isinstance(payload, (bytes, str)):
        try:
            data = json.loads(payload)
        except ValueError as exc:
            raise ValidationError("Webhook body is not valid JSON.", connector=_CONNECTOR) from exc
    else:
        data = payload
    if not isinstance(data, dict):
        raise ValidationError("Webhook body must be a JSON object.", connector=_CONNECTOR)
    obj = data.get("object")
    if obj != "whatsapp_business_account":
        raise ValidationError(
            f"Unexpected webhook object {obj!r} (expected 'whatsapp_business_account').",
            connector=_CONNECTOR,
        )

    events: list[WhatsAppEvent] = []
    entries = data.get("entry")
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        waba_id = str(entry.get("id", ""))
        entry_time = entry.get("time", 0)
        changes = entry.get("changes")
        for change in changes if isinstance(changes, list) else []:
            if not isinstance(change, dict):
                continue
            field = str(change.get("field", ""))
            value = change.get("value")
            raw_value = value if isinstance(value, dict) else {}
            # Malformed 'messages' values leave messages_value=None; the
            # untouched payload is always available in raw_value.
            messages_value = (
                safe_validate(WhatsAppMessagesValue, raw_value) if field == "messages" else None
            )
            events.append(
                WhatsAppEvent(
                    waba_id=waba_id,
                    field=field,
                    entry_time=safe_int(entry_time, 0),
                    messages_value=messages_value,
                    raw_value=raw_value,
                )
            )
    return events
