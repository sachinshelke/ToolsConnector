"""Outlook connector -- read, send, and manage emails via the Microsoft Graph API.

Uses httpx for direct HTTP calls against the MS Graph REST API v1.0.
Expects an OAuth 2.0 access token passed as ``credentials``.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from toolsconnector.errors import APIError, NotFoundError, RateLimitError
from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import ConnectorCategory, ProtocolType, RateLimitSpec
from toolsconnector.types import PageState, PaginatedList

from .types import EmailRecipient, MailFolder, OutlookMessage, OutlookMessageId

logger = logging.getLogger("toolsconnector.outlook")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_recipient(raw: dict[str, Any]) -> EmailRecipient:
    """Parse an MS Graph ``emailAddress`` object into an EmailRecipient.

    Args:
        raw: Dict with ``emailAddress`` containing ``name`` and ``address``.

    Returns:
        Parsed EmailRecipient.
    """
    addr = raw.get("emailAddress", {})
    return EmailRecipient(
        email=addr.get("address", ""),
        name=addr.get("name") or None,
    )


def _parse_message(data: dict[str, Any]) -> OutlookMessage:
    """Parse an MS Graph message JSON into an OutlookMessage model.

    Args:
        data: Raw JSON response from the messages endpoint.

    Returns:
        Populated OutlookMessage instance.
    """
    from_raw = data.get("from")
    from_addr = _parse_recipient(from_raw) if from_raw else None

    to_list = [_parse_recipient(r) for r in data.get("toRecipients", [])]
    cc_list = [_parse_recipient(r) for r in data.get("ccRecipients", [])]

    body = data.get("body", {})

    return OutlookMessage(
        id=data.get("id", ""),
        subject=data.get("subject"),
        body_preview=data.get("bodyPreview"),
        body_content=body.get("content"),
        body_content_type=body.get("contentType"),
        from_address=from_addr,
        to_recipients=to_list,
        cc_recipients=cc_list,
        received_datetime=data.get("receivedDateTime"),
        sent_datetime=data.get("sentDateTime"),
        is_read=data.get("isRead", False),
        has_attachments=data.get("hasAttachments", False),
        importance=data.get("importance", "normal"),
        conversation_id=data.get("conversationId"),
        web_link=data.get("webLink"),
    )


def _parse_folder(data: dict[str, Any]) -> MailFolder:
    """Parse an MS Graph mailFolder JSON into a MailFolder model.

    Args:
        data: Raw JSON response from the mailFolders endpoint.

    Returns:
        Populated MailFolder instance.
    """
    return MailFolder(
        id=data.get("id", ""),
        display_name=data.get("displayName", ""),
        parent_folder_id=data.get("parentFolderId"),
        child_folder_count=data.get("childFolderCount", 0),
        total_item_count=data.get("totalItemCount", 0),
        unread_item_count=data.get("unreadItemCount", 0),
    )


class Outlook(BaseConnector):
    """Connect to Microsoft Outlook to read, send, and manage emails.

    Requires an OAuth 2.0 access token for Microsoft Graph passed as
    ``credentials``. Uses the MS Graph REST API v1.0 with ``@odata.nextLink``
    pagination.
    """

    name = "outlook"
    display_name = "Microsoft Outlook"
    category = ConnectorCategory.COMMUNICATION
    protocol = ProtocolType.REST
    base_url = "https://graph.microsoft.com/v1.0"
    description = "Connect to Microsoft Outlook to read, send, and manage emails via MS Graph."
    _rate_limit_config = RateLimitSpec(rate=10000, period=600, burst=100)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Initialise the persistent async HTTP client."""
        self._client = httpx.AsyncClient(
            base_url=self._base_url or self.__class__.base_url,
            headers={
                "Authorization": f"Bearer {self._credentials}",
                "Content-Type": "application/json",
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
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[dict[str, Any]] = None,
        full_url: Optional[str] = None,
    ) -> dict[str, Any]:
        """Execute an authenticated HTTP request against the MS Graph API.

        Args:
            method: HTTP method (GET, POST, PATCH, DELETE).
            path: API path relative to base_url (e.g. ``/me/messages``).
            params: URL query parameters.
            json_body: JSON request body.
            full_url: If provided, use this absolute URL instead of base_url + path.
                Used for following ``@odata.nextLink`` pagination URLs.

        Returns:
            Parsed JSON response as a dict.

        Raises:
            RateLimitError: When MS Graph returns HTTP 429.
            NotFoundError: When the resource is not found (HTTP 404).
            APIError: For any other non-2xx status.
        """
        kwargs: dict[str, Any] = {}
        if params:
            kwargs["params"] = params
        if json_body is not None:
            kwargs["json"] = json_body

        if full_url:
            response = await self._client.request(method, full_url, **kwargs)
        else:
            response = await self._client.request(method, path, **kwargs)

        if response.status_code == 429:
            retry_after = float(response.headers.get("Retry-After", "60"))
            raise RateLimitError(
                "MS Graph rate limit exceeded",
                connector="outlook",
                action=path,
                retry_after_seconds=retry_after,
            )
        if response.status_code == 404:
            raise NotFoundError(
                f"Resource not found: {path}",
                connector="outlook",
                action=path,
            )
        if response.status_code >= 400:
            detail = response.text[:500]
            raise APIError(
                f"MS Graph error {response.status_code}: {detail}",
                connector="outlook",
                action=path,
                details={"status_code": response.status_code},
            )

        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    @action("List email messages from a folder")
    async def list_messages(
        self,
        folder: Optional[str] = None,
        limit: int = 25,
        skip: int = 0,
        page_url: Optional[str] = None,
    ) -> PaginatedList[OutlookMessage]:
        """List email messages from the user's mailbox.

        Args:
            folder: Mail folder ID to list from (defaults to Inbox).
            limit: Maximum number of messages per page (max 1000).
            skip: Number of messages to skip (offset pagination).
            page_url: Full ``@odata.nextLink`` URL for fetching the next page.

        Returns:
            Paginated list of OutlookMessage objects.
        """
        if page_url:
            data = await self._request("GET", "", full_url=page_url)
        else:
            base_path = f"/me/mailFolders/{folder}/messages" if folder else "/me/messages"
            params: dict[str, Any] = {
                "$top": min(limit, 1000),
                "$orderby": "receivedDateTime desc",
            }
            if skip > 0:
                params["$skip"] = skip
            data = await self._request("GET", base_path, params=params)

        messages = [_parse_message(m) for m in data.get("value", [])]
        next_link = data.get("@odata.nextLink")

        return PaginatedList(
            items=messages,
            page_state=PageState(
                cursor=next_link,
                has_more=next_link is not None,
            ),
            total_count=data.get("@odata.count"),
        )

    @action("Get a single email message by ID")
    async def get_message(self, message_id: str) -> OutlookMessage:
        """Retrieve a single email message by its ID.

        Args:
            message_id: The unique ID of the email message.

        Returns:
            The requested OutlookMessage.
        """
        data = await self._request("GET", f"/me/messages/{message_id}")
        return _parse_message(data)

    @action("Send an email message", dangerous=True)
    async def send_message(
        self,
        to: list[str],
        subject: str,
        body: str,
        cc: Optional[list[str]] = None,
    ) -> OutlookMessageId:
        """Send an email message via MS Graph.

        Args:
            to: List of recipient email addresses.
            subject: Email subject line.
            body: Email body content (HTML supported).
            cc: Optional list of CC recipient email addresses.

        Returns:
            OutlookMessageId with the sent message's ID.
        """
        to_recipients = [
            {"emailAddress": {"address": addr}} for addr in to
        ]
        cc_recipients = [
            {"emailAddress": {"address": addr}} for addr in (cc or [])
        ]

        payload: dict[str, Any] = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "HTML",
                    "content": body,
                },
                "toRecipients": to_recipients,
            },
            "saveToSentItems": True,
        }
        if cc_recipients:
            payload["message"]["ccRecipients"] = cc_recipients

        data = await self._request("POST", "/me/sendMail", json_body=payload)
        # sendMail returns 202 Accepted with no body; return empty ID
        return OutlookMessageId(id=data.get("id", ""))

    @action("List mail folders")
    async def list_folders(self) -> list[MailFolder]:
        """List all mail folders in the user's mailbox.

        Returns:
            List of MailFolder objects (Inbox, Sent Items, etc.).
        """
        data = await self._request("GET", "/me/mailFolders", params={"$top": 100})
        return [_parse_folder(f) for f in data.get("value", [])]

    @action("Search email messages")
    async def search_messages(
        self,
        query: str,
        limit: int = 25,
        page_url: Optional[str] = None,
    ) -> PaginatedList[OutlookMessage]:
        """Search email messages using the MS Graph ``$search`` parameter.

        Uses KQL (Keyword Query Language) syntax supported by MS Graph.

        Args:
            query: Search query string (e.g. ``"subject:meeting"``).
            limit: Maximum results per page.
            page_url: Full ``@odata.nextLink`` URL for fetching the next page.

        Returns:
            Paginated list of matching OutlookMessage objects.
        """
        if page_url:
            data = await self._request("GET", "", full_url=page_url)
        else:
            params: dict[str, Any] = {
                "$search": f'"{query}"',
                "$top": min(limit, 250),
            }
            data = await self._request("GET", "/me/messages", params=params)

        messages = [_parse_message(m) for m in data.get("value", [])]
        next_link = data.get("@odata.nextLink")

        return PaginatedList(
            items=messages,
            page_state=PageState(
                cursor=next_link,
                has_more=next_link is not None,
            ),
        )

    @action("Delete an email message", dangerous=True)
    async def delete_message(self, message_id: str) -> None:
        """Permanently delete an email message.

        Args:
            message_id: The unique ID of the message to delete.

        Warning:
            This permanently deletes the message. It cannot be undone.
        """
        await self._request("DELETE", f"/me/messages/{message_id}")

    @action("Create an email draft")
    async def create_draft(
        self,
        to: list[str],
        subject: str,
        body: str,
    ) -> OutlookMessageId:
        """Create a draft email message.

        Args:
            to: List of recipient email addresses.
            subject: Email subject line.
            body: Email body content (HTML supported).

        Returns:
            OutlookMessageId with the created draft's ID.
        """
        to_recipients = [
            {"emailAddress": {"address": addr}} for addr in to
        ]

        payload: dict[str, Any] = {
            "subject": subject,
            "body": {
                "contentType": "HTML",
                "content": body,
            },
            "toRecipients": to_recipients,
        }

        data = await self._request("POST", "/me/messages", json_body=payload)
        return OutlookMessageId(id=data.get("id", ""))

    @action("Reply to an email message", dangerous=True)
    async def reply_to_message(
        self,
        message_id: str,
        body: str,
    ) -> None:
        """Reply to an email message.

        Sends a reply to all original recipients of the specified message.

        Args:
            message_id: The unique ID of the message to reply to.
            body: Reply body content (HTML supported).
        """
        payload: dict[str, Any] = {
            "comment": body,
        }
        await self._request(
            "POST",
            f"/me/messages/{message_id}/reply",
            json_body=payload,
        )
