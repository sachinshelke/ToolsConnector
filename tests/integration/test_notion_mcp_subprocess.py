"""End-to-end integration test: spawn the real MCP server as a
subprocess and verify the full JSON-RPC handshake + tool calls.

This is the test that converts our last MCP-related assumption
("FastMCP correctly wires our handlers") into a verified fact. We
don't just test the handler factory in isolation — we boot a real
MCP stdio server, send real JSON-RPC frames, and parse real responses.

**Auto-skipped** on Python < 3.10 because the ``mcp`` package
(FastMCP) requires 3.10+. On 3.10+ environments — CI, local dev,
release validation — the test runs and exercises the full stack.

Boot mechanism:
    1. Spawn a Python subprocess running the embedded server script
       (which wires up respx mocks so no real Notion API access).
    2. Wait for ``MCP_SERVER_READY`` on stderr.
    3. Run the standard MCP handshake: initialize → initialized.
    4. ``tools/list`` → verify all 24 notion tools.
    5. ``tools/call notion_get_me`` → verify the result shape.
    6. ``tools/call notion_search`` → verify PaginatedList shape.
    7. ``tools/call notion_get_page`` with a path-traversal id →
       verify the ValidationError surfaces through MCP.
    8. ``tools/call`` with an unknown tool name → verify error.
    9. Terminate the subprocess.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path
from typing import Any, Optional

import pytest

# FastMCP requires Python 3.10+; this file's tests are no-ops on 3.9.
pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 10),
    reason="MCP server (FastMCP) requires Python 3.10+; skipping on this interpreter",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _server_script(repo_root: Path) -> str:
    """Inline server script — keeps the test self-contained.

    Mounts respx with routes for the actions this test exercises, so the
    subprocess never touches the real Notion API.
    """
    return textwrap.dedent(
        f"""
        import sys
        sys.path.insert(0, {str(repo_root / "src")!r})

        import httpx
        import respx

        from toolsconnector.connectors.notion import Notion
        from toolsconnector.serve import ToolKit

        router = respx.mock(base_url="https://api.notion.com/v1", assert_all_called=False)
        router.start()

        router.get("/users/me").mock(
            return_value=httpx.Response(
                200,
                json={{"object": "user", "id": "bot-mcp-test", "type": "bot", "name": "MCP Bot"}},
            )
        )
        router.post("/search").mock(
            return_value=httpx.Response(
                200,
                json={{
                    "object": "list",
                    "results": [{{
                        "object": "page",
                        "id": "page-mcp-001",
                        "archived": False,
                        "parent": {{"type": "workspace", "workspace": True}},
                        "properties": {{}},
                    }}],
                    "has_more": False,
                    "next_cursor": None,
                }},
            )
        )

        kit = ToolKit(["notion"], credentials={{"notion": "ntn_mcp_test"}})
        print("MCP_SERVER_READY", file=sys.stderr, flush=True)
        kit.serve_mcp(transport="stdio", name="notion-test")
        """
    ).strip()


def _send(proc: subprocess.Popen, msg: dict[str, Any]) -> None:
    """Write a JSON-RPC frame + newline (per MCP stdio spec)."""
    assert proc.stdin is not None
    proc.stdin.write(json.dumps(msg).encode() + b"\n")
    proc.stdin.flush()


def _recv(
    proc: subprocess.Popen,
    expected_id: Optional[int] = None,
    timeout: float = 8.0,
) -> dict[str, Any]:
    """Read JSON-RPC frames until one matches ``expected_id`` (or any)."""
    assert proc.stdout is not None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        line = proc.stdout.readline()
        if not line:
            time.sleep(0.02)
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if expected_id is None or msg.get("id") == expected_id:
            return msg
    raise TimeoutError(f"no JSON-RPC response with id={expected_id} in {timeout}s")


# ---------------------------------------------------------------------------
# The integration test
# ---------------------------------------------------------------------------


def test_notion_mcp_server_end_to_end_handshake() -> None:
    """Full MCP stdio round-trip against a real FastMCP server.

    Validates that everything between toolsconnector and an MCP client
    (LLM agent, Claude Desktop, Cursor, etc.) is wired correctly: tool
    listing, tool calling, error surfacing, schema generation.
    """
    # Skip if the mcp package isn't available even on Py 3.10+ — e.g.
    # the test env didn't install the [mcp] extra.
    try:
        import mcp  # noqa: F401
    except ImportError:
        pytest.skip("mcp package not installed; install with toolsconnector[mcp]")

    repo_root = Path(__file__).resolve().parent.parent.parent
    server_src = _server_script(repo_root)

    with tempfile.TemporaryDirectory() as tmpdir:
        server_path = Path(tmpdir) / "notion_mcp_server.py"
        server_path.write_text(server_src)

        # Use the same Python that runs the tests
        proc = subprocess.Popen(
            [sys.executable, str(server_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )

        try:
            # Wait for ready marker
            ready = False
            for _ in range(50):  # 5s
                assert proc.stderr is not None
                line = proc.stderr.readline()
                if line and b"MCP_SERVER_READY" in line:
                    ready = True
                    break
                time.sleep(0.1)
            assert ready, "server did not signal ready"

            # 1. initialize handshake
            _send(
                proc,
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "tc-test", "version": "0.1"},
                    },
                },
            )
            init = _recv(proc, expected_id=1)
            assert "result" in init, f"initialize failed: {init}"
            assert init["result"]["serverInfo"]["name"] == "notion-test"

            _send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})

            # 2. tools/list
            _send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
            listed = _recv(proc, expected_id=2)
            tools = listed["result"]["tools"]
            notion_tools = [t for t in tools if t["name"].startswith("notion_")]
            assert len(notion_tools) == 24, f"expected 24 tools, got {len(notion_tools)}"

            # Spot-check a tool's inputSchema
            get_page = next(t for t in notion_tools if t["name"] == "notion_get_page")
            assert get_page["inputSchema"].get("required") == ["page_id"]

            # 3. tools/call notion_get_me — happy path
            _send(
                proc,
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "notion_get_me", "arguments": {}},
                },
            )
            call = _recv(proc, expected_id=3)
            content = call["result"]["content"][0]["text"]
            parsed = json.loads(content)
            assert parsed["id"] == "bot-mcp-test"
            assert parsed["type"] == "bot"

            # 4. tools/call notion_search — paginated, no limit (the
            # round-6 None-limit bug would hit here pre-fix)
            _send(
                proc,
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {"name": "notion_search", "arguments": {"query": "test"}},
                },
            )
            search = _recv(proc, expected_id=4)
            assert not search["result"].get("isError"), f"search returned error: {search['result']}"
            search_content = search["result"]["content"][0]["text"]
            search_parsed = json.loads(search_content)
            assert isinstance(search_parsed["items"], list)
            assert len(search_parsed["items"]) == 1

            # 5. tools/call notion_get_page with path-traversal — must
            # surface as a typed ValidationError via the MCP error frame
            _send(
                proc,
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {"name": "notion_get_page", "arguments": {"page_id": "../users/me"}},
                },
            )
            blocked = _recv(proc, expected_id=5)
            is_error = "error" in blocked or blocked.get("result", {}).get("isError")
            assert is_error, f"path-traversal NOT blocked through MCP: {blocked}"

            # 6. tools/call with unknown tool name
            _send(
                proc,
                {
                    "jsonrpc": "2.0",
                    "id": 6,
                    "method": "tools/call",
                    "params": {"name": "notion_nonexistent", "arguments": {}},
                },
            )
            unknown = _recv(proc, expected_id=6)
            is_error = "error" in unknown or unknown.get("result", {}).get("isError")
            assert is_error, f"unknown tool name didn't return error: {unknown}"

        finally:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
