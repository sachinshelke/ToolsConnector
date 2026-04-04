"""Segment connector -- event tracking and source/destination management."""

from __future__ import annotations

from .connector import Segment
from .types import SegmentDestination, SegmentEvent, SegmentSource

__all__ = [
    "Segment",
    "SegmentDestination",
    "SegmentEvent",
    "SegmentSource",
]
