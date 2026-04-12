"""Microsoft Teams connector -- manage teams, channels, and messages via MS Graph.

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
    Team,
    TeamsChannel,
    TeamsChat,
    TeamsMember,
    TeamsMessage,
    TeamsMessageBody,
    TeamsMessageFrom,
    TeamsPresence,
)

logger = logging.getLogger("toolsconnector.teams")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_team(data: dict[str, Any]) -> Team:
    """Parse an MS Graph team JSON into a Team model.

    Args:
        data: Raw JSON from the teams endpoint.

    Returns:
        Populated Team instance.
    """
    return Team(
        id=data.get("id", ""),
        display_name=data.get("displayName", ""),
        description=data.get("description"),
        visibility=data.get("visibility"),
        web_url=data.get("webUrl"),
        is_archived=data.get("isArchived", False),
    )


def _parse_channel(data: dict[str, Any]) -> TeamsChannel:
    """Parse an MS Graph channel JSON into a TeamsChannel model.

    Args:
        data: Raw JSON from the channels endpoint.

    Returns:
        Populated TeamsChannel instance.
    """
    return TeamsChannel(
        id=data.get("id", ""),
        display_name=data.get("displayName", ""),
        description=data.get("description"),
        membership_type=data.get("membershipType"),
        web_url=data.get("webUrl"),
        email=data.get("email"),
    )


def _parse_message(data: dict[str, Any]) -> TeamsMessage:
    """Parse an MS Graph channelMessage JSON into a TeamsMessage model.

    Args:
        data: Raw JSON from the messages endpoint.

    Returns:
        Populated TeamsMessage instance.
    """
    body_raw = data.get("body", {})
    body = TeamsMessageBody(
        content=body_raw.get("content"),
        content_type=body_raw.get("contentType", "html"),
    ) if body_raw else None

    from_raw = data.get("from", {})
    from_user = None
    if from_raw:
        user_data = from_raw.get("user", {})
        if user_data:
            from_user = TeamsMessageFrom(
                display_name=user_data.get("displayName"),
                user_id=user_data.get("id"),
            )

    return TeamsMessage(
        id=data.get("id", ""),
        body=body,
        from_user=from_user,
        created_datetime=data.get("createdDateTime"),
        last_modified_datetime=data.get("lastModifiedDateTime"),
        subject=data.get("subject"),
        importance=data.get("importance", "normal"),
        web_url=data.get("webUrl"),
        attachments=data.get("attachments", []),
    )


def _parse_member(data: dict[str, Any]) -> TeamsMember:
    """Parse an MS Graph team member JSON into a TeamsMember model.

    Args:
        data: Raw JSON from the members endpoint.

    Returns:
        Populated TeamsMember instance.
    """
    return TeamsMember(
        id=data.get("id", ""),
        display_name=data.get("displayName"),
        user_id=data.get("userId"),
        email=data.get("email"),
        roles=data.get("roles", []),
    )


class Teams(BaseConnector):
    """Connect to Microsoft Teams to manage teams, channels, and messages.

    Requires an OAuth 2.0 access token for Microsoft Graph passed as
    ``credentials``. Uses the MS Graph REST API v1.0 with ``@odata.nextLink``
    pagination.
    """

    name = "teams"
    display_name = "Microsoft Teams"
    category = ConnectorCategory.COMMUNICATION
    protocol = ProtocolType.REST
    base_url = "https://graph.microsoft.com/v1.0"
    description = "Connect to Microsoft Teams to manage teams, channels, and messages via MS Graph."
    _rate_limit_config = RateLimitSpec(rate=600, period=60, burst=50)

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
            path: API path relative to base_url.
            params: URL query parameters.
            json_body: JSON request body.
            full_url: Absolute URL for ``@odata.nextLink`` pagination.

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
                connector="teams",
                action=path,
                retry_after_seconds=retry_after,
            )
        if response.status_code == 404:
            raise NotFoundError(
                f"Resource not found: {path}",
                connector="teams",
                action=path,
            )
        if response.status_code >= 400:
            detail = response.text[:500]
            raise APIError(
                f"MS Graph error {response.status_code}: {detail}",
                connector="teams",
                action=path,
                details={"status_code": response.status_code},
            )

        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    @action("List teams the user has joined")
    async def list_teams(self) -> list[Team]:
        """List all teams the authenticated user is a member of.

        Returns:
            List of Team objects.
        """
        data = await self._request("GET", "/me/joinedTeams")
        return [_parse_team(t) for t in data.get("value", [])]

    @action("Get a single team by ID")
    async def get_team(self, team_id: str) -> Team:
        """Retrieve details for a single team.

        Args:
            team_id: The unique ID of the team.

        Returns:
            The requested Team object.
        """
        data = await self._request("GET", f"/teams/{team_id}")
        return _parse_team(data)

    @action("List channels in a team")
    async def list_channels(self, team_id: str) -> list[TeamsChannel]:
        """List all channels in a team.

        Args:
            team_id: The unique ID of the team.

        Returns:
            List of TeamsChannel objects.
        """
        data = await self._request("GET", f"/teams/{team_id}/channels")
        return [_parse_channel(ch) for ch in data.get("value", [])]

    @action("Send a message to a Teams channel", dangerous=True)
    async def send_message(
        self,
        team_id: str,
        channel_id: str,
        content: str,
    ) -> TeamsMessage:
        """Send a message to a channel in a team.

        Args:
            team_id: The unique ID of the team.
            channel_id: The unique ID of the channel.
            content: Message content (HTML supported).

        Returns:
            The sent TeamsMessage object.
        """
        payload: dict[str, Any] = {
            "body": {
                "contentType": "html",
                "content": content,
            },
        }
        data = await self._request(
            "POST",
            f"/teams/{team_id}/channels/{channel_id}/messages",
            json_body=payload,
        )
        return _parse_message(data)

    @action("List messages in a Teams channel")
    async def list_messages(
        self,
        team_id: str,
        channel_id: str,
        limit: int = 50,
        page_url: Optional[str] = None,
    ) -> PaginatedList[TeamsMessage]:
        """List messages in a channel.

        Args:
            team_id: The unique ID of the team.
            channel_id: The unique ID of the channel.
            limit: Maximum number of messages per page (max 50).
            page_url: Full ``@odata.nextLink`` URL for the next page.

        Returns:
            Paginated list of TeamsMessage objects.
        """
        if page_url:
            data = await self._request("GET", "", full_url=page_url)
        else:
            params: dict[str, Any] = {"$top": min(limit, 50)}
            data = await self._request(
                "GET",
                f"/teams/{team_id}/channels/{channel_id}/messages",
                params=params,
            )

        messages = [_parse_message(m) for m in data.get("value", [])]
        next_link = data.get("@odata.nextLink")

        return PaginatedList(
            items=messages,
            page_state=PageState(
                cursor=next_link,
                has_more=next_link is not None,
            ),
        )

    @action("List members of a team")
    async def list_members(self, team_id: str) -> list[TeamsMember]:
        """List all members of a team.

        Args:
            team_id: The unique ID of the team.

        Returns:
            List of TeamsMember objects.
        """
        data = await self._request("GET", f"/teams/{team_id}/members")
        return [_parse_member(m) for m in data.get("value", [])]

    @action("Create a new channel in a team")
    async def create_channel(
        self,
        team_id: str,
        name: str,
        description: Optional[str] = None,
    ) -> TeamsChannel:
        """Create a new channel in a team.

        Args:
            team_id: The unique ID of the team.
            name: Display name for the new channel.
            description: Optional description for the channel.

        Returns:
            The created TeamsChannel object.
        """
        payload: dict[str, Any] = {
            "displayName": name,
            "membershipType": "standard",
        }
        if description:
            payload["description"] = description

        data = await self._request(
            "POST",
            f"/teams/{team_id}/channels",
            json_body=payload,
        )
        return _parse_channel(data)

    @action("Get a single channel by ID")
    async def get_channel(
        self,
        team_id: str,
        channel_id: str,
    ) -> TeamsChannel:
        """Retrieve details for a single channel.

        Args:
            team_id: The unique ID of the team.
            channel_id: The unique ID of the channel.

        Returns:
            The requested TeamsChannel object.
        """
        data = await self._request(
            "GET",
            f"/teams/{team_id}/channels/{channel_id}",
        )
        return _parse_channel(data)

    # ------------------------------------------------------------------
    # Actions — Replies
    # ------------------------------------------------------------------

    @action("Reply to a message in a Teams channel", dangerous=True)
    async def reply_to_message(
        self,
        team_id: str,
        channel_id: str,
        message_id: str,
        content: str,
    ) -> TeamsMessage:
        """Reply to an existing message in a channel.

        Args:
            team_id: The unique ID of the team.
            channel_id: The unique ID of the channel.
            message_id: The ID of the message to reply to.
            content: Reply content (HTML supported).

        Returns:
            The created reply TeamsMessage object.
        """
        payload: dict[str, Any] = {
            "body": {
                "contentType": "html",
                "content": content,
            },
        }
        data = await self._request(
            "POST",
            f"/teams/{team_id}/channels/{channel_id}/messages/{message_id}/replies",
            json_body=payload,
        )
        return _parse_message(data)

    # ------------------------------------------------------------------
    # Actions — Chats
    # ------------------------------------------------------------------

    @action("List chats the user is part of")
    async def list_chats(
        self, limit: Optional[int] = None,
    ) -> list[TeamsChat]:
        """List all chats the authenticated user participates in.

        Args:
            limit: Maximum number of chats to return.

        Returns:
            List of TeamsChat objects.
        """
        params: dict[str, Any] = {}
        if limit is not None:
            params["$top"] = min(limit, 50)
        data = await self._request("GET", "/me/chats", params=params or None)
        return [
            TeamsChat(
                id=c.get("id", ""),
                topic=c.get("topic"),
                chat_type=c.get("chatType"),
                created_datetime=c.get("createdDateTime"),
                last_updated_datetime=c.get("lastUpdatedDateTime"),
                web_url=c.get("webUrl"),
            )
            for c in data.get("value", [])
        ]

    @action("Send a message to a Teams chat", dangerous=True)
    async def send_chat_message(
        self, chat_id: str, content: str,
    ) -> TeamsMessage:
        """Send a message to a 1:1 or group chat.

        Args:
            chat_id: The unique ID of the chat.
            content: Message content (HTML supported).

        Returns:
            The sent TeamsMessage object.
        """
        payload: dict[str, Any] = {
            "body": {
                "contentType": "html",
                "content": content,
            },
        }
        data = await self._request(
            "POST", f"/chats/{chat_id}/messages", json_body=payload,
        )
        return _parse_message(data)

    # ------------------------------------------------------------------
    # Actions — Presence
    # ------------------------------------------------------------------

    @action("Get a user's presence status in Teams")
    async def get_user_presence(self, user_id: str) -> TeamsPresence:
        """Get a user's current presence/availability status.

        Args:
            user_id: The unique ID of the user.

        Returns:
            TeamsPresence with availability and activity info.
        """
        data = await self._request(
            "GET", f"/users/{user_id}/presence",
        )
        return TeamsPresence(
            id=data.get("id"),
            availability=data.get("availability"),
            activity=data.get("activity"),
        )

    # ------------------------------------------------------------------
    # Actions -- Chat messages
    # ------------------------------------------------------------------

    @action("List messages in a Teams chat")
    async def list_chat_messages(
        self,
        chat_id: str,
        limit: int = 50,
        page_url: Optional[str] = None,
    ) -> PaginatedList[TeamsMessage]:
        """List messages in a 1:1 or group chat.

        Args:
            chat_id: The unique ID of the chat.
            limit: Maximum number of messages per page (max 50).
            page_url: Full ``@odata.nextLink`` URL for the next page.

        Returns:
            Paginated list of TeamsMessage objects.
        """
        if page_url:
            data = await self._request("GET", "", full_url=page_url)
        else:
            params: dict[str, Any] = {"$top": min(limit, 50)}
            data = await self._request(
                "GET",
                f"/chats/{chat_id}/messages",
                params=params,
            )

        messages = [_parse_message(m) for m in data.get("value", [])]
        next_link = data.get("@odata.nextLink")

        return PaginatedList(
            items=messages,
            page_state=PageState(
                cursor=next_link,
                has_more=next_link is not None,
            ),
        )

    # ------------------------------------------------------------------
    # Actions -- Channel management
    # ------------------------------------------------------------------

    @action("Update a channel in a team")
    async def update_channel(
        self,
        team_id: str,
        channel_id: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> TeamsChannel:
        """Update the display name or description of a channel.

        Args:
            team_id: The unique ID of the team.
            channel_id: The unique ID of the channel.
            display_name: New display name for the channel.
            description: New description for the channel.

        Returns:
            The updated TeamsChannel object.
        """
        payload: dict[str, Any] = {}
        if display_name is not None:
            payload["displayName"] = display_name
        if description is not None:
            payload["description"] = description

        data = await self._request(
            "PATCH",
            f"/teams/{team_id}/channels/{channel_id}",
            json_body=payload,
        )
        return _parse_channel(data)

    @action("Delete a channel from a team", dangerous=True)
    async def delete_channel(
        self,
        team_id: str,
        channel_id: str,
    ) -> None:
        """Delete a channel from a team.

        Only standard channels can be deleted; the General channel cannot
        be removed.

        Args:
            team_id: The unique ID of the team.
            channel_id: The unique ID of the channel to delete.

        Warning:
            This permanently deletes the channel and all its messages.
        """
        await self._request(
            "DELETE",
            f"/teams/{team_id}/channels/{channel_id}",
        )

    # ------------------------------------------------------------------
    # Actions -- Member management
    # ------------------------------------------------------------------

    @action("Add a member to a team", dangerous=True)
    async def add_member(
        self,
        team_id: str,
        user_id: str,
        roles: Optional[list[str]] = None,
    ) -> TeamsMember:
        """Add a user as a member of a team.

        Args:
            team_id: The unique ID of the team.
            user_id: The Azure AD object ID of the user to add.
            roles: Optional list of roles to assign (e.g.
                ``["owner"]``). Defaults to member if omitted.

        Returns:
            The created TeamsMember object.
        """
        payload: dict[str, Any] = {
            "@odata.type": "#microsoft.graph.aadUserConversationMember",
            "roles": roles or [],
            "user@odata.bind": (
                f"https://graph.microsoft.com/v1.0/users('{user_id}')"
            ),
        }
        data = await self._request(
            "POST",
            f"/teams/{team_id}/members",
            json_body=payload,
        )
        return _parse_member(data)

    @action("Remove a member from a team", dangerous=True)
    async def remove_member(
        self,
        team_id: str,
        member_id: str,
    ) -> None:
        """Remove a member from a team.

        Args:
            team_id: The unique ID of the team.
            member_id: The membership ID of the member to remove
                (this is the conversation member ID, not the user ID).

        Warning:
            The member will immediately lose access to the team and
            all its channels.
        """
        await self._request(
            "DELETE",
            f"/teams/{team_id}/members/{member_id}",
        )
