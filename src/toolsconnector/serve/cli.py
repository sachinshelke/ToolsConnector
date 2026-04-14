"""tc CLI command for ToolsConnector.

Usage:
    tc list                                    -- list all connectors
    tc <connector> actions                     -- list actions
    tc <connector> <action> [--param value]    -- execute action
    tc <connector> spec [--format json|yaml]   -- export spec
    tc serve mcp <connectors...> [--transport] -- start MCP server
    tc serve rest <connectors...> [--port]     -- start REST server
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Optional


def main(argv: Optional[list[str]] = None) -> int:
    """Main entry point for the tc CLI.

    Args:
        argv: Command-line arguments. Defaults to ``sys.argv[1:]``.

    Returns:
        Exit code (0 for success, non-zero for errors).
    """
    parser = argparse.ArgumentParser(
        prog="tc",
        description="ToolsConnector CLI -- manage and serve tool connectors",
    )
    subparsers = parser.add_subparsers(dest="command")

    # tc list
    subparsers.add_parser("list", help="List all available connectors")

    # tc serve
    serve_parser = subparsers.add_parser("serve", help="Start a server")
    serve_sub = serve_parser.add_subparsers(dest="serve_type")

    # tc serve mcp
    mcp_parser = serve_sub.add_parser("mcp", help="Start MCP server")
    mcp_parser.add_argument("connectors", nargs="+", help="Connectors to serve")
    mcp_parser.add_argument(
        "--transport",
        default="stdio",
        help="Transport: stdio|sse|streamable-http",
    )
    mcp_parser.add_argument(
        "--port", type=int, default=3000, help="Port for HTTP transports"
    )
    mcp_parser.add_argument(
        "--name", default="toolsconnector", help="Server name"
    )

    # tc serve rest
    rest_parser = serve_sub.add_parser("rest", help="Start REST server")
    rest_parser.add_argument("connectors", nargs="+", help="Connectors to serve")
    rest_parser.add_argument("--port", type=int, default=8000, help="Port")
    rest_parser.add_argument("--prefix", default="/api/v1", help="URL prefix")

    # Try dynamic connector command FIRST (before argparse)
    # This handles: tc gmail actions, tc gmail list_emails --query "..."
    effective_argv = argv if argv is not None else sys.argv[1:]
    if effective_argv and effective_argv[0] not in ("list", "serve", "-h", "--help"):
        from toolsconnector.serve._discovery import list_connectors as _lc
        if effective_argv[0] in _lc():
            return _handle_connector_command(list(effective_argv))

    # Standard subcommand parsing
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 1

    if args.command == "list":
        return _cmd_list()
    elif args.command == "serve":
        if args.serve_type == "mcp":
            return _cmd_serve_mcp(args)
        elif args.serve_type == "rest":
            return _cmd_serve_rest(args)
        else:
            serve_parser.print_help()
            return 1

    return 0


def _cmd_list() -> int:
    """List all available connectors.

    Returns:
        Exit code.
    """
    from toolsconnector.serve._discovery import list_connectors, get_connector_class

    connectors = list_connectors()
    print(f"\nAvailable connectors ({len(connectors)}):\n")

    # Group by category
    categories: dict[str, list[tuple[str, str]]] = {}
    for name in connectors:
        try:
            cls = get_connector_class(name)
            spec = cls.get_spec()
            cat = spec.category.value
            categories.setdefault(cat, []).append((name, spec.display_name))
        except Exception:
            categories.setdefault("unknown", []).append((name, name))

    for cat in sorted(categories.keys()):
        items = categories[cat]
        print(f"  {cat}:")
        for name, display in sorted(items):
            print(f"    {name:<20} {display}")
    print()
    return 0


def _cmd_serve_mcp(args: argparse.Namespace) -> int:
    """Start MCP server.

    Args:
        args: Parsed CLI arguments.

    Returns:
        Exit code.
    """
    from toolsconnector.serve.toolkit import ToolKit

    try:
        kit = ToolKit(args.connectors)
        print(f"Starting MCP server with {len(kit.list_tools())} tools...")
        kit.serve_mcp(
            transport=args.transport,
            name=args.name,
            port=args.port,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


def _cmd_serve_rest(args: argparse.Namespace) -> int:
    """Start REST server.

    Args:
        args: Parsed CLI arguments.

    Returns:
        Exit code.
    """
    try:
        import uvicorn
    except ImportError:
        print(
            "REST server requires uvicorn. "
            'Install with: pip install "toolsconnector[rest]"',
            file=sys.stderr,
        )
        return 1

    from toolsconnector.serve.toolkit import ToolKit

    try:
        kit = ToolKit(args.connectors)
        app = kit.create_rest_app(prefix=args.prefix)
        print(
            f"Starting REST server with {len(kit.list_tools())} tools "
            f"on port {args.port}..."
        )
        uvicorn.run(app, host="0.0.0.0", port=args.port)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


def _handle_connector_command(argv: list[str]) -> int:
    """Handle tc <connector> [actions|<action> --params|spec].

    Args:
        argv: Raw CLI arguments starting with the connector name.

    Returns:
        Exit code.
    """
    from toolsconnector.serve._discovery import get_connector_class, list_connectors
    from toolsconnector.serve._serialization import serialize_result

    connector_name = argv[0]

    # Check if it's a known connector
    if connector_name not in list_connectors():
        print(f"Unknown command or connector: '{connector_name}'", file=sys.stderr)
        print("Use 'tc list' to see available connectors.", file=sys.stderr)
        return 1

    if len(argv) < 2:
        # tc gmail -> show actions
        return _show_actions(connector_name)

    subcommand = argv[1]

    if subcommand == "actions":
        return _show_actions(connector_name)

    if subcommand == "spec":
        return _show_spec(connector_name, argv[2:])

    # tc gmail list_emails --query "is:unread"
    return _execute_action(connector_name, subcommand, argv[2:])


def _show_actions(connector_name: str) -> int:
    """Show all actions for a connector.

    Args:
        connector_name: Registered connector name.

    Returns:
        Exit code.
    """
    from toolsconnector.serve._discovery import get_connector_class

    cls = get_connector_class(connector_name)
    spec = cls.get_spec()

    print(f"\n{spec.display_name} ({spec.name}) -- {spec.description}\n")
    print(f"Actions ({len(spec.actions)}):\n")
    for name, action in sorted(spec.actions.items()):
        danger = " [DANGEROUS]" if action.dangerous else ""
        params = ", ".join(p.name for p in action.parameters)
        print(f"  {name:<30} {action.description}{danger}")
        if params:
            print(f"    params: {params}")
    print()
    return 0


def _show_spec(connector_name: str, extra_args: list[str]) -> int:
    """Export connector spec.

    Args:
        connector_name: Registered connector name.
        extra_args: Additional CLI arguments (e.g. ``--format yaml``).

    Returns:
        Exit code.
    """
    from toolsconnector.serve._discovery import get_connector_class

    cls = get_connector_class(connector_name)
    spec = cls.get_spec()

    fmt = "json"
    for i, arg in enumerate(extra_args):
        if arg == "--format" and i + 1 < len(extra_args):
            fmt = extra_args[i + 1]

    if fmt == "json":
        print(spec.model_dump_json(indent=2))
    elif fmt == "yaml":
        try:
            import yaml

            print(yaml.dump(spec.model_dump(), default_flow_style=False))
        except ImportError:
            print(
                "YAML export requires pyyaml. Install with: pip install pyyaml",
                file=sys.stderr,
            )
            return 1
    else:
        print(f"Unknown format: {fmt}. Use 'json' or 'yaml'.", file=sys.stderr)
        return 1
    return 0


def _execute_action(
    connector_name: str, action_name: str, args_list: list[str]
) -> int:
    """Execute a connector action from CLI args.

    Parses ``--key value`` pairs from the argument list, coercing values
    to int, float, or bool where possible, then delegates to ToolKit.

    Args:
        connector_name: Registered connector name.
        action_name: Action to invoke.
        args_list: Remaining CLI arguments as ``--key value`` pairs.

    Returns:
        Exit code.
    """
    from toolsconnector.serve.toolkit import ToolKit
    from toolsconnector.serve._serialization import serialize_result

    # Parse --key value pairs
    arguments: dict[str, object] = {}
    i = 0
    while i < len(args_list):
        if args_list[i].startswith("--"):
            key = args_list[i][2:].replace("-", "_")
            if i + 1 < len(args_list) and not args_list[i + 1].startswith("--"):
                value = args_list[i + 1]
                # Try to parse as int/float/bool
                try:
                    arguments[key] = int(value)
                except ValueError:
                    try:
                        arguments[key] = float(value)
                    except ValueError:
                        if value.lower() in ("true", "false"):
                            arguments[key] = value.lower() == "true"
                        else:
                            arguments[key] = value
                i += 2
            else:
                arguments[key] = True
                i += 1
        else:
            i += 1

    tool_name = f"{connector_name}_{action_name}"

    try:
        kit = ToolKit([connector_name])
        result = kit.execute(tool_name, arguments)
        print(result)
        return 0
    except Exception as e:
        if hasattr(e, "suggestion") and e.suggestion:
            print(f"Error: {e}\nSuggestion: {e.suggestion}", file=sys.stderr)
        else:
            print(f"Error: {e}", file=sys.stderr)
        return 1
