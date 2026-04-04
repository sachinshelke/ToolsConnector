"""Unit tests for toolsconnector.serve._validation."""

from __future__ import annotations

import pytest

from toolsconnector.serve._validation import validate_arguments


class TestValidateArguments:
    """Tests for lightweight JSON Schema argument validation."""

    def test_valid_arguments(self) -> None:
        """No errors returned when arguments match the schema."""
        schema = {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "description": "Max results"},
            },
            "required": ["query"],
        }
        errors = validate_arguments(schema, {"query": "is:unread", "limit": 10})
        assert errors == []

    def test_missing_required_field(self) -> None:
        """Catches missing required parameters."""
        schema = {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
            },
            "required": ["query"],
        }
        errors = validate_arguments(schema, {})
        assert len(errors) == 1
        assert "query" in errors[0]
        assert "Missing required" in errors[0]

    def test_wrong_type_string_for_int(self) -> None:
        """Catches type mismatch when a string is passed for an integer field."""
        schema = {
            "type": "object",
            "properties": {
                "limit": {"type": "integer"},
            },
        }
        errors = validate_arguments(schema, {"limit": "not_a_number"})
        assert len(errors) == 1
        assert "integer" in errors[0]

    def test_invalid_enum_value(self) -> None:
        """Catches values not in the allowed enum list."""
        schema = {
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "enum": ["full", "minimal", "metadata"],
                },
            },
        }
        errors = validate_arguments(schema, {"format": "invalid_choice"})
        assert len(errors) == 1
        assert "must be one of" in errors[0]

    def test_extra_fields_allowed(self) -> None:
        """Unknown fields do not produce validation errors."""
        schema = {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
            },
        }
        errors = validate_arguments(schema, {"query": "test", "extra_field": 42})
        assert errors == []

    def test_nullable_field_accepts_none(self) -> None:
        """None passes validation for any typed field (nullable by default)."""
        schema = {
            "type": "object",
            "properties": {
                "page_token": {"type": "string"},
            },
        }
        errors = validate_arguments(schema, {"page_token": None})
        assert errors == []

    def test_empty_schema_accepts_anything(self) -> None:
        """An empty schema imposes no constraints."""
        errors = validate_arguments({}, {"any_key": "any_value", "count": 5})
        assert errors == []
