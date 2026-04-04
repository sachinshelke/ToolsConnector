"""Connector specification — the top-level contract."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from .action import ActionSpec
from .auth import AuthSpec
from .errors import ErrorSpec
from .types import TypeSpec
from .version import SPEC_VERSION


class ConnectorCategory(str, Enum):
    """Categories of tools that connectors integrate with."""

    COMMUNICATION = "communication"
    PROJECT_MANAGEMENT = "project_management"
    CRM = "crm"
    CODE_PLATFORM = "code_platform"
    STORAGE = "storage"
    KNOWLEDGE = "knowledge"
    DATABASE = "database"
    ANALYTICS = "analytics"
    FINANCE = "finance"
    MARKETING = "marketing"
    HR = "hr"
    ECOMMERCE = "ecommerce"
    DEVOPS = "devops"
    SOCIAL = "social"
    MESSAGE_QUEUE = "message_queue"
    SECURITY = "security"
    AI_ML = "ai_ml"
    PRODUCTIVITY = "productivity"
    CUSTOM = "custom"


class ProtocolType(str, Enum):
    """Communication protocols supported by connectors."""

    REST = "rest"
    GRAPHQL = "graphql"
    SOAP = "soap"
    GRPC = "grpc"
    WEBSOCKET = "websocket"
    DATABASE = "database"
    MESSAGE_QUEUE = "message_queue"
    CUSTOM = "custom"


class RateLimitSpec(BaseModel):
    """Rate limit configuration for a connector."""

    rate: int = Field(
        default=60,
        description="Maximum requests per period.",
    )
    period: int = Field(
        default=60,
        description="Period in seconds.",
    )
    burst: int = Field(
        default=10,
        description="Maximum burst above steady-state rate.",
    )
    per_action: dict[str, "RateLimitSpec"] = Field(
        default_factory=dict,
        description="Per-action rate limit overrides.",
    )


class ConnectorSpec(BaseModel):
    """The complete specification of a connector.

    This is the language-agnostic interface contract. In Python, it is
    auto-extracted from connector classes via ``get_spec()``. For other
    language SDKs, it can be authored as standalone YAML/JSON.

    The ConnectorSpec drives:
    - MCP server generation (serve/mcp.py)
    - OpenAI/Anthropic/Gemini schema generation (serve/schema.py)
    - CLI discovery (serve/cli.py)
    - Documentation generation (codegen/docs.py)
    - Conformance testing
    - Multi-language code generation
    """

    spec_version: str = Field(
        default=SPEC_VERSION,
        description="Version of the connector spec format.",
    )
    name: str = Field(description="Machine-readable connector name (e.g., 'gmail').")
    display_name: str = Field(description="Human-readable display name (e.g., 'Gmail').")
    category: ConnectorCategory = Field(description="Tool category.")
    description: str = Field(description="One-paragraph description of the connector.")
    version: str = Field(default="0.1.0", description="Connector implementation version.")

    protocol: ProtocolType = Field(
        default=ProtocolType.REST,
        description="Primary communication protocol.",
    )
    base_url: Optional[str] = Field(
        default=None,
        description="Base URL for API requests.",
    )

    auth: AuthSpec = Field(
        default_factory=AuthSpec,
        description="Supported authentication methods.",
    )
    rate_limits: RateLimitSpec = Field(
        default_factory=RateLimitSpec,
        description="Rate limit configuration.",
    )
    actions: dict[str, ActionSpec] = Field(
        default_factory=dict,
        description="Available actions keyed by method name.",
    )
    events: list[str] = Field(
        default_factory=list,
        description="Event types this connector can emit (v2).",
    )
    types: dict[str, TypeSpec] = Field(
        default_factory=dict,
        description="Custom type definitions used in actions.",
    )
    errors: list[ErrorSpec] = Field(
        default_factory=list,
        description="Possible error types this connector can produce.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional connector metadata.",
    )
