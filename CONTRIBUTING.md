# Contributing to ToolsConnector

Thank you for your interest in contributing to ToolsConnector. This guide covers everything you need to add a new connector, fix a bug, or improve the core.

## Quick Start

```bash
# Clone and setup
git clone https://github.com/sachinshelke/ToolsConnector.git
cd toolsconnector
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
PYTHONPATH=src pytest tests/ -v

# Lint
ruff check src/
```

## Adding a New Connector

This is the most common contribution. A connector is a Python package in `src/toolsconnector/connectors/` that wraps a tool's API.

### Step 1: Create the directory

```bash
mkdir -p src/toolsconnector/connectors/mytool
```

### Step 2: Define types (`types.py`)

```python
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

class MyRecord(BaseModel):
    """A record from MyTool."""
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    created_at: Optional[str] = None
```

### Step 3: Build the connector (`connector.py`)

```python
from __future__ import annotations
from typing import Optional, Any
import httpx
from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import ConnectorCategory, ProtocolType, RateLimitSpec
from toolsconnector.types import PaginatedList, PageState
from .types import MyRecord

class MyTool(BaseConnector):
    """Connect to MyTool to manage records."""

    name = "mytool"
    display_name = "MyTool"
    category = ConnectorCategory.CUSTOM
    protocol = ProtocolType.REST
    base_url = "https://api.mytool.com/v1"
    description = "Connect to MyTool to manage records."
    _rate_limit_config = RateLimitSpec(rate=100, period=60, burst=20)

    async def _setup(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=self._base_url or self.base_url,
            headers={"Authorization": f"Bearer {self._credentials}"},
            timeout=self._timeout,
        )

    async def _teardown(self) -> None:
        if hasattr(self, "_client"):
            await self._client.aclose()

    @action("List all records")
    async def list_records(
        self, limit: int = 10, offset: int = 0
    ) -> PaginatedList[MyRecord]:
        """List records from MyTool.

        Args:
            limit: Maximum records to return.
            offset: Number of records to skip.

        Returns:
            Paginated list of records.
        """
        response = await self._client.get(
            "/records", params={"limit": limit, "offset": offset}
        )
        response.raise_for_status()
        data = response.json()
        items = [MyRecord(**r) for r in data.get("records", [])]
        has_more = len(items) == limit
        return PaginatedList(
            items=items,
            page_state=PageState(offset=offset + limit, has_more=has_more),
        )
```

### Step 4: Create `__init__.py`

```python
from .connector import MyTool
from .types import MyRecord

__all__ = ["MyTool", "MyRecord"]
```

### Step 5: Register in discovery

Add your connector to `src/toolsconnector/serve/_discovery.py`:

```python
_KNOWN_CONNECTORS["mytool"] = "toolsconnector.connectors.mytool:MyTool"
```

And to `pyproject.toml`:

```toml
mytool = []  # or ["mytool-sdk>=1.0"] if it needs a dependency
```

### Step 6: Test

```bash
PYTHONPATH=src python -c "
from toolsconnector.connectors.mytool import MyTool
spec = MyTool.get_spec()
print(f'{spec.name}: {len(spec.actions)} actions')
for name, action in spec.actions.items():
    print(f'  {name}: {action.description}')
"
```

## Connector Quality Checklist

Before submitting a PR, verify:

- [ ] All `@action` methods are `async def`
- [ ] All parameters have type hints (no bare `Any`)
- [ ] All parameters have descriptions in Google-style docstrings
- [ ] `connector.py` is under 500 lines
- [ ] Types use `ConfigDict(frozen=True)` for response models
- [ ] Uses `from __future__ import annotations`
- [ ] Uses `Optional[X]` for Pydantic fields (Python 3.9 compat)
- [ ] Dangerous actions marked with `dangerous=True`
- [ ] Rate limits declared via `_rate_limit_config`
- [ ] No credentials hardcoded
- [ ] `get_spec()` works without instantiation
- [ ] Tests pass: `pytest tests/ -v`

## Architecture Rules

- **spec/** imports nothing from other toolsconnector modules
- **connectors/** never imports from `serve/` or other connectors
- **serve/** reads metadata via `get_spec()`, never imports connector internals
- Core dependencies: only pydantic, httpx, docstring-parser

## Code Style

- Python 3.9+ compatible
- Lines under 100 characters
- Google-style docstrings with Args, Returns, Raises
- Ruff for linting: `ruff check src/`

## Pull Request Process

1. Fork the repo and create a branch
2. Make your changes
3. Ensure all tests pass
4. Submit a PR with a clear description
5. Core maintainers will review within 48 hours
