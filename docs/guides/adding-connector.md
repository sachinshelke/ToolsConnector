# Adding a Connector

Step-by-step guide for implementing a new ToolsConnector connector. Follow this pattern exactly to ensure consistency across all 50+ connectors.

## Directory Structure

Every connector lives under `src/toolsconnector/connectors/{name}/` with three files:

```
src/toolsconnector/connectors/yourservice/
    __init__.py       # Public exports
    types.py          # Pydantic V2 response models
    connector.py      # BaseConnector subclass with @action methods
```

## Step 1: Define Types (`types.py`)

Create Pydantic V2 models for all API response objects. Use `frozen=True` for immutability.

```python
"""Pydantic models for YourService connector types."""
from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class Item(BaseModel):
    """A single item from YourService."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str = ""
    description: Optional[str] = None
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ItemList(BaseModel):
    """Collection of items with pagination metadata."""

    model_config = ConfigDict(frozen=True)

    items: list[Item] = Field(default_factory=list)
    total: int = 0
```

Key rules for types:

- One model per API resource (Item, Project, User, etc.)
- Use `ConfigDict(frozen=True)` on all response models.
- Use `Optional[T] = None` for fields the API may omit.
- Use `Field(default_factory=list)` for mutable defaults.
- Keep models flat. Use embedded models only for genuinely nested structures (e.g., `SlackTopic` inside `Channel`).

## Step 2: Implement the Connector (`connector.py`)

Subclass `BaseConnector`, set metadata, and implement `@action` methods.

```python
"""YourService connector -- manage items via the YourService API."""
from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from toolsconnector.errors import APIError, NotFoundError, RateLimitError
from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import ConnectorCategory, ProtocolType, RateLimitSpec
from toolsconnector.types import PageState, PaginatedList

from .types import Item

logger = logging.getLogger("toolsconnector.yourservice")


class YourService(BaseConnector):
    """Connect to YourService to manage items."""

    name = "yourservice"
    display_name = "YourService"
    category = ConnectorCategory.PRODUCTIVITY
    protocol = ProtocolType.REST
    base_url = "https://api.yourservice.com/v1"
    description = "Connect to YourService to create and manage items."
    _rate_limit_config = RateLimitSpec(rate=60, period=60, burst=10)

    # -- Lifecycle --

    async def _setup(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=self._base_url or self.__class__.base_url,
            headers={
                "Authorization": f"Bearer {self._credentials}",
                "Content-Type": "application/json",
            },
            timeout=self._timeout,
        )

    async def _teardown(self) -> None:
        if hasattr(self, "_client"):
            await self._client.aclose()

    # -- Internal helpers --

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        response = await self._client.request(method, path, params=params, json=json_body)

        if response.status_code == 429:
            retry_after = float(response.headers.get("Retry-After", "30"))
            raise RateLimitError(
                "Rate limited by YourService",
                connector="yourservice",
                action=path,
                retry_after_seconds=retry_after,
            )
        if response.status_code == 404:
            raise NotFoundError(
                f"Resource not found: {path}",
                connector="yourservice",
                action=path,
            )
        if response.status_code >= 400:
            raise APIError(
                f"YourService API error: {response.status_code}",
                connector="yourservice",
                action=path,
                upstream_status=response.status_code,
                details={"body": response.text},
            )
        return response.json()

    # -- Actions --

    @action("List items", idempotent=True)
    async def list_items(
        self,
        limit: int = 20,
        cursor: Optional[str] = None,
    ) -> PaginatedList[Item]:
        """List items from YourService.

        Args:
            limit: Maximum number of items to return.
            cursor: Pagination cursor from a previous response.
        """
        params: dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor

        body = await self._request("GET", "/items", params=params)

        items = [Item(**i) for i in body.get("items", [])]
        next_cursor = body.get("next_cursor")

        return PaginatedList(
            items=items,
            page_state=PageState(
                cursor=next_cursor,
                has_more=next_cursor is not None,
            ),
        )

    @action("Create an item", dangerous=True)
    async def create_item(self, name: str, description: str = "") -> Item:
        """Create a new item.

        Args:
            name: Name of the item.
            description: Optional description.
        """
        body = await self._request("POST", "/items", json_body={
            "name": name,
            "description": description,
        })
        return Item(**body)
```

## The `@action` Decorator

The decorator is the heart of every connector. It does three things automatically:

1. Parses type hints and the Google-style docstring to generate JSON Schema.
2. Creates a sync wrapper so both `connector.list_items()` and `await connector.alist_items()` work.
3. Registers the method for discovery by `ToolKit`.

Key parameters:

| Parameter | Type | Purpose |
|-----------|------|---------|
| `description` | `str` | Human-readable action description (required, positional) |
| `dangerous` | `bool` | Mark destructive actions (send, delete, create) |
| `idempotent` | `bool` | Mark safe-to-retry actions (list, get) |
| `requires_scope` | `str` | OAuth scope needed for this action |
| `tags` | `list[str]` | Categorization tags |
| `rate_limit_weight` | `int` | Rate limit token cost (default 1) |

All `@action` methods MUST be `async def`. The decorator raises `TypeError` if you forget.

## Auth Patterns

Choose the auth pattern that matches the target API.

**Bearer token (most common):**

```python
headers={"Authorization": f"Bearer {self._credentials}"}
```

**API key in header:**

```python
headers={"X-API-Key": self._credentials}
```

**API key in query string:**

```python
params["api_key"] = self._credentials
```

**Basic auth:**

```python
import base64
encoded = base64.b64encode(f"{user}:{password}".encode()).decode()
headers={"Authorization": f"Basic {encoded}"}
```

**OAuth2:** Use `self._credentials` as a `CredentialSet` object containing `access_token` and `refresh_token`. See the Gmail connector for a complete example.

## Pagination Patterns

ToolsConnector supports three pagination strategies. Always return `PaginatedList[T]`.

**Cursor-based (Slack, Notion, Stripe):**

```python
return PaginatedList(
    items=items,
    page_state=PageState(cursor=next_cursor, has_more=bool(next_cursor)),
)
```

**Offset-based (Jira, HubSpot):**

```python
return PaginatedList(
    items=items,
    page_state=PageState(offset=offset + limit, has_more=offset + limit < total),
    total_count=total,
)
```

**Page number (GitLab, some REST APIs):**

```python
return PaginatedList(
    items=items,
    page_state=PageState(page=current_page + 1, has_more=current_page < total_pages),
    total_count=total,
)
```

## Error Handling

Map API errors to the structured error hierarchy. Every error carries metadata for debugging and AI agent routing.

- `RateLimitError` -- HTTP 429, include `retry_after_seconds`
- `NotFoundError` -- HTTP 404
- `ValidationError` -- HTTP 400 / 422, bad input
- `PermissionDeniedError` -- HTTP 403
- `ServerError` -- HTTP 500+
- `APIError` -- catch-all for other API failures

Always set `connector=` and `action=` on raised errors.

## Step 3: Create `__init__.py`

```python
"""YourService connector."""
from .connector import YourService

__all__ = ["YourService"]
```

## Step 4: Register in Discovery

Add the connector's install extra to `pyproject.toml`:

```toml
[project.optional-dependencies]
yourservice = []  # No extra deps needed for raw httpx connectors
```

Register the connector class in the connector registry so `ToolKit(["yourservice"])` can find it.

## Step 5: Write Tests

Create tests under `tests/connectors/yourservice/`:

```
tests/connectors/yourservice/
    __init__.py
    test_connector.py   # Unit tests with mocked HTTP
    test_types.py       # Model serialization tests
```

Test at minimum:

- Each action returns the correct type.
- Pagination state is set correctly.
- Error mapping works for 404, 429, and 500 responses.
- The `get_spec()` class method returns a valid `ConnectorSpec`.

## Common Pitfalls

1. **Forgetting `async def`** -- All `@action` methods must be async. The decorator enforces this.
2. **Missing docstring `Args:` section** -- Parameter descriptions are extracted from docstrings. Without them, the generated JSON Schema has no descriptions.
3. **Mutable default arguments** -- Use `Field(default_factory=list)` in Pydantic models, never `= []`.
4. **Not closing the HTTP client** -- Always implement `_teardown` to call `await self._client.aclose()`.
5. **Hardcoding base URLs** -- Use `self._base_url` so users can override for testing or on-premise deployments.
6. **Swallowing errors** -- Never catch and ignore API errors. Map them to the structured error hierarchy.
