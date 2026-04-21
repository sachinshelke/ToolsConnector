"""Trello connector -- boards, lists, cards, and comments.

Uses the Trello REST API v1 with API key + token query-parameter auth.
Trello does not use standard pagination for most list endpoints; results
are returned in full up to the API limit.
"""

from __future__ import annotations

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

from ._parsers import (
    parse_action,
    parse_attachment,
    parse_board,
    parse_card,
    parse_comment,
    parse_label,
    parse_list,
    parse_member,
)
from .types import (
    TrelloAction,
    TrelloAttachment,
    TrelloBoard,
    TrelloCard,
    TrelloComment,
    TrelloLabel,
    TrelloList,
    TrelloMember,
)

logger = logging.getLogger("toolsconnector.trello")


class Trello(BaseConnector):
    """Connect to Trello to manage boards, lists, cards, and comments.

    Supports API key + token authentication via query parameters.
    Credentials format: ``api_key:token``.
    """

    name = "trello"
    display_name = "Trello"
    category = ConnectorCategory.PROJECT_MANAGEMENT
    protocol = ProtocolType.REST
    base_url = "https://api.trello.com/1"
    description = "Connect to Trello to manage boards, lists, cards, and comments."
    _rate_limit_config = RateLimitSpec(rate=100, period=10, burst=30)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Initialise the httpx async client with Trello auth params.

        Parses credentials as ``api_key:token`` and injects them as
        default query parameters on every request.
        """
        creds = self._credentials or ":"
        parts = creds.split(":", 1)
        self._api_key = parts[0]
        self._token = parts[1] if len(parts) > 1 else ""

        self._client = httpx.AsyncClient(
            base_url=self._base_url or self.__class__.base_url,
            headers={
                "Accept": "application/json",
            },
            timeout=self._timeout,
        )

    async def _teardown(self) -> None:
        """Close the httpx client."""
        if hasattr(self, "_client"):
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _auth_params(self) -> dict[str, str]:
        """Return query parameters for Trello authentication.

        Returns:
            Dict with ``key`` and ``token`` parameters.
        """
        return {"key": self._api_key, "token": self._token}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[dict[str, Any]] = None,
    ) -> httpx.Response:
        """Send an authenticated request to the Trello API.

        Args:
            method: HTTP method (GET, POST, PUT, etc.).
            path: API path relative to base_url.
            params: Additional query parameters.
            json_body: JSON body for POST/PUT requests.

        Returns:
            httpx.Response object.

        Raises:
            httpx.HTTPStatusError: On 4xx/5xx responses.
        """
        merged_params = {**self._auth_params(), **(params or {})}

        resp = await self._client.request(
            method,
            path,
            params=merged_params,
            json=json_body,
        )
        resp.raise_for_status()
        return resp

    # ------------------------------------------------------------------
    # Actions -- Boards
    # ------------------------------------------------------------------

    @action("List boards for a Trello member")
    async def list_boards(
        self,
        member: str = "me",
    ) -> PaginatedList[TrelloBoard]:
        """List boards accessible by the specified member.

        Args:
            member: Member ID or ``me`` for the authenticated user.

        Returns:
            List of TrelloBoard objects (no pagination required).
        """
        resp = await self._request(
            "GET",
            f"/members/{member}/boards",
            params={"fields": "all"},
        )
        items = [parse_board(b) for b in resp.json()]

        return PaginatedList(
            items=items,
            page_state=PageState(has_more=False),
        )

    @action("Get a single Trello board by ID")
    async def get_board(self, board_id: str) -> TrelloBoard:
        """Retrieve a single board by its ID.

        Args:
            board_id: The Trello board ID.

        Returns:
            TrelloBoard object.
        """
        resp = await self._request("GET", f"/boards/{board_id}")
        return parse_board(resp.json())

    # ------------------------------------------------------------------
    # Actions -- Lists
    # ------------------------------------------------------------------

    @action("List all lists on a Trello board")
    async def list_lists(self, board_id: str) -> PaginatedList[TrelloList]:
        """List all lists on a board.

        Args:
            board_id: The Trello board ID.

        Returns:
            List of TrelloList objects.
        """
        resp = await self._request("GET", f"/boards/{board_id}/lists")
        items = [parse_list(lst) for lst in resp.json()]

        return PaginatedList(
            items=items,
            page_state=PageState(has_more=False),
        )

    # ------------------------------------------------------------------
    # Actions -- Cards
    # ------------------------------------------------------------------

    @action("List cards in a Trello list")
    async def list_cards(self, list_id: str) -> PaginatedList[TrelloCard]:
        """List all cards in a specific list.

        Args:
            list_id: The Trello list ID.

        Returns:
            List of TrelloCard objects.
        """
        resp = await self._request("GET", f"/lists/{list_id}/cards")
        items = [parse_card(c) for c in resp.json()]

        return PaginatedList(
            items=items,
            page_state=PageState(has_more=False),
        )

    @action("Get a single Trello card by ID")
    async def get_card(self, card_id: str) -> TrelloCard:
        """Retrieve a single card by its ID.

        Args:
            card_id: The Trello card ID.

        Returns:
            TrelloCard object.
        """
        resp = await self._request("GET", f"/cards/{card_id}")
        return parse_card(resp.json())

    @action("Create a new Trello card", dangerous=True)
    async def create_card(
        self,
        list_id: str,
        name: str,
        desc: Optional[str] = None,
    ) -> TrelloCard:
        """Create a new card in the specified list.

        Args:
            list_id: The list ID where the card will be created.
            name: Card name/title.
            desc: Optional card description.

        Returns:
            The created TrelloCard object.
        """
        params: dict[str, Any] = {"idList": list_id, "name": name}
        if desc is not None:
            params["desc"] = desc

        resp = await self._request("POST", "/cards", params=params)
        return parse_card(resp.json())

    @action("Update a Trello card", dangerous=True)
    async def update_card(
        self,
        card_id: str,
        name: Optional[str] = None,
        desc: Optional[str] = None,
        list_id: Optional[str] = None,
    ) -> TrelloCard:
        """Update an existing card's properties.

        Args:
            card_id: The Trello card ID to update.
            name: New card name.
            desc: New card description.
            list_id: Move card to a different list.

        Returns:
            The updated TrelloCard object.
        """
        params: dict[str, Any] = {}
        if name is not None:
            params["name"] = name
        if desc is not None:
            params["desc"] = desc
        if list_id is not None:
            params["idList"] = list_id

        resp = await self._request(
            "PUT",
            f"/cards/{card_id}",
            params=params,
        )
        return parse_card(resp.json())

    @action("Add a comment to a Trello card", dangerous=True)
    async def add_comment(
        self,
        card_id: str,
        text: str,
    ) -> TrelloComment:
        """Add a comment to a card.

        Args:
            card_id: The Trello card ID.
            text: Comment text.

        Returns:
            The created TrelloComment action.
        """
        resp = await self._request(
            "POST",
            f"/cards/{card_id}/actions/comments",
            params={"text": text},
        )
        return parse_comment(resp.json())

    # ------------------------------------------------------------------
    # Actions -- Card management (extended)
    # ------------------------------------------------------------------

    @action("Delete a Trello card", dangerous=True)
    async def delete_card(self, card_id: str) -> bool:
        """Permanently delete a Trello card.

        Args:
            card_id: The Trello card ID to delete.

        Returns:
            True if the card was deleted successfully.
        """
        resp = await self._request("DELETE", f"/cards/{card_id}")
        return resp.status_code == 200

    @action("Add a label to a Trello card")
    async def add_label(self, card_id: str, label_id: str) -> bool:
        """Add an existing label to a card.

        Args:
            card_id: The Trello card ID.
            label_id: The label ID to add.

        Returns:
            True if the label was added successfully.
        """
        await self._request(
            "POST",
            f"/cards/{card_id}/idLabels",
            params={"value": label_id},
        )
        return True

    # ------------------------------------------------------------------
    # Actions -- Board members
    # ------------------------------------------------------------------

    @action("List members of a Trello board")
    async def list_members(self, board_id: str) -> list[TrelloMember]:
        """List all members of a board.

        Args:
            board_id: The Trello board ID.

        Returns:
            List of TrelloMember objects.
        """
        resp = await self._request("GET", f"/boards/{board_id}/members")
        return [
            TrelloMember(
                id=m.get("id", ""),
                username=m.get("username"),
                full_name=m.get("fullName"),
                initials=m.get("initials"),
                avatar_url=m.get("avatarUrl"),
                url=m.get("url"),
            )
            for m in resp.json()
        ]

    # ------------------------------------------------------------------
    # Actions -- Lists
    # ------------------------------------------------------------------

    @action("Create a new list on a Trello board", dangerous=True)
    async def create_list(
        self,
        board_id: str,
        name: str,
    ) -> TrelloList:
        """Create a new list on a board.

        Args:
            board_id: The Trello board ID.
            name: Name for the new list.

        Returns:
            The created TrelloList object.
        """
        resp = await self._request(
            "POST",
            "/lists",
            params={"name": name, "idBoard": board_id},
        )
        return parse_list(resp.json())

    # ------------------------------------------------------------------
    # Actions -- Labels
    # ------------------------------------------------------------------

    @action("List all labels on a Trello board")
    async def list_labels(
        self,
        board_id: str,
    ) -> list[TrelloLabel]:
        """List all labels defined on a board.

        Args:
            board_id: The Trello board ID.

        Returns:
            List of TrelloLabel objects.
        """
        resp = await self._request("GET", f"/boards/{board_id}/labels")
        return [parse_label(lb) for lb in resp.json()]

    @action("Create a label on a Trello board", dangerous=True)
    async def create_label(
        self,
        board_id: str,
        name: str,
        color: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create a new label on a board.

        Args:
            board_id: The Trello board ID.
            name: Label name.
            color: Label colour (e.g. ``"green"``, ``"red"``,
                ``"blue"``). Pass ``None`` for no colour.

        Returns:
            Dict with the created label data including ``id``,
            ``name``, and ``color``.
        """
        params: dict[str, Any] = {
            "name": name,
            "idBoard": board_id,
        }
        if color is not None:
            params["color"] = color

        resp = await self._request("POST", "/labels", params=params)
        return resp.json()

    # ------------------------------------------------------------------
    # Actions -- Card movement
    # ------------------------------------------------------------------

    @action("Move a Trello card to a different list", dangerous=True)
    async def move_card(
        self,
        card_id: str,
        list_id: str,
    ) -> TrelloCard:
        """Move a card to a different list.

        Args:
            card_id: The Trello card ID to move.
            list_id: The destination list ID.

        Returns:
            The updated TrelloCard object in its new list.
        """
        resp = await self._request(
            "PUT",
            f"/cards/{card_id}",
            params={"idList": list_id},
        )
        return parse_card(resp.json())

    # ------------------------------------------------------------------
    # Actions -- Card attachments
    # ------------------------------------------------------------------

    @action("List attachments on a Trello card")
    async def list_attachments(
        self,
        card_id: str,
    ) -> list[TrelloAttachment]:
        """List all attachments on a card.

        Args:
            card_id: The Trello card ID.

        Returns:
            List of TrelloAttachment objects.
        """
        resp = await self._request(
            "GET",
            f"/cards/{card_id}/attachments",
        )
        return [parse_attachment(a) for a in resp.json()]

    @action("Add an attachment to a Trello card", dangerous=True)
    async def add_attachment(
        self,
        card_id: str,
        url: Optional[str] = None,
        name: Optional[str] = None,
    ) -> dict[str, Any]:
        """Add a URL attachment to a card.

        Args:
            card_id: The Trello card ID.
            url: URL to attach to the card.
            name: Display name for the attachment.

        Returns:
            Dict with the created attachment data.
        """
        params: dict[str, Any] = {}
        if url is not None:
            params["url"] = url
        if name is not None:
            params["name"] = name

        resp = await self._request(
            "POST",
            f"/cards/{card_id}/attachments",
            params=params,
        )
        return resp.json()

    # ------------------------------------------------------------------
    # Actions -- Board members (alias)
    # ------------------------------------------------------------------

    @action("List members of a Trello board")
    async def list_board_members(
        self,
        board_id: str,
    ) -> list[TrelloMember]:
        """List all members of a board.

        This is an alias for ``list_members`` with a clearer name
        when working alongside card-level member endpoints.

        Args:
            board_id: The Trello board ID.

        Returns:
            List of TrelloMember objects.
        """
        resp = await self._request(
            "GET",
            f"/boards/{board_id}/members",
        )
        return [parse_member(m) for m in resp.json()]

    # ------------------------------------------------------------------
    # Actions -- List operations (extended)
    # ------------------------------------------------------------------

    @action("Get a single Trello list by ID")
    async def get_list(self, list_id: str) -> TrelloList:
        """Retrieve a single list by its ID.

        Args:
            list_id: The Trello list ID.

        Returns:
            TrelloList object.
        """
        resp = await self._request("GET", f"/lists/{list_id}")
        return parse_list(resp.json())

    @action("Archive a Trello list", dangerous=True)
    async def archive_list(self, list_id: str) -> TrelloList:
        """Archive (close) a Trello list.

        Archived lists are hidden from the board but not deleted.

        Args:
            list_id: The Trello list ID to archive.

        Returns:
            The archived TrelloList object.
        """
        resp = await self._request(
            "PUT",
            f"/lists/{list_id}/closed",
            params={"value": "true"},
        )
        return parse_list(resp.json())

    # ------------------------------------------------------------------
    # Actions -- Card actions (activity log)
    # ------------------------------------------------------------------

    @action("List actions (activity log) on a Trello card")
    async def list_card_actions(
        self,
        card_id: str,
    ) -> list[TrelloAction]:
        """List the action history (activity log) for a card.

        Returns all actions including comments, moves, and updates.

        Args:
            card_id: The Trello card ID.

        Returns:
            List of TrelloAction objects.
        """
        resp = await self._request(
            "GET",
            f"/cards/{card_id}/actions",
        )
        return [parse_action(a) for a in resp.json()]

    # ------------------------------------------------------------------
    # Actions -- Card archiving
    # ------------------------------------------------------------------

    @action("Archive a Trello card", dangerous=True)
    async def archive_card(self, card_id: str) -> TrelloCard:
        """Archive (close) a Trello card.

        Archived cards are hidden from the board but not deleted.

        Args:
            card_id: The Trello card ID to archive.

        Returns:
            The archived TrelloCard object.
        """
        resp = await self._request(
            "PUT",
            f"/cards/{card_id}",
            params={"closed": "true"},
        )
        return parse_card(resp.json())

    @action("Unarchive a Trello card")
    async def unarchive_card(self, card_id: str) -> TrelloCard:
        """Unarchive (reopen) a previously archived Trello card.

        Args:
            card_id: The Trello card ID to unarchive.

        Returns:
            The unarchived TrelloCard object.
        """
        resp = await self._request(
            "PUT",
            f"/cards/{card_id}",
            params={"closed": "false"},
        )
        return parse_card(resp.json())

    # ------------------------------------------------------------------
    # Actions -- Checklists
    # ------------------------------------------------------------------

    @action("List checklists on a Trello card")
    async def list_checklists(
        self,
        card_id: str,
    ) -> list[dict[str, Any]]:
        """List all checklists on a card.

        Args:
            card_id: The Trello card ID.

        Returns:
            List of checklist dicts with id, name, checkItems, etc.
        """
        resp = await self._request(
            "GET",
            f"/cards/{card_id}/checklists",
        )
        return resp.json() if isinstance(resp.json(), list) else []

    @action("Create a checklist on a Trello card", dangerous=True)
    async def create_checklist(
        self,
        card_id: str,
        name: str,
    ) -> dict[str, Any]:
        """Create a new checklist on a card.

        Args:
            card_id: The Trello card ID.
            name: Name for the new checklist.

        Returns:
            Dict with the created checklist details.
        """
        resp = await self._request(
            "POST",
            "/checklists",
            params={"idCard": card_id, "name": name},
        )
        return resp.json()
