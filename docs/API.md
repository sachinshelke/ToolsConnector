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
    connectors: list[str],
    credentials: dict[str, str] | None = None,
    keystore: KeyStore | None = None,
    timeout: float = 30.0,
    max_retries: int = 3,
    dry_run: bool = False,
    circuit_breaker: dict | None = None,
    retry: dict | None = None,
)
```

**Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `execute` | `(action: str, params: dict) -> Any` | Execute an action synchronously |
| `aexecute` | `async (action: str, params: dict) -> Any` | Execute an action asynchronously |
| `list_tools` | `() -> list[ActionSpec]` | List all available actions across connectors |
| `get_spec` | `(connector: str) -> ConnectorSpec` | Get the full spec for a connector |
| `to_openai_tools` | `() -> list[dict]` | Generate OpenAI function-calling schemas |
| `to_anthropic_tools` | `() -> list[dict]` | Generate Anthropic tool-use schemas |
| `to_gemini_tools` | `() -> list[dict]` | Generate Google Gemini function declarations |
| `to_langchain_tools` | `() -> list[Tool]` | Convert actions to LangChain tools |
| `to_crewai_tools` | `() -> list[Tool]` | Convert actions to CrewAI tools |
| `serve_mcp` | `(transport: str = "stdio", port: int = 8080, ...) -> None` | Start an MCP server |
| `create_rest_app` | `(prefix: str = "/api/v1") -> ASGIApp` | Create a Starlette/ASGI REST app |
| `health_check` | `() -> dict[str, HealthStatus]` | Check health of all connectors |

---

## ToolKitFactory

Creates per-tenant `ToolKit` instances for multi-tenant deployments.

```python
from toolsconnector.serve import ToolKitFactory
```

**Constructor:**

```python
ToolKitFactory(
    connectors: list[str],
    keystore: KeyStore | None = None,
)
```

**Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `for_tenant` | `(tenant_id: str, credentials: dict) -> ToolKit` | Create a tenant-scoped ToolKit |

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
| `keystore` | `KeyStore` | `None` | Credential storage backend |
| `middleware` | `list` | `None` | Additional middleware |
| `tenant_id` | `str` | `None` | Tenant identifier |
| `base_url` | `str` | `None` | Override class-level base URL |
| `timeout` | `float` | `30.0` | Request timeout in seconds |
| `max_retries` | `int` | `3` | Max retry attempts |

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
    idempotent: bool = False,       # Safe to retry
    pagination: PaginationSpec | None,
    tags: list[str] | None,
    rate_limit_weight: int = 1,
)
```

The decorated method MUST be `async def`. The decorator automatically:
- Parses type hints to build JSON Schema for inputs.
- Parses Google-style docstring to extract parameter descriptions.
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
| `anext_page` | `async () -> PaginatedList | None` | Fetch the next page (async) |
| `next_page` | `() -> PaginatedList | None` | Fetch the next page (sync) |
| `collect` | `async (max_items: int = 1000) -> list` | Collect all pages (async) |
| `collect_sync` | `(max_items: int = 1000) -> list` | Collect all pages (sync) |
| `__iter__` | `-> Iterator` | Iterate over current page items |
| `__len__` | `-> int` | Number of items in current page |

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
