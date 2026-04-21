"""Stripe connector internal helpers.

Extracted to keep connector.py focused on action definitions.
"""

from __future__ import annotations

from collections.abc import Coroutine
from typing import Any, Callable, Optional, TypeVar

from toolsconnector.types import PageState, PaginatedList

T = TypeVar("T")


def build_page_state(body: dict[str, Any]) -> PageState:
    """Build a PageState from a Stripe list response.

    Args:
        body: Parsed JSON response body from a Stripe list endpoint.

    Returns:
        PageState with cursor set to the last item ID if more pages exist.
    """
    has_more = body.get("has_more", False)
    items = body.get("data", [])
    cursor = items[-1]["id"] if has_more and items else None
    return PageState(has_more=has_more, cursor=cursor)


def build_paginated_result(
    items: list[T],
    body: dict[str, Any],
    fetch_next_factory: Optional[Callable[[str], Coroutine[Any, Any, PaginatedList[T]]]] = None,
) -> PaginatedList[T]:
    """Construct a PaginatedList from parsed items and the raw Stripe response.

    Args:
        items: Already-parsed model instances for the current page.
        body: Raw JSON response body from the Stripe list endpoint.
        fetch_next_factory: A callable that accepts a cursor string and
            returns a coroutine fetching the next page.  Pass ``None``
            to disable auto-pagination.

    Returns:
        A fully wired PaginatedList with ``_fetch_next`` set when more
        pages are available.
    """
    page_state = build_page_state(body)

    result: PaginatedList[T] = PaginatedList(
        items=items,
        page_state=page_state,
        total_count=body.get("total_count"),
    )

    if page_state.has_more and fetch_next_factory is not None:
        result._fetch_next = lambda cursor=page_state.cursor: fetch_next_factory(cursor)
    else:
        result._fetch_next = None

    return result
