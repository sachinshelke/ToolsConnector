"""Response models for the WhatsApp Business connector.

Wire shapes follow the Cloud API (Graph v25.0) envelopes verified in
``.agent/artifacts/whatsapp-wire-register.md`` (2026-07-22). All models are
frozen, alias-tolerant, and ignore unknown vendor fields so Meta can add
fields without breaking parsing.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

_CFG = ConfigDict(frozen=True, populate_by_name=True, extra="ignore")


class WhatsAppContactRef(BaseModel):
    """Recipient echo returned by every send: input number + canonical wa_id."""

    model_config = _CFG

    input: str = ""
    wa_id: str = ""


class WhatsAppMessageRef(BaseModel):
    """Sent-message reference (the ``wamid`` used for replies/reactions/status)."""

    model_config = _CFG

    id: str = ""
    message_status: str = ""


class WhatsAppSendResult(BaseModel):
    """Envelope returned by ``POST /<PHONE_NUMBER_ID>/messages``."""

    model_config = _CFG

    messaging_product: str = "whatsapp"
    contacts: list[WhatsAppContactRef] = Field(default_factory=list)
    messages: list[WhatsAppMessageRef] = Field(default_factory=list)

    @property
    def message_id(self) -> str:
        """The wamid of the first sent message (empty string if absent)."""
        return self.messages[0].id if self.messages else ""


class WhatsAppBusinessProfile(BaseModel):
    """Business profile shown in the chat header / contact view."""

    model_config = _CFG

    about: str = ""
    address: str = ""
    description: str = ""
    email: str = ""
    profile_picture_url: str = ""
    websites: list[str] = Field(default_factory=list)
    vertical: str = ""
    messaging_product: str = "whatsapp"


class WhatsAppThroughput(BaseModel):
    """Per-number throughput level as reported by the phone-number node."""

    model_config = _CFG

    level: str = ""


class WhatsAppPhoneNumber(BaseModel):
    """Business phone-number node (quality, name status, throughput, limit)."""

    model_config = _CFG

    id: str = ""
    display_phone_number: str = ""
    verified_name: str = ""
    quality_rating: str = ""
    code_verification_status: str = ""
    name_status: str = ""
    platform_type: str = ""
    throughput: Optional[WhatsAppThroughput] = None
    messaging_limit: str = Field("", alias="whatsapp_business_manager_messaging_limit")


class WhatsAppMediaInfo(BaseModel):
    """``GET /<MEDIA_ID>`` result — the download ``url`` expires in ~5 minutes."""

    model_config = _CFG

    id: str = ""
    url: str = ""
    mime_type: str = ""
    sha256: str = ""
    file_size: int = 0
    messaging_product: str = "whatsapp"


class WhatsAppMediaContent(BaseModel):
    """Downloaded media bytes, base64-encoded for transport-safe dual use."""

    model_config = _CFG

    media_id: str = ""
    content_base64: str = ""
    mime_type: str = ""
    byte_size: int = 0
    sha256: str = ""


class WhatsAppUploadResult(BaseModel):
    """``POST /<PHONE_NUMBER_ID>/media`` result — id is valid for 30 days."""

    model_config = _CFG

    id: str = ""


class WhatsAppSuccessResult(BaseModel):
    """Generic ``{"success": true}`` acknowledgement envelope."""

    model_config = _CFG

    success: bool = False
    extra: dict[str, Any] = Field(default_factory=dict)


class WhatsAppTemplate(BaseModel):
    """Message template asset on the WABA (id is numeric on the wire)."""

    model_config = _CFG

    id: str = ""
    name: str = ""
    language: str = ""
    category: str = ""
    status: str = ""
    parameter_format: str = ""
    # Both quality shapes are seen in the wild (Whatomate cross-check).
    quality_score: dict[str, Any] = Field(default_factory=dict)
    quality_rating: str = ""
    components: list[dict[str, Any]] = Field(default_factory=list)


class WhatsAppTemplateCreateResult(BaseModel):
    """``POST /<WABA_ID>/message_templates`` response."""

    model_config = _CFG

    id: str = ""
    status: str = ""
    category: str = ""


class WhatsAppQRCode(BaseModel):
    """Managed QR code / short link (``wa.me/message/<code>``)."""

    model_config = _CFG

    code: str = ""
    prefilled_message: str = ""
    deep_link_url: str = ""
    qr_image_url: str = ""


class WhatsAppWABA(BaseModel):
    """WhatsApp Business Account node."""

    model_config = _CFG

    id: str = ""
    name: str = ""
    currency: str = ""
    status: str = ""
    business_verification_status: str = ""
    country: str = ""


class WhatsAppBlockResult(BaseModel):
    """``block_users`` mutation result (added/removed vs failed split)."""

    model_config = _CFG

    added_users: list[dict[str, Any]] = Field(default_factory=list)
    removed_users: list[dict[str, Any]] = Field(default_factory=list)
    failed_users: list[dict[str, Any]] = Field(default_factory=list)


class WhatsAppTokenExchange(BaseModel):
    """Embedded Signup code->token exchange result (BYOK: returned, never stored).

    ``token_type``/``expires_in`` are not in Meta's documented response —
    treat them as optional. Business Integration System User tokens default
    to never expiring.
    """

    model_config = _CFG

    access_token: str = ""
    token_type: str = ""
    expires_in: int = 0


class WhatsAppGranularScope(BaseModel):
    """One granular scope grant, with the asset ids it applies to."""

    model_config = _CFG

    scope: str = ""
    target_ids: list[str] = Field(default_factory=list)

    @field_validator("target_ids", mode="before")
    @classmethod
    def _stringify_ids(cls, value: Any) -> Any:
        # Meta's reference types these int[] but real ES responses send
        # strings — accept both, normalize to str.
        if isinstance(value, list):
            return [str(item) for item in value]
        return value


class WhatsAppTokenInfo(BaseModel):
    """``GET /debug_token`` result — what a token is and what it can reach.

    ``waba_ids`` is derived from the ``whatsapp_business_management`` /
    ``whatsapp_business_messaging`` granular scopes (most recently
    onboarded first), so a platform never has to ask the user for ids.
    """

    model_config = _CFG

    app_id: str = ""
    application: str = ""
    type: str = ""
    is_valid: bool = False
    user_id: str = ""
    issued_at: int = 0
    expires_at: int = 0
    data_access_expires_at: int = 0
    scopes: list[str] = Field(default_factory=list)
    granular_scopes: list[WhatsAppGranularScope] = Field(default_factory=list)
    waba_ids: list[str] = Field(default_factory=list)
    error: dict[str, Any] = Field(default_factory=dict)
