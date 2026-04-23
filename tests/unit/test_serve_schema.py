"""Unit tests for toolsconnector.serve.schema."""

from __future__ import annotations

import pytest

from toolsconnector.connectors.gmail import Gmail
from toolsconnector.serve._filtering import build_tool_list
from toolsconnector.serve.schema import (
    to_anthropic_schema,
    to_gemini_schema,
    to_openai_schema,
)


@pytest.fixture
def gmail_tool_entries():
    """Build the tool entries for Gmail once per test session."""
    return build_tool_list([Gmail])


class TestOpenAISchema:
    """Tests for OpenAI function-calling schema generation."""

    def test_openai_schema_format(self, gmail_tool_entries) -> None:
        """Verify top-level structure: type=function, function.name, function.parameters."""
        entry = gmail_tool_entries[0]
        schema = to_openai_schema(entry)
        assert schema["type"] == "function"
        assert "function" in schema
        func = schema["function"]
        assert "name" in func
        assert "description" in func
        assert "parameters" in func

    def test_schema_has_description(self, gmail_tool_entries) -> None:
        """Verify the OpenAI schema description is non-empty."""
        entry = gmail_tool_entries[0]
        schema = to_openai_schema(entry)
        assert len(schema["function"]["description"]) > 0


class TestAnthropicSchema:
    """Tests for Anthropic tool-use schema generation."""

    def test_anthropic_schema_format(self, gmail_tool_entries) -> None:
        """Verify structure: name, description, input_schema."""
        entry = gmail_tool_entries[0]
        schema = to_anthropic_schema(entry)
        assert "name" in schema
        assert "description" in schema
        assert "input_schema" in schema

    def test_schema_has_description(self, gmail_tool_entries) -> None:
        """Verify the Anthropic schema description is non-empty."""
        entry = gmail_tool_entries[0]
        schema = to_anthropic_schema(entry)
        assert len(schema["description"]) > 0


class TestGeminiSchema:
    """Tests for Google Gemini function declaration schema generation."""

    def test_gemini_schema_format(self, gmail_tool_entries) -> None:
        """Verify structure: name, description, parameters."""
        entry = gmail_tool_entries[0]
        schema = to_gemini_schema(entry)
        assert "name" in schema
        assert "description" in schema
        assert "parameters" in schema

    def test_schema_has_description(self, gmail_tool_entries) -> None:
        """Verify the Gemini schema description is non-empty."""
        entry = gmail_tool_entries[0]
        schema = to_gemini_schema(entry)
        assert len(schema["description"]) > 0


class TestSchemaToolNameFormat:
    """Cross-format tests for tool name consistency."""

    def test_schema_tool_name_format(self, gmail_tool_entries) -> None:
        """Tool names match {connector}_{action} across all schema formats."""
        for entry in gmail_tool_entries:
            openai = to_openai_schema(entry)
            anthropic = to_anthropic_schema(entry)
            gemini = to_gemini_schema(entry)

            expected = f"{entry.connector_name}_{entry.action_name}"
            assert openai["function"]["name"] == expected
            assert anthropic["name"] == expected
            assert gemini["name"] == expected
