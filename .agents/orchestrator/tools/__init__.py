"""Tool definitions for agent sessions.

Re-exports the combined ``ALL_TOOLS`` list so callers can do::

    from .tools import ALL_TOOLS
"""

from __future__ import annotations

from typing import Any

from .filesystem import FILESYSTEM_TOOLS
from .shell import SHELL_TOOLS
from .git import GIT_TOOLS
from .test import TEST_TOOLS

ALL_TOOLS: list[dict[str, Any]] = [
    *FILESYSTEM_TOOLS,
    *SHELL_TOOLS,
    *GIT_TOOLS,
    *TEST_TOOLS,
]

__all__ = [
    "ALL_TOOLS",
    "FILESYSTEM_TOOLS",
    "SHELL_TOOLS",
    "GIT_TOOLS",
    "TEST_TOOLS",
]
