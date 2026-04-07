"""Gmail connector -- read, send, and manage emails via the Gmail REST API v1.

Uses httpx for direct HTTP calls against the Gmail REST API.
Expects an OAuth 2.0 access token passed as ``credentials``.
"""

from __future__ import annotations

import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Optional

import httpx

from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import ConnectorCategory, ProtocolType, RateLimitSpec
from toolsconnector.types import PageState, PaginatedList

from ._helpers import parse_message as _parse_message
from .types import Attachment, DraftId, Email, EmailAddress, Label, LabelColor, MessageId, Thread


class Gmail(BaseConnector):
    """Connect to Gmail to read, send, and manage emails.

    Supports OAuth 2.0 authentication. Pass an access token as
    ``credentials`` when instantiating. Uses the Gmail REST API v1
    via direct httpx calls.
    """

    name = "gmail"
    display_name = "Gmail"
    category = ConnectorCategory.COMMUNICATION
    protocol = ProtocolType.REST
    base_url = "https://gmail.googleapis.com/gmail/v1"
    description = "Connect to Gmail to read, send, and manage emails."
    _rate_limit_config = RateLimitSpec(rate=250, period=60, burst=50)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_headers(self) -> dict[str, str]:
        """Build authorization headers for Gmail API requests.

        Returns:
            Dict with Authorization bearer header.
        """
        return {"Authorization": f"Bearer {self._credentials}"}

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """Execute an authenticated HTTP request against the Gmail API.

        Args:
            method: HTTP method (GET, POST, DELETE, etc.).
            path: API path relative to base_url (e.g., '/users/me/messages').
            **kwargs: Additional keyword arguments passed to httpx (params, json, etc.).

        Returns:
            Parsed JSON response as a dict.

        Raises:
            httpx.HTTPStatusError: If the API returns a non-2xx status.
        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.request(
                method,
                f"{self._base_url}{path}",
                headers=self._get_headers(),
                **kwargs,
            )
            response.raise_for_status()
            if response.status_code == 204 or not response.content:
                return {}
            return response.json()

    def _build_rfc2822(
        self,
        to: str,
        subject: str,
        body: str,
        cc: Optional[list[str]] = None,
        bcc: Optional[list[str]] = None,
        reply_to: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> str:
        """Build an RFC 2822 email message and return base64url-encoded bytes.

        Args:
            to: Recipient email address.
            subject: Email subject line.
            body: Email body (HTML supported).
            cc: Optional CC recipients.
            bcc: Optional BCC recipients.
            reply_to: Optional reply-to address.
            thread_id: Optional thread ID for threading (unused in MIME).

        Returns:
            Base64url-encoded string of the RFC 2822 message.
        """
        msg = MIMEMultipart("alternative")
        msg["To"] = to
        msg["Subject"] = subject
        if cc:
            msg["Cc"] = ", ".join(cc)
        if bcc:
            msg["Bcc"] = ", ".join(bcc)
        if reply_to:
            msg["Reply-To"] = reply_to

        # Attach both plain text and HTML parts
        plain_text = body.replace("<br>", "\n").replace("<br/>", "\n")
        msg.attach(MIMEText(plain_text, "plain"))
        msg.attach(MIMEText(body, "html"))

        raw_bytes = msg.as_bytes()
        return base64.urlsafe_b64encode(raw_bytes).decode("ascii")

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

        Fetches message IDs matching the query, then batch-fetches full
        message details for each ID.

        Args:
            query: Gmail search query (same syntax as Gmail search bar).
            limit: Maximum number of emails to return per page.
            labels: Filter by label IDs (e.g., ["INBOX", "IMPORTANT"]).
            page_token: Token for fetching the next page of results.

        Returns:
            Paginated list of Email objects.
        """
        params: dict[str, Any] = {"q": query, "maxResults": limit}
        if labels:
            params["labelIds"] = labels
        if page_token:
            params["pageToken"] = page_token

        data = await self._request("GET", "/users/me/messages", params=params)

        messages_meta = data.get("messages", [])
        next_page_token = data.get("nextPageToken")

        # Fetch full message details for each returned ID
        emails: list[Email] = []
        for msg_meta in messages_meta:
            msg_id = msg_meta.get("id", "")
            msg_data = await self._request(
                "GET",
                f"/users/me/messages/{msg_id}",
                params={"format": "full"},
            )
            emails.append(_parse_message(msg_data))

        return PaginatedList(
            items=emails,
            page_state=PageState(
                cursor=next_page_token,
                has_more=next_page_token is not None,
            ),
            total_count=data.get("resultSizeEstimate"),
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
            The requested Email object with parsed headers and body.
        """
        data = await self._request(
            "GET",
            f"/users/me/messages/{email_id}",
            params={"format": format},
        )
        return _parse_message(data)

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

        Constructs an RFC 2822 message, base64url-encodes it, and sends
        it via the Gmail API.

        Args:
            to: Recipient email address.
            subject: Email subject line.
            body: Email body (supports HTML).
            cc: Optional CC recipients.
            bcc: Optional BCC recipients.
            reply_to: Optional reply-to address.

        Returns:
            MessageId with the sent message's ID and thread ID.
        """
        raw = self._build_rfc2822(
            to=to, subject=subject, body=body,
            cc=cc, bcc=bcc, reply_to=reply_to,
        )

        data = await self._request(
            "POST",
            "/users/me/messages/send",
            json={"raw": raw},
        )
        return MessageId(
            id=data.get("id", ""),
            thread_id=data.get("threadId"),
        )

    @action("Search emails with advanced query", requires_scope="read")
    async def search_emails(
        self,
        query: str,
        limit: int = 25,
        page_token: Optional[str] = None,
    ) -> PaginatedList[Email]:
        """Search emails using Gmail's advanced query syntax.

        This is functionally identical to list_emails but provided as a
        separate semantic action for clarity in agent tooling.

        Args:
            query: Gmail search query (e.g., "from:boss has:attachment after:2024/01/01").
            limit: Maximum results per page.
            page_token: Pagination token for next page.

        Returns:
            Paginated list of matching emails.
        """
        return await self.alist_emails(query=query, limit=limit, page_token=page_token)

    @action("List all labels", requires_scope="read")
    async def list_labels(self) -> list[Label]:
        """List all labels in the user's mailbox.

        Returns:
            List of Label objects including system and user-created labels.
        """
        data = await self._request("GET", "/users/me/labels")

        labels: list[Label] = []
        for lbl in data.get("labels", []):
            labels.append(
                Label(
                    id=lbl.get("id", ""),
                    name=lbl.get("name", ""),
                    type=lbl.get("type", "user"),
                    messages_total=lbl.get("messagesTotal", 0),
                    messages_unread=lbl.get("messagesUnread", 0),
                )
            )
        return labels

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
            DraftId with the created draft's ID and associated message ID.
        """
        raw = self._build_rfc2822(to=to, subject=subject, body=body, cc=cc)

        data = await self._request(
            "POST",
            "/users/me/drafts",
            json={"message": {"raw": raw}},
        )
        return DraftId(
            id=data.get("id", ""),
            message_id=data.get("message", {}).get("id"),
        )

    @action("Delete an email", requires_scope="full", dangerous=True)
    async def delete_email(self, email_id: str) -> None:
        """Permanently delete an email message.

        Args:
            email_id: The ID of the email to delete.

        Warning:
            This action permanently deletes the email. It cannot be undone.
        """
        await self._request("DELETE", f"/users/me/messages/{email_id}")

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
            The updated Email object with refreshed label list.
        """
        payload: dict[str, Any] = {}
        if add_labels:
            payload["addLabelIds"] = add_labels
        if remove_labels:
            payload["removeLabelIds"] = remove_labels

        data = await self._request(
            "POST",
            f"/users/me/messages/{email_id}/modify",
            json=payload,
        )
        return _parse_message(data)

    # ------------------------------------------------------------------
    # Actions — Threads
    # ------------------------------------------------------------------

    @action("List email threads", requires_scope="read")
    async def list_threads(
        self,
        query: Optional[str] = None,
        limit: int = 10,
        page_token: Optional[str] = None,
    ) -> PaginatedList[Thread]:
        """List conversation threads from the user's mailbox.

        Args:
            query: Gmail search query to filter threads (same syntax as
                the Gmail search bar). Omit to list all threads.
            limit: Maximum number of threads to return per page.
            page_token: Token for fetching the next page of results.

        Returns:
            Paginated list of Thread objects.
        """
        params: dict[str, Any] = {"maxResults": limit}
        if query:
            params["q"] = query
        if page_token:
            params["pageToken"] = page_token

        data = await self._request("GET", "/users/me/threads", params=params)

        threads_meta = data.get("threads", [])
        next_page_token = data.get("nextPageToken")

        threads: list[Thread] = []
        for meta in threads_meta:
            threads.append(
                Thread(
                    id=meta.get("id", ""),
                    snippet=meta.get("snippet", ""),
                    history_id=meta.get("historyId"),
                    messages_count=len(meta.get("messages", [])),
                )
            )

        return PaginatedList(
            items=threads,
            page_state=PageState(
                cursor=next_page_token,
                has_more=next_page_token is not None,
            ),
            total_count=data.get("resultSizeEstimate"),
        )

    @action("Get a single thread by ID", requires_scope="read")
    async def get_thread(
        self,
        thread_id: str,
        format: str = "metadata",
    ) -> Thread:
        """Retrieve a single conversation thread by its ID.

        Args:
            thread_id: The ID of the thread to retrieve.
            format: Response format: 'full', 'metadata', or 'minimal'.

        Returns:
            Thread object with message count populated.
        """
        data = await self._request(
            "GET",
            f"/users/me/threads/{thread_id}",
            params={"format": format},
        )
        return Thread(
            id=data.get("id", ""),
            snippet=data.get("snippet", ""),
            history_id=data.get("historyId"),
            messages_count=len(data.get("messages", [])),
        )

    # ------------------------------------------------------------------
    # Actions — Trash / Untrash
    # ------------------------------------------------------------------

    @action("Move an email to trash", requires_scope="full")
    async def trash_email(self, email_id: str) -> Email:
        """Move an email to the trash folder.

        The email can be recovered with ``untrash_email`` within 30 days.

        Args:
            email_id: The ID of the email to trash.

        Returns:
            The updated Email object with TRASH label applied.
        """
        data = await self._request(
            "POST",
            f"/users/me/messages/{email_id}/trash",
        )
        return _parse_message(data)

    @action("Remove an email from trash", requires_scope="full")
    async def untrash_email(self, email_id: str) -> Email:
        """Remove an email from the trash folder.

        Args:
            email_id: The ID of the email to untrash.

        Returns:
            The updated Email object with TRASH label removed.
        """
        data = await self._request(
            "POST",
            f"/users/me/messages/{email_id}/untrash",
        )
        return _parse_message(data)

    # ------------------------------------------------------------------
    # Actions — Read / Unread / Star / Unstar
    # ------------------------------------------------------------------

    @action("Mark an email as read", requires_scope="full")
    async def mark_as_read(self, email_id: str) -> Email:
        """Mark an email as read by removing the UNREAD label.

        Args:
            email_id: The ID of the email to mark as read.

        Returns:
            The updated Email object.
        """
        return await self.amodify_labels(
            email_id=email_id,
            remove_labels=["UNREAD"],
        )

    @action("Mark an email as unread", requires_scope="full")
    async def mark_as_unread(self, email_id: str) -> Email:
        """Mark an email as unread by adding the UNREAD label.

        Args:
            email_id: The ID of the email to mark as unread.

        Returns:
            The updated Email object.
        """
        return await self.amodify_labels(
            email_id=email_id,
            add_labels=["UNREAD"],
        )

    @action("Star an email", requires_scope="full")
    async def star_email(self, email_id: str) -> Email:
        """Star an email by adding the STARRED label.

        Args:
            email_id: The ID of the email to star.

        Returns:
            The updated Email object.
        """
        return await self.amodify_labels(
            email_id=email_id,
            add_labels=["STARRED"],
        )

    @action("Remove star from an email", requires_scope="full")
    async def unstar_email(self, email_id: str) -> Email:
        """Remove the star from an email by removing the STARRED label.

        Args:
            email_id: The ID of the email to unstar.

        Returns:
            The updated Email object.
        """
        return await self.amodify_labels(
            email_id=email_id,
            remove_labels=["STARRED"],
        )

    # ------------------------------------------------------------------
    # Actions — Labels (create / delete)
    # ------------------------------------------------------------------

    @action("Create a new label", requires_scope="full")
    async def create_label(
        self,
        name: str,
        label_color: Optional[LabelColor] = None,
    ) -> Label:
        """Create a new user label.

        Args:
            name: Display name for the label.
            label_color: Optional color specification with text_color and
                background_color hex values.

        Returns:
            The created Label object.
        """
        payload: dict[str, Any] = {
            "name": name,
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show",
        }
        if label_color:
            payload["color"] = {}
            if label_color.text_color:
                payload["color"]["textColor"] = label_color.text_color
            if label_color.background_color:
                payload["color"]["backgroundColor"] = label_color.background_color

        data = await self._request(
            "POST",
            "/users/me/labels",
            json=payload,
        )
        return Label(
            id=data.get("id", ""),
            name=data.get("name", ""),
            type=data.get("type", "user"),
            messages_total=data.get("messagesTotal", 0),
            messages_unread=data.get("messagesUnread", 0),
        )

    @action("Delete a label", requires_scope="full", dangerous=True)
    async def delete_label(self, label_id: str) -> None:
        """Permanently delete a user label.

        System labels (INBOX, SPAM, TRASH, etc.) cannot be deleted.

        Args:
            label_id: The ID of the label to delete.

        Warning:
            This action permanently removes the label. Emails are not
            deleted but will no longer have this label applied.
        """
        await self._request("DELETE", f"/users/me/labels/{label_id}")

    # ------------------------------------------------------------------
    # Actions — Attachments
    # ------------------------------------------------------------------

    @action("Download an email attachment", requires_scope="read")
    async def get_attachment(
        self,
        email_id: str,
        attachment_id: str,
    ) -> Attachment:
        """Download an attachment from an email.

        Args:
            email_id: The ID of the email containing the attachment.
            attachment_id: The ID of the attachment to download.

        Returns:
            Attachment object with base64-encoded data populated.
        """
        # First get message metadata to find the attachment part info
        msg_data = await self._request(
            "GET",
            f"/users/me/messages/{email_id}",
            params={"format": "full"},
        )

        # Find the attachment part for filename and mime_type
        filename = ""
        mime_type = ""
        size = 0
        payload = msg_data.get("payload", {})
        parts = payload.get("parts", [])
        for part in parts:
            body = part.get("body", {})
            if body.get("attachmentId") == attachment_id:
                filename = part.get("filename", "")
                mime_type = part.get("mimeType", "")
                size = body.get("size", 0)
                break

        # Fetch the actual attachment data
        att_data = await self._request(
            "GET",
            f"/users/me/messages/{email_id}/attachments/{attachment_id}",
        )

        return Attachment(
            id=attachment_id,
            filename=filename,
            mime_type=mime_type,
            size=att_data.get("size", size),
            data=att_data.get("data"),
        )

    # ------------------------------------------------------------------
    # Actions — Batch operations
    # ------------------------------------------------------------------

    @action("Batch modify labels on multiple emails", requires_scope="full")
    async def batch_modify(
        self,
        email_ids: list[str],
        add_labels: Optional[list[str]] = None,
        remove_labels: Optional[list[str]] = None,
    ) -> None:
        """Add or remove labels from multiple emails in a single request.

        Args:
            email_ids: List of message IDs to modify (max 1000).
            add_labels: Label IDs to add to all specified messages.
            remove_labels: Label IDs to remove from all specified messages.
        """
        payload: dict[str, Any] = {"ids": email_ids}
        if add_labels:
            payload["addLabelIds"] = add_labels
        if remove_labels:
            payload["removeLabelIds"] = remove_labels

        await self._request(
            "POST",
            "/users/me/messages/batchModify",
            json=payload,
        )
