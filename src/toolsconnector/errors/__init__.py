"""ToolsConnector Runtime Errors.

Structured exception hierarchy for all connector operations.
Each error carries machine-readable metadata (code, retry eligibility,
suggestion) suitable for both human debugging and AI agent routing.

Hierarchy
---------
ToolsConnectorError
    AuthError
        TokenExpiredError
        InvalidCredentialsError
        InsufficientScopeError
        RefreshFailedError
    APIError
        RateLimitError
        NotFoundError
        ValidationError
        ConflictError
        PermissionDeniedError
        ServerError
    TransportError
        TimeoutError
        ConnectionError
        DNSError
    ConnectorError
        ConnectorNotConfiguredError
        ConnectorInitError
        ActionNotFoundError
    ConfigError
        InvalidConfigError
        MissingConfigError
"""

from .api import (
    APIError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    ValidationError,
)
from .auth import (
    AuthError,
    InsufficientScopeError,
    InvalidCredentialsError,
    RefreshFailedError,
    TokenExpiredError,
)
from .base import ToolsConnectorError
from .config import ConfigError, InvalidConfigError, MissingConfigError
from .connector import (
    ActionNotFoundError,
    ConnectorError,
    ConnectorInitError,
    ConnectorNotConfiguredError,
)
from .transport import ConnectionError, DNSError, TimeoutError, TransportError

__all__ = [
    # Base
    "ToolsConnectorError",
    # Auth
    "AuthError",
    "TokenExpiredError",
    "InvalidCredentialsError",
    "InsufficientScopeError",
    "RefreshFailedError",
    # API
    "APIError",
    "RateLimitError",
    "NotFoundError",
    "ValidationError",
    "ConflictError",
    "PermissionDeniedError",
    "ServerError",
    # Transport
    "TransportError",
    "TimeoutError",
    "ConnectionError",
    "DNSError",
    # Connector
    "ConnectorError",
    "ConnectorNotConfiguredError",
    "ConnectorInitError",
    "ActionNotFoundError",
    # Config
    "ConfigError",
    "InvalidConfigError",
    "MissingConfigError",
]
