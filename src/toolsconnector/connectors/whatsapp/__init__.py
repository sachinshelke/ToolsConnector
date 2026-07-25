"""WhatsApp link connector — offline click-to-chat primitives (no API).

Personal WhatsApp has no official API; this connector builds, parses,
and QR-renders WhatsApp's officially documented click-to-chat links
entirely offline. For programmatic send/receive use the
``whatsapp_business`` connector (official Meta Cloud API).
"""

from __future__ import annotations

from .connector import WhatsApp
from .types import WhatsAppLinkResult, WhatsAppParsedLink, WhatsAppQRResult

__all__ = [
    "WhatsApp",
    "WhatsAppLinkResult",
    "WhatsAppParsedLink",
    "WhatsAppQRResult",
]
