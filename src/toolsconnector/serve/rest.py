"""REST API exposure for ToolsConnector.

Creates a lightweight ASGI app that exposes ToolKit tools as REST endpoints.
Requires ``starlette`` (optional dependency via ``pip install "toolsconnector[rest]"``).

Routes::

    GET  {prefix}/connectors              — list all connectors and tools
    GET  {prefix}/{connector}/actions     — list actions for a connector
    POST {prefix}/{connector}/{action}    — execute a tool call
    GET  {prefix}/health                  — health status of all connectors
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from toolsconnector.serve.toolkit import ToolKit

logger = logging.getLogger("toolsconnector.serve.rest")


def create_rest_app(toolkit: ToolKit, *, prefix: str = "/api/v1") -> Any:
    """Create an ASGI app exposing ToolKit tools as REST endpoints.

    Args:
        toolkit: Configured ToolKit instance.
        prefix: URL prefix for all routes (default ``/api/v1``).

    Returns:
        A Starlette ASGI application.

    Raises:
        ImportError: If ``starlette`` is not installed.
    """
    try:
        from starlette.applications import Starlette
        from starlette.requests import Request
        from starlette.responses import JSONResponse
        from starlette.routing import Route
    except ImportError:
        raise ImportError(
            "REST server requires 'starlette' and 'uvicorn'. "
            'Install with: pip install "toolsconnector[rest]"'
        )

    async def list_connectors(request: Request) -> JSONResponse:
        """GET /connectors — list all available tools."""
        tools = toolkit.list_tools()
        connectors: dict[str, Any] = {}
        for t in tools:
            name = t["connector"]
            if name not in connectors:
                connectors[name] = {
                    "name": name,
                    "display_name": t.get("connector_display_name", name),
                    "status": t.get("status", "unknown"),
                    "actions": [],
                }
            connectors[name]["actions"].append(
                {
                    "name": t["action"],
                    "tool_name": t["name"],
                    "description": t["description"],
                    "dangerous": t.get("dangerous", False),
                }
            )
        return JSONResponse(
            {
                "connectors": list(connectors.values()),
                "total_tools": len(tools),
            }
        )

    async def list_actions(request: Request) -> JSONResponse:
        """GET /{connector}/actions — list actions for a connector."""
        connector = request.path_params["connector"]
        tools = toolkit.list_tools()
        actions = [
            {
                "name": t["action"],
                "tool_name": t["name"],
                "description": t["description"],
                "dangerous": t.get("dangerous", False),
                "input_schema": t.get("input_schema", {}),
            }
            for t in tools
            if t["connector"] == connector
        ]
        if not actions:
            return JSONResponse(
                {"error": f"Connector '{connector}' not found"},
                status_code=404,
            )
        return JSONResponse({"connector": connector, "actions": actions})

    async def execute_action(request: Request) -> JSONResponse:
        """POST /{connector}/{action} — execute a tool call."""
        connector = request.path_params["connector"]
        action = request.path_params["action"]
        tool_name = f"{connector}_{action}"

        try:
            body = await request.json()
        except Exception:
            body = {}

        try:
            result = await toolkit.aexecute(tool_name, body)
            # Result is already serialized as string
            try:
                parsed = json.loads(result)
                return JSONResponse({"result": parsed})
            except (json.JSONDecodeError, TypeError):
                return JSONResponse({"result": result})
        except Exception as e:
            status = 500
            error_body: dict[str, Any] = {
                "error": type(e).__name__,
                "message": str(e),
            }
            if hasattr(e, "to_dict"):
                error_body = e.to_dict()
            if hasattr(e, "upstream_status") and e.upstream_status:
                status = e.upstream_status
            if hasattr(e, "suggestion") and e.suggestion:
                error_body["suggestion"] = e.suggestion
            return JSONResponse(error_body, status_code=status)

    async def health(request: Request) -> JSONResponse:
        """GET /health — health status of all connectors."""
        statuses = toolkit.get_connector_status()
        healthy = all(s == "healthy" for s in statuses.values())
        return JSONResponse(
            {
                "status": "healthy" if healthy else "degraded",
                "connectors": statuses,
            }
        )

    routes = [
        Route(f"{prefix}/connectors", list_connectors, methods=["GET"]),
        Route(f"{prefix}/health", health, methods=["GET"]),
        Route(
            f"{prefix}/{{connector}}/actions",
            list_actions,
            methods=["GET"],
        ),
        Route(
            f"{prefix}/{{connector}}/{{action}}",
            execute_action,
            methods=["POST"],
        ),
    ]

    app = Starlette(routes=routes)
    logger.info(f"REST app created with {len(toolkit.list_tools())} tools")
    return app
