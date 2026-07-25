"""Result models for the WhatsApp link connector (offline, no API)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

_CFG = ConfigDict(frozen=True, populate_by_name=True, extra="ignore")


class WhatsAppLinkResult(BaseModel):
    """A generated click-to-chat link."""

    model_config = _CFG

    url: str = ""
    phone: str = ""
    text: str = ""
    scheme: str = ""


class WhatsAppParsedLink(BaseModel):
    """A parsed/validated WhatsApp link of any known scheme.

    ``kind`` is one of ``chat`` (wa.me/<number>), ``text_only``
    (wa.me/?text=), ``short_link`` (wa.me/message/<CODE>, API-managed),
    ``group_invite`` (chat.whatsapp.com/<code>), or ``unknown``.
    """

    model_config = _CFG

    valid: bool = False
    kind: str = "unknown"
    phone: str = ""
    text: str = ""
    code: str = ""


class WhatsAppQRResult(BaseModel):
    """An offline-rendered QR code for a click-to-chat link."""

    model_config = _CFG

    url: str = ""
    svg: str = ""
