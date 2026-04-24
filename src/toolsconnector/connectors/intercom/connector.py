"""Intercom connector -- contacts, conversations, and messaging via Intercom API."""

from __future__ import annotations

from typing import Any, Optional

import httpx

from toolsconnector.connectors._helpers import raise_typed_for_status
from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import (
    ConnectorCategory,
    ProtocolType,
    RateLimitSpec,
)
from toolsconnector.types import PageState, PaginatedList

from .types import (
    IntercomAdmin,
    IntercomContact,
    IntercomConversation,
    IntercomMessage,
    IntercomTag,
)


class Intercom(BaseConnector):
    """Connect to Intercom to manage contacts, conversations, and messaging.

    Requires an access token (from an Intercom OAuth app or personal
    token) passed as ``credentials``.  Uses cursor-based pagination
    via ``starting_after`` for list endpoints and scroll/search for
    contacts.
    """

    name = "intercom"
    display_name = "Intercom"
    category = ConnectorCategory.CRM
    protocol = ProtocolType.REST
    base_url = "https://api.intercom.io"
    description = "Connect to Intercom to manage contacts, conversations, and send messages."
    _rate_limit_config = RateLimitSpec(rate=100, period=10, burst=20)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Initialise the async HTTP client with Bearer auth."""
        self._client = httpx.AsyncClient(
            base_url=self._base_url or self.__class__.base_url,
            headers={
                "Authorization": f"Bearer {self._credentials}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Intercom-Version": "2.10",
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
        """Execute an HTTP request against the Intercom API.

        Args:
            method: HTTP method.
            path: API path relative to ``base_url``.
            json: JSON request body.
            params: Query parameters.

        Returns:
            Parsed JSON response dict.

        Raises:
            toolsconnector.errors.APIError (subclass): On any non-2xx response.
                Maps to a typed exception by status: 401 -> InvalidCredentialsError
                or TokenExpiredError; 403 -> PermissionDeniedError; 404 -> NotFoundError;
                409 -> ConflictError; 400/422 -> ValidationError; 429 -> RateLimitError;
                5xx -> ServerError; other 4xx -> APIError. See
                toolsconnector.connectors._helpers.raise_typed_for_status for the full mapping.

        """
        response = await self._client.request(method, path, json=json, params=params)
        raise_typed_for_status(response, connector=self.name)
        if response.status_code == 204:
            return {}
        return response.json()

    @staticmethod
    def _parse_contact(data: dict[str, Any]) -> IntercomContact:
        """Parse raw JSON into an IntercomContact."""
        return IntercomContact(
            id=data.get("id", ""),
            type=data.get("type", "contact"),
            role=data.get("role", "user"),
            email=data.get("email"),
            name=data.get("name"),
            phone=data.get("phone"),
            external_id=data.get("external_id"),
            avatar=data.get("avatar", {}).get("image_url")
            if isinstance(data.get("avatar"), dict)
            else None,
            owner_id=data.get("owner_id"),
            signed_up_at=data.get("signed_up_at"),
            last_seen_at=data.get("last_seen_at"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            unsubscribed_from_emails=data.get("unsubscribed_from_emails", False),
            has_hard_bounced=data.get("has_hard_bounced", False),
            custom_attributes=data.get("custom_attributes", {}),
            tags=data.get("tags", {}).get("data", []) if isinstance(data.get("tags"), dict) else [],
            location=data.get("location"),
        )

    @staticmethod
    def _parse_conversation(data: dict[str, Any]) -> IntercomConversation:
        """Parse raw JSON into an IntercomConversation."""
        contacts_data = data.get("contacts", {})
        contacts_list = contacts_data.get("contacts", []) if isinstance(contacts_data, dict) else []
        return IntercomConversation(
            id=data.get("id", ""),
            type=data.get("type", "conversation"),
            title=data.get("title"),
            state=data.get("state", "open"),
            read=data.get("read", False),
            priority=data.get("priority", "not_priority"),
            admin_assignee_id=data.get("admin_assignee_id"),
            team_assignee_id=data.get("team_assignee_id"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            waiting_since=data.get("waiting_since"),
            snoozed_until=data.get("snoozed_until"),
            open=data.get("open", True),
            tags=data.get("tags", {}).get("tags", []) if isinstance(data.get("tags"), dict) else [],
            source=data.get("source"),
            contacts=contacts_list,
            statistics=data.get("statistics"),
        )

    @staticmethod
    def _parse_message(data: dict[str, Any]) -> IntercomMessage:
        """Parse raw JSON into an IntercomMessage."""
        return IntercomMessage(
            id=data.get("id", ""),
            type=data.get("type", "admin_message"),
            message_type=data.get("message_type", "email"),
            subject=data.get("subject"),
            body=data.get("body", ""),
            created_at=data.get("created_at"),
            owner=data.get("owner"),
        )

    # ------------------------------------------------------------------
    # Actions -- Contacts
    # ------------------------------------------------------------------

    @action("List contacts")
    async def list_contacts(
        self,
        limit: int = 50,
        starting_after: Optional[str] = None,
    ) -> PaginatedList[IntercomContact]:
        """List contacts with cursor-based pagination.

        Args:
            limit: Maximum results per page (max 150).
            starting_after: Cursor from a previous response for the next page.

        Returns:
            Paginated list of IntercomContact objects.
        """
        params: dict[str, Any] = {
            "per_page": min(limit, 150),
        }
        if starting_after:
            params["starting_after"] = starting_after

        data = await self._request("GET", "/contacts", params=params)

        contacts_data = data.get("data", [])
        contacts = [self._parse_contact(c) for c in contacts_data]

        pages = data.get("pages", {})
        next_info = pages.get("next")
        next_cursor = None
        if isinstance(next_info, dict):
            next_cursor = next_info.get("starting_after")

        return PaginatedList(
            items=contacts,
            page_state=PageState(
                cursor=next_cursor,
                has_more=next_cursor is not None,
            ),
            total_count=data.get("total_count"),
        )

    @action("Get a single contact by ID")
    async def get_contact(self, contact_id: str) -> IntercomContact:
        """Retrieve a single contact by ID.

        Args:
            contact_id: The Intercom contact ID.

        Returns:
            The requested IntercomContact.
        """
        data = await self._request("GET", f"/contacts/{contact_id}")
        return self._parse_contact(data)

    @action("Create a new contact", dangerous=True)
    async def create_contact(
        self,
        role: str = "user",
        email: Optional[str] = None,
        name: Optional[str] = None,
        phone: Optional[str] = None,
    ) -> IntercomContact:
        """Create a new contact (user or lead).

        Args:
            role: Contact role: ``"user"`` or ``"lead"``.
            email: Email address.
            name: Full name.
            phone: Phone number.

        Returns:
            The newly created IntercomContact.
        """
        body: dict[str, Any] = {"role": role}
        if email is not None:
            body["email"] = email
        if name is not None:
            body["name"] = name
        if phone is not None:
            body["phone"] = phone

        data = await self._request("POST", "/contacts", json=body)
        return self._parse_contact(data)

    @action("Search contacts using filters")
    async def search_contacts(
        self,
        query: str,
        field: str = "email",
        operator: str = "=",
    ) -> PaginatedList[IntercomContact]:
        """Search contacts using Intercom's search API.

        Args:
            query: The value to search for.
            field: The contact field to search on (e.g. ``"email"``,
                ``"name"``, ``"phone"``).
            operator: Comparison operator (``"="``, ``"!="``, ``"~"``,
                ``"contains"``, ``"starts_with"``).

        Returns:
            Paginated list of matching IntercomContact objects.
        """
        body: dict[str, Any] = {
            "query": {
                "field": field,
                "operator": operator,
                "value": query,
            },
        }
        data = await self._request("POST", "/contacts/search", json=body)

        contacts_data = data.get("data", [])
        contacts = [self._parse_contact(c) for c in contacts_data]

        pages = data.get("pages", {})
        next_info = pages.get("next")
        next_cursor = None
        if isinstance(next_info, dict):
            next_cursor = next_info.get("starting_after")

        return PaginatedList(
            items=contacts,
            page_state=PageState(
                cursor=next_cursor,
                has_more=next_cursor is not None,
            ),
            total_count=data.get("total_count"),
        )

    # ------------------------------------------------------------------
    # Actions -- Conversations
    # ------------------------------------------------------------------

    @action("List conversations")
    async def list_conversations(
        self,
        limit: int = 20,
        starting_after: Optional[str] = None,
    ) -> PaginatedList[IntercomConversation]:
        """List conversations with cursor-based pagination.

        Args:
            limit: Maximum results per page (max 150).
            starting_after: Cursor from a previous response for the next page.

        Returns:
            Paginated list of IntercomConversation objects.
        """
        params: dict[str, Any] = {
            "per_page": min(limit, 150),
        }
        if starting_after:
            params["starting_after"] = starting_after

        data = await self._request("GET", "/conversations", params=params)

        conversations_data = data.get("conversations", [])
        conversations = [self._parse_conversation(c) for c in conversations_data]

        pages = data.get("pages", {})
        next_info = pages.get("next")
        next_cursor = None
        if isinstance(next_info, dict):
            next_cursor = next_info.get("starting_after")

        return PaginatedList(
            items=conversations,
            page_state=PageState(
                cursor=next_cursor,
                has_more=next_cursor is not None,
            ),
            total_count=data.get("total_count"),
        )

    @action("Get a single conversation by ID")
    async def get_conversation(
        self,
        conversation_id: str,
    ) -> IntercomConversation:
        """Retrieve a single conversation by its ID.

        Args:
            conversation_id: The Intercom conversation ID.

        Returns:
            The requested IntercomConversation.
        """
        data = await self._request("GET", f"/conversations/{conversation_id}")
        return self._parse_conversation(data)

    @action("Reply to a conversation", dangerous=True)
    async def reply_to_conversation(
        self,
        conversation_id: str,
        body: str,
        message_type: str = "comment",
    ) -> IntercomConversation:
        """Post a reply to an existing conversation.

        Args:
            conversation_id: The Intercom conversation ID.
            body: Reply body text.
            message_type: Type of reply: ``"comment"`` or ``"note"``.

        Returns:
            The updated IntercomConversation.
        """
        payload: dict[str, Any] = {
            "body": body,
            "message_type": message_type,
            "type": "admin",
        }
        data = await self._request(
            "POST",
            f"/conversations/{conversation_id}/reply",
            json=payload,
        )
        return self._parse_conversation(data)

    # ------------------------------------------------------------------
    # Actions -- Messages
    # ------------------------------------------------------------------

    @action("Create and send a new message", dangerous=True)
    async def create_message(
        self,
        from_email: str,
        to_email: str,
        subject: str,
        body: str,
    ) -> IntercomMessage:
        """Create and send a new outbound message.

        Args:
            from_email: Admin email sending the message.
            to_email: Recipient contact email address.
            subject: Message subject line.
            body: Message body (HTML allowed).

        Returns:
            The created IntercomMessage.
        """
        payload: dict[str, Any] = {
            "message_type": "email",
            "subject": subject,
            "body": body,
            "from": {
                "type": "admin",
                "email": from_email,
            },
            "to": {
                "type": "user",
                "email": to_email,
            },
        }
        data = await self._request("POST", "/messages", json=payload)
        return self._parse_message(data)

    # ------------------------------------------------------------------
    # Actions -- Admins
    # ------------------------------------------------------------------

    @action("List all admins in the workspace")
    async def list_admins(self) -> list[IntercomAdmin]:
        """List all admins and operators in the workspace.

        Returns:
            List of IntercomAdmin objects.
        """
        data = await self._request("GET", "/admins")
        return [
            IntercomAdmin(
                id=a.get("id", ""),
                type=a.get("type", "admin"),
                name=a.get("name"),
                email=a.get("email"),
                job_title=a.get("job_title"),
                has_inbox_seat=a.get("has_inbox_seat", False),
                avatar=a.get("avatar", {}).get("image_url")
                if isinstance(a.get("avatar"), dict)
                else None,
            )
            for a in data.get("admins", [])
        ]

    # ------------------------------------------------------------------
    # Actions -- Conversation management (extended)
    # ------------------------------------------------------------------

    @action("Close a conversation")
    async def close_conversation(
        self,
        conversation_id: str,
    ) -> IntercomConversation:
        """Close an open conversation.

        Args:
            conversation_id: The Intercom conversation ID.

        Returns:
            The closed IntercomConversation.
        """
        payload: dict[str, Any] = {
            "message_type": "close",
            "type": "admin",
            "body": "Closing conversation.",
        }
        data = await self._request(
            "POST",
            f"/conversations/{conversation_id}/parts",
            json=payload,
        )
        return self._parse_conversation(data)

    # ------------------------------------------------------------------
    # Actions -- Tags
    # ------------------------------------------------------------------

    @action("Tag a contact", dangerous=True)
    async def tag_contact(
        self,
        contact_id: str,
        tag_name: str,
    ) -> bool:
        """Apply a tag to a contact.

        Args:
            contact_id: The Intercom contact ID.
            tag_name: Name of the tag to apply.

        Returns:
            True if the tag was applied successfully.
        """
        payload: dict[str, Any] = {
            "name": tag_name,
            "users": [{"id": contact_id}],
        }
        await self._request("POST", "/tags", json=payload)
        return True

    # ------------------------------------------------------------------
    # Actions -- Notes
    # ------------------------------------------------------------------

    @action("Create a note on a contact", dangerous=True)
    async def create_note(
        self,
        contact_id: str,
        body: str,
    ) -> dict[str, Any]:
        """Create a note on an Intercom contact.

        Args:
            contact_id: The Intercom contact ID.
            body: Note body text (HTML allowed).

        Returns:
            Dict with the created note details.
        """
        payload: dict[str, Any] = {"body": body}
        data = await self._request(
            "POST",
            f"/contacts/{contact_id}/notes",
            json=payload,
        )
        return data

    @action("List notes on a contact")
    async def list_notes(
        self,
        contact_id: str,
    ) -> list[dict[str, Any]]:
        """List all notes on an Intercom contact.

        Args:
            contact_id: The Intercom contact ID.

        Returns:
            List of note dicts with id, body, author, etc.
        """
        data = await self._request(
            "GET",
            f"/contacts/{contact_id}/notes",
        )
        return data.get("data", [])

    # ------------------------------------------------------------------
    # Actions -- Admin details
    # ------------------------------------------------------------------

    @action("Get a single admin by ID")
    async def get_admin(self, admin_id: str) -> IntercomAdmin:
        """Retrieve a single admin by their ID.

        Args:
            admin_id: The Intercom admin ID.

        Returns:
            The requested IntercomAdmin.
        """
        data = await self._request("GET", f"/admins/{admin_id}")
        return IntercomAdmin(
            id=data.get("id", ""),
            type=data.get("type", "admin"),
            name=data.get("name"),
            email=data.get("email"),
            job_title=data.get("job_title"),
            has_inbox_seat=data.get("has_inbox_seat", False),
            avatar=data.get("avatar", {}).get("image_url")
            if isinstance(data.get("avatar"), dict)
            else None,
        )

    # ------------------------------------------------------------------
    # Actions -- Contact updates
    # ------------------------------------------------------------------

    @action("Update an existing contact")
    async def update_contact(
        self,
        contact_id: str,
        name: Optional[str] = None,
        email: Optional[str] = None,
    ) -> IntercomContact:
        """Update an existing contact's attributes.

        Args:
            contact_id: The Intercom contact ID.
            name: New full name.
            email: New email address.

        Returns:
            The updated IntercomContact.
        """
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if email is not None:
            body["email"] = email

        data = await self._request(
            "PUT",
            f"/contacts/{contact_id}",
            json=body,
        )
        return self._parse_contact(data)

    @action("List all tags in the workspace")
    async def list_tags(self) -> list[IntercomTag]:
        """List all tags defined in the workspace.

        Returns:
            List of IntercomTag objects.
        """
        data = await self._request("GET", "/tags")
        return [
            IntercomTag(
                id=t.get("id", ""),
                name=t.get("name", ""),
                type=t.get("type", "tag"),
                applied_count=t.get("applied_count"),
            )
            for t in data.get("data", [])
        ]
