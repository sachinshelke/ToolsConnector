"""Telegram connector -- send messages and manage bot interactions via the Bot API.

Uses the Telegram Bot API (``https://api.telegram.org/bot{token}/...``).
Credentials should be the bot token string obtained from @BotFather.
The token is embedded in the URL path, so no Authorization header is needed.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from toolsconnector.errors import APIError, NotFoundError
from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import (
    ConnectorCategory,
    ProtocolType,
    RateLimitSpec,
)
from toolsconnector.types import PaginatedList, PageState

from .types import (
    TelegramChat,
    TelegramChatMember,
    TelegramMessage,
    TelegramUpdate,
    TelegramUser,
    TelegramWebhookInfo,
)

logger = logging.getLogger("toolsconnector.telegram")


class Telegram(BaseConnector):
    """Connect to the Telegram Bot API to send messages and receive updates.

    Credentials: The bot token string from @BotFather.
    The token is used as part of the base URL path.
    """

    name = "telegram"
    display_name = "Telegram"
    category = ConnectorCategory.COMMUNICATION
    protocol = ProtocolType.REST
    base_url = "https://api.telegram.org"
    description = (
        "Connect to Telegram Bot API to send messages, photos, "
        "documents, and receive updates."
    )
    _rate_limit_config = RateLimitSpec(rate=30, period=1, burst=30)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Initialise the HTTP client with the bot token in the base URL."""
        self._bot_token = str(self._credentials)
        bot_base = f"https://api.telegram.org/bot{self._bot_token}"

        self._client = httpx.AsyncClient(
            base_url=bot_base,
            headers={"Content-Type": "application/json"},
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
        method_name: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[dict[str, Any]] = None,
    ) -> Any:
        """Execute a request against the Telegram Bot API.

        Telegram wraps all responses in ``{"ok": true, "result": ...}``.
        This helper unwraps the response and raises on errors.

        Args:
            method_name: Telegram Bot API method (e.g. ``sendMessage``).
            params: URL query parameters.
            json_body: JSON request body.

        Returns:
            The ``result`` field from the Telegram response.

        Raises:
            NotFoundError: If the chat or message is not found.
            APIError: For any other Telegram API error.
        """
        kwargs: dict[str, Any] = {}
        if params:
            kwargs["params"] = params
        if json_body is not None:
            kwargs["json"] = json_body

        response = await self._client.post(f"/{method_name}", **kwargs)
        body = response.json()

        if not body.get("ok", False):
            error_code = body.get("error_code", 0)
            description = body.get("description", "Unknown Telegram error")
            err_msg = f"Telegram API error ({error_code}): {description}"

            if error_code == 400 and "chat not found" in description.lower():
                raise NotFoundError(
                    err_msg,
                    connector="telegram",
                    action=method_name,
                    details=body,
                )
            if error_code == 400 and "message" in description.lower():
                raise NotFoundError(
                    err_msg,
                    connector="telegram",
                    action=method_name,
                    details=body,
                )
            raise APIError(
                err_msg,
                connector="telegram",
                action=method_name,
                upstream_status=error_code,
                details=body,
            )

        return body.get("result")

    @staticmethod
    def _parse_message(data: dict[str, Any]) -> TelegramMessage:
        """Parse a raw message dict into a TelegramMessage.

        Args:
            data: Raw message data from the Telegram API.

        Returns:
            Parsed TelegramMessage.
        """
        chat_data = data.get("chat")
        chat = TelegramChat(**chat_data) if chat_data else None

        from_data = data.get("from")
        from_user = TelegramUser(**from_data) if from_data else None

        return TelegramMessage(
            message_id=data.get("message_id", 0),
            date=data.get("date", 0),
            chat=chat,
            from_user=from_user,
            text=data.get("text"),
            caption=data.get("caption"),
            photo=data.get("photo"),
            document=data.get("document"),
            reply_to_message=data.get("reply_to_message"),
            edit_date=data.get("edit_date"),
            entities=data.get("entities", []),
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    @action("Send a text message to a chat")
    async def send_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: Optional[str] = None,
    ) -> TelegramMessage:
        """Send a text message to a Telegram chat.

        Args:
            chat_id: Unique identifier for the target chat or username
                (e.g. ``@channelusername``).
            text: Text of the message (up to 4096 characters).
            parse_mode: Parse mode for formatting (``Markdown``, ``HTML``,
                or ``MarkdownV2``).

        Returns:
            The sent TelegramMessage.
        """
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if parse_mode:
            payload["parse_mode"] = parse_mode

        result = await self._request("sendMessage", json_body=payload)
        return self._parse_message(result)

    @action("Get incoming updates for the bot")
    async def get_updates(
        self,
        offset: Optional[int] = None,
        limit: int = 100,
        timeout: Optional[int] = None,
    ) -> list[TelegramUpdate]:
        """Receive incoming updates using long polling.

        Args:
            offset: Identifier of the first update to be returned.
                Set to ``last_update_id + 1`` to acknowledge previous updates.
            limit: Maximum number of updates to retrieve (1-100).
            timeout: Timeout in seconds for long polling (0 for short polling).

        Returns:
            List of TelegramUpdate objects.
        """
        payload: dict[str, Any] = {"limit": min(limit, 100)}
        if offset is not None:
            payload["offset"] = offset
        if timeout is not None:
            payload["timeout"] = timeout

        result = await self._request("getUpdates", json_body=payload)
        updates = []
        for u in (result or []):
            msg_data = u.get("message")
            msg = self._parse_message(msg_data) if msg_data else None

            edited_data = u.get("edited_message")
            edited = self._parse_message(edited_data) if edited_data else None

            channel_data = u.get("channel_post")
            channel_post = (
                self._parse_message(channel_data) if channel_data else None
            )

            updates.append(
                TelegramUpdate(
                    update_id=u.get("update_id", 0),
                    message=msg,
                    edited_message=edited,
                    channel_post=channel_post,
                    callback_query=u.get("callback_query"),
                )
            )
        return updates

    @action("Get information about a chat")
    async def get_chat(self, chat_id: str) -> TelegramChat:
        """Get detailed information about a chat.

        Args:
            chat_id: Unique identifier or username of the target chat.

        Returns:
            TelegramChat with full details.
        """
        result = await self._request(
            "getChat", json_body={"chat_id": chat_id},
        )
        return TelegramChat(**result)

    @action("Get the number of members in a chat")
    async def get_chat_members_count(self, chat_id: str) -> int:
        """Get the number of members in a chat.

        Args:
            chat_id: Unique identifier or username of the target chat.

        Returns:
            Number of members in the chat.
        """
        result = await self._request(
            "getChatMemberCount", json_body={"chat_id": chat_id},
        )
        return int(result)

    @action("Send a photo to a chat")
    async def send_photo(
        self,
        chat_id: str,
        photo_url: str,
        caption: Optional[str] = None,
    ) -> TelegramMessage:
        """Send a photo to a Telegram chat by URL.

        Args:
            chat_id: Unique identifier or username of the target chat.
            photo_url: URL of the photo to send.
            caption: Optional photo caption (up to 1024 characters).

        Returns:
            The sent TelegramMessage.
        """
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "photo": photo_url,
        }
        if caption:
            payload["caption"] = caption

        result = await self._request("sendPhoto", json_body=payload)
        return self._parse_message(result)

    @action("Send a document to a chat")
    async def send_document(
        self,
        chat_id: str,
        document_url: str,
        caption: Optional[str] = None,
    ) -> TelegramMessage:
        """Send a document to a Telegram chat by URL.

        Args:
            chat_id: Unique identifier or username of the target chat.
            document_url: URL of the document to send.
            caption: Optional document caption (up to 1024 characters).

        Returns:
            The sent TelegramMessage.
        """
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "document": document_url,
        }
        if caption:
            payload["caption"] = caption

        result = await self._request("sendDocument", json_body=payload)
        return self._parse_message(result)

    @action("Edit a text message")
    async def edit_message(
        self,
        chat_id: str,
        message_id: int,
        text: str,
    ) -> TelegramMessage:
        """Edit the text of a previously sent message.

        Args:
            chat_id: Unique identifier of the chat containing the message.
            message_id: Identifier of the message to edit.
            text: New text for the message.

        Returns:
            The edited TelegramMessage.
        """
        result = await self._request("editMessageText", json_body={
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
        })
        return self._parse_message(result)

    @action("Delete a message from a chat", dangerous=True)
    async def delete_message(
        self,
        chat_id: str,
        message_id: int,
    ) -> bool:
        """Delete a message from a chat.

        Args:
            chat_id: Unique identifier of the chat.
            message_id: Identifier of the message to delete.

        Returns:
            True if the message was deleted successfully.
        """
        result = await self._request("deleteMessage", json_body={
            "chat_id": chat_id,
            "message_id": message_id,
        })
        return bool(result)

    # ------------------------------------------------------------------
    # Actions — Webhook management
    # ------------------------------------------------------------------

    @action("Set a webhook URL for receiving updates")
    async def set_webhook(self, url: str) -> bool:
        """Set a webhook URL for the bot to receive updates via HTTPS POST.

        Args:
            url: HTTPS URL to send updates to.

        Returns:
            True if the webhook was set successfully.
        """
        result = await self._request(
            "setWebhook", json_body={"url": url},
        )
        return bool(result)

    @action("Delete the current webhook")
    async def delete_webhook(self) -> bool:
        """Remove the current webhook integration.

        Returns:
            True if the webhook was removed successfully.
        """
        result = await self._request("deleteWebhook")
        return bool(result)

    # ------------------------------------------------------------------
    # Actions — Bot info
    # ------------------------------------------------------------------

    @action("Get information about the bot")
    async def get_me(self) -> TelegramUser:
        """Get basic information about the bot.

        Returns:
            TelegramUser representing the bot itself.
        """
        result = await self._request("getMe")
        return TelegramUser(**result)

    # ------------------------------------------------------------------
    # Actions — Chat moderation
    # ------------------------------------------------------------------

    @action("Ban a user from a chat", dangerous=True)
    async def ban_chat_member(
        self, chat_id: str, user_id: int,
    ) -> bool:
        """Ban a user from a group, supergroup, or channel.

        Args:
            chat_id: Unique identifier of the target chat.
            user_id: Unique identifier of the user to ban.

        Returns:
            True if the user was banned successfully.
        """
        result = await self._request("banChatMember", json_body={
            "chat_id": chat_id,
            "user_id": user_id,
        })
        return bool(result)

    @action("Pin a message in a chat")
    async def pin_message(
        self, chat_id: str, message_id: int,
    ) -> bool:
        """Pin a message in a group, supergroup, or channel.

        Args:
            chat_id: Unique identifier of the target chat.
            message_id: Identifier of the message to pin.

        Returns:
            True if the message was pinned successfully.
        """
        result = await self._request("pinChatMessage", json_body={
            "chat_id": chat_id,
            "message_id": message_id,
        })
        return bool(result)

    @action("Unpin a message in a chat")
    async def unpin_message(
        self,
        chat_id: str,
        message_id: Optional[int] = None,
    ) -> bool:
        """Remove a message from the list of pinned messages in a chat.

        If *message_id* is omitted, the most recent pinned message is
        unpinned.

        Args:
            chat_id: Unique identifier of the target chat.
            message_id: Identifier of the message to unpin. If not
                specified, the most recent pinned message is unpinned.

        Returns:
            True if the message was unpinned successfully.
        """
        payload: dict[str, Any] = {"chat_id": chat_id}
        if message_id is not None:
            payload["message_id"] = message_id

        result = await self._request(
            "unpinChatMessage", json_body=payload,
        )
        return bool(result)

    @action("Unpin all messages in a chat", dangerous=True)
    async def unpin_all_messages(self, chat_id: str) -> bool:
        """Clear all pinned messages in a chat.

        Args:
            chat_id: Unique identifier of the target chat.

        Returns:
            True if all messages were unpinned successfully.
        """
        result = await self._request(
            "unpinAllChatMessages",
            json_body={"chat_id": chat_id},
        )
        return bool(result)

    @action("Leave a chat", dangerous=True)
    async def leave_chat(self, chat_id: str) -> bool:
        """Remove the bot from a group, supergroup, or channel.

        Args:
            chat_id: Unique identifier of the chat to leave.

        Returns:
            True if the bot left the chat successfully.
        """
        result = await self._request(
            "leaveChat", json_body={"chat_id": chat_id},
        )
        return bool(result)

    @action("Get information about a chat member")
    async def get_chat_member(
        self, chat_id: str, user_id: int,
    ) -> TelegramChatMember:
        """Get information about a member of a chat.

        Args:
            chat_id: Unique identifier of the target chat.
            user_id: Unique identifier of the target user.

        Returns:
            TelegramChatMember with the user's membership details.
        """
        result = await self._request("getChatMember", json_body={
            "chat_id": chat_id,
            "user_id": user_id,
        })
        user_data = result.get("user")
        user = TelegramUser(**user_data) if user_data else None
        return TelegramChatMember(
            user=user,
            status=result.get("status", ""),
            custom_title=result.get("custom_title"),
            is_anonymous=result.get("is_anonymous"),
            can_be_edited=result.get("can_be_edited"),
            can_manage_chat=result.get("can_manage_chat"),
            can_delete_messages=result.get("can_delete_messages"),
            can_manage_video_chats=result.get("can_manage_video_chats"),
            can_restrict_members=result.get("can_restrict_members"),
            can_promote_members=result.get("can_promote_members"),
            can_change_info=result.get("can_change_info"),
            can_invite_users=result.get("can_invite_users"),
            can_post_messages=result.get("can_post_messages"),
            can_edit_messages=result.get("can_edit_messages"),
            can_pin_messages=result.get("can_pin_messages"),
            until_date=result.get("until_date"),
        )

    @action("Unban a user from a chat")
    async def unban_chat_member(
        self, chat_id: str, user_id: int,
    ) -> bool:
        """Unban a previously banned user in a supergroup or channel.

        The user will not return to the group automatically but will be
        able to join via link, etc.

        Args:
            chat_id: Unique identifier of the target chat.
            user_id: Unique identifier of the user to unban.

        Returns:
            True if the user was unbanned successfully.
        """
        result = await self._request("unbanChatMember", json_body={
            "chat_id": chat_id,
            "user_id": user_id,
        })
        return bool(result)

    @action("Send a location to a chat")
    async def send_location(
        self,
        chat_id: str,
        latitude: float,
        longitude: float,
    ) -> TelegramMessage:
        """Send a point on the map to a Telegram chat.

        Args:
            chat_id: Unique identifier or username of the target chat.
            latitude: Latitude of the location (-90 to 90).
            longitude: Longitude of the location (-180 to 180).

        Returns:
            The sent TelegramMessage.
        """
        result = await self._request("sendLocation", json_body={
            "chat_id": chat_id,
            "latitude": latitude,
            "longitude": longitude,
        })
        return self._parse_message(result)

    @action("Send a contact to a chat")
    async def send_contact(
        self,
        chat_id: str,
        phone_number: str,
        first_name: str,
        last_name: Optional[str] = None,
    ) -> TelegramMessage:
        """Send a phone contact to a Telegram chat.

        Args:
            chat_id: Unique identifier or username of the target chat.
            phone_number: Contact phone number.
            first_name: Contact first name.
            last_name: Optional contact last name.

        Returns:
            The sent TelegramMessage.
        """
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "phone_number": phone_number,
            "first_name": first_name,
        }
        if last_name:
            payload["last_name"] = last_name

        result = await self._request("sendContact", json_body=payload)
        return self._parse_message(result)

    @action("Send a poll to a chat", dangerous=True)
    async def send_poll(
        self,
        chat_id: str,
        question: str,
        options: list[str],
        is_anonymous: bool = True,
    ) -> TelegramMessage:
        """Send a native poll to a Telegram chat.

        Args:
            chat_id: Unique identifier or username of the target chat.
            question: Poll question (1-300 characters).
            options: List of 2-10 answer options.
            is_anonymous: Whether the poll is anonymous (default True).

        Returns:
            The sent TelegramMessage.
        """
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "question": question,
            "options": [{"text": o} for o in options],
            "is_anonymous": is_anonymous,
        }
        result = await self._request("sendPoll", json_body=payload)
        return self._parse_message(result)

    @action("Answer a callback query from an inline keyboard")
    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: Optional[str] = None,
        show_alert: bool = False,
    ) -> bool:
        """Answer a callback query sent from an inline keyboard.

        After the user presses a callback button, Telegram clients
        show a progress bar until this method is called.

        Args:
            callback_query_id: Unique identifier for the callback query.
            text: Optional notification text (0-200 characters).
            show_alert: If True, show an alert instead of a toast.

        Returns:
            True if the callback query was answered successfully.
        """
        payload: dict[str, Any] = {
            "callback_query_id": callback_query_id,
        }
        if text is not None:
            payload["text"] = text
        if show_alert:
            payload["show_alert"] = True

        result = await self._request(
            "answerCallbackQuery", json_body=payload,
        )
        return bool(result)

    @action("Set the title of a chat", dangerous=True)
    async def set_chat_title(
        self, chat_id: str, title: str,
    ) -> bool:
        """Change the title of a group, supergroup, or channel.

        Args:
            chat_id: Unique identifier of the target chat.
            title: New chat title (1-128 characters).

        Returns:
            True if the title was changed successfully.
        """
        result = await self._request("setChatTitle", json_body={
            "chat_id": chat_id,
            "title": title,
        })
        return bool(result)

    @action("Set the description of a chat", dangerous=True)
    async def set_chat_description(
        self, chat_id: str, description: str,
    ) -> bool:
        """Change the description of a group, supergroup, or channel.

        Args:
            chat_id: Unique identifier of the target chat.
            description: New chat description (0-255 characters).

        Returns:
            True if the description was changed successfully.
        """
        result = await self._request("setChatDescription", json_body={
            "chat_id": chat_id,
            "description": description,
        })
        return bool(result)

    @action("Export an invite link for a chat")
    async def export_chat_invite_link(self, chat_id: str) -> str:
        """Generate a new primary invite link for a chat.

        Any previously generated primary link is revoked. The bot must
        be an administrator with the appropriate rights.

        Args:
            chat_id: Unique identifier of the target chat.

        Returns:
            The new invite link as a string.
        """
        result = await self._request(
            "exportChatInviteLink",
            json_body={"chat_id": chat_id},
        )
        return str(result)

    @action("Get the list of administrators in a chat")
    async def get_chat_administrators(
        self, chat_id: str,
    ) -> list[TelegramChatMember]:
        """Get a list of administrators in a chat.

        Args:
            chat_id: Unique identifier of the target chat.

        Returns:
            List of TelegramChatMember objects for each administrator.
        """
        result = await self._request(
            "getChatAdministrators",
            json_body={"chat_id": chat_id},
        )
        admins: list[TelegramChatMember] = []
        for member_data in (result or []):
            user_data = member_data.get("user")
            user = TelegramUser(**user_data) if user_data else None
            admins.append(
                TelegramChatMember(
                    user=user,
                    status=member_data.get("status", ""),
                    custom_title=member_data.get("custom_title"),
                    is_anonymous=member_data.get("is_anonymous"),
                    can_be_edited=member_data.get("can_be_edited"),
                    can_manage_chat=member_data.get("can_manage_chat"),
                    can_delete_messages=member_data.get(
                        "can_delete_messages",
                    ),
                    can_manage_video_chats=member_data.get(
                        "can_manage_video_chats",
                    ),
                    can_restrict_members=member_data.get(
                        "can_restrict_members",
                    ),
                    can_promote_members=member_data.get(
                        "can_promote_members",
                    ),
                    can_change_info=member_data.get("can_change_info"),
                    can_invite_users=member_data.get("can_invite_users"),
                    can_post_messages=member_data.get(
                        "can_post_messages",
                    ),
                    can_edit_messages=member_data.get(
                        "can_edit_messages",
                    ),
                    can_pin_messages=member_data.get("can_pin_messages"),
                    until_date=member_data.get("until_date"),
                )
            )
        return admins
