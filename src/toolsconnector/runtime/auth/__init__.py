"""Runtime authentication providers and manager.

Public API
----------
.. autosummary::

    AuthProvider
    AuthState
    AuthManager
    APIKeyProvider
    BearerTokenProvider
    BasicAuthProvider
    OAuth2Provider
"""

from __future__ import annotations

from .api_key import APIKeyProvider
from .base import AuthProvider, AuthState
from .basic import BasicAuthProvider
from .bearer import BearerTokenProvider
from .manager import AuthManager
from .oauth2 import OAuth2Provider

__all__ = [
    # Protocol & state
    "AuthProvider",
    "AuthState",
    # Manager
    "AuthManager",
    # Concrete providers
    "APIKeyProvider",
    "BearerTokenProvider",
    "BasicAuthProvider",
    "OAuth2Provider",
]
