"""Unit tests for toolsconnector.serve._credentials."""

from __future__ import annotations

import pytest

from toolsconnector.errors import MissingConfigError
from toolsconnector.serve._credentials import (
    require_credentials,
    resolve_credentials,
)


class TestResolveCredentials:
    """Tests for the multi-source credential resolution logic."""

    def test_resolve_from_overrides(self) -> None:
        """Dict override takes priority over everything else."""
        result = resolve_credentials(
            "gmail",
            overrides={"gmail": "override-token"},
        )
        assert result == "override-token"

    def test_resolve_from_env_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """TC_GMAIL_CREDENTIALS env var is resolved correctly."""
        monkeypatch.setenv("TC_GMAIL_CREDENTIALS", "cred-from-env")
        result = resolve_credentials("gmail")
        assert result == "cred-from-env"

    def test_resolve_from_env_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """TC_GMAIL_API_KEY env var is resolved correctly."""
        monkeypatch.setenv("TC_GMAIL_API_KEY", "api-key-from-env")
        result = resolve_credentials("gmail")
        assert result == "api-key-from-env"

    def test_resolve_from_env_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """TC_GMAIL_TOKEN env var is resolved correctly."""
        monkeypatch.setenv("TC_GMAIL_TOKEN", "token-from-env")
        result = resolve_credentials("gmail")
        assert result == "token-from-env"

    def test_resolve_returns_none_when_missing(self) -> None:
        """Returns None when no credential source is available."""
        result = resolve_credentials("gmail")
        assert result is None

    def test_resolve_priority_order(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify priority: override > CREDENTIALS > API_KEY > TOKEN."""
        monkeypatch.setenv("TC_GMAIL_CREDENTIALS", "cred-env")
        monkeypatch.setenv("TC_GMAIL_API_KEY", "api-key-env")
        monkeypatch.setenv("TC_GMAIL_TOKEN", "token-env")

        # Override wins over everything
        result = resolve_credentials("gmail", overrides={"gmail": "override"})
        assert result == "override"

        # Without override, CREDENTIALS wins
        result = resolve_credentials("gmail")
        assert result == "cred-env"

        # Without CREDENTIALS, API_KEY wins
        monkeypatch.delenv("TC_GMAIL_CREDENTIALS")
        result = resolve_credentials("gmail")
        assert result == "api-key-env"

        # Without API_KEY, TOKEN is last
        monkeypatch.delenv("TC_GMAIL_API_KEY")
        result = resolve_credentials("gmail")
        assert result == "token-env"


class TestRequireCredentials:
    """Tests for require_credentials which raises on missing."""

    def test_require_credentials_raises_with_suggestion(self) -> None:
        """MissingConfigError includes TC_ env var names in the suggestion."""
        with pytest.raises(MissingConfigError, match="No credentials found") as exc_info:
            require_credentials("gmail")
        assert exc_info.value.suggestion is not None
        assert "TC_GMAIL" in exc_info.value.suggestion
