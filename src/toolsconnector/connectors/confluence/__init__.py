"""Confluence connector -- manage pages and spaces via the Atlassian v2 API."""

from __future__ import annotations

from .connector import Confluence
from .types import (
    ConfluenceComment,
    ConfluenceLabel,
    ConfluencePage,
    ConfluenceSpace,
    ConfluenceVersion,
)

__all__ = [
    "Confluence",
    "ConfluenceComment",
    "ConfluenceLabel",
    "ConfluencePage",
    "ConfluenceSpace",
    "ConfluenceVersion",
]
