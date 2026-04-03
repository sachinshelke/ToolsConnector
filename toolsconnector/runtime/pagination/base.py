"""Base pagination strategy protocol.

Defines the :class:`PaginationStrategy` interface that all concrete
pagination implementations must satisfy.
"""

from __future__ import annotations

from typing import Any, Protocol

from toolsconnector.types.common import PageState


class PaginationStrategy(Protocol):
    """Protocol for pagination strategies.

    Each strategy translates between ToolsConnector's generic
    :class:`PageState` and the API-specific parameters / response
    fields used by a particular pagination scheme.
    """

    def get_page_params(self, page_state: PageState) -> dict[str, Any]:
        """Build API request parameters from the current page state.

        Args:
            page_state: The current pagination state.

        Returns:
            A dict of query parameters (or body fields) to include
            in the next API request.
        """
        ...

    def parse_page_info(
        self,
        response_data: Any,
        response_headers: dict[str, str],
    ) -> PageState:
        """Extract pagination metadata from an API response.

        Args:
            response_data: The decoded response body (typically a
                dict parsed from JSON).
            response_headers: HTTP response headers.

        Returns:
            A new :class:`PageState` reflecting the position after
            this page.
        """
        ...
