"""ToolsConnector Runtime Engine.

The execution layer that powers all connectors. Provides:
- BaseConnector: Abstract base class for connector implementations.
- @action: Decorator that marks methods as externally-callable actions.
- Auth providers: Pluggable authentication (OAuth2, API key, etc.).
- Protocol adapters: REST, GraphQL, etc.
- Middleware: Request pipeline (retry, rate limit, auth, logging).
- Pagination: Strategy-based pagination handling.
"""

from .action import ActionMeta, action, get_actions
from .base import BaseConnector, HealthStatus
from .context import ActionContext

__all__ = [
    "action",
    "ActionMeta",
    "get_actions",
    "BaseConnector",
    "HealthStatus",
    "ActionContext",
]
