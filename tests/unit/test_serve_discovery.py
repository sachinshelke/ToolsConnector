"""Unit tests for toolsconnector.serve._discovery."""

from __future__ import annotations

import pytest

from toolsconnector.errors import ConnectorNotConfiguredError
from toolsconnector.serve._discovery import (
    get_connector_class,
    list_connectors,
    resolve_connectors,
)


class TestListConnectors:
    """Tests for the list_connectors registry function."""

    def test_list_connectors_returns_53(self) -> None:
        """Verify the registry contains exactly 53 connectors."""
        connectors = list_connectors()
        assert len(connectors) >= 53

    def test_list_connectors_sorted(self) -> None:
        """Verify the list is returned in alphabetical order."""
        connectors = list_connectors()
        assert connectors == sorted(connectors)


class TestGetConnectorClass:
    """Tests for lazily importing connector classes by name."""

    def test_get_connector_class_gmail(self) -> None:
        """Verify get_connector_class returns the Gmail class."""
        cls = get_connector_class("gmail")
        from toolsconnector.connectors.gmail import Gmail

        assert cls is Gmail

    def test_get_connector_class_unknown_raises(self) -> None:
        """Verify ConnectorNotConfiguredError with suggestion for unknown names."""
        with pytest.raises(ConnectorNotConfiguredError, match="Unknown connector") as exc_info:
            get_connector_class("not_a_real_connector")
        assert exc_info.value.suggestion is not None
        assert "list_connectors()" in exc_info.value.suggestion

    def test_get_connector_class_has_get_spec(self) -> None:
        """Verify the returned class has a callable get_spec classmethod."""
        cls = get_connector_class("gmail")
        assert hasattr(cls, "get_spec")
        spec = cls.get_spec()
        assert spec.name == "gmail"


class TestResolveConnectors:
    """Tests for resolving mixed lists of strings and classes."""

    def test_resolve_connectors_strings(self) -> None:
        """Resolve a list of connector name strings to classes."""
        from toolsconnector.connectors.gmail import Gmail
        from toolsconnector.connectors.slack import Slack

        classes = resolve_connectors(["gmail", "slack"])
        assert len(classes) == 2
        assert classes[0] is Gmail
        assert classes[1] is Slack

    def test_resolve_connectors_mixed(self) -> None:
        """Resolve a mix of strings and class objects."""
        from toolsconnector.connectors.gmail import Gmail

        classes = resolve_connectors(["slack", Gmail])
        assert len(classes) == 2
        assert classes[1] is Gmail

    def test_resolve_connectors_class_passthrough(self) -> None:
        """Class objects passed directly should come through unchanged."""
        from toolsconnector.connectors.gmail import Gmail

        classes = resolve_connectors([Gmail])
        assert len(classes) == 1
        assert classes[0] is Gmail
