"""Token-based pagination strategy (Google-style pageToken).

Implements the ``pageToken`` / ``nextPageToken`` pattern common across
Google Cloud APIs, Firebase, and similar services.
"""

from __future__ import annotations

from typing import Any

from toolsconnector.types.common import PageState


class TokenPagination:
    """Google-style pageToken pagination.

    Functionally similar to cursor pagination but uses the naming
    conventions established by Google APIs (``pageToken`` /
    ``nextPageToken`` / ``items``).

    Args:
        token_param: Request parameter name for the page token.
            Defaults to ``"pageToken"``.
        token_field: Response field containing the next page token.
            Defaults to ``"nextPageToken"``.
        items_field: Response field containing the page items.
            Defaults to ``"items"``.
    """

    def __init__(
        self,
        token_param: str = "pageToken",
        token_field: str = "nextPageToken",
        items_field: str = "items",
    ) -> None:
        """Initialize token pagination settings.

        Args:
            token_param: Request parameter name for the token.
            token_field: Response field name for the next token.
            items_field: Response field name for the items list.
        """
        self._token_param = token_param
        self._token_field = token_field
        self._items_field = items_field

    def get_page_params(self, page_state: PageState) -> dict[str, Any]:
        """Build request params from the current page token.

        Args:
            page_state: Current pagination state.  The token is stored
                in :attr:`PageState.cursor`.

        Returns:
            A dict containing the token parameter if a token is
            present, or an empty dict for the first page.
        """
        if page_state.cursor:
            return {self._token_param: page_state.cursor}
        return {}

    def parse_page_info(
        self,
        response_data: Any,
        response_headers: dict[str, str],
    ) -> PageState:
        """Extract the next page token from the response.

        Args:
            response_data: Decoded response body (expected to be a
                dict).
            response_headers: HTTP response headers (unused for token
                pagination).

        Returns:
            A :class:`PageState` with the next token stored as
            ``cursor`` and ``has_more`` set accordingly.
        """
        next_token: str | None = None

        if isinstance(response_data, dict):
            next_token = response_data.get(self._token_field)

        return PageState(
            cursor=next_token,
            has_more=bool(next_token),
        )
