"""Unit tests for toolsconnector.serve.toolkit.ToolKit."""

from __future__ import annotations

import pytest

from toolsconnector.errors import ConnectorNotConfiguredError
from toolsconnector.serve.toolkit import ToolKit, ToolKitFactory


class TestToolKitCreation:
    """Tests for ToolKit construction and basic properties."""

    def test_toolkit_creation(self) -> None:
        """Basic creation with connector name strings succeeds."""
        kit = ToolKit(["gmail"])
        assert kit is not None
        assert "gmail" in kit.connector_names

    def test_toolkit_tool_count(self) -> None:
        """tool_count returns the correct number of available tools."""
        kit = ToolKit(["gmail"])
        assert kit.tool_count > 0
        assert kit.tool_count == len(kit)

    def test_toolkit_repr(self) -> None:
        """repr shows connector and tool count."""
        kit = ToolKit(["gmail"])
        r = repr(kit)
        assert "ToolKit" in r
        assert "connectors=" in r
        assert "tools=" in r


class TestToolKitListTools:
    """Tests for ToolKit tool listing and introspection."""

    def test_toolkit_list_tools(self) -> None:
        """list_tools returns a list of dicts with expected keys."""
        kit = ToolKit(["gmail"])
        tools = kit.list_tools()
        assert isinstance(tools, list)
        assert len(tools) > 0
        first = tools[0]
        assert "name" in first
        assert "description" in first
        assert "status" in first

    def test_toolkit_get_tool_schema(self) -> None:
        """get_tool_schema returns the input_schema for a known tool."""
        kit = ToolKit(["gmail"])
        tools = kit.list_tools()
        tool_name = tools[0]["name"]
        schema = kit.get_tool_schema(tool_name)
        assert isinstance(schema, dict)

    def test_toolkit_unknown_tool_raises(self) -> None:
        """get_tool_schema with a bad name raises ConnectorNotConfiguredError."""
        kit = ToolKit(["gmail"])
        with pytest.raises(ConnectorNotConfiguredError, match="Unknown tool"):
            kit.get_tool_schema("nonexistent_action_xyz")

    def test_toolkit_connector_status(self) -> None:
        """get_connector_status returns a dict with connector names as keys."""
        kit = ToolKit(["gmail"])
        status = kit.get_connector_status()
        assert isinstance(status, dict)
        assert "gmail" in status
        assert status["gmail"] == "unknown"


class TestToolKitFiltering:
    """Tests for ToolKit filtering capabilities."""

    def test_toolkit_filtering_exclude_dangerous(self) -> None:
        """exclude_dangerous removes dangerous actions from the toolkit."""
        kit_all = ToolKit(["gmail"])
        kit_safe = ToolKit(["gmail"], exclude_dangerous=True)
        assert kit_safe.tool_count <= kit_all.tool_count
        safe_tools = kit_safe.list_tools()
        assert not any(t.get("dangerous") for t in safe_tools)

    def test_toolkit_filtering_include_actions(self) -> None:
        """include_actions limits tools to matching glob patterns."""
        kit = ToolKit(["gmail"], include_actions=["list_*"])
        tools = kit.list_tools()
        assert len(tools) > 0
        for t in tools:
            action_name = t["action"]
            assert action_name.startswith("list_")


class TestToolKitSchemaGeneration:
    """Tests for multi-framework schema generation."""

    def test_toolkit_openai_schema(self) -> None:
        """to_openai_tools format matches the OpenAI function-calling spec."""
        kit = ToolKit(["gmail"])
        schemas = kit.to_openai_tools()
        assert isinstance(schemas, list)
        assert len(schemas) > 0
        first = schemas[0]
        assert first["type"] == "function"
        assert "function" in first
        assert "name" in first["function"]
        assert "description" in first["function"]
        assert "parameters" in first["function"]

    def test_toolkit_anthropic_schema(self) -> None:
        """to_anthropic_tools format matches the Anthropic tool-use spec."""
        kit = ToolKit(["gmail"])
        schemas = kit.to_anthropic_tools()
        assert isinstance(schemas, list)
        assert len(schemas) > 0
        first = schemas[0]
        assert "name" in first
        assert "description" in first
        assert "input_schema" in first

    def test_toolkit_gemini_schema(self) -> None:
        """to_gemini_tools format matches the Gemini function declaration spec."""
        kit = ToolKit(["gmail"])
        schemas = kit.to_gemini_tools()
        assert isinstance(schemas, list)
        assert len(schemas) > 0
        first = schemas[0]
        assert "name" in first
        assert "description" in first
        assert "parameters" in first


class TestToolKitExecution:
    """Tests for ToolKit execution error paths."""

    @pytest.mark.asyncio
    async def test_toolkit_unknown_tool_raises_on_aexecute(self) -> None:
        """aexecute with a bad tool name raises ConnectorNotConfiguredError."""
        kit = ToolKit(["gmail"])
        with pytest.raises(ConnectorNotConfiguredError, match="Unknown tool"):
            await kit.aexecute("nonexistent_tool_xyz", {})


class _FakeInstance:
    """Stand-in connector instance that records teardown calls."""

    def __init__(self) -> None:
        self.torn_down = False

    async def _teardown(self) -> None:
        self.torn_down = True


class TestToolKitFactory:
    """Tests for per-tenant caching, credential rotation, and eviction."""

    def test_same_credentials_returns_cached_kit(self) -> None:
        """A second call with identical credentials reuses the cached kit."""
        factory = ToolKitFactory(["gmail"])
        kit1 = factory.for_tenant("t1", {"gmail": "tok-A"})
        kit2 = factory.for_tenant("t1", {"gmail": "tok-A"})
        assert kit2 is kit1

    def test_changed_credentials_rebuilds_kit(self) -> None:
        """A rotated token must reach the kit: stale kit is retired, new one built."""
        factory = ToolKitFactory(["gmail"])
        kit1 = factory.for_tenant("t1", {"gmail": "tok-A"})
        stale_instance = _FakeInstance()
        kit1._instances["gmail"] = stale_instance

        kit2 = factory.for_tenant("t1", {"gmail": "tok-B"})

        assert kit2 is not kit1
        assert kit2._credentials["gmail"] == "tok-B"
        assert stale_instance.torn_down, "stale kit's connectors must be torn down"
        assert factory.active_tenants == ["t1"]

    def test_stored_credentials_are_copied(self) -> None:
        """Mutating the caller's dict after the call must not mask a rotation."""
        factory = ToolKitFactory(["gmail"])
        creds = {"gmail": "tok-A"}
        kit1 = factory.for_tenant("t1", creds)
        creds["gmail"] = "tok-B"
        kit2 = factory.for_tenant("t1", creds)
        assert kit2 is not kit1
        assert kit2._credentials["gmail"] == "tok-B"

    def test_max_tenants_evicts_least_recently_used(self) -> None:
        """With max_tenants set, the LRU tenant's kit is retired on overflow."""
        factory = ToolKitFactory(["gmail"], max_tenants=2)
        kit1 = factory.for_tenant("t1", {"gmail": "tok-1"})
        kit2 = factory.for_tenant("t2", {"gmail": "tok-2"})
        evicted_instance = _FakeInstance()
        kit2._instances["gmail"] = evicted_instance

        # Touch t1 so t2 becomes least-recently-used.
        assert factory.for_tenant("t1", {"gmail": "tok-1"}) is kit1

        factory.for_tenant("t3", {"gmail": "tok-3"})

        assert factory.active_tenants == ["t1", "t3"]
        assert evicted_instance.torn_down

    def test_max_tenants_rejects_non_positive(self) -> None:
        """max_tenants below 1 is a configuration error."""
        with pytest.raises(ValueError, match="max_tenants"):
            ToolKitFactory(["gmail"], max_tenants=0)

    @pytest.mark.asyncio
    async def test_close_tenant_clears_cached_credentials(self) -> None:
        """After close_tenant, the same credentials build a fresh kit."""
        factory = ToolKitFactory(["gmail"])
        kit1 = factory.for_tenant("t1", {"gmail": "tok-A"})
        await factory.close_tenant("t1")
        assert factory.active_tenants == []
        kit2 = factory.for_tenant("t1", {"gmail": "tok-A"})
        assert kit2 is not kit1

    @pytest.mark.asyncio
    async def test_retire_inside_event_loop_completes_on_close_all(self) -> None:
        """Retirement scheduled on a running loop finishes by close_all."""
        factory = ToolKitFactory(["gmail"])
        kit1 = factory.for_tenant("t1", {"gmail": "tok-A"})
        stale_instance = _FakeInstance()
        kit1._instances["gmail"] = stale_instance

        kit2 = factory.for_tenant("t1", {"gmail": "tok-B"})
        assert kit2 is not kit1

        await factory.close_all()
        assert stale_instance.torn_down
        assert factory.active_tenants == []
