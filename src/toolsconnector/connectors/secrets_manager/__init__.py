"""AWS Secrets Manager connector -- store, rotate, and retrieve secrets."""

from __future__ import annotations

from .connector import SecretsManager
from .types import (
    SMSecret,
    SMSecretValue,
    SMSecretVersion,
)

__all__ = [
    "SecretsManager",
    "SMSecret",
    "SMSecretValue",
    "SMSecretVersion",
]
