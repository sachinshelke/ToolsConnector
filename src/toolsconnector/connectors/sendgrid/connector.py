"""SendGrid connector — email sending, contacts, lists, templates, and stats.

Uses the SendGrid Web API v3 with Bearer token authentication.
The ``/mail/send`` endpoint uses a specific nested JSON structure.
Marketing contacts use the ``/marketing/`` sub-API.
"""

from __future__ import annotations

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

from .types import (
    SendGridContact,
    SendGridJobId,
    SendGridList,
    SendGridResponse,
    SendGridStat,
    SendGridTemplate,
    SendGridTemplateVersion,
)

logger = logging.getLogger("toolsconnector.sendgrid")


def _parse_contact(data: dict[str, Any]) -> SendGridContact:
    """Parse a SendGridContact from API JSON.

    Args:
        data: Raw JSON dict from the SendGrid API.

    Returns:
        A SendGridContact instance.
    """
    return SendGridContact(
        id=data.get("id"),
        email=data.get("email"),
        first_name=data.get("first_name"),
        last_name=data.get("last_name"),
        phone_number=data.get("phone_number"),
        address_line_1=data.get("address_line_1"),
        address_line_2=data.get("address_line_2"),
        city=data.get("city"),
        state_province_region=data.get("state_province_region"),
        postal_code=data.get("postal_code"),
        country=data.get("country"),
        alternate_emails=data.get("alternate_emails") or [],
        custom_fields=data.get("custom_fields") or {},
        list_ids=data.get("list_ids") or [],
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
    )


def _parse_template(data: dict[str, Any]) -> SendGridTemplate:
    """Parse a SendGridTemplate from API JSON.

    Args:
        data: Raw JSON dict from the SendGrid API.

    Returns:
        A SendGridTemplate instance.
    """
    versions = [
        SendGridTemplateVersion(
            id=v.get("id"),
            name=v.get("name"),
            subject=v.get("subject"),
            active=v.get("active", 0),
            html_content=v.get("html_content"),
            plain_content=v.get("plain_content"),
            editor=v.get("editor"),
            updated_at=v.get("updated_at"),
        )
        for v in data.get("versions", [])
    ]
    return SendGridTemplate(
        id=data["id"],
        name=data.get("name"),
        generation=data.get("generation"),
        updated_at=data.get("updated_at"),
        versions=versions,
    )


class SendGrid(BaseConnector):
    """Connect to SendGrid to send emails, manage contacts, and view statistics.

    Authenticates via Bearer token (API key) in the Authorization header.
    """

    name = "sendgrid"
    display_name = "SendGrid"
    category = ConnectorCategory.MARKETING
    protocol = ProtocolType.REST
    base_url = "https://api.sendgrid.com/v3"
    description = (
        "Connect to SendGrid to send transactional email, manage marketing "
        "contacts and lists, view email statistics, and manage templates."
    )
    _rate_limit_config = RateLimitSpec(rate=600, period=60, burst=50)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Initialise the httpx async client with Bearer token auth."""
        headers: dict[str, str] = {
            "Content-Type": "application/json",
        }
        if self._credentials:
            headers["Authorization"] = f"Bearer {self._credentials}"

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

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json: Optional[Any] = None,
    ) -> httpx.Response:
        """Send an authenticated request to the SendGrid API.

        Args:
            method: HTTP method (GET, POST, etc.).
            path: API path relative to base_url.
            params: Query parameters.
            json: JSON body for POST/PUT/PATCH requests.

        Returns:
            httpx.Response object.

        Raises:
            httpx.HTTPStatusError: On 4xx/5xx responses.
        """
        resp = await self._client.request(
            method, path, params=params, json=json,
        )
        resp.raise_for_status()
        return resp

    # ------------------------------------------------------------------
    # Actions — Email Sending
    # ------------------------------------------------------------------

    @action("Send an email via SendGrid", dangerous=True)
    async def send_email(
        self,
        to: str,
        from_email: str,
        subject: str,
        content: str,
        content_type: str = "text/plain",
    ) -> SendGridResponse:
        """Send a single email using the SendGrid v3 mail/send endpoint.

        The payload follows the SendGrid mail/send JSON structure with
        ``personalizations``, ``from``, ``subject``, and ``content`` fields.

        Args:
            to: Recipient email address.
            from_email: Sender email address.
            subject: Email subject line.
            content: Email body content.
            content_type: MIME type of content (``text/plain`` or
                ``text/html``). Defaults to ``text/plain``.

        Returns:
            SendGridResponse confirming acceptance.
        """
        payload: dict[str, Any] = {
            "personalizations": [
                {
                    "to": [{"email": to}],
                    "subject": subject,
                },
            ],
            "from": {"email": from_email},
            "content": [
                {
                    "type": content_type,
                    "value": content,
                },
            ],
        }

        resp = await self._request("POST", "/mail/send", json=payload)

        # SendGrid returns 202 with empty body on success
        message_id = resp.headers.get("X-Message-Id")
        return SendGridResponse(
            status_code=resp.status_code,
            message="Email accepted for delivery",
            message_id=message_id,
        )

    # ------------------------------------------------------------------
    # Actions — Contacts
    # ------------------------------------------------------------------

    @action("List marketing contacts from SendGrid")
    async def list_contacts(
        self,
        limit: int = 50,
    ) -> PaginatedList[SendGridContact]:
        """List marketing contacts.

        Uses the ``/marketing/contacts`` endpoint. SendGrid returns all
        contacts in a single response (no server-side pagination for the
        list endpoint), so we apply the limit client-side.

        Args:
            limit: Maximum number of contacts to return.

        Returns:
            Paginated list of SendGridContact objects.
        """
        resp = await self._request("GET", "/marketing/contacts")
        body = resp.json()

        all_contacts = body.get("result", [])
        items = [_parse_contact(c) for c in all_contacts[:limit]]

        has_more = len(all_contacts) > limit
        page_state = PageState(has_more=has_more)

        return PaginatedList(
            items=items,
            page_state=page_state,
            total_count=body.get("contact_count"),
        )

    @action("Add or update marketing contacts in SendGrid", dangerous=True)
    async def add_contacts(
        self,
        contacts: list[dict[str, Any]],
    ) -> SendGridJobId:
        """Add or update contacts (upsert) asynchronously.

        Each contact dict should contain at minimum an ``email`` field.
        Optional fields include ``first_name``, ``last_name``, etc.

        Args:
            contacts: List of contact dicts with at least ``email`` key.

        Returns:
            SendGridJobId for tracking the async import job.
        """
        payload: dict[str, Any] = {"contacts": contacts}
        resp = await self._request(
            "PUT", "/marketing/contacts", json=payload,
        )
        body = resp.json()
        return SendGridJobId(job_id=body["job_id"])

    @action("Search marketing contacts using a SGQL query")
    async def search_contacts(
        self,
        query: str,
    ) -> PaginatedList[SendGridContact]:
        """Search contacts using SendGrid Query Language (SGQL).

        Example query: ``email LIKE '%@example.com' AND CONTAINS(list_ids, 'abc-123')``

        Args:
            query: SGQL query string.

        Returns:
            Paginated list of matching SendGridContact objects.
        """
        payload: dict[str, Any] = {"query": query}
        resp = await self._request(
            "POST", "/marketing/contacts/search", json=payload,
        )
        body = resp.json()

        items = [_parse_contact(c) for c in body.get("result", [])]
        contact_count = body.get("contact_count", len(items))

        return PaginatedList(
            items=items,
            page_state=PageState(has_more=False),
            total_count=contact_count,
        )

    # ------------------------------------------------------------------
    # Actions — Lists
    # ------------------------------------------------------------------

    @action("List all contact lists in SendGrid")
    async def list_lists(self) -> list[SendGridList]:
        """List all marketing contact lists.

        Returns:
            List of SendGridList objects.
        """
        resp = await self._request("GET", "/marketing/lists")
        body = resp.json()

        return [
            SendGridList(
                id=lst.get("id"),
                name=lst.get("name"),
                contact_count=lst.get("contact_count", 0),
                sample_contacts=lst.get("_metadata", {}).get(
                    "sample_contacts", [],
                ),
                created_at=lst.get("created_at"),
                updated_at=lst.get("updated_at"),
            )
            for lst in body.get("result", [])
        ]

    # ------------------------------------------------------------------
    # Actions — Statistics
    # ------------------------------------------------------------------

    @action("Retrieve email statistics from SendGrid")
    async def get_stats(
        self,
        start_date: str,
        end_date: Optional[str] = None,
    ) -> list[SendGridStat]:
        """Retrieve global email statistics for a date range.

        Args:
            start_date: Start date in ``YYYY-MM-DD`` format.
            end_date: End date in ``YYYY-MM-DD`` format. Defaults to today.

        Returns:
            List of SendGridStat objects, one per day.
        """
        params: dict[str, Any] = {"start_date": start_date}
        if end_date:
            params["end_date"] = end_date

        resp = await self._request("GET", "/stats", params=params)
        body = resp.json()

        return [
            SendGridStat(
                date=entry.get("date"),
                stats=entry.get("stats", []),
            )
            for entry in body
        ]

    # ------------------------------------------------------------------
    # Actions — Templates
    # ------------------------------------------------------------------

    @action("List transactional templates from SendGrid")
    async def list_templates(
        self,
        limit: int = 50,
    ) -> PaginatedList[SendGridTemplate]:
        """List transactional templates.

        Args:
            limit: Maximum number of templates to return.

        Returns:
            Paginated list of SendGridTemplate objects.
        """
        params: dict[str, Any] = {
            "generations": "dynamic",
            "page_size": min(limit, 200),
        }
        resp = await self._request("GET", "/templates", params=params)
        body = resp.json()

        templates = body.get("result") or body.get("templates", [])
        items = [_parse_template(t) for t in templates]

        # SendGrid template pagination uses metadata
        metadata = body.get("_metadata", {})
        has_more = metadata.get("count", 0) > len(items)

        return PaginatedList(
            items=items,
            page_state=PageState(has_more=has_more),
            total_count=metadata.get("count"),
        )

    @action("Retrieve a single SendGrid template by ID")
    async def get_template(self, template_id: str) -> SendGridTemplate:
        """Retrieve a single transactional template with its versions.

        Args:
            template_id: The SendGrid template ID.

        Returns:
            SendGridTemplate object with version details.
        """
        resp = await self._request("GET", f"/templates/{template_id}")
        return _parse_template(resp.json())
