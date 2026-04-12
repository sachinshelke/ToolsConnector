"""Twilio connector — SMS, voice calls, phone numbers, and account info.

Uses the Twilio REST API (2010-04-01) with HTTP Basic auth
(Account SID as username, Auth Token as password). URL pattern:
``/Accounts/{account_sid}/Resource.json``. Form-encoded POST bodies.
Pagination via ``next_page_uri`` field in responses.
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Optional

import httpx

from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import (
    ConnectorCategory,
    ProtocolType,
    RateLimitSpec,
)
from toolsconnector.types import PageState, PaginatedList

from ._parsers import parse_call, parse_message, parse_phone_number
from .types import (
    PhoneNumber,
    TwilioAccount,
    TwilioCall,
    TwilioConversation,
    TwilioLookupResult,
    TwilioMessage,
    TwilioRecording,
    TwilioUsageRecord,
    TwilioVerification,
    TwilioVerificationCheck,
    TwilioVerifyService,
)

logger = logging.getLogger("toolsconnector.twilio")


class Twilio(BaseConnector):
    """Connect to Twilio to send SMS, manage calls, and query phone numbers.

    Authenticates via HTTP Basic auth using Account SID and Auth Token.
    Credentials should be provided as ``"account_sid:auth_token"`` string.
    """

    name = "twilio"
    display_name = "Twilio"
    category = ConnectorCategory.COMMUNICATION
    protocol = ProtocolType.REST
    base_url = "https://api.twilio.com/2010-04-01"
    description = (
        "Connect to Twilio to send SMS/MMS, manage voice calls, "
        "and query phone numbers and account information."
    )
    _rate_limit_config = RateLimitSpec(rate=100, period=1, burst=50)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Initialise httpx async clients with Basic auth.

        Creates separate clients for the main REST API, the Verify v2 API,
        the Lookup v2 API, and the Conversations v1 API since they use
        different base URLs.
        """
        creds = self._credentials or ":"
        parts = creds.split(":", 1)
        self._account_sid = parts[0]
        auth_token = parts[1] if len(parts) > 1 else ""

        token = base64.b64encode(
            f"{self._account_sid}:{auth_token}".encode()
        ).decode()

        form_headers: dict[str, str] = {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        json_headers: dict[str, str] = {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
        }

        self._client = httpx.AsyncClient(
            base_url=self._base_url or self.__class__.base_url,
            headers=form_headers,
            timeout=self._timeout,
        )
        self._verify_client = httpx.AsyncClient(
            base_url="https://verify.twilio.com/v2",
            headers=form_headers,
            timeout=self._timeout,
        )
        self._lookup_client = httpx.AsyncClient(
            base_url="https://lookups.twilio.com/v2",
            headers=json_headers,
            timeout=self._timeout,
        )
        self._conversations_client = httpx.AsyncClient(
            base_url="https://conversations.twilio.com/v1",
            headers=json_headers,
            timeout=self._timeout,
        )

    async def _teardown(self) -> None:
        """Close all httpx clients."""
        for attr in ("_client", "_verify_client", "_lookup_client",
                     "_conversations_client"):
            client = getattr(self, attr, None)
            if client is not None:
                await client.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _acct(self, resource: str) -> str:
        """Build an account-scoped resource path.

        Args:
            resource: Resource path segment (e.g. ``Messages.json``).

        Returns:
            Full path like ``/Accounts/{sid}/Messages.json``.
        """
        return f"/Accounts/{self._account_sid}/{resource}"

    async def _request(
        self, method: str, path: str, *,
        params: Optional[dict[str, Any]] = None,
        data: Optional[dict[str, Any]] = None,
    ) -> httpx.Response:
        """Send an authenticated request to the Twilio API.

        Args:
            method: HTTP method (GET, POST, etc.).
            path: API path relative to base_url.
            params: Query parameters for GET requests.
            data: Form-encoded body for POST requests.

        Returns:
            httpx.Response object.

        Raises:
            httpx.HTTPStatusError: On 4xx/5xx responses.
        """
        resp = await self._client.request(
            method, path, params=params, data=data,
        )
        resp.raise_for_status()
        return resp

    def _page_state(self, body: dict[str, Any]) -> PageState:
        """Build a PageState from Twilio pagination fields.

        Args:
            body: Parsed JSON response body.

        Returns:
            PageState with cursor set to next_page_uri if present.
        """
        next_uri = body.get("next_page_uri")
        return PageState(has_more=next_uri is not None, cursor=next_uri)

    # ------------------------------------------------------------------
    # Actions — Messages (SMS/MMS)
    # ------------------------------------------------------------------

    @action("Send an SMS or MMS message via Twilio", dangerous=True)
    async def send_sms(
        self, to: str, from_: str, body: str,
    ) -> TwilioMessage:
        """Send an SMS message.

        Args:
            to: Recipient phone number in E.164 format.
            from_: Sender phone number (must be a Twilio number).
            body: Message text content.

        Returns:
            The created TwilioMessage object.
        """
        form_data = {"To": to, "From": from_, "Body": body}
        resp = await self._request(
            "POST", self._acct("Messages.json"), data=form_data,
        )
        return parse_message(resp.json())

    @action("List SMS/MMS messages from your Twilio account")
    async def list_messages(
        self,
        to: Optional[str] = None,
        from_: Optional[str] = None,
        limit: int = 20,
    ) -> PaginatedList[TwilioMessage]:
        """List messages with optional filters.

        Args:
            to: Filter by recipient phone number.
            from_: Filter by sender phone number.
            limit: Maximum messages per page (max 1000).

        Returns:
            Paginated list of TwilioMessage objects.
        """
        params: dict[str, Any] = {"PageSize": min(limit, 1000)}
        if to:
            params["To"] = to
        if from_:
            params["From"] = from_

        resp = await self._request(
            "GET", self._acct("Messages.json"), params=params,
        )
        body = resp.json()
        items = [parse_message(m) for m in body.get("messages", [])]
        ps = self._page_state(body)

        result = PaginatedList(items=items, page_state=ps)
        result._fetch_next = (
            (lambda c=ps.cursor: self._fetch_msgs(c))
            if ps.has_more else None
        )
        return result

    async def _fetch_msgs(self, uri: str) -> PaginatedList[TwilioMessage]:
        """Fetch the next page of messages.

        Args:
            uri: The ``next_page_uri`` from a previous response.

        Returns:
            Paginated list of TwilioMessage objects.
        """
        resp = await self._client.get(uri)
        resp.raise_for_status()
        body = resp.json()
        items = [parse_message(m) for m in body.get("messages", [])]
        ps = self._page_state(body)
        result = PaginatedList(items=items, page_state=ps)
        result._fetch_next = (
            (lambda c=ps.cursor: self._fetch_msgs(c))
            if ps.has_more else None
        )
        return result

    @action("Retrieve a single Twilio message by SID")
    async def get_message(self, message_sid: str) -> TwilioMessage:
        """Retrieve a single message.

        Args:
            message_sid: The Twilio message SID (e.g. ``SM...``).

        Returns:
            TwilioMessage object.
        """
        path = self._acct(f"Messages/{message_sid}.json")
        resp = await self._request("GET", path)
        return parse_message(resp.json())

    # ------------------------------------------------------------------
    # Actions — Calls
    # ------------------------------------------------------------------

    @action("List voice calls from your Twilio account")
    async def list_calls(
        self,
        to: Optional[str] = None,
        from_: Optional[str] = None,
        limit: int = 20,
    ) -> PaginatedList[TwilioCall]:
        """List calls with optional filters.

        Args:
            to: Filter by recipient phone number.
            from_: Filter by caller phone number.
            limit: Maximum calls per page (max 1000).

        Returns:
            Paginated list of TwilioCall objects.
        """
        params: dict[str, Any] = {"PageSize": min(limit, 1000)}
        if to:
            params["To"] = to
        if from_:
            params["From"] = from_

        resp = await self._request(
            "GET", self._acct("Calls.json"), params=params,
        )
        body = resp.json()
        items = [parse_call(c) for c in body.get("calls", [])]
        ps = self._page_state(body)

        result = PaginatedList(items=items, page_state=ps)
        result._fetch_next = (
            (lambda c=ps.cursor: self._fetch_calls(c))
            if ps.has_more else None
        )
        return result

    async def _fetch_calls(self, uri: str) -> PaginatedList[TwilioCall]:
        """Fetch the next page of calls.

        Args:
            uri: The ``next_page_uri`` from a previous response.

        Returns:
            Paginated list of TwilioCall objects.
        """
        resp = await self._client.get(uri)
        resp.raise_for_status()
        body = resp.json()
        items = [parse_call(c) for c in body.get("calls", [])]
        ps = self._page_state(body)
        result = PaginatedList(items=items, page_state=ps)
        result._fetch_next = (
            (lambda c=ps.cursor: self._fetch_calls(c))
            if ps.has_more else None
        )
        return result

    @action("Initiate a voice call via Twilio", dangerous=True)
    async def make_call(
        self, to: str, from_: str, url: str,
    ) -> TwilioCall:
        """Initiate an outbound voice call.

        Args:
            to: Recipient phone number in E.164 format.
            from_: Caller phone number (must be a Twilio number).
            url: TwiML URL that controls the call flow.

        Returns:
            The created TwilioCall object.
        """
        form_data = {"To": to, "From": from_, "Url": url}
        resp = await self._request(
            "POST", self._acct("Calls.json"), data=form_data,
        )
        return parse_call(resp.json())

    @action("Retrieve a single Twilio call by SID")
    async def get_call(self, call_sid: str) -> TwilioCall:
        """Retrieve a single call.

        Args:
            call_sid: The Twilio call SID (e.g. ``CA...``).

        Returns:
            TwilioCall object.
        """
        path = self._acct(f"Calls/{call_sid}.json")
        resp = await self._request("GET", path)
        return parse_call(resp.json())

    # ------------------------------------------------------------------
    # Actions — Phone Numbers
    # ------------------------------------------------------------------

    @action("List incoming phone numbers on your Twilio account")
    async def list_phone_numbers(self) -> list[PhoneNumber]:
        """List all incoming phone numbers.

        Returns:
            List of PhoneNumber objects.
        """
        path = self._acct("IncomingPhoneNumbers.json")
        resp = await self._request("GET", path)
        body = resp.json()
        return [
            parse_phone_number(p)
            for p in body.get("incoming_phone_numbers", [])
        ]

    # ------------------------------------------------------------------
    # Actions — Account
    # ------------------------------------------------------------------

    @action("Retrieve your Twilio account details")
    async def get_account(self) -> TwilioAccount:
        """Retrieve account information.

        Returns:
            TwilioAccount object with account details.
        """
        resp = await self._request(
            "GET", f"/Accounts/{self._account_sid}.json",
        )
        data = resp.json()
        return TwilioAccount(
            sid=data["sid"],
            friendly_name=data.get("friendly_name"),
            status=data.get("status"),
            type=data.get("type"),
            owner_account_sid=data.get("owner_account_sid"),
            date_created=data.get("date_created"),
            date_updated=data.get("date_updated"),
            uri=data.get("uri"),
        )

    # ------------------------------------------------------------------
    # Actions — Usage
    # ------------------------------------------------------------------

    @action("Get account usage records for the current billing period")
    async def get_account_usage(self) -> list[TwilioUsageRecord]:
        """Retrieve usage records for the current billing period.

        Returns:
            List of TwilioUsageRecord objects summarising usage by category.
        """
        path = self._acct("Usage/Records.json")
        resp = await self._request("GET", path)
        body = resp.json()
        return [
            TwilioUsageRecord(
                category=r.get("category", ""),
                description=r.get("description"),
                count=r.get("count"),
                count_unit=r.get("count_unit"),
                usage=r.get("usage"),
                usage_unit=r.get("usage_unit"),
                price=r.get("price"),
                price_unit=r.get("price_unit"),
                start_date=r.get("start_date"),
                end_date=r.get("end_date"),
                uri=r.get("uri"),
            )
            for r in body.get("usage_records", [])
        ]

    # ------------------------------------------------------------------
    # Actions — Recordings
    # ------------------------------------------------------------------

    @action("List call recordings from your Twilio account")
    async def list_recordings(
        self, limit: Optional[int] = None,
    ) -> list[TwilioRecording]:
        """List call recordings.

        Args:
            limit: Maximum number of recordings to return.

        Returns:
            List of TwilioRecording objects.
        """
        params: dict[str, Any] = {}
        if limit is not None:
            params["PageSize"] = min(limit, 1000)
        path = self._acct("Recordings.json")
        resp = await self._request("GET", path, params=params or None)
        body = resp.json()
        return [
            TwilioRecording(
                sid=r["sid"],
                account_sid=r.get("account_sid"),
                call_sid=r.get("call_sid"),
                duration=r.get("duration"),
                channels=r.get("channels"),
                status=r.get("status"),
                price=r.get("price"),
                price_unit=r.get("price_unit"),
                source=r.get("source"),
                uri=r.get("uri"),
                date_created=r.get("date_created"),
                date_updated=r.get("date_updated"),
            )
            for r in body.get("recordings", [])
        ]

    @action("Delete a call recording by SID", dangerous=True)
    async def delete_recording(self, sid: str) -> bool:
        """Delete a call recording.

        Args:
            sid: The recording SID (e.g. ``RE...``).

        Returns:
            True if the recording was deleted successfully.
        """
        path = self._acct(f"Recordings/{sid}.json")
        resp = await self._request("DELETE", path)
        return resp.status_code == 204

    # ------------------------------------------------------------------
    # Actions — MMS
    # ------------------------------------------------------------------

    @action("Send an MMS message with media via Twilio", dangerous=True)
    async def send_mms(
        self, to: str, from_: str, body: str, media_url: str,
    ) -> TwilioMessage:
        """Send an MMS message with a media attachment.

        Args:
            to: Recipient phone number in E.164 format.
            from_: Sender phone number (must be a Twilio number).
            body: Message text content.
            media_url: Public URL of the media to attach.

        Returns:
            The created TwilioMessage object.
        """
        form_data = {
            "To": to,
            "From": from_,
            "Body": body,
            "MediaUrl": media_url,
        }
        resp = await self._request(
            "POST", self._acct("Messages.json"), data=form_data,
        )
        return parse_message(resp.json())

    @action("Update or redact a Twilio message")
    async def update_message(
        self,
        message_sid: str,
        body: Optional[str] = None,
    ) -> TwilioMessage:
        """Update or redact the content of an existing message.

        To redact a message, set *body* to an empty string ``""``.

        Args:
            message_sid: The Twilio message SID (e.g. ``SM...``).
            body: New message body text (set to ``""`` to redact).

        Returns:
            The updated TwilioMessage object.
        """
        form_data: dict[str, Any] = {}
        if body is not None:
            form_data["Body"] = body

        path = self._acct(f"Messages/{message_sid}.json")
        resp = await self._request("POST", path, data=form_data)
        return parse_message(resp.json())

    @action("Delete a message from your Twilio account", dangerous=True)
    async def delete_message(self, message_sid: str) -> bool:
        """Delete a message permanently from your account.

        Args:
            message_sid: The Twilio message SID (e.g. ``SM...``).

        Returns:
            True if the message was deleted successfully.
        """
        path = self._acct(f"Messages/{message_sid}.json")
        resp = await self._request("DELETE", path)
        return resp.status_code == 204

    # ------------------------------------------------------------------
    # Actions — Verify API (v2)
    # ------------------------------------------------------------------

    @action("Create a Twilio Verify service", dangerous=True)
    async def create_verify_service(
        self, friendly_name: str,
    ) -> TwilioVerifyService:
        """Create a new Verify service for sending verification tokens.

        A single service can be reused for multiple verifications.

        Args:
            friendly_name: Human-readable name for the service
                (up to 32 characters).

        Returns:
            The created TwilioVerifyService object.
        """
        resp = await self._verify_client.post(
            "/Services", data={"FriendlyName": friendly_name},
        )
        resp.raise_for_status()
        data = resp.json()
        return TwilioVerifyService(
            sid=data["sid"],
            account_sid=data.get("account_sid"),
            friendly_name=data.get("friendly_name"),
            code_length=data.get("code_length"),
            lookup_enabled=data.get("lookup_enabled"),
            date_created=data.get("date_created"),
            date_updated=data.get("date_updated"),
            url=data.get("url"),
        )

    @action("Send a verification token via Twilio Verify", dangerous=True)
    async def send_verification(
        self,
        service_sid: str,
        to: str,
        channel: str = "sms",
    ) -> TwilioVerification:
        """Send a verification token to an end user.

        Args:
            service_sid: The Verify service SID (e.g. ``VA...``).
            to: Recipient phone number (E.164) or email address.
            channel: Delivery channel (``sms``, ``call``, ``email``,
                or ``whatsapp``).

        Returns:
            The created TwilioVerification with status ``pending``.
        """
        resp = await self._verify_client.post(
            f"/Services/{service_sid}/Verifications",
            data={"To": to, "Channel": channel},
        )
        resp.raise_for_status()
        data = resp.json()
        return TwilioVerification(
            sid=data["sid"],
            service_sid=data.get("service_sid"),
            account_sid=data.get("account_sid"),
            to=data.get("to"),
            channel=data.get("channel"),
            status=data.get("status"),
            valid=data.get("valid"),
            date_created=data.get("date_created"),
            date_updated=data.get("date_updated"),
            url=data.get("url"),
        )

    @action("Check a verification code via Twilio Verify")
    async def check_verification(
        self,
        service_sid: str,
        to: str,
        code: str,
    ) -> TwilioVerificationCheck:
        """Check whether a user-provided verification code is correct.

        Args:
            service_sid: The Verify service SID (e.g. ``VA...``).
            to: The phone number or email that was verified.
            code: The 4-10 character verification code to check.

        Returns:
            TwilioVerificationCheck with ``valid`` indicating success.
        """
        resp = await self._verify_client.post(
            f"/Services/{service_sid}/VerificationCheck",
            data={"To": to, "Code": code},
        )
        resp.raise_for_status()
        data = resp.json()
        return TwilioVerificationCheck(
            sid=data["sid"],
            service_sid=data.get("service_sid"),
            account_sid=data.get("account_sid"),
            to=data.get("to"),
            channel=data.get("channel"),
            status=data.get("status"),
            valid=data.get("valid"),
            date_created=data.get("date_created"),
            date_updated=data.get("date_updated"),
        )

    # ------------------------------------------------------------------
    # Actions — Lookup API (v2)
    # ------------------------------------------------------------------

    @action("Look up information about a phone number")
    async def lookup_phone(
        self,
        phone_number: str,
        fields: Optional[str] = None,
    ) -> TwilioLookupResult:
        """Look up formatting, validation, and carrier info for a number.

        The basic lookup (no *fields*) is free and returns E.164
        formatting plus validation. Pass *fields* for paid data
        packages.

        Args:
            phone_number: Phone number in E.164 or national format.
            fields: Comma-separated data packages to include
                (e.g. ``"line_type_intelligence,caller_name"``).

        Returns:
            TwilioLookupResult with the requested data.
        """
        params: dict[str, Any] = {}
        if fields:
            params["Fields"] = fields

        resp = await self._lookup_client.get(
            f"/PhoneNumbers/{phone_number}",
            params=params or None,
        )
        resp.raise_for_status()
        data = resp.json()
        return TwilioLookupResult(
            phone_number=data.get("phone_number"),
            national_format=data.get("national_format"),
            country_code=data.get("country_code"),
            calling_country_code=data.get("calling_country_code"),
            valid=data.get("valid"),
            validation_errors=data.get("validation_errors"),
            caller_name=data.get("caller_name"),
            line_type_intelligence=data.get("line_type_intelligence"),
            url=data.get("url"),
        )

    # ------------------------------------------------------------------
    # Actions — Conversations API (v1)
    # ------------------------------------------------------------------

    @action("List conversations from your Twilio account")
    async def list_conversations(
        self, limit: int = 20,
    ) -> list[TwilioConversation]:
        """List conversations in the default Conversations service.

        Args:
            limit: Maximum number of conversations to return.

        Returns:
            List of TwilioConversation objects.
        """
        params: dict[str, Any] = {"PageSize": min(limit, 1000)}
        resp = await self._conversations_client.get(
            "/Conversations", params=params,
        )
        resp.raise_for_status()
        body = resp.json()
        return [
            TwilioConversation(
                sid=c["sid"],
                account_sid=c.get("account_sid"),
                chat_service_sid=c.get("chat_service_sid"),
                friendly_name=c.get("friendly_name"),
                unique_name=c.get("unique_name"),
                state=c.get("state"),
                attributes=c.get("attributes"),
                date_created=c.get("date_created"),
                date_updated=c.get("date_updated"),
                url=c.get("url"),
            )
            for c in body.get("conversations", [])
        ]

    @action("Create a new Twilio conversation", dangerous=True)
    async def create_conversation(
        self, friendly_name: str,
    ) -> TwilioConversation:
        """Create a new conversation in the default Conversations service.

        Args:
            friendly_name: Human-readable name for the conversation
                (max 256 characters).

        Returns:
            The created TwilioConversation object.
        """
        resp = await self._conversations_client.post(
            "/Conversations",
            json={"friendly_name": friendly_name},
        )
        resp.raise_for_status()
        data = resp.json()
        return TwilioConversation(
            sid=data["sid"],
            account_sid=data.get("account_sid"),
            chat_service_sid=data.get("chat_service_sid"),
            friendly_name=data.get("friendly_name"),
            unique_name=data.get("unique_name"),
            state=data.get("state"),
            attributes=data.get("attributes"),
            date_created=data.get("date_created"),
            date_updated=data.get("date_updated"),
            url=data.get("url"),
        )
