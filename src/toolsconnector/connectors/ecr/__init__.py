"""AWS ECR connector -- manage container image repositories and lifecycle policies."""

from __future__ import annotations

from .connector import ECR
from .types import (
    ECRAuthorizationData,
    ECRBatchDeleteResult,
    ECRImage,
    ECRLifecyclePolicy,
    ECRRepository,
)

__all__ = [
    "ECR",
    "ECRAuthorizationData",
    "ECRBatchDeleteResult",
    "ECRImage",
    "ECRLifecyclePolicy",
    "ECRRepository",
]
