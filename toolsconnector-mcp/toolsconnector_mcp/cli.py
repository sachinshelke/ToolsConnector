"""CLI entry point for toolsconnector-mcp.

Usage:
    tc-mcp serve gmail slack github --transport stdio
    tc-mcp serve gmail slack --exclude-dangerous
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional


def main(argv: Optional[list[str]] = None) -> int:
    """Main entry point for tc-mcp CLI."""
    parser = argparse.ArgumentParser(
        prog="tc-mcp",
        description="ToolsConnector Enhanced MCP Server",
    )
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="Start MCP server")
    serve.add_argument(
        "connectors", nargs="+", help="Connectors to serve"
    )
    serve.add_argument(
        "--transport",
        default="stdio",
        help="Transport: stdio|sse|streamable-http",
    )
    serve.add_argument(
        "--port", type=int, default=3000, help="Port for HTTP"
    )
    serve.add_argument(
        "--name",
        default="toolsconnector",
        help="Server name",
    )
    serve.add_argument(
        "--exclude-dangerous",
        action="store_true",
        help="Exclude dangerous actions",
    )
    serve.add_argument(
        "--no-optimize",
        action="store_true",
        help="Disable schema optimization",
    )

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 1

    if args.command == "serve":
        from toolsconnector_mcp.server import MCPServer

        server = MCPServer(
            args.connectors,
            exclude_dangerous=args.exclude_dangerous,
            name=args.name,
            optimize_schemas=not args.no_optimize,
        )
        print(
            f"Starting MCP server with {server.tool_count} tools "
            f"({', '.join(server.connector_names)})"
        )
        try:
            server.run(transport=args.transport, port=args.port)
        except KeyboardInterrupt:
            print("\nServer stopped.")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
