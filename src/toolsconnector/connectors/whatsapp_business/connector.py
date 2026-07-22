"""WhatsApp Business Platform (Cloud API) connector — official Meta API, BYOK.

Sends and manages WhatsApp messages through Meta's Cloud API (Graph v25.0),
the ONLY official WhatsApp API. No scraping, no unofficial clients: personal
WhatsApp accounts have no API, and reverse-engineered clients violate
WhatsApp's Terms of Service and get numbers banned — for the personal-side
use case (compose a message a human taps to send) use the offline
``whatsapp`` link connector instead.

BYOK credentials (JSON string or dict)::

    {"access_token": "<System User token>",       # whatsapp_business_messaging
     "phone_number_id": "<PHONE_NUMBER_ID>",      # + whatsapp_business_management
     "waba_id": "<WABA_ID>",                      # optional: WABA-level actions
     "app_secret": "<APP_SECRET>"}                # optional: webhook verify

Receiving messages is webhook-push only (no polling endpoint exists) — see
``toolsconnector.connectors.whatsapp_business.webhooks`` for the pure
verify/parse primitives; the HTTPS listener is yours.

Pricing reality (per-message model, since 2025-07-01): free-form ("service")
messages are free but only allowed within 24 h of the user's last inbound
message; outside that window only approved templates can be sent, billed per
delivered message (utility templates inside an open window are free).

Docs: https://developers.facebook.com/documentation/business-messaging/whatsapp
Wire shapes verified 2026-07-22 (.agent/artifacts/whatsapp-wire-register.md).
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from toolsconnector.connectors._helpers import (
    coerce_optional_int,
    raise_typed_for_status,
    safe_int,
    safe_validate,
    scrub_secret,
    validate_list,
)
from toolsconnector.errors import (
    APIError,
    InvalidCredentialsError,
    MissingConfigError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    TokenExpiredError,
    TransportError,
    ValidationError,
)
from toolsconnector.errors import (
    ConnectionError as ToolsConnectorConnectionError,
)
from toolsconnector.errors import (
    TimeoutError as ToolsConnectorTimeoutError,
)
from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.auth import APIKeySpec, AuthProviderSpec, AuthType
from toolsconnector.spec.connector import ConnectorCategory, ProtocolType, RateLimitSpec
from toolsconnector.types import PageState, PaginatedList

from .types import (
    WhatsAppBlockResult,
    WhatsAppBusinessProfile,
    WhatsAppFlow,
    WhatsAppFlowAsset,
    WhatsAppFlowMutationResult,
    WhatsAppMarketingEligibility,
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

logger = logging.getLogger(__name__)

_TOKEN_KEYS = ("access_token", "token", "bearer_token", "api_key")
_PHONE_ID_KEYS = ("phone_number_id", "phone_id", "from_phone_number_id")
_WABA_KEYS = ("waba_id", "whatsapp_business_account_id", "business_account_id")
_SECRET_KEYS = ("app_secret", "client_secret")
_APP_ID_KEYS = ("app_id", "client_id")

# Graph error codes -> typed errors (HTTP status alone is unreliable: the
# Cloud API returns 400 for most failures with the real code in the body).
_RATE_LIMIT_CODES = {4, 17, 80007, 130429, 131048, 131056, 133016}
_AUTH_CODES = {190, 0}
# 139000 Blocked by Integrity (business-verification / quality gate),
# 131215 Groups not eligible, 138000 Calling not enabled — all "your account
# may not do this", not server faults (live-verified 2026-07-23).
_PERMISSION_CODES = {10, 200, 299, 131031, 131215, 138000, 139000}
# 134100 = Marketing Messages API given a non-marketing template.
_VALIDATION_CODES = {100, 131008, 131009, 131051, 130501, 134100}

_MAX_BUTTONS = 3
_MAX_LIST_ROWS = 10


@dataclass(frozen=True)
class _Credentials:
    access_token: str
    phone_number_id: str
    waba_id: str
    app_secret: str
    app_id: str = ""


def _parse_credentials(raw: Any) -> _Credentials:
    """Accept a JSON string or dict; tolerate common key aliases.

    ``None`` yields empty credentials — the connector must instantiate
    without credentials (repo contract); the token is enforced at
    ``_setup`` time instead.
    """
    if raw is None:
        return _Credentials("", "", "", "", "")
    data: Any = raw
    if isinstance(data, str):
        text = data.strip()
        if text.startswith("{"):
            try:
                data = json.loads(text)
            except ValueError as exc:
                raise MissingConfigError(
                    "whatsapp_business credentials look like JSON but do not parse.",
                    connector="whatsapp_business",
                    suggestion=(
                        'Pass {"access_token": ..., "phone_number_id": ...}'
                        " as a dict or JSON string."
                    ),
                ) from exc
        else:
            # A bare token: allowed, but phone-scoped actions need the id.
            data = {"access_token": text}
    if not isinstance(data, dict):
        raise MissingConfigError(
            "whatsapp_business credentials must be a dict or JSON string.",
            connector="whatsapp_business",
        )

    def pick(keys: tuple[str, ...]) -> str:
        for key in keys:
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    return _Credentials(
        access_token=pick(_TOKEN_KEYS),
        phone_number_id=pick(_PHONE_ID_KEYS),
        waba_id=pick(_WABA_KEYS),
        app_secret=pick(_SECRET_KEYS),
        app_id=pick(_APP_ID_KEYS),
    )


class WhatsAppBusiness(BaseConnector):
    """Send, receive (via webhooks), and manage WhatsApp via Meta's Cloud API.

    One connector covers the whole official surface — messaging, media,
    templates, business profile, and phone-number operations — because Meta
    exposes them behind one credential set (connector boundary = credential).
    """

    name = "whatsapp_business"
    display_name = "WhatsApp Business"
    category = ConnectorCategory.COMMUNICATION
    protocol = ProtocolType.REST
    base_url = "https://graph.facebook.com/v25.0"
    # Tier 1 — LIVE-verified 2026-07-22/23 against a real Meta test WABA
    # (Graph v25.0), contract-scoped like contactout: 50/64 actions
    # round-tripped with device-confirmed delivery of all 11 message types
    # (text, threaded reply, image, document, location, contacts, buttons,
    # list, cta_url, location_request, hello_world template) + media
    # upload->5-min-URL->download byte-identical + business-profile
    # write->read-back + production error codes (132001, 131030, invalid
    # token; no secret leakage). Webhook receive verified END-TO-END
    # 2026-07-23 (Meta -> tunnel -> localhost): real inbound messages
    # parsed (unicode+emoji through signature verify), Meta's duplicate
    # redelivery observed, outbound 'sent' statuses received, and
    # mark_as_read/send_typing_indicator/send_reaction round-tripped on a
    # real inbound wamid (device-confirmed). Webhook setup itself was done
    # 100% via API (POST /{APP_ID}/subscriptions app-token + POST
    # /{WABA_ID}/subscribed_apps). NOT live-verified (honest scope):
    # send_interactive escape hatch (gated Flows/catalog/address setup),
    # edit_template (needs an owned APPROVED template; 1 edit/24h),
    # get_template_analytics (insights opt-in enabled live; Meta data lags
    # ~24h and needs send volume), unblock_users (nothing blocked), and
    # the 6 phone-lifecycle/block mutations (register/deregister/
    # request_code/verify_code/set_two_step_pin/block_users) — protective
    # skip: they act on the credentials' own phone_number_id and would
    # disrupt or lock the live test number. All 13 are request-shape
    # pinned by tests and marked dangerous=True so platforms can filter
    # them with ToolKit(exclude_dangerous=True).
    # per-WABA override_callback_uri (Meta 400s until an app-level
    # dashboard-context subscription exists). Live lesson: a
    # degenerate 1x1 PNG was API-ACCEPTED (wamid returned) but silently
    # dropped by WhatsApp's media pipeline before delivery — "accepted !=
    # delivered"; only the statuses webhook reveals such failures.
    verification_status = "live"
    description = (
        "WhatsApp Business Platform (Cloud API) — Meta's official WhatsApp"
        " API (BYOK: your Meta app + System User token). Free-form sends"
        " within the 24h customer-service window, template sends outside it,"
        " media up/download, business profile, and webhook receive"
        " primitives. Personal WhatsApp accounts have no API — for"
        " human-in-the-loop links use the 'whatsapp' connector."
    )
    # Cloud API default throughput is 80 msgs/sec per number.
    _rate_limit_config = RateLimitSpec(rate=80, period=1, burst=20)
    # Machine-readable credential contract: platforms render their
    # "connect" form from this instead of parsing the README.
    _default_auth_type = AuthType.BEARER_TOKEN
    _auth_providers_config = [
        AuthProviderSpec(
            type=AuthType.BEARER_TOKEN,
            api_key=APIKeySpec(location="header", param_name="Authorization", prefix="Bearer"),
            extra={
                "credential_format": "json",
                "env_var": "TC_WHATSAPP_BUSINESS_CREDENTIALS",
                "obtain_url": "https://developers.facebook.com/apps/",
                "docs_url": (
                    "https://developers.facebook.com/documentation/"
                    "business-messaging/whatsapp/access-tokens"
                ),
                "scopes": [
                    "whatsapp_business_messaging",
                    "whatsapp_business_management",
                ],
                "fields": [
                    {
                        "name": "access_token",
                        "label": "System User access token",
                        "required": True,
                        "secret": True,
                        "help": (
                            "Business Settings > System users > Generate token"
                            " with both whatsapp_business_* permissions."
                            " Never-expiring is supported."
                        ),
                    },
                    {
                        "name": "phone_number_id",
                        "label": "Phone number ID",
                        "required": True,
                        "secret": False,
                        "help": (
                            "WhatsApp > API Setup. Required by every"
                            " messaging and phone-scoped action."
                        ),
                    },
                    {
                        "name": "waba_id",
                        "label": "WhatsApp Business Account ID",
                        "required": False,
                        "secret": False,
                        "help": (
                            "Needed for templates, flows, analytics and"
                            " webhook subscription actions."
                        ),
                    },
                    {
                        "name": "app_secret",
                        "label": "Meta app secret",
                        "required": False,
                        "secret": True,
                        "help": (
                            "Only for webhook signature verification and the"
                            " Embedded Signup actions."
                        ),
                    },
                    {
                        "name": "app_id",
                        "label": "Meta app ID",
                        "required": False,
                        "secret": False,
                        "help": (
                            "Only for Embedded Signup (exchange_code /"
                            " debug_token / set_app_webhook)."
                        ),
                    },
                ],
            },
        ),
    ]

    def __init__(self, credentials: Any = None, **kwargs: Any) -> None:
        super().__init__(credentials=credentials, **kwargs)
        self._creds = _parse_credentials(self._credentials)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        # A platform bootstrapping Embedded Signup has only app credentials
        # until the customer's token comes back from exchange_code, so an
        # app_secret alone is a valid configuration.
        if not self._creds.access_token and not self._creds.app_secret:
            raise MissingConfigError(
                "whatsapp_business credentials are missing the access token.",
                connector=self.name,
                suggestion=(
                    "Provide a System User token as 'access_token' with"
                    " whatsapp_business_messaging +"
                    " whatsapp_business_management permissions"
                    " (TC_WHATSAPP_BUSINESS_CREDENTIALS accepts the full"
                    " JSON). For Embedded Signup bootstrap, 'app_id' +"
                    " 'app_secret' alone are enough to call exchange_code."
                ),
            )
        headers = {"Accept": "application/json"}
        if self._creds.access_token:
            headers["Authorization"] = f"Bearer {self._creds.access_token}"
        self._client = httpx.AsyncClient(
            base_url=self._base_url or self.__class__.base_url,
            headers=headers,
            timeout=self._timeout,
        )

    async def _teardown(self) -> None:
        if hasattr(self, "_client"):
            await self._client.aclose()

    # ------------------------------------------------------------------
    # HTTP + error boundary
    # ------------------------------------------------------------------

    def _phone_path(self, suffix: str = "messages") -> str:
        if not self._creds.phone_number_id:
            raise MissingConfigError(
                "This action needs 'phone_number_id' in the credentials.",
                connector=self.name,
            )
        return f"/{self._creds.phone_number_id}/{suffix}"

    def _waba_path(self, suffix: str) -> str:
        if not self._creds.waba_id:
            raise MissingConfigError(
                "This action needs 'waba_id' in the credentials.",
                connector=self.name,
            )
        return f"/{self._creds.waba_id}/{suffix}"

    def _raise_graph_error(self, response: httpx.Response, action_name: str) -> None:
        """Map Graph error-body codes to typed errors, then fall back to HTTP."""
        if response.status_code < 400:
            return
        try:
            err = response.json().get("error", {})
        except ValueError:
            err = {}
        if not isinstance(err, dict):
            err = {}
        # 0 is a REAL Graph AuthException code, so "code missing/unparseable"
        # must be distinguishable from it (else HTML proxy pages and codeless
        # bodies would read as invalid-credentials).
        code_raw = err.get("code")
        has_code = code_raw is not None and safe_int(code_raw, -1) >= 0
        code = safe_int(code_raw, -1) if has_code else -1
        subcode = safe_int(err.get("error_subcode"), 0)
        message = str(err.get("message") or "")[:300]
        details = {
            "graph_code": code,
            "graph_subcode": subcode,
            "fbtrace_id": err.get("fbtrace_id", ""),
            "error_user_msg": err.get("error_user_msg", ""),
            "error_data": err.get("error_data", {}),
        }
        kwargs: dict[str, Any] = {
            "connector": self.name,
            "action": action_name,
            "details": details,
        }
        if has_code and code in _AUTH_CODES and response.status_code in (400, 401):
            if subcode == 463 or "expired" in message.lower():
                raise TokenExpiredError(f"WhatsApp access token expired: {message}", **kwargs)
            raise InvalidCredentialsError(
                f"WhatsApp rejected the access token: {message}", **kwargs
            )
        if code in _RATE_LIMIT_CODES:
            raise RateLimitError(
                f"WhatsApp rate/messaging limit hit (code {code}): {message}",
                **kwargs,
            )
        if code in _PERMISSION_CODES:
            raise PermissionDeniedError(
                f"WhatsApp permission denied (code {code}): {message}", **kwargs
            )
        if code in _VALIDATION_CODES:
            raise ValidationError(
                f"WhatsApp rejected the request (code {code}): {message}",
                **kwargs,
            )
        if response.status_code >= 500 or code in {1, 2, 131000, 131016}:
            raise ServerError(f"WhatsApp server error (code {code}): {message}", **kwargs)
        if has_code and code > 0:
            raise APIError(f"WhatsApp API error (code {code}): {message}", **kwargs)
        # No usable Graph code: let the HTTP status decide (400->Validation,
        # 401->auth, 403->permission, ...).
        raise_typed_for_status(response, connector=self.name, action=action_name)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
        files: Optional[dict[str, Any]] = None,
        data: Optional[dict[str, Any]] = None,
        absolute_url: Optional[str] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        if not hasattr(self, "_client"):
            raise ToolsConnectorConnectionError(
                "Connector is not set up (use it as a context manager or call _setup()).",
                connector=self.name,
            )
        # App-scoped calls (Embedded Signup bootstrap) carry their own
        # credentials; everything else needs the user/System-User token.
        carries_own_auth = bool(headers and "Authorization" in headers) or bool(
            params and "client_secret" in params
        )
        if not self._creds.access_token and not carries_own_auth:
            raise MissingConfigError(
                f"{path} needs an 'access_token' in the credentials"
                " (app_id/app_secret alone only cover Embedded Signup"
                " bootstrap actions).",
                connector=self.name,
            )
        try:
            try:
                response = await self._client.request(
                    method,
                    absolute_url or path,
                    json=json_body,
                    params=params,
                    files=files,
                    data=data,
                    headers=headers,
                )
            except httpx.InvalidURL as exc:
                raise ValidationError(
                    f"Invalid URL for {path}: {exc}", connector=self.name
                ) from exc
            except httpx.TimeoutException as exc:
                raise ToolsConnectorTimeoutError(
                    f"WhatsApp request timed out: {path}", connector=self.name
                ) from exc
            except httpx.ConnectError as exc:
                raise ToolsConnectorConnectionError(
                    f"Cannot reach graph.facebook.com: {exc}",
                    connector=self.name,
                ) from exc
            except httpx.HTTPError as exc:
                raise TransportError(
                    f"Transport failure calling WhatsApp: {exc}",
                    connector=self.name,
                ) from exc
            except RuntimeError as exc:
                raise ToolsConnectorConnectionError(
                    "Connector is not set up (use it as a context manager or call _setup()).",
                    connector=self.name,
                ) from exc
            self._raise_graph_error(response, path)
            if response.status_code == 204:
                return {}
            try:
                body = response.json()
            except ValueError:
                return {}
            return body if isinstance(body, dict) else {}
        except Exception as exc:
            scrub_secret(exc, self._creds.access_token)
            scrub_secret(exc, self._creds.app_secret)
            raise

    async def _download(self, url: str) -> httpx.Response:
        """Authenticated GET of a lookaside media URL (returns raw response)."""
        if not hasattr(self, "_client"):
            raise ToolsConnectorConnectionError(
                "Connector is not set up (use it as a context manager or call _setup()).",
                connector=self.name,
            )
        try:
            try:
                response = await self._client.get(url)
            except httpx.TimeoutException as exc:
                raise ToolsConnectorTimeoutError(
                    "WhatsApp media download timed out.", connector=self.name
                ) from exc
            except httpx.HTTPError as exc:
                raise TransportError(
                    f"Transport failure downloading media: {exc}",
                    connector=self.name,
                ) from exc
            if response.status_code >= 400:
                self._raise_graph_error(response, "media_download")
            return response
        except Exception as exc:
            scrub_secret(exc, self._creds.access_token)
            scrub_secret(exc, self._creds.app_secret)
            raise

    # ------------------------------------------------------------------
    # Send helpers
    # ------------------------------------------------------------------

    def _require_to(self, to: str) -> str:
        cleaned = str(to).strip()
        if not cleaned:
            raise ValidationError(
                "'to' must be a non-empty E.164 phone number.",
                connector=self.name,
            )
        return cleaned

    async def _send(
        self,
        to: str,
        message_type: str,
        payload: dict[str, Any],
        *,
        reply_to: Optional[str] = None,
        tracking_data: Optional[str] = None,
    ) -> WhatsAppSendResult:
        body: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": self._require_to(to),
            "type": message_type,
            message_type: payload,
        }
        if reply_to:
            body["context"] = {"message_id": reply_to}
        if tracking_data:
            body["biz_opaque_callback_data"] = tracking_data
        raw = await self._request("POST", self._phone_path(), json_body=body)
        return safe_validate(WhatsAppSendResult, raw) or WhatsAppSendResult()

    @staticmethod
    def _media_ref(media_id: Optional[str], link: Optional[str], **extra: Any) -> dict[str, Any]:
        if bool(media_id) == bool(link):
            raise ValidationError(
                "Provide exactly one of the media id or the https link.",
                connector="whatsapp_business",
            )
        ref: dict[str, Any] = {"id": media_id} if media_id else {"link": link}
        for key, value in extra.items():
            if value is not None:
                ref[key] = value
        return ref

    # ------------------------------------------------------------------
    # Messaging actions (free-form types need an open 24h service window)
    # ------------------------------------------------------------------

    @action("Send a WhatsApp text message (24h window)")
    async def send_text(
        self,
        to: str,
        body: str,
        preview_url: bool = False,
        reply_to: Optional[str] = None,
        tracking_data: Optional[str] = None,
    ) -> WhatsAppSendResult:
        """Send a free-form text message.

        Endpoint: ``POST /<PHONE_NUMBER_ID>/messages``.

        Only deliverable inside the 24-hour customer-service window (i.e.
        the user messaged you within the last 24h); outside it use
        ``send_template``.

        Args:
            to: Recipient phone number in E.164 digits.
            body: Message text, up to 4096 characters.
            preview_url: Render a URL preview for the first link in body.
            reply_to: Optional wamid to reply to (threads the message).
            tracking_data: Optional string echoed back on status webhooks
                as ``biz_opaque_callback_data`` (correlate to your ids).

        Returns:
            Send envelope with the new message's wamid.
        """
        text = str(body)
        if not text or len(text) > 4096:
            raise ValidationError("text body must be 1..4096 characters.", connector=self.name)
        return await self._send(
            to,
            "text",
            {"body": text, "preview_url": bool(preview_url)},
            reply_to=reply_to,
            tracking_data=tracking_data,
        )

    @action("Send an image (24h window)")
    async def send_image(
        self,
        to: str,
        image_id: Optional[str] = None,
        image_url: Optional[str] = None,
        caption: Optional[str] = None,
        reply_to: Optional[str] = None,
        tracking_data: Optional[str] = None,
    ) -> WhatsAppSendResult:
        """Send an image (JPEG/PNG, ≤5 MB) by uploaded media id or public URL.

        Endpoint: ``POST /<PHONE_NUMBER_ID>/messages``.

        Args:
            to: Recipient number (E.164 digits).
            image_id: Media id from ``upload_media`` (preferred).
            image_url: Public https link (exactly one of id/url).
            caption: Optional caption text.
            reply_to: Optional wamid to reply to.
            tracking_data: Echoed back on status webhooks.
        """
        return await self._send(
            to,
            "image",
            self._media_ref(image_id, image_url, caption=caption),
            reply_to=reply_to,
            tracking_data=tracking_data,
        )

    @action("Send an audio clip or voice note (24h window)")
    async def send_audio(
        self,
        to: str,
        audio_id: Optional[str] = None,
        audio_url: Optional[str] = None,
        reply_to: Optional[str] = None,
        tracking_data: Optional[str] = None,
    ) -> WhatsAppSendResult:
        """Send audio (AAC/AMR/MP3/M4A/OGG-opus, ≤16 MB).

        Endpoint: ``POST /<PHONE_NUMBER_ID>/messages``.

        Args:
            to: Recipient number (E.164 digits).
            audio_id: Media id from ``upload_media`` (preferred).
            audio_url: Public https link (exactly one of id/url).
            reply_to: Optional wamid to reply to.
            tracking_data: Echoed back on status webhooks.
        """
        return await self._send(
            to,
            "audio",
            self._media_ref(audio_id, audio_url),
            reply_to=reply_to,
            tracking_data=tracking_data,
        )

    @action("Send a video (24h window)")
    async def send_video(
        self,
        to: str,
        video_id: Optional[str] = None,
        video_url: Optional[str] = None,
        caption: Optional[str] = None,
        reply_to: Optional[str] = None,
        tracking_data: Optional[str] = None,
    ) -> WhatsAppSendResult:
        """Send a video (MP4/3GPP, H.264+AAC, ≤16 MB).

        Endpoint: ``POST /<PHONE_NUMBER_ID>/messages``.

        Args:
            to: Recipient number (E.164 digits).
            video_id: Media id from ``upload_media`` (preferred).
            video_url: Public https link (exactly one of id/url).
            caption: Optional caption text.
            reply_to: Optional wamid to reply to.
            tracking_data: Echoed back on status webhooks.
        """
        return await self._send(
            to,
            "video",
            self._media_ref(video_id, video_url, caption=caption),
            reply_to=reply_to,
            tracking_data=tracking_data,
        )

    @action("Send a document (24h window)")
    async def send_document(
        self,
        to: str,
        document_id: Optional[str] = None,
        document_url: Optional[str] = None,
        caption: Optional[str] = None,
        filename: Optional[str] = None,
        reply_to: Optional[str] = None,
        tracking_data: Optional[str] = None,
    ) -> WhatsAppSendResult:
        """Send a document (PDF/Office/TXT, ≤100 MB).

        Endpoint: ``POST /<PHONE_NUMBER_ID>/messages``.

        Args:
            to: Recipient number (E.164 digits).
            document_id: Media id from ``upload_media`` (preferred).
            document_url: Public https link (exactly one of id/url).
            caption: Optional caption text.
            filename: Filename shown to the recipient.
            reply_to: Optional wamid to reply to.
            tracking_data: Echoed back on status webhooks.
        """
        return await self._send(
            to,
            "document",
            self._media_ref(document_id, document_url, caption=caption, filename=filename),
            reply_to=reply_to,
            tracking_data=tracking_data,
        )

    @action("Send a sticker (24h window)")
    async def send_sticker(
        self,
        to: str,
        sticker_id: Optional[str] = None,
        sticker_url: Optional[str] = None,
        reply_to: Optional[str] = None,
        tracking_data: Optional[str] = None,
    ) -> WhatsAppSendResult:
        """Send a WebP sticker (static ≤100 KB, animated ≤500 KB).

        Endpoint: ``POST /<PHONE_NUMBER_ID>/messages``.

        Args:
            to: Recipient number (E.164 digits).
            sticker_id: Media id from ``upload_media`` (preferred).
            sticker_url: Public https link (exactly one of id/url).
            reply_to: Optional wamid to reply to.
            tracking_data: Echoed back on status webhooks.
        """
        return await self._send(
            to,
            "sticker",
            self._media_ref(sticker_id, sticker_url),
            reply_to=reply_to,
            tracking_data=tracking_data,
        )

    @action("Send a location pin (24h window)")
    async def send_location(
        self,
        to: str,
        latitude: float,
        longitude: float,
        name: Optional[str] = None,
        address: Optional[str] = None,
        reply_to: Optional[str] = None,
        tracking_data: Optional[str] = None,
    ) -> WhatsAppSendResult:
        """Send a location message.

        Endpoint: ``POST /<PHONE_NUMBER_ID>/messages``.

        Args:
            to: Recipient number (E.164 digits).
            latitude: Latitude in decimal degrees.
            longitude: Longitude in decimal degrees.
            name: Optional location label.
            address: Optional address line shown under the name.
            reply_to: Optional wamid to reply to.
            tracking_data: Echoed back on status webhooks.
        """
        try:
            payload: dict[str, Any] = {
                "latitude": float(latitude),
                "longitude": float(longitude),
            }
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "latitude/longitude must be numeric decimal degrees.",
                connector=self.name,
            ) from exc
        if name:
            payload["name"] = name
        if address:
            payload["address"] = address
        return await self._send(
            to,
            "location",
            payload,
            reply_to=reply_to,
            tracking_data=tracking_data,
        )

    @action("Send contact cards (24h window)")
    async def send_contacts(
        self,
        to: str,
        contacts: list[dict[str, Any]],
        reply_to: Optional[str] = None,
        tracking_data: Optional[str] = None,
    ) -> WhatsAppSendResult:
        """Send one or more vCard-style contact cards.

        Endpoint: ``POST /<PHONE_NUMBER_ID>/messages``.

        Args:
            to: Recipient number (E.164 digits).
            contacts: Contact objects, each like
                ``{"name": {"formatted_name": "Ada"},
                "phones": [{"phone": "+1555...", "type": "CELL"}]}``.
            reply_to: Optional wamid to reply to.
            tracking_data: Echoed back on status webhooks.
        """
        if not contacts:
            raise ValidationError("contacts must be a non-empty list.", connector=self.name)
        body: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": self._require_to(to),
            "type": "contacts",
            "contacts": contacts,
        }
        if reply_to:
            body["context"] = {"message_id": reply_to}
        if tracking_data:
            body["biz_opaque_callback_data"] = tracking_data
        raw = await self._request("POST", self._phone_path(), json_body=body)
        return safe_validate(WhatsAppSendResult, raw) or WhatsAppSendResult()

    @action("React to a message with an emoji")
    async def send_reaction(
        self,
        to: str,
        message_id: str,
        emoji: str = "",
    ) -> WhatsAppSendResult:
        """Add (or remove) an emoji reaction on a received message.

        Endpoint: ``POST /<PHONE_NUMBER_ID>/messages``.

        Args:
            to: The chat's phone number (E.164 digits).
            message_id: The wamid of the message to react to.
            emoji: A single emoji; empty string removes your reaction.
        """
        if not message_id:
            raise ValidationError("message_id (wamid) is required.", connector=self.name)
        return await self._send(to, "reaction", {"message_id": message_id, "emoji": emoji})

    # ------------------------------------------------------------------
    # Interactive messages (agent-friendly structured choices)
    # ------------------------------------------------------------------

    @action("Send up to 3 tappable reply buttons (24h window)")
    async def send_interactive_buttons(
        self,
        to: str,
        body: str,
        buttons: list[dict[str, str]],
        header_text: Optional[str] = None,
        footer_text: Optional[str] = None,
        reply_to: Optional[str] = None,
        tracking_data: Optional[str] = None,
    ) -> WhatsAppSendResult:
        """Send reply buttons; the tap comes back as ``interactive.button_reply``.

        Endpoint: ``POST /<PHONE_NUMBER_ID>/messages``.

        Args:
            to: Recipient number (E.164 digits).
            body: Body text (≤1024 chars).
            buttons: 1-3 items of ``{"id": "<≤256>", "title": "<≤20>"}`` —
                the id is returned verbatim in the reply webhook.
            header_text: Optional text header (≤60 chars).
            footer_text: Optional footer (≤60 chars).
            reply_to: Optional wamid to reply to.
            tracking_data: Echoed back on status webhooks.
        """
        if not buttons or len(buttons) > _MAX_BUTTONS:
            raise ValidationError(
                f"buttons must contain 1..{_MAX_BUTTONS} items.",
                connector=self.name,
            )
        interactive: dict[str, Any] = {
            "type": "button",
            "body": {"text": body},
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": str(b.get("id", "")),
                            "title": str(b.get("title", "")),
                        },
                    }
                    for b in buttons
                ]
            },
        }
        if header_text:
            interactive["header"] = {"type": "text", "text": header_text}
        if footer_text:
            interactive["footer"] = {"text": footer_text}
        return await self._send(
            to,
            "interactive",
            interactive,
            reply_to=reply_to,
            tracking_data=tracking_data,
        )

    @action("Send a selectable list menu (24h window)")
    async def send_interactive_list(
        self,
        to: str,
        body: str,
        button_text: str,
        sections: list[dict[str, Any]],
        header_text: Optional[str] = None,
        footer_text: Optional[str] = None,
        reply_to: Optional[str] = None,
        tracking_data: Optional[str] = None,
    ) -> WhatsAppSendResult:
        """Send a list message; the pick comes back as ``interactive.list_reply``.

        Endpoint: ``POST /<PHONE_NUMBER_ID>/messages``.

        Args:
            to: Recipient number (E.164 digits).
            body: Body text (≤4096 chars).
            button_text: Label of the list-opening button (≤20 chars).
            sections: Up to 10 sections, 10 rows TOTAL across all sections;
                each section ``{"title": ..., "rows": [{"id", "title",
                "description"?}]}`` (row title ≤24, description ≤72).
            header_text: Optional text header (≤60 chars).
            footer_text: Optional footer (≤60 chars).
            reply_to: Optional wamid to reply to.
            tracking_data: Echoed back on status webhooks.
        """
        if not sections:
            raise ValidationError("sections must be a non-empty list.", connector=self.name)
        total_rows = sum(len(s.get("rows", [])) for s in sections if isinstance(s, dict))
        if total_rows == 0 or total_rows > _MAX_LIST_ROWS:
            raise ValidationError(
                f"list messages allow 1..{_MAX_LIST_ROWS} rows total (got {total_rows}).",
                connector=self.name,
            )
        interactive: dict[str, Any] = {
            "type": "list",
            "body": {"text": body},
            "action": {"button": button_text, "sections": sections},
        }
        if header_text:
            interactive["header"] = {"type": "text", "text": header_text}
        if footer_text:
            interactive["footer"] = {"text": footer_text}
        return await self._send(
            to,
            "interactive",
            interactive,
            reply_to=reply_to,
            tracking_data=tracking_data,
        )

    @action("Send a call-to-action URL button (24h window)")
    async def send_cta_url(
        self,
        to: str,
        body: str,
        display_text: str,
        url: str,
        header_text: Optional[str] = None,
        footer_text: Optional[str] = None,
        reply_to: Optional[str] = None,
        tracking_data: Optional[str] = None,
    ) -> WhatsAppSendResult:
        """Send a message with a single URL button.

        Endpoint: ``POST /<PHONE_NUMBER_ID>/messages``.

        Args:
            to: Recipient number (E.164 digits).
            body: Body text.
            display_text: Button label.
            url: The https URL the button opens.
            header_text: Optional text header.
            footer_text: Optional footer.
            reply_to: Optional wamid to reply to.
            tracking_data: Echoed back on status webhooks.
        """
        interactive: dict[str, Any] = {
            "type": "cta_url",
            "body": {"text": body},
            "action": {
                "name": "cta_url",
                "parameters": {"display_text": display_text, "url": url},
            },
        }
        if header_text:
            interactive["header"] = {"type": "text", "text": header_text}
        if footer_text:
            interactive["footer"] = {"text": footer_text}
        return await self._send(
            to,
            "interactive",
            interactive,
            reply_to=reply_to,
            tracking_data=tracking_data,
        )

    @action("Ask the user to share their location (24h window)")
    async def send_location_request(
        self,
        to: str,
        body: str,
        reply_to: Optional[str] = None,
    ) -> WhatsAppSendResult:
        """Send a location-request message; the reply arrives as ``location``.

        Endpoint: ``POST /<PHONE_NUMBER_ID>/messages``.

        Args:
            to: Recipient number (E.164 digits).
            body: Prompt text shown above the "Send location" button.
            reply_to: Optional wamid to reply to.
        """
        interactive = {
            "type": "location_request_message",
            "body": {"text": body},
            "action": {"name": "send_location"},
        }
        return await self._send(to, "interactive", interactive, reply_to=reply_to)

    @action("Send a raw interactive payload (flows, products, address)")
    async def send_interactive(
        self,
        to: str,
        interactive: dict[str, Any],
        reply_to: Optional[str] = None,
        tracking_data: Optional[str] = None,
    ) -> WhatsAppSendResult:
        """Escape hatch for interactive subtypes without a dedicated action.

        Endpoint: ``POST /<PHONE_NUMBER_ID>/messages``.

        Covers ``flow``, ``product``, ``product_list``, ``catalog_message``,
        ``address_message``, and ``call_permission_request`` — pass the full
        ``interactive`` object per Meta's reference (these surfaces are
        gated by catalog/Flow/country setup on your WABA).

        Args:
            to: Recipient number (E.164 digits).
            interactive: Complete ``interactive`` object incl. ``type``.
            reply_to: Optional wamid to reply to.
            tracking_data: Echoed back on status webhooks.
        """
        if not interactive.get("type"):
            raise ValidationError("interactive payload needs a 'type' key.", connector=self.name)
        return await self._send(
            to,
            "interactive",
            interactive,
            reply_to=reply_to,
            tracking_data=tracking_data,
        )

    @action("Send an approved template (works outside the 24h window)")
    async def send_template(
        self,
        to: str,
        template_name: str,
        language_code: str = "en_US",
        components: Optional[list[dict[str, Any]]] = None,
        tracking_data: Optional[str] = None,
    ) -> WhatsAppSendResult:
        """Send a pre-approved template — the only type allowed outside the CSW.

        Endpoint: ``POST /<PHONE_NUMBER_ID>/messages``.

        Marketing/utility/authentication templates are billed per delivered
        message (utility is free inside an open service window). Requires
        prior user opt-in per WhatsApp policy.

        Args:
            to: Recipient number (E.164 digits).
            template_name: Approved template name (lowercase_underscore).
            language_code: Template language/locale, e.g. ``en_US``.
            components: Optional parameter components, e.g.
                ``[{"type": "body", "parameters": [{"type": "text",
                "text": "Ada"}]}]`` (carousel/coupon/LTO/auth buttons
                follow Meta's component reference verbatim).
            tracking_data: Echoed back on status webhooks.
        """
        if not template_name:
            raise ValidationError("template_name is required.", connector=self.name)
        payload: dict[str, Any] = {
            "name": template_name,
            "language": {"code": language_code},
        }
        if components is not None:
            payload["components"] = components
        return await self._send(to, "template", payload, tracking_data=tracking_data)

    # ------------------------------------------------------------------
    # Message management
    # ------------------------------------------------------------------

    @action("Mark a received message as read (blue ticks)")
    async def mark_as_read(self, message_id: str) -> WhatsAppSuccessResult:
        """Mark a message (and everything before it) as read.

        Endpoint: ``POST /<PHONE_NUMBER_ID>/messages``.

        Args:
            message_id: The inbound message's wamid (from the webhook).
        """
        if not message_id:
            raise ValidationError("message_id (wamid) is required.", connector=self.name)
        raw = await self._request(
            "POST",
            self._phone_path(),
            json_body={
                "messaging_product": "whatsapp",
                "status": "read",
                "message_id": message_id,
            },
        )
        return safe_validate(WhatsAppSuccessResult, raw) or WhatsAppSuccessResult()

    @action("Show a typing indicator in the chat")
    async def send_typing_indicator(self, message_id: str) -> WhatsAppSuccessResult:
        """Mark as read AND show typing (auto-dismisses after ~25s or on reply).

        Endpoint: ``POST /<PHONE_NUMBER_ID>/messages``.

        Args:
            message_id: The inbound message's wamid you are responding to.
        """
        if not message_id:
            raise ValidationError("message_id (wamid) is required.", connector=self.name)
        raw = await self._request(
            "POST",
            self._phone_path(),
            json_body={
                "messaging_product": "whatsapp",
                "status": "read",
                "message_id": message_id,
                "typing_indicator": {"type": "text"},
            },
        )
        return safe_validate(WhatsAppSuccessResult, raw) or WhatsAppSuccessResult()

    # ------------------------------------------------------------------
    # Media
    # ------------------------------------------------------------------

    @action("Upload media, returns a reusable media id (30 days)")
    async def upload_media(
        self,
        content_base64: str,
        mime_type: str,
        filename: str = "upload",
    ) -> WhatsAppUploadResult:
        """Upload a file to WhatsApp's media store.

        Endpoint: ``POST /<PHONE_NUMBER_ID>/media`` (multipart).

        Args:
            content_base64: File bytes, base64-encoded.
            mime_type: MIME type, e.g. ``image/jpeg`` — must match the
                supported type/size matrix for the target message type.
            filename: Filename for the multipart part.
        """
        if not content_base64:
            raise ValidationError("content_base64 is required.", connector=self.name)
        # 100 MB is the API's largest media limit (documents); base64 adds 4/3.
        if len(content_base64) > 140_000_000:
            raise ValidationError(
                "content_base64 exceeds the 100 MB Cloud API media limit.",
                connector=self.name,
            )
        try:
            blob = base64.b64decode(content_base64, validate=True)
        except Exception as exc:
            raise ValidationError(
                "content_base64 is not valid base64.", connector=self.name
            ) from exc
        raw = await self._request(
            "POST",
            self._phone_path("media"),
            files={"file": (filename, blob, mime_type)},
            data={"messaging_product": "whatsapp", "type": mime_type},
        )
        return safe_validate(WhatsAppUploadResult, raw) or WhatsAppUploadResult()

    @action("Get a media item's short-lived download URL")
    async def get_media_info(self, media_id: str) -> WhatsAppMediaInfo:
        """Look up a media id — the returned URL expires in ~5 minutes.

        Endpoint: ``GET /<MEDIA_ID>``.

        Args:
            media_id: Media id (from ``upload_media`` or an inbound webhook;
                webhook-delivered ids stay valid for 7 days).
        """
        if not media_id:
            raise ValidationError("media_id is required.", connector=self.name)
        raw = await self._request("GET", f"/{media_id}")
        return safe_validate(WhatsAppMediaInfo, raw) or WhatsAppMediaInfo()

    @action("Download media content (handles the 5-minute URL dance)")
    async def download_media(self, media_id: str) -> WhatsAppMediaContent:
        """Resolve the media URL and download the bytes in one call.

        Endpoints: ``GET /<MEDIA_ID>`` then authenticated ``GET <url>``.

        Args:
            media_id: Media id from an inbound webhook or upload.

        Returns:
            Base64 content + mime type (feed to vision/ASR or save to disk).
        """
        # `a`-prefixed siblings are bound at runtime by BaseConnector.
        info = await self.aget_media_info(media_id)  # type: ignore[attr-defined]
        if not info.url:
            raise APIError(
                f"Media {media_id} returned no download URL.",
                connector=self.name,
            )
        response = await self._download(info.url)
        blob = response.content
        return WhatsAppMediaContent(
            media_id=media_id,
            content_base64=base64.b64encode(blob).decode("ascii"),
            mime_type=info.mime_type or response.headers.get("content-type", ""),
            byte_size=len(blob),
            sha256=info.sha256,
        )

    @action("Delete an uploaded media item", dangerous=True)
    async def delete_media(self, media_id: str) -> WhatsAppSuccessResult:
        """Delete a media id from WhatsApp's store.

        Endpoint: ``DELETE /<MEDIA_ID>``.

        Args:
            media_id: The media id to delete.
        """
        if not media_id:
            raise ValidationError("media_id is required.", connector=self.name)
        raw = await self._request("DELETE", f"/{media_id}")
        return safe_validate(WhatsAppSuccessResult, raw) or WhatsAppSuccessResult()

    # ------------------------------------------------------------------
    # Business profile + phone numbers
    # ------------------------------------------------------------------

    @action("Get the business profile shown in the chat header")
    async def get_business_profile(self) -> WhatsAppBusinessProfile:
        """Fetch the number's public business profile.

        Endpoint: ``GET /<PHONE_NUMBER_ID>/whatsapp_business_profile``.
        """
        raw = await self._request(
            "GET",
            self._phone_path("whatsapp_business_profile"),
            params={
                "fields": ("about,address,description,email,profile_picture_url,websites,vertical")
            },
        )
        data = raw.get("data")
        first = data[0] if isinstance(data, list) and data and isinstance(data[0], dict) else {}
        return safe_validate(WhatsAppBusinessProfile, first) or WhatsAppBusinessProfile()

    @action("Update the business profile", dangerous=True)
    async def update_business_profile(
        self,
        about: Optional[str] = None,
        address: Optional[str] = None,
        description: Optional[str] = None,
        email: Optional[str] = None,
        websites: Optional[list[str]] = None,
        vertical: Optional[str] = None,
    ) -> WhatsAppSuccessResult:
        """Update public business-profile fields (only the ones provided).

        Endpoint: ``POST /<PHONE_NUMBER_ID>/whatsapp_business_profile``.

        Args:
            about: Short status line.
            address: Business address.
            description: Business description.
            email: Contact email.
            websites: Up to 2 website URLs.
            vertical: Industry vertical enum value (see Meta's reference).
        """
        body: dict[str, Any] = {"messaging_product": "whatsapp"}
        for key, value in (
            ("about", about),
            ("address", address),
            ("description", description),
            ("email", email),
            ("websites", websites),
            ("vertical", vertical),
        ):
            if value is not None:
                body[key] = value
        if len(body) == 1:
            raise ValidationError(
                "Provide at least one profile field to update.",
                connector=self.name,
            )
        raw = await self._request(
            "POST", self._phone_path("whatsapp_business_profile"), json_body=body
        )
        return safe_validate(WhatsAppSuccessResult, raw) or WhatsAppSuccessResult()

    @action("Get this number's quality, limits, and name status")
    async def get_phone_number(self) -> WhatsAppPhoneNumber:
        """Fetch the business phone-number node (health/limit monitoring).

        Endpoint: ``GET /<PHONE_NUMBER_ID>``.
        """
        raw = await self._request(
            "GET",
            self._phone_path("").rstrip("/"),
            params={
                "fields": (
                    "id,display_phone_number,verified_name,quality_rating,"
                    "code_verification_status,name_status,platform_type,"
                    "throughput,whatsapp_business_manager_messaging_limit"
                )
            },
        )
        return safe_validate(WhatsAppPhoneNumber, raw) or WhatsAppPhoneNumber.model_validate({})

    @action("List all phone numbers on the WhatsApp Business Account")
    async def list_phone_numbers(
        self,
        limit: int = 25,
        after: Optional[str] = None,
    ) -> PaginatedList[WhatsAppPhoneNumber]:
        """List the WABA's business phone numbers (cursor-paginated).

        Endpoint: ``GET /<WABA_ID>/phone_numbers`` (needs ``waba_id`` in
        the credentials).

        Args:
            limit: Page size (1..100).
            after: Cursor from the previous page.
        """
        size = max(1, min(safe_int(limit, 25), 100))
        params: dict[str, Any] = {
            "limit": size,
            "fields": (
                "id,display_phone_number,verified_name,quality_rating,"
                "code_verification_status,name_status,platform_type"
            ),
        }
        if after:
            params["after"] = after
        raw = await self._request("GET", self._waba_path("phone_numbers"), params=params)
        items = validate_list(WhatsAppPhoneNumber, raw.get("data"))
        paging_raw = raw.get("paging")
        paging: dict[str, Any] = paging_raw if isinstance(paging_raw, dict) else {}
        cursors_raw = paging.get("cursors")
        cursors: dict[str, Any] = cursors_raw if isinstance(cursors_raw, dict) else {}
        next_cursor = str(cursors.get("after") or "")
        has_more = bool(items) and bool(paging.get("next")) and bool(next_cursor)
        total = coerce_optional_int(raw.get("total_count"))
        result: PaginatedList[WhatsAppPhoneNumber] = PaginatedList(
            items=items,
            page_state=PageState(cursor=next_cursor or None, has_more=has_more, total_count=total),
        )
        if has_more:
            # `a`-prefixed sibling is bound at runtime by BaseConnector.
            result._fetch_next = lambda c=next_cursor: self.alist_phone_numbers(  # type: ignore[attr-defined]
                limit=size, after=c
            )
        return result

    # ------------------------------------------------------------------
    # Template management (WABA-level)
    # ------------------------------------------------------------------

    @action("Create a message template (goes to Meta review)")
    async def create_template(
        self,
        name: str,
        language: str,
        category: str,
        components: list[dict[str, Any]],
        parameter_format: Optional[str] = None,
    ) -> WhatsAppTemplateCreateResult:
        """Create a template on the WABA (max 100 creations/WABA/hour).

        Endpoint: ``POST /<WABA_ID>/message_templates``.

        Args:
            name: Template name (lowercase + underscores, <=512 chars).
            language: Locale code, e.g. ``en_US``.
            category: ``MARKETING`` | ``UTILITY`` | ``AUTHENTICATION``.
            components: HEADER/BODY/FOOTER/BUTTONS objects per Meta's
                reference (include ``example`` values for every variable).
            parameter_format: ``NAMED`` to use ``{{param_name}}`` variables
                (default is positional ``{{1}}``).
        """
        if not name or not components:
            raise ValidationError("name and components are required.", connector=self.name)
        body: dict[str, Any] = {
            "name": name,
            "language": language,
            "category": category,
            "components": components,
        }
        if parameter_format:
            body["parameter_format"] = parameter_format
        raw = await self._request("POST", self._waba_path("message_templates"), json_body=body)
        return safe_validate(WhatsAppTemplateCreateResult, raw) or WhatsAppTemplateCreateResult()

    @action("List message templates with status and quality")
    async def list_templates(
        self,
        status: Optional[str] = None,
        category: Optional[str] = None,
        language: Optional[str] = None,
        limit: int = 25,
        after: Optional[str] = None,
    ) -> PaginatedList[WhatsAppTemplate]:
        """List the WABA's templates (cursor-paginated — always follow paging).

        Endpoint: ``GET /<WABA_ID>/message_templates``.

        Args:
            status: Filter, e.g. ``APPROVED`` | ``REJECTED`` | ``PAUSED``.
            category: Filter by template category.
            language: Filter by locale code.
            limit: Page size (1..100).
            after: Cursor from the previous page.
        """
        size = max(1, min(safe_int(limit, 25), 100))
        params: dict[str, Any] = {
            "limit": size,
            "fields": (
                "id,name,language,category,status,parameter_format,quality_score,components"
            ),
        }
        for key, value in (
            ("status", status),
            ("category", category),
            ("language", language),
        ):
            if value:
                params[key] = value
        if after:
            params["after"] = after
        raw = await self._request("GET", self._waba_path("message_templates"), params=params)
        items = validate_list(WhatsAppTemplate, raw.get("data"))
        paging_raw = raw.get("paging")
        paging: dict[str, Any] = paging_raw if isinstance(paging_raw, dict) else {}
        cursors_raw = paging.get("cursors")
        cursors: dict[str, Any] = cursors_raw if isinstance(cursors_raw, dict) else {}
        next_cursor = str(cursors.get("after") or "")
        has_more = bool(items) and bool(paging.get("next")) and bool(next_cursor)
        result: PaginatedList[WhatsAppTemplate] = PaginatedList(
            items=items,
            page_state=PageState(cursor=next_cursor or None, has_more=has_more),
        )
        if has_more:
            # `a`-prefixed sibling is bound at runtime by BaseConnector.
            result._fetch_next = lambda c=next_cursor: self.alist_templates(  # type: ignore[attr-defined]
                status=status,
                category=category,
                language=language,
                limit=size,
                after=c,
            )
        return result

    @action("Get one template by id")
    async def get_template(self, template_id: str) -> WhatsAppTemplate:
        """Fetch a single template node.

        Endpoint: ``GET /<TEMPLATE_ID>``.

        Args:
            template_id: The template's numeric id (as a string).
        """
        if not template_id:
            raise ValidationError("template_id is required.", connector=self.name)
        raw = await self._request(
            "GET",
            f"/{template_id}",
            params={
                "fields": (
                    "id,name,language,category,status,parameter_format,quality_score,components"
                )
            },
        )
        return safe_validate(WhatsAppTemplate, raw) or WhatsAppTemplate()

    @action("Edit a template's components or category", dangerous=True)
    async def edit_template(
        self,
        template_id: str,
        components: Optional[list[dict[str, Any]]] = None,
        category: Optional[str] = None,
    ) -> WhatsAppSuccessResult:
        """Edit an APPROVED/REJECTED/PAUSED template.

        Endpoint: ``POST /<TEMPLATE_ID>``.

        Approved templates allow 10 edits/30 days (max 1/24h); the whole
        ``components`` array is replaced, not merged. An approved
        template's category cannot be changed.

        Args:
            template_id: The template's numeric id (as a string).
            components: Full replacement components array.
            category: New category (unapproved templates only).
        """
        if not template_id:
            raise ValidationError("template_id is required.", connector=self.name)
        body: dict[str, Any] = {}
        if components is not None:
            body["components"] = components
        if category:
            body["category"] = category
        if not body:
            raise ValidationError("Provide components and/or category.", connector=self.name)
        raw = await self._request("POST", f"/{template_id}", json_body=body)
        return safe_validate(WhatsAppSuccessResult, raw) or WhatsAppSuccessResult()

    @action("Delete a template by name (all languages)", dangerous=True)
    async def delete_template(
        self,
        name: str,
        template_id: Optional[str] = None,
    ) -> WhatsAppSuccessResult:
        """Delete a template (name reuse blocked for 30 days after).

        Endpoint: ``DELETE /<WABA_ID>/message_templates``.

        Args:
            name: Template name; deletes ALL language versions unless
                ``template_id`` narrows it to one.
            template_id: Optional numeric id (``hsm_id``) to delete a
                single language version.
        """
        if not name:
            raise ValidationError("name is required.", connector=self.name)
        params: dict[str, Any] = {"name": name}
        if template_id:
            params["hsm_id"] = template_id
        raw = await self._request("DELETE", self._waba_path("message_templates"), params=params)
        return safe_validate(WhatsAppSuccessResult, raw) or WhatsAppSuccessResult()

    # ------------------------------------------------------------------
    # QR codes / short links (wa.me/message/<code>)
    # ------------------------------------------------------------------

    @action("Create a managed QR code / short link")
    async def create_qr_code(
        self,
        prefilled_message: str,
        image_format: str = "SVG",
    ) -> WhatsAppQRCode:
        """Create a ``wa.me/message/<code>`` short link + QR image.

        Endpoint: ``POST /<PHONE_NUMBER_ID>/message_qrdls``.

        Args:
            prefilled_message: Message prefilled on scan (<=140 chars).
            image_format: ``SVG`` or ``PNG``.
        """
        message = str(prefilled_message)
        if not message or len(message) > 140:
            raise ValidationError(
                "prefilled_message must be 1..140 characters.",
                connector=self.name,
            )
        raw = await self._request(
            "POST",
            self._phone_path("message_qrdls"),
            json_body={
                "prefilled_message": message,
                "generate_qr_image": image_format,
            },
        )
        return safe_validate(WhatsAppQRCode, raw) or WhatsAppQRCode()

    @action("List managed QR codes")
    async def list_qr_codes(self, code: Optional[str] = None) -> list[WhatsAppQRCode]:
        """List QR codes on the number (max 2,000 exist per number).

        Endpoint: ``GET /<PHONE_NUMBER_ID>/message_qrdls``.

        Args:
            code: Optional single code to fetch.
        """
        path = self._phone_path("message_qrdls")
        if code:
            path = f"{path}/{code}"
        raw = await self._request("GET", path)
        return validate_list(WhatsAppQRCode, raw.get("data"))

    @action("Update a managed QR code's prefilled message", dangerous=True)
    async def update_qr_code(self, code: str, prefilled_message: str) -> WhatsAppQRCode:
        """Update the prefilled message behind an existing code.

        Endpoint: ``POST /<PHONE_NUMBER_ID>/message_qrdls``.

        Args:
            code: The QR code id to update.
            prefilled_message: New prefilled message (<=140 chars).
        """
        if not code:
            raise ValidationError("code is required.", connector=self.name)
        message = str(prefilled_message)
        if not message or len(message) > 140:
            raise ValidationError(
                "prefilled_message must be 1..140 characters.",
                connector=self.name,
            )
        raw = await self._request(
            "POST",
            self._phone_path("message_qrdls"),
            json_body={"code": code, "prefilled_message": message},
        )
        return safe_validate(WhatsAppQRCode, raw) or WhatsAppQRCode()

    @action("Delete a managed QR code", dangerous=True)
    async def delete_qr_code(self, code: str) -> WhatsAppSuccessResult:
        """Delete a QR code (scans then show "This QR code has expired").

        Endpoint: ``DELETE /<PHONE_NUMBER_ID>/message_qrdls/<code>``.

        Args:
            code: The QR code id to delete.
        """
        if not code:
            raise ValidationError("code is required.", connector=self.name)
        raw = await self._request("DELETE", self._phone_path(f"message_qrdls/{code}"))
        return safe_validate(WhatsAppSuccessResult, raw) or WhatsAppSuccessResult()

    # ------------------------------------------------------------------
    # Block list
    # ------------------------------------------------------------------

    @staticmethod
    def _block_payload(numbers: list[str]) -> dict[str, Any]:
        if not numbers or len(numbers) > 1000:
            raise ValidationError(
                "numbers must contain 1..1000 entries.",
                connector="whatsapp_business",
            )
        return {"messaging_product": "whatsapp", "block_users": [{"user": str(n)} for n in numbers]}

    @staticmethod
    def _block_result(raw: dict[str, Any]) -> WhatsAppBlockResult:
        nested = raw.get("block_users")
        source = nested if isinstance(nested, dict) else raw
        return safe_validate(WhatsAppBlockResult, source) or WhatsAppBlockResult()

    @action("Block users from messaging this number", dangerous=True)
    async def block_users(self, numbers: list[str]) -> WhatsAppBlockResult:
        """Block users (only those who messaged you in the last 24h).

        Endpoint: ``POST /<PHONE_NUMBER_ID>/block_users``.

        Args:
            numbers: 1..1000 wa_id / phone numbers to block
                (blocklist cap: 64,000).
        """
        raw = await self._request(
            "POST",
            self._phone_path("block_users"),
            json_body=self._block_payload(numbers),
        )
        return self._block_result(raw)

    @action("Unblock previously blocked users", dangerous=True)
    async def unblock_users(self, numbers: list[str]) -> WhatsAppBlockResult:
        """Remove users from the block list.

        Endpoint: ``DELETE /<PHONE_NUMBER_ID>/block_users``.

        Args:
            numbers: 1..1000 wa_id / phone numbers to unblock.
        """
        raw = await self._request(
            "DELETE",
            self._phone_path("block_users"),
            json_body=self._block_payload(numbers),
        )
        return self._block_result(raw)

    @action("List blocked users")
    async def list_blocked_users(
        self, limit: int = 100, after: Optional[str] = None
    ) -> dict[str, Any]:
        """List the number's block list (cursor-paginated raw envelope).

        Endpoint: ``GET /<PHONE_NUMBER_ID>/block_users``.

        Args:
            limit: Page size.
            after: Cursor from the previous page.
        """
        params: dict[str, Any] = {"limit": max(1, safe_int(limit, 100))}
        if after:
            params["after"] = after
        return await self._request("GET", self._phone_path("block_users"), params=params)

    # ------------------------------------------------------------------
    # Registration / verification / PIN
    # ------------------------------------------------------------------

    @action("Request a phone verification code (SMS or voice)", dangerous=True)
    async def request_verification_code(
        self, code_method: str = "SMS", language: str = "en_US"
    ) -> WhatsAppSuccessResult:
        """Ask Meta to send the ownership-verification code to the number.

        Endpoint: ``POST /<PHONE_NUMBER_ID>/request_code``.

        Args:
            code_method: ``SMS`` or ``VOICE``.
            language: Locale for the code message.
        """
        raw = await self._request(
            "POST",
            self._phone_path("request_code"),
            json_body={"code_method": code_method, "language": language},
        )
        return safe_validate(WhatsAppSuccessResult, raw) or WhatsAppSuccessResult()

    @action("Submit the phone verification code", dangerous=True)
    async def verify_code(self, code: str) -> WhatsAppSuccessResult:
        """Complete number-ownership verification.

        Endpoint: ``POST /<PHONE_NUMBER_ID>/verify_code``.

        Args:
            code: The code received via SMS/voice.
        """
        if not code:
            raise ValidationError("code is required.", connector=self.name)
        raw = await self._request("POST", self._phone_path("verify_code"), json_body={"code": code})
        return safe_validate(WhatsAppSuccessResult, raw) or WhatsAppSuccessResult()

    @action("Register the number for Cloud API messaging", dangerous=True)
    async def register_phone(
        self, pin: str, data_localization_region: Optional[str] = None
    ) -> WhatsAppSuccessResult:
        """Register the number (rate limit: 10 calls/number/72h).

        Endpoint: ``POST /<PHONE_NUMBER_ID>/register``.

        Args:
            pin: 6-digit two-step verification PIN.
            data_localization_region: Optional 2-letter region for local
                data storage (e.g. ``IN``, ``DE``, ``BR``).
        """
        if not pin:
            raise ValidationError("pin is required.", connector=self.name)
        body: dict[str, Any] = {"messaging_product": "whatsapp", "pin": str(pin)}
        if data_localization_region:
            body["data_localization_region"] = data_localization_region
        raw = await self._request("POST", self._phone_path("register"), json_body=body)
        return safe_validate(WhatsAppSuccessResult, raw) or WhatsAppSuccessResult()

    @action("Deregister the number from Cloud API", dangerous=True)
    async def deregister_phone(self) -> WhatsAppSuccessResult:
        """Disable Cloud API use for the number (does not delete it).

        Endpoint: ``POST /<PHONE_NUMBER_ID>/deregister``.
        """
        raw = await self._request("POST", self._phone_path("deregister"))
        return safe_validate(WhatsAppSuccessResult, raw) or WhatsAppSuccessResult()

    @action("Set the two-step verification PIN", dangerous=True)
    async def set_two_step_pin(self, pin: str) -> WhatsAppSuccessResult:
        """Change the number's 6-digit two-step PIN (no API to disable).

        Endpoint: ``POST /<PHONE_NUMBER_ID>``.

        Args:
            pin: New 6-digit PIN.
        """
        cleaned = str(pin)
        if len(cleaned) != 6 or not cleaned.isdigit():
            raise ValidationError("pin must be exactly 6 digits.", connector=self.name)
        raw = await self._request(
            "POST", self._phone_path("").rstrip("/"), json_body={"pin": cleaned}
        )
        return safe_validate(WhatsAppSuccessResult, raw) or WhatsAppSuccessResult()

    # ------------------------------------------------------------------
    # WABA + analytics
    # ------------------------------------------------------------------

    @action("Get the WhatsApp Business Account node")
    async def get_waba(self) -> WhatsAppWABA:
        """Fetch WABA name/currency/status/verification.

        Endpoint: ``GET /<WABA_ID>``.
        """
        raw = await self._request(
            "GET",
            self._waba_path("").rstrip("/"),
            params={"fields": ("id,name,currency,status,business_verification_status,country")},
        )
        return safe_validate(WhatsAppWABA, raw) or WhatsAppWABA()

    @action("Get message-volume analytics")
    async def get_messaging_analytics(
        self,
        start: int,
        end: int,
        granularity: str = "DAY",
        phone_numbers: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Sent/delivered volumes per time bucket (raw envelope).

        Endpoint: ``GET /<WABA_ID>?fields=analytics.start(..).end(..)...``.

        Args:
            start: Start unix timestamp (seconds).
            end: End unix timestamp (seconds).
            granularity: ``HALF_HOUR`` | ``DAY`` | ``MONTH``.
            phone_numbers: Optional display-number filter list.
        """
        field = f"analytics.start({safe_int(start, 0)}).end({safe_int(end, 0)}).granularity({granularity})"
        if phone_numbers:
            numbers = ",".join(f'"{n}"' for n in phone_numbers)
            field += f".phone_numbers([{numbers}])"
        return await self._request("GET", self._waba_path("").rstrip("/"), params={"fields": field})

    @action("Get per-message pricing/cost analytics")
    async def get_pricing_analytics(
        self,
        start: int,
        end: int,
        granularity: str = "DAILY",
        metric_types: Optional[list[str]] = None,
        dimensions: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Cost/volume under the per-message pricing model (raw envelope).

        Endpoint: ``GET /<WABA_ID>?fields=pricing_analytics...``. Note the
        granularity naming differs from ``analytics`` (DAILY vs DAY).

        Args:
            start: Start unix timestamp (seconds).
            end: End unix timestamp (seconds).
            granularity: ``HALF_HOUR`` | ``DAILY`` | ``MONTHLY``.
            metric_types: e.g. ``["COST", "VOLUME"]``.
            dimensions: e.g. ``["PRICING_CATEGORY", "COUNTRY", "TIER"]``.
        """
        field = (
            f"pricing_analytics.start({safe_int(start, 0)})"
            f".end({safe_int(end, 0)}).granularity({granularity})"
        )
        # Live-verified 2026-07-23: values must be QUOTED strings — the
        # unquoted enum form is rejected with Graph code 100.
        if metric_types:
            quoted = ",".join(f'"{m}"' for m in metric_types)
            field += f".metric_types([{quoted}])"
        if dimensions:
            quoted = ",".join(f'"{d}"' for d in dimensions)
            field += f".dimensions([{quoted}])"
        return await self._request("GET", self._waba_path("").rstrip("/"), params={"fields": field})

    @action("Get per-template analytics (opt-in required)")
    async def get_template_analytics(
        self,
        template_ids: list[str],
        start: int,
        end: int,
        metric_types: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Daily SENT/DELIVERED/READ/CLICKED/COST per template (raw).

        Endpoint: ``GET /<WABA_ID>/template_analytics`` (daily-only;
        requires one-time ``enable_template_analytics``; <=10 ids).

        Args:
            template_ids: 1..10 numeric template ids.
            start: Start unix timestamp (seconds).
            end: End unix timestamp (seconds).
            metric_types: Default ``["SENT", "DELIVERED", "READ"]``.
        """
        if not template_ids or len(template_ids) > 10:
            raise ValidationError("template_ids must contain 1..10 ids.", connector=self.name)
        # Wire expects numeric UNQUOTED ids (Whatomate cross-check).
        ids = ",".join(str(safe_int(t, 0)) for t in template_ids)
        metrics = ",".join(metric_types or ["SENT", "DELIVERED", "READ"])
        return await self._request(
            "GET",
            self._waba_path("template_analytics"),
            params={
                "start": safe_int(start, 0),
                "end": safe_int(end, 0),
                "granularity": "DAILY",
                "template_ids": f"[{ids}]",
                "metric_types": f"[{metrics}]",
            },
        )

    @action("Enable template analytics on the WABA", dangerous=True)
    async def enable_template_analytics(self) -> WhatsAppSuccessResult:
        """One-time opt-in required before ``get_template_analytics``.

        Endpoint: ``POST /<WABA_ID>?is_enabled_for_insights=true``.
        """
        raw = await self._request(
            "POST",
            self._waba_path("").rstrip("/"),
            params={"is_enabled_for_insights": "true"},
        )
        return safe_validate(WhatsAppSuccessResult, raw) or WhatsAppSuccessResult()

    # ------------------------------------------------------------------
    # Webhook subscription management (live-verified pattern 2026-07-23)
    # ------------------------------------------------------------------

    @action("Subscribe this app to the WABA's webhooks")
    async def subscribe_app(
        self,
        override_callback_uri: Optional[str] = None,
        verify_token: Optional[str] = None,
    ) -> WhatsAppSuccessResult:
        """Bind the app to the WABA so webhook events flow.

        Endpoint: ``POST /<WABA_ID>/subscribed_apps``.

        The per-WABA callback override only works AFTER an app-level
        subscription exists (otherwise Meta returns code 100 —
        live-verified); use ``set_app_webhook`` first.

        Args:
            override_callback_uri: Optional per-WABA callback URL.
            verify_token: Verify token for the override URL (required
                with ``override_callback_uri``).
        """
        body: Optional[dict[str, Any]] = None
        if override_callback_uri:
            if not verify_token:
                raise ValidationError(
                    "verify_token is required with override_callback_uri.",
                    connector=self.name,
                )
            body = {
                "override_callback_uri": override_callback_uri,
                "verify_token": verify_token,
            }
        raw = await self._request("POST", self._waba_path("subscribed_apps"), json_body=body)
        return safe_validate(WhatsAppSuccessResult, raw) or WhatsAppSuccessResult()

    @action("List apps subscribed to the WABA's webhooks")
    async def list_subscribed_apps(self) -> dict[str, Any]:
        """List webhook-subscribed apps (raw envelope).

        Endpoint: ``GET /<WABA_ID>/subscribed_apps``.
        """
        return await self._request("GET", self._waba_path("subscribed_apps"))

    # ------------------------------------------------------------------
    # Flows — in-chat forms (CSAT, booking, lead capture, KYC)
    # ------------------------------------------------------------------

    @action("Create a Flow (in-chat form); returns it in DRAFT")
    async def create_flow(
        self,
        name: str,
        categories: list[str],
        flow_json: Optional[str] = None,
        endpoint_uri: Optional[str] = None,
        clone_flow_id: Optional[str] = None,
        publish: bool = False,
    ) -> WhatsAppFlowMutationResult:
        """Create a Flow on the WABA.

        Endpoint: ``POST /<WABA_ID>/flows``.

        Anyone can create and build Flows; **publishing and sending** need
        business verification and high message quality. Always inspect
        ``validation_errors`` — a create can return 200 with a broken
        Flow JSON.

        Args:
            name: Flow name.
            categories: One or more of ``SIGN_UP``, ``SIGN_IN``,
                ``APPOINTMENT_BOOKING``, ``LEAD_GENERATION``,
                ``CONTACT_US``, ``CUSTOMER_SUPPORT``, ``SURVEY``,
                ``OTHER``.
            flow_json: Optional Flow JSON (string) to attach immediately;
                otherwise upload it later with ``upload_flow_json``.
            endpoint_uri: Optional data-channel endpoint for
                ``data_exchange`` flows.
            clone_flow_id: Optional id of a flow to clone.
            publish: Publish immediately (requires business verification).

        Returns:
            The new flow id plus any Flow JSON validation errors.
        """
        if not name or not categories:
            raise ValidationError("name and categories are required.", connector=self.name)
        body: dict[str, Any] = {"name": name, "categories": categories}
        for key, value in (
            ("flow_json", flow_json),
            ("endpoint_uri", endpoint_uri),
            ("clone_flow_id", clone_flow_id),
        ):
            if value is not None:
                body[key] = value
        if publish:
            body["publish"] = True
        raw = await self._request("POST", self._waba_path("flows"), json_body=body)
        return safe_validate(WhatsAppFlowMutationResult, raw) or WhatsAppFlowMutationResult()

    @action("List Flows on the WhatsApp Business Account")
    async def list_flows(
        self,
        limit: int = 25,
        after: Optional[str] = None,
    ) -> PaginatedList[WhatsAppFlow]:
        """List the WABA's Flows (cursor-paginated).

        Endpoint: ``GET /<WABA_ID>/flows``.

        Args:
            limit: Page size (1..100).
            after: Cursor from the previous page.
        """
        size = max(1, min(safe_int(limit, 25), 100))
        params: dict[str, Any] = {"limit": size}
        if after:
            params["after"] = after
        raw = await self._request("GET", self._waba_path("flows"), params=params)
        items = validate_list(WhatsAppFlow, raw.get("data"))
        paging_raw = raw.get("paging")
        paging: dict[str, Any] = paging_raw if isinstance(paging_raw, dict) else {}
        cursors_raw = paging.get("cursors")
        cursors: dict[str, Any] = cursors_raw if isinstance(cursors_raw, dict) else {}
        next_cursor = str(cursors.get("after") or "")
        has_more = bool(items) and bool(paging.get("next")) and bool(next_cursor)
        result: PaginatedList[WhatsAppFlow] = PaginatedList(
            items=items,
            page_state=PageState(cursor=next_cursor or None, has_more=has_more),
        )
        if has_more:
            # `a`-prefixed sibling is bound at runtime by BaseConnector.
            result._fetch_next = lambda c=next_cursor: self.alist_flows(  # type: ignore[attr-defined]
                limit=size, after=c
            )
        return result

    @action("Get a Flow's status, categories, and validation errors")
    async def get_flow(self, flow_id: str, include_preview: bool = False) -> WhatsAppFlow:
        """Fetch one Flow.

        Endpoint: ``GET /<FLOW_ID>``.

        Args:
            flow_id: The Flow id.
            include_preview: Also request the shareable web preview URL
                (not returned by default).
        """
        if not flow_id:
            raise ValidationError("flow_id is required.", connector=self.name)
        fields = (
            "id,name,status,categories,validation_errors,json_version,data_api_version,endpoint_uri"
        )
        if include_preview:
            fields += ",preview.invalidate(false)"
        raw = await self._request("GET", f"/{flow_id}", params={"fields": fields})
        return safe_validate(WhatsAppFlow, raw) or WhatsAppFlow()

    @action("Update a Flow's metadata", dangerous=True)
    async def update_flow(
        self,
        flow_id: str,
        name: Optional[str] = None,
        categories: Optional[list[str]] = None,
        endpoint_uri: Optional[str] = None,
    ) -> WhatsAppSuccessResult:
        """Rename a Flow or change its categories / data endpoint.

        Endpoint: ``POST /<FLOW_ID>``.

        Args:
            flow_id: The Flow id.
            name: New name.
            categories: Replacement category list.
            endpoint_uri: Data-channel endpoint for ``data_exchange``.
        """
        if not flow_id:
            raise ValidationError("flow_id is required.", connector=self.name)
        body: dict[str, Any] = {}
        for key, value in (
            ("name", name),
            ("categories", categories),
            ("endpoint_uri", endpoint_uri),
        ):
            if value is not None:
                body[key] = value
        if not body:
            raise ValidationError("Provide at least one field to update.", connector=self.name)
        raw = await self._request("POST", f"/{flow_id}", json_body=body)
        return safe_validate(WhatsAppSuccessResult, raw) or WhatsAppSuccessResult()

    @action("Upload the Flow JSON that defines the form's screens")
    async def upload_flow_json(self, flow_id: str, flow_json: str) -> WhatsAppFlowMutationResult:
        """Attach/replace a Flow's JSON definition (max 10 MB).

        Endpoint: ``POST /<FLOW_ID>/assets`` (multipart; the part name and
        asset type are fixed literals).

        Args:
            flow_id: The Flow id.
            flow_json: The Flow JSON document as a string.

        Returns:
            Result with ``validation_errors`` — a 200 does NOT mean the
            Flow JSON is valid.
        """
        if not flow_id or not flow_json:
            raise ValidationError("flow_id and flow_json are required.", connector=self.name)
        raw = await self._request(
            "POST",
            f"/{flow_id}/assets",
            files={"file": ("flow.json", flow_json.encode("utf-8"), "application/json")},
            data={"name": "flow.json", "asset_type": "FLOW_JSON"},
        )
        return safe_validate(WhatsAppFlowMutationResult, raw) or WhatsAppFlowMutationResult()

    @action("List a Flow's assets (its Flow JSON download URL)")
    async def list_flow_assets(self, flow_id: str) -> list[WhatsAppFlowAsset]:
        """List assets attached to a Flow.

        Endpoint: ``GET /<FLOW_ID>/assets``.

        Args:
            flow_id: The Flow id.
        """
        if not flow_id:
            raise ValidationError("flow_id is required.", connector=self.name)
        raw = await self._request("GET", f"/{flow_id}/assets")
        return validate_list(WhatsAppFlowAsset, raw.get("data"))

    @action("Publish a Flow so it can be sent", dangerous=True)
    async def publish_flow(self, flow_id: str) -> WhatsAppSuccessResult:
        """Move a Flow from DRAFT to PUBLISHED.

        Endpoint: ``POST /<FLOW_ID>/publish``.

        Requires business verification and high message quality. Published
        Flows can no longer be edited — clone to iterate.

        Args:
            flow_id: The Flow id.
        """
        if not flow_id:
            raise ValidationError("flow_id is required.", connector=self.name)
        raw = await self._request("POST", f"/{flow_id}/publish")
        return safe_validate(WhatsAppSuccessResult, raw) or WhatsAppSuccessResult()

    @action("Deprecate a published Flow", dangerous=True)
    async def deprecate_flow(self, flow_id: str) -> WhatsAppSuccessResult:
        """Retire a published Flow (existing sends stop working).

        Endpoint: ``POST /<FLOW_ID>/deprecate``.

        Args:
            flow_id: The Flow id.
        """
        if not flow_id:
            raise ValidationError("flow_id is required.", connector=self.name)
        raw = await self._request("POST", f"/{flow_id}/deprecate")
        return safe_validate(WhatsAppSuccessResult, raw) or WhatsAppSuccessResult()

    @action("Delete a draft Flow", dangerous=True)
    async def delete_flow(self, flow_id: str) -> WhatsAppSuccessResult:
        """Delete a Flow (drafts only — published Flows must be deprecated).

        Endpoint: ``DELETE /<FLOW_ID>``.

        Args:
            flow_id: The Flow id.
        """
        if not flow_id:
            raise ValidationError("flow_id is required.", connector=self.name)
        raw = await self._request("DELETE", f"/{flow_id}")
        return safe_validate(WhatsAppSuccessResult, raw) or WhatsAppSuccessResult()

    @action("Send a Flow (in-chat form) to a user")
    async def send_flow(
        self,
        to: str,
        flow_cta: str,
        body: str,
        flow_id: Optional[str] = None,
        flow_name: Optional[str] = None,
        screen: Optional[str] = None,
        data: Optional[dict[str, Any]] = None,
        flow_token: Optional[str] = None,
        flow_action: str = "navigate",
        mode: str = "published",
        header_text: Optional[str] = None,
        footer_text: Optional[str] = None,
        tracking_data: Optional[str] = None,
    ) -> WhatsAppSendResult:
        """Send an interactive Flow message (24h window).

        Endpoint: ``POST /<PHONE_NUMBER_ID>/messages``
        (``interactive.type = "flow"``).

        The user's completed form arrives on the ``messages`` webhook as
        ``interactive.nfm_reply`` — its ``response_json`` is a
        JSON-**encoded string** you must parse, and it echoes back
        ``flow_token`` so you can correlate the reply to the send.

        Args:
            to: Recipient number (E.164 digits).
            flow_cta: Button label (Meta advises <= 30 characters).
            body: Body text shown above the button. Documented as
                optional, but live-verified as **required** — omitting it
                fails with "(#131008) Required parameter is missing".
            flow_id: The Flow to send — provide exactly one of
                ``flow_id`` / ``flow_name``.
            flow_name: Alternative to ``flow_id``.
            screen: Entry screen id (used with ``navigate``).
            data: Initial data passed to that screen.
            flow_token: Your own correlation token, echoed back in the
                reply (optional but recommended).
            flow_action: ``navigate`` (default) or ``data_exchange``.
            mode: ``published`` (default) or ``draft`` for testing an
                unpublished Flow.
            header_text: Optional text header.
            footer_text: Optional footer.
            tracking_data: Echoed back on status webhooks.
        """
        if bool(flow_id) == bool(flow_name):
            raise ValidationError(
                "Provide exactly one of flow_id or flow_name.",
                connector=self.name,
            )
        if not flow_cta or not body:
            raise ValidationError("flow_cta and body are required.", connector=self.name)
        # Live-verified 2026-07-23: navigate without an entry screen is
        # rejected upstream with the opaque "(#131008) Required parameter
        # is missing" — fail here with something actionable instead.
        if flow_action == "navigate" and not screen:
            raise ValidationError(
                "flow_action='navigate' requires the entry 'screen' id.",
                connector=self.name,
            )
        parameters: dict[str, Any] = {
            "flow_message_version": "3",
            "flow_cta": flow_cta,
            "flow_action": flow_action,
        }
        parameters["flow_id" if flow_id else "flow_name"] = flow_id or flow_name
        if flow_token:
            parameters["flow_token"] = flow_token
        if mode and mode != "published":
            parameters["mode"] = mode
        if screen is not None or data is not None:
            payload: dict[str, Any] = {}
            if screen is not None:
                payload["screen"] = screen
            if data is not None:
                payload["data"] = data
            parameters["flow_action_payload"] = payload
        interactive: dict[str, Any] = {
            "type": "flow",
            "action": {"name": "flow", "parameters": parameters},
        }
        interactive["body"] = {"text": body}
        if header_text:
            interactive["header"] = {"type": "text", "text": header_text}
        if footer_text:
            interactive["footer"] = {"text": footer_text}
        return await self._send(to, "interactive", interactive, tracking_data=tracking_data)

    # ------------------------------------------------------------------
    # Marketing Messages API (formerly "MM Lite")
    # ------------------------------------------------------------------

    @action("Check whether the WABA can use the Marketing Messages API")
    async def get_marketing_eligibility(self) -> WhatsAppMarketingEligibility:
        """Read the WABA's Marketing Messages API onboarding status.

        Endpoint:
        ``GET /<WABA_ID>?fields=marketing_messages_onboarding_status``.

        Returns:
            Status (``ELIGIBLE`` when the API may be used).
        """
        raw = await self._request(
            "GET",
            self._waba_path("").rstrip("/"),
            params={"fields": "marketing_messages_onboarding_status"},
        )
        return safe_validate(WhatsAppMarketingEligibility, raw) or WhatsAppMarketingEligibility()

    @action("Send a marketing template via the Marketing Messages API")
    async def send_marketing_message(
        self,
        to: str,
        template_name: str,
        language_code: str = "en_US",
        components: Optional[list[dict[str, Any]]] = None,
        message_activity_sharing: Optional[bool] = None,
        tracking_data: Optional[str] = None,
    ) -> WhatsAppSendResult:
        """Send a MARKETING template through Meta's optimized delivery path.

        Endpoint: ``POST /<PHONE_NUMBER_ID>/marketing_messages``.

        Send-only and **marketing-category templates only** — other
        categories belong on ``send_template``. Status webhooks arrive as
        usual but carry ``pricing.category = "marketing_lite"``. Requires
        the business to have accepted the Marketing Messages API terms
        (check with ``get_marketing_eligibility``).

        Args:
            to: Recipient number (E.164 digits).
            template_name: An approved MARKETING template.
            language_code: Template locale, e.g. ``en_US``.
            components: Parameter components, same shape as
                ``send_template``.
            message_activity_sharing: Opt in to extra **click** webhook
                events when the user taps a CTA URL.
            tracking_data: Echoed back on status webhooks.
        """
        if not template_name:
            raise ValidationError("template_name is required.", connector=self.name)
        template: dict[str, Any] = {
            "name": template_name,
            "language": {"code": language_code},
        }
        if components is not None:
            template["components"] = components
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": self._require_to(to),
            "type": "template",
            "template": template,
        }
        if message_activity_sharing is not None:
            payload["message_activity_sharing"] = bool(message_activity_sharing)
        if tracking_data:
            payload["biz_opaque_callback_data"] = tracking_data
        raw = await self._request("POST", self._phone_path("marketing_messages"), json_body=payload)
        return safe_validate(WhatsAppSendResult, raw) or WhatsAppSendResult()

    # ------------------------------------------------------------------
    # Embedded Signup — platform onboarding ("Connect WhatsApp" button)
    # ------------------------------------------------------------------

    def _require_app_id(self, app_id: Optional[str]) -> str:
        resolved = str(app_id or self._creds.app_id or "").strip()
        if not resolved:
            raise MissingConfigError(
                "app_id is required (pass it, or put 'app_id' in the credentials).",
                connector=self.name,
            )
        return resolved

    def _require_app_secret(self) -> str:
        if not self._creds.app_secret:
            raise MissingConfigError(
                "This action needs 'app_secret' in the credentials.",
                connector=self.name,
            )
        return self._creds.app_secret

    @action("Exchange an Embedded Signup code for a customer access token")
    async def exchange_code(
        self,
        code: str,
        app_id: Optional[str] = None,
    ) -> WhatsAppTokenExchange:
        """Turn the code from Meta's Embedded Signup popup into a token.

        Endpoint: ``GET /oauth/access_token`` (params ``client_id``,
        ``client_secret``, ``code`` — no ``redirect_uri``, no
        ``grant_type``).

        This is the server-side half of the "Connect WhatsApp" button: the
        browser flow (Facebook Login for Business) returns a short-lived
        code, and this exchanges it for a **customer-scoped Business
        Integration System User token** that can act on that customer's
        WABA. BYOK-safe: the token is returned to you, never stored by the
        library.

        The code expires in ~30 seconds — exchange it immediately. The
        resulting token defaults to never expiring. Follow up with
        ``debug_token`` to discover the granted WABA id, then
        ``register_phone`` and ``subscribe_app``.

        Requires ``app_secret`` in the credentials (``app_id`` too, unless
        passed here). No user access token is needed.

        Args:
            code: The authorization code returned by the ES popup.
            app_id: Your Meta app id (defaults to the credentials value).

        Returns:
            The customer-scoped access token.
        """
        if not code:
            raise ValidationError("code is required.", connector=self.name)
        resolved_app_id = self._require_app_id(app_id)
        raw = await self._request(
            "GET",
            "/oauth/access_token",
            params={
                "client_id": resolved_app_id,
                "client_secret": self._require_app_secret(),
                "code": code,
            },
        )
        return safe_validate(WhatsAppTokenExchange, raw) or WhatsAppTokenExchange()

    @action("Inspect a token: validity, scopes, and the WABA ids it can reach")
    async def debug_token(
        self,
        input_token: Optional[str] = None,
        app_id: Optional[str] = None,
    ) -> WhatsAppTokenInfo:
        """Introspect an access token and extract the WABA ids it grants.

        Endpoint: ``GET /debug_token`` (authenticated with the app token
        ``<app_id>|<app_secret>``).

        After ``exchange_code``, this tells you which WhatsApp Business
        Account(s) the customer granted — so onboarding never has to ask
        them to paste ids. ``waba_ids`` is derived from the
        ``whatsapp_business_management`` / ``whatsapp_business_messaging``
        granular scopes, most recently onboarded first.

        ``waba_ids`` is populated for **Embedded Signup** tokens, where
        Meta scopes the grant to specific assets. A System User token with
        assets assigned directly reports the same scopes with **empty**
        ``target_ids`` (live-verified 2026-07-23) — that means "not
        asset-scoped", not "no access"; use your configured ``waba_id``.

        Also the cheapest way to answer "is this stored customer token
        still alive?" — check ``is_valid`` and ``expires_at`` (``0`` means
        never expires) instead of discovering it mid-send.

        Args:
            input_token: Token to inspect (defaults to the connector's own
                ``access_token``).
            app_id: Your Meta app id (defaults to the credentials value).

        Returns:
            Token metadata including ``is_valid``, ``scopes``, and the
            derived ``waba_ids``.
        """
        token = str(input_token or self._creds.access_token or "").strip()
        if not token:
            raise ValidationError(
                "input_token is required (or set 'access_token' in the credentials).",
                connector=self.name,
            )
        resolved_app_id = self._require_app_id(app_id)
        raw = await self._request(
            "GET",
            "/debug_token",
            params={"input_token": token},
            headers={"Authorization": (f"Bearer {resolved_app_id}|{self._require_app_secret()}")},
        )
        data = raw.get("data")
        payload: dict[str, Any] = dict(data) if isinstance(data, dict) else {}
        waba_ids: list[str] = []
        scopes_raw = payload.get("granular_scopes")
        for entry in scopes_raw if isinstance(scopes_raw, list) else []:
            if not isinstance(entry, dict):
                continue
            # Field drift is documented in the wild (business_management vs
            # whatsapp_business_management) — match on the suffix.
            if "whatsapp_business" not in str(entry.get("scope", "")):
                continue
            targets = entry.get("target_ids")
            for target in targets if isinstance(targets, list) else []:
                identifier = str(target)
                if identifier not in waba_ids:
                    waba_ids.append(identifier)
        payload["waba_ids"] = waba_ids
        return safe_validate(WhatsAppTokenInfo, payload) or WhatsAppTokenInfo()

    @action("Configure the app-level webhook callback via API", dangerous=True)
    async def set_app_webhook(
        self,
        app_id: str,
        callback_url: str,
        verify_token: str,
        fields: str = "messages",
    ) -> WhatsAppSuccessResult:
        """Set the Meta app's webhook callback programmatically.

        Endpoint: ``POST /<APP_ID>/subscriptions`` (authenticated with the
        app token ``<app_id>|<app_secret>`` — requires ``app_secret`` in
        the credentials).

        Meta fires the GET verification handshake at ``callback_url``
        during this call — the endpoint must already be live and answering
        ``hub.challenge`` (see the webhooks module). Live-verified
        2026-07-23: this + ``subscribe_app`` fully replaces the dashboard
        webhook configuration.

        Args:
            app_id: The Meta app id.
            callback_url: Public https endpoint for webhook delivery.
            verify_token: The token your endpoint echoes on verification.
            fields: Comma-separated subscription fields (default
                ``messages``).
        """
        if not self._creds.app_secret:
            raise MissingConfigError(
                "set_app_webhook needs 'app_secret' in the credentials.",
                connector=self.name,
            )
        if not app_id or not callback_url or not verify_token:
            raise ValidationError(
                "app_id, callback_url and verify_token are required.",
                connector=self.name,
            )
        raw = await self._request(
            "POST",
            f"/{app_id}/subscriptions",
            params={
                "object": "whatsapp_business_account",
                "callback_url": callback_url,
                "verify_token": verify_token,
                "fields": fields,
            },
            # App-level config authenticates with the APP token, not the
            # System User token (per-request override).
            headers={"Authorization": f"Bearer {app_id}|{self._creds.app_secret}"},
        )
        return safe_validate(WhatsAppSuccessResult, raw) or WhatsAppSuccessResult()
