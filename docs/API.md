# API Reference

Complete reference for all public classes, methods, and types in ToolsConnector.

---

## ToolKit

The single entry point for all connector operations. Configure once, use everywhere.

```python
from toolsconnector.serve import ToolKit
```

**Constructor:**

```python
ToolKit(
    connectors: list[type[BaseConnector] | str],
    *,
    credentials: dict[str, str] | None = None,
    tenant_id: str | None = None,
    include_actions: list[str] | None = None,
    exclude_actions: list[str] | None = None,
    exclude_dangerous: bool = False,
    timeout_budget: float = 25.0,
    action_timeout: float = 15.0,
    verify_on_init: bool = False,
    circuit_breaker_threshold: int = 5,
    circuit_breaker_recovery: float = 60.0,
)
```

**Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `execute` | `(tool_name: str, arguments: dict | str, *, dry_run: bool = False) -> Any` | Execute an action; `arguments` may be a JSON object string |
| `aexecute` | `async (tool_name: str, arguments: dict | str, *, dry_run: bool = False) -> Any` | Async version of `execute` |
| `list_tools` | `() -> list[dict]` | All tools with description, input schema, `access`, `access_classified`, `dangerous` and status |
| `get_tool_schema` | `(tool_name: str) -> dict` | Input JSON Schema of one tool |
| `to_openai_tools` | `() -> list[dict]` | Generate OpenAI function-calling schemas |
| `to_anthropic_tools` | `() -> list[dict]` | Generate Anthropic tool-use schemas |
| `to_gemini_tools` | `() -> list[dict]` | Generate Google Gemini function declarations |
| `to_langchain_tools` | `() -> list[Tool]` | Convert actions to LangChain tools |
| `to_crewai_tools` | `() -> list[Tool]` | Convert actions to CrewAI tools |
| `serve_mcp` | `(*, transport: str = "stdio", name: str = "toolsconnector", host: str = "127.0.0.1", port: int = 3000) -> None` | Start an MCP server |
| `create_rest_app` | `(*, prefix: str = "/api/v1") -> ASGIApp` | Create a Starlette/ASGI REST app |
| `get_connector_status` | `() -> dict[str, str]` | Last known state per connector: `unknown`, `healthy` or `degraded` |

---

## ToolKitFactory

Creates per-tenant `ToolKit` instances for multi-tenant deployments.

```python
from toolsconnector.serve import ToolKitFactory
```

**Constructor:**

```python
ToolKitFactory(
    connectors: list[type[BaseConnector] | str],
    *,
    include_actions: list[str] | None = None,
    exclude_actions: list[str] | None = None,
    exclude_dangerous: bool = False,
    timeout_budget: float = 25.0,
    action_timeout: float = 15.0,
    max_tenants: int | None = None,
)
```

**Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `for_tenant` | `(tenant_id: str, credentials: dict[str, str]) -> ToolKit` | Create a tenant-scoped ToolKit |
| `active_tenants` | `property` | Tenants with a live ToolKit |
| `close_tenant` / `close_all` | see docstrings | Release cached ToolKits |

---

## BaseConnector

Abstract base class for all connectors. Subclass this to implement a new connector.

```python
from toolsconnector.runtime import BaseConnector
```

**Class attributes (set by subclasses):**

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Machine-readable connector name (e.g., `"gmail"`) |
| `display_name` | `str` | Human-readable display name (e.g., `"Gmail"`) |
| `category` | `ConnectorCategory` | Tool category enum value |
| `description` | `str` | One-paragraph description |
| `protocol` | `ProtocolType` | Communication protocol (REST, GraphQL, etc.) |
| `base_url` | `str | None` | Base URL for API requests |

**Constructor kwargs:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `credentials` | `Any` | `None` | API key, token, or `CredentialSet` |
| `keystore` | `KeyStore` | `None` | Accepted but not used yet |
| `middleware` | `list` | `None` | Accepted but not used yet |
| `tenant_id` | `str` | `None` | Tenant identifier |
| `base_url` | `str` | `None` | Override class-level base URL |
| `timeout` | `float` | `30.0` | Request timeout in seconds |
| `max_retries` | `int` | `3` | Accepted but not used; retries happen in `ToolKit` |

**Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `get_actions` | `classmethod () -> dict[str, ActionMeta]` | Extract all action metadata |
| `get_spec` | `classmethod () -> ConnectorSpec` | Extract the full connector spec |
| `_setup` | `async () -> None` | Lifecycle hook: init client (override) |
| `_teardown` | `async () -> None` | Lifecycle hook: cleanup (override) |
| `_health_check` | `async () -> HealthStatus` | Health probe (override) |

Supports both sync and async context managers (`with`/`async with`).

---

## @action Decorator

Marks a connector method as an externally-callable action.

```python
from toolsconnector.runtime import action
```

**Signature:**

```python
@action(
    description: str,               # Required: human-readable description
    *,
    requires_scope: str | None,     # OAuth scope needed
    dangerous: bool = False,        # Destructive side effects
    access: str | None = None,      # "read"|"write"|"destructive" (auto-"destructive" if dangerous)
    idempotent: bool = False,       # Safe to retry
    pagination: PaginationSpec | None,
    tags: list[str] | None,
    rate_limit_weight: int = 1,
    deprecated: bool = False,
    deprecation_message: str | None = None,
)
```

The decorated method MUST be `async def`. The decorator automatically:
- Parses type hints to build JSON Schema for inputs.
- Parses the Google-style docstring: the `Args:` block becomes the parameter
  descriptions, and the prose above it (summary + body) becomes the action's
  `long_description`, published to LLM callers after the `description` title
  (length-capped; a summary that just repeats the title is dropped).
- Creates a sync wrapper (original becomes `alist_*`, sync becomes `list_*`).
- Attaches `ActionMeta` as `__action_meta__`.

---

## PaginatedList[T]

Generic paginated response container.

```python
from toolsconnector.types import PaginatedList
```

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `items` | `list[Any]` | Items in the current page |
| `page_state` | `PageState` | Pagination cursor/offset state |
| `total_count` | `int | None` | Server-reported total, if known |

**Properties and methods:**

| Member | Signature | Description |
|--------|-----------|-------------|
| `has_more` | `@property -> bool` | Whether more pages exist |
| `anext_page` | `async () -> PaginatedList | None` | Fetch the next page (async). `None` only when `has_more` is false |
| `next_page` | `() -> PaginatedList | None` | Fetch the next page (sync) |
| `collect` | `async (max_items: int = 1000, max_pages: int = 10000) -> list` | Collect all pages (async) |
| `collect_sync` | `(max_items: int = 1000, max_pages: int = 10000) -> list` | Collect all pages (sync) |
| `__iter__` | `-> Iterator` | Iterate over current page items |
| `__len__` | `-> int` | Number of items in current page |

If `has_more` is true but the page has no fetcher, the four page methods raise `PaginationNotWiredError`.

---

## Error Hierarchy

All errors inherit from `ToolsConnectorError` and carry structured metadata.

```python
from toolsconnector.errors import ToolsConnectorError
```

```
ToolsConnectorError
    AuthError
        TokenExpiredError
        InvalidCredentialsError
        InsufficientScopeError
        RefreshFailedError
    APIError
        RateLimitError
        NotFoundError
        ValidationError
        ConflictError
        PermissionDeniedError
        ServerError
    TransportError
        TimeoutError
        ConnectionError
        DNSError
    ConnectorError
        ConnectorNotConfiguredError
        ConnectorInitError
        ActionNotFoundError
        PaginationNotWiredError
    ConfigError
        InvalidConfigError
        MissingConfigError
```

**ToolsConnectorError attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `message` | `str` | Human-readable error description |
| `connector` | `str` | Connector name (e.g., `"slack"`) |
| `action` | `str | None` | Action name, if applicable |
| `code` | `str` | Machine-readable error code |
| `retry_eligible` | `bool` | Whether the caller may retry |
| `retry_after_seconds` | `float | None` | Suggested wait before retry |
| `suggestion` | `str | None` | Actionable hint |
| `details` | `dict` | Extra context (JSON-serializable) |
| `upstream_status` | `int | None` | HTTP status from upstream API |

**Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `to_dict` | `() -> dict` | JSON-serializable dict |
| `to_json` | `() -> str` | Compact JSON string |

---

## KeyStore Protocol

Pluggable credential storage interface. Any class with these four async methods satisfies the protocol.

```python
from toolsconnector.keystore.base import KeyStore
```

| Method | Signature | Description |
|--------|-----------|-------------|
| `get` | `async (key: str) -> str | None` | Retrieve a credential |
| `set` | `async (key: str, value: str, ttl: int | None = None) -> None` | Store a credential |
| `delete` | `async (key: str) -> None` | Remove a credential |
| `exists` | `async (key: str) -> bool` | Check if a key exists |

**Key naming convention:** `{connector}:{tenant_id}:{credential_type}`

**Built-in implementations:**

| Class | Module | Description |
|-------|--------|-------------|
| `InMemoryKeyStore` | `toolsconnector.keystore.memory` | Dict-backed, with optional TTL |
| `EnvironmentKeyStore` | `toolsconnector.keystore.env` | Read-only, maps to `TC_*` env vars |
| `LocalFileKeyStore` | `toolsconnector.keystore.local` | Encrypted file; needs the `local-keystore` extra |

---

## ConnectorSpec

The language-agnostic connector contract. Auto-extracted from connector classes via `get_spec()`.

```python
from toolsconnector.spec.connector import ConnectorSpec
```

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Machine-readable name |
| `display_name` | `str` | Human-readable name |
| `category` | `ConnectorCategory` | Tool category |
| `description` | `str` | Connector description |
| `version` | `str` | Implementation version |
| `protocol` | `ProtocolType` | Communication protocol |
| `base_url` | `str | None` | Base API URL |
| `auth` | `AuthSpec` | Supported auth methods |
| `rate_limits` | `RateLimitSpec` | Rate limit config |
| `actions` | `dict[str, ActionSpec]` | Available actions |

---

## ActionSpec

Specification for a single connector action.

```python
from toolsconnector.spec.action import ActionSpec
```

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Method name (e.g., `"list_emails"`) |
| `description` | `str` | Human-readable description |
| `parameters` | `list[ParameterSpec]` | Input parameters |
| `input_schema` | `dict` | JSON Schema for input |
| `output_schema` | `dict` | JSON Schema for output |
| `return_type` | `str` | Python return type as string |
| `dangerous` | `bool` | Has destructive side effects |
| `access` | `str \| null` | Read/write classification: `read` \| `write` \| `destructive`, or `null` if unclassified (read-only consumers fail closed on `null`) |
| `idempotent` | `bool` | Safe to retry |
| `idempotent` | `bool` | Safe to retry |
| `deprecated` | `bool` | Whether deprecated |

---

## CLI Commands

```bash
tc list                                    # List all available connectors
tc <connector> actions                     # List actions for a connector
tc <connector> <action> [--params]         # Execute an action
tc <connector> spec --format json          # Export connector spec as JSON
tc serve mcp <connectors> [--transport]    # Start MCP server
```
