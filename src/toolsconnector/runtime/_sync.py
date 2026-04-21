"""Sync/async bridge utility.

Provides ``run_sync()`` to call async functions from synchronous code.
Handles the case where an event loop may or may not already be running.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from typing import Any, TypeVar

T = TypeVar("T")

# A dedicated background thread + event loop for running async code
# from synchronous contexts when an event loop is already running.
_background_loop: asyncio.AbstractEventLoop | None = None
_background_thread: threading.Thread | None = None
_lock = threading.Lock()


def _get_background_loop() -> asyncio.AbstractEventLoop:
    """Get or create the background event loop running in a daemon thread."""
    global _background_loop, _background_thread

    if _background_loop is not None and _background_loop.is_running():
        return _background_loop

    with _lock:
        if _background_loop is not None and _background_loop.is_running():
            return _background_loop

        _background_loop = asyncio.new_event_loop()

        def _run_loop() -> None:
            asyncio.set_event_loop(_background_loop)
            _background_loop.run_forever()  # type: ignore[union-attr]

        _background_thread = threading.Thread(
            target=_run_loop,
            daemon=True,
            name="toolsconnector-sync-bridge",
        )
        _background_thread.start()
        return _background_loop


def run_sync(coro: Coroutine[Any, Any, T]) -> T:
    """Run an async coroutine synchronously.

    Always dispatches to a long-lived background-thread event loop so
    that async resources (httpx clients, connection pools, cached
    connector instances) can survive across multiple sync calls.

    Rationale:
        An earlier version used ``asyncio.run()`` when no loop was
        active. That creates a fresh loop per call and closes it after
        the coroutine returns. ``ToolKit`` caches connector instances
        (including their ``httpx.AsyncClient``) across calls, so the
        second ``kit.execute()`` would try to use a client whose
        transport was bound to the closed first loop, raising
        ``RuntimeError: Event loop is closed`` during response cleanup.

        Using a single persistent background loop means the cached
        httpx transports stay bound to a loop that never closes for
        the process lifetime — cache + sync API now compose correctly.

    Args:
        coro: The coroutine to execute.

    Returns:
        The coroutine's return value.

    Raises:
        RuntimeError: If called from inside a coroutine running on the
            background loop itself (would deadlock). Use ``await`` there.
    """
    bg_loop = _get_background_loop()

    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None

    if running is bg_loop:
        raise RuntimeError(
            "run_sync() called from inside the background async loop; use 'await' directly instead."
        )

    future = asyncio.run_coroutine_threadsafe(coro, bg_loop)
    return future.result()
