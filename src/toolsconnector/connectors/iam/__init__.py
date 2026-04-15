"""AWS IAM connector -- manage IAM roles, policies, users, and access keys."""

from __future__ import annotations

from .connector import IAM
from .types import (
    IAMAccessKey,
    IAMAttachedPolicy,
    IAMInstanceProfile,
    IAMPolicy,
    IAMRole,
    IAMUser,
)

__all__ = [
    "IAM",
    "IAMAccessKey",
    "IAMAttachedPolicy",
    "IAMInstanceProfile",
    "IAMPolicy",
    "IAMRole",
    "IAMUser",
]
