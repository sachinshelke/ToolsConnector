"""Slack connector — full Slack Web API coverage.

Covers messaging, channels, users, reactions, pins, search, reminders,
scheduled messages, bookmarks, and workspace management.

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

from .types import (
    Bookmark,
    Channel,
    CustomEmoji,
    Message,
    PinnedItem,
    Reaction,
    Reminder,
    ScheduledMessage,
    SearchResult,
    SlackFile,
    SlackTeam,
    SlackUser,
    SlackUserGroup,
    UserPresence,
    UserProfile,
)

logger = logging.getLogger("toolsconnector.slack")


class Slack(BaseConnector):
    """Connect to Slack workspaces with full API coverage.

    Requires a Slack Bot token (xoxb-...) passed as ``credentials``.
    Uses the Slack Web API with cursor-based pagination.

    Covers: messaging, channels, users, reactions, pins, files, search,
    reminders, scheduled messages, bookmarks, emoji, and user presence.
    """

    name = "slack"
    display_name = "Slack"
    category = ConnectorCategory.COMMUNICATION
    protocol = ProtocolType.REST
    base_url = "https://slack.com/api"
    description = (
        "Connect to Slack workspaces — send and manage messages, "
        "channels, users, files, reactions, pins, reminders, and more."
    )
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
            if error_code in (
                "channel_not_found",
                "user_not_found",
                "file_not_found",
                "message_not_found",
                "not_found",
            ):
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

    def _parse_user(self, member: dict[str, Any]) -> SlackUser:
        """Parse a Slack user dict into a SlackUser model."""
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

    # ======================================================================
    # MESSAGING
    # ======================================================================

    @action("Send a message to a Slack channel or thread", dangerous=True)
    async def send_message(
        self,
        channel: str,
        text: str,
        thread_ts: Optional[str] = None,
        unfurl_links: bool = True,
        unfurl_media: bool = True,
    ) -> Message:
        """Send a message to a Slack channel.

        Args:
            channel: Channel ID (e.g. ``C01234ABCDE``) or name.
            text: Message text (supports Slack mrkdwn formatting).
            thread_ts: Optional parent message timestamp to reply in a thread.
            unfurl_links: Whether to unfurl text-based URLs.
            unfurl_media: Whether to unfurl media content.

        Returns:
            The sent Message object.
        """
        payload: dict[str, Any] = {
            "channel": channel,
            "text": text,
            "unfurl_links": unfurl_links,
            "unfurl_media": unfurl_media,
        }
        if thread_ts:
            payload["thread_ts"] = thread_ts

        body = await self._request("POST", "chat.postMessage", json_body=payload)
        msg_data = body.get("message", {})
        msg_data["channel"] = body.get("channel", channel)
        return Message(**msg_data)

    @action("Update an existing message", dangerous=True)
    async def update_message(
        self,
        channel: str,
        ts: str,
        text: str,
    ) -> Message:
        """Update the text of an existing message.

        Args:
            channel: Channel ID containing the message.
            ts: Timestamp (``ts``) of the message to update.
            text: New message text (supports Slack mrkdwn formatting).

        Returns:
            The updated Message object.
        """
        body = await self._request(
            "POST",
            "chat.update",
            json_body={"channel": channel, "ts": ts, "text": text},
        )
        msg_data = body.get("message", {})
        msg_data["channel"] = body.get("channel", channel)
        return Message(**msg_data)

    @action("Delete a message from a channel", dangerous=True)
    async def delete_message(
        self,
        channel: str,
        ts: str,
    ) -> None:
        """Delete a message. Requires ``chat:write`` scope and either
        the message must be authored by the bot, or the bot must have
        ``chat:write.customize`` and ``admin`` permissions.

        Args:
            channel: Channel ID containing the message.
            ts: Timestamp (``ts``) of the message to delete.
        """
        await self._request(
            "POST",
            "chat.delete",
            json_body={"channel": channel, "ts": ts},
        )

    @action("Schedule a message for future delivery", dangerous=True)
    async def schedule_message(
        self,
        channel: str,
        text: str,
        post_at: int,
        thread_ts: Optional[str] = None,
    ) -> ScheduledMessage:
        """Schedule a message to be sent at a future time.

        Args:
            channel: Channel ID to send to.
            text: Message text (supports Slack mrkdwn formatting).
            post_at: Unix timestamp for when to send the message.
            thread_ts: Optional parent message timestamp for threading.

        Returns:
            The ScheduledMessage object with its ID and scheduled time.
        """
        payload: dict[str, Any] = {
            "channel": channel,
            "text": text,
            "post_at": post_at,
        }
        if thread_ts:
            payload["thread_ts"] = thread_ts

        body = await self._request(
            "POST", "chat.scheduleMessage", json_body=payload,
        )
        return ScheduledMessage(
            id=body.get("scheduled_message_id", ""),
            channel_id=body.get("channel", channel),
            post_at=body.get("post_at", post_at),
            date_created=0,
            text=text,
        )

    @action("List scheduled messages")
    async def list_scheduled_messages(
        self,
        channel: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: int = 100,
    ) -> PaginatedList[ScheduledMessage]:
        """List messages that have been scheduled but not yet sent.

        Args:
            channel: Optional channel ID to filter by.
            cursor: Pagination cursor from a previous response.
            limit: Maximum number of results to return (max 100).

        Returns:
            Paginated list of ScheduledMessage objects.
        """
        payload: dict[str, Any] = {"limit": min(limit, 100)}
        if channel:
            payload["channel"] = channel
        if cursor:
            payload["cursor"] = cursor

        body = await self._request(
            "POST", "chat.scheduledMessages.list", json_body=payload,
        )
        items = [
            ScheduledMessage(
                id=m.get("id", ""),
                channel_id=m.get("channel_id", ""),
                post_at=m.get("post_at", 0),
                date_created=m.get("date_created", 0),
                text=m.get("text", ""),
            )
            for m in body.get("scheduled_messages", [])
        ]
        next_cursor = body.get("response_metadata", {}).get("next_cursor", "")
        has_more = bool(next_cursor)
        return PaginatedList(
            items=items,
            page_state=PageState(
                cursor=next_cursor if has_more else None,
                has_more=has_more,
            ),
        )

    @action("Delete a scheduled message", dangerous=True)
    async def delete_scheduled_message(
        self,
        channel: str,
        scheduled_message_id: str,
    ) -> None:
        """Cancel a scheduled message before it is sent.

        Args:
            channel: Channel ID the message was scheduled in.
            scheduled_message_id: The ID of the scheduled message.
        """
        await self._request(
            "POST",
            "chat.deleteScheduledMessage",
            json_body={
                "channel": channel,
                "scheduled_message_id": scheduled_message_id,
            },
        )

    @action("Get a permalink URL for a specific message")
    async def get_permalink(
        self,
        channel: str,
        message_ts: str,
    ) -> str:
        """Get a permanent URL that points to a specific message.

        Args:
            channel: Channel ID containing the message.
            message_ts: Timestamp (``ts``) of the message.

        Returns:
            The permalink URL string.
        """
        body = await self._request(
            "GET",
            "chat.getPermalink",
            params={"channel": channel, "message_ts": message_ts},
        )
        return body.get("permalink", "")

    # ======================================================================
    # CHANNELS
    # ======================================================================

    @action("List channels in the workspace")
    async def list_channels(
        self,
        limit: int = 100,
        cursor: Optional[str] = None,
        exclude_archived: bool = False,
    ) -> PaginatedList[Channel]:
        """List public and private channels the bot has access to.

        Args:
            limit: Maximum number of channels to return (max 1000).
            cursor: Pagination cursor from a previous response.
            exclude_archived: If ``True``, exclude archived channels.

        Returns:
            Paginated list of Channel objects.
        """
        params: dict[str, Any] = {
            "types": "public_channel,private_channel",
            "limit": min(limit, 1000),
            "exclude_archived": str(exclude_archived).lower(),
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

    @action("Create a new channel", dangerous=True)
    async def create_channel(
        self,
        name: str,
        is_private: bool = False,
    ) -> Channel:
        """Create a new public or private channel.

        Args:
            name: Name of the channel (lowercase, no spaces,
                max 80 characters).
            is_private: If ``True``, create a private channel.

        Returns:
            The newly created Channel object.
        """
        body = await self._request(
            "POST",
            "conversations.create",
            json_body={"name": name, "is_private": is_private},
        )
        return Channel(**body.get("channel", {}))

    @action("Archive a channel", dangerous=True)
    async def archive_channel(self, channel: str) -> None:
        """Archive a channel. Can be unarchived later.

        Args:
            channel: Channel ID to archive.
        """
        await self._request(
            "POST", "conversations.archive", json_body={"channel": channel},
        )

    @action("Unarchive a channel")
    async def unarchive_channel(self, channel: str) -> None:
        """Unarchive a previously archived channel.

        Args:
            channel: Channel ID to unarchive.
        """
        await self._request(
            "POST", "conversations.unarchive", json_body={"channel": channel},
        )

    @action("Rename a channel", dangerous=True)
    async def rename_channel(self, channel: str, name: str) -> Channel:
        """Rename an existing channel.

        Args:
            channel: Channel ID to rename.
            name: New channel name (lowercase, no spaces, max 80 chars).

        Returns:
            The updated Channel object.
        """
        body = await self._request(
            "POST",
            "conversations.rename",
            json_body={"channel": channel, "name": name},
        )
        return Channel(**body.get("channel", {}))

    @action("Set the topic of a channel")
    async def set_channel_topic(self, channel: str, topic: str) -> Channel:
        """Set or update the topic of a channel.

        Args:
            channel: Channel ID.
            topic: New topic string (max 250 characters).

        Returns:
            The updated Channel object with the new topic.
        """
        body = await self._request(
            "POST",
            "conversations.setTopic",
            json_body={"channel": channel, "topic": topic},
        )
        return Channel(**body.get("channel", {}))

    @action("Set the purpose of a channel")
    async def set_channel_purpose(self, channel: str, purpose: str) -> Channel:
        """Set or update the purpose/description of a channel.

        Args:
            channel: Channel ID.
            purpose: New purpose string (max 250 characters).

        Returns:
            The updated Channel object with the new purpose.
        """
        body = await self._request(
            "POST",
            "conversations.setPurpose",
            json_body={"channel": channel, "purpose": purpose},
        )
        return Channel(**body.get("channel", {}))

    @action("Invite a user to a channel")
    async def invite_to_channel(self, channel: str, users: str) -> Channel:
        """Invite one or more users to a channel.

        Args:
            channel: Channel ID to invite users to.
            users: Comma-separated user IDs (e.g. ``U01,U02``).

        Returns:
            The Channel object after invite.
        """
        body = await self._request(
            "POST",
            "conversations.invite",
            json_body={"channel": channel, "users": users},
        )
        return Channel(**body.get("channel", {}))

    @action("Remove a user from a channel", dangerous=True)
    async def kick_from_channel(self, channel: str, user: str) -> None:
        """Remove a user from a channel.

        Args:
            channel: Channel ID.
            user: User ID to remove.
        """
        await self._request(
            "POST",
            "conversations.kick",
            json_body={"channel": channel, "user": user},
        )

    @action("Join a channel")
    async def join_channel(self, channel: str) -> Channel:
        """Join an existing channel.

        Args:
            channel: Channel ID to join.

        Returns:
            The Channel object after joining.
        """
        body = await self._request(
            "POST", "conversations.join", json_body={"channel": channel},
        )
        return Channel(**body.get("channel", {}))

    @action("Leave a channel")
    async def leave_channel(self, channel: str) -> None:
        """Leave a channel.

        Args:
            channel: Channel ID to leave.
        """
        await self._request(
            "POST", "conversations.leave", json_body={"channel": channel},
        )

    @action("List members of a channel")
    async def list_channel_members(
        self,
        channel: str,
        limit: int = 100,
        cursor: Optional[str] = None,
    ) -> PaginatedList[str]:
        """List user IDs of all members in a channel.

        Args:
            channel: Channel ID.
            limit: Maximum number of members to return (max 1000).
            cursor: Pagination cursor from a previous response.

        Returns:
            Paginated list of user ID strings.
        """
        params: dict[str, Any] = {
            "channel": channel,
            "limit": min(limit, 1000),
        }
        if cursor:
            params["cursor"] = cursor

        body = await self._request("GET", "conversations.members", params=params)
        members = body.get("members", [])
        next_cursor = body.get("response_metadata", {}).get("next_cursor", "")
        has_more = bool(next_cursor)
        return PaginatedList(
            items=members,
            page_state=PageState(
                cursor=next_cursor if has_more else None,
                has_more=has_more,
            ),
        )

    # ======================================================================
    # MESSAGES (history & threads)
    # ======================================================================

    @action("List messages in a channel")
    async def list_messages(
        self,
        channel: str,
        limit: int = 100,
        cursor: Optional[str] = None,
        oldest: Optional[str] = None,
        latest: Optional[str] = None,
    ) -> PaginatedList[Message]:
        """Retrieve message history from a Slack channel.

        Args:
            channel: Channel ID to fetch messages from.
            limit: Maximum number of messages to return (max 1000).
            cursor: Pagination cursor from a previous response.
            oldest: Only messages after this Unix timestamp.
            latest: Only messages before this Unix timestamp.

        Returns:
            Paginated list of Message objects (newest first).
        """
        params: dict[str, Any] = {
            "channel": channel,
            "limit": min(limit, 1000),
        }
        if cursor:
            params["cursor"] = cursor
        if oldest:
            params["oldest"] = oldest
        if latest:
            params["latest"] = latest

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

    @action("List replies in a message thread")
    async def list_thread_replies(
        self,
        channel: str,
        thread_ts: str,
        limit: int = 100,
        cursor: Optional[str] = None,
    ) -> PaginatedList[Message]:
        """Retrieve all replies in a message thread.

        Args:
            channel: Channel ID containing the thread.
            thread_ts: Timestamp of the parent message.
            limit: Maximum number of replies to return (max 1000).
            cursor: Pagination cursor from a previous response.

        Returns:
            Paginated list of Message objects in the thread.
        """
        params: dict[str, Any] = {
            "channel": channel,
            "ts": thread_ts,
            "limit": min(limit, 1000),
        }
        if cursor:
            params["cursor"] = cursor

        body = await self._request("GET", "conversations.replies", params=params)
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

    # ======================================================================
    # REACTIONS
    # ======================================================================

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

    @action("Remove a reaction emoji from a message")
    async def remove_reaction(
        self,
        channel: str,
        timestamp: str,
        emoji: str,
    ) -> None:
        """Remove an emoji reaction from a message.

        Args:
            channel: Channel ID containing the message.
            timestamp: Message timestamp (``ts`` field).
            emoji: Emoji name without colons (e.g. ``thumbsup``).
        """
        await self._request(
            "POST",
            "reactions.remove",
            json_body={
                "channel": channel,
                "timestamp": timestamp,
                "name": emoji,
            },
        )

    @action("Get reactions for a message")
    async def get_reactions(
        self,
        channel: str,
        timestamp: str,
    ) -> list[Reaction]:
        """Get all reactions on a specific message.

        Args:
            channel: Channel ID containing the message.
            timestamp: Message timestamp (``ts`` field).

        Returns:
            List of Reaction objects with emoji names, counts, and users.
        """
        body = await self._request(
            "GET",
            "reactions.get",
            params={"channel": channel, "timestamp": timestamp, "full": "true"},
        )
        msg = body.get("message", {})
        return [
            Reaction(
                name=r.get("name", ""),
                count=r.get("count", 0),
                users=r.get("users", []),
            )
            for r in msg.get("reactions", [])
        ]

    # ======================================================================
    # PINS
    # ======================================================================

    @action("Pin a message to a channel")
    async def pin_message(self, channel: str, timestamp: str) -> None:
        """Pin a message to a channel for easy reference.

        Args:
            channel: Channel ID containing the message.
            timestamp: Message timestamp (``ts`` field) to pin.
        """
        await self._request(
            "POST",
            "pins.add",
            json_body={"channel": channel, "timestamp": timestamp},
        )

    @action("Unpin a message from a channel")
    async def unpin_message(self, channel: str, timestamp: str) -> None:
        """Remove a pinned message from a channel.

        Args:
            channel: Channel ID.
            timestamp: Message timestamp (``ts`` field) to unpin.
        """
        await self._request(
            "POST",
            "pins.remove",
            json_body={"channel": channel, "timestamp": timestamp},
        )

    @action("List pinned items in a channel")
    async def list_pins(self, channel: str) -> list[PinnedItem]:
        """List all pinned items in a channel.

        Args:
            channel: Channel ID to list pins for.

        Returns:
            List of PinnedItem objects.
        """
        body = await self._request(
            "GET", "pins.list", params={"channel": channel},
        )
        return [
            PinnedItem(
                type=item.get("type", ""),
                channel=channel,
                message=item.get("message"),
                file=item.get("file"),
                created=item.get("created", 0),
                created_by=item.get("created_by"),
            )
            for item in body.get("items", [])
        ]

    # ======================================================================
    # FILES
    # ======================================================================

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

    @action("Delete a file", dangerous=True)
    async def delete_file(self, file_id: str) -> None:
        """Delete a file from Slack.

        Args:
            file_id: The file ID to delete.
        """
        await self._request(
            "POST", "files.delete", json_body={"file": file_id},
        )

    @action("Get file info")
    async def get_file_info(self, file_id: str) -> SlackFile:
        """Retrieve information about a file.

        Args:
            file_id: The file ID (e.g. ``F01234ABCDE``).

        Returns:
            The SlackFile object with full metadata.
        """
        body = await self._request(
            "GET", "files.info", params={"file": file_id},
        )
        return SlackFile(**body.get("file", {}))

    # ======================================================================
    # USERS
    # ======================================================================

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

        users = [self._parse_user(m) for m in body.get("members", [])]

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
        return self._parse_user(body.get("user", {}))

    @action("Look up a user by email address")
    async def lookup_user_by_email(self, email: str) -> SlackUser:
        """Find a user by their email address.

        Args:
            email: The email address to look up.

        Returns:
            The matching SlackUser object.
        """
        body = await self._request(
            "GET",
            "users.lookupByEmail",
            params={"email": email},
        )
        return self._parse_user(body.get("user", {}))

    @action("Get a user's presence status")
    async def get_user_presence(self, user_id: str) -> UserPresence:
        """Get the presence/online status of a user.

        Args:
            user_id: The user ID.

        Returns:
            UserPresence object with activity status.
        """
        body = await self._request(
            "GET", "users.getPresence", params={"user": user_id},
        )
        return UserPresence(
            presence=body.get("presence", "away"),
            online=body.get("online", False),
            auto_away=body.get("auto_away", False),
            manual_away=body.get("manual_away", False),
            last_activity=body.get("last_activity"),
        )

    @action("Get a user's profile")
    async def get_user_profile(self, user_id: str) -> UserProfile:
        """Get the profile information of a user.

        Args:
            user_id: The user ID.

        Returns:
            UserProfile object with extended profile fields.
        """
        body = await self._request(
            "GET",
            "users.profile.get",
            params={"user": user_id},
        )
        p = body.get("profile", {})
        return UserProfile(
            status_text=p.get("status_text", ""),
            status_emoji=p.get("status_emoji", ""),
            status_expiration=p.get("status_expiration", 0),
            real_name=p.get("real_name", ""),
            display_name=p.get("display_name", ""),
            email=p.get("email"),
            first_name=p.get("first_name", ""),
            last_name=p.get("last_name", ""),
            title=p.get("title", ""),
            phone=p.get("phone", ""),
            image_72=p.get("image_72", ""),
            image_192=p.get("image_192", ""),
        )

    @action("Set the bot user's presence status")
    async def set_presence(self, presence: str) -> None:
        """Set the bot's presence status.

        Args:
            presence: Either ``auto`` or ``away``.
        """
        await self._request(
            "POST",
            "users.setPresence",
            json_body={"presence": presence},
        )

    # ======================================================================
    # SEARCH
    # ======================================================================

    @action("Search for messages across the workspace")
    async def search_messages(
        self,
        query: str,
        sort: str = "timestamp",
        sort_dir: str = "desc",
        count: int = 20,
        page: int = 1,
    ) -> list[SearchResult]:
        """Search for messages matching a query string.

        Requires a user token (xoxp-...) — bot tokens cannot search.

        Args:
            query: Search query (supports Slack search modifiers like
                ``from:@user``, ``in:#channel``, ``has:link``).
            sort: Sort field — ``timestamp`` or ``score``.
            sort_dir: Sort direction — ``asc`` or ``desc``.
            count: Number of results per page (max 100).
            page: Page number (1-based).

        Returns:
            List of SearchResult objects.
        """
        body = await self._request(
            "GET",
            "search.messages",
            params={
                "query": query,
                "sort": sort,
                "sort_dir": sort_dir,
                "count": min(count, 100),
                "page": page,
            },
        )
        matches = body.get("messages", {}).get("matches", [])
        return [
            SearchResult(
                channel=m.get("channel"),
                ts=m.get("ts", ""),
                text=m.get("text", ""),
                user=m.get("user"),
                permalink=m.get("permalink", ""),
                score=m.get("score"),
            )
            for m in matches
        ]

    # ======================================================================
    # BOOKMARKS
    # ======================================================================

    @action("Add a bookmark to a channel")
    async def add_bookmark(
        self,
        channel_id: str,
        title: str,
        link: str,
        emoji: Optional[str] = None,
    ) -> Bookmark:
        """Add a bookmark (link) to a channel's bookmark bar.

        Args:
            channel_id: Channel ID.
            title: Display title for the bookmark.
            link: URL for the bookmark.
            emoji: Optional emoji to display (e.g. ``:link:``).

        Returns:
            The created Bookmark object.
        """
        payload: dict[str, Any] = {
            "channel_id": channel_id,
            "title": title,
            "type": "link",
            "link": link,
        }
        if emoji:
            payload["emoji"] = emoji

        body = await self._request(
            "POST", "bookmarks.add", json_body=payload,
        )
        bk = body.get("bookmark", {})
        return Bookmark(
            id=bk.get("id", ""),
            channel_id=bk.get("channel_id", channel_id),
            title=bk.get("title", title),
            link=bk.get("link", link),
            emoji=bk.get("emoji", ""),
            type=bk.get("type", "link"),
            created=bk.get("date_created", 0),
            updated=bk.get("date_updated", 0),
        )

    @action("List bookmarks in a channel")
    async def list_bookmarks(self, channel_id: str) -> list[Bookmark]:
        """List all bookmarks in a channel.

        Args:
            channel_id: Channel ID.

        Returns:
            List of Bookmark objects.
        """
        body = await self._request(
            "GET", "bookmarks.list", params={"channel_id": channel_id},
        )
        return [
            Bookmark(
                id=bk.get("id", ""),
                channel_id=bk.get("channel_id", channel_id),
                title=bk.get("title", ""),
                link=bk.get("link", ""),
                emoji=bk.get("emoji", ""),
                type=bk.get("type", "link"),
                created=bk.get("date_created", 0),
                updated=bk.get("date_updated", 0),
            )
            for bk in body.get("bookmarks", [])
        ]

    @action("Remove a bookmark from a channel", dangerous=True)
    async def remove_bookmark(
        self,
        bookmark_id: str,
        channel_id: str,
    ) -> None:
        """Remove a bookmark from a channel.

        Args:
            bookmark_id: The bookmark ID.
            channel_id: The channel ID.
        """
        await self._request(
            "POST",
            "bookmarks.remove",
            json_body={"bookmark_id": bookmark_id, "channel_id": channel_id},
        )

    # ======================================================================
    # REMINDERS
    # ======================================================================

    @action("Create a reminder")
    async def add_reminder(
        self,
        text: str,
        time: str,
        user: Optional[str] = None,
    ) -> Reminder:
        """Create a reminder for yourself or another user.

        Args:
            text: The reminder text.
            time: When to trigger — Unix timestamp, or natural language
                like ``in 15 minutes``, ``every Thursday``.
            user: Optional user ID. Defaults to the authed user.

        Returns:
            The created Reminder object.
        """
        payload: dict[str, Any] = {"text": text, "time": time}
        if user:
            payload["user"] = user

        body = await self._request(
            "POST", "reminders.add", json_body=payload,
        )
        r = body.get("reminder", {})
        return Reminder(
            id=r.get("id", ""),
            creator=r.get("creator", ""),
            text=r.get("text", text),
            user=r.get("user", ""),
            recurring=r.get("recurring", False),
            time=r.get("time"),
            complete_ts=r.get("complete_ts"),
        )

    @action("List all reminders")
    async def list_reminders(self) -> list[Reminder]:
        """List all reminders created by or for the authenticated user.

        Returns:
            List of Reminder objects.
        """
        body = await self._request("GET", "reminders.list")
        return [
            Reminder(
                id=r.get("id", ""),
                creator=r.get("creator", ""),
                text=r.get("text", ""),
                user=r.get("user", ""),
                recurring=r.get("recurring", False),
                time=r.get("time"),
                complete_ts=r.get("complete_ts"),
            )
            for r in body.get("reminders", [])
        ]

    @action("Delete a reminder", dangerous=True)
    async def delete_reminder(self, reminder_id: str) -> None:
        """Delete a reminder.

        Args:
            reminder_id: The reminder ID.
        """
        await self._request(
            "POST", "reminders.delete", json_body={"reminder": reminder_id},
        )

    # ======================================================================
    # EMOJI
    # ======================================================================

    @action("List custom emoji in the workspace")
    async def list_emoji(self) -> list[CustomEmoji]:
        """List all custom emoji in the workspace.

        Returns:
            List of CustomEmoji objects with names and URLs.
        """
        body = await self._request("GET", "emoji.list")
        emoji_map = body.get("emoji", {})
        result: list[CustomEmoji] = []
        for name, url in emoji_map.items():
            if url.startswith("alias:"):
                result.append(CustomEmoji(
                    name=name, url="", alias_for=url.removeprefix("alias:"),
                ))
            else:
                result.append(CustomEmoji(name=name, url=url))
        return result

    # ======================================================================
    # WORKSPACE / AUTH TEST
    # ======================================================================

    @action("Test authentication and get workspace info")
    async def auth_test(self) -> dict[str, Any]:
        """Test the bot token and return authenticated identity info.

        Useful for verifying credentials and discovering the workspace,
        team, and bot identity.

        Returns:
            Dict with keys: ``url``, ``team``, ``user``, ``team_id``,
            ``user_id``, ``bot_id``.
        """
        body = await self._request("POST", "auth.test")
        return {
            "url": body.get("url", ""),
            "team": body.get("team", ""),
            "user": body.get("user", ""),
            "team_id": body.get("team_id", ""),
            "user_id": body.get("user_id", ""),
            "bot_id": body.get("bot_id", ""),
        }

    @action("Get workspace team information")
    async def get_team_info(self) -> SlackTeam:
        """Retrieve information about the Slack workspace (team).

        Returns basic metadata including the team name, domain,
        email domain, and enterprise info if applicable.

        Returns:
            SlackTeam object with workspace details.
        """
        body = await self._request("GET", "team.info")
        t = body.get("team", {})
        return SlackTeam(
            id=t.get("id", ""),
            name=t.get("name", ""),
            domain=t.get("domain", ""),
            email_domain=t.get("email_domain", ""),
            icon=t.get("icon"),
            enterprise_id=t.get("enterprise_id"),
            enterprise_name=t.get("enterprise_name"),
        )

    # ======================================================================
    # USER PROFILE
    # ======================================================================

    @action("Set the authenticated user's status", dangerous=True)
    async def set_status(
        self,
        status_text: str,
        status_emoji: Optional[str] = None,
        expiration: Optional[int] = None,
    ) -> None:
        """Set the status text and emoji on the authenticated user's profile.

        Requires the ``users.profile:write`` scope.

        Args:
            status_text: Status text to display (max 100 characters).
            status_emoji: Optional emoji code (e.g. ``:house_with_garden:``).
                Pass an empty string to clear the emoji.
            expiration: Optional Unix timestamp for when the status should
                expire. Pass ``0`` to keep the status indefinitely.
        """
        profile: dict[str, Any] = {"status_text": status_text}
        if status_emoji is not None:
            profile["status_emoji"] = status_emoji
        if expiration is not None:
            profile["status_expiration"] = expiration

        await self._request(
            "POST",
            "users.profile.set",
            json_body={"profile": profile},
        )

    # ======================================================================
    # USER GROUPS
    # ======================================================================

    @action("Create a user group", dangerous=True)
    async def create_usergroup(
        self,
        name: str,
        handle: str,
        description: Optional[str] = None,
        channels: Optional[str] = None,
    ) -> SlackUserGroup:
        """Create a new user group (handle) in the workspace.

        Requires the ``usergroups:write`` scope.

        Args:
            name: Display name for the user group.
            handle: Short mention handle (e.g. ``engineering`` for
                ``@engineering``). Must be unique in the workspace.
            description: Optional purpose/description for the group.
            channels: Optional comma-separated channel IDs to associate
                with the group as default channels.

        Returns:
            The created SlackUserGroup object.
        """
        payload: dict[str, Any] = {"name": name, "handle": handle}
        if description is not None:
            payload["description"] = description
        if channels is not None:
            payload["channels"] = channels

        body = await self._request(
            "POST", "usergroups.create", json_body=payload,
        )
        ug = body.get("usergroup", {})
        return SlackUserGroup(
            id=ug.get("id", ""),
            team_id=ug.get("team_id", ""),
            name=ug.get("name", name),
            handle=ug.get("handle", handle),
            description=ug.get("description", ""),
            is_external=ug.get("is_external", False),
            is_usergroup=ug.get("is_usergroup", True),
            auto_type=ug.get("auto_type"),
            date_create=ug.get("date_create", 0),
            date_update=ug.get("date_update", 0),
            date_delete=ug.get("date_delete", 0),
            created_by=ug.get("created_by", ""),
            updated_by=ug.get("updated_by", ""),
            user_count=ug.get("user_count", 0),
            users=ug.get("users", []),
            channels=ug.get("prefs", {}).get("channels", []),
        )

    @action("List user groups in the workspace")
    async def list_usergroups(
        self,
        include_users: bool = False,
        include_disabled: bool = False,
    ) -> list[SlackUserGroup]:
        """List all user groups in the workspace.

        Requires the ``usergroups:read`` scope.

        Args:
            include_users: If ``True``, include the list of user IDs
                for each user group.
            include_disabled: If ``True``, include disabled user groups.

        Returns:
            List of SlackUserGroup objects.
        """
        params: dict[str, Any] = {
            "include_users": str(include_users).lower(),
            "include_disabled": str(include_disabled).lower(),
        }
        body = await self._request("GET", "usergroups.list", params=params)
        return [
            SlackUserGroup(
                id=ug.get("id", ""),
                team_id=ug.get("team_id", ""),
                name=ug.get("name", ""),
                handle=ug.get("handle", ""),
                description=ug.get("description", ""),
                is_external=ug.get("is_external", False),
                is_usergroup=ug.get("is_usergroup", True),
                auto_type=ug.get("auto_type"),
                date_create=ug.get("date_create", 0),
                date_update=ug.get("date_update", 0),
                date_delete=ug.get("date_delete", 0),
                created_by=ug.get("created_by", ""),
                updated_by=ug.get("updated_by", ""),
                user_count=ug.get("user_count", 0),
                users=ug.get("users", []),
                channels=ug.get("prefs", {}).get("channels", []),
            )
            for ug in body.get("usergroups", [])
        ]

    @action("Update an existing user group", dangerous=True)
    async def update_usergroup(
        self,
        usergroup_id: str,
        name: Optional[str] = None,
        handle: Optional[str] = None,
        description: Optional[str] = None,
        channels: Optional[str] = None,
    ) -> SlackUserGroup:
        """Update an existing user group's properties.

        Requires the ``usergroups:write`` scope.

        Args:
            usergroup_id: The user group ID (e.g. ``S01234ABCDE``).
            name: Optional new display name.
            handle: Optional new mention handle.
            description: Optional new description.
            channels: Optional comma-separated channel IDs to set as
                default channels.

        Returns:
            The updated SlackUserGroup object.
        """
        payload: dict[str, Any] = {"usergroup": usergroup_id}
        if name is not None:
            payload["name"] = name
        if handle is not None:
            payload["handle"] = handle
        if description is not None:
            payload["description"] = description
        if channels is not None:
            payload["channels"] = channels

        body = await self._request(
            "POST", "usergroups.update", json_body=payload,
        )
        ug = body.get("usergroup", {})
        return SlackUserGroup(
            id=ug.get("id", ""),
            team_id=ug.get("team_id", ""),
            name=ug.get("name", ""),
            handle=ug.get("handle", ""),
            description=ug.get("description", ""),
            is_external=ug.get("is_external", False),
            is_usergroup=ug.get("is_usergroup", True),
            auto_type=ug.get("auto_type"),
            date_create=ug.get("date_create", 0),
            date_update=ug.get("date_update", 0),
            date_delete=ug.get("date_delete", 0),
            created_by=ug.get("created_by", ""),
            updated_by=ug.get("updated_by", ""),
            user_count=ug.get("user_count", 0),
            users=ug.get("users", []),
            channels=ug.get("prefs", {}).get("channels", []),
        )
