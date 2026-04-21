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

from ._helpers import (
    parse_draft as _parse_draft,
)
from ._helpers import (
    parse_history_record as _parse_history_record,
)
from ._helpers import (
    parse_label as _parse_label,
)
from ._helpers import (
    parse_message as _parse_message,
)
from ._helpers import (
    parse_thread as _parse_thread,
)
from ._helpers import (
    parse_vacation_settings as _parse_vacation_settings,
)
from .types import (
    Attachment,
    Draft,
    DraftId,
    Email,
    HistoryRecord,
    Label,
    LabelColor,
    MessageId,
    Thread,
    UserProfile,
    VacationSettings,
)


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
            to=to,
            subject=subject,
            body=body,
            cc=cc,
            bcc=bcc,
            reply_to=reply_to,
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
        return [_parse_label(lbl) for lbl in data.get("labels", [])]

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

        return PaginatedList(
            items=[_parse_thread(meta) for meta in threads_meta],
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
        return _parse_thread(data)

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
        return _parse_label(data)

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

    # ------------------------------------------------------------------
    # Actions — Drafts (full lifecycle)
    # ------------------------------------------------------------------

    @action("List drafts", requires_scope="read")
    async def list_drafts(
        self,
        limit: int = 10,
        page_token: Optional[str] = None,
    ) -> PaginatedList[Draft]:
        """List drafts in the user's mailbox.

        Args:
            limit: Maximum number of drafts to return per page.
            page_token: Token for fetching the next page of results.

        Returns:
            Paginated list of Draft objects.
        """
        params: dict[str, Any] = {"maxResults": limit}
        if page_token:
            params["pageToken"] = page_token

        data = await self._request("GET", "/users/me/drafts", params=params)

        drafts_meta = data.get("drafts", [])
        next_page_token = data.get("nextPageToken")

        return PaginatedList(
            items=[_parse_draft(meta) for meta in drafts_meta],
            page_state=PageState(
                cursor=next_page_token,
                has_more=next_page_token is not None,
            ),
            total_count=data.get("resultSizeEstimate"),
        )

    @action("Get a single draft by ID", requires_scope="read")
    async def get_draft(
        self,
        draft_id: str,
        format: str = "full",
    ) -> Draft:
        """Retrieve a single draft by its ID.

        Args:
            draft_id: The ID of the draft to retrieve.
            format: Response format: 'full', 'metadata', or 'minimal'.

        Returns:
            Draft object with its associated message.
        """
        data = await self._request(
            "GET",
            f"/users/me/drafts/{draft_id}",
            params={"format": format},
        )
        return _parse_draft(data)

    @action("Update a draft", requires_scope="send")
    async def update_draft(
        self,
        draft_id: str,
        to: str,
        subject: str,
        body: str,
        cc: Optional[list[str]] = None,
    ) -> Draft:
        """Replace the content of an existing draft.

        The entire message is replaced; partial updates are not supported
        by the Gmail API.

        Args:
            draft_id: The ID of the draft to update.
            to: Recipient email address.
            subject: Email subject line.
            body: Email body (supports HTML).
            cc: Optional CC recipients.

        Returns:
            Updated Draft object.
        """
        raw = self._build_rfc2822(to=to, subject=subject, body=body, cc=cc)

        data = await self._request(
            "PUT",
            f"/users/me/drafts/{draft_id}",
            json={"message": {"raw": raw}},
        )
        return _parse_draft(data)

    @action("Delete a draft", requires_scope="send", dangerous=True)
    async def delete_draft(self, draft_id: str) -> None:
        """Permanently delete a draft.

        Args:
            draft_id: The ID of the draft to delete.

        Warning:
            This action permanently deletes the draft. It cannot be undone.
        """
        await self._request("DELETE", f"/users/me/drafts/{draft_id}")

    @action("Send a draft", requires_scope="send", dangerous=True)
    async def send_draft(self, draft_id: str) -> MessageId:
        """Send an existing draft.

        The draft is removed from the drafts list after sending.

        Args:
            draft_id: The ID of the draft to send.

        Returns:
            MessageId with the sent message's ID and thread ID.
        """
        data = await self._request(
            "POST",
            "/users/me/drafts/send",
            json={"id": draft_id},
        )
        return MessageId(
            id=data.get("id", ""),
            thread_id=data.get("threadId"),
        )

    # ------------------------------------------------------------------
    # Actions — Threads (complete)
    # ------------------------------------------------------------------

    @action("Modify thread labels", requires_scope="full")
    async def modify_thread(
        self,
        thread_id: str,
        add_labels: Optional[list[str]] = None,
        remove_labels: Optional[list[str]] = None,
    ) -> Thread:
        """Add or remove labels from all messages in a thread.

        Args:
            thread_id: The ID of the thread to modify.
            add_labels: Label IDs to add (e.g., ["STARRED", "IMPORTANT"]).
            remove_labels: Label IDs to remove (e.g., ["UNREAD"]).

        Returns:
            Updated Thread object.
        """
        payload: dict[str, Any] = {}
        if add_labels:
            payload["addLabelIds"] = add_labels
        if remove_labels:
            payload["removeLabelIds"] = remove_labels

        data = await self._request(
            "POST",
            f"/users/me/threads/{thread_id}/modify",
            json=payload,
        )
        return _parse_thread(data)

    @action("Move a thread to trash", requires_scope="full")
    async def trash_thread(self, thread_id: str) -> Thread:
        """Move all messages in a thread to the trash folder.

        The thread can be recovered with ``untrash_thread`` within 30 days.

        Args:
            thread_id: The ID of the thread to trash.

        Returns:
            Updated Thread object with TRASH label applied.
        """
        data = await self._request(
            "POST",
            f"/users/me/threads/{thread_id}/trash",
        )
        return _parse_thread(data)

    @action("Remove a thread from trash", requires_scope="full")
    async def untrash_thread(self, thread_id: str) -> Thread:
        """Remove all messages in a thread from the trash folder.

        Args:
            thread_id: The ID of the thread to untrash.

        Returns:
            Updated Thread object with TRASH label removed.
        """
        data = await self._request(
            "POST",
            f"/users/me/threads/{thread_id}/untrash",
        )
        return _parse_thread(data)

    @action("Permanently delete a thread", requires_scope="full", dangerous=True)
    async def delete_thread(self, thread_id: str) -> None:
        """Permanently delete a thread and all its messages.

        Args:
            thread_id: The ID of the thread to delete.

        Warning:
            This action permanently deletes the thread. It cannot be undone.
        """
        await self._request("DELETE", f"/users/me/threads/{thread_id}")

    # ------------------------------------------------------------------
    # Actions — Labels (complete)
    # ------------------------------------------------------------------

    @action("Get a single label by ID", requires_scope="read")
    async def get_label(self, label_id: str) -> Label:
        """Retrieve a single label by its ID.

        Args:
            label_id: The ID of the label to retrieve.

        Returns:
            The requested Label object with message counts.
        """
        data = await self._request("GET", f"/users/me/labels/{label_id}")
        return _parse_label(data)

    @action("Update a label", requires_scope="full")
    async def update_label(
        self,
        label_id: str,
        name: Optional[str] = None,
        label_color: Optional[LabelColor] = None,
    ) -> Label:
        """Update a user label's name or color.

        System labels (INBOX, SPAM, TRASH, etc.) cannot be updated.

        Args:
            label_id: The ID of the label to update.
            name: New display name for the label.
            label_color: Optional new color specification with text_color
                and background_color hex values.

        Returns:
            The updated Label object.
        """
        # Fetch current label to merge with updates
        current = await self._request("GET", f"/users/me/labels/{label_id}")

        payload: dict[str, Any] = {
            "name": name if name is not None else current.get("name", ""),
        }
        if label_color:
            color: dict[str, str] = {}
            if label_color.text_color:
                color["textColor"] = label_color.text_color
            if label_color.background_color:
                color["backgroundColor"] = label_color.background_color
            payload["color"] = color
        elif "color" in current:
            payload["color"] = current["color"]

        data = await self._request(
            "PUT",
            f"/users/me/labels/{label_id}",
            json=payload,
        )
        return _parse_label(data)

    # ------------------------------------------------------------------
    # Actions — User profile
    # ------------------------------------------------------------------

    @action("Get user profile", requires_scope="read")
    async def get_profile(self) -> UserProfile:
        """Retrieve the authenticated user's Gmail profile.

        Returns:
            UserProfile with email address, message and thread totals,
            and the current history ID for incremental sync.
        """
        data = await self._request("GET", "/users/me/profile")
        return UserProfile(
            email_address=data.get("emailAddress", ""),
            messages_total=data.get("messagesTotal", 0),
            threads_total=data.get("threadsTotal", 0),
            history_id=data.get("historyId", ""),
        )

    # ------------------------------------------------------------------
    # Actions — History (incremental sync)
    # ------------------------------------------------------------------

    @action("List mailbox history", requires_scope="read")
    async def list_history(
        self,
        start_history_id: str,
        label_id: Optional[str] = None,
        history_types: Optional[list[str]] = None,
        limit: int = 100,
        page_token: Optional[str] = None,
    ) -> PaginatedList[HistoryRecord]:
        """List history records for incremental mailbox sync.

        Returns changes that occurred after the given history ID. Use
        ``get_profile()`` to obtain the current history ID, then poll
        this endpoint to detect new messages, deletions, and label
        changes without re-fetching the entire mailbox.

        Args:
            start_history_id: History ID to start listing from. Only
                changes after this ID are returned.
            label_id: Only return history for this label ID.
            history_types: Filter by change type. Valid values:
                ``messageAdded``, ``messageDeleted``,
                ``labelAdded``, ``labelRemoved``.
            limit: Maximum number of history records per page.
            page_token: Token for fetching the next page of results.

        Returns:
            Paginated list of HistoryRecord objects.
        """
        params: dict[str, Any] = {
            "startHistoryId": start_history_id,
            "maxResults": limit,
        }
        if label_id:
            params["labelId"] = label_id
        if history_types:
            params["historyTypes"] = history_types
        if page_token:
            params["pageToken"] = page_token

        data = await self._request("GET", "/users/me/history", params=params)

        raw_history = data.get("history", [])
        next_page_token = data.get("nextPageToken")

        return PaginatedList(
            items=[_parse_history_record(entry) for entry in raw_history],
            page_state=PageState(
                cursor=next_page_token,
                has_more=next_page_token is not None,
            ),
        )

    # ------------------------------------------------------------------
    # Actions — Settings (vacation auto-reply)
    # ------------------------------------------------------------------

    @action("Get vacation auto-reply settings", requires_scope="read")
    async def get_vacation_settings(self) -> VacationSettings:
        """Retrieve the user's vacation auto-reply settings.

        Returns:
            VacationSettings with current auto-reply configuration.
        """
        data = await self._request("GET", "/users/me/settings/vacation")
        return _parse_vacation_settings(data)

    @action("Update vacation auto-reply settings", requires_scope="full", dangerous=True)
    async def update_vacation_settings(
        self,
        enable: bool,
        response_subject: Optional[str] = None,
        response_body: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> VacationSettings:
        """Update the user's vacation auto-reply settings.

        Args:
            enable: Whether to enable the vacation auto-reply.
            response_subject: Subject line for the auto-reply message.
            response_body: Body of the auto-reply (supports HTML).
            start_time: Start time as epoch milliseconds string.
                Required when enabling auto-reply.
            end_time: End time as epoch milliseconds string.
                Required when enabling auto-reply.

        Returns:
            Updated VacationSettings.

        Warning:
            Enabling auto-reply will send automatic responses to
            incoming emails. Use with caution.
        """
        payload: dict[str, Any] = {"enableAutoReply": enable}
        if response_subject is not None:
            payload["responseSubject"] = response_subject
        if response_body is not None:
            payload["responseBodyPlainText"] = response_body
            payload["responseBodyHtml"] = response_body
        if start_time is not None:
            payload["startTime"] = int(start_time)
        if end_time is not None:
            payload["endTime"] = int(end_time)

        data = await self._request(
            "PUT",
            "/users/me/settings/vacation",
            json=payload,
        )
        return _parse_vacation_settings(data)

    # ------------------------------------------------------------------
    # Actions — Message import
    # ------------------------------------------------------------------

    @action("Import an email message into the mailbox", dangerous=True)
    async def import_message(
        self,
        raw_rfc2822: str,
        label_ids: Optional[list[str]] = None,
        internal_date_source: str = "dateHeader",
    ) -> MessageId:
        """Import a raw RFC 2822 email into the user's mailbox.

        Useful for email migrations, backups, and bulk import. The message
        is inserted as if it was received at the time indicated by its
        Date header (or receivedTime if specified).

        Args:
            raw_rfc2822: The complete RFC 2822 formatted email as a string.
            label_ids: Labels to apply (e.g., ["INBOX", "UNREAD"]).
            internal_date_source: How to determine the internal date.
                "dateHeader" uses the Date header, "receivedTime" uses
                the import time.

        Returns:
            MessageId of the imported message.
        """
        import base64

        encoded = base64.urlsafe_b64encode(raw_rfc2822.encode("utf-8")).decode("ascii")

        payload: dict[str, Any] = {"raw": encoded}
        if label_ids:
            payload["labelIds"] = label_ids

        params = {"internalDateSource": internal_date_source}
        data = await self._request(
            "POST",
            "/users/me/messages/import",
            json=payload,
            params=params,
        )
        return MessageId(
            id=data.get("id", ""),
            thread_id=data.get("threadId"),
        )

    @action("Insert an email message directly into the mailbox", dangerous=True)
    async def insert_message(
        self,
        raw_rfc2822: str,
        label_ids: Optional[list[str]] = None,
        internal_date_source: str = "receivedTime",
    ) -> MessageId:
        """Insert a raw RFC 2822 email directly into the mailbox.

        Unlike import, insert does not trigger spam checks or forwarding
        rules. Used for programmatic message creation with full control
        over headers and timestamps.

        Args:
            raw_rfc2822: The complete RFC 2822 formatted email as a string.
            label_ids: Labels to apply.
            internal_date_source: "receivedTime" (default) or "dateHeader".

        Returns:
            MessageId of the inserted message.
        """
        import base64

        encoded = base64.urlsafe_b64encode(raw_rfc2822.encode("utf-8")).decode("ascii")

        payload: dict[str, Any] = {"raw": encoded}
        if label_ids:
            payload["labelIds"] = label_ids

        params = {"internalDateSource": internal_date_source}
        data = await self._request(
            "POST",
            "/users/me/messages/insert",
            json=payload,
            params=params,
        )
        return MessageId(
            id=data.get("id", ""),
            thread_id=data.get("threadId"),
        )

    @action("Batch delete messages permanently", dangerous=True)
    async def batch_delete(
        self,
        email_ids: list[str],
    ) -> None:
        """Permanently delete multiple messages in a single request.

        This action is irreversible. Use trash_email for recoverable
        deletion. Maximum 1000 message IDs per request.

        Args:
            email_ids: List of message IDs to delete (max 1000).
        """
        await self._request(
            "POST",
            "/users/me/messages/batchDelete",
            json={"ids": email_ids[:1000]},
        )
