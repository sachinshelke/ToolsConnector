"""Unit tests for toolsconnector.serve._filtering."""

from __future__ import annotations

from toolsconnector.connectors.gmail import Gmail
from toolsconnector.serve._filtering import ToolEntry, build_tool_list


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

        delete_count = sum(1 for e in all_entries if e.action_name.startswith("delete_"))
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


class TestDescriptionCarriesDocstringProse:
    """The published tool description must include the docstring usage contract,
    not just the @action title — a model can't read the source, so syntax,
    examples, value formats, and "use X instead" pointers are invisible without
    it (and produce wrong / destructive calls).
    """

    @staticmethod
    def _desc(conn_cls: type, action_suffix: str) -> str:
        by = {e.tool_name: e for e in build_tool_list([conn_cls])}
        for name, entry in by.items():
            if name.endswith(action_suffix):
                return entry.description
        raise AssertionError(f"no tool ending {action_suffix!r}")

    def test_gdrive_search_files_publishes_query_syntax(self) -> None:
        from toolsconnector.connectors.gdrive import GoogleDrive

        d = self._desc(GoogleDrive, "search_files")
        # Headline (title) is still there — backward compatible.
        assert d.startswith("Google Drive: ")
        # The previously-dropped usage contract is now published, incl. a
        # concrete, copyable example — so a model forms a valid Drive query
        # instead of sending a bare "quarterly report" and getting HTTP 400.
        assert "Drive query language" in d
        assert "name contains '" in d

    def test_spot_checks_across_connectors(self) -> None:
        from toolsconnector.connectors.gcalendar import GoogleCalendar
        from toolsconnector.connectors.gdocs import GoogleDocs
        from toolsconnector.connectors.github import GitHub
        from toolsconnector.connectors.gmail import Gmail

        assert "usage shapes" in self._desc(Gmail, "send_email")
        assert "PUT semantics" in self._desc(GoogleCalendar, "update_calendar")
        assert "base64" in self._desc(GitHub, "get_content")
        assert "get_document_text" in self._desc(GoogleDocs, "get_document")

    def test_long_docstring_is_capped_but_keeps_the_key_fact(self) -> None:
        from toolsconnector.connectors.gmail import Gmail

        # gmail.send_email has ~1150 chars of prose (four code-block examples);
        # it must be bounded, but the usage-shape fact survives the cap.
        d = self._desc(Gmail, "send_email")
        assert d.endswith("…"), "long prose should be truncated with an ellipsis"
        assert len(d) < 1000
        assert "usage shapes" in d


class TestBuildDescriptionUnit:
    """Direct unit tests of the description builder + prose truncation."""

    @staticmethod
    def _spec_action(title: str, prose: str):
        from toolsconnector.spec import ActionSpec, ConnectorCategory, ConnectorSpec

        spec = ConnectorSpec(
            name="x", display_name="X", category=ConnectorCategory.CUSTOM, description="d"
        )
        action = ActionSpec(name="do", description=title, long_description=prose)
        return spec, action

    def test_no_prose_returns_clean_headline(self) -> None:
        from toolsconnector.serve._filtering import _build_description

        spec, action = self._spec_action("Do a thing", "")
        # No docstring prose → exactly the old behavior, no trailing separator.
        assert _build_description(spec, action) == "X: Do a thing"

    def test_prose_appended_on_blank_line(self) -> None:
        from toolsconnector.serve._filtering import _build_description

        spec, action = self._spec_action("Do a thing", "Extra contract detail.")
        assert _build_description(spec, action) == "X: Do a thing\n\nExtra contract detail."

    def test_truncate_prose(self) -> None:
        from toolsconnector.serve._filtering import _truncate_prose

        assert _truncate_prose("short", 900) == "short"  # under cap: untouched
        capped = _truncate_prose("Sentence one. " * 100, 100)
        assert capped.endswith("…")
        assert len(capped) <= 104  # cap + boundary slack + ellipsis


class TestAccessAndIdempotentSurfaced:
    """list_tools() must expose the read/write/destructive `access` classification
    and the `idempotent` flag — a positive contract, not a naming heuristic.
    """

    @staticmethod
    def _by_action(conn_cls: type) -> dict:
        return {e.action_name: e for e in build_tool_list([conn_cls])}

    def test_to_dict_exposes_access_and_idempotent(self) -> None:
        d = build_tool_list([Gmail])[0].to_dict()
        assert "access" in d
        assert "idempotent" in d

    def test_dangerous_auto_classified_destructive(self) -> None:
        by = self._by_action(Gmail)
        assert by["send_email"].dangerous is True
        assert by["send_email"].access == "destructive"

    def test_reads_and_writes_are_classified(self) -> None:
        by = self._by_action(Gmail)
        assert by["list_labels"].access == "read"  # GET, no side effect
        assert by["create_label"].access == "write"  # POST create

    def test_unclassified_exposes_write_never_null_or_read(self) -> None:
        # A non-Tier-1 connector is not classified, so its actions must surface
        # the fail-safe "write" default — never null, never "read".
        from toolsconnector.connectors.airtable import Airtable

        entries = build_tool_list([Airtable])
        values = {e.access for e in entries}
        assert None not in values
        assert "read" not in values  # unclassified must not claim read
        assert values <= {"write", "destructive"}
        # to_dict never emits null either
        assert all(d["access"] is not None for d in (e.to_dict() for e in entries))
