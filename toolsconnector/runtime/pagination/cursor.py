"""Cursor-based pagination strategy.

Implements the common cursor/next-cursor pattern used by APIs such as
Slack, Notion, and many GraphQL endpoints.
"""

from __future__ import annotations

from typing import Any

from toolsconnector.types.common import PageState


class CursorPagination:
    """Cursor-based pagination.

    Reads an opaque cursor token from the response and passes it back
    as a query parameter on subsequent requests.

    Args:
        cursor_param: Name of the request parameter that carries the
            cursor.  Defaults to ``"cursor"``.
        cursor_field: Key in the response body that contains the next
            cursor value.  Defaults to ``"next_cursor"``.
    """

    def __init__(
        self,
        cursor_param: str = "cursor",
        cursor_field: str = "next_cursor",
    ) -> None:
        """Initialize cursor pagination settings.

        Args:
            cursor_param: Request parameter name for the cursor.
            cursor_field: Response field name containing the next cursor.
        """
        self._cursor_param = cursor_param
        self._cursor_field = cursor_field

    def get_page_params(self, page_state: PageState) -> dict[str, Any]:
        """Build request params from the current cursor.

        Args:
            page_state: Current pagination state.

        Returns:
            A dict containing the cursor parameter if a cursor is
            present, or an empty dict for the first page.
        """
        if page_state.cursor:
            return {self._cursor_param: page_state.cursor}
        return {}

    def parse_page_info(
        self,
        response_data: Any,
        response_headers: dict[str, str],
    ) -> PageState:
        """Extract the next cursor from the response.

        Args:
            response_data: Decoded response body (expected to be a
                dict).
            response_headers: HTTP response headers (unused for cursor
                pagination).

        Returns:
            A :class:`PageState` with the next cursor and
            ``has_more`` set accordingly.
        """
        next_cursor: str | None = None

        if isinstance(response_data, dict):
            next_cursor = response_data.get(self._cursor_field)

        return PageState(
            cursor=next_cursor,
            has_more=bool(next_cursor),
        )
