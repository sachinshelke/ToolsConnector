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

from .types import (
    MailFolder,
    MailRule,
    MailTip,
    OutlookAttachment,
    OutlookCalendarEvent,
    OutlookCategory,
    OutlookContact,
    OutlookMessage,
    OutlookMessageId,
)

from ._helpers import (
    parse_attachment as _parse_attachment,
    parse_calendar_event as _parse_calendar_event,
    parse_category as _parse_category,
    parse_contact as _parse_contact,
    parse_folder as _parse_folder,
    parse_mail_rule as _parse_mail_rule,
    parse_mail_tip as _parse_mail_tip,
    parse_message as _parse_message,
)

logger = logging.getLogger("toolsconnector.outlook")


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
    async def reply_message(
        self,
        message_id: str,
        body: str,
        reply_all: bool = False,
    ) -> None:
        """Reply to an email message.

        Sends a reply to the sender, or to all original recipients when
        ``reply_all`` is ``True``.

        Args:
            message_id: The unique ID of the message to reply to.
            body: Reply body content (HTML supported).
            reply_all: If ``True``, reply to all original recipients.
                Defaults to ``False`` (reply to sender only).
        """
        endpoint = "replyAll" if reply_all else "reply"
        payload: dict[str, Any] = {
            "comment": body,
        }
        await self._request(
            "POST",
            f"/me/messages/{message_id}/{endpoint}",
            json_body=payload,
        )

    # ------------------------------------------------------------------
    # Actions -- Contacts
    # ------------------------------------------------------------------

    @action("List contacts")
    async def list_contacts(
        self,
        limit: int = 25,
        skip: int = 0,
        page_url: Optional[str] = None,
    ) -> PaginatedList[OutlookContact]:
        """List contacts from the user's default contacts folder.

        Args:
            limit: Maximum number of contacts per page (max 1000).
            skip: Number of contacts to skip (offset pagination).
            page_url: Full ``@odata.nextLink`` URL for the next page.

        Returns:
            Paginated list of OutlookContact objects.
        """
        if page_url:
            data = await self._request("GET", "", full_url=page_url)
        else:
            params: dict[str, Any] = {"$top": min(limit, 1000)}
            if skip > 0:
                params["$skip"] = skip
            data = await self._request("GET", "/me/contacts", params=params)

        contacts = [_parse_contact(c) for c in data.get("value", [])]
        next_link = data.get("@odata.nextLink")

        return PaginatedList(
            items=contacts,
            page_state=PageState(
                cursor=next_link,
                has_more=next_link is not None,
            ),
        )

    @action("Get a single contact by ID")
    async def get_contact(self, contact_id: str) -> OutlookContact:
        """Retrieve a single contact by its ID.

        Args:
            contact_id: The unique ID of the contact.

        Returns:
            The requested OutlookContact.
        """
        data = await self._request("GET", f"/me/contacts/{contact_id}")
        return _parse_contact(data)

    @action("Create a new contact", dangerous=True)
    async def create_contact(
        self,
        given_name: str,
        surname: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
    ) -> OutlookContact:
        """Create a new contact in the user's default contacts folder.

        Args:
            given_name: First name of the contact.
            surname: Last name of the contact.
            email: Primary email address.
            phone: Primary phone number.

        Returns:
            The created OutlookContact.
        """
        payload: dict[str, Any] = {"givenName": given_name}
        if surname:
            payload["surname"] = surname
        if email:
            payload["emailAddresses"] = [
                {"address": email, "name": f"{given_name} {surname or ''}".strip()},
            ]
        if phone:
            payload["businessPhones"] = [phone]

        data = await self._request("POST", "/me/contacts", json_body=payload)
        return _parse_contact(data)

    # ------------------------------------------------------------------
    # Actions -- Calendar
    # ------------------------------------------------------------------

    @action("List calendar events")
    async def list_calendar_events(
        self,
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: int = 25,
        page_url: Optional[str] = None,
    ) -> PaginatedList[OutlookCalendarEvent]:
        """List calendar events from the user's default calendar.

        When ``start`` and ``end`` are provided, uses the calendarView
        endpoint to return events within that time range. Otherwise lists
        events ordered by start time.

        Args:
            start: ISO 8601 start datetime for the range filter
                (e.g. ``2024-01-01T00:00:00Z``).
            end: ISO 8601 end datetime for the range filter.
            limit: Maximum events per page (max 1000).
            page_url: Full ``@odata.nextLink`` URL for the next page.

        Returns:
            Paginated list of OutlookCalendarEvent objects.
        """
        if page_url:
            data = await self._request("GET", "", full_url=page_url)
        elif start and end:
            params: dict[str, Any] = {
                "startDateTime": start,
                "endDateTime": end,
                "$top": min(limit, 1000),
                "$orderby": "start/dateTime",
            }
            data = await self._request(
                "GET", "/me/calendarView", params=params,
            )
        else:
            params = {
                "$top": min(limit, 1000),
                "$orderby": "start/dateTime",
            }
            data = await self._request("GET", "/me/events", params=params)

        events = [_parse_calendar_event(e) for e in data.get("value", [])]
        next_link = data.get("@odata.nextLink")

        return PaginatedList(
            items=events,
            page_state=PageState(
                cursor=next_link,
                has_more=next_link is not None,
            ),
        )

    @action("Create a calendar event", dangerous=True)
    async def create_calendar_event(
        self,
        subject: str,
        start: str,
        end: str,
        attendees: Optional[list[str]] = None,
        body: Optional[str] = None,
    ) -> OutlookCalendarEvent:
        """Create a new event on the user's default calendar.

        Args:
            subject: Event title/subject.
            start: ISO 8601 start datetime (e.g. ``2024-06-15T09:00:00``).
            end: ISO 8601 end datetime (e.g. ``2024-06-15T10:00:00``).
            attendees: Optional list of attendee email addresses.
            body: Optional event body/description (HTML supported).

        Returns:
            The created OutlookCalendarEvent.
        """
        payload: dict[str, Any] = {
            "subject": subject,
            "start": {"dateTime": start, "timeZone": "UTC"},
            "end": {"dateTime": end, "timeZone": "UTC"},
        }
        if attendees:
            payload["attendees"] = [
                {
                    "emailAddress": {"address": addr},
                    "type": "required",
                }
                for addr in attendees
            ]
        if body:
            payload["body"] = {"contentType": "HTML", "content": body}

        data = await self._request("POST", "/me/events", json_body=payload)
        return _parse_calendar_event(data)

    # ------------------------------------------------------------------
    # Actions -- Message management
    # ------------------------------------------------------------------

    @action("Move a message to another folder")
    async def move_message(
        self,
        message_id: str,
        destination_folder_id: str,
    ) -> OutlookMessage:
        """Move an email message to a different mail folder.

        Args:
            message_id: The unique ID of the message to move.
            destination_folder_id: The ID of the destination mail folder.

        Returns:
            The moved OutlookMessage with its updated ID.
        """
        payload: dict[str, Any] = {"destinationId": destination_folder_id}
        data = await self._request(
            "POST",
            f"/me/messages/{message_id}/move",
            json_body=payload,
        )
        return _parse_message(data)

    @action("Create a mail folder", dangerous=True)
    async def create_folder(
        self,
        display_name: str,
        parent_folder_id: Optional[str] = None,
    ) -> MailFolder:
        """Create a new mail folder.

        Args:
            display_name: Display name for the new folder.
            parent_folder_id: Optional parent folder ID. If omitted the
                folder is created at the top level of the mailbox.

        Returns:
            The created MailFolder.
        """
        payload: dict[str, Any] = {"displayName": display_name}

        if parent_folder_id:
            path = f"/me/mailFolders/{parent_folder_id}/childFolders"
        else:
            path = "/me/mailFolders"

        data = await self._request("POST", path, json_body=payload)
        return _parse_folder(data)

    @action("Forward an email message", dangerous=True)
    async def forward_message(
        self,
        message_id: str,
        to: list[str],
        comment: Optional[str] = None,
    ) -> None:
        """Forward an email message to one or more recipients.

        Args:
            message_id: The unique ID of the message to forward.
            to: List of recipient email addresses to forward to.
            comment: Optional comment to include with the forwarded message.
        """
        to_recipients = [
            {"emailAddress": {"address": addr}} for addr in to
        ]
        payload: dict[str, Any] = {
            "toRecipients": to_recipients,
        }
        if comment:
            payload["comment"] = comment

        await self._request(
            "POST",
            f"/me/messages/{message_id}/forward",
            json_body=payload,
        )

    # ------------------------------------------------------------------
    # Actions -- Attachments
    # ------------------------------------------------------------------

    @action("List attachments on an email message")
    async def list_attachments(self, message_id: str) -> list[OutlookAttachment]:
        """List all attachments on an email message.

        Args:
            message_id: The unique ID of the email message.

        Returns:
            List of OutlookAttachment objects.
        """
        data = await self._request(
            "GET",
            f"/me/messages/{message_id}/attachments",
        )
        return [_parse_attachment(a) for a in data.get("value", [])]

    @action("Get a single attachment by ID")
    async def get_attachment(
        self,
        message_id: str,
        attachment_id: str,
    ) -> OutlookAttachment:
        """Retrieve a single attachment from an email message.

        Args:
            message_id: The unique ID of the email message.
            attachment_id: The unique ID of the attachment.

        Returns:
            The requested OutlookAttachment (includes ``content_bytes``
            for file attachments).
        """
        data = await self._request(
            "GET",
            f"/me/messages/{message_id}/attachments/{attachment_id}",
        )
        return _parse_attachment(data)

    # ------------------------------------------------------------------
    # Actions -- Message update
    # ------------------------------------------------------------------

    @action("Update properties of an email message")
    async def update_message(
        self,
        message_id: str,
        is_read: Optional[bool] = None,
        categories: Optional[list[str]] = None,
        importance: Optional[str] = None,
    ) -> OutlookMessage:
        """Update mutable properties of an email message.

        Supports marking messages as read/unread, assigning categories,
        and changing importance.

        Args:
            message_id: The unique ID of the message to update.
            is_read: Mark the message as read (``True``) or unread (``False``).
            categories: List of category names to assign to the message.
            importance: Message importance (``"low"``, ``"normal"``, or ``"high"``).

        Returns:
            The updated OutlookMessage.
        """
        payload: dict[str, Any] = {}
        if is_read is not None:
            payload["isRead"] = is_read
        if categories is not None:
            payload["categories"] = categories
        if importance is not None:
            payload["importance"] = importance

        data = await self._request(
            "PATCH",
            f"/me/messages/{message_id}",
            json_body=payload,
        )
        return _parse_message(data)

    # ------------------------------------------------------------------
    # Actions -- Mail rules
    # ------------------------------------------------------------------

    @action("List inbox message rules")
    async def list_mail_rules(self) -> list[MailRule]:
        """List all message rules defined on the user's Inbox folder.

        Returns:
            List of MailRule objects.
        """
        data = await self._request(
            "GET",
            "/me/mailFolders/inbox/messageRules",
        )
        return [_parse_mail_rule(r) for r in data.get("value", [])]

    @action("Create a new inbox message rule", dangerous=True)
    async def create_mail_rule(
        self,
        display_name: str,
        conditions: dict[str, Any],
        actions: dict[str, Any],
    ) -> MailRule:
        """Create a new message rule on the user's Inbox folder.

        The ``conditions`` and ``actions`` dicts follow the MS Graph
        ``messageRulePredicates`` and ``messageRuleActions`` schemas.

        Example conditions::

            {"senderContains": ["noreply@example.com"]}

        Example actions::

            {"moveToFolder": "AAMk...", "markAsRead": True}

        Args:
            display_name: Human-readable name for the rule.
            conditions: Rule conditions that trigger the rule.
            actions: Actions to take when conditions are met.

        Returns:
            The created MailRule.
        """
        payload: dict[str, Any] = {
            "displayName": display_name,
            "sequence": 0,
            "isEnabled": True,
            "conditions": conditions,
            "actions": actions,
        }
        data = await self._request(
            "POST",
            "/me/mailFolders/inbox/messageRules",
            json_body=payload,
        )
        return _parse_mail_rule(data)

    # ------------------------------------------------------------------
    # Actions -- Categories
    # ------------------------------------------------------------------

    @action("List master categories")
    async def list_categories(self) -> list[OutlookCategory]:
        """List all master categories defined in the user's mailbox.

        Returns:
            List of OutlookCategory objects.
        """
        data = await self._request(
            "GET",
            "/me/outlook/masterCategories",
        )
        return [_parse_category(c) for c in data.get("value", [])]

    # ------------------------------------------------------------------
    # Actions -- Mail tips
    # ------------------------------------------------------------------

    @action("Get mail tips for email addresses")
    async def get_mail_tips(
        self,
        email_addresses: list[str],
    ) -> list[MailTip]:
        """Get mail tips for one or more email addresses.

        Returns delivery status information such as automatic replies,
        mailbox-full status, delivery restrictions, and distribution
        list membership counts.

        Args:
            email_addresses: List of email addresses to retrieve tips for.

        Returns:
            List of MailTip objects, one per requested address.
        """
        payload: dict[str, Any] = {
            "emailAddresses": email_addresses,
            "mailTipsOptions": "automaticReplies,mailboxFullStatus,"
            "maxMessageSize,deliveryRestriction,"
            "moderationStatus,recipientScope,"
            "totalMemberCount,externalMemberCount",
        }
        data = await self._request(
            "POST",
            "/me/getMailTips",
            json_body=payload,
        )
        return [_parse_mail_tip(t) for t in data.get("value", [])]
