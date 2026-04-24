"""Gmail connector -- read, send, and manage emails via the Gmail REST API v1.

Uses httpx for direct HTTP calls against the Gmail REST API.
Expects an OAuth 2.0 access token passed as ``credentials``.
"""

from __future__ import annotations

import base64
import logging
import mimetypes
import re
from email.encoders import encode_base64
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Optional, Union

import httpx

from toolsconnector.connectors._helpers import raise_typed_for_status
from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import ConnectorCategory, ProtocolType, RateLimitSpec
from toolsconnector.types import PageState, PaginatedList

from ._helpers import (
    build_filter_action_payload as _build_filter_action_payload,
)
from ._helpers import (
    build_filter_criteria_payload as _build_filter_criteria_payload,
)
from ._helpers import (
    html_to_text as _html_to_text,
)
from ._helpers import (
    parse_auto_forwarding as _parse_auto_forwarding,
)
from ._helpers import (
    parse_delegate as _parse_delegate,
)
from ._helpers import (
    parse_draft as _parse_draft,
)
from ._helpers import (
    parse_filter as _parse_filter,
)
from ._helpers import (
    parse_forwarding_address as _parse_forwarding_address,
)
from ._helpers import (
    parse_history_record as _parse_history_record,
)
from ._helpers import (
    parse_imap_settings as _parse_imap_settings,
)
from ._helpers import (
    parse_label as _parse_label,
)
from ._helpers import (
    parse_language_settings as _parse_language_settings,
)
from ._helpers import (
    parse_message as _parse_message,
)
from ._helpers import (
    parse_pop_settings as _parse_pop_settings,
)
from ._helpers import (
    parse_send_as as _parse_send_as,
)
from ._helpers import (
    parse_thread as _parse_thread,
)
from ._helpers import (
    parse_vacation_settings as _parse_vacation_settings,
)
from .types import (
    Attachment,
    AutoForwarding,
    Delegate,
    Draft,
    DraftId,
    Email,
    Filter,
    FilterAction,
    FilterCriteria,
    ForwardingAddress,
    HistoryRecord,
    ImapSettings,
    Label,
    LabelColor,
    LanguageSettings,
    MessageId,
    PopSettings,
    SendAs,
    Thread,
    UserProfile,
    VacationSettings,
)

logger = logging.getLogger("toolsconnector.gmail")

# Matches any HTML-like tag. Used to detect HTML content in the `body`
# parameter for backward-compat auto-routing (pre-0.3.5 callers passed
# HTML directly in `body` without setting `html_body`).
_HTML_TAG_RE = re.compile(r"<[a-zA-Z][^>]*>")


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
            toolsconnector.errors.APIError (subclass): On any non-2xx response.
                Maps to a typed exception by status: 401 -> InvalidCredentialsError
                or TokenExpiredError; 403 -> PermissionDeniedError; 404 -> NotFoundError;
                409 -> ConflictError; 400/422 -> ValidationError; 429 -> RateLimitError;
                5xx -> ServerError; other 4xx -> APIError. See
                toolsconnector.connectors._helpers.raise_typed_for_status for the full mapping.

        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.request(
                method,
                f"{self._base_url}{path}",
                headers=self._get_headers(),
                **kwargs,
            )
            raise_typed_for_status(response, connector=self.name)
            if response.status_code == 204 or not response.content:
                return {}
            return response.json()

    def _build_rfc2822(
        self,
        to: str,
        subject: str,
        text_body: Optional[str] = None,
        html_body: Optional[str] = None,
        cc: Optional[list[str]] = None,
        bcc: Optional[list[str]] = None,
        reply_to: Optional[str] = None,
        attachments: Optional[list[dict[str, Any]]] = None,
        headers: Optional[dict[str, str]] = None,
        thread_id: Optional[str] = None,  # noqa: ARG002 — kept for API compat
    ) -> str:
        """Build an RFC 2822 email message and return base64url-encoded bytes.

        Supports four content shapes, chosen automatically from inputs:

        1. **Plain only** (``text_body`` set, ``html_body=None``, no
           attachments): simple ``text/plain`` message.
        2. **HTML only** (``html_body`` set, ``text_body=None``, no
           attachments): ``multipart/alternative`` with the HTML as the
           primary part and an auto-derived plain-text fallback (via
           ``_html_to_text``).
        3. **Both** (``text_body`` AND ``html_body`` set): ``multipart/
           alternative`` with both parts verbatim. Use this when you want
           to control the plain-text fallback yourself.
        4. **With attachments**: whatever body shape is chosen above is
           wrapped in a ``multipart/mixed`` with each attachment added as
           a separate part.

        Args:
            to: Recipient email address.
            subject: Email subject line.
            text_body: Plain-text body. Required if ``html_body`` is None.
            html_body: HTML body. Required if ``text_body`` is None.
            cc: Optional CC recipients.
            bcc: Optional BCC recipients.
            reply_to: Optional Reply-To address.
            attachments: Optional list of dicts, each with ``filename``
                (str), ``content`` (base64-encoded str), and optional
                ``content_type`` (MIME type — inferred from filename if
                omitted).
            headers: Optional dict of custom headers (e.g.
                ``{"In-Reply-To": "<msg-id>", "List-Unsubscribe": "<mailto:…>"}``).
            thread_id: Reserved for future use (threading happens via the
                Gmail ``threadId`` field on send, not via MIME).

        Returns:
            Base64url-encoded string of the RFC 2822 message, ready to
            pass to Gmail's ``/messages/send`` endpoint.

        Raises:
            ValueError: If neither ``text_body`` nor ``html_body`` is set,
                or if an attachment's ``content`` is not valid base64.
        """
        if text_body is None and html_body is None:
            raise ValueError("_build_rfc2822 requires at least one of `text_body` or `html_body`.")

        # ── 1. Build the core body part (plain, html, or alternative) ─
        body_part: Union[MIMEText, MIMEMultipart]
        if html_body is not None and text_body is not None:
            body_part = MIMEMultipart("alternative")
            body_part.attach(MIMEText(text_body, "plain", _charset="utf-8"))
            body_part.attach(MIMEText(html_body, "html", _charset="utf-8"))
        elif html_body is not None:
            # HTML-only → still emit as multipart/alternative with an
            # auto-derived text fallback. Mail clients without HTML support
            # (rare but not zero) need it; spam filters penalize single-part
            # HTML messages.
            body_part = MIMEMultipart("alternative")
            body_part.attach(MIMEText(_html_to_text(html_body), "plain", _charset="utf-8"))
            body_part.attach(MIMEText(html_body, "html", _charset="utf-8"))
        else:
            # text_body only (text_body is not None here per the guard above)
            assert text_body is not None  # noqa: S101 — narrowing for mypy
            body_part = MIMEText(text_body, "plain", _charset="utf-8")

        # ── 2. Wrap in multipart/mixed if there are attachments ───────
        msg: Union[MIMEText, MIMEMultipart]
        if attachments:
            mixed = MIMEMultipart("mixed")
            mixed.attach(body_part)
            for idx, att in enumerate(attachments):
                mixed.attach(self._build_attachment_part(att, idx))
            msg = mixed
        else:
            msg = body_part

        # ── 3. Top-level headers ──────────────────────────────────────
        msg["To"] = to
        msg["Subject"] = subject
        if cc:
            msg["Cc"] = ", ".join(cc)
        if bcc:
            msg["Bcc"] = ", ".join(bcc)
        if reply_to:
            msg["Reply-To"] = reply_to

        # ── 4. Custom headers (late so they can override defaults) ────
        if headers:
            for name, value in headers.items():
                if name in msg:
                    msg.replace_header(name, value)
                else:
                    msg[name] = value

        raw_bytes = msg.as_bytes()
        return base64.urlsafe_b64encode(raw_bytes).decode("ascii")

    @staticmethod
    def _build_attachment_part(att: dict[str, Any], idx: int) -> MIMEBase:
        """Build a MIMEBase part from an attachment dict.

        Args:
            att: Dict with ``filename`` (str), ``content`` (base64 str),
                and optional ``content_type`` (MIME type).
            idx: Zero-based index — used only for error messages when
                validation fails.

        Returns:
            A MIMEBase part with base64 Content-Transfer-Encoding and a
            proper Content-Disposition: attachment header.

        Raises:
            ValueError: If ``filename`` is missing, ``content`` is not a
                string, or ``content`` is not valid base64.
        """
        filename = att.get("filename")
        if not filename or not isinstance(filename, str):
            raise ValueError(f"Attachment {idx} is missing a `filename` (str). Got: {att!r}")

        content = att.get("content")
        if not isinstance(content, str):
            raise ValueError(
                f"Attachment '{filename}' requires `content` to be a "
                f"base64-encoded string. Got type: {type(content).__name__}."
            )

        content_type = att.get("content_type") or (
            mimetypes.guess_type(filename)[0] or "application/octet-stream"
        )
        if "/" not in content_type:
            raise ValueError(
                f"Attachment '{filename}' has invalid content_type "
                f"{content_type!r}. Expected '<maintype>/<subtype>'."
            )
        maintype, subtype = content_type.split("/", 1)

        try:
            payload_bytes = base64.b64decode(content, validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Attachment '{filename}' content is not valid base64: {exc}") from exc

        part = MIMEBase(maintype, subtype)
        part.set_payload(payload_bytes)
        # Gmail requires base64 Content-Transfer-Encoding for binary parts.
        encode_base64(part)
        part.add_header(
            "Content-Disposition",
            "attachment",
            filename=filename,
        )
        return part

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
        html_body: Optional[str] = None,
        attachments: Optional[list[dict[str, Any]]] = None,
        cc: Optional[list[str]] = None,
        bcc: Optional[list[str]] = None,
        reply_to: Optional[str] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> MessageId:
        """Send an email message.

        Constructs an RFC 2822 message, base64url-encodes it, and sends
        it via the Gmail API.

        Four common usage shapes:

        **Plain-text email**

        .. code-block:: python

            send_email(to="x@y.com", subject="Hi", body="Hello from plain text")

        **HTML email with auto-generated plain-text fallback**

        .. code-block:: python

            send_email(
                to="x@y.com",
                subject="Styled",
                body="Plain text version",
                html_body="<h1>Hello</h1><p>With <b>inline styles</b>.</p>",
            )

        **HTML-only** (``body`` becomes the caller-supplied text fallback)

        Leave ``body`` as a brief plain summary and put the rich content in
        ``html_body``. Clients without HTML support show ``body`` instead.

        **With attachments**

        .. code-block:: python

            import base64
            with open("report.pdf", "rb") as f:
                pdf_b64 = base64.b64encode(f.read()).decode("ascii")
            send_email(
                to="x@y.com",
                subject="Report",
                body="See attached report.",
                attachments=[{
                    "filename": "report.pdf",
                    "content": pdf_b64,
                    # content_type inferred from filename if omitted
                }],
            )

        Args:
            to: Recipient email address.
            subject: Email subject line.
            body: Plain-text body. If only HTML content is passed here
                (for backward compatibility with earlier releases), it
                is auto-routed to ``html_body`` and a text fallback is
                derived. Prefer explicit ``html_body`` in new code.
            html_body: Optional HTML body. When set, the message becomes
                ``multipart/alternative`` with ``body`` as the plain-text
                part and ``html_body`` as the HTML part.
            attachments: Optional list of attachment dicts. Each dict
                must have ``filename`` (str) and ``content`` (base64-
                encoded str); ``content_type`` is optional and inferred
                from the filename extension when not provided.
            cc: Optional CC recipients.
            bcc: Optional BCC recipients.
            reply_to: Optional Reply-To address.
            headers: Optional dict of custom headers. Useful for
                ``In-Reply-To`` / ``References`` (proper threading),
                ``List-Unsubscribe`` (bulk-mail compliance), and custom
                ``Message-ID``.

        Returns:
            MessageId with the sent message's ID and thread ID.

        Raises:
            ValueError: If an attachment's ``content`` is not valid base64.
        """
        # ── Backward-compat auto-routing ──────────────────────────────
        # Pre-0.3.5 callers passed HTML directly in `body`. Detect that
        # and route it to html_body so the new multipart logic kicks in,
        # and emit a one-time deprecation log message.
        effective_text = body
        effective_html = html_body
        if html_body is None and _HTML_TAG_RE.search(body):
            logger.debug(
                "gmail.send_email received HTML content in `body` with no "
                "`html_body` set. Auto-routing to html_body for backward "
                "compatibility. Prefer passing HTML to `html_body` explicitly."
            )
            effective_html = body
            effective_text = _html_to_text(body)

        raw = self._build_rfc2822(
            to=to,
            subject=subject,
            text_body=effective_text,
            html_body=effective_html,
            cc=cc,
            bcc=bcc,
            reply_to=reply_to,
            attachments=attachments,
            headers=headers,
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
        html_body: Optional[str] = None,
        attachments: Optional[list[dict[str, Any]]] = None,
        cc: Optional[list[str]] = None,
        bcc: Optional[list[str]] = None,
        reply_to: Optional[str] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> DraftId:
        """Create a draft email message.

        Accepts the same full content shape as :meth:`send_email` —
        plain text, multipart HTML+text, attachments, and custom headers.
        See :meth:`send_email` for usage examples.

        Args:
            to: Recipient email address.
            subject: Email subject line.
            body: Plain-text body (or HTML for backward compatibility —
                see :meth:`send_email` for the auto-routing behavior).
            html_body: Optional HTML body (triggers multipart/alternative).
            attachments: Optional list of attachment dicts (see
                :meth:`send_email` for the dict shape).
            cc: Optional CC recipients.
            bcc: Optional BCC recipients.
            reply_to: Optional Reply-To address.
            headers: Optional dict of custom headers.

        Returns:
            DraftId with the created draft's ID and associated message ID.
        """
        effective_text = body
        effective_html = html_body
        if html_body is None and _HTML_TAG_RE.search(body):
            logger.debug(
                "gmail.create_draft received HTML content in `body` with no "
                "`html_body` set. Auto-routing for backward compatibility."
            )
            effective_html = body
            effective_text = _html_to_text(body)

        raw = self._build_rfc2822(
            to=to,
            subject=subject,
            text_body=effective_text,
            html_body=effective_html,
            cc=cc,
            bcc=bcc,
            reply_to=reply_to,
            attachments=attachments,
            headers=headers,
        )

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
        html_body: Optional[str] = None,
        attachments: Optional[list[dict[str, Any]]] = None,
        cc: Optional[list[str]] = None,
        bcc: Optional[list[str]] = None,
        reply_to: Optional[str] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> Draft:
        """Replace the content of an existing draft.

        The entire message is replaced; partial updates are not supported
        by the Gmail API. Accepts the same full content shape as
        :meth:`send_email` — plain text, multipart HTML+text, attachments,
        and custom headers.

        Args:
            draft_id: The ID of the draft to update.
            to: Recipient email address.
            subject: Email subject line.
            body: Plain-text body (or HTML for backward compatibility).
            html_body: Optional HTML body (triggers multipart/alternative).
            attachments: Optional list of attachment dicts.
            cc: Optional CC recipients.
            bcc: Optional BCC recipients.
            reply_to: Optional Reply-To address.
            headers: Optional dict of custom headers.

        Returns:
            Updated Draft object.
        """
        effective_text = body
        effective_html = html_body
        if html_body is None and _HTML_TAG_RE.search(body):
            effective_html = body
            effective_text = _html_to_text(body)

        raw = self._build_rfc2822(
            to=to,
            subject=subject,
            text_body=effective_text,
            html_body=effective_html,
            cc=cc,
            bcc=bcc,
            reply_to=reply_to,
            attachments=attachments,
            headers=headers,
        )

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

    # ==================================================================
    # Settings — Filters (auto-categorization rules)
    # ==================================================================
    # Docs: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.settings.filters
    # All filter actions require the gmail.settings.basic scope.

    @action("List all filters", requires_scope="settings")
    async def list_filters(self) -> list[Filter]:
        """List every filter (auto-categorization rule) on the mailbox.

        Filters run server-side on incoming mail and can label, archive,
        delete, or forward messages that match their criteria.

        Returns:
            All filters on the account. Empty list if none configured.
        """
        data = await self._request("GET", "/users/me/settings/filters")
        return [_parse_filter(f) for f in data.get("filter", [])]

    @action("Get a single filter by ID", requires_scope="settings")
    async def get_filter(self, filter_id: str) -> Filter:
        """Retrieve a single filter by its ID.

        Args:
            filter_id: The filter's server-assigned ID.

        Returns:
            The Filter object.
        """
        data = await self._request("GET", f"/users/me/settings/filters/{filter_id}")
        return _parse_filter(data)

    @action("Create a new filter", requires_scope="settings", dangerous=True)
    async def create_filter(
        self,
        criteria: FilterCriteria,
        action: FilterAction,
    ) -> Filter:
        """Create a new filter that runs on every incoming message.

        This is powerful — a filter can auto-archive, auto-delete, or
        auto-forward. Marked dangerous so agents with
        ``exclude_dangerous=True`` don't create rules silently.

        Args:
            criteria: Match conditions (from, to, subject, query, size, etc.).
                All specified fields must match for the filter to trigger.
            action: Actions to apply to matching messages (add/remove labels,
                forward to a verified forwarding address).

        Returns:
            The created Filter object with its server-assigned ID.

        Raises:
            ValidationError: if criteria/action are empty or invalid (HTTP 400/422).
            PermissionDeniedError: if missing the gmail.settings.basic scope (HTTP 403).
        """
        payload = {
            "criteria": _build_filter_criteria_payload(criteria),
            "action": _build_filter_action_payload(action),
        }
        data = await self._request("POST", "/users/me/settings/filters", json=payload)
        return _parse_filter(data)

    @action("Delete a filter", requires_scope="settings", dangerous=True)
    async def delete_filter(self, filter_id: str) -> None:
        """Permanently delete a filter.

        Args:
            filter_id: ID of the filter to delete.
        """
        await self._request("DELETE", f"/users/me/settings/filters/{filter_id}")

    # ==================================================================
    # Settings — Send-As aliases (multi-identity sending)
    # ==================================================================
    # Docs: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.settings.sendAs

    @action("List send-as aliases", requires_scope="settings")
    async def list_send_as(self) -> list[SendAs]:
        """List every address the user can send email from.

        Includes the primary account plus any verified aliases.

        Returns:
            All send-as entries for the account.
        """
        data = await self._request("GET", "/users/me/settings/sendAs")
        return [_parse_send_as(s) for s in data.get("sendAs", [])]

    @action("Get a single send-as alias", requires_scope="settings")
    async def get_send_as(self, send_as_email: str) -> SendAs:
        """Retrieve a single send-as alias by email.

        Args:
            send_as_email: The alias address (primary key in this resource).

        Returns:
            The SendAs object.
        """
        data = await self._request("GET", f"/users/me/settings/sendAs/{send_as_email}")
        return _parse_send_as(data)

    @action("Create a send-as alias", requires_scope="settings", dangerous=True)
    async def create_send_as(
        self,
        send_as_email: str,
        display_name: Optional[str] = None,
        reply_to_address: Optional[str] = None,
        signature: Optional[str] = None,
        treat_as_alias: bool = True,
    ) -> SendAs:
        """Create a new send-as alias.

        Non-primary aliases require email verification — the new entry
        starts in ``verification_status = "pending"`` and a verification
        message is sent to the address. Call :meth:`verify_send_as` to
        resend that message if needed.

        Args:
            send_as_email: The address to add (must be different from
                existing aliases).
            display_name: Friendly display name shown on outgoing mail
                (``"Sachin <sachin@example.com>"``).
            reply_to_address: Default Reply-To for mail sent from this
                address.
            signature: HTML signature appended to outgoing mail.
            treat_as_alias: Whether Gmail treats this as an alias (True)
                or a distinct account (False, requires SMTP relay config).

        Returns:
            The created SendAs entry (typically with status=pending).
        """
        payload: dict[str, Any] = {
            "sendAsEmail": send_as_email,
            "treatAsAlias": treat_as_alias,
        }
        if display_name is not None:
            payload["displayName"] = display_name
        if reply_to_address is not None:
            payload["replyToAddress"] = reply_to_address
        if signature is not None:
            payload["signature"] = signature

        data = await self._request("POST", "/users/me/settings/sendAs", json=payload)
        return _parse_send_as(data)

    @action("Update a send-as alias", requires_scope="settings")
    async def update_send_as(
        self,
        send_as_email: str,
        display_name: Optional[str] = None,
        reply_to_address: Optional[str] = None,
        signature: Optional[str] = None,
        is_default: Optional[bool] = None,
        treat_as_alias: Optional[bool] = None,
    ) -> SendAs:
        """Update mutable fields on a send-as alias.

        Uses ``PATCH`` semantics — only the fields you set are changed.

        Args:
            send_as_email: The alias to update (URL-path key).
            display_name: New display name, or None to leave unchanged.
            reply_to_address: New default Reply-To, or None.
            signature: New HTML signature, or None.
            is_default: Set True to make this the default send-from address.
            treat_as_alias: Toggle alias vs. distinct-account behavior.

        Returns:
            The updated SendAs entry.
        """
        payload: dict[str, Any] = {}
        if display_name is not None:
            payload["displayName"] = display_name
        if reply_to_address is not None:
            payload["replyToAddress"] = reply_to_address
        if signature is not None:
            payload["signature"] = signature
        if is_default is not None:
            payload["isDefault"] = is_default
        if treat_as_alias is not None:
            payload["treatAsAlias"] = treat_as_alias

        data = await self._request(
            "PATCH", f"/users/me/settings/sendAs/{send_as_email}", json=payload
        )
        return _parse_send_as(data)

    @action("Delete a send-as alias", requires_scope="settings", dangerous=True)
    async def delete_send_as(self, send_as_email: str) -> None:
        """Remove a send-as alias.

        Deletes even if the alias is the default (another address will
        become default on the server side).

        Args:
            send_as_email: The alias to remove.
        """
        await self._request("DELETE", f"/users/me/settings/sendAs/{send_as_email}")

    @action("Re-send verification for a pending send-as", requires_scope="settings")
    async def verify_send_as(self, send_as_email: str) -> None:
        """Trigger Gmail to re-send the ownership-verification email.

        Only meaningful when the alias is in ``verification_status = "pending"``.

        Args:
            send_as_email: The pending alias to re-verify.
        """
        await self._request("POST", f"/users/me/settings/sendAs/{send_as_email}/verify")

    # ==================================================================
    # Settings — Delegates (mailbox-access sharing, Workspace only)
    # ==================================================================
    # Docs: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.settings.delegates

    @action("List mailbox delegates", requires_scope="settings")
    async def list_delegates(self) -> list[Delegate]:
        """List accounts that have been delegated access to this mailbox.

        Workspace-only feature — returns empty list on consumer Gmail.
        """
        data = await self._request("GET", "/users/me/settings/delegates")
        return [_parse_delegate(d) for d in data.get("delegates", [])]

    @action("Get a delegate by email", requires_scope="settings")
    async def get_delegate(self, delegate_email: str) -> Delegate:
        """Retrieve a single delegate's info (including verification status)."""
        data = await self._request("GET", f"/users/me/settings/delegates/{delegate_email}")
        return _parse_delegate(data)

    @action("Add a mailbox delegate", requires_scope="settings", dangerous=True)
    async def create_delegate(self, delegate_email: str) -> Delegate:
        """Grant another account access to this mailbox.

        The new delegate receives an email asking them to accept. Their
        verification_status stays "pending" until they do.

        Args:
            delegate_email: The account to grant delegated access to.
        """
        data = await self._request(
            "POST",
            "/users/me/settings/delegates",
            json={"delegateEmail": delegate_email},
        )
        return _parse_delegate(data)

    @action("Remove a mailbox delegate", requires_scope="settings", dangerous=True)
    async def delete_delegate(self, delegate_email: str) -> None:
        """Revoke a delegate's access.

        Args:
            delegate_email: The delegate to remove.
        """
        await self._request("DELETE", f"/users/me/settings/delegates/{delegate_email}")

    # ==================================================================
    # Settings — Forwarding addresses
    # ==================================================================
    # Docs: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.settings.forwardingAddresses

    @action("List forwarding addresses", requires_scope="settings")
    async def list_forwarding_addresses(self) -> list[ForwardingAddress]:
        """List every verified forwarding address on the account.

        Forwarding addresses are separate from send-as aliases — they're
        *destinations* where Gmail can forward incoming mail.
        """
        data = await self._request("GET", "/users/me/settings/forwardingAddresses")
        return [_parse_forwarding_address(f) for f in data.get("forwardingAddresses", [])]

    @action("Get a forwarding address", requires_scope="settings")
    async def get_forwarding_address(self, forwarding_email: str) -> ForwardingAddress:
        """Retrieve a single forwarding address and its verification status."""
        data = await self._request(
            "GET",
            f"/users/me/settings/forwardingAddresses/{forwarding_email}",
        )
        return _parse_forwarding_address(data)

    @action(
        "Add a forwarding address (pending verification)",
        requires_scope="settings",
        dangerous=True,
    )
    async def create_forwarding_address(self, forwarding_email: str) -> ForwardingAddress:
        """Add a forwarding address.

        Gmail sends a verification email to the address; status stays
        ``pending`` until the recipient clicks the verification link.

        Args:
            forwarding_email: The destination address for forwarded mail.
        """
        data = await self._request(
            "POST",
            "/users/me/settings/forwardingAddresses",
            json={"forwardingEmail": forwarding_email},
        )
        return _parse_forwarding_address(data)

    @action("Remove a forwarding address", requires_scope="settings", dangerous=True)
    async def delete_forwarding_address(self, forwarding_email: str) -> None:
        """Remove a forwarding address.

        If this address was used by any filters with ``forward`` actions,
        those filter actions become no-ops (not an error).

        Args:
            forwarding_email: The address to remove.
        """
        await self._request(
            "DELETE",
            f"/users/me/settings/forwardingAddresses/{forwarding_email}",
        )

    # ==================================================================
    # Settings — Top-level auto-forwarding
    # ==================================================================
    # Separate from filters and forwarding addresses: this is the global
    # "forward ALL incoming mail to X" setting.

    @action("Get auto-forwarding settings", requires_scope="settings")
    async def get_auto_forwarding(self) -> AutoForwarding:
        """Retrieve the global auto-forwarding configuration."""
        data = await self._request("GET", "/users/me/settings/autoForwarding")
        return _parse_auto_forwarding(data)

    @action("Update auto-forwarding settings", requires_scope="settings", dangerous=True)
    async def update_auto_forwarding(
        self,
        enabled: bool,
        email_address: Optional[str] = None,
        disposition: Optional[str] = None,
    ) -> AutoForwarding:
        """Enable, disable, or reconfigure global auto-forwarding.

        Args:
            enabled: Whether auto-forwarding is on.
            email_address: Destination (must be a verified forwarding
                address — see :meth:`create_forwarding_address`).
                Required when ``enabled=True``.
            disposition: What happens to the original in this mailbox.
                One of ``"leaveInInbox"``, ``"archive"``, ``"trash"``,
                ``"markRead"``. Required when ``enabled=True``.

        Returns:
            The updated AutoForwarding config.
        """
        payload: dict[str, Any] = {"enabled": enabled}
        if email_address is not None:
            payload["emailAddress"] = email_address
        if disposition is not None:
            payload["disposition"] = disposition
        data = await self._request("PUT", "/users/me/settings/autoForwarding", json=payload)
        return _parse_auto_forwarding(data)

    # ==================================================================
    # Settings — IMAP / POP / Language
    # ==================================================================

    @action("Get IMAP settings", requires_scope="settings")
    async def get_imap_settings(self) -> ImapSettings:
        """Retrieve IMAP access configuration."""
        data = await self._request("GET", "/users/me/settings/imap")
        return _parse_imap_settings(data)

    @action("Update IMAP settings", requires_scope="settings", dangerous=True)
    async def update_imap_settings(
        self,
        enabled: bool,
        auto_expunge: Optional[bool] = None,
        expunge_behavior: Optional[str] = None,
        max_folder_size: Optional[int] = None,
    ) -> ImapSettings:
        """Enable/disable IMAP and configure expunge behavior.

        Args:
            enabled: Whether IMAP access is allowed.
            auto_expunge: Whether to auto-expunge deleted messages.
            expunge_behavior: ``"archive"``, ``"trash"``, or ``"deleteForever"``.
            max_folder_size: Max folder size (0 = unlimited).
        """
        payload: dict[str, Any] = {"enabled": enabled}
        if auto_expunge is not None:
            payload["autoExpunge"] = auto_expunge
        if expunge_behavior is not None:
            payload["expungeBehavior"] = expunge_behavior
        if max_folder_size is not None:
            payload["maxFolderSize"] = max_folder_size
        data = await self._request("PUT", "/users/me/settings/imap", json=payload)
        return _parse_imap_settings(data)

    @action("Get POP settings", requires_scope="settings")
    async def get_pop_settings(self) -> PopSettings:
        """Retrieve POP3 access configuration."""
        data = await self._request("GET", "/users/me/settings/pop")
        return _parse_pop_settings(data)

    @action("Update POP settings", requires_scope="settings", dangerous=True)
    async def update_pop_settings(
        self,
        access_window: Optional[str] = None,
        disposition: Optional[str] = None,
    ) -> PopSettings:
        """Configure POP3 access.

        Args:
            access_window: ``"disabled"``, ``"allMail"``, or ``"fromNowOn"``.
            disposition: What happens to fetched messages in the mailbox
                (``"leaveInInbox"``, ``"archive"``, ``"trash"``, ``"markRead"``).
        """
        payload: dict[str, Any] = {}
        if access_window is not None:
            payload["accessWindow"] = access_window
        if disposition is not None:
            payload["disposition"] = disposition
        data = await self._request("PUT", "/users/me/settings/pop", json=payload)
        return _parse_pop_settings(data)

    @action("Get language settings", requires_scope="settings")
    async def get_language(self) -> LanguageSettings:
        """Retrieve the account's Gmail UI language preference."""
        data = await self._request("GET", "/users/me/settings/language")
        return _parse_language_settings(data)

    @action("Update language settings", requires_scope="settings")
    async def update_language(self, display_language: str) -> LanguageSettings:
        """Set the Gmail UI language.

        Args:
            display_language: BCP-47 language code (e.g. ``"en-US"``,
                ``"es"``, ``"ja"``). Non-existent codes are accepted by
                the API but have no effect.
        """
        data = await self._request(
            "PUT",
            "/users/me/settings/language",
            json={"displayLanguage": display_language},
        )
        return _parse_language_settings(data)

    # ==================================================================
    # Push notifications — /watch and /stop
    # ==================================================================
    # Gmail's push model uses Google Cloud Pub/Sub. Users must:
    #   1. Create a Pub/Sub topic in a GCP project
    #   2. Grant gmail-api-push@system.gserviceaccount.com the
    #      pubsub.publisher role on that topic
    #   3. Pass the fully-qualified topic name here
    # See: https://developers.google.com/workspace/gmail/api/guides/push

    @action(
        "Start receiving mailbox-change push notifications",
        requires_scope="read",
        dangerous=True,
    )
    async def watch(
        self,
        topic_name: str,
        label_ids: Optional[list[str]] = None,
        label_filter_behavior: Optional[str] = None,
    ) -> dict[str, Any]:
        """Subscribe this mailbox to push notifications on a Pub/Sub topic.

        Gmail's push notifications aren't webhooks — they publish to a
        Google Cloud Pub/Sub topic that the caller owns. You must have
        created the topic and granted
        ``gmail-api-push@system.gserviceaccount.com`` the
        ``pubsub.publisher`` role on it before calling this.

        Returns a short-lived ``historyId`` that must be renewed every
        ~7 days; call this action again on a schedule.

        Args:
            topic_name: Fully-qualified Pub/Sub topic name, e.g.
                ``"projects/my-project/topics/gmail-notifs"``.
            label_ids: Restrict notifications to changes on these labels.
            label_filter_behavior: ``"include"`` (default — only listed
                labels) or ``"exclude"`` (notify for everything EXCEPT
                these labels).

        Returns:
            A dict with ``historyId`` and ``expiration`` (epoch ms).
        """
        payload: dict[str, Any] = {"topicName": topic_name}
        if label_ids is not None:
            payload["labelIds"] = label_ids
        if label_filter_behavior is not None:
            payload["labelFilterBehavior"] = label_filter_behavior
        return await self._request("POST", "/users/me/watch", json=payload)

    @action("Stop push notifications", requires_scope="read")
    async def stop(self) -> None:
        """Cancel any active push-notification subscription for this mailbox.

        Idempotent — safe to call even if no watch is active.
        """
        await self._request("POST", "/users/me/stop")
