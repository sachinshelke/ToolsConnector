"""HubSpot connector -- contacts, deals, and CRM via the HubSpot API v3."""

from __future__ import annotations

from typing import Any, Optional

import httpx

from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import (
    ConnectorCategory,
    ProtocolType,
    RateLimitSpec,
)
from toolsconnector.types import PageState, PaginatedList

from .types import HubSpotContact, HubSpotDeal


class HubSpot(BaseConnector):
    """Connect to HubSpot to manage contacts, deals, and CRM data.

    Requires a private app access token passed as ``credentials``.
    Uses the HubSpot CRM API v3 with cursor-based pagination via
    ``paging.next.after``.
    """

    name = "hubspot"
    display_name = "HubSpot"
    category = ConnectorCategory.CRM
    protocol = ProtocolType.REST
    base_url = "https://api.hubapi.com"
    description = (
        "Connect to HubSpot CRM to manage contacts, deals, "
        "and search across CRM objects."
    )
    _rate_limit_config = RateLimitSpec(rate=100, period=10, burst=20)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Initialise the async HTTP client."""
        self._client = httpx.AsyncClient(
            base_url=self._base_url or self.__class__.base_url,
            headers={
                "Authorization": f"Bearer {self._credentials}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=self._timeout,
        )

    async def _teardown(self) -> None:
        """Close the HTTP client."""
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
        json: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Execute an HTTP request against the HubSpot API.

        Args:
            method: HTTP method.
            path: API path relative to ``base_url``.
            json: JSON request body.
            params: Query parameters.

        Returns:
            Parsed JSON response dict.

        Raises:
            httpx.HTTPStatusError: On non-2xx responses.
        """
        response = await self._client.request(
            method,
            path,
            json=json,
            params=params,
        )
        response.raise_for_status()
        if response.status_code == 204:
            return {}
        return response.json()

    # ------------------------------------------------------------------
    # Response parsers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_contact(data: dict[str, Any]) -> HubSpotContact:
        """Parse a raw HubSpot contact JSON into a HubSpotContact model."""
        return HubSpotContact(
            id=data.get("id", ""),
            properties=data.get("properties", {}),
            created_at=data.get("createdAt"),
            updated_at=data.get("updatedAt"),
            archived=data.get("archived", False),
        )

    @staticmethod
    def _parse_deal(data: dict[str, Any]) -> HubSpotDeal:
        """Parse a raw HubSpot deal JSON into a HubSpotDeal model."""
        return HubSpotDeal(
            id=data.get("id", ""),
            properties=data.get("properties", {}),
            created_at=data.get("createdAt"),
            updated_at=data.get("updatedAt"),
            archived=data.get("archived", False),
        )

    @staticmethod
    def _extract_cursor(data: dict[str, Any]) -> Optional[str]:
        """Extract the next cursor from the HubSpot paging envelope.

        Args:
            data: Raw API response dict.

        Returns:
            The ``after`` cursor string, or ``None`` if no more pages.
        """
        paging = data.get("paging")
        if not paging:
            return None
        next_page = paging.get("next")
        if not next_page:
            return None
        return next_page.get("after")

    # ------------------------------------------------------------------
    # Actions -- Contacts
    # ------------------------------------------------------------------

    @action("List contacts")
    async def list_contacts(
        self,
        limit: int = 100,
        after: Optional[str] = None,
    ) -> PaginatedList[HubSpotContact]:
        """List CRM contacts with cursor-based pagination.

        Args:
            limit: Maximum results per page (max 100).
            after: Cursor token from a previous response for the next page.

        Returns:
            Paginated list of HubSpotContact objects.
        """
        params: dict[str, Any] = {
            "limit": min(limit, 100),
        }
        if after:
            params["after"] = after

        data = await self._request(
            "GET", "/crm/v3/objects/contacts", params=params
        )

        contacts = [
            self._parse_contact(c) for c in data.get("results", [])
        ]
        next_cursor = self._extract_cursor(data)

        return PaginatedList(
            items=contacts,
            page_state=PageState(
                cursor=next_cursor,
                has_more=next_cursor is not None,
            ),
        )

    @action("Get a single contact by ID")
    async def get_contact(self, contact_id: str) -> HubSpotContact:
        """Retrieve a single CRM contact by its ID.

        Args:
            contact_id: The HubSpot contact ID.

        Returns:
            The requested HubSpotContact.
        """
        data = await self._request(
            "GET", f"/crm/v3/objects/contacts/{contact_id}"
        )
        return self._parse_contact(data)

    @action("Create a new contact", dangerous=True)
    async def create_contact(
        self,
        email: str,
        firstname: Optional[str] = None,
        lastname: Optional[str] = None,
        phone: Optional[str] = None,
        company: Optional[str] = None,
    ) -> HubSpotContact:
        """Create a new CRM contact.

        Args:
            email: Email address (required).
            firstname: First name.
            lastname: Last name.
            phone: Phone number.
            company: Company name.

        Returns:
            The newly created HubSpotContact.
        """
        properties: dict[str, Any] = {"email": email}
        if firstname is not None:
            properties["firstname"] = firstname
        if lastname is not None:
            properties["lastname"] = lastname
        if phone is not None:
            properties["phone"] = phone
        if company is not None:
            properties["company"] = company

        body: dict[str, Any] = {"properties": properties}
        data = await self._request(
            "POST", "/crm/v3/objects/contacts", json=body
        )
        return self._parse_contact(data)

    @action("Update an existing contact")
    async def update_contact(
        self,
        contact_id: str,
        properties: dict[str, Any],
    ) -> HubSpotContact:
        """Update properties on an existing CRM contact.

        Args:
            contact_id: The HubSpot contact ID.
            properties: Dict of property names to new values.

        Returns:
            The updated HubSpotContact.
        """
        body: dict[str, Any] = {"properties": properties}
        data = await self._request(
            "PATCH", f"/crm/v3/objects/contacts/{contact_id}", json=body
        )
        return self._parse_contact(data)

    # ------------------------------------------------------------------
    # Actions -- Deals
    # ------------------------------------------------------------------

    @action("List deals")
    async def list_deals(
        self,
        limit: int = 100,
        after: Optional[str] = None,
    ) -> PaginatedList[HubSpotDeal]:
        """List CRM deals with cursor-based pagination.

        Args:
            limit: Maximum results per page (max 100).
            after: Cursor token from a previous response for the next page.

        Returns:
            Paginated list of HubSpotDeal objects.
        """
        params: dict[str, Any] = {
            "limit": min(limit, 100),
        }
        if after:
            params["after"] = after

        data = await self._request(
            "GET", "/crm/v3/objects/deals", params=params
        )

        deals = [self._parse_deal(d) for d in data.get("results", [])]
        next_cursor = self._extract_cursor(data)

        return PaginatedList(
            items=deals,
            page_state=PageState(
                cursor=next_cursor,
                has_more=next_cursor is not None,
            ),
        )

    @action("Get a single deal by ID")
    async def get_deal(self, deal_id: str) -> HubSpotDeal:
        """Retrieve a single CRM deal by its ID.

        Args:
            deal_id: The HubSpot deal ID.

        Returns:
            The requested HubSpotDeal.
        """
        data = await self._request(
            "GET", f"/crm/v3/objects/deals/{deal_id}"
        )
        return self._parse_deal(data)

    @action("Create a new deal", dangerous=True)
    async def create_deal(
        self,
        dealname: str,
        pipeline: Optional[str] = None,
        dealstage: Optional[str] = None,
        amount: Optional[float] = None,
    ) -> HubSpotDeal:
        """Create a new CRM deal.

        Args:
            dealname: Name of the deal (required).
            pipeline: Pipeline ID (defaults to the default pipeline).
            dealstage: Deal stage ID within the pipeline.
            amount: Deal monetary amount.

        Returns:
            The newly created HubSpotDeal.
        """
        properties: dict[str, Any] = {"dealname": dealname}
        if pipeline is not None:
            properties["pipeline"] = pipeline
        if dealstage is not None:
            properties["dealstage"] = dealstage
        if amount is not None:
            properties["amount"] = str(amount)

        body: dict[str, Any] = {"properties": properties}
        data = await self._request(
            "POST", "/crm/v3/objects/deals", json=body
        )
        return self._parse_deal(data)

    # ------------------------------------------------------------------
    # Actions -- Search
    # ------------------------------------------------------------------

    @action("Search contacts by query")
    async def search_contacts(
        self,
        query: str,
        limit: int = 10,
    ) -> PaginatedList[HubSpotContact]:
        """Search CRM contacts using a full-text query.

        HubSpot's search endpoint searches across default searchable
        properties (firstname, lastname, email, phone, etc.).

        Args:
            query: Search query string.
            limit: Maximum results to return (max 100).

        Returns:
            Paginated list of matching HubSpotContact objects.
        """
        body: dict[str, Any] = {
            "query": query,
            "limit": min(limit, 100),
        }
        data = await self._request(
            "POST", "/crm/v3/objects/contacts/search", json=body
        )

        contacts = [
            self._parse_contact(c) for c in data.get("results", [])
        ]
        next_cursor = self._extract_cursor(data)

        return PaginatedList(
            items=contacts,
            page_state=PageState(
                cursor=next_cursor,
                has_more=next_cursor is not None,
            ),
            total_count=data.get("total"),
        )
