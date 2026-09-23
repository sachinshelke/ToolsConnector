"""Regression tests for ``create_and_run_mcp_server`` transport wiring.

These pin the fix for issue #22: ``serve_mcp(transport="streamable-http",
port=...)`` used to crash with ``TypeError: FastMCP.run() got an
unexpected keyword argument 'port'``. FastMCP requires host/port at
``__init__`` time — its ``run()`` method only takes ``transport`` and
``mount_path``. The fix moves host/port to construction; these tests
make sure that contract is preserved.

We mock ``mcp.server.fastmcp.FastMCP`` rather than depending on the
real package so the test:
  - runs on every Python version the project supports (the real ``mcp``
    package requires 3.10+; toolsconnector's floor is 3.9).
  - doesn't actually bind a socket — pure call-record assertions.
  - stays fast (no I/O at all).
"""

from __future__ import annotations

import builtins
import inspect
import sys
import types
from typing import Any
from unittest.mock import MagicMock

import pytest


def _install_fake_fastmcp(monkeypatch: pytest.MonkeyPatch) -> tuple[MagicMock, MagicMock]:
    """Install a fake ``mcp.server.fastmcp.FastMCP`` and return:
      (FastMCP_class_mock, server_instance_mock)

    The class mock records all ``__init__`` kwargs; the instance mock
    records ``.run()`` and ``.tool()`` calls. Together they let us
    assert *where* host/port flowed and that ``.run()`` was NEVER
    called with a ``port=`` kwarg (the bug).
    """
    server_instance = MagicMock(name="FastMCP_instance")
    # ``server.tool(...)`` returns a decorator that consumes the handler
    # and returns it. Match FastMCP's real shape so our caller's
    # ``server.tool(name=..., description=...)(handler)`` doesn't crash.
    server_instance.tool.return_value = lambda fn: fn

    fastmcp_class = MagicMock(name="FastMCP_class", return_value=server_instance)

    fake_fastmcp_mod = types.ModuleType("mcp.server.fastmcp")
    fake_fastmcp_mod.FastMCP = fastmcp_class  # type: ignore[attr-defined]
    fake_server_mod = types.ModuleType("mcp.server")
    fake_root_mod = types.ModuleType("mcp")

    monkeypatch.setitem(sys.modules, "mcp", fake_root_mod)
    monkeypatch.setitem(sys.modules, "mcp.server", fake_server_mod)
    monkeypatch.setitem(sys.modules, "mcp.server.fastmcp", fake_fastmcp_mod)

    return fastmcp_class, server_instance


def _make_toolkit_stub() -> Any:
    """Minimal ToolKit stand-in: just ``list_tools()`` returning a
    single fake entry. We don't need real connectors here — the
    transport wiring is what's under test.
    """
    tk = MagicMock(name="ToolKit_stub")
    tk.list_tools.return_value = [
        {
            "name": "fake_tool",
            "description": "Fake: do nothing",
            "input_schema": {"type": "object", "properties": {}},
        }
    ]
    return tk


# ---------------------------------------------------------------------------
# Issue #22 regression — port must NOT be forwarded to FastMCP.run()
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("transport", ["sse", "streamable-http"])
def test_http_transports_pass_host_and_port_to_init_not_run(
    transport: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fix from issue #22: for HTTP transports, host/port go to
    ``FastMCP(name, host=..., port=...)`` — NOT to ``server.run()``.

    Pre-fix code did ``server.run(transport=..., port=port)`` which
    raises ``TypeError: FastMCP.run() got an unexpected keyword
    argument 'port'`` because real FastMCP.run's signature is
    ``run(transport=..., mount_path=...)``.
    """
    fastmcp_class, server_instance = _install_fake_fastmcp(monkeypatch)
    from toolsconnector.serve.mcp import create_and_run_mcp_server

    create_and_run_mcp_server(
        _make_toolkit_stub(),
        transport=transport,
        name="testserver",
        host="127.0.0.1",
        port=9999,
    )

    # __init__ must have received host + port
    fastmcp_class.assert_called_once()
    init_kwargs = fastmcp_class.call_args.kwargs
    assert init_kwargs.get("host") == "127.0.0.1"
    assert init_kwargs.get("port") == 9999

    # run() must NOT have received port — that's the bug we're guarding
    server_instance.run.assert_called_once()
    run_kwargs = server_instance.run.call_args.kwargs
    assert "port" not in run_kwargs, (
        "regression: port was forwarded to FastMCP.run() — see issue #22. "
        f"run() called with: {run_kwargs}"
    )
    assert "host" not in run_kwargs, (
        "regression: host was forwarded to FastMCP.run() — see issue #22"
    )
    assert run_kwargs.get("transport") == transport


def test_stdio_transport_does_not_pass_host_or_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stdio doesn't bind a socket, so passing host/port to FastMCP
    is wasted at best and confusing at worst. Verify they're omitted
    entirely from both __init__ and run() for the stdio path.
    """
    fastmcp_class, server_instance = _install_fake_fastmcp(monkeypatch)
    from toolsconnector.serve.mcp import create_and_run_mcp_server

    create_and_run_mcp_server(
        _make_toolkit_stub(),
        transport="stdio",
        name="testserver",
        host="0.0.0.0",  # would be a security smell if it actually bound
        port=9999,
    )

    fastmcp_class.assert_called_once()
    init_args = fastmcp_class.call_args
    # stdio path: host/port should NOT have been threaded through.
    assert "host" not in init_args.kwargs
    assert "port" not in init_args.kwargs

    server_instance.run.assert_called_once_with(transport="stdio")


def test_unknown_transport_raises_before_constructing_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A typo'd transport must fail loudly with ValueError BEFORE we
    construct FastMCP — otherwise we'd bind a port for a server we're
    about to refuse to run, leaking the FD on the way out.
    """
    fastmcp_class, _server = _install_fake_fastmcp(monkeypatch)
    from toolsconnector.serve.mcp import create_and_run_mcp_server

    with pytest.raises(ValueError, match="Unknown transport"):
        create_and_run_mcp_server(
            _make_toolkit_stub(),
            transport="http",  # the documented-but-wrong value from the old docstring
        )

    fastmcp_class.assert_not_called()


# ---------------------------------------------------------------------------
# Defaults — host defaults to loopback (secure-by-default)
# ---------------------------------------------------------------------------


def test_http_transport_default_host_is_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default ``host`` must be ``127.0.0.1`` so a daemon doesn't
    accidentally listen on all interfaces. The HTTP transports ship
    without built-in auth — exposing them on 0.0.0.0 by default would
    be a footgun. Callers opt-in explicitly to LAN/external bind.
    """
    fastmcp_class, _server = _install_fake_fastmcp(monkeypatch)
    from toolsconnector.serve.mcp import create_and_run_mcp_server

    create_and_run_mcp_server(
        _make_toolkit_stub(),
        transport="streamable-http",
        port=3000,
        # host left as default
    )

    init_kwargs = fastmcp_class.call_args.kwargs
    assert init_kwargs["host"] == "127.0.0.1"


def test_explicit_host_override_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the operator explicitly opts into a non-loopback bind
    (e.g. behind their own auth proxy), the override must reach
    FastMCP unchanged.
    """
    fastmcp_class, _server = _install_fake_fastmcp(monkeypatch)
    from toolsconnector.serve.mcp import create_and_run_mcp_server

    create_and_run_mcp_server(
        _make_toolkit_stub(),
        transport="streamable-http",
        host="0.0.0.0",
        port=3000,
    )

    assert fastmcp_class.call_args.kwargs["host"] == "0.0.0.0"


# ---------------------------------------------------------------------------
# anyOf union params — the MCP handler signature must accept every member
# shape, or FastMCP's derived Pydantic model rejects e.g. a batch list before
# the handler runs. Regression for batch embeddings via MCP stdio.
# ---------------------------------------------------------------------------


def test_json_type_anyof_builds_union_annotation() -> None:
    from typing import Union, get_args

    from toolsconnector.serve.mcp import _json_type_to_python

    # required str|array -> Union[str, list] (no None)
    ann = _json_type_to_python({"anyOf": [{"type": "string"}, {"type": "array"}]}, True)
    assert ann == Union[str, list]
    assert list in get_args(ann)

    # optional str|object -> Union[str, dict, None]
    ann_opt = _json_type_to_python({"anyOf": [{"type": "string"}, {"type": "object"}]}, False)
    assert str in get_args(ann_opt) and dict in get_args(ann_opt)
    assert type(None) in get_args(ann_opt)

    # single-member anyOf collapses (no spurious Union)
    assert _json_type_to_python({"anyOf": [{"type": "string"}]}, True) is str

    # plain typed params are unchanged
    assert _json_type_to_python({"type": "string"}, True) is str
    assert _json_type_to_python({"type": "integer"}, True) is int


def test_make_tool_handler_signature_accepts_union_param() -> None:
    """The dynamically-built handler signature exposes a Union annotation for
    an ``anyOf`` param, so FastMCP accepts both the string and array forms.
    """
    from typing import Union, get_args
    from unittest.mock import MagicMock

    from toolsconnector.serve.mcp import _make_tool_handler

    schema = {
        "type": "object",
        "properties": {
            "model": {"type": "string"},
            "inputs": {"anyOf": [{"type": "string"}, {"type": "array"}]},
            "provider": {"type": "string", "default": "hf-inference"},
        },
        "required": ["model", "inputs"],
    }
    handler = _make_tool_handler(
        MagicMock(name="toolkit"), "huggingface_feature_extraction", schema
    )
    params = handler.__signature__.parameters
    assert params["inputs"].annotation == Union[str, list]
    assert list in get_args(params["inputs"].annotation)
    # required param has no default; optional one defaults to None (None-strip).
    import inspect as _inspect

    assert params["model"].default is _inspect.Parameter.empty
    assert params["provider"].default is None


def test_json_type_typed_array_preserves_item_type() -> None:
    """A typed array schema (``items: {type: ...}``) maps to ``list[<item>]`` so
    FastMCP regenerates a typed array; a bare array stays plain ``list``.
    """
    from typing import Optional, get_args

    from toolsconnector.serve.mcp import _json_type_to_python

    ann = _json_type_to_python({"type": "array", "items": {"type": "string"}}, False)
    assert ann == Optional[list[str]]
    assert list[str] in get_args(ann)

    assert _json_type_to_python({"type": "array", "items": {"type": "integer"}}, True) == list[int]
    # Bare array (no item type) stays plain ``list`` — unchanged behaviour.
    assert _json_type_to_python({"type": "array"}, True) is list


# ---------------------------------------------------------------------------
# ImportError handling for the ``mcp`` package
#
# mcp 2.x removed ``mcp.server.fastmcp``; the module is a tombstone that
# raises ModuleNotFoundError with a genuinely useful message (it names
# MCPServer, links the migration guide, and suggests pinning 'mcp<2').
# The old handler caught ImportError and re-raised WITHOUT ``from e``,
# discarding all of that and substituting "install with: pip install
# toolsconnector[mcp]" — advice the user had already followed.
# ---------------------------------------------------------------------------

_TOMBSTONE_MESSAGE = (
    "No module named 'mcp.server.fastmcp'. This is mcp 2.x, where FastMCP was "
    "renamed to MCPServer (from mcp.server.mcpserver import MCPServer) and other "
    "APIs changed; see the migration guide at "
    "https://py.sdk.modelcontextprotocol.io/v2/migration/#fastmcp-renamed-to-mcpserver "
    "or pin 'mcp<2' to keep running v1 code."
)


def _break_fastmcp_import(monkeypatch: pytest.MonkeyPatch, exc: ImportError) -> None:
    """Make ``from mcp.server.fastmcp import FastMCP`` raise ``exc``.

    Mirrors how mcp 2.x actually fails: the parent packages import fine,
    and only the ``mcp.server.fastmcp`` submodule blows up.
    """
    monkeypatch.setitem(sys.modules, "mcp", types.ModuleType("mcp"))
    monkeypatch.setitem(sys.modules, "mcp.server", types.ModuleType("mcp.server"))
    monkeypatch.delitem(sys.modules, "mcp.server.fastmcp", raising=False)

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "mcp.server.fastmcp":
            raise exc
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)


def _set_installed_mcp_version(monkeypatch: pytest.MonkeyPatch, version: str | None) -> None:
    """Pretend ``mcp`` is installed at ``version`` (or absent when None)."""
    import importlib.metadata as md

    real_version = md.version

    def fake_version(name: str) -> str:
        if name == "mcp":
            if version is None:
                raise md.PackageNotFoundError("mcp")
            return version
        return real_version(name)

    monkeypatch.setattr(md, "version", fake_version)


def test_import_error_chains_the_original_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``raise ... from e`` — mcp 2.x's own diagnostic must survive.

    Without the chain, the migration guide URL and the ``pin 'mcp<2'``
    hint are destroyed and the user is left with a message that tells
    them to re-run the install they already ran.
    """
    from toolsconnector.serve.mcp import create_and_run_mcp_server

    original = ModuleNotFoundError(_TOMBSTONE_MESSAGE, name="mcp.server.fastmcp")
    _break_fastmcp_import(monkeypatch, original)
    _set_installed_mcp_version(monkeypatch, "2.2.0")

    with pytest.raises(ImportError) as excinfo:
        create_and_run_mcp_server(_make_toolkit_stub())

    assert excinfo.value.__cause__ is original, (
        "the ImportError handler dropped the original exception — re-raise "
        "with `from e` so mcp 2.x's migration guidance survives the traceback"
    )
    # The upstream hint must be reachable from the raised error.
    assert "MCPServer" in str(excinfo.value.__cause__)
    assert "migration" in str(excinfo.value.__cause__)


def test_import_error_message_differs_when_mcp_is_installed_but_incompatible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ "Not installed" and "installed but wrong major" need different advice."""
    from toolsconnector.serve.mcp import create_and_run_mcp_server

    def _message(installed: str | None) -> str:
        with monkeypatch.context() as m:
            _break_fastmcp_import(m, ModuleNotFoundError(_TOMBSTONE_MESSAGE))
            _set_installed_mcp_version(m, installed)
            with pytest.raises(ImportError) as excinfo:
                create_and_run_mcp_server(_make_toolkit_stub())
            return str(excinfo.value)

    incompatible = _message("2.2.0")
    missing = _message(None)

    assert incompatible != missing, (
        "the handler gives identical advice whether 'mcp' is missing or "
        "installed-but-incompatible; the 2.x case must not tell the user to "
        "re-run the install that produced it"
    )
    # The incompatible case must name the offending version and the fix.
    assert "2.2.0" in incompatible
    assert "mcp>=1.10,<2" in incompatible
    # The missing case is the only one that should recommend the extra.
    assert "toolsconnector[mcp]" in missing


# ---------------------------------------------------------------------------
# Integration: exercise the real ``mcp`` package when it is installed.
#
# NOTE: CI installs only ``.[dev]``, which does not include ``[mcp]``, so
# this SKIPS on CI today. It runs in any env where the extra is present.
# ---------------------------------------------------------------------------


def test_real_mcp_package_serves_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """With the pinned extra installed, the real server path must work.

    This is the test that would have caught the 2.x breakage: it runs
    ``create_and_run_mcp_server`` against the REAL ``FastMCP`` (not the
    mock used above) — import, construction, and tool registration
    through the ``__signature__``-rewriting handler — stopping only at
    ``run()`` so no stdio loop or socket is started.
    """
    pytest.importorskip(
        "mcp.server.fastmcp",
        reason="requires the [mcp] extra (mcp>=1.10,<2)",
    )
    import asyncio

    from mcp.server.fastmcp import FastMCP

    from toolsconnector.serve.mcp import create_and_run_mcp_server

    # The pinned floor exists for these two kwargs — assert they are real.
    tool_params = inspect.signature(FastMCP.tool).parameters
    assert "annotations" in tool_params, "mcp too old: FastMCP.tool() lacks annotations="
    assert "structured_output" in tool_params, (
        "mcp too old: FastMCP.tool() lacks structured_output= (needs >=1.10)"
    )

    captured: list[Any] = []
    monkeypatch.setattr(FastMCP, "run", lambda self, *a, **kw: captured.append((self, a, kw)))

    toolkit = _make_toolkit_stub()
    toolkit.list_tools.return_value = [
        {
            "name": "echo",
            "description": "Echo a message back.",
            "input_schema": {
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
            },
        }
    ]

    create_and_run_mcp_server(toolkit, transport="stdio")

    assert len(captured) == 1, "run() was not reached"
    server, _, run_kwargs = captured[0]
    assert run_kwargs == {"transport": "stdio"}

    tools = {t.name: t for t in asyncio.run(server.list_tools())}
    assert set(tools) == {"echo"}
    # The rewritten signature must surface as a real input schema, not **kwargs.
    assert tools["echo"].inputSchema["properties"].keys() == {"message"}
    assert tools["echo"].inputSchema.get("required") == ["message"]
