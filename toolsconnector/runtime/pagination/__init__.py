"""Pagination strategies for the ToolsConnector runtime.

Re-exports
----------
.. autoclass:: PaginationStrategy
.. autoclass:: CursorPagination
.. autoclass:: TokenPagination
.. autoclass:: OffsetPagination
"""

from __future__ import annotations

from toolsconnector.runtime.pagination.base import PaginationStrategy
from toolsconnector.runtime.pagination.cursor import CursorPagination
from toolsconnector.runtime.pagination.offset import OffsetPagination
from toolsconnector.runtime.pagination.token import TokenPagination

__all__ = [
    "CursorPagination",
    "OffsetPagination",
    "PaginationStrategy",
    "TokenPagination",
]
