"""Offset-based pagination strategy.

Implements the classic ``offset`` + ``limit`` pattern where the client
advances through a result set by incrementing a numeric offset.
"""

from __future__ import annotations

from typing import Any, Optional

from toolsconnector.types.common import PageState


class OffsetPagination:
    """Offset/limit pagination.

    Calculates ``has_more`` by comparing ``offset + limit`` against the
    ``total`` count returned in the API response.  The current offset is
    read from the response body if the API echoes it; otherwise the
    strategy tracks it via an internal counter that increments by
    ``limit`` on each call to :meth:`parse_page_info`.

    Args:
        offset_param: Request parameter name for the offset.
            Defaults to ``"offset"``.
        limit_param: Request parameter name for the page size.
            Defaults to ``"limit"``.
        total_field: Response field containing the total item count.
            Defaults to ``"total"``.
        limit: Default page size.  Defaults to ``50``.
    """

    def __init__(
        self,
        offset_param: str = "offset",
        limit_param: str = "limit",
        total_field: str = "total",
        limit: int = 50,
    ) -> None:
        """Initialize offset pagination settings.

        Args:
            offset_param: Request parameter name for the offset.
            limit_param: Request parameter name for the limit.
            total_field: Response field for total item count.
            limit: Default page size.
        """
        self._offset_param = offset_param
        self._limit_param = limit_param
        self._total_field = total_field
        self._limit = limit
        self._current_offset: int = 0

    def get_page_params(self, page_state: PageState) -> dict[str, Any]:
        """Build request params from the current offset.

        Args:
            page_state: Current pagination state.

        Returns:
            A dict containing the offset and limit parameters.
        """
        offset = page_state.offset if page_state.offset is not None else 0
        self._current_offset = offset
        return {
            self._offset_param: offset,
            self._limit_param: self._limit,
        }

    def parse_page_info(
        self,
        response_data: Any,
        response_headers: dict[str, str],
    ) -> PageState:
        """Calculate next offset and has_more from the response.

        Uses the offset from the most recent :meth:`get_page_params`
        call and advances it by ``limit``.

        Args:
            response_data: Decoded response body (expected to be a
                dict containing a total count field).
            response_headers: HTTP response headers (unused for offset
                pagination).

        Returns:
            A :class:`PageState` with the next offset,
            ``total_count``, and ``has_more`` computed from
            ``offset + limit`` vs ``total``.
        """
        total: Optional[int] = None
        if isinstance(response_data, dict):
            raw_total = response_data.get(self._total_field)
            if raw_total is not None:
                total = int(raw_total)

        # Advance from the offset used in the request.
        next_offset = self._current_offset + self._limit

        has_more = False
        if total is not None:
            has_more = next_offset < total

        return PageState(
            offset=next_offset,
            total_count=total,
            has_more=has_more,
        )
