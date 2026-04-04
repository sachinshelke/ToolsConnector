"""Unit tests for toolsconnector.serve._filtering."""

from __future__ import annotations

import pytest

from toolsconnector.serve._filtering import ToolEntry, build_tool_list
from toolsconnector.connectors.gmail import Gmail


class TestBuildToolList:
    """Tests for building ToolEntry lists from connector classes."""

    def test_build_tool_list_basic(self) -> None:
        """Verify ToolEntry objects are created from Gmail's actions."""
        entries = build_tool_list([Gmail])
        assert len(entries) > 0
        assert all(isinstance(e, ToolEntry) for e in entries)

    def test_tool_name_format(self) -> None:
        """Verify tool names follow the '{connector}_{action}' format."""
        entries = build_tool_list([Gmail])
        for entry in entries:
            assert entry.tool_name == f"{entry.connector_name}_{entry.action_name}"
            assert entry.tool_name.startswith("gmail_")

    def test_description_has_connector_context(self) -> None:
        """Verify descriptions include the 'Gmail:' prefix for context."""
        entries = build_tool_list([Gmail])
        for entry in entries:
            assert entry.description.startswith("Gmail:")

    def test_exclude_dangerous(self) -> None:
        """Dangerous actions are filtered out when exclude_dangerous=True."""
        all_entries = build_tool_list([Gmail])
        safe_entries = build_tool_list([Gmail], exclude_dangerous=True)

        dangerous_count = sum(1 for e in all_entries if e.dangerous)
        assert dangerous_count > 0, "Gmail should have at least one dangerous action"
        assert len(safe_entries) == len(all_entries) - dangerous_count
        assert not any(e.dangerous for e in safe_entries)

    def test_include_actions_glob(self) -> None:
        """include_actions=['list_*'] filters to only list_ actions."""
        entries = build_tool_list([Gmail], include_actions=["list_*"])
        assert len(entries) > 0
        for entry in entries:
            assert entry.action_name.startswith("list_")

    def test_exclude_actions_glob(self) -> None:
        """exclude_actions=['delete_*'] filters out delete_ actions."""
        all_entries = build_tool_list([Gmail])
        filtered = build_tool_list([Gmail], exclude_actions=["delete_*"])

        delete_count = sum(
            1 for e in all_entries if e.action_name.startswith("delete_")
        )
        assert delete_count > 0, "Gmail should have at least one delete action"
        assert len(filtered) == len(all_entries) - delete_count
        assert not any(e.action_name.startswith("delete_") for e in filtered)

    def test_combined_filters(self) -> None:
        """include + exclude work together correctly."""
        # Include only list_ and get_ actions, but exclude get_email
        entries = build_tool_list(
            [Gmail],
            include_actions=["list_*", "get_*"],
            exclude_actions=["get_email"],
        )
        for entry in entries:
            assert entry.action_name.startswith(("list_", "get_"))
            assert entry.action_name != "get_email"


class TestToolEntry:
    """Tests for the ToolEntry dataclass."""

    def test_tool_entry_to_dict(self) -> None:
        """Verify to_dict serialization contains all expected keys."""
        entries = build_tool_list([Gmail])
        assert len(entries) > 0
        d = entries[0].to_dict()

        assert "connector" in d
        assert "connector_display_name" in d
        assert "action" in d
        assert "name" in d
        assert "description" in d
        assert "input_schema" in d
        assert "dangerous" in d
        assert "requires_scope" in d
