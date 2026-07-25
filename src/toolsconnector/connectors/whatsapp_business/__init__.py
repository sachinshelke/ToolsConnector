"""WhatsApp Business connector — official Meta Cloud API (BYOK).

Messaging + media + profile actions live on :class:`WhatsAppBusiness`;
webhook receive primitives (``verify_signature``, ``handle_verification``,
``parse_events``) are pure functions in :mod:`.webhooks` — mount them in
your own HTTPS endpoint. For personal-WhatsApp link building (no API
exists for personal accounts) use the ``whatsapp`` connector instead.
"""

from __future__ import annotations

from .connector import WhatsAppBusiness
from .types import (
    WhatsAppBlockResult,
    WhatsAppBusinessProfile,
    WhatsAppMediaContent,
    WhatsAppMediaInfo,
    WhatsAppPhoneNumber,
    WhatsAppQRCode,
    WhatsAppSendResult,
    WhatsAppSuccessResult,
    WhatsAppTemplate,
    WhatsAppTemplateCreateResult,
    WhatsAppTokenExchange,
    WhatsAppTokenInfo,
    WhatsAppUploadResult,
    WhatsAppWABA,
)
from .webhooks import (
    WhatsAppEvent,
    WhatsAppInboundMessage,
    WhatsAppMessagesValue,
    WhatsAppStatus,
    handle_verification,
    parse_events,
    verify_signature,
)

__all__ = [
    "WhatsAppBlockResult",
    "WhatsAppBusiness",
    "WhatsAppBusinessProfile",
    "WhatsAppEvent",
    "WhatsAppInboundMessage",
    "WhatsAppMediaContent",
    "WhatsAppMediaInfo",
    "WhatsAppMessagesValue",
    "WhatsAppPhoneNumber",
    "WhatsAppQRCode",
    "WhatsAppSendResult",
    "WhatsAppStatus",
    "WhatsAppSuccessResult",
    "WhatsAppTemplate",
    "WhatsAppTemplateCreateResult",
    "WhatsAppTokenExchange",
    "WhatsAppTokenInfo",
    "WhatsAppUploadResult",
    "WhatsAppWABA",
    "handle_verification",
    "parse_events",
    "verify_signature",
]
