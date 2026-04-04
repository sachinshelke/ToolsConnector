"""Sync/async bridge utility.

Provides ``run_sync()`` to call async functions from synchronous code.
Handles the case where an event loop may or may not already be running.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Coroutine, TypeVar

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

    Detects whether an event loop is already running:
    - If no loop is running: uses ``asyncio.run()``.
    - If a loop is already running (e.g., inside Jupyter, FastAPI):
      dispatches to a background thread's event loop.

    Args:
        coro: The coroutine to execute.

    Returns:
        The coroutine's return value.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is None:
        # No event loop running — safe to use asyncio.run()
        return asyncio.run(coro)
    else:
        # Event loop already running — dispatch to background thread
        bg_loop = _get_background_loop()
        future = asyncio.run_coroutine_threadsafe(coro, bg_loop)
        return future.result()
