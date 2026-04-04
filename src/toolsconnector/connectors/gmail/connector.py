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

from .types import DraftId, Email, EmailAddress, Label, MessageId


def _parse_email_address(raw: str) -> EmailAddress:
    """Parse a 'Display Name <email>' string into an EmailAddress.

    Args:
        raw: Raw address string from a Gmail header value.

    Returns:
        Parsed EmailAddress with name and email fields.
    """
    raw = raw.strip()
    if "<" in raw and raw.endswith(">"):
        name_part = raw[: raw.index("<")].strip().strip('"')
        email_part = raw[raw.index("<") + 1 : -1].strip()
        return EmailAddress(email=email_part, name=name_part or None)
    return EmailAddress(email=raw)


def _get_header(headers: list[dict[str, str]], name: str) -> str:
    """Extract a header value by name from the Gmail headers array.

    Args:
        headers: List of {"name": ..., "value": ...} dicts from the API.
        name: Case-insensitive header name to find.

    Returns:
        The header value, or empty string if not found.
    """
    lower_name = name.lower()
    for h in headers:
        if h.get("name", "").lower() == lower_name:
            return h.get("value", "")
    return ""


def _extract_body(payload: dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    """Recursively extract plain-text and HTML body from message payload.

    Args:
        payload: The Gmail API message payload dict.

    Returns:
        Tuple of (plain_text_body, html_body), either may be None.
    """
    text_body: Optional[str] = None
    html_body: Optional[str] = None

    mime_type = payload.get("mimeType", "")

    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            text_body = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    elif mime_type == "text/html":
        data = payload.get("body", {}).get("data", "")
        if data:
            html_body = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    elif mime_type.startswith("multipart/"):
        for part in payload.get("parts", []):
            t, h = _extract_body(part)
            if t and not text_body:
                text_body = t
            if h and not html_body:
                html_body = h

    return text_body, html_body


def _has_attachments(payload: dict[str, Any]) -> bool:
    """Check whether the message payload contains file attachments.

    Args:
        payload: The Gmail API message payload dict.

    Returns:
        True if at least one part has a non-empty filename.
    """
    for part in payload.get("parts", []):
        if part.get("filename"):
            return True
        if part.get("parts"):
            if _has_attachments(part):
                return True
    return False


def _parse_message(data: dict[str, Any]) -> Email:
    """Parse a Gmail API message response into an Email model.

    Args:
        data: Raw JSON response from GET /users/me/messages/{id}.

    Returns:
        Populated Email instance.
    """
    payload = data.get("payload", {})
    headers = payload.get("headers", [])

    subject = _get_header(headers, "Subject")
    from_raw = _get_header(headers, "From")
    to_raw = _get_header(headers, "To")
    cc_raw = _get_header(headers, "Cc")
    date_str = _get_header(headers, "Date")

    from_addr = _parse_email_address(from_raw) if from_raw else None
    to_addrs = [_parse_email_address(a) for a in to_raw.split(",") if a.strip()] if to_raw else []
    cc_addrs = [_parse_email_address(a) for a in cc_raw.split(",") if a.strip()] if cc_raw else []

    text_body, html_body = _extract_body(payload)

    return Email(
        id=data.get("id", ""),
        thread_id=data.get("threadId", ""),
        subject=subject,
        from_address=from_addr,
        to=to_addrs,
        cc=cc_addrs,
        date=date_str,
        snippet=data.get("snippet", ""),
        body_text=text_body,
        body_html=html_body,
        labels=data.get("labelIds", []),
        has_attachments=_has_attachments(payload),
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
