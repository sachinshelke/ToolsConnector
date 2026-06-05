"""End-to-end integration test: spawn the real MCP server as a subprocess
and verify the full JSON-RPC handshake + tool calls for HuggingFace.

Boots a real FastMCP stdio server (with respx-mocked HF hosts so no network),
runs the standard MCP handshake, lists tools, and calls tools — proving the
whole chain between an MCP client (Claude Desktop, Cursor, an LLM agent) and
the HuggingFace connector is wired correctly.

The load-bearing case here is ``huggingface_feature_extraction`` called with a
**batch list** of inputs: it exercises both the ``anyOf`` union schema (so the
arg validator accepts the list) and the MCP handler's ``Union[str, list]``
signature annotation (so FastMCP's Pydantic model accepts the list instead of
rejecting it as "expects string"). It also calls ``zero_shot_classification``
to confirm the router list-shape parser fix survives the MCP round-trip.

**Auto-skipped** on Python < 3.10 because the ``mcp`` package (FastMCP)
requires 3.10+. On 3.10+ (CI, release validation) the test runs end to end.
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

pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 10),
    reason="MCP server (FastMCP) requires Python 3.10+; skipping on this interpreter",
)


def _server_script(repo_root: Path) -> str:
    """Inline server script with respx routes for the two HF hosts (router +
    Hub), so the subprocess never touches the real Hugging Face API.
    """
    return textwrap.dedent(
        f"""
        import sys
        sys.path.insert(0, {str(repo_root / "src")!r})

        import httpx
        import respx

        from toolsconnector.connectors.huggingface import HuggingFace
        from toolsconnector.serve import ToolKit

        router = respx.mock(assert_all_called=False)
        router.start()

        # Hub identity
        router.get("https://huggingface.co/api/whoami-v2").mock(
            return_value=httpx.Response(
                200, json={{"name": "mcp-bot", "type": "user", "email": None, "orgs": []}}
            )
        )
        # Batch embeddings — the anyOf / Union-signature regression case.
        router.post(
            "https://router.huggingface.co/hf-inference/models/"
            "sentence-transformers/all-MiniLM-L6-v2/pipeline/feature-extraction"
        ).mock(return_value=httpx.Response(200, json=[[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]))
        # Zero-shot — router list-of-{{label,score}} shape (parser fix).
        router.post(
            "https://router.huggingface.co/hf-inference/models/"
            "facebook/bart-large-mnli/pipeline/zero-shot-classification"
        ).mock(
            return_value=httpx.Response(
                200,
                json=[
                    {{"label": "finance", "score": 0.9}},
                    {{"label": "sports", "score": 0.1}},
                ],
            )
        )

        kit = ToolKit(["huggingface"], credentials={{"huggingface": "hf_mcp_test"}})
        print("MCP_SERVER_READY", file=sys.stderr, flush=True)
        kit.serve_mcp(transport="stdio", name="huggingface-test")
        """
    ).strip()


def _send(proc: subprocess.Popen, msg: dict[str, Any]) -> None:
    assert proc.stdin is not None
    proc.stdin.write(json.dumps(msg).encode() + b"\n")
    proc.stdin.flush()


def _recv(
    proc: subprocess.Popen,
    expected_id: Optional[int] = None,
    timeout: float = 8.0,
) -> dict[str, Any]:
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


def test_huggingface_mcp_server_end_to_end_handshake() -> None:
    """Full MCP stdio round-trip against a real FastMCP server for HuggingFace."""
    try:
        import mcp  # noqa: F401
    except ImportError:
        pytest.skip("mcp package not installed; install with toolsconnector[mcp]")

    repo_root = Path(__file__).resolve().parent.parent.parent
    server_src = _server_script(repo_root)

    with tempfile.TemporaryDirectory() as tmpdir:
        server_path = Path(tmpdir) / "huggingface_mcp_server.py"
        server_path.write_text(server_src)

        proc = subprocess.Popen(
            [sys.executable, str(server_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )

        try:
            ready = False
            for _ in range(50):  # 5s
                assert proc.stderr is not None
                line = proc.stderr.readline()
                if line and b"MCP_SERVER_READY" in line:
                    ready = True
                    break
                time.sleep(0.1)
            assert ready, "server did not signal ready"

            # 1. initialize
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
            assert init["result"]["serverInfo"]["name"] == "huggingface-test"

            _send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})

            # 2. tools/list — all 27 huggingface tools
            _send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
            listed = _recv(proc, expected_id=2)
            tools = listed["result"]["tools"]
            hf_tools = [t for t in tools if t["name"].startswith("huggingface_")]
            assert len(hf_tools) == 27, f"expected 27 tools, got {len(hf_tools)}"

            # feature_extraction inputSchema must advertise the union (string or array)
            fe = next(t for t in hf_tools if t["name"] == "huggingface_feature_extraction")
            inputs_schema = fe["inputSchema"]["properties"]["inputs"]
            # FastMCP may render the Union[str, list] as anyOf or as a multi-type;
            # either way the array form must be representable.
            schema_text = json.dumps(inputs_schema)
            assert "array" in schema_text, f"inputs schema lost the array form: {inputs_schema}"

            # 3. tools/call huggingface_whoami — happy path
            _send(
                proc,
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "huggingface_whoami", "arguments": {}},
                },
            )
            call = _recv(proc, expected_id=3)
            parsed = json.loads(call["result"]["content"][0]["text"])
            assert parsed["name"] == "mcp-bot"

            # 4. tools/call feature_extraction with a BATCH LIST — the load-bearing
            # regression: a list arg must NOT be rejected by FastMCP's Pydantic model.
            _send(
                proc,
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {
                        "name": "huggingface_feature_extraction",
                        "arguments": {
                            "model": "sentence-transformers/all-MiniLM-L6-v2",
                            "inputs": ["alpha", "beta", "gamma"],
                        },
                    },
                },
            )
            batch = _recv(proc, expected_id=4)
            assert not batch["result"].get("isError"), f"batch call errored: {batch['result']}"
            rows = json.loads(batch["result"]["content"][0]["text"])
            assert len(rows) == 3, f"batch embeddings lost rows: {rows}"

            # 5. tools/call zero_shot_classification — router list-shape parser fix
            _send(
                proc,
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {
                        "name": "huggingface_zero_shot_classification",
                        "arguments": {
                            "model": "facebook/bart-large-mnli",
                            "inputs": "stocks rose",
                            "candidate_labels": ["finance", "sports"],
                        },
                    },
                },
            )
            zs = _recv(proc, expected_id=5)
            assert not zs["result"].get("isError"), f"zero-shot errored: {zs['result']}"
            zs_parsed = json.loads(zs["result"]["content"][0]["text"])
            assert zs_parsed["labels"] == ["finance", "sports"]
            assert zs_parsed["scores"][0] == 0.9

            # 6. tools/call with unknown tool name -> error
            _send(
                proc,
                {
                    "jsonrpc": "2.0",
                    "id": 6,
                    "method": "tools/call",
                    "params": {"name": "huggingface_nonexistent", "arguments": {}},
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
