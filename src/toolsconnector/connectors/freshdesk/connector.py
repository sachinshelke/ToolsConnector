"""Freshdesk connector -- tickets, contacts, and helpdesk via Freshdesk API v2."""

from __future__ import annotations

import base64
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
    FreshdeskAgent,
    FreshdeskCompany,
    FreshdeskContact,
    FreshdeskNote,
    FreshdeskReply,
    FreshdeskTicket,
    FreshdeskTicketField,
)


class Freshdesk(BaseConnector):
    """Connect to Freshdesk to manage support tickets and contacts.

    Credentials format: ``"api_key:domain"`` where *domain* is the
    Freshdesk subdomain (e.g. ``"mycompany"`` for
    ``mycompany.freshdesk.com``).  Freshdesk uses the API key as the
    HTTP Basic username with ``X`` as the password.

    Uses page-number pagination via the ``page`` query parameter.
    """

    name = "freshdesk"
    display_name = "Freshdesk"
    category = ConnectorCategory.CRM
    protocol = ProtocolType.REST
    base_url = "https://{domain}.freshdesk.com/api/v2"
    description = (
        "Connect to Freshdesk helpdesk to manage support tickets, "
        "contacts, and conversations."
    )
    _rate_limit_config = RateLimitSpec(rate=50, period=60, burst=10)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _parse_credentials(self) -> tuple[str, str]:
        """Extract api_key and domain from credentials string.

        Returns:
            Tuple of (api_key, domain).
        """
        creds = str(self._credentials)
        if ":" not in creds:
            raise ValueError(
                "Freshdesk credentials must be 'api_key:domain' format"
            )
        api_key, domain = creds.split(":", 1)
        return api_key.strip(), domain.strip()

    async def _setup(self) -> None:
        """Initialise the async HTTP client with Basic auth."""
        api_key, domain = self._parse_credentials()
        # Freshdesk uses API key as username, "X" as password
        auth_bytes = base64.b64encode(f"{api_key}:X".encode()).decode()
        resolved_url = self._base_url or self.__class__.base_url
        resolved_url = resolved_url.replace("{domain}", domain)

        self._client = httpx.AsyncClient(
            base_url=resolved_url,
            headers={
                "Authorization": f"Basic {auth_bytes}",
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
    ) -> Any:
        """Execute an HTTP request against the Freshdesk API.

        Args:
            method: HTTP method.
            path: API path relative to ``base_url``.
            json: JSON request body.
            params: Query parameters.

        Returns:
            Parsed JSON response.

        Raises:
            httpx.HTTPStatusError: On non-2xx responses.
        """
        response = await self._client.request(
            method, path, json=json, params=params
        )
        response.raise_for_status()
        if response.status_code == 204:
            return {}
        return response.json()

    @staticmethod
    def _parse_ticket(data: dict[str, Any]) -> FreshdeskTicket:
        """Parse raw JSON into a FreshdeskTicket."""
        return FreshdeskTicket(
            id=data.get("id", 0),
            subject=data.get("subject", ""),
            description=data.get("description"),
            description_text=data.get("description_text"),
            status=data.get("status", 2),
            priority=data.get("priority", 1),
            type=data.get("type"),
            requester_id=data.get("requester_id"),
            responder_id=data.get("responder_id"),
            group_id=data.get("group_id"),
            source=data.get("source", 0),
            email=data.get("email"),
            tags=data.get("tags", []),
            cc_emails=data.get("cc_emails", []),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            due_by=data.get("due_by"),
        )

    @staticmethod
    def _parse_contact(data: dict[str, Any]) -> FreshdeskContact:
        """Parse raw JSON into a FreshdeskContact."""
        return FreshdeskContact(
            id=data.get("id", 0),
            name=data.get("name"),
            email=data.get("email"),
            phone=data.get("phone"),
            mobile=data.get("mobile"),
            company_id=data.get("company_id"),
            active=data.get("active", True),
            address=data.get("address"),
            job_title=data.get("job_title"),
            tags=data.get("tags", []),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )

    @staticmethod
    def _parse_reply(data: dict[str, Any]) -> FreshdeskReply:
        """Parse raw JSON into a FreshdeskReply."""
        return FreshdeskReply(
            id=data.get("id", 0),
            body=data.get("body", ""),
            body_text=data.get("body_text"),
            user_id=data.get("user_id"),
            ticket_id=data.get("ticket_id"),
            incoming=data.get("incoming", False),
            private=data.get("private", False),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            attachments=data.get("attachments", []),
        )

    # ------------------------------------------------------------------
    # Actions -- Tickets
    # ------------------------------------------------------------------

    @action("List support tickets")
    async def list_tickets(
        self,
        status: Optional[int] = None,
        priority: Optional[int] = None,
        limit: int = 30,
        page: int = 1,
    ) -> PaginatedList[FreshdeskTicket]:
        """List support tickets with optional filters.

        Args:
            status: Filter by status (2=Open, 3=Pending, 4=Resolved, 5=Closed).
            priority: Filter by priority (1=Low, 2=Medium, 3=High, 4=Urgent).
            limit: Number of tickets per page (max 100).
            page: Page number (1-indexed).

        Returns:
            Paginated list of FreshdeskTicket objects.
        """
        params: dict[str, Any] = {
            "per_page": min(limit, 100),
            "page": page,
        }
        if status is not None:
            params["filter"] = "status"
            params["status"] = status
        if priority is not None:
            params["priority"] = priority

        data = await self._request("GET", "/tickets", params=params)

        tickets = [self._parse_ticket(t) for t in (data if isinstance(data, list) else [])]
        # Freshdesk returns fewer results when no more pages
        has_more = len(tickets) >= min(limit, 100)

        return PaginatedList(
            items=tickets,
            page_state=PageState(
                page_number=page,
                has_more=has_more,
            ),
        )

    @action("Get a single ticket by ID")
    async def get_ticket(self, ticket_id: int) -> FreshdeskTicket:
        """Retrieve a single support ticket by its ID.

        Args:
            ticket_id: The Freshdesk ticket ID.

        Returns:
            The requested FreshdeskTicket.
        """
        data = await self._request("GET", f"/tickets/{ticket_id}")
        return self._parse_ticket(data)

    @action("Create a new support ticket", dangerous=True)
    async def create_ticket(
        self,
        subject: str,
        description: str,
        email: str,
        priority: int = 1,
        status: int = 2,
    ) -> FreshdeskTicket:
        """Create a new support ticket.

        Args:
            subject: Ticket subject line.
            description: Ticket body (HTML allowed).
            email: Requester email address.
            priority: Priority (1=Low, 2=Medium, 3=High, 4=Urgent).
            status: Initial status (2=Open, 3=Pending, 4=Resolved, 5=Closed).

        Returns:
            The newly created FreshdeskTicket.
        """
        body: dict[str, Any] = {
            "subject": subject,
            "description": description,
            "email": email,
            "priority": priority,
            "status": status,
        }
        data = await self._request("POST", "/tickets", json=body)
        return self._parse_ticket(data)

    @action("Update an existing ticket")
    async def update_ticket(
        self,
        ticket_id: int,
        status: Optional[int] = None,
        priority: Optional[int] = None,
    ) -> FreshdeskTicket:
        """Update the status or priority of a ticket.

        Args:
            ticket_id: The Freshdesk ticket ID.
            status: New status value.
            priority: New priority value.

        Returns:
            The updated FreshdeskTicket.
        """
        body: dict[str, Any] = {}
        if status is not None:
            body["status"] = status
        if priority is not None:
            body["priority"] = priority

        data = await self._request(
            "PUT", f"/tickets/{ticket_id}", json=body
        )
        return self._parse_ticket(data)

    @action("Reply to a ticket", dangerous=True)
    async def reply_to_ticket(
        self,
        ticket_id: int,
        body: str,
    ) -> FreshdeskReply:
        """Post a public reply to an existing ticket.

        Args:
            ticket_id: The Freshdesk ticket ID.
            body: Reply body (HTML allowed).

        Returns:
            The created FreshdeskReply.
        """
        payload: dict[str, Any] = {"body": body}
        data = await self._request(
            "POST", f"/tickets/{ticket_id}/reply", json=payload
        )
        return self._parse_reply(data)

    # ------------------------------------------------------------------
    # Actions -- Contacts
    # ------------------------------------------------------------------

    @action("List contacts")
    async def list_contacts(
        self,
        limit: int = 30,
        page: int = 1,
    ) -> PaginatedList[FreshdeskContact]:
        """List contacts with page-number pagination.

        Args:
            limit: Number of contacts per page (max 100).
            page: Page number (1-indexed).

        Returns:
            Paginated list of FreshdeskContact objects.
        """
        params: dict[str, Any] = {
            "per_page": min(limit, 100),
            "page": page,
        }
        data = await self._request("GET", "/contacts", params=params)

        contacts = [
            self._parse_contact(c)
            for c in (data if isinstance(data, list) else [])
        ]
        has_more = len(contacts) >= min(limit, 100)

        return PaginatedList(
            items=contacts,
            page_state=PageState(
                page_number=page,
                has_more=has_more,
            ),
        )

    @action("Get a single contact by ID")
    async def get_contact(self, contact_id: int) -> FreshdeskContact:
        """Retrieve a single contact by ID.

        Args:
            contact_id: The Freshdesk contact ID.

        Returns:
            The requested FreshdeskContact.
        """
        data = await self._request("GET", f"/contacts/{contact_id}")
        return self._parse_contact(data)

    # ------------------------------------------------------------------
    # Actions -- Search
    # ------------------------------------------------------------------

    @action("Search tickets using Freshdesk query language")
    async def search_tickets(
        self,
        query: str,
    ) -> PaginatedList[FreshdeskTicket]:
        """Search tickets using Freshdesk's query language.

        The query uses Freshdesk filter syntax, e.g.
        ``"priority:3 AND status:2"`` or ``"email:'user@example.com'"``.

        Args:
            query: Freshdesk search query string.

        Returns:
            Paginated list of matching FreshdeskTicket objects.
        """
        params: dict[str, Any] = {"query": f'"{query}"'}
        data = await self._request(
            "GET", "/search/tickets", params=params
        )

        results = data.get("results", []) if isinstance(data, dict) else []
        tickets = [self._parse_ticket(t) for t in results]
        total = data.get("total", 0) if isinstance(data, dict) else 0

        return PaginatedList(
            items=tickets,
            page_state=PageState(has_more=False),
            total_count=total,
        )

    # ------------------------------------------------------------------
    # Actions -- Ticket management (extended)
    # ------------------------------------------------------------------

    @action("Delete a Freshdesk ticket", dangerous=True)
    async def delete_ticket(self, ticket_id: int) -> bool:
        """Permanently delete a support ticket.

        Args:
            ticket_id: The Freshdesk ticket ID.

        Returns:
            True if the ticket was deleted successfully.
        """
        await self._request("DELETE", f"/tickets/{ticket_id}")
        return True

    @action("Add a note to a ticket")
    async def add_note(
        self, ticket_id: int, body: str,
    ) -> FreshdeskNote:
        """Add a private note to a ticket.

        Args:
            ticket_id: The Freshdesk ticket ID.
            body: Note body (HTML allowed).

        Returns:
            The created FreshdeskNote.
        """
        payload: dict[str, Any] = {"body": body, "private": True}
        data = await self._request(
            "POST", f"/tickets/{ticket_id}/notes", json=payload,
        )
        return FreshdeskNote(
            id=data.get("id", 0),
            body=data.get("body", ""),
            body_text=data.get("body_text"),
            user_id=data.get("user_id"),
            private=data.get("private", True),
            incoming=data.get("incoming", False),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )

    @action("Merge multiple tickets into one", dangerous=True)
    async def merge_tickets(
        self,
        primary_id: int,
        secondary_ids: list[int],
    ) -> bool:
        """Merge secondary tickets into a primary ticket.

        Args:
            primary_id: The ticket ID that will remain open.
            secondary_ids: List of ticket IDs to merge into the primary.

        Returns:
            True if the merge was successful.
        """
        payload: dict[str, Any] = {
            "primary_id": primary_id,
            "ticket_ids": secondary_ids,
        }
        await self._request(
            "POST", "/tickets/merge", json=payload,
        )
        return True

    # ------------------------------------------------------------------
    # Actions -- Agents
    # ------------------------------------------------------------------

    @action("List agents in Freshdesk")
    async def list_agents(
        self, limit: Optional[int] = None,
    ) -> list[FreshdeskAgent]:
        """List all agents in the helpdesk.

        Args:
            limit: Maximum number of agents to return.

        Returns:
            List of FreshdeskAgent objects.
        """
        params: dict[str, Any] = {}
        if limit is not None:
            params["per_page"] = min(limit, 100)
        data = await self._request(
            "GET", "/agents", params=params or None,
        )
        agents_list = data if isinstance(data, list) else []
        return [
            FreshdeskAgent(
                id=a.get("id", 0),
                name=a.get("contact", {}).get("name"),
                email=a.get("contact", {}).get("email"),
                active=a.get("active", True),
                occasional=a.get("occasional", False),
                ticket_scope=a.get("ticket_scope"),
                group_ids=a.get("group_ids", []),
                created_at=a.get("created_at"),
                updated_at=a.get("updated_at"),
            )
            for a in agents_list
        ]

    # ------------------------------------------------------------------
    # Actions -- Contact management (extended)
    # ------------------------------------------------------------------

    @action("Create a new contact", dangerous=True)
    async def create_contact(
        self,
        name: str,
        email: str,
    ) -> FreshdeskContact:
        """Create a new contact in Freshdesk.

        Args:
            name: Contact's full name.
            email: Contact's email address.

        Returns:
            The created FreshdeskContact.
        """
        payload: dict[str, Any] = {
            "name": name,
            "email": email,
        }
        data = await self._request("POST", "/contacts", json=payload)
        return self._parse_contact(data)

    @action("Update an existing contact")
    async def update_contact(
        self,
        contact_id: int,
        name: Optional[str] = None,
        email: Optional[str] = None,
    ) -> FreshdeskContact:
        """Update a contact's name or email.

        Args:
            contact_id: The Freshdesk contact ID.
            name: New name for the contact.
            email: New email for the contact.

        Returns:
            The updated FreshdeskContact.
        """
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if email is not None:
            payload["email"] = email

        data = await self._request(
            "PUT", f"/contacts/{contact_id}", json=payload,
        )
        return self._parse_contact(data)

    # ------------------------------------------------------------------
    # Actions -- Groups
    # ------------------------------------------------------------------

    @action("List agent groups in Freshdesk")
    async def list_groups(self) -> list[dict[str, Any]]:
        """List all agent groups in the helpdesk.

        Returns:
            List of group dicts with id, name, description, etc.
        """
        data = await self._request("GET", "/groups")
        return data if isinstance(data, list) else []

    # ------------------------------------------------------------------
    # Actions -- Agent details
    # ------------------------------------------------------------------

    @action("Get a single agent by ID")
    async def get_agent(self, agent_id: int) -> FreshdeskAgent:
        """Retrieve a single agent by their ID.

        Args:
            agent_id: The Freshdesk agent ID.

        Returns:
            FreshdeskAgent object.
        """
        data = await self._request("GET", f"/agents/{agent_id}")
        return FreshdeskAgent(
            id=data.get("id", 0),
            name=data.get("contact", {}).get("name"),
            email=data.get("contact", {}).get("email"),
            active=data.get("active", True),
            occasional=data.get("occasional", False),
            ticket_scope=data.get("ticket_scope"),
            group_ids=data.get("group_ids", []),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )

    # ------------------------------------------------------------------
    # Actions -- Companies
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_company(data: dict[str, Any]) -> FreshdeskCompany:
        """Parse raw JSON into a FreshdeskCompany."""
        return FreshdeskCompany(
            id=data.get("id", 0),
            name=data.get("name"),
            description=data.get("description"),
            domains=data.get("domains", []),
            note=data.get("note"),
            health_score=data.get("health_score"),
            account_tier=data.get("account_tier"),
            renewal_date=data.get("renewal_date"),
            industry=data.get("industry"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )

    @action("List companies in Freshdesk")
    async def list_companies(
        self,
        limit: int = 30,
        page: int = 1,
    ) -> PaginatedList[FreshdeskCompany]:
        """List companies with page-number pagination.

        Args:
            limit: Number of companies per page (max 100).
            page: Page number (1-indexed).

        Returns:
            Paginated list of FreshdeskCompany objects.
        """
        params: dict[str, Any] = {
            "per_page": min(limit, 100),
            "page": page,
        }
        data = await self._request("GET", "/companies", params=params)

        companies = [
            self._parse_company(c)
            for c in (data if isinstance(data, list) else [])
        ]
        has_more = len(companies) >= min(limit, 100)

        return PaginatedList(
            items=companies,
            page_state=PageState(
                page_number=page,
                has_more=has_more,
            ),
        )

    @action("Get a single company by ID")
    async def get_company(self, company_id: int) -> FreshdeskCompany:
        """Retrieve a single company by its ID.

        Args:
            company_id: The Freshdesk company ID.

        Returns:
            The requested FreshdeskCompany.
        """
        data = await self._request("GET", f"/companies/{company_id}")
        return self._parse_company(data)

    @action("Create a new company", dangerous=True)
    async def create_company(
        self,
        name: str,
        domains: Optional[list[str]] = None,
        description: Optional[str] = None,
    ) -> FreshdeskCompany:
        """Create a new company in Freshdesk.

        Args:
            name: Company name.
            domains: List of email domains associated with the company.
            description: Company description.

        Returns:
            The created FreshdeskCompany.
        """
        payload: dict[str, Any] = {"name": name}
        if domains is not None:
            payload["domains"] = domains
        if description is not None:
            payload["description"] = description

        data = await self._request("POST", "/companies", json=payload)
        return self._parse_company(data)

    # ------------------------------------------------------------------
    # Actions -- Ticket Fields
    # ------------------------------------------------------------------

    @action("List ticket fields in Freshdesk")
    async def list_ticket_fields(self) -> list[FreshdeskTicketField]:
        """List all ticket field definitions in the helpdesk.

        Returns:
            List of FreshdeskTicketField objects describing each
            system and custom ticket field.
        """
        data = await self._request("GET", "/ticket_fields")
        fields_list = data if isinstance(data, list) else []
        return [
            FreshdeskTicketField(
                id=f.get("id", 0),
                name=f.get("name", ""),
                label=f.get("label", ""),
                type=f.get("type", ""),
                default=f.get("default", False),
                required_for_closure=f.get("required_for_closure", False),
                required_for_agents=f.get("required_for_agents", False),
                required_for_customers=f.get("required_for_customers", False),
                position=f.get("position", 0),
                choices=f.get("choices", []),
                created_at=f.get("created_at"),
                updated_at=f.get("updated_at"),
            )
            for f in fields_list
        ]

    # ------------------------------------------------------------------
    # Actions -- Satisfaction Ratings
    # ------------------------------------------------------------------

    @action("List satisfaction ratings")
    async def list_satisfaction_ratings(
        self,
        limit: int = 30,
        page: int = 1,
    ) -> PaginatedList[dict[str, Any]]:
        """List customer satisfaction ratings.

        Args:
            limit: Number of ratings per page (max 100).
            page: Page number (1-indexed).

        Returns:
            Paginated list of satisfaction rating dicts containing
            id, survey_id, rating, feedback, etc.
        """
        params: dict[str, Any] = {
            "per_page": min(limit, 100),
            "page": page,
        }
        data = await self._request(
            "GET", "/surveys/satisfaction_ratings", params=params,
        )
        ratings = data if isinstance(data, list) else []
        has_more = len(ratings) >= min(limit, 100)

        return PaginatedList(
            items=ratings,
            page_state=PageState(
                page_number=page,
                has_more=has_more,
            ),
        )

    # ------------------------------------------------------------------
    # Actions -- Canned Responses
    # ------------------------------------------------------------------

    @action("List canned responses")
    async def list_canned_responses(self) -> list[dict[str, Any]]:
        """List all canned response templates in the helpdesk.

        Returns:
            List of canned response dicts with id, title, content, etc.
        """
        data = await self._request("GET", "/canned_responses")
        return data if isinstance(data, list) else []

    # ------------------------------------------------------------------
    # Actions -- Email Configs
    # ------------------------------------------------------------------

    @action("List email configurations")
    async def list_email_configs(self) -> list[dict[str, Any]]:
        """List all configured email addresses for the helpdesk.

        Returns:
            List of email config dicts with id, name, reply_email,
            to_email, primary_role, etc.
        """
        data = await self._request("GET", "/email_configs")
        return data if isinstance(data, list) else []
