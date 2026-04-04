"""Slack connector — send messages, manage channels, and interact with Slack workspaces.

Uses the Slack Web API (https://api.slack.com/methods) with Bot token authentication.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from toolsconnector.errors import APIError, NotFoundError, RateLimitError
from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import ConnectorCategory, ProtocolType, RateLimitSpec
from toolsconnector.types import PageState, PaginatedList

from .types import Channel, Message, SlackFile, SlackUser

logger = logging.getLogger("toolsconnector.slack")


class Slack(BaseConnector):
    """Connect to Slack to send messages, manage channels, and list users.

    Requires a Slack Bot token (xoxb-...) passed as ``credentials``.
    Uses the Slack Web API with cursor-based pagination.
    """

    name = "slack"
    display_name = "Slack"
    category = ConnectorCategory.COMMUNICATION
    protocol = ProtocolType.REST
    base_url = "https://slack.com/api"
    description = "Connect to Slack to send messages, manage channels, and list users."
    _rate_limit_config = RateLimitSpec(rate=1, period=1, burst=5)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Initialise the async HTTP client."""
        self._client = httpx.AsyncClient(
            base_url=self._base_url or self.__class__.base_url,
            headers={
                "Authorization": f"Bearer {self._credentials}",
                "Content-Type": "application/json; charset=utf-8",
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
        endpoint: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[dict[str, Any]] = None,
        data: Optional[dict[str, Any]] = None,
        files: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Execute an HTTP request against the Slack Web API.

        Slack always returns HTTP 200 with ``{"ok": true/false}`` in the body.
        This helper raises structured errors when ``ok`` is ``false``.

        Args:
            method: HTTP method (GET or POST).
            endpoint: Slack API method name (e.g. ``chat.postMessage``).
            params: URL query parameters.
            json_body: JSON request body (mutually exclusive with data/files).
            data: Form-encoded body (used with file uploads).
            files: Multipart file payload.

        Returns:
            The parsed JSON response dict (with ``ok`` removed).

        Raises:
            RateLimitError: If the API returns ``ratelimited``.
            NotFoundError: If the target resource is not found.
            APIError: For any other Slack API error.
        """
        kwargs: dict[str, Any] = {}
        if params:
            kwargs["params"] = params
        if json_body:
            kwargs["json"] = json_body
        if data:
            kwargs["data"] = data
        if files:
            kwargs["files"] = files
            # Remove JSON content-type for multipart uploads
            kwargs["headers"] = {
                "Authorization": f"Bearer {self._credentials}",
            }

        response = await self._client.request(method, f"/{endpoint}", **kwargs)
        body = response.json()

        if not body.get("ok", False):
            error_code = body.get("error", "unknown_error")
            error_msg = f"Slack API error: {error_code}"

            if error_code == "ratelimited":
                retry_after = float(response.headers.get("Retry-After", "30"))
                raise RateLimitError(
                    error_msg,
                    connector="slack",
                    action=endpoint,
                    retry_after_seconds=retry_after,
                    details={"slack_error": error_code},
                )
            if error_code in ("channel_not_found", "user_not_found", "file_not_found"):
                raise NotFoundError(
                    error_msg,
                    connector="slack",
                    action=endpoint,
                    details={"slack_error": error_code},
                )
            raise APIError(
                error_msg,
                connector="slack",
                action=endpoint,
                details={"slack_error": error_code, "response": body},
            )

        return body

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    @action("Send a message to a Slack channel or thread", dangerous=True)
    async def send_message(
        self,
        channel: str,
        text: str,
        thread_ts: Optional[str] = None,
    ) -> Message:
        """Send a message to a Slack channel.

        Args:
            channel: Channel ID (e.g. ``C01234ABCDE``) or name.
            text: Message text (supports Slack mrkdwn formatting).
            thread_ts: Optional parent message timestamp to reply in a thread.

        Returns:
            The sent Message object.
        """
        payload: dict[str, Any] = {"channel": channel, "text": text}
        if thread_ts:
            payload["thread_ts"] = thread_ts

        body = await self._request("POST", "chat.postMessage", json_body=payload)
        msg_data = body.get("message", {})
        msg_data["channel"] = body.get("channel", channel)
        return Message(**msg_data)

    @action("List channels in the workspace")
    async def list_channels(
        self,
        limit: int = 100,
        cursor: Optional[str] = None,
    ) -> PaginatedList[Channel]:
        """List public and private channels the bot has access to.

        Args:
            limit: Maximum number of channels to return (max 1000).
            cursor: Pagination cursor from a previous response.

        Returns:
            Paginated list of Channel objects.
        """
        params: dict[str, Any] = {
            "types": "public_channel,private_channel",
            "limit": min(limit, 1000),
            "exclude_archived": "false",
        }
        if cursor:
            params["cursor"] = cursor

        body = await self._request("GET", "conversations.list", params=params)

        channels = [Channel(**ch) for ch in body.get("channels", [])]
        next_cursor = body.get("response_metadata", {}).get("next_cursor", "")
        has_more = bool(next_cursor)

        return PaginatedList(
            items=channels,
            page_state=PageState(
                cursor=next_cursor if has_more else None,
                has_more=has_more,
            ),
        )

    @action("Get a single channel by ID")
    async def get_channel(self, channel_id: str) -> Channel:
        """Retrieve details for a single Slack channel.

        Args:
            channel_id: The channel ID (e.g. ``C01234ABCDE``).

        Returns:
            The requested Channel object.
        """
        body = await self._request(
            "GET",
            "conversations.info",
            params={"channel": channel_id},
        )
        return Channel(**body.get("channel", {}))

    @action("List messages in a channel")
    async def list_messages(
        self,
        channel: str,
        limit: int = 100,
        cursor: Optional[str] = None,
    ) -> PaginatedList[Message]:
        """Retrieve message history from a Slack channel.

        Args:
            channel: Channel ID to fetch messages from.
            limit: Maximum number of messages to return (max 1000).
            cursor: Pagination cursor from a previous response.

        Returns:
            Paginated list of Message objects (newest first).
        """
        params: dict[str, Any] = {
            "channel": channel,
            "limit": min(limit, 1000),
        }
        if cursor:
            params["cursor"] = cursor

        body = await self._request("GET", "conversations.history", params=params)

        messages = [
            Message(**{**msg, "channel": channel})
            for msg in body.get("messages", [])
        ]
        next_cursor = body.get("response_metadata", {}).get("next_cursor", "")
        has_more = body.get("has_more", False) or bool(next_cursor)

        return PaginatedList(
            items=messages,
            page_state=PageState(
                cursor=next_cursor if has_more else None,
                has_more=has_more,
            ),
        )

    @action("Upload a file to Slack channels", dangerous=True)
    async def upload_file(
        self,
        channels: str,
        content: str,
        filename: str,
        title: Optional[str] = None,
    ) -> SlackFile:
        """Upload a file to one or more Slack channels.

        Args:
            channels: Comma-separated channel IDs to share the file in.
            content: File content as a string.
            filename: Name for the uploaded file.
            title: Optional display title for the file.

        Returns:
            The uploaded SlackFile object.
        """
        form_data: dict[str, Any] = {
            "channels": channels,
            "content": content,
            "filename": filename,
        }
        if title:
            form_data["title"] = title

        body = await self._request("POST", "files.upload", data=form_data)
        return SlackFile(**body.get("file", {}))

    @action("Add a reaction emoji to a message")
    async def add_reaction(
        self,
        channel: str,
        timestamp: str,
        emoji: str,
    ) -> None:
        """Add an emoji reaction to a message.

        Args:
            channel: Channel ID containing the message.
            timestamp: Message timestamp (``ts`` field) to react to.
            emoji: Emoji name without colons (e.g. ``thumbsup``).
        """
        await self._request(
            "POST",
            "reactions.add",
            json_body={
                "channel": channel,
                "timestamp": timestamp,
                "name": emoji,
            },
        )

    @action("List users in the workspace")
    async def list_users(
        self,
        limit: int = 100,
        cursor: Optional[str] = None,
    ) -> PaginatedList[SlackUser]:
        """List members of the Slack workspace.

        Args:
            limit: Maximum number of users to return (max 1000).
            cursor: Pagination cursor from a previous response.

        Returns:
            Paginated list of SlackUser objects.
        """
        params: dict[str, Any] = {"limit": min(limit, 1000)}
        if cursor:
            params["cursor"] = cursor

        body = await self._request("GET", "users.list", params=params)

        users: list[SlackUser] = []
        for member in body.get("members", []):
            profile = member.get("profile", {})
            users.append(
                SlackUser(
                    id=member.get("id", ""),
                    name=member.get("name", ""),
                    real_name=member.get("real_name", profile.get("real_name", "")),
                    display_name=profile.get("display_name", ""),
                    email=profile.get("email"),
                    is_bot=member.get("is_bot", False),
                    is_admin=member.get("is_admin", False),
                    is_owner=member.get("is_owner", False),
                    deleted=member.get("deleted", False),
                    tz=member.get("tz"),
                    avatar_url=profile.get("image_72"),
                )
            )

        next_cursor = body.get("response_metadata", {}).get("next_cursor", "")
        has_more = bool(next_cursor)

        return PaginatedList(
            items=users,
            page_state=PageState(
                cursor=next_cursor if has_more else None,
                has_more=has_more,
            ),
        )

    @action("Get a single user by ID")
    async def get_user(self, user_id: str) -> SlackUser:
        """Retrieve details for a single Slack user.

        Args:
            user_id: The user ID (e.g. ``U01234ABCDE``).

        Returns:
            The requested SlackUser object.
        """
        body = await self._request(
            "GET",
            "users.info",
            params={"user": user_id},
        )
        member = body.get("user", {})
        profile = member.get("profile", {})
        return SlackUser(
            id=member.get("id", ""),
            name=member.get("name", ""),
            real_name=member.get("real_name", profile.get("real_name", "")),
            display_name=profile.get("display_name", ""),
            email=profile.get("email"),
            is_bot=member.get("is_bot", False),
            is_admin=member.get("is_admin", False),
            is_owner=member.get("is_owner", False),
            deleted=member.get("deleted", False),
            tz=member.get("tz"),
            avatar_url=profile.get("image_72"),
        )
