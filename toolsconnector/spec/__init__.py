"""ToolsConnector Specification Types.

Pure Pydantic V2 models defining the language-agnostic connector contract.
No implementation logic — just types. These drive schema generation,
MCP serving, documentation, and multi-language code generation.
"""

from .action import ActionSpec, ParameterSpec
from .auth import (
    APIKeySpec,
    AuthProviderSpec,
    AuthSpec,
    AuthType,
    OAuthSpec,
    ScopeSet,
    ServiceAccountSpec,
)
from .connector import (
    ConnectorCategory,
    ConnectorSpec,
    ProtocolType,
    RateLimitSpec,
)
from .errors import ErrorCode, ErrorSpec
from .pagination import PaginationSpec, PaginationStrategyType
from .types import TypeSpec
from .version import SPEC_VERSION

__all__ = [
    # Connector
    "ConnectorSpec",
    "ConnectorCategory",
    "ProtocolType",
    "RateLimitSpec",
    # Action
    "ActionSpec",
    "ParameterSpec",
    # Auth
    "AuthSpec",
    "AuthProviderSpec",
    "AuthType",
    "OAuthSpec",
    "ScopeSet",
    "ServiceAccountSpec",
    "APIKeySpec",
    # Pagination
    "PaginationSpec",
    "PaginationStrategyType",
    # Errors
    "ErrorSpec",
    "ErrorCode",
    # Types
    "TypeSpec",
    # Version
    "SPEC_VERSION",
]
