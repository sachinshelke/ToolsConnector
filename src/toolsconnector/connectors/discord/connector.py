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

from .types import DiscordChannel, DiscordMessage, DiscordUser, Embed, GuildMember

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
