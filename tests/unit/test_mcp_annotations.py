"""MCP ``tools/list`` carries declared safety metadata and no junk.

The wire tests build a real FastMCP server (``run`` is stubbed, nothing is
served) and read back the exact ``tools/list`` result. A ``sys.modules`` stub
would not do: stubbed MCP tests are how a broken fresh install shipped
unnoticed.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from toolsconnector.serve import ToolKit
from toolsconnector.serve.mcp import _tool_annotation_hints, create_and_run_mcp_server


def _entry(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "access": "write",
        "access_classified": True,
        "idempotent": False,
    }
    base.update(overrides)
    return base


class TestToolAnnotationHints:
    """Only declared facts become hints; anything undeclared is omitted so
    clients fall back to the MCP spec's worst-case defaults."""

    def test_read(self) -> None:
        assert _tool_annotation_hints(_entry(access="read")) == {"readOnlyHint": True}

    def test_write(self) -> None:
        assert _tool_annotation_hints(_entry(access="write")) == {
            "readOnlyHint": False,
            "destructiveHint": False,
        }

    def test_destructive(self) -> None:
        assert _tool_annotation_hints(_entry(access="destructive")) == {
            "readOnlyHint": False,
            "destructiveHint": True,
        }

    def test_unclassified_access_emits_no_access_hints(self) -> None:
        """The library's fail-safe ``"write"`` default must not become a
        confident ``destructiveHint: false`` on the wire."""
        assert _tool_annotation_hints(_entry(access_classified=False)) == {}

    def test_declared_idempotent_is_emitted_even_if_access_unknown(self) -> None:
        hints = _tool_annotation_hints(_entry(access_classified=False, idempotent=True))
        assert hints == {"idempotentHint": True}

    def test_idempotent_is_not_emitted_for_read_only(self) -> None:
        """The spec defines idempotentHint only for non-read-only tools."""
        hints = _tool_annotation_hints(_entry(access="read", idempotent=True))
        assert hints == {"readOnlyHint": True}


@pytest.fixture
def tools_by_name(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    fastmcp = pytest.importorskip("mcp.server.fastmcp")
    captured: dict[str, Any] = {}

    def _capture(self: Any, *args: Any, **kwargs: Any) -> None:
        captured["server"] = self

    monkeypatch.setattr(fastmcp.FastMCP, "run", _capture)
    create_and_run_mcp_server(ToolKit(["gmail", "slack"]), transport="stdio")
    tools = asyncio.run(captured["server"].list_tools())
    return {t.name: t for t in tools}


class TestToolsListWire:
    def test_read_tool_is_read_only(self, tools_by_name: dict[str, Any]) -> None:
        ann = tools_by_name["gmail_list_emails"].annotations
        assert ann is not None and ann.readOnlyHint is True

    def test_destructive_tool_is_destructive(self, tools_by_name: dict[str, Any]) -> None:
        ann = tools_by_name["gmail_batch_delete"].annotations
        assert ann is not None
        assert ann.readOnlyHint is False and ann.destructiveHint is True

    def test_write_tool_is_not_destructive(self, tools_by_name: dict[str, Any]) -> None:
        ann = tools_by_name["gmail_create_draft"].annotations
        assert ann is not None
        assert ann.readOnlyHint is False and ann.destructiveHint is False

    def test_unclassified_tool_fails_closed(self, tools_by_name: dict[str, Any]) -> None:
        """No hints -> client assumes destructive, per the MCP spec defaults."""
        assert tools_by_name["slack_add_reaction"].annotations is None

    def test_no_placeholder_output_schema(self, tools_by_name: dict[str, Any]) -> None:
        """FastMCP otherwise derives ``{"result": string}`` from the handler's
        ``-> str`` annotation for every tool (about a fifth of the payload)."""
        with_schema = [n for n, t in tools_by_name.items() if t.outputSchema]
        assert with_schema == []
