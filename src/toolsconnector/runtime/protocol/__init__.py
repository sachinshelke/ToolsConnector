"""Protocol adapter layer -- wire-protocol abstractions.

Re-exports
----------
.. autoclass:: ProtocolAdapter
.. autoclass:: ProtocolResponse
.. autoclass:: RESTAdapter
.. autoclass:: GraphQLAdapter
.. autoclass:: WebSocketAdapter
"""

from __future__ import annotations

from .base import ProtocolAdapter, ProtocolResponse
from .graphql import GraphQLAdapter
from .rest import RESTAdapter
from .websocket import WebSocketAdapter

__all__ = [
    "ProtocolAdapter",
    "ProtocolResponse",
    "RESTAdapter",
    "GraphQLAdapter",
    "WebSocketAdapter",
]
