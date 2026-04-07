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
