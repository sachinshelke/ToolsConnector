"""ToolKit — the centerpiece of the ToolsConnector serve layer.

Configured container that ties together:

- **Schema generation** for OpenAI, Anthropic, and Gemini function-calling formats
- **Tool execution** with async-first design and robust sync wrappers
- **Connector instance caching** with async-safe lazy initialisation
- **Circuit breakers** per connector to avoid hammering dead APIs
- **Pre-validation** of arguments against JSON Schema before execution
- **Timeout budgets** with per-action and per-request deadlines
- **Dry-run mode** for dangerous actions (validate without executing)
- **Graceful degradation** — unhealthy connectors don't block healthy ones
- **Structured logging** with request IDs for observability

Configure once, use everywhere::

    kit = ToolKit(
        ["gmail", "slack"],
        credentials={"gmail": "token1", "slack": "token2"},
    )

    # Generate schemas for any AI framework
    tools = kit.to_openai_tools()

    # Execute tool calls
    result = await kit.aexecute("gmail_list_emails", {"query": "is:unread"})

    # Serve as MCP server
    kit.serve_mcp()
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Optional

from toolsconnector.serve._discovery import resolve_connectors
from toolsconnector.serve._credentials import resolve_credentials
from toolsconnector.serve._filtering import build_tool_list, ToolEntry
from toolsconnector.serve._validation import validate_arguments
from toolsconnector.serve._circuit_breaker import CircuitBreaker
from toolsconnector.serve._serialization import serialize_result

from toolsconnector.runtime.base import BaseConnector
from toolsconnector.runtime._sync import run_sync
from toolsconnector.errors import (
    ToolsConnectorError,
    ValidationError,
    TokenExpiredError,
    ConnectorNotConfiguredError,
    ServerError,
)
from toolsconnector.errors import TimeoutError as TCTimeoutError


# ---------------------------------------------------------------------------
# Schema format helpers
#
# These live inline because the ``toolsconnector.serve.schema`` module is
# defined separately and may not exist yet.  The ToolKit methods delegate
# to a lazy import so the file is self-contained at import time.
# ---------------------------------------------------------------------------

def _to_openai_schema(entry: ToolEntry) -> dict[str, Any]:
    """Convert a ToolEntry to an OpenAI function-calling tool definition.

    Matches the ``tools`` array format expected by ``chat.completions.create``.

    Args:
        entry: The ToolEntry to convert.

    Returns:
        Dict conforming to the OpenAI tool schema.
    """
    return {
        "type": "function",
        "function": {
            "name": entry.tool_name,
            "description": entry.description,
            "parameters": entry.input_schema,
        },
    }


def _to_anthropic_schema(entry: ToolEntry) -> dict[str, Any]:
    """Convert a ToolEntry to an Anthropic tool-use definition.

    Matches the ``tools`` array format expected by ``messages.create``.

    Args:
        entry: The ToolEntry to convert.

    Returns:
        Dict conforming to the Anthropic tool schema.
    """
    return {
        "name": entry.tool_name,
        "description": entry.description,
        "input_schema": entry.input_schema,
    }


def _to_gemini_schema(entry: ToolEntry) -> dict[str, Any]:
    """Convert a ToolEntry to a Google Gemini function declaration.

    Matches the ``function_declarations`` format expected by the
    Gemini ``generate_content`` API.

    Args:
        entry: The ToolEntry to convert.

    Returns:
        Dict conforming to the Gemini function declaration schema.
    """
    # Gemini uses a slightly different schema envelope: top-level keys are
    # name / description / parameters, and the parameters block must not
    # include ``additionalProperties`` (Gemini rejects it).
    params = dict(entry.input_schema)
    params.pop("additionalProperties", None)

    return {
        "name": entry.tool_name,
        "description": entry.description,
        "parameters": params,
    }


# ---------------------------------------------------------------------------
# ToolKit
# ---------------------------------------------------------------------------

class ToolKit:
    """Configured container for connectors with schema generation + execution.

    ToolKit is the primary interface for the serve layer.  Configure once,
    use everywhere -- MCP, OpenAI, Anthropic, Gemini, LangChain, REST, CLI.

    Args:
        connectors: List of connector classes or name strings.
            E.g. ``["gmail", "slack"]`` or ``[Gmail, Slack]``.
        credentials: Mapping of connector name to credential string.
        tenant_id: Tenant identifier for multi-tenant deployments.
        include_actions: Glob patterns -- only matching actions included.
        exclude_actions: Glob patterns -- matching actions excluded.
        exclude_dangerous: If ``True``, exclude all dangerous actions.
        timeout_budget: Maximum wall-clock seconds for a single
            ``aexecute`` call, including retries.
        action_timeout: Per-attempt timeout for a single action call.
        verify_on_init: If ``True``, health-check all connectors at init.
        circuit_breaker_threshold: Consecutive failures before opening.
        circuit_breaker_recovery: Seconds before testing recovery.

    Example::

        kit = ToolKit(
            ["gmail", "slack"],
            credentials={"gmail": "token1", "slack": "token2"},
        )

        # Generate schemas for any AI framework
        tools = kit.to_openai_tools()

        # Execute tool calls
        result = await kit.aexecute("gmail_list_emails", {"query": "is:unread"})

        # Serve as MCP server
        kit.serve_mcp()
    """

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def __init__(
        self,
        connectors: list,  # list[type[BaseConnector] | str]
        *,
        credentials: Optional[dict[str, str]] = None,
        tenant_id: Optional[str] = None,
        include_actions: Optional[list[str]] = None,
        exclude_actions: Optional[list[str]] = None,
        exclude_dangerous: bool = False,
        timeout_budget: float = 25.0,
        action_timeout: float = 15.0,
        verify_on_init: bool = False,
        circuit_breaker_threshold: int = 5,
        circuit_breaker_recovery: float = 60.0,
    ) -> None:
        # -- Resolve connector classes --
        self._connector_classes: dict[str, type] = {}
        resolved = resolve_connectors(connectors)
        for cls in resolved:
            self._connector_classes[cls.name] = cls

        # -- Config --
        self._credentials = credentials or {}
        self._tenant_id = tenant_id
        self._timeout_budget = timeout_budget
        self._action_timeout = action_timeout

        # -- Build filtered tool list --
        self._tool_entries_list: list[ToolEntry] = build_tool_list(
            resolved,
            include_actions=include_actions,
            exclude_actions=exclude_actions,
            exclude_dangerous=exclude_dangerous,
        )

        # Index by tool_name for O(1) lookup during execution
        self._tool_entries: dict[str, ToolEntry] = {
            e.tool_name: e for e in self._tool_entries_list
        }

        # -- Instance cache (lazy, one per connector) --
        self._instances: dict[str, BaseConnector] = {}
        # Locks created lazily in _get_instance() to avoid requiring
        # an event loop at ToolKit construction time (Python 3.9 compat)
        self._setup_locks: dict[str, asyncio.Lock] = {}

        # -- Circuit breakers (one per connector) --
        self._circuit_breakers: dict[str, CircuitBreaker] = {
            name: CircuitBreaker(
                failure_threshold=circuit_breaker_threshold,
                recovery_timeout=circuit_breaker_recovery,
            )
            for name in self._connector_classes
        }

        # -- Health tracking --
        self._connector_status: dict[str, str] = {
            name: "unknown" for name in self._connector_classes
        }

        # -- Logger --
        self._logger = logging.getLogger("toolsconnector.serve")

        # -- Optional eagerness --
        if verify_on_init:
            run_sync(self._verify_all())

    # ------------------------------------------------------------------
    # Schema generation
    # ------------------------------------------------------------------

    def to_openai_tools(self) -> list[dict[str, Any]]:
        """Generate OpenAI function-calling tool definitions.

        Returns:
            List of tool dicts ready for ``tools`` param in
            ``chat.completions.create``.
        """
        try:
            from toolsconnector.serve.schema import to_openai_schema
            return [to_openai_schema(e) for e in self._tool_entries_list]
        except ImportError:
            return [_to_openai_schema(e) for e in self._tool_entries_list]

    def to_anthropic_tools(self) -> list[dict[str, Any]]:
        """Generate Anthropic tool-use definitions.

        Returns:
            List of tool dicts ready for ``tools`` param in
            ``messages.create``.
        """
        try:
            from toolsconnector.serve.schema import to_anthropic_schema
            return [to_anthropic_schema(e) for e in self._tool_entries_list]
        except ImportError:
            return [_to_anthropic_schema(e) for e in self._tool_entries_list]

    def to_gemini_tools(self) -> list[dict[str, Any]]:
        """Generate Google Gemini function declarations.

        Returns:
            List of function declaration dicts ready for Gemini's
            ``generate_content`` API.
        """
        try:
            from toolsconnector.serve.schema import to_gemini_schema
            return [to_gemini_schema(e) for e in self._tool_entries_list]
        except ImportError:
            return [_to_gemini_schema(e) for e in self._tool_entries_list]

    def to_langchain_tools(self) -> list:
        """Generate LangChain StructuredTool objects with built-in execution.

        Requires langchain-core: pip install langchain-core
        """
        from toolsconnector.serve.adapters import to_langchain_tools
        return to_langchain_tools(self)

    def to_crewai_tools(self) -> list:
        """Generate CrewAI-compatible tools."""
        from toolsconnector.serve.adapters import to_crewai_tools
        return to_crewai_tools(self)

    # ------------------------------------------------------------------
    # Execution — async
    # ------------------------------------------------------------------

    async def aexecute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        dry_run: bool = False,
    ) -> Any:
        """Execute a tool call by name (async).

        This is the primary execution entry point.  It performs:

        1. Tool lookup and validation
        2. Dry-run check for dangerous actions
        3. Argument pre-validation against JSON Schema
        4. Circuit breaker gating
        5. Budgeted execution with auto-retry on transient failures

        Args:
            tool_name: Tool name in ``"{connector}_{action}"`` format.
            arguments: Arguments dict matching the tool's input schema.
            dry_run: If ``True`` and action is dangerous, validate
                without executing.

        Returns:
            Serialized result string (JSON).

        Raises:
            ConnectorNotConfiguredError: Unknown tool name.
            ValidationError: Arguments don't match schema.
            ToolsConnectorError: Any connector error.
        """
        request_id = uuid.uuid4().hex[:8]
        start = time.monotonic()

        # 1. Find tool entry
        entry = self._tool_entries.get(tool_name)
        if entry is None:
            available = ", ".join(sorted(self._tool_entries.keys())[:5])
            raise ConnectorNotConfiguredError(
                f"Unknown tool '{tool_name}'.",
                connector="",
                suggestion=(
                    f"Available tools: {available}..."
                    f" Use list_tools() for full list."
                ),
            )

        connector_name = entry.connector_name
        action_name = entry.action_name

        self._logger.info(
            "tool.call.start",
            extra={
                "request_id": request_id,
                "tool": tool_name,
                "connector": connector_name,
                "tenant": self._tenant_id,
            },
        )

        # 2. Dry-run check for dangerous actions
        if dry_run and entry.dangerous:
            return serialize_result({
                "dry_run": True,
                "tool": tool_name,
                "would_execute": entry.description,
                "arguments": arguments,
                "warning": (
                    "Destructive action. Set dry_run=False to execute."
                ),
            })

        # 3. Pre-validate arguments
        errors = validate_arguments(entry.input_schema, arguments)
        if errors:
            raise ValidationError(
                f"Invalid arguments for {tool_name}: {'; '.join(errors)}",
                connector=connector_name,
                action=action_name,
                suggestion=(
                    "Expected parameters: "
                    f"{list(entry.input_schema.get('properties', {}).keys())}"
                ),
                details={"validation_errors": errors},
            )

        # 4. Circuit breaker gating
        cb = self._circuit_breakers.get(connector_name)
        if cb and cb.is_open:
            recovery_secs = cb.status_dict().get("recovery_in_seconds", 60)
            raise ServerError(
                f"Connector '{connector_name}' is temporarily unavailable"
                " (circuit open).",
                connector=connector_name,
                action=action_name,
                retry_eligible=True,
                retry_after_seconds=recovery_secs,
                suggestion=(
                    f"The {connector_name} API has been failing."
                    f" Will retry automatically in {int(recovery_secs)}s."
                ),
            )

        # 5. Execute with timeout budget + auto-retry
        try:
            result = await self._execute_with_budget(
                connector_name, action_name, arguments, request_id,
            )

            # Record success on the circuit breaker
            if cb:
                cb.record_success()
            self._connector_status[connector_name] = "healthy"

            duration = time.monotonic() - start
            self._logger.info(
                "tool.call.success",
                extra={
                    "request_id": request_id,
                    "tool": tool_name,
                    "duration_ms": round(duration * 1000),
                },
            )
            return serialize_result(result)

        except ToolsConnectorError as exc:
            if cb and exc.retry_eligible:
                cb.record_failure(exc)

            duration = time.monotonic() - start
            self._logger.error(
                "tool.call.error",
                extra={
                    "request_id": request_id,
                    "tool": tool_name,
                    "error_code": exc.code,
                    "duration_ms": round(duration * 1000),
                },
            )
            raise

    # ------------------------------------------------------------------
    # Execution — sync
    # ------------------------------------------------------------------

    def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        dry_run: bool = False,
    ) -> Any:
        """Execute a tool call by name (sync wrapper).

        Delegates to :meth:`aexecute` via the sync/async bridge.
        See :meth:`aexecute` for full documentation.

        Args:
            tool_name: Tool name in ``"{connector}_{action}"`` format.
            arguments: Arguments dict matching the tool's input schema.
            dry_run: If ``True`` and action is dangerous, validate
                without executing.

        Returns:
            Serialized result string (JSON).
        """
        return run_sync(
            self.aexecute(tool_name, arguments, dry_run=dry_run)
        )

    # ------------------------------------------------------------------
    # Internal execution
    # ------------------------------------------------------------------

    async def _execute_with_budget(
        self,
        connector_name: str,
        action_name: str,
        arguments: dict[str, Any],
        request_id: str,
    ) -> Any:
        """Execute an action within the timeout budget with auto-retry.

        Handles:
        - Per-attempt timeouts (``_action_timeout``)
        - Overall deadline (``_timeout_budget``)
        - Token refresh on ``TokenExpiredError``
        - Exponential backoff on transient failures

        Args:
            connector_name: Name of the connector.
            action_name: Name of the action method.
            arguments: Validated arguments dict.
            request_id: Correlation ID for logging.

        Returns:
            Raw action result (not yet serialized).

        Raises:
            TCTimeoutError: If the budget is exhausted.
            ToolsConnectorError: Propagated from the action.
        """
        deadline = time.monotonic() + self._timeout_budget
        attempt = 0
        last_error: Optional[Exception] = None

        while time.monotonic() < deadline:
            attempt += 1
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break

            try:
                instance = await self._get_instance(connector_name)

                # Prefer async method (a{action_name}), fall back to sync
                method = getattr(instance, f"a{action_name}", None)
                if method is None:
                    method = getattr(instance, action_name)

                return await asyncio.wait_for(
                    method(**arguments),
                    timeout=min(self._action_timeout, remaining),
                )

            except TokenExpiredError:
                self._logger.info(
                    "tool.auth.refresh",
                    extra={
                        "request_id": request_id,
                        "connector": connector_name,
                    },
                )
                # Evict cached instance so next attempt re-authenticates
                self._instances.pop(connector_name, None)
                if attempt >= 2:
                    raise
                continue

            except ToolsConnectorError as exc:
                last_error = exc
                if not exc.retry_eligible or time.monotonic() >= deadline:
                    raise
                wait = min(
                    exc.retry_after_seconds or (2 ** attempt),
                    remaining - 0.5,
                )
                if wait <= 0:
                    raise
                self._logger.info(
                    "tool.retry",
                    extra={
                        "request_id": request_id,
                        "connector": connector_name,
                        "attempt": attempt,
                        "wait_seconds": round(wait, 1),
                    },
                )
                await asyncio.sleep(wait)

            except asyncio.TimeoutError:
                last_error = TCTimeoutError(
                    f"Action '{action_name}' timed out after"
                    f" {self._action_timeout}s",
                    connector=connector_name,
                    action=action_name,
                )
                if time.monotonic() >= deadline:
                    raise last_error
                self._logger.warning(
                    "tool.timeout",
                    extra={
                        "request_id": request_id,
                        "connector": connector_name,
                        "attempt": attempt,
                    },
                )
                continue

        # Budget exhausted
        if last_error is not None:
            raise last_error
        raise TCTimeoutError(
            "Timeout budget exhausted.",
            connector=connector_name,
        )

    # ------------------------------------------------------------------
    # Instance management
    # ------------------------------------------------------------------

    async def _get_instance(self, connector_name: str) -> BaseConnector:
        """Get or create a cached connector instance.

        Uses per-connector async locks to prevent duplicate instantiation
        during concurrent requests.

        Args:
            connector_name: The connector to instantiate.

        Returns:
            A ready-to-use BaseConnector instance.

        Raises:
            ConnectorNotConfiguredError: If the connector class is unknown.
            Exception: If setup fails (status set to ``"degraded"``).
        """
        if connector_name in self._instances:
            return self._instances[connector_name]

        lock = self._setup_locks.get(connector_name)
        if lock is None:
            lock = asyncio.Lock()
            self._setup_locks[connector_name] = lock

        async with lock:
            # Double-checked locking
            if connector_name in self._instances:
                return self._instances[connector_name]

            cls = self._connector_classes.get(connector_name)
            if cls is None:
                raise ConnectorNotConfiguredError(
                    f"Connector '{connector_name}' is not registered.",
                    connector=connector_name,
                )

            cred = resolve_credentials(connector_name, self._credentials)
            instance = cls(
                credentials=cred,
                tenant_id=self._tenant_id,
            )

            try:
                await instance._setup()
                self._instances[connector_name] = instance
                self._connector_status[connector_name] = "healthy"
                self._logger.debug(
                    "connector.setup.ok",
                    extra={"connector": connector_name},
                )
                return instance
            except Exception as exc:
                self._connector_status[connector_name] = "degraded"
                self._logger.warning(
                    "connector.setup.failed",
                    extra={
                        "connector": connector_name,
                        "error": str(exc),
                    },
                )
                raise

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def list_tools(self) -> list[dict[str, Any]]:
        """List all available tools with metadata and health status.

        Returns:
            List of tool dicts enriched with connector status.
        """
        return [
            {
                **entry.to_dict(),
                "status": self._connector_status.get(
                    entry.connector_name, "unknown"
                ),
            }
            for entry in self._tool_entries_list
        ]

    def get_tool_schema(self, tool_name: str) -> dict[str, Any]:
        """Get the input JSON Schema for a specific tool.

        Args:
            tool_name: The namespaced tool name.

        Returns:
            JSON Schema dict for the tool's input parameters.

        Raises:
            ConnectorNotConfiguredError: If the tool name is unknown.
        """
        entry = self._tool_entries.get(tool_name)
        if entry is None:
            raise ConnectorNotConfiguredError(
                f"Unknown tool '{tool_name}'.",
                connector="",
            )
        return entry.input_schema

    def get_connector_status(self) -> dict[str, str]:
        """Get the health status of all configured connectors.

        Returns:
            Dict mapping connector name to status string.
            Possible values: ``"unknown"``, ``"healthy"``, ``"degraded"``.
        """
        return dict(self._connector_status)

    @property
    def tool_count(self) -> int:
        """Number of tools available in this ToolKit."""
        return len(self._tool_entries)

    @property
    def connector_names(self) -> list[str]:
        """Sorted list of configured connector names."""
        return sorted(self._connector_classes.keys())

    # ------------------------------------------------------------------
    # Serving
    # ------------------------------------------------------------------

    def serve_mcp(
        self,
        *,
        transport: str = "stdio",
        name: str = "toolsconnector",
        port: int = 3000,
    ) -> None:
        """Start an MCP server exposing all configured tools.

        Blocks until the server shuts down.

        Args:
            transport: Transport type (``"stdio"`` or ``"http"``).
            name: Server name advertised to MCP clients.
            port: Port number for HTTP transport.
        """
        from toolsconnector.serve.mcp import create_and_run_mcp_server

        create_and_run_mcp_server(
            self, transport=transport, name=name, port=port,
        )

    def create_rest_app(self, *, prefix: str = "/api/v1") -> Any:
        """Create an ASGI app exposing tools as REST endpoints.

        Args:
            prefix: URL prefix for all tool endpoints.

        Returns:
            An ASGI application (e.g. Starlette or FastAPI).
        """
        from toolsconnector.serve.rest import create_rest_app

        return create_rest_app(self, prefix=prefix)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _verify_all(self) -> None:
        """Health-check all connectors during init.

        Called when ``verify_on_init=True``.  Failures are logged but
        do not prevent ToolKit construction -- the connector is simply
        marked as ``"degraded"``.
        """
        for name in self._connector_classes:
            try:
                instance = await self._get_instance(name)
                health = await instance._health_check()
                if health.healthy:
                    self._connector_status[name] = "healthy"
                    latency = (
                        f"{health.latency_ms}ms" if health.latency_ms else "?"
                    )
                    self._logger.info(
                        "connector.verify.healthy",
                        extra={
                            "connector": name,
                            "latency": latency,
                        },
                    )
                else:
                    self._connector_status[name] = "degraded"
                    self._logger.warning(
                        "connector.verify.degraded",
                        extra={
                            "connector": name,
                            "message": health.message,
                        },
                    )
            except Exception as exc:
                self._connector_status[name] = "degraded"
                self._logger.warning(
                    "connector.verify.failed",
                    extra={
                        "connector": name,
                        "error": str(exc),
                    },
                )

    async def aclose(self) -> None:
        """Gracefully shut down all cached connector instances.

        Calls ``_teardown()`` on each active instance.  Errors during
        teardown are logged but do not propagate.
        """
        for name, instance in self._instances.items():
            try:
                await instance._teardown()
                self._logger.debug(
                    "connector.teardown.ok",
                    extra={"connector": name},
                )
            except Exception as exc:
                self._logger.warning(
                    "connector.teardown.failed",
                    extra={
                        "connector": name,
                        "error": str(exc),
                    },
                )
        self._instances.clear()

    def close(self) -> None:
        """Gracefully shut down all cached connector instances (sync).

        Delegates to :meth:`aclose` via the sync/async bridge.
        """
        run_sync(self.aclose())

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    async def __aenter__(self) -> ToolKit:
        """Async context manager entry."""
        return self

    async def __aexit__(self, *exc: Any) -> None:
        """Async context manager exit -- tears down all connectors."""
        await self.aclose()

    def __enter__(self) -> ToolKit:
        """Sync context manager entry."""
        return self

    def __exit__(self, *exc: Any) -> None:
        """Sync context manager exit -- tears down all connectors."""
        self.close()

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        n_tools = len(self._tool_entries)
        n_connectors = len(self._connector_classes)
        return f"<ToolKit(connectors={n_connectors}, tools={n_tools})>"

    def __len__(self) -> int:
        """Return the number of tools available."""
        return len(self._tool_entries)

    def __contains__(self, tool_name: str) -> bool:
        """Check if a tool name is available in this ToolKit."""
        return tool_name in self._tool_entries


# ---------------------------------------------------------------------------
# ToolKitFactory — multi-tenant ToolKit management
# ---------------------------------------------------------------------------

class ToolKitFactory:
    """Factory for creating per-tenant ToolKit instances.

    In multi-tenant deployments (like AgentStore), each user/tenant
    gets their own ToolKit with isolated credentials and rate limits.

    Usage::

        factory = ToolKitFactory(
            connectors=["gmail", "slack"],
            exclude_dangerous=True,
        )

        # Per-user toolkit
        user_kit = factory.for_tenant(
            tenant_id="user-123",
            credentials={"gmail": user_gmail_token, "slack": user_slack_token},
        )
        result = await user_kit.aexecute("gmail_list_emails", {"query": "is:unread"})
    """

    def __init__(
        self,
        connectors: list,
        *,
        include_actions: Optional[list[str]] = None,
        exclude_actions: Optional[list[str]] = None,
        exclude_dangerous: bool = False,
        timeout_budget: float = 25.0,
        action_timeout: float = 15.0,
    ) -> None:
        self._connectors = connectors
        self._include_actions = include_actions
        self._exclude_actions = exclude_actions
        self._exclude_dangerous = exclude_dangerous
        self._timeout_budget = timeout_budget
        self._action_timeout = action_timeout
        self._tenant_kits: dict[str, ToolKit] = {}

    def for_tenant(
        self,
        tenant_id: str,
        credentials: dict[str, str],
    ) -> ToolKit:
        """Get or create a ToolKit for a specific tenant.

        Args:
            tenant_id: Unique tenant identifier.
            credentials: Per-tenant credentials dict.

        Returns:
            ToolKit configured for this tenant.
        """
        if tenant_id not in self._tenant_kits:
            self._tenant_kits[tenant_id] = ToolKit(
                self._connectors,
                credentials=credentials,
                tenant_id=tenant_id,
                include_actions=self._include_actions,
                exclude_actions=self._exclude_actions,
                exclude_dangerous=self._exclude_dangerous,
                timeout_budget=self._timeout_budget,
                action_timeout=self._action_timeout,
            )
        return self._tenant_kits[tenant_id]

    async def close_tenant(self, tenant_id: str) -> None:
        """Close and remove a tenant's ToolKit.

        Args:
            tenant_id: Tenant to close.
        """
        kit = self._tenant_kits.pop(tenant_id, None)
        if kit:
            await kit.aclose()

    async def close_all(self) -> None:
        """Close all tenant ToolKits."""
        for kit in self._tenant_kits.values():
            await kit.aclose()
        self._tenant_kits.clear()

    @property
    def active_tenants(self) -> list[str]:
        """Sorted list of currently active tenant IDs."""
        return sorted(self._tenant_kits.keys())
