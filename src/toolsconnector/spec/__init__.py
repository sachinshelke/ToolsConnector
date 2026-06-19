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
from .binding import (
    ActionBinding,
    AuthKind,
    ConnectorBinding,
    ContextVar,
    EndpointBinding,
    Location,
    PaginationBinding,
    PaginationKind,
    ParamBinding,
    PathVariant,
    Style,
)
from .connector import (
    ConnectorCategory,
    ConnectorSpec,
    ProtocolType,
    RateLimitSpec,
)
from .errors import ErrorCode, ErrorSpec
from .executor import build_request, next_request
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
    # Binding (HTTP-binding IR — drives the runtime executor + multi-language codegen)
    "ActionBinding",
    "ConnectorBinding",
    "EndpointBinding",
    "ParamBinding",
    "PathVariant",
    "PaginationBinding",
    "ContextVar",
    "Location",
    "Style",
    "AuthKind",
    "PaginationKind",
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
    # Executor (binding-driven request builder)
    "build_request",
    "next_request",
]
