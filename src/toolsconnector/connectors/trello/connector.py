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

from ._parsers import parse_board, parse_card, parse_comment, parse_list
from .types import TrelloBoard, TrelloCard, TrelloComment, TrelloList

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
    description = (
        "Connect to Trello to manage boards, lists, "
        "cards, and comments."
    )
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
            method, path, params=merged_params, json=json_body,
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
            "GET", f"/members/{member}/boards",
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
            "PUT", f"/cards/{card_id}", params=params,
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
            "POST", f"/cards/{card_id}/actions/comments",
            params={"text": text},
        )
        return parse_comment(resp.json())
