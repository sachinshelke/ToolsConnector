"""Action specification types."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from .pagination import PaginationSpec


class ParameterSpec(BaseModel):
    """Specification for a single action parameter.

    Derived from Python type hints and docstrings at class definition time.
    """

    name: str = Field(description="Parameter name.")
    type: str = Field(description="JSON Schema type (string, integer, etc.).")
    description: str = Field(default="", description="Human-readable description.")
    required: bool = Field(default=True, description="Whether this parameter is required.")
    default: Any = Field(default=None, description="Default value if not required.")
    enum: Optional[list[Any]] = Field(
        default=None, description="Allowed values (enum constraint)."
    )
    format: Optional[str] = Field(
        default=None, description="Format hint (e.g., 'email', 'date-time', 'uri')."
    )
    items: Optional[dict[str, Any]] = Field(
        default=None, description="Schema for array items (if type is 'array')."
    )
    nullable: bool = Field(default=False, description="Whether None/null is allowed.")


class ActionSpec(BaseModel):
    """Specification for a single connector action.

    Captures everything needed to:
    - Call the action from Python
    - Generate MCP tool definition
    - Generate OpenAI/Anthropic/Gemini function schema
    - Generate documentation
    """

    name: str = Field(description="Method name (e.g., 'list_emails').")
    description: str = Field(description="Human-readable description of what this action does.")
    parameters: list[ParameterSpec] = Field(
        default_factory=list,
        description="Input parameters for this action.",
    )
    input_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="Full JSON Schema for the action input.",
    )
    output_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="JSON Schema for the action return type.",
    )
    return_type: str = Field(
        default="Any",
        description="Python return type annotation as string.",
    )
    requires_scope: Optional[str] = Field(
        default=None,
        description="OAuth scope name required for this action.",
    )
    dangerous: bool = Field(
        default=False,
        description="Whether this action has destructive side effects (delete, send, etc.).",
    )
    idempotent: bool = Field(
        default=False,
        description="Whether this action is safe to retry.",
    )
    pagination: Optional[PaginationSpec] = Field(
        default=None,
        description="Pagination configuration if this action returns a list.",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Categorization tags for this action.",
    )
    rate_limit_weight: int = Field(
        default=1,
        description="How many rate limit tokens this action costs.",
    )
    deprecated: bool = Field(
        default=False,
        description="Whether this action is deprecated.",
    )
    deprecation_message: Optional[str] = Field(
        default=None,
        description="Message to show if action is deprecated.",
    )
