"""Unit tests for the errors/ module."""

from __future__ import annotations

import json

import pytest

from toolsconnector.errors import (
    ToolsConnectorError,
    AuthError,
    TokenExpiredError,
    InvalidCredentialsError,
    InsufficientScopeError,
    RefreshFailedError,
    APIError,
    RateLimitError,
    NotFoundError,
    ValidationError,
    ServerError,
    TransportError,
    ConnectorError,
    ConnectorNotConfiguredError,
    ConfigError,
    InvalidConfigError,
    MissingConfigError,
)


class TestToolsConnectorError:
    def test_basic_creation(self):
        err = ToolsConnectorError("Something went wrong", connector="gmail")
        assert str(err) is not None
        assert err.connector == "gmail"

    def test_to_dict(self):
        err = ToolsConnectorError(
            "Something failed",
            connector="gmail",
            action="list_emails",
            code="UNKNOWN",
        )
        d = err.to_dict()
        assert isinstance(d, dict)
        assert d["connector"] == "gmail"

    def test_to_json(self):
        err = ToolsConnectorError("Test error", connector="test")
        j = err.to_json()
        parsed = json.loads(j)
        assert "connector" in parsed or "error" in parsed


class TestAuthErrors:
    def test_token_expired(self):
        err = TokenExpiredError("Token expired", connector="gmail")
        assert err.retry_eligible is True
        assert err.code == "AUTH_TOKEN_EXPIRED"

    def test_invalid_credentials(self):
        err = InvalidCredentialsError("Bad creds", connector="gmail")
        assert err.retry_eligible is False

    def test_insufficient_scope(self):
        err = InsufficientScopeError("Need more scope", connector="gmail")
        assert err.retry_eligible is False

    def test_refresh_failed(self):
        err = RefreshFailedError("Refresh failed", connector="gmail")
        assert err.retry_eligible is False


class TestAPIErrors:
    def test_rate_limit(self):
        err = RateLimitError(
            "Too many requests",
            connector="gmail",
            retry_after_seconds=30.0,
        )
        assert err.retry_eligible is True
        assert err.retry_after_seconds == 30.0

    def test_not_found(self):
        err = NotFoundError("Email not found", connector="gmail")
        assert err.retry_eligible is False

    def test_server_error(self):
        err = ServerError("Internal error", connector="gmail")
        assert err.retry_eligible is True


class TestTransportErrors:
    def test_transport_error_retryable(self):
        err = TransportError("Connection lost", connector="gmail")
        assert err.retry_eligible is True


class TestConnectorErrors:
    def test_not_configured(self):
        err = ConnectorNotConfiguredError("No credentials", connector="gmail")
        assert err.retry_eligible is False


class TestConfigErrors:
    def test_missing_config(self):
        err = MissingConfigError("Missing API key", connector="gmail")
        assert err.retry_eligible is False

    def test_invalid_config(self):
        err = InvalidConfigError("Bad format", connector="gmail")
        assert err.retry_eligible is False


class TestErrorHierarchy:
    def test_inheritance(self):
        assert issubclass(AuthError, ToolsConnectorError)
        assert issubclass(TokenExpiredError, AuthError)
        assert issubclass(APIError, ToolsConnectorError)
        assert issubclass(RateLimitError, APIError)
        assert issubclass(TransportError, ToolsConnectorError)
        assert issubclass(ConnectorError, ToolsConnectorError)
        assert issubclass(ConfigError, ToolsConnectorError)

    def test_catch_base(self):
        with pytest.raises(ToolsConnectorError):
            raise RateLimitError("test", connector="test")

    def test_catch_specific(self):
        with pytest.raises(RateLimitError):
            raise RateLimitError("test", connector="test")
