"""Unit tests for all connectors.

Verifies that every connector:
1. Imports correctly
2. Has a valid get_spec()
3. Has the right name and category
4. Has at least 1 action
5. All actions have descriptions
6. All actions have input_schema with type=object
7. Dangerous actions are properly flagged
8. Can be instantiated without credentials
9. Has sync wrappers for all actions
"""

from __future__ import annotations

import json

import pytest

from toolsconnector.serve._discovery import get_connector_class, list_connectors


ALL_CONNECTORS = list_connectors()


# ---------------------------------------------------------------------------
# 1. Import & class basics
# ---------------------------------------------------------------------------


class TestAllConnectorsImport:
    """Every registered connector must import without errors."""

    @pytest.mark.parametrize("name", ALL_CONNECTORS)
    def test_connector_imports(self, name: str) -> None:
        cls = get_connector_class(name)
        assert cls is not None

    @pytest.mark.parametrize("name", ALL_CONNECTORS)
    def test_connector_has_get_spec(self, name: str) -> None:
        cls = get_connector_class(name)
        assert hasattr(cls, "get_spec")

    @pytest.mark.parametrize("name", ALL_CONNECTORS)
    def test_connector_has_get_actions(self, name: str) -> None:
        cls = get_connector_class(name)
        assert hasattr(cls, "get_actions")


# ---------------------------------------------------------------------------
# 2. ConnectorSpec contract
# ---------------------------------------------------------------------------


class TestAllConnectorsSpec:
    """Every connector must produce a valid spec."""

    @pytest.mark.parametrize("name", ALL_CONNECTORS)
    def test_spec_has_name(self, name: str) -> None:
        cls = get_connector_class(name)
        spec = cls.get_spec()
        assert spec.name, f"{name}: spec.name is empty"

    @pytest.mark.parametrize("name", ALL_CONNECTORS)
    def test_spec_name_matches_registry(self, name: str) -> None:
        cls = get_connector_class(name)
        spec = cls.get_spec()
        assert spec.name == name, (
            f"Registry key '{name}' != spec.name '{spec.name}'"
        )

    @pytest.mark.parametrize("name", ALL_CONNECTORS)
    def test_spec_has_display_name(self, name: str) -> None:
        cls = get_connector_class(name)
        spec = cls.get_spec()
        assert spec.display_name, f"{name}: display_name is empty"

    @pytest.mark.parametrize("name", ALL_CONNECTORS)
    def test_spec_has_description(self, name: str) -> None:
        cls = get_connector_class(name)
        spec = cls.get_spec()
        assert spec.description, f"{name}: description is empty"

    @pytest.mark.parametrize("name", ALL_CONNECTORS)
    def test_spec_has_actions(self, name: str) -> None:
        cls = get_connector_class(name)
        spec = cls.get_spec()
        assert len(spec.actions) > 0, f"{name}: no actions"

    @pytest.mark.parametrize("name", ALL_CONNECTORS)
    def test_spec_has_category(self, name: str) -> None:
        cls = get_connector_class(name)
        spec = cls.get_spec()
        assert spec.category, f"{name}: category is empty"

    @pytest.mark.parametrize("name", ALL_CONNECTORS)
    def test_spec_has_protocol(self, name: str) -> None:
        cls = get_connector_class(name)
        spec = cls.get_spec()
        assert spec.protocol, f"{name}: protocol is empty"


# ---------------------------------------------------------------------------
# 3. Action metadata
# ---------------------------------------------------------------------------


class TestAllConnectorsActions:
    """Every action must have proper metadata."""

    @pytest.mark.parametrize("name", ALL_CONNECTORS)
    def test_actions_have_descriptions(self, name: str) -> None:
        cls = get_connector_class(name)
        spec = cls.get_spec()
        for action_name, action in spec.actions.items():
            assert action.description, (
                f"{name}.{action_name}: action has no description"
            )

    @pytest.mark.parametrize("name", ALL_CONNECTORS)
    def test_actions_have_input_schema(self, name: str) -> None:
        cls = get_connector_class(name)
        spec = cls.get_spec()
        for action_name, action in spec.actions.items():
            schema = action.input_schema
            assert isinstance(schema, dict), (
                f"{name}.{action_name}: input_schema is not a dict"
            )
            assert schema.get("type") == "object", (
                f"{name}.{action_name}: input_schema type is not 'object'"
            )

    @pytest.mark.parametrize("name", ALL_CONNECTORS)
    def test_actions_have_names(self, name: str) -> None:
        cls = get_connector_class(name)
        spec = cls.get_spec()
        for action_name, action in spec.actions.items():
            assert action.name, (
                f"{name}.{action_name}: action.name is empty"
            )
            assert action.name == action_name, (
                f"{name}: action key '{action_name}' != action.name '{action.name}'"
            )

    @pytest.mark.parametrize("name", ALL_CONNECTORS)
    def test_dangerous_flag_is_bool(self, name: str) -> None:
        cls = get_connector_class(name)
        spec = cls.get_spec()
        for action_name, action in spec.actions.items():
            assert isinstance(action.dangerous, bool), (
                f"{name}.{action_name}: dangerous is not bool"
            )


# ---------------------------------------------------------------------------
# 4. Instantiation (no credentials required)
# ---------------------------------------------------------------------------


class TestAllConnectorsInstantiation:
    """Every connector must be instantiable without credentials."""

    @pytest.mark.parametrize("name", ALL_CONNECTORS)
    def test_connector_instantiates(self, name: str) -> None:
        cls = get_connector_class(name)
        instance = cls()
        assert instance is not None

    @pytest.mark.parametrize("name", ALL_CONNECTORS)
    def test_connector_has_sync_wrappers(self, name: str) -> None:
        cls = get_connector_class(name)
        instance = cls()
        spec = cls.get_spec()
        for action_name in spec.actions:
            assert hasattr(instance, action_name), (
                f"{name}: missing sync wrapper for {action_name}"
            )

    @pytest.mark.parametrize("name", ALL_CONNECTORS)
    def test_connector_repr(self, name: str) -> None:
        cls = get_connector_class(name)
        instance = cls()
        r = repr(instance)
        assert name in r, f"{name}: repr does not contain connector name"


# ---------------------------------------------------------------------------
# 5. JSON serialisation round-trip
# ---------------------------------------------------------------------------


class TestAllConnectorsJsonSchema:
    """Spec must serialize to valid JSON."""

    @pytest.mark.parametrize("name", ALL_CONNECTORS)
    def test_spec_serializes_to_json(self, name: str) -> None:
        cls = get_connector_class(name)
        spec = cls.get_spec()
        j = spec.model_dump_json()
        parsed = json.loads(j)
        assert parsed["name"] == spec.name

    @pytest.mark.parametrize("name", ALL_CONNECTORS)
    def test_spec_model_dump_has_actions(self, name: str) -> None:
        cls = get_connector_class(name)
        spec = cls.get_spec()
        data = spec.model_dump()
        assert "actions" in data
        assert len(data["actions"]) == len(spec.actions)


# ---------------------------------------------------------------------------
# 6. Aggregate count validations
# ---------------------------------------------------------------------------


class TestConnectorCounts:
    """Verify overall connector counts."""

    def test_total_connector_count(self) -> None:
        assert len(ALL_CONNECTORS) == 50

    def test_total_action_count(self) -> None:
        total = 0
        for name in ALL_CONNECTORS:
            cls = get_connector_class(name)
            spec = cls.get_spec()
            total += len(spec.actions)
        assert total == 395

    def test_dangerous_actions_exist(self) -> None:
        """At least some actions should be marked dangerous."""
        dangerous_count = 0
        for name in ALL_CONNECTORS:
            cls = get_connector_class(name)
            spec = cls.get_spec()
            for action in spec.actions.values():
                if action.dangerous:
                    dangerous_count += 1
        assert dangerous_count > 50, (
            f"Only {dangerous_count} dangerous actions -- expected 50+"
        )

    def test_all_categories_covered(self) -> None:
        """Connectors should span multiple categories."""
        categories = set()
        for name in ALL_CONNECTORS:
            cls = get_connector_class(name)
            spec = cls.get_spec()
            categories.add(spec.category.value)
        assert len(categories) >= 8, (
            f"Only {len(categories)} categories -- expected 8+"
        )

    def test_no_duplicate_connector_names(self) -> None:
        """Each connector spec.name must be unique."""
        seen: dict[str, str] = {}
        for name in ALL_CONNECTORS:
            cls = get_connector_class(name)
            spec = cls.get_spec()
            assert spec.name not in seen, (
                f"Duplicate spec.name '{spec.name}': {name} vs {seen[spec.name]}"
            )
            seen[spec.name] = name
