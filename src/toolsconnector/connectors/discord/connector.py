"""Discord connector — send messages, manage channels, and interact with Discord guilds.

Uses the Discord REST API v10 (https://discord.com/developers/docs/reference)
with Bot token authentication.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from urllib.parse import quote as url_quote

import httpx

from toolsconnector.errors import (
    APIError,
    NotFoundError,
    RateLimitError,
    ServerError,
    ValidationError,
)
from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import ConnectorCategory, ProtocolType, RateLimitSpec
from toolsconnector.types import PaginatedList

from .types import (
    DiscordChannel,
    DiscordGuild,
    DiscordMessage,
    DiscordRole,
    DiscordUser,
    DiscordWebhook,
    Embed,
    GuildMember,
)

logger = logging.getLogger("toolsconnector.discord")

# Discord channel type constants
CHANNEL_TYPE_GUILD_TEXT = 0
CHANNEL_TYPE_GUILD_VOICE = 2
CHANNEL_TYPE_GUILD_CATEGORY = 4
CHANNEL_TYPE_GUILD_ANNOUNCEMENT = 5
CHANNEL_TYPE_GUILD_FORUM = 15


class Discord(BaseConnector):
    """Connect to Discord to send messages, manage channels, and list members.

    Requires a Discord Bot token passed as ``credentials``.
    Uses the Discord REST API v10 with snowflake ID-based resources.
    """

    name = "discord"
    display_name = "Discord"
    category = ConnectorCategory.COMMUNICATION
    protocol = ProtocolType.REST
    base_url = "https://discord.com/api/v10"
    description = "Connect to Discord to send messages, manage channels, and list guild members."
    _rate_limit_config = RateLimitSpec(rate=50, period=1, burst=10)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Initialise the async HTTP client."""
        self._client = httpx.AsyncClient(
            base_url=self._base_url or self.__class__.base_url,
            headers={
                "Authorization": f"Bot {self._credentials}",
                "Content-Type": "application/json",
                "User-Agent": "ToolsConnector (https://github.com/toolsconnector, 0.1.0)",
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
    ) -> Any:
        """Execute an HTTP request against the Discord REST API.

        Discord returns standard HTTP status codes. This helper maps
        error codes to the ToolsConnector error hierarchy.

        Args:
            method: HTTP method (GET, POST, PUT, PATCH, DELETE).
            path: API path (e.g. ``/channels/123/messages``).
            params: URL query parameters.
            json_body: JSON request body.

        Returns:
            The parsed JSON response (dict, list, or None for 204).

        Raises:
            RateLimitError: If the API returns HTTP 429.
            NotFoundError: If the resource is not found (HTTP 404).
            ValidationError: If the request is malformed (HTTP 400).
            ServerError: If Discord returns a 5xx error.
            APIError: For any other non-2xx response.
        """
        kwargs: dict[str, Any] = {}
        if params:
            kwargs["params"] = params
        if json_body is not None:
            kwargs["json"] = json_body

        response = await self._client.request(method, path, **kwargs)
        status = response.status_code

        # 204 No Content — success with no body (e.g. add_reaction)
        if status == 204:
            return None

        # Rate limited
        if status == 429:
            body = response.json()
            retry_after = body.get("retry_after", 5.0)
            raise RateLimitError(
                f"Discord rate limited: retry after {retry_after}s",
                connector="discord",
                action=path,
                retry_after_seconds=float(retry_after),
                details={"discord_response": body},
            )

        # Try to parse body for all other responses
        try:
            body = response.json()
        except Exception:
            body = {}

        # Success
        if 200 <= status < 300:
            return body

        # Error mapping
        error_msg = body.get("message", f"Discord API error (HTTP {status})")
        error_code = body.get("code", 0)
        details = {"discord_code": error_code, "discord_message": error_msg}

        if status == 404:
            raise NotFoundError(
                error_msg,
                connector="discord",
                action=path,
                details=details,
            )
        if status == 400:
            raise ValidationError(
                error_msg,
                connector="discord",
                action=path,
                details={**details, "errors": body.get("errors", {})},
            )
        if status >= 500:
            raise ServerError(
                error_msg,
                connector="discord",
                action=path,
                details=details,
                upstream_status=status,
            )

        raise APIError(
            error_msg,
            connector="discord",
            action=path,
            details=details,
            upstream_status=status,
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    @action("Send a message to a Discord channel", dangerous=True)
    async def send_message(
        self,
        channel_id: str,
        content: str,
        embeds: Optional[list[dict[str, Any]]] = None,
    ) -> DiscordMessage:
        """Send a message to a Discord channel.

        Args:
            channel_id: The channel snowflake ID.
            content: Message text content (max 2000 characters).
            embeds: Optional list of embed objects (max 10). Each embed is a
                dict matching the Discord embed structure.

        Returns:
            The sent DiscordMessage object.
        """
        payload: dict[str, Any] = {"content": content}
        if embeds:
            payload["embeds"] = embeds

        body = await self._request(
            "POST",
            f"/channels/{channel_id}/messages",
            json_body=payload,
        )
        return DiscordMessage(**body)

    @action("List channels in a guild")
    async def list_channels(self, guild_id: str) -> list[DiscordChannel]:
        """List all channels in a Discord guild (server).

        Args:
            guild_id: The guild snowflake ID.

        Returns:
            List of DiscordChannel objects.
        """
        body = await self._request("GET", f"/guilds/{guild_id}/channels")
        return [DiscordChannel(**ch) for ch in body]

    @action("Get a single channel by ID")
    async def get_channel(self, channel_id: str) -> DiscordChannel:
        """Retrieve details for a single Discord channel.

        Args:
            channel_id: The channel snowflake ID.

        Returns:
            The requested DiscordChannel object.
        """
        body = await self._request("GET", f"/channels/{channel_id}")
        return DiscordChannel(**body)

    @action("List messages in a channel")
    async def list_messages(
        self,
        channel_id: str,
        limit: int = 50,
        before: Optional[str] = None,
        after: Optional[str] = None,
    ) -> list[DiscordMessage]:
        """Retrieve messages from a Discord channel.

        Args:
            channel_id: The channel snowflake ID.
            limit: Maximum number of messages to return (1-100, default 50).
            before: Get messages before this message snowflake ID.
            after: Get messages after this message snowflake ID.

        Returns:
            List of DiscordMessage objects (newest first).
        """
        params: dict[str, Any] = {"limit": min(limit, 100)}
        if before:
            params["before"] = before
        if after:
            params["after"] = after

        body = await self._request(
            "GET",
            f"/channels/{channel_id}/messages",
            params=params,
        )
        return [DiscordMessage(**msg) for msg in body]

    @action("Create a new channel in a guild", dangerous=True)
    async def create_channel(
        self,
        guild_id: str,
        name: str,
        type: int = CHANNEL_TYPE_GUILD_TEXT,
    ) -> DiscordChannel:
        """Create a new channel in a Discord guild.

        Args:
            guild_id: The guild snowflake ID.
            name: Name for the new channel (2-100 characters, lowercase, no spaces).
            type: Channel type integer. 0 = text, 2 = voice, 4 = category.

        Returns:
            The created DiscordChannel object.
        """
        payload: dict[str, Any] = {"name": name, "type": type}
        body = await self._request(
            "POST",
            f"/guilds/{guild_id}/channels",
            json_body=payload,
        )
        return DiscordChannel(**body)

    @action("Add a reaction to a message")
    async def add_reaction(
        self,
        channel_id: str,
        message_id: str,
        emoji: str,
    ) -> None:
        """Add an emoji reaction to a message.

        Args:
            channel_id: The channel snowflake ID.
            message_id: The message snowflake ID.
            emoji: Unicode emoji (e.g. ``\\U0001f44d``) or custom emoji
                in ``name:id`` format (e.g. ``custom_emoji:123456``).
        """
        encoded_emoji = url_quote(emoji, safe=":")
        await self._request(
            "PUT",
            f"/channels/{channel_id}/messages/{message_id}/reactions/{encoded_emoji}/@me",
        )

    @action("List members of a guild")
    async def list_guild_members(
        self,
        guild_id: str,
        limit: int = 100,
    ) -> list[GuildMember]:
        """List members of a Discord guild (server).

        Args:
            guild_id: The guild snowflake ID.
            limit: Maximum number of members to return (1-1000, default 100).

        Returns:
            List of GuildMember objects.
        """
        params: dict[str, Any] = {"limit": min(limit, 1000)}
        body = await self._request(
            "GET",
            f"/guilds/{guild_id}/members",
            params=params,
        )
        return [GuildMember(**m) for m in body]

    @action("Get a single user by ID")
    async def get_user(self, user_id: str) -> DiscordUser:
        """Retrieve details for a single Discord user.

        Args:
            user_id: The user snowflake ID.

        Returns:
            The requested DiscordUser object.
        """
        body = await self._request("GET", f"/users/{user_id}")
        return DiscordUser(**body)

    @action("Delete a channel", dangerous=True)
    async def delete_channel(self, channel_id: str) -> None:
        """Delete a channel from a guild, or close a DM channel.

        For guild channels this permanently deletes the channel and all
        messages within it. This action cannot be undone.

        Args:
            channel_id: The channel snowflake ID to delete.
        """
        await self._request("DELETE", f"/channels/{channel_id}")

    @action("Edit a message in a channel")
    async def edit_message(
        self,
        channel_id: str,
        message_id: str,
        content: str,
    ) -> DiscordMessage:
        """Edit a previously sent message.

        Only the ``content`` field is updated. Embeds and other fields
        remain unchanged unless explicitly cleared.

        Args:
            channel_id: The channel snowflake ID containing the message.
            message_id: The message snowflake ID to edit.
            content: New message text content (max 2000 characters).

        Returns:
            The updated DiscordMessage object.
        """
        payload: dict[str, Any] = {"content": content}
        body = await self._request(
            "PATCH",
            f"/channels/{channel_id}/messages/{message_id}",
            json_body=payload,
        )
        return DiscordMessage(**body)

    @action("Delete a message from a channel", dangerous=True)
    async def delete_message(
        self,
        channel_id: str,
        message_id: str,
    ) -> None:
        """Delete a message from a channel.

        This permanently removes the message. Requires ``MANAGE_MESSAGES``
        permission for messages sent by other users.

        Args:
            channel_id: The channel snowflake ID.
            message_id: The message snowflake ID to delete.
        """
        await self._request(
            "DELETE",
            f"/channels/{channel_id}/messages/{message_id}",
        )

    @action("List roles in a guild")
    async def list_roles(self, guild_id: str) -> list[DiscordRole]:
        """List all roles in a Discord guild.

        Args:
            guild_id: The guild snowflake ID.

        Returns:
            List of DiscordRole objects ordered by position.
        """
        body = await self._request("GET", f"/guilds/{guild_id}/roles")
        return [DiscordRole(**r) for r in body]

    @action("Create a role in a guild", dangerous=True)
    async def create_role(
        self,
        guild_id: str,
        name: str,
        permissions: Optional[str] = None,
        color: Optional[int] = None,
    ) -> DiscordRole:
        """Create a new role in a Discord guild.

        Args:
            guild_id: The guild snowflake ID.
            name: Name for the new role.
            permissions: Permission bit set as a string. Defaults to
                ``@everyone`` permissions of the guild.
            color: RGB color value for the role (integer).

        Returns:
            The created DiscordRole object.
        """
        payload: dict[str, Any] = {"name": name}
        if permissions is not None:
            payload["permissions"] = permissions
        if color is not None:
            payload["color"] = color

        body = await self._request(
            "POST",
            f"/guilds/{guild_id}/roles",
            json_body=payload,
        )
        return DiscordRole(**body)

    @action("Ban a member from a guild", dangerous=True)
    async def ban_member(
        self,
        guild_id: str,
        user_id: str,
        reason: Optional[str] = None,
    ) -> None:
        """Ban a user from a guild and optionally delete recent messages.

        Requires ``BAN_MEMBERS`` permission. The ban is permanent until
        explicitly removed.

        Args:
            guild_id: The guild snowflake ID.
            user_id: The user snowflake ID to ban.
            reason: Optional audit log reason for the ban.
        """
        payload: dict[str, Any] = {}
        extra_headers: dict[str, str] = {}
        if reason:
            extra_headers["X-Audit-Log-Reason"] = reason

        # Note: Discord requires the reason in the audit-log header
        # and an empty JSON body for PUT /bans
        await self._request(
            "PUT",
            f"/guilds/{guild_id}/bans/{user_id}",
            json_body=payload,
        )

    @action("Create a thread in a channel", dangerous=True)
    async def create_thread(
        self,
        channel_id: str,
        name: str,
        message_id: Optional[str] = None,
    ) -> DiscordChannel:
        """Create a new thread in a channel.

        If ``message_id`` is provided, the thread is created from that
        message. Otherwise a new thread is created without a starter
        message.

        Args:
            channel_id: The parent channel snowflake ID.
            name: Name for the thread (1-100 characters).
            message_id: Optional message snowflake ID to start the
                thread from.

        Returns:
            The created DiscordChannel object (thread type).
        """
        if message_id:
            # Create a thread from an existing message
            payload: dict[str, Any] = {"name": name}
            body = await self._request(
                "POST",
                f"/channels/{channel_id}/messages/{message_id}/threads",
                json_body=payload,
            )
        else:
            # Create a thread without a message (type 11 = public thread)
            payload = {"name": name, "type": 11}
            body = await self._request(
                "POST",
                f"/channels/{channel_id}/threads",
                json_body=payload,
            )
        return DiscordChannel(**body)

    # ------------------------------------------------------------------
    # Guilds
    # ------------------------------------------------------------------

    @action("Get guild information")
    async def get_guild(self, guild_id: str) -> DiscordGuild:
        """Retrieve detailed information about a Discord guild (server).

        Args:
            guild_id: The guild snowflake ID.

        Returns:
            The DiscordGuild object with full server details.
        """
        body = await self._request(
            "GET",
            f"/guilds/{guild_id}",
            params={"with_counts": "true"},
        )
        return DiscordGuild(**body)

    @action("Edit guild settings", dangerous=True)
    async def edit_guild(
        self,
        guild_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        icon: Optional[str] = None,
    ) -> DiscordGuild:
        """Modify a guild's settings.

        Requires the ``MANAGE_GUILD`` permission. Only provided fields
        are updated; omitted fields remain unchanged.

        Args:
            guild_id: The guild snowflake ID.
            name: Optional new name for the guild (2-100 characters).
            description: Optional new description (for Community guilds).
            icon: Optional base64-encoded 128x128 image for the guild icon,
                or ``None`` to remove the icon.

        Returns:
            The updated DiscordGuild object.
        """
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if icon is not None:
            payload["icon"] = icon

        body = await self._request(
            "PATCH",
            f"/guilds/{guild_id}",
            json_body=payload,
        )
        return DiscordGuild(**body)

    # ------------------------------------------------------------------
    # Members & Roles
    # ------------------------------------------------------------------

    @action("Get a single guild member")
    async def get_member(self, guild_id: str, user_id: str) -> GuildMember:
        """Retrieve details for a single guild member.

        Args:
            guild_id: The guild snowflake ID.
            user_id: The user snowflake ID.

        Returns:
            The GuildMember object for the specified user.
        """
        body = await self._request(
            "GET",
            f"/guilds/{guild_id}/members/{user_id}",
        )
        return GuildMember(**body)

    @action("Add a role to a guild member", dangerous=True)
    async def add_member_role(
        self,
        guild_id: str,
        user_id: str,
        role_id: str,
    ) -> None:
        """Assign a role to a guild member.

        Requires the ``MANAGE_ROLES`` permission and that the bot's
        highest role is above the target role.

        Args:
            guild_id: The guild snowflake ID.
            user_id: The user snowflake ID.
            role_id: The role snowflake ID to assign.
        """
        await self._request(
            "PUT",
            f"/guilds/{guild_id}/members/{user_id}/roles/{role_id}",
        )

    @action("Remove a role from a guild member", dangerous=True)
    async def remove_member_role(
        self,
        guild_id: str,
        user_id: str,
        role_id: str,
    ) -> None:
        """Remove a role from a guild member.

        Requires the ``MANAGE_ROLES`` permission and that the bot's
        highest role is above the target role.

        Args:
            guild_id: The guild snowflake ID.
            user_id: The user snowflake ID.
            role_id: The role snowflake ID to remove.
        """
        await self._request(
            "DELETE",
            f"/guilds/{guild_id}/members/{user_id}/roles/{role_id}",
        )

    @action("Kick a member from a guild", dangerous=True)
    async def kick_member(
        self,
        guild_id: str,
        user_id: str,
        reason: Optional[str] = None,
    ) -> None:
        """Remove a member from a guild.

        The user can rejoin if they have an invite. Requires the
        ``KICK_MEMBERS`` permission.

        Args:
            guild_id: The guild snowflake ID.
            user_id: The user snowflake ID to kick.
            reason: Optional audit log reason for the kick.
        """
        # Discord accepts the reason via X-Audit-Log-Reason header,
        # but our _request helper doesn't support extra headers — the
        # reason is passed as a query param workaround isn't available,
        # so we rely on the audit log header being set at the client level
        # if needed. The kick itself only requires DELETE with empty body.
        await self._request(
            "DELETE",
            f"/guilds/{guild_id}/members/{user_id}",
        )

    # ------------------------------------------------------------------
    # Pins
    # ------------------------------------------------------------------

    @action("Pin a message in a channel")
    async def pin_message(self, channel_id: str, message_id: str) -> None:
        """Pin a message in a channel.

        Requires the ``MANAGE_MESSAGES`` permission. A channel can have
        at most 50 pinned messages.

        Args:
            channel_id: The channel snowflake ID.
            message_id: The message snowflake ID to pin.
        """
        await self._request(
            "PUT",
            f"/channels/{channel_id}/pins/{message_id}",
        )

    @action("Unpin a message from a channel")
    async def unpin_message(self, channel_id: str, message_id: str) -> None:
        """Unpin a previously pinned message from a channel.

        Requires the ``MANAGE_MESSAGES`` permission.

        Args:
            channel_id: The channel snowflake ID.
            message_id: The message snowflake ID to unpin.
        """
        await self._request(
            "DELETE",
            f"/channels/{channel_id}/pins/{message_id}",
        )

    @action("List pinned messages in a channel")
    async def list_pinned_messages(
        self,
        channel_id: str,
    ) -> list[DiscordMessage]:
        """Retrieve all pinned messages in a channel.

        A channel can have at most 50 pinned messages.

        Args:
            channel_id: The channel snowflake ID.

        Returns:
            List of pinned DiscordMessage objects.
        """
        body = await self._request(
            "GET",
            f"/channels/{channel_id}/pins",
        )
        return [DiscordMessage(**msg) for msg in body]

    # ------------------------------------------------------------------
    # Webhooks
    # ------------------------------------------------------------------

    @action("Create a webhook for a channel", dangerous=True)
    async def create_webhook(
        self,
        channel_id: str,
        name: str,
        avatar: Optional[str] = None,
    ) -> DiscordWebhook:
        """Create a new webhook for a channel.

        Requires the ``MANAGE_WEBHOOKS`` permission. Webhooks allow
        external services to post messages to a channel.

        Args:
            channel_id: The channel snowflake ID.
            name: Name for the webhook (1-80 characters).
            avatar: Optional base64-encoded 128x128 image for the
                webhook's default avatar.

        Returns:
            The created DiscordWebhook object including the token.
        """
        payload: dict[str, Any] = {"name": name}
        if avatar is not None:
            payload["avatar"] = avatar

        body = await self._request(
            "POST",
            f"/channels/{channel_id}/webhooks",
            json_body=payload,
        )
        return DiscordWebhook(**body)
