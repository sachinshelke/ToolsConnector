"""Unit tests for toolsconnector.serve.toolkit.ToolKit."""

from __future__ import annotations

import json

import pytest
import respx

from toolsconnector.errors import ConnectorNotConfiguredError, ValidationError
from toolsconnector.serve import list_connectors
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


class TestDryRun:
    """``dry_run=True`` never reaches the network for anything but a declared read."""

    @staticmethod
    async def _dry_run(tool: str, arguments: dict, connector: str) -> tuple[dict, int]:
        kit = ToolKit([connector], credentials={connector: "test-token"})
        # No routes: any outbound request is recorded and auto-answered 200.
        with respx.mock(assert_all_mocked=False, assert_all_called=False) as router:
            result = await kit.aexecute(tool, arguments, dry_run=True)
            # Read inside the block: respx clears its call log on exit.
            calls = router.calls.call_count
        return json.loads(result), calls

    @pytest.mark.asyncio
    async def test_destructive_action_is_previewed(self) -> None:
        preview, calls = await self._dry_run("gmail_batch_delete", {"email_ids": ["m1"]}, "gmail")
        assert preview["dry_run"] is True
        assert calls == 0

    @pytest.mark.asyncio
    async def test_non_dangerous_write_is_previewed(self) -> None:
        preview, calls = await self._dry_run("gmail_mark_as_read", {"email_id": "m1"}, "gmail")
        assert preview["dry_run"] is True
        assert preview["access"] == "write"
        assert calls == 0

    @pytest.mark.asyncio
    async def test_unclassified_action_is_previewed(self) -> None:
        """No declared access means the action might write, so it must not run."""
        preview, calls = await self._dry_run("slack_leave_channel", {"channel": "C1"}, "slack")
        assert preview["dry_run"] is True
        assert calls == 0

    @pytest.mark.asyncio
    async def test_declared_read_still_executes(self) -> None:
        kit = ToolKit(["gmail"], credentials={"gmail": "test-token"})
        with respx.mock(assert_all_mocked=False, assert_all_called=False) as router:
            router.get(path__regex=r".*/labels$").respond(json={"labels": []})
            await kit.aexecute("gmail_list_labels", {}, dry_run=True)
            assert router.calls.call_count == 1

    @pytest.mark.asyncio
    async def test_arguments_are_validated(self) -> None:
        """A preview of a call that could never succeed is a false green."""
        kit = ToolKit(["gmail"], credentials={"gmail": "test-token"})
        with pytest.raises(ValidationError):
            await kit.aexecute("gmail_batch_delete", {}, dry_run=True)

    def test_every_non_read_tool_is_previewed(self) -> None:
        """Catalog-wide: only a declared read may run under dry_run."""
        kit = ToolKit(list_connectors())
        runs = [e for e in kit._tool_entries_list if not kit._previews_in_dry_run(e)]
        assert runs
        assert {e.access for e in runs} == {"read"}
        assert not any(e.dangerous for e in runs)


class TestJsonStringArguments:
    """OpenAI hands tool arguments over as a JSON string; the README passes
    ``tool_call.function.arguments`` straight to ``execute``."""

    def test_json_string_is_parsed(self) -> None:
        kit = ToolKit(["gmail"], credentials={"gmail": "test-token"})
        preview = kit.execute("gmail_batch_delete", '{"email_ids": ["m1"]}', dry_run=True)
        assert json.loads(preview)["arguments"] == {"email_ids": ["m1"]}

    @pytest.mark.parametrize("bad", ["{not json", "[1, 2]", "null"])
    def test_anything_but_a_json_object_is_rejected(self, bad: str) -> None:
        kit = ToolKit(["gmail"], credentials={"gmail": "test-token"})
        with pytest.raises(ValidationError, match="JSON object"):
            kit.execute("gmail_batch_delete", bad, dry_run=True)

    def test_empty_string_means_no_arguments(self) -> None:
        """Some models send ``""`` for a tool that takes no arguments."""
        kit = ToolKit(["gmail"], credentials={"gmail": "test-token"})
        with pytest.raises(ValidationError, match="Missing required parameter"):
            kit.execute("gmail_batch_delete", "", dry_run=True)
