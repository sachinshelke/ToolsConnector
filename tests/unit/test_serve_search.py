"""Tool search: ranking, the risk split, and what reaches the wire."""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

import pytest

from toolsconnector.errors import ConnectorNotConfiguredError, ValidationError
from toolsconnector.serve import ToolKit, list_connectors
from toolsconnector.serve.search import RISKS, ToolIndex, risk_of, search_tool_definitions

# Everyday requests and the tools that would each be a right answer.
GOLDEN: list[tuple[str, set[str]]] = [
    ("send an email with gmail", {"gmail_send_email"}),
    ("post a message in slack", {"slack_send_message"}),
    ("slack list channels", {"slack_list_channels"}),
    ("open a github issue", {"github_create_issue"}),
    ("github list commits", {"github_list_commits"}),
    ("create a google calendar event", {"gcalendar_create_event"}),
    ("create a jira ticket", {"jira_create_issue"}),
    ("refund a stripe charge", {"stripe_refund_charge"}),
    ("cancel a stripe subscription", {"stripe_cancel_subscription"}),
    ("create hubspot contact", {"hubspot_create_contact"}),
    ("linear new issue", {"linear_create_issue"}),
    ("asana create a task", {"asana_create_task"}),
    ("trello create card", {"trello_create_card"}),
    ("notion search pages", {"notion_search"}),
    ("list zendesk tickets", {"zendesk_list_tickets"}),
    ("delete s3 bucket", {"s3_delete_bucket"}),
    ("discord send a message", {"discord_send_message"}),
    ("shopify list orders", {"shopify_list_orders"}),
]


@pytest.fixture(scope="module")
def full_kit() -> ToolKit:
    names = list_connectors()
    return ToolKit(names, credentials={n: "x" for n in names})


class TestRanking:
    @pytest.mark.parametrize(("query", "expected"), GOLDEN)
    def test_right_tool_is_in_the_top_five(
        self, full_kit: ToolKit, query: str, expected: set[str]
    ) -> None:
        found = [m["tool"] for m in full_kit.search_tools(query)]
        assert expected & set(found), found

    def test_connector_filter(self, full_kit: ToolKit) -> None:
        found = full_kit.search_tools("send message", connector="telegram")
        assert found and all(m["tool"].startswith("telegram_") for m in found)

    def test_unknown_connector_is_an_error(self, full_kit: ToolKit) -> None:
        with pytest.raises(ConnectorNotConfiguredError):
            full_kit.search_tools("send", connector="nope")

    @pytest.mark.parametrize("query", ["", "   ", "the of to", "zzqqxx", "🎉", "x" * 100_000])
    def test_hopeless_queries_do_not_raise(self, full_kit: ToolKit, query: str) -> None:
        assert isinstance(full_kit.search_tools(query), list)

    @pytest.mark.parametrize(("limit", "most"), [(-5, 1), (0, 1), (3, 3), (9999, 20)])
    def test_limit_is_clamped(self, full_kit: ToolKit, limit: int, most: int) -> None:
        assert len(full_kit.search_tools("list", limit=limit)) == most

    def test_only_enabled_tools_are_found(self) -> None:
        kit = ToolKit(["gmail"], credentials={"gmail": "x"}, read_only=True)
        found = kit.search_tools("delete email send", limit=20)
        assert found and {m["risk"] for m in found} == {"read"}

    def test_empty_index(self) -> None:
        assert ToolIndex([]).search("anything") == []


class TestRisk:
    def test_anything_undeclared_is_destructive(self, full_kit: ToolKit) -> None:
        for entry in full_kit._tool_entries_list:
            assert risk_of(entry) in RISKS
            if entry.dangerous or not entry.access_classified:
                assert risk_of(entry) == "destructive"

    @pytest.mark.parametrize("risk", ["read", "write"])
    def test_lower_runner_refuses_a_destructive_tool(self, full_kit: ToolKit, risk: str) -> None:
        with pytest.raises(ValidationError, match="tc_run_destructive"):
            asyncio.run(full_kit.arun_tool(risk, "gmail_batch_delete", {}))

    def test_unknown_tool(self, full_kit: ToolKit) -> None:
        with pytest.raises(ConnectorNotConfiguredError):
            asyncio.run(full_kit.arun_tool("read", "gmail_nope", {}))

    def test_read_only_kit_offers_no_other_runner(self) -> None:
        kit = ToolKit(["gmail"], read_only=True)
        names = [d["name"] for d in search_tool_definitions(kit._tool_entries_list)]
        assert names == ["tc_find_tools", "tc_run_read"]


class TestProviderFormats:
    def test_anthropic_defers_everything_but_the_search_tool(self) -> None:
        search, *rest = ToolKit(["gmail"]).to_anthropic_search_tools()
        assert search["type"].startswith("tool_search_tool_bm25")
        assert "defer_loading" not in search
        assert rest and all(t["defer_loading"] is True for t in rest)

    def test_openai_groups_by_connector(self) -> None:
        kit = ToolKit(["gmail", "slack"])
        *groups, search = kit.to_openai_search_tools()
        assert search == {"type": "tool_search"}
        assert [g["name"] for g in groups] == ["gmail", "slack"]
        functions = [f for g in groups for f in g["tools"]]
        assert len(functions) == kit.tool_count
        assert all(f["defer_loading"] is True for f in functions)


class TestFilters:
    def test_include_tools_globs(self) -> None:
        kit = ToolKit(["gmail", "slack"], include_tools=["gmail_list_*", "slack_send_message"])
        names = {t["name"] for t in kit.list_tools()}
        assert "slack_send_message" in names
        assert all(n.startswith("gmail_list_") for n in names - {"slack_send_message"})


_CLI = "import sys; from toolsconnector.serve.cli import main; sys.exit(main())"


def _stdio_session(args: list[str], body: Any) -> Any:
    pytest.importorskip("mcp")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def run() -> Any:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-c", _CLI, "serve", "mcp", *args],
            env={"PYTHONPATH": ":".join(p for p in sys.path if p)},
        )
        async with stdio_client(params) as (r, w), ClientSession(r, w) as session:
            await session.initialize()
            return await body(session)

    return asyncio.run(asyncio.wait_for(run(), 60))


class TestRealMcpClient:
    """A real client over stdio: no stubbed FastMCP."""

    def test_search_mode_exposes_four_tools_whatever_the_catalog(self) -> None:
        async def body(session: Any) -> Any:
            return (await session.list_tools()).tools

        tools = _stdio_session([*list_connectors(), "--mode", "search"], body)
        by_name = {t.name: t for t in tools}
        assert set(by_name) == {
            "tc_find_tools",
            "tc_run_read",
            "tc_run_write",
            "tc_run_destructive",
        }
        assert by_name["tc_run_read"].annotations.readOnlyHint is True
        assert by_name["tc_run_destructive"].annotations.destructiveHint is True
        size = sum(len(t.model_dump_json(exclude_none=True)) for t in tools)
        assert size < 4000

    def test_find_then_wrong_runner(self) -> None:
        async def body(session: Any) -> Any:
            found = await session.call_tool("tc_find_tools", {"query": "delete gmail messages"})
            wrong = await session.call_tool(
                "tc_run_read", {"tool": "gmail_batch_delete", "arguments": {"message_ids": ["1"]}}
            )
            return found, wrong

        found, wrong = _stdio_session(["gmail", "--mode", "search"], body)
        matches = json.loads(found.content[0].text)["matches"]
        assert any(m["run_with"] == "tc_run_destructive" for m in matches)
        assert wrong.isError and "tc_run_destructive" in wrong.content[0].text

    def test_auto_stays_direct_for_a_small_set(self) -> None:
        async def body(session: Any) -> Any:
            return [t.name for t in (await session.list_tools()).tools]

        names = _stdio_session(["gmail", "--mode", "auto", "--tools", "gmail_list_*"], body)
        assert names and all(n.startswith("gmail_list_") for n in names)
