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

from ._helpers import (
    extract_cursor,
    parse_company,
    parse_contact,
    parse_deal,
    parse_pipeline,
    parse_ticket,
)
from .types import (
    HubSpotCompany,
    HubSpotContact,
    HubSpotDeal,
    HubSpotPipeline,
    HubSpotTicket,
)


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
        "Connect to HubSpot CRM to manage contacts, deals, companies, tickets, and pipelines."
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
        params: dict[str, Any] = {"limit": min(limit, 100)}
        if after:
            params["after"] = after

        data = await self._request("GET", "/crm/v3/objects/contacts", params=params)

        contacts = [parse_contact(c) for c in data.get("results", [])]
        next_cursor = extract_cursor(data)

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
        data = await self._request("GET", f"/crm/v3/objects/contacts/{contact_id}")
        return parse_contact(data)

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
        data = await self._request("POST", "/crm/v3/objects/contacts", json=body)
        return parse_contact(data)

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
        data = await self._request("PATCH", f"/crm/v3/objects/contacts/{contact_id}", json=body)
        return parse_contact(data)

    @action("Delete a contact", dangerous=True)
    async def delete_contact(self, contact_id: str) -> None:
        """Delete a CRM contact by its ID.

        This is a destructive action.  The contact is moved to the
        recycling bin and can be restored within 90 days.

        Args:
            contact_id: The HubSpot contact ID to delete.
        """
        await self._request("DELETE", f"/crm/v3/objects/contacts/{contact_id}")

    @action("Search contacts by query")
    async def search_contacts(
        self,
        query: str,
        limit: int = 10,
    ) -> PaginatedList[HubSpotContact]:
        """Search CRM contacts using a full-text query.

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
        data = await self._request("POST", "/crm/v3/objects/contacts/search", json=body)

        contacts = [parse_contact(c) for c in data.get("results", [])]
        next_cursor = extract_cursor(data)

        return PaginatedList(
            items=contacts,
            page_state=PageState(
                cursor=next_cursor,
                has_more=next_cursor is not None,
            ),
            total_count=data.get("total"),
        )

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
        params: dict[str, Any] = {"limit": min(limit, 100)}
        if after:
            params["after"] = after

        data = await self._request("GET", "/crm/v3/objects/deals", params=params)

        deals = [parse_deal(d) for d in data.get("results", [])]
        next_cursor = extract_cursor(data)

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
        data = await self._request("GET", f"/crm/v3/objects/deals/{deal_id}")
        return parse_deal(data)

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
        data = await self._request("POST", "/crm/v3/objects/deals", json=body)
        return parse_deal(data)

    # ------------------------------------------------------------------
    # Actions -- Companies
    # ------------------------------------------------------------------

    @action("List companies")
    async def list_companies(
        self,
        limit: int = 100,
        after: Optional[str] = None,
    ) -> PaginatedList[HubSpotCompany]:
        """List CRM companies with cursor-based pagination.

        Args:
            limit: Maximum results per page (max 100).
            after: Cursor token from a previous response for the next page.

        Returns:
            Paginated list of HubSpotCompany objects.
        """
        params: dict[str, Any] = {"limit": min(limit, 100)}
        if after:
            params["after"] = after

        data = await self._request("GET", "/crm/v3/objects/companies", params=params)

        companies = [parse_company(c) for c in data.get("results", [])]
        next_cursor = extract_cursor(data)

        return PaginatedList(
            items=companies,
            page_state=PageState(
                cursor=next_cursor,
                has_more=next_cursor is not None,
            ),
        )

    @action("Get a single company by ID")
    async def get_company(self, company_id: str) -> HubSpotCompany:
        """Retrieve a single CRM company by its ID.

        Args:
            company_id: The HubSpot company ID.

        Returns:
            The requested HubSpotCompany.
        """
        data = await self._request("GET", f"/crm/v3/objects/companies/{company_id}")
        return parse_company(data)

    @action("Create a new company", dangerous=True)
    async def create_company(
        self,
        name: str,
        domain: Optional[str] = None,
        properties: Optional[dict[str, Any]] = None,
    ) -> HubSpotCompany:
        """Create a new CRM company.

        Args:
            name: Company name (required).
            domain: Company domain / website.
            properties: Additional property key-value pairs.

        Returns:
            The newly created HubSpotCompany.
        """
        props: dict[str, Any] = {"name": name}
        if domain is not None:
            props["domain"] = domain
        if properties:
            props.update(properties)

        body: dict[str, Any] = {"properties": props}
        data = await self._request("POST", "/crm/v3/objects/companies", json=body)
        return parse_company(data)

    # ------------------------------------------------------------------
    # Actions -- Tickets
    # ------------------------------------------------------------------

    @action("List tickets")
    async def list_tickets(
        self,
        limit: int = 100,
        after: Optional[str] = None,
    ) -> PaginatedList[HubSpotTicket]:
        """List CRM tickets with cursor-based pagination.

        Args:
            limit: Maximum results per page (max 100).
            after: Cursor token from a previous response for the next page.

        Returns:
            Paginated list of HubSpotTicket objects.
        """
        params: dict[str, Any] = {"limit": min(limit, 100)}
        if after:
            params["after"] = after

        data = await self._request("GET", "/crm/v3/objects/tickets", params=params)

        tickets = [parse_ticket(t) for t in data.get("results", [])]
        next_cursor = extract_cursor(data)

        return PaginatedList(
            items=tickets,
            page_state=PageState(
                cursor=next_cursor,
                has_more=next_cursor is not None,
            ),
        )

    @action("Create a new ticket", dangerous=True)
    async def create_ticket(
        self,
        subject: str,
        pipeline: Optional[str] = None,
        stage: Optional[str] = None,
        priority: Optional[str] = None,
    ) -> HubSpotTicket:
        """Create a new CRM ticket.

        Args:
            subject: Ticket subject (required).
            pipeline: Pipeline ID for the ticket.
            stage: Pipeline stage ID.
            priority: Ticket priority (e.g., ``"HIGH"``).

        Returns:
            The newly created HubSpotTicket.
        """
        properties: dict[str, Any] = {"subject": subject}
        if pipeline is not None:
            properties["hs_pipeline"] = pipeline
        if stage is not None:
            properties["hs_pipeline_stage"] = stage
        if priority is not None:
            properties["hs_ticket_priority"] = priority

        body: dict[str, Any] = {"properties": properties}
        data = await self._request("POST", "/crm/v3/objects/tickets", json=body)
        return parse_ticket(data)

    @action("Get a single ticket by ID")
    async def get_ticket(self, ticket_id: str) -> HubSpotTicket:
        """Retrieve a single CRM ticket by its ID.

        Args:
            ticket_id: The HubSpot ticket ID.

        Returns:
            The requested HubSpotTicket.
        """
        data = await self._request("GET", f"/crm/v3/objects/tickets/{ticket_id}")
        return parse_ticket(data)

    @action("Update an existing deal")
    async def update_deal(
        self,
        deal_id: str,
        properties: dict[str, Any],
    ) -> HubSpotDeal:
        """Update properties on an existing CRM deal.

        Args:
            deal_id: The HubSpot deal ID.
            properties: Dict of property names to new values.

        Returns:
            The updated HubSpotDeal.
        """
        body: dict[str, Any] = {"properties": properties}
        data = await self._request("PATCH", f"/crm/v3/objects/deals/{deal_id}", json=body)
        return parse_deal(data)

    @action("Update an existing ticket")
    async def update_ticket(
        self,
        ticket_id: str,
        properties: dict[str, Any],
    ) -> HubSpotTicket:
        """Update properties on an existing CRM ticket.

        Args:
            ticket_id: The HubSpot ticket ID.
            properties: Dict of property names to new values.

        Returns:
            The updated HubSpotTicket.
        """
        body: dict[str, Any] = {"properties": properties}
        data = await self._request("PATCH", f"/crm/v3/objects/tickets/{ticket_id}", json=body)
        return parse_ticket(data)

    @action("Delete a deal", dangerous=True)
    async def delete_deal(self, deal_id: str) -> None:
        """Delete a CRM deal by its ID.

        This is a destructive action. The deal is moved to the
        recycling bin and can be restored within 90 days.

        Args:
            deal_id: The HubSpot deal ID to delete.
        """
        await self._request("DELETE", f"/crm/v3/objects/deals/{deal_id}")

    # ------------------------------------------------------------------
    # Actions -- Pipelines
    # ------------------------------------------------------------------

    @action("List pipelines for an object type")
    async def list_pipelines(
        self,
        object_type: str = "deals",
    ) -> list[HubSpotPipeline]:
        """List all pipelines for a given CRM object type.

        Args:
            object_type: The CRM object type (e.g., ``"deals"``,
                ``"tickets"``).  Defaults to ``"deals"``.

        Returns:
            List of HubSpotPipeline objects with their stages.
        """
        data = await self._request("GET", f"/crm/v3/pipelines/{object_type}")
        return [parse_pipeline(p) for p in data.get("results", [])]
