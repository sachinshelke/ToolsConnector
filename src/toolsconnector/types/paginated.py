"""PaginatedList generic type for universal paginated responses."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Coroutine, Iterator
from typing import Any, Callable, Generic, TypeVar, cast

from pydantic import BaseModel, Field, PrivateAttr

from toolsconnector.types.common import PageState

T = TypeVar("T")


def _run_sync(coro: Coroutine[Any, Any, T]) -> T:
    """Run an async coroutine synchronously.

    Attempts to use the current running event loop if available (via
    ``loop.run_until_complete``). Falls back to ``asyncio.run()`` when
    no loop is running.

    Args:
        coro: The awaitable coroutine to execute.

    Returns:
        The result of the coroutine.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        # We are inside an already-running loop (e.g. Jupyter, some web
        # frameworks).  Create a new thread to avoid deadlocking.
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future: concurrent.futures.Future[T] = pool.submit(asyncio.run, coro)
            return future.result()

    return asyncio.run(coro)


class PaginatedList(BaseModel, Generic[T]):
    """Universal paginated response that works with all pagination strategies.

    ``PaginatedList`` is a generic container returned by every connector
    action that yields multiple results.  It holds the current page of
    items together with the :class:`PageState` needed to fetch subsequent
    pages.

    Both **sync** and **async** consumption patterns are supported:

    Async usage::

        page = await connector.messages.list(limit=50)
        while page is not None:
            for msg in page:
                process(msg)
            page = await page.anext_page()

    Sync usage::

        page = connector.messages.list_sync(limit=50)
        all_items = page.collect_sync(max_items=500)

    Attributes:
        items: The list of items in the current page.
        page_state: Pagination state for fetching subsequent pages.
        total_count: Server-reported total item count, if known.
    """

    items: list[Any] = Field(default_factory=list)
    page_state: PageState = Field(default_factory=PageState)
    total_count: int | None = None

    _fetch_next: Callable[..., Awaitable[PaginatedList[Any]]] | None = PrivateAttr(
        default=None,
    )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def has_more(self) -> bool:
        """Return ``True`` if more pages are available."""
        return self.page_state.has_more

    # ------------------------------------------------------------------
    # Iteration helpers
    # ------------------------------------------------------------------

    def __iter__(self) -> Iterator[Any]:  # type: ignore[override]
        """Iterate over items in the current page.

        Yields:
            Each item in :attr:`items`.
        """
        return iter(self.items)

    def __len__(self) -> int:
        """Return the number of items in the current page."""
        return len(self.items)

    # ------------------------------------------------------------------
    # Async pagination
    # ------------------------------------------------------------------

    async def anext_page(self) -> PaginatedList[Any] | None:
        """Fetch the next page asynchronously.

        Returns:
            The next :class:`PaginatedList` page, or ``None`` if there are
            no more pages or no fetch callback was configured.
        """
        if not self.has_more or self._fetch_next is None:
            return None
        # _fetch_next is Callable[..., Awaitable[PaginatedList[Any]]];
        # mypy loses the precise return type through the Callable->await
        # combo, so cast it back.
        return cast("PaginatedList[Any] | None", await self._fetch_next())

    async def collect(self, max_items: int = 1000, max_pages: int = 10_000) -> list[Any]:
        """Collect items across all remaining pages asynchronously.

        Fetches successive pages until :attr:`has_more` is ``False``,
        ``max_items`` is reached, an empty page is returned, or ``max_pages``
        pages have been fetched.

        Two guards keep a misbehaving upstream from spinning this loop forever
        (a real hazard surfaced by chaos testing — see codevira D000009):

        * **Stall guard** — a page that advertises ``has_more=True`` but returns
          **no items** is treated as terminal. Without this, an upstream that
          keeps returning empty-but-"more" pages (or a ``total`` that's never
          reached) loops indefinitely because ``len(collected)`` never grows.
        * **Page ceiling** — ``max_pages`` bounds the number of fetches outright,
          a backstop against a server that advances forever with tiny non-empty
          pages.

        Args:
            max_items: Maximum total number of items to accumulate.
            max_pages: Maximum number of additional pages to fetch.

        Returns:
            A flat list of items gathered from the current and subsequent
            pages.
        """
        collected: list[Any] = list(self.items[:max_items])
        page: PaginatedList[Any] | None = self
        pages_fetched = 0

        while len(collected) < max_items and pages_fetched < max_pages:
            page = await page.anext_page()  # type: ignore[union-attr]
            if page is None:
                break
            pages_fetched += 1
            if not page.items:
                # Stall guard: an empty page (even with has_more=True) is treated
                # as terminal — otherwise the loop never makes progress.
                break
            remaining = max_items - len(collected)
            collected.extend(page.items[:remaining])

        return collected

    # ------------------------------------------------------------------
    # Sync wrappers
    # ------------------------------------------------------------------

    def next_page(self) -> PaginatedList[Any] | None:
        """Fetch the next page synchronously.

        Convenience wrapper around :meth:`anext_page` for use outside of
        async contexts.

        Returns:
            The next :class:`PaginatedList` page, or ``None`` if there are
            no more pages.
        """
        return _run_sync(self.anext_page())

    def collect_sync(self, max_items: int = 1000, max_pages: int = 10_000) -> list[Any]:
        """Collect items across all remaining pages synchronously.

        Convenience wrapper around :meth:`collect` for use outside of
        async contexts.

        Args:
            max_items: Maximum total number of items to accumulate.
            max_pages: Maximum number of additional pages to fetch (stall/loop
                backstop — see :meth:`collect`).

        Returns:
            A flat list of items gathered from the current and subsequent
            pages.
        """
        return _run_sync(self.collect(max_items=max_items, max_pages=max_pages))
