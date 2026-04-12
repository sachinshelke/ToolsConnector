"""Mailchimp connector -- audience lists, members, and campaigns.

Uses the Mailchimp Marketing API v3.0 with Basic auth (``anystring:api_key``).
The datacenter is extracted from the API key suffix (e.g. ``us21``).
Offset-based pagination via ``offset`` and ``count`` parameters.
"""

from __future__ import annotations

import base64
import hashlib
import logging
from typing import Any, Optional

import httpx

from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import (
    ConnectorCategory,
    ProtocolType,
    RateLimitSpec,
)
from toolsconnector.types import PageState, PaginatedList

from ._parsers import parse_campaign, parse_list, parse_member
from .types import (
    MailchimpCampaign,
    MailchimpCampaignReport,
    MailchimpList,
    MailchimpMember,
    MailchimpSegment,
    MailchimpTemplate,
)

logger = logging.getLogger("toolsconnector.mailchimp")


class Mailchimp(BaseConnector):
    """Connect to Mailchimp to manage audience lists, members, and campaigns.

    Supports API key authentication via HTTP Basic auth. The API key
    contains the datacenter suffix (e.g. ``abc123-us21``), which is
    extracted to build the base URL.
    """

    name = "mailchimp"
    display_name = "Mailchimp"
    category = ConnectorCategory.MARKETING
    protocol = ProtocolType.REST
    base_url = "https://{dc}.api.mailchimp.com/3.0"
    description = (
        "Connect to Mailchimp to manage audience lists, "
        "subscribers, and email campaigns."
    )
    _rate_limit_config = RateLimitSpec(rate=10, period=1, burst=5)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Initialise the httpx async client with Mailchimp Basic auth.

        Extracts the datacenter from the API key (text after the last
        ``-``) and builds the base URL. Auth uses Basic auth with
        ``anystring`` as the username and the API key as the password.
        """
        api_key = self._credentials or ""

        # Extract datacenter from API key (e.g. "abc123def456-us21" -> "us21")
        if "-" in api_key:
            dc = api_key.rsplit("-", 1)[-1]
        else:
            dc = "us1"

        resolved_url = (
            self._base_url
            or self.__class__.base_url.format(dc=dc)
        )

        auth_string = f"anystring:{api_key}"
        token = base64.b64encode(auth_string.encode()).decode()

        headers: dict[str, str] = {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        self._client = httpx.AsyncClient(
            base_url=resolved_url,
            headers=headers,
            timeout=self._timeout,
        )

    async def _teardown(self) -> None:
        """Close the httpx client."""
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
    ) -> httpx.Response:
        """Send an authenticated request to the Mailchimp API.

        Args:
            method: HTTP method (GET, POST, PUT, PATCH, etc.).
            path: API path relative to base_url.
            params: Query parameters.
            json_body: JSON body for POST/PUT/PATCH requests.

        Returns:
            httpx.Response object.

        Raises:
            httpx.HTTPStatusError: On 4xx/5xx responses.
        """
        resp = await self._client.request(
            method, path, params=params, json=json_body,
        )
        resp.raise_for_status()
        return resp

    @staticmethod
    def _subscriber_hash(email: str) -> str:
        """Compute the MD5 hash of a lowercased email for Mailchimp member IDs.

        Args:
            email: Subscriber email address.

        Returns:
            MD5 hex digest of the lowercased email.
        """
        return hashlib.md5(email.lower().encode()).hexdigest()

    def _build_offset_page_state(
        self,
        body: dict[str, Any],
        offset: int,
        count: int,
    ) -> PageState:
        """Build a PageState from Mailchimp offset pagination metadata.

        Args:
            body: Parsed JSON response body.
            offset: Current offset.
            count: Items per page.

        Returns:
            PageState with cursor set to next offset if more items exist.
        """
        total = body.get("total_items", 0)
        next_offset = offset + count
        has_more = next_offset < total
        return PageState(
            has_more=has_more,
            cursor=str(next_offset) if has_more else None,
        )

    # ------------------------------------------------------------------
    # Actions -- Lists (Audiences)
    # ------------------------------------------------------------------

    @action("List Mailchimp audience lists")
    async def list_lists(
        self,
        limit: int = 10,
        offset: int = 0,
    ) -> PaginatedList[MailchimpList]:
        """List audience lists (audiences) with offset pagination.

        Args:
            limit: Maximum number of lists to return (1-1000).
            offset: Offset for pagination.

        Returns:
            Paginated list of MailchimpList objects.
        """
        params: dict[str, Any] = {
            "count": min(limit, 1000),
            "offset": offset,
        }

        resp = await self._request("GET", "/lists", params=params)
        body = resp.json()

        items = [parse_list(lst) for lst in body.get("lists", [])]
        page_state = self._build_offset_page_state(body, offset, limit)

        result = PaginatedList(
            items=items,
            page_state=page_state,
            total_count=body.get("total_items"),
        )
        result._fetch_next = (
            (lambda next_off=offset + limit: self.list_lists(
                limit=limit, offset=next_off,
            ))
            if page_state.has_more else None
        )
        return result

    @action("Get a single Mailchimp audience list by ID")
    async def get_list(self, list_id: str) -> MailchimpList:
        """Retrieve a single audience list.

        Args:
            list_id: The Mailchimp list/audience ID.

        Returns:
            MailchimpList object.
        """
        resp = await self._request("GET", f"/lists/{list_id}")
        return parse_list(resp.json())

    # ------------------------------------------------------------------
    # Actions -- Members (Subscribers)
    # ------------------------------------------------------------------

    @action("List members in a Mailchimp audience list")
    async def list_members(
        self,
        list_id: str,
        status: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
    ) -> PaginatedList[MailchimpMember]:
        """List members (subscribers) in an audience list.

        Args:
            list_id: The Mailchimp list/audience ID.
            status: Filter by status (subscribed, unsubscribed, cleaned, etc.).
            limit: Maximum number of members to return (1-1000).
            offset: Offset for pagination.

        Returns:
            Paginated list of MailchimpMember objects.
        """
        params: dict[str, Any] = {
            "count": min(limit, 1000),
            "offset": offset,
        }
        if status is not None:
            params["status"] = status

        resp = await self._request(
            "GET", f"/lists/{list_id}/members", params=params,
        )
        body = resp.json()

        items = [parse_member(m) for m in body.get("members", [])]
        page_state = self._build_offset_page_state(body, offset, limit)

        result = PaginatedList(
            items=items,
            page_state=page_state,
            total_count=body.get("total_items"),
        )
        result._fetch_next = (
            (lambda next_off=offset + limit: self.list_members(
                list_id=list_id, status=status,
                limit=limit, offset=next_off,
            ))
            if page_state.has_more else None
        )
        return result

    @action("Add a member to a Mailchimp audience list", dangerous=True)
    async def add_member(
        self,
        list_id: str,
        email: str,
        status: Optional[str] = None,
        merge_fields: Optional[dict[str, str]] = None,
    ) -> MailchimpMember:
        """Add a new member (subscriber) to an audience list.

        Args:
            list_id: The Mailchimp list/audience ID.
            email: Email address of the new member.
            status: Subscription status (subscribed, pending, etc.).
                Defaults to ``subscribed``.
            merge_fields: Merge field values (FNAME, LNAME, etc.).

        Returns:
            The created MailchimpMember object.
        """
        member_data: dict[str, Any] = {
            "email_address": email,
            "status": status or "subscribed",
        }
        if merge_fields is not None:
            member_data["merge_fields"] = merge_fields

        resp = await self._request(
            "POST", f"/lists/{list_id}/members",
            json_body=member_data,
        )
        return parse_member(resp.json())

    @action("Update a member in a Mailchimp audience list", dangerous=True)
    async def update_member(
        self,
        list_id: str,
        email: str,
        status: Optional[str] = None,
        merge_fields: Optional[dict[str, str]] = None,
    ) -> MailchimpMember:
        """Update an existing member's information.

        Uses the subscriber hash (MD5 of lowercased email) as the
        member identifier per Mailchimp API requirements.

        Args:
            list_id: The Mailchimp list/audience ID.
            email: Email address of the member to update.
            status: New subscription status.
            merge_fields: Updated merge field values.

        Returns:
            The updated MailchimpMember object.
        """
        subscriber_hash = self._subscriber_hash(email)
        member_data: dict[str, Any] = {}
        if status is not None:
            member_data["status"] = status
        if merge_fields is not None:
            member_data["merge_fields"] = merge_fields

        resp = await self._request(
            "PATCH",
            f"/lists/{list_id}/members/{subscriber_hash}",
            json_body=member_data,
        )
        return parse_member(resp.json())

    # ------------------------------------------------------------------
    # Actions -- Campaigns
    # ------------------------------------------------------------------

    @action("List Mailchimp campaigns")
    async def list_campaigns(
        self,
        status: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
    ) -> PaginatedList[MailchimpCampaign]:
        """List email campaigns with offset pagination.

        Args:
            status: Filter by campaign status (save, paused, schedule,
                sending, sent).
            limit: Maximum number of campaigns to return (1-1000).
            offset: Offset for pagination.

        Returns:
            Paginated list of MailchimpCampaign objects.
        """
        params: dict[str, Any] = {
            "count": min(limit, 1000),
            "offset": offset,
        }
        if status is not None:
            params["status"] = status

        resp = await self._request("GET", "/campaigns", params=params)
        body = resp.json()

        items = [parse_campaign(c) for c in body.get("campaigns", [])]
        page_state = self._build_offset_page_state(body, offset, limit)

        result = PaginatedList(
            items=items,
            page_state=page_state,
            total_count=body.get("total_items"),
        )
        result._fetch_next = (
            (lambda next_off=offset + limit: self.list_campaigns(
                status=status, limit=limit, offset=next_off,
            ))
            if page_state.has_more else None
        )
        return result

    @action("Get a single Mailchimp campaign by ID")
    async def get_campaign(self, campaign_id: str) -> MailchimpCampaign:
        """Retrieve a single campaign by its ID.

        Args:
            campaign_id: The Mailchimp campaign ID.

        Returns:
            MailchimpCampaign object.
        """
        resp = await self._request("GET", f"/campaigns/{campaign_id}")
        return parse_campaign(resp.json())

    @action("Send a Mailchimp campaign", dangerous=True)
    async def send_campaign(self, campaign_id: str) -> dict[str, Any]:
        """Send a campaign immediately.

        This is a destructive action that sends the email campaign
        to all recipients. The campaign must be in a ``ready`` state.

        Args:
            campaign_id: The Mailchimp campaign ID to send.

        Returns:
            Empty dict on success (Mailchimp returns 204 No Content).
        """
        resp = await self._request(
            "POST", f"/campaigns/{campaign_id}/actions/send",
        )
        # Mailchimp returns 204 on success with no body
        if resp.status_code == 204:
            return {"status": "sent", "campaign_id": campaign_id}
        return resp.json()

    # ------------------------------------------------------------------
    # Actions — Member management (extended)
    # ------------------------------------------------------------------

    @action("Delete a member from a list", dangerous=True)
    async def delete_member(
        self, list_id: str, email: str,
    ) -> bool:
        """Permanently delete a member from a list.

        Args:
            list_id: The Mailchimp list/audience ID.
            email: The member's email address.

        Returns:
            True if the member was deleted successfully.
        """
        subscriber_hash = hashlib.md5(
            email.lower().encode()
        ).hexdigest()
        resp = await self._request(
            "DELETE",
            f"/lists/{list_id}/members/{subscriber_hash}/actions/delete-permanent",
        )
        return resp.status_code in (200, 204)

    # ------------------------------------------------------------------
    # Actions — Segments
    # ------------------------------------------------------------------

    @action("List segments for an audience list")
    async def list_segments(
        self, list_id: str,
    ) -> list[MailchimpSegment]:
        """List all saved segments for an audience list.

        Args:
            list_id: The Mailchimp list/audience ID.

        Returns:
            List of MailchimpSegment objects.
        """
        resp = await self._request(
            "GET", f"/lists/{list_id}/segments",
        )
        body = resp.json()
        return [
            MailchimpSegment(
                id=s.get("id", 0),
                name=s.get("name", ""),
                member_count=s.get("member_count", 0),
                type=s.get("type"),
                list_id=s.get("list_id"),
                created_at=s.get("created_at"),
                updated_at=s.get("updated_at"),
            )
            for s in body.get("segments", [])
        ]

    @action("Create a segment for an audience list", dangerous=True)
    async def create_segment(
        self,
        list_id: str,
        name: str,
        conditions: list[dict[str, Any]],
    ) -> MailchimpSegment:
        """Create a new segment for an audience list.

        Args:
            list_id: The Mailchimp list/audience ID.
            name: Segment name.
            conditions: List of condition dicts defining the segment rules.

        Returns:
            The created MailchimpSegment.
        """
        payload: dict[str, Any] = {
            "name": name,
            "options": {
                "match": "all",
                "conditions": conditions,
            },
        }
        resp = await self._request(
            "POST", f"/lists/{list_id}/segments",
            json_body=payload,
        )
        data = resp.json()
        return MailchimpSegment(
            id=data.get("id", 0),
            name=data.get("name", ""),
            member_count=data.get("member_count", 0),
            type=data.get("type"),
            list_id=data.get("list_id"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )

    # ------------------------------------------------------------------
    # Actions — Campaign Reports
    # ------------------------------------------------------------------

    @action("Get a campaign performance report")
    async def get_campaign_report(
        self, campaign_id: str,
    ) -> MailchimpCampaignReport:
        """Get performance report for a sent campaign.

        Args:
            campaign_id: The Mailchimp campaign ID.

        Returns:
            MailchimpCampaignReport with performance metrics.
        """
        resp = await self._request(
            "GET", f"/reports/{campaign_id}",
        )
        data = resp.json()
        return MailchimpCampaignReport(
            id=data.get("id", ""),
            campaign_title=data.get("campaign_title"),
            emails_sent=data.get("emails_sent", 0),
            opens=data.get("opens", {}).get("opens_total", 0),
            unique_opens=data.get("opens", {}).get("unique_opens", 0),
            clicks=data.get("clicks", {}).get("clicks_total", 0),
            subscriber_clicks=data.get("clicks", {}).get("unique_subscriber_clicks", 0),
            unsubscribed=data.get("unsubscribed", 0),
            bounces=data.get("bounces"),
            send_time=data.get("send_time"),
        )

    # ------------------------------------------------------------------
    # Actions -- Member details
    # ------------------------------------------------------------------

    @action("Get a single member from an audience list")
    async def get_member(
        self,
        list_id: str,
        email: str,
    ) -> MailchimpMember:
        """Retrieve a single member by email from an audience list.

        Uses the MD5 hash of the lowercased email as the member
        identifier per Mailchimp API requirements.

        Args:
            list_id: The Mailchimp list/audience ID.
            email: The member's email address.

        Returns:
            MailchimpMember object.
        """
        subscriber_hash = self._subscriber_hash(email)
        resp = await self._request(
            "GET", f"/lists/{list_id}/members/{subscriber_hash}",
        )
        return parse_member(resp.json())

    # ------------------------------------------------------------------
    # Actions -- Campaign management (extended)
    # ------------------------------------------------------------------

    @action("Update an existing campaign")
    async def update_campaign(
        self,
        campaign_id: str,
        settings: dict[str, Any],
    ) -> MailchimpCampaign:
        """Update campaign settings (subject, from_name, etc.).

        Args:
            campaign_id: The Mailchimp campaign ID.
            settings: Dict of campaign settings to update (e.g.
                ``subject_line``, ``from_name``, ``reply_to``).

        Returns:
            The updated MailchimpCampaign.
        """
        payload: dict[str, Any] = {"settings": settings}
        resp = await self._request(
            "PATCH", f"/campaigns/{campaign_id}",
            json_body=payload,
        )
        return parse_campaign(resp.json())

    # ------------------------------------------------------------------
    # Actions -- Automations
    # ------------------------------------------------------------------

    @action("List automations")
    async def list_automations(self) -> list[dict[str, Any]]:
        """List all automations in the Mailchimp account.

        Returns:
            List of automation dicts with id, status, settings, etc.
        """
        resp = await self._request("GET", "/automations")
        body = resp.json()
        return body.get("automations", [])

    # ------------------------------------------------------------------
    # Actions -- List growth history
    # ------------------------------------------------------------------

    @action("Get list growth history")
    async def get_list_growth(
        self, list_id: str,
    ) -> list[dict[str, Any]]:
        """Get growth history (subscriber counts over time) for a list.

        Args:
            list_id: The Mailchimp list/audience ID.

        Returns:
            List of growth history dicts with month, existing,
            imports, opt-ins, etc.
        """
        resp = await self._request(
            "GET", f"/lists/{list_id}/growth-history",
        )
        body = resp.json()
        return body.get("history", [])

    # ------------------------------------------------------------------
    # Actions -- Member tagging
    # ------------------------------------------------------------------

    @action("Add or remove tags on a member", dangerous=True)
    async def tag_member(
        self,
        list_id: str,
        email: str,
        tags: list[dict[str, str]],
    ) -> bool:
        """Add or remove tags on a list member.

        Each tag dict must contain ``name`` (the tag name) and
        ``status`` (``"active"`` to add, ``"inactive"`` to remove).

        Args:
            list_id: The Mailchimp list/audience ID.
            email: The member's email address.
            tags: List of tag dicts, e.g.
                ``[{"name": "VIP", "status": "active"}]``.

        Returns:
            True if the tags were updated.
        """
        subscriber_hash = self._subscriber_hash(email)
        resp = await self._request(
            "POST",
            f"/lists/{list_id}/members/{subscriber_hash}/tags",
            json_body={"tags": tags},
        )
        return resp.status_code in (200, 204)

    @action("List tags for an audience list")
    async def list_tags(
        self,
        list_id: str,
    ) -> list[dict[str, Any]]:
        """Search and list all tags defined on an audience list.

        Uses the ``/lists/{id}/tag-search`` endpoint which returns
        all tags when called without a search term.

        Args:
            list_id: The Mailchimp list/audience ID.

        Returns:
            List of tag dicts with ``id`` and ``name``.
        """
        resp = await self._request(
            "GET", f"/lists/{list_id}/tag-search",
        )
        body = resp.json()
        return body.get("tags", [])

    # ------------------------------------------------------------------
    # Actions -- Campaign content and creation
    # ------------------------------------------------------------------

    @action("Get campaign content")
    async def get_campaign_content(
        self,
        campaign_id: str,
    ) -> dict[str, Any]:
        """Get the HTML, plain-text, and template content of a campaign.

        Args:
            campaign_id: The Mailchimp campaign ID.

        Returns:
            Dict with ``plain_text``, ``html``, ``archive_html``,
            and template content fields.
        """
        resp = await self._request(
            "GET", f"/campaigns/{campaign_id}/content",
        )
        return resp.json()

    @action("Create a new campaign", dangerous=True)
    async def create_campaign(
        self,
        list_id: str,
        subject: str,
        from_name: str,
        reply_to: str,
        type: str = "regular",
    ) -> MailchimpCampaign:
        """Create a new email campaign.

        Creates a campaign with the specified settings. After creation,
        use ``get_campaign_content`` and the Mailchimp API to set the
        content before sending or scheduling.

        Args:
            list_id: The Mailchimp list/audience ID for recipients.
            subject: Email subject line.
            from_name: The ``From`` name displayed to recipients.
            reply_to: The reply-to email address.
            type: Campaign type. One of ``regular``, ``plaintext``,
                ``absplit``, or ``rss``. Defaults to ``regular``.

        Returns:
            The created MailchimpCampaign object.
        """
        payload: dict[str, Any] = {
            "type": type,
            "recipients": {"list_id": list_id},
            "settings": {
                "subject_line": subject,
                "from_name": from_name,
                "reply_to": reply_to,
            },
        }
        resp = await self._request(
            "POST", "/campaigns", json_body=payload,
        )
        return parse_campaign(resp.json())

    @action("Schedule a campaign for sending", dangerous=True)
    async def schedule_campaign(
        self,
        campaign_id: str,
        schedule_time: str,
    ) -> bool:
        """Schedule a campaign for sending at a specific time.

        The campaign must be in a ``ready`` state with content set.
        Once scheduled, it can be unscheduled via the Mailchimp API
        before the send time.

        Args:
            campaign_id: The Mailchimp campaign ID to schedule.
            schedule_time: UTC datetime string in ISO 8601 format
                (e.g. ``"2024-12-25T09:00:00+00:00"``).

        Returns:
            True if the campaign was scheduled.
        """
        resp = await self._request(
            "POST",
            f"/campaigns/{campaign_id}/actions/schedule",
            json_body={"schedule_time": schedule_time},
        )
        return resp.status_code in (200, 204)

    # ------------------------------------------------------------------
    # Actions -- Templates
    # ------------------------------------------------------------------

    @action("List email templates")
    async def list_templates(
        self,
        limit: int = 10,
        offset: int = 0,
    ) -> PaginatedList[MailchimpTemplate]:
        """List available email templates with pagination.

        Args:
            limit: Maximum number of templates to return (1-1000).
            offset: Offset for pagination.

        Returns:
            Paginated list of MailchimpTemplate objects.
        """
        params: dict[str, Any] = {
            "count": min(limit, 1000),
            "offset": offset,
        }
        resp = await self._request("GET", "/templates", params=params)
        body = resp.json()

        items = [
            MailchimpTemplate(
                id=t.get("id", 0),
                name=t.get("name", ""),
                type=t.get("type"),
                category=t.get("category"),
                date_created=t.get("date_created"),
                date_edited=t.get("date_edited"),
                active=t.get("active", False),
                folder_id=t.get("folder_id"),
                thumbnail=t.get("thumbnail"),
            )
            for t in body.get("templates", [])
        ]
        page_state = self._build_offset_page_state(body, offset, limit)

        result = PaginatedList(
            items=items,
            page_state=page_state,
            total_count=body.get("total_items"),
        )
        result._fetch_next = (
            (lambda next_off=offset + limit: self.list_templates(
                limit=limit, offset=next_off,
            ))
            if page_state.has_more else None
        )
        return result

    @action("Get a single email template by ID")
    async def get_template(self, template_id: int) -> MailchimpTemplate:
        """Retrieve a single email template by its numeric ID.

        Args:
            template_id: The Mailchimp template ID (integer).

        Returns:
            MailchimpTemplate object.
        """
        resp = await self._request("GET", f"/templates/{template_id}")
        data = resp.json()
        return MailchimpTemplate(
            id=data.get("id", 0),
            name=data.get("name", ""),
            type=data.get("type"),
            category=data.get("category"),
            date_created=data.get("date_created"),
            date_edited=data.get("date_edited"),
            active=data.get("active", False),
            folder_id=data.get("folder_id"),
            thumbnail=data.get("thumbnail"),
        )
