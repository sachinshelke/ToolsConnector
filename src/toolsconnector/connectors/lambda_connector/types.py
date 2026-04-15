"""Pydantic models for AWS Lambda connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class LambdaFunction(BaseModel):
    """An AWS Lambda function."""

    model_config = ConfigDict(frozen=True)

    function_name: str = ""
    function_arn: str = ""
    runtime: str = ""
    role: str = ""
    handler: str = ""
    code_size: int = 0
    description: str = ""
    timeout: int = 0
    memory_size: int = 0
    last_modified: str = ""
    version: str = ""
    state: str = ""
    state_reason: str = ""
    architectures: list[str] = Field(default_factory=list)
    environment: dict[str, Any] = Field(default_factory=dict)
    layers: list[str] = Field(default_factory=list)
    package_type: str = ""


class LambdaFunctionVersion(BaseModel):
    """A published version of a Lambda function."""

    model_config = ConfigDict(frozen=True)

    function_name: str = ""
    function_arn: str = ""
    version: str = ""
    description: str = ""
    runtime: str = ""
    handler: str = ""
    code_size: int = 0
    last_modified: str = ""


class LambdaAlias(BaseModel):
    """An alias pointing to a specific Lambda function version."""

    model_config = ConfigDict(frozen=True)

    alias_arn: str = ""
    name: str = ""
    function_version: str = ""
    description: str = ""


class LambdaInvocationResult(BaseModel):
    """Result of invoking a Lambda function."""

    model_config = ConfigDict(frozen=True)

    status_code: int = 0
    payload: str = ""
    function_error: Optional[str] = None
    log_result: Optional[str] = None
    executed_version: Optional[str] = None
