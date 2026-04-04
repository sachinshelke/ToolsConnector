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
from .types import PhoneNumber, TwilioAccount, TwilioCall, TwilioMessage

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
        """Initialise the httpx async client with Basic auth."""
        creds = self._credentials or ":"
        parts = creds.split(":", 1)
        self._account_sid = parts[0]
        auth_token = parts[1] if len(parts) > 1 else ""

        token = base64.b64encode(
            f"{self._account_sid}:{auth_token}".encode()
        ).decode()

        headers: dict[str, str] = {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        self._client = httpx.AsyncClient(
            base_url=self._base_url or self.__class__.base_url,
            headers=headers,
            timeout=self._timeout,
        )

    async def _teardown(self) -> None:
        """Close the httpx client."""
        if hasattr(self, "_client"):
            await self._client.aclose()

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
