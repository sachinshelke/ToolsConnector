"""MCP server integration.

Creates and runs an MCP server from a ToolKit instance.
Tools are dynamically registered from the ToolKit's filtered tool list.
"""

from __future__ import annotations

import inspect
import json
import logging
from typing import TYPE_CHECKING, Any, Literal, Optional, Union, cast

if TYPE_CHECKING:
    from toolsconnector.serve.toolkit import ToolKit

logger = logging.getLogger("toolsconnector.serve.mcp")


def _json_type_to_python(param_schema: dict[str, Any], required: bool) -> Any:
    """Map a JSON Schema property definition to a Python type annotation.

    Args:
        param_schema: JSON Schema dict for a single property.
        required: Whether the parameter is required by the tool.

    Returns:
        A Python type suitable for use as an ``inspect.Parameter`` annotation.
    """
    type_map: dict[str, Any] = {
        "integer": int,
        "number": float,
        "boolean": bool,
        "string": str,
        "array": list,
        "object": dict,
    }

    # Multi-type union params are rendered as ``anyOf`` in the input schema
    # (e.g. ``Union[str, list[str]]`` for batch embeddings). Build a Python
    # ``Union`` annotation so FastMCP's derived Pydantic model accepts every
    # member shape; collapsing to a single type here would make FastMCP reject
    # the other forms (e.g. a list arg) before the handler ever runs.
    any_of = param_schema.get("anyOf")
    if any_of:
        members: list[Any] = []
        for sub in any_of:
            member = type_map.get(sub.get("type"), Any)
            if member not in members:
                members.append(member)
        if len(members) == 1:
            py_type: Any = members[0]
        else:
            py_type = Union[tuple(members)]
    else:
        json_type = param_schema.get("type", "string")
        py_type = type_map.get(json_type, Any)
        # Preserve the element type for typed arrays (``items: {type: ...}``)
        # so FastMCP regenerates ``list[str]`` rather than an untyped ``list``
        # (which would emit ``items: {}`` and drop the element type). A bare
        # array with no item type stays plain ``list``.
        if json_type == "array":
            item_type = (param_schema.get("items") or {}).get("type")
            if item_type:
                # Runtime construction of the handler's ``list[<item>]``
                # annotation; mypy can't statically resolve the dynamic
                # subscript, so build it via the parametrized-generic API.
                py_type = list[type_map.get(item_type, Any)]  # type: ignore[misc]

    return py_type if required else Optional[py_type]


def _tool_annotation_hints(entry: dict[str, Any]) -> dict[str, bool]:
    """Map a tool's declared safety metadata to MCP ``ToolAnnotations`` hints.

    Only declared facts become hints. Anything undeclared is omitted, so the
    client falls back to the MCP spec defaults, which are the worst case
    (not read-only, destructive, not idempotent). In particular, an action
    with no declared ``access`` surfaces the library's fail-safe ``"write"``
    in :class:`ToolEntry`; stating that as ``destructiveHint: false`` would
    publish a guess as fact, so it is not emitted.

    ``openWorldHint`` is never emitted: every connector calls a remote API,
    which is the spec default.

    Args:
        entry: A tool dict from ``ToolKit.list_tools()``.

    Returns:
        Keyword arguments for ``mcp.types.ToolAnnotations`` (possibly empty).
    """
    hints: dict[str, bool] = {}
    access = entry.get("access")
    if entry.get("access_classified"):
        if access == "read":
            hints["readOnlyHint"] = True
        else:
            hints["readOnlyHint"] = False
            hints["destructiveHint"] = access == "destructive"
    # The spec defines idempotentHint only for tools that are not read-only.
    if entry.get("idempotent") and not hints.get("readOnlyHint"):
        hints["idempotentHint"] = True
    return hints


def _make_tool_handler(
    toolkit: ToolKit,
    tool_name: str,
    input_schema: dict[str, Any],
) -> Any:
    """Return an async handler whose ``__signature__`` matches the tool's JSON Schema.

    FastMCP (and every other ``inspect.signature``-based schema generator)
    derives the tool's MCP input schema from the handler's parameter list.
    If the signature is ``(**kwargs: Any)`` FastMCP creates a single opaque
    ``kwargs`` parameter of type ``object`` and routes the LLM's arguments as
    ``_handler(kwargs={...})`` — wrapping the real args in a nested dict.

    By replacing ``__signature__`` with one built from the tool's actual JSON
    Schema properties, each tool's handler has the correct named parameters
    (e.g. ``q``, ``maxResults``).  FastMCP then:

    1. Generates the right per-parameter schema for LLM clients.
    2. Calls the handler as ``_handler(q="...", maxResults=50)``.
    3. ``kwargs`` inside the handler is ``{"q": "...", "maxResults": 50}``.
    4. ``aexecute(tool_name, kwargs)`` receives the correct ``arguments`` dict.
    5. ``method(**arguments)`` unpacks correctly into the connector action.

    Args:
        toolkit: The ToolKit instance that owns the connector.
        tool_name: Fully-qualified tool name (``"{connector}_{action}"``).
        input_schema: JSON Schema dict for the tool's input (from ToolEntry).

    Returns:
        An async callable with a proper ``__signature__`` for schema generation.
    """
    properties: dict[str, Any] = input_schema.get("properties", {})
    required_set: set[str] = set(input_schema.get("required", []))

    params: list[inspect.Parameter] = []
    for param_name, param_schema in properties.items():
        is_required = param_name in required_set
        params.append(
            inspect.Parameter(
                param_name,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                # Omitted optionals surface here (and to FastMCP's Pydantic model)
                # as None. ToolKit.aexecute strips None-valued optionals so the
                # connector action's own default applies — otherwise the action
                # would emit an empty/missing param that upstream APIs reject
                # (HTTP 400). See ToolKit.aexecute for the strip.
                default=inspect.Parameter.empty if is_required else None,
                annotation=_json_type_to_python(param_schema, is_required),
            )
        )

    async def _handler(**kwargs: Any) -> str:
        try:
            result = await toolkit.aexecute(tool_name, kwargs)
            return result if isinstance(result, str) else json.dumps(result, default=str)
        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}")
            raise

    # Replace the signature so FastMCP sees real parameter names, not **kwargs.
    # __signature__ is not a documented attribute of the function type but
    # inspect.signature honors it when present (PEP 362). Pyright/mypy don't
    # know this — runtime is correct.
    _handler.__signature__ = inspect.Signature(params, return_annotation=str)  # type: ignore[attr-defined]
    return _handler


# Minimum ``mcp`` version whose ``FastMCP.tool()`` accepts BOTH
# ``annotations=`` (added 1.7.0) and ``structured_output=`` (added 1.10.0).
# Kept in sync with the ``[mcp]`` extra in pyproject.toml.
_MCP_MIN = "1.10"
# Exclusive ceiling: mcp 2.x removed ``mcp.server.fastmcp`` entirely.
_MCP_MAX_EXCLUSIVE = "2"
_MCP_SPECIFIER = f"mcp>={_MCP_MIN},<{_MCP_MAX_EXCLUSIVE}"


def _mcp_import_error_message(exc: ImportError) -> str:
    """Build a diagnostic for a failed ``mcp.server.fastmcp`` import.

    "Not installed" and "installed but incompatible" (in practice, mcp
    2.x) are different problems with different fixes. The old single
    message ("install with: pip install toolsconnector[mcp]") was wrong
    for the second — it told a user who had just run that exact command
    to run it again.

    Args:
        exc: The original ImportError raised by the failed import.

    Returns:
        A message naming the actual cause and its fix. The caller is
        responsible for chaining ``exc`` via ``raise ... from exc`` so
        mcp 2.x's own diagnostic (which names MCPServer and links the
        migration guide) survives in the traceback.
    """
    try:
        from importlib.metadata import PackageNotFoundError, version

        installed: Optional[str] = version("mcp")
    except PackageNotFoundError:
        installed = None
    except Exception:  # pragma: no cover - metadata backend misbehaving
        installed = None

    if installed is not None:
        # Installed but unusable — almost always a 2.x resolve from an
        # environment that predates the ceiling. Surface the version,
        # because "it's installed" is exactly what makes this confusing.
        return (
            f"The installed 'mcp' package (version {installed}) is not compatible "
            f"with this MCP server. Required: {_MCP_SPECIFIER}. "
            f'Fix with: pip install "{_MCP_SPECIFIER}". '
            f"Original import error: {exc}"
        )

    return (
        f"MCP server requires the 'mcp' package. "
        f'Install with: pip install "toolsconnector[mcp]" '
        f"(resolves to {_MCP_SPECIFIER}). "
        f"Original import error: {exc}"
    )


def create_and_run_mcp_server(
    toolkit: ToolKit,
    *,
    transport: str = "stdio",
    name: str = "toolsconnector",
    host: str = "127.0.0.1",
    port: int = 3000,
) -> None:
    """Create and run an MCP server from a ToolKit.

    Dynamically registers all tools from the ToolKit's filtered list
    with a FastMCP server instance, then starts the server using the
    specified transport.

    Args:
        toolkit: Configured ToolKit instance.
        transport: Transport protocol (``"stdio"``, ``"sse"``,
            ``"streamable-http"``).
        name: Server name shown to MCP clients.
        host: Bind address for HTTP transports. Defaults to
            ``"127.0.0.1"`` (loopback only) — explicit opt-in is
            required for LAN/external exposure since the HTTP transports
            ship without built-in auth. Ignored for stdio.
        port: Port for HTTP transports. Ignored for stdio.

    Raises:
        ImportError: If the ``mcp`` package is not installed.
        ValueError: If an unknown transport is specified.
    """
    try:
        from mcp.server.fastmcp import FastMCP
        from mcp.types import ToolAnnotations
    except ImportError as e:
        # ``from e`` is load-bearing: mcp 2.x's tombstone module raises a
        # ModuleNotFoundError whose message names MCPServer and links the
        # migration guide. Swallowing it cost users the only useful clue.
        raise ImportError(_mcp_import_error_message(e)) from e

    # Validate transport up-front so we don't construct the server
    # (or bind a port) for an unknown value.
    if transport not in ("stdio", "sse", "streamable-http"):
        raise ValueError(
            f"Unknown transport '{transport}'. Supported: 'stdio', 'sse', 'streamable-http'"
        )

    # FastMCP requires host/port at construction time — its ``run()``
    # method does not accept them as kwargs (signature is just
    # ``run(transport=..., mount_path=...)``). Passing them to ``run()``
    # raises ``TypeError: FastMCP.run() got an unexpected keyword
    # argument 'port'``. So we have to wire them in via ``__init__``.
    # See issue #22 for the original repro.
    if transport in ("sse", "streamable-http"):
        server = FastMCP(name, host=host, port=port)
    else:
        # stdio doesn't bind a socket — skip host/port entirely so we
        # don't even hold a port number we'll never use.
        server = FastMCP(name)

    tool_entries = toolkit.list_tools()

    logger.info(f"Registering {len(tool_entries)} tools with MCP server '{name}'")

    for entry_dict in tool_entries:
        tool_name = entry_dict["name"]
        description = entry_dict["description"]
        input_schema = entry_dict.get("input_schema", {})

        handler = _make_tool_handler(toolkit, tool_name, input_schema)
        handler.__name__ = tool_name
        handler.__doc__ = description

        hints = _tool_annotation_hints(entry_dict)
        server.tool(
            name=tool_name,
            description=description,
            # None, not an empty model: the client then applies the spec's
            # worst-case defaults for every undeclared hint.
            annotations=ToolAnnotations.model_validate(hints) if hints else None,
            # Without this FastMCP derives ``{"result": string}`` from the
            # handler's ``-> str`` return type and advertises it as every
            # tool's outputSchema — about a fifth of tools/list, no information.
            structured_output=False,
        )(handler)

    if transport == "stdio":
        logger.info("Starting MCP server (transport=stdio)")
        server.run(transport="stdio")
    else:
        logger.info(f"Starting MCP server (transport={transport}, bind={host}:{port})")
        # Validated against the supported set above; mypy can't narrow ``str``
        # to the Literal that FastMCP.run() declares.
        server.run(transport=cast("Literal['sse', 'streamable-http']", transport))
