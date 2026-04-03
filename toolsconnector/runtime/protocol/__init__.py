"""Protocol adapter layer -- wire-protocol abstractions.

Re-exports
----------
.. autoclass:: ProtocolAdapter
.. autoclass:: ProtocolResponse
.. autoclass:: RESTAdapter
"""

from __future__ import annotations

from .base import ProtocolAdapter, ProtocolResponse
from .rest import RESTAdapter

__all__ = [
    "ProtocolAdapter",
    "ProtocolResponse",
    "RESTAdapter",
]
