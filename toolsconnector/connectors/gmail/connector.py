"""Gmail connector — read, send, and manage emails via the Gmail REST API v1."""

from __future__ import annotations

from typing import Optional

from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import ConnectorCategory, ProtocolType, RateLimitSpec
from toolsconnector.types import PageState, PaginatedList

from .types import DraftId, Email, Label, MessageId


class Gmail(BaseConnector):
    """Connect to Gmail to read, send, and manage emails.

    Supports OAuth 2.0 and service account authentication.
    Uses the Gmail REST API v1.
    """

    name = "gmail"
    display_name = "Gmail"
    category = ConnectorCategory.COMMUNICATION
    protocol = ProtocolType.REST
    base_url = "https://gmail.googleapis.com"
    description = "Connect to Gmail to read, send, and manage emails."
    _rate_limit_config = RateLimitSpec(rate=250, period=60, burst=50)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    @action("List emails matching a query", requires_scope="read")
    async def list_emails(
        self,
        query: str = "is:unread",
        limit: int = 10,
        labels: Optional[list[str]] = None,
        page_token: Optional[str] = None,
    ) -> PaginatedList[Email]:
        """List emails from the user's mailbox.

        Args:
            query: Gmail search query (same syntax as Gmail search bar).
            limit: Maximum number of emails to return per page.
            labels: Filter by label IDs (e.g., ["INBOX", "IMPORTANT"]).
            page_token: Token for fetching the next page of results.

        Returns:
            Paginated list of Email objects.
        """
        # Build API params
        params: dict = {"q": query, "maxResults": limit}
        if labels:
            params["labelIds"] = labels
        if page_token:
            params["pageToken"] = page_token

        # NOTE: Placeholder — the actual HTTP call would be:
        # response = await self._http_get(
        #     "/gmail/v1/users/me/messages", params=params
        # )
        # Then parse each message ID and batch-fetch full messages.

        return PaginatedList(
            items=[],
            page_state=PageState(has_more=False),
        )

    @action("Get a single email by ID", requires_scope="read")
    async def get_email(
        self,
        email_id: str,
        format: str = "full",
    ) -> Email:
        """Retrieve a single email message by its ID.

        Args:
            email_id: The ID of the email message to retrieve.
            format: Response format: 'full', 'metadata', 'minimal', or 'raw'.

        Returns:
            The requested Email object.
        """
        # Placeholder — would call:
        # response = await self._http_get(
        #     f"/gmail/v1/users/me/messages/{email_id}",
        #     params={"format": format},
        # )
        return Email(id=email_id, thread_id="", subject="")

    @action("Send an email", requires_scope="send", dangerous=True)
    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        cc: Optional[list[str]] = None,
        bcc: Optional[list[str]] = None,
        reply_to: Optional[str] = None,
    ) -> MessageId:
        """Send an email message.

        Args:
            to: Recipient email address.
            subject: Email subject line.
            body: Email body (supports HTML).
            cc: Optional CC recipients.
            bcc: Optional BCC recipients.
            reply_to: Optional reply-to address.

        Returns:
            MessageId with the sent message's ID.
        """
        # Placeholder — would build RFC 2822 message and POST to:
        # /gmail/v1/users/me/messages/send
        return MessageId(id="sent-placeholder")

    @action("Search emails with advanced query", requires_scope="read")
    async def search_emails(
        self,
        query: str,
        limit: int = 25,
        page_token: Optional[str] = None,
    ) -> PaginatedList[Email]:
        """Search emails using Gmail's advanced query syntax.

        Args:
            query: Gmail search query (e.g., "from:boss has:attachment after:2024/01/01").
            limit: Maximum results per page.
            page_token: Pagination token for next page.

        Returns:
            Paginated list of matching emails.
        """
        return PaginatedList(items=[], page_state=PageState(has_more=False))

    @action("List all labels", requires_scope="read")
    async def list_labels(self) -> list[Label]:
        """List all labels in the user's mailbox.

        Returns:
            List of Label objects.
        """
        # Placeholder — would call:
        # response = await self._http_get("/gmail/v1/users/me/labels")
        return []

    @action("Create a draft email", requires_scope="send")
    async def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
        cc: Optional[list[str]] = None,
    ) -> DraftId:
        """Create a draft email message.

        Args:
            to: Recipient email address.
            subject: Email subject line.
            body: Email body (supports HTML).
            cc: Optional CC recipients.

        Returns:
            DraftId with the created draft's ID.
        """
        # Placeholder — would POST to:
        # /gmail/v1/users/me/drafts
        return DraftId(id="draft-placeholder")

    @action("Delete an email", requires_scope="full", dangerous=True)
    async def delete_email(self, email_id: str) -> None:
        """Permanently delete an email message.

        Args:
            email_id: The ID of the email to delete.

        Warning:
            This action permanently deletes the email. It cannot be undone.
        """
        # Placeholder — would call:
        # await self._http_delete(
        #     f"/gmail/v1/users/me/messages/{email_id}"
        # )
        pass

    @action("Modify email labels", requires_scope="full")
    async def modify_labels(
        self,
        email_id: str,
        add_labels: Optional[list[str]] = None,
        remove_labels: Optional[list[str]] = None,
    ) -> Email:
        """Add or remove labels from an email.

        Args:
            email_id: The ID of the email to modify.
            add_labels: Labels to add (e.g., ["STARRED", "IMPORTANT"]).
            remove_labels: Labels to remove (e.g., ["UNREAD"]).

        Returns:
            The updated Email object.
        """
        # Placeholder — would POST to:
        # /gmail/v1/users/me/messages/{email_id}/modify
        return Email(id=email_id, thread_id="", subject="")
