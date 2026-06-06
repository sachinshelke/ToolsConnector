"""Tests for `tc serve mcp` / `tc serve rest` CLI command wrappers.

This file pins behaviors that, if regressed, break stdio-transport MCP
clients silently (Claude Desktop, Cursor, VS Code MCP). The wire format
on stdio is line-delimited JSON-RPC, so any plain `print()` from the
server side corrupts the channel and the client disconnects.
"""

from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch

import pytest

from toolsconnector.serve import cli


def _build_args(connectors: list[str], transport: str = "stdio") -> argparse.Namespace:
    """Construct the argparse.Namespace shape `_cmd_serve_mcp` expects."""
    return argparse.Namespace(
        connectors=connectors,
        transport=transport,
        name=None,
        host="localhost",
        port=3000,
    )


def test_serve_mcp_startup_banner_goes_to_stderr_not_stdout(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Regression test for the stdio-transport JSON-RPC corruption bug.

    ``_cmd_serve_mcp`` prints a "Starting MCP server with N tools..."
    banner on startup. STDOUT is the JSON-RPC channel for the default
    stdio transport — Claude Desktop / Cursor / VS Code MCP clients
    read each line as a JSON-RPC message and disconnect on parse error.

    Pre-fix behavior: banner went to stdout, every stdio MCP client saw
    a JSONDecodeError on first message and dropped the session.

    Post-fix behavior (pinned here): banner goes to stderr, stdout is
    pristine until the underlying MCP library starts writing real
    JSON-RPC responses to it.
    """
    # Stub `serve_mcp` so the test doesn't actually start a server.
    with patch("toolsconnector.serve.toolkit.ToolKit.serve_mcp") as mock_serve:
        cli._cmd_serve_mcp(_build_args(["webhook"]))
        # ToolKit.serve_mcp was reached (no exception in setup)
        mock_serve.assert_called_once()

    captured = capsys.readouterr()
    # Stdout MUST be clean — anything here breaks the JSON-RPC channel
    assert captured.out == "", (
        f"REGRESSION: _cmd_serve_mcp wrote {captured.out!r} to stdout. "
        f"stdio-transport MCP clients (Claude Desktop, Cursor, etc.) "
        f"will receive that as the first 'message' and disconnect. "
        f"All informational output must go to stderr."
    )
    # Stderr carries the banner
    assert "Starting MCP server with" in captured.err
    assert "tools" in captured.err


def test_serve_mcp_error_path_writes_to_stderr_too(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Errors during MCP server setup must NOT leak to stdout either —
    a half-line of stack trace corrupts the channel the same way the
    success banner did.
    """
    with patch("toolsconnector.serve.toolkit.ToolKit.serve_mcp") as mock_serve:
        mock_serve.side_effect = RuntimeError("simulated startup failure")
        rc = cli._cmd_serve_mcp(_build_args(["webhook"]))
    assert rc == 1
    captured = capsys.readouterr()
    # The banner still went to stderr before the exception
    assert captured.out == "", (
        f"REGRESSION: error path wrote {captured.out!r} to stdout. "
        f"All output must go to stderr on stdio transport."
    )
    assert "Error: simulated startup failure" in captured.err


def _build_rest_args(
    connectors: list[str],
    host: str = "127.0.0.1",
    port: int = 8000,
    prefix: str = "/api/v1",
) -> argparse.Namespace:
    """Construct the argparse.Namespace shape ``_cmd_serve_rest`` expects."""
    return argparse.Namespace(
        connectors=connectors,
        host=host,
        port=port,
        prefix=prefix,
    )


def test_serve_rest_binds_loopback_by_default() -> None:
    """SECURITY: ``tc serve rest`` must default to 127.0.0.1, not 0.0.0.0.

    The REST transport ships without built-in auth, so binding all interfaces
    by default would expose every connector action to the local network.
    """
    fake_uvicorn = MagicMock()
    with (
        patch.dict("sys.modules", {"uvicorn": fake_uvicorn}),
        patch("toolsconnector.serve.toolkit.ToolKit") as mock_kit,
    ):
        mock_kit.return_value.list_tools.return_value = []
        mock_kit.return_value.create_rest_app.return_value = object()
        rc = cli._cmd_serve_rest(_build_rest_args(["webhook"]))

    assert rc == 0
    fake_uvicorn.run.assert_called_once()
    assert fake_uvicorn.run.call_args.kwargs["host"] == "127.0.0.1"


def test_serve_rest_warns_when_exposing_all_interfaces(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Opting into 0.0.0.0 is allowed but must print a no-auth warning to stderr."""
    fake_uvicorn = MagicMock()
    with (
        patch.dict("sys.modules", {"uvicorn": fake_uvicorn}),
        patch("toolsconnector.serve.toolkit.ToolKit") as mock_kit,
    ):
        mock_kit.return_value.list_tools.return_value = []
        mock_kit.return_value.create_rest_app.return_value = object()
        rc = cli._cmd_serve_rest(_build_rest_args(["webhook"], host="0.0.0.0"))

    assert rc == 0
    assert fake_uvicorn.run.call_args.kwargs["host"] == "0.0.0.0"
    assert "NO built-in authentication" in capsys.readouterr().err
