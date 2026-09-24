"""Unit tests for toolsconnector.serve._credentials."""

from __future__ import annotations

import os
import re

import pytest
import respx

from toolsconnector.errors import MissingConfigError
from toolsconnector.serve import ToolKit
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


@pytest.fixture
def _no_tc_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove every TC_* variable so the developer's shell can't leak in."""
    for key in list(os.environ):
        if key.startswith("TC_"):
            monkeypatch.delenv(key)


@pytest.mark.usefixtures("_no_tc_env")
class TestToolKitCredentialPreflight:
    """A connector that declares it needs credentials is never instantiated
    without them, so it can never send an unauthenticated request."""

    @pytest.mark.asyncio
    async def test_missing_credentials_fail_before_any_request(self) -> None:
        """No credentials -> MissingConfigError naming the env var and where
        to get the key, and zero outbound requests (not ``Bearer None``)."""
        kit = ToolKit(["gmail"])
        # No routes: any outbound request is recorded and auto-answered 200.
        with (
            respx.mock(assert_all_mocked=False, assert_all_called=False) as router,
            pytest.raises(MissingConfigError) as exc_info,
        ):
            await kit.aexecute("gmail_list_emails", {"query": "is:unread"})
        assert router.calls.call_count == 0
        message = str(exc_info.value)
        assert "TC_GMAIL_CREDENTIALS" in message
        assert "https://console.cloud.google.com/apis/credentials" in message

    @pytest.mark.asyncio
    async def test_delimited_error_names_field_order(self) -> None:
        """Delimited credentials show the real shape, not ``your-token``."""
        kit = ToolKit(["twilio"])
        with pytest.raises(MissingConfigError) as exc_info:
            await kit._get_instance("twilio")
        message = str(exc_info.value)
        assert "<account_sid>:<auth_token>" in message
        assert "your-token" not in message
        # Exact match on the extracted URLs, not a substring check (CodeQL
        # py/incomplete-url-substring-sanitization).
        urls = re.findall(r"https://[^\s)'\"]+", message)
        assert any(url == "https://console.twilio.com/" for url in urls), urls

    @pytest.mark.asyncio
    async def test_blank_credential_counts_as_missing(self) -> None:
        """Whitespace would otherwise be sent as ``Bearer    ``."""
        kit = ToolKit(["gmail"], credentials={"gmail": "   "})
        with pytest.raises(MissingConfigError):
            await kit._get_instance("gmail")

    @pytest.mark.asyncio
    async def test_connector_without_auth_still_instantiates(self) -> None:
        """``credential_format == "none"`` connectors need nothing."""
        kit = ToolKit(["webhook"])
        assert await kit._get_instance("webhook") is not None

    @pytest.mark.asyncio
    async def test_provided_credentials_pass_through(self) -> None:
        kit = ToolKit(["gmail"], credentials={"gmail": "ya29.test"})
        assert await kit._get_instance("gmail") is not None
