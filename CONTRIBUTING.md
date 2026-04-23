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

### Step 7: Write per-connector tests (respx pattern)

Connectors that ship without dedicated tests are silently fragile —
the parametrized smoke test in `tests/unit/test_connectors.py` only
verifies that `get_spec()` works, not that any action actually does
the right thing.

The pattern is established in `tests/connectors/test_slack.py`,
`test_github.py`, `test_openai.py`. Copy one of those whose vendor
shape most resembles yours:

| Pattern | Reference test | Vendor shape |
|---|---|---|
| HTTP 200 + body-flag auth (`{"ok": false, "error": "..."}`) | `test_slack.py` | Slack-style |
| HTTP status code auth (200/401/404) | `test_github.py` | most REST APIs |
| Per-request httpx client + JSON body + tool-use parameters | `test_openai.py` | LLM APIs |

Five tests is the floor, ten the ceiling. Cover at minimum:

1. **Happy path on the most-common action** — verify request method,
   URL, auth header, request body, and response parsing.
2. **Error mapping** — vendor's auth/notfound/ratelimit responses
   translate to our typed exceptions (or HTTPStatusError where the
   connector hasn't done that mapping yet).
3. **Pagination** — if the connector exposes paginated listings,
   test that PageState.cursor + has_more wire through correctly on
   a 2-page sequence.
4. **`dangerous=True` flag declarations** — write/delete actions
   carry the flag, read actions don't. Guards against an accidental
   edit dropping it (which would silently expose dangerous actions
   to AI agents under the default `exclude_dangerous=True` ToolKit).

Don't try to test every action. The 1432 framework tests in
`tests/unit/` already cover the runtime; per-connector tests are for
**behavioral correctness on representative actions**.

```python
# tests/connectors/test_mytool.py
import httpx, pytest, pytest_asyncio, respx
from toolsconnector.connectors.mytool import MyTool

@pytest_asyncio.fixture           # NOT @pytest.fixture — strict-mode asyncio
async def mytool() -> MyTool:
    connector = MyTool(credentials="fake-token")
    await connector._setup()
    yield connector
    await connector._teardown()

@pytest.mark.asyncio
async def test_list_records_happy_path(mytool: MyTool) -> None:
    with respx.mock(base_url="https://api.mytool.com/v1") as m:
        route = m.get("/records").mock(return_value=httpx.Response(
            200, json={"records": [{"id": "1", "name": "Alice"}]}
        ))
        result = await mytool.alist_records()  # NOTE the `a` prefix for async
        assert result.items[0].name == "Alice"
        assert route.calls.last.request.headers["authorization"] == "Bearer fake-token"
```

Two key gotchas:

- **`await connector.aname()` not `await connector.name()`.**
  `BaseConnector.__init__` installs sync wrappers as `name(...)` and
  exposes the raw async coroutine as `aname(...)`. Tests should
  `await` the `a*` form.
- **`@pytest_asyncio.fixture` not `@pytest.fixture`.** The project
  runs pytest-asyncio in strict mode (see `pyproject.toml`), so
  async fixtures need the explicit decorator.

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
- [ ] **`tests/connectors/test_<name>.py` exists with 5+ respx tests** (see Step 7 above)
- [ ] All tests pass: `pytest tests/ -v`

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

## Versioning Policy (pre-1.0)

ToolsConnector is **pre-1.0**. Semantic Versioning (SemVer) treats the `0.X.Y`
range as a place where anything can change, which makes the post-1.0 contract
(`MAJOR.MINOR.PATCH` = breaking/feature/fix) not directly applicable. We narrow
that ambiguity with an explicit pre-1.0 rule:

| While `0.x.y` | Bump rule |
|---|---|
| `feat:`, `fix:`, `perf:`, `refactor:` (no breaking change) | **Patch** (`0.3.2 → 0.3.3`) |
| `feat!:` or any `BREAKING CHANGE:` footer | **Minor** (`0.3.3 → 0.4.0`) — minor axis signals breaking change while major stays at 0 |
| Manual decision | **Major** (`0.x → 1.0.0`) — only when the public API is deliberately frozen |

The `0.X` axis (minor) is the pre-1.0 "compatibility-break" axis. Users
should pin exact versions (`toolsconnector==0.3.3`) until 1.0 and read the
CHANGELOG before upgrading across a minor bump. This is enforced in
`.release-please-config.json` via `bump-patch-for-minor-pre-major: true`.

## Commit Messages — Conventional Commits

This repo uses [Conventional Commits](https://www.conventionalcommits.org/) so
[Release Please](https://github.com/googleapis/release-please) can automate
versioning and the `CHANGELOG.md`. Use this prefix in every commit:

| Prefix | Effect on next release (pre-1.0) | Example |
|---|---|---|
| `feat:` | Patch bump (`0.3.2 → 0.3.3`) | `feat(slack): add scheduled message support` |
| `fix:` | Patch bump | `fix(linkedin): correct EMPTY_ACCESS_TOKEN handling` |
| `perf:` | Patch bump | `perf(http): reuse httpx pool across actions` |
| `feat!:` or `BREAKING CHANGE:` in body | **Minor bump** (`0.3.3 → 0.4.0`) — reserved for real API breaks | `feat!: rename ToolKit.execute → ToolKit.run` |
| `refactor:` | No version bump (still in changelog) | `refactor(serve): extract _request helper` |
| `docs:` `ci:` `build:` `test:` `chore:` `style:` | No version bump | `docs: fix typo in linkedin README` |

Post-1.0 the bump table will shift to standard SemVer (`feat:` → minor,
`feat!:` → major). No commit-message syntax changes will be required at
that cutover — only the release-please config flips.

## Release Process (what happens when you merge to `main`)

```
push commits with feat:/fix: messages
   ↓
CI runs (lint + test + conformance + security)
   ↓
Release Please updates an OPEN PR titled "chore(main): release X.Y.Z"
   ↓
Maintainer reviews the proposed CHANGELOG + version, then merges
   ↓
Release Please bumps pyproject.toml + CHANGELOG.md, creates v-tag + GitHub Release
   ↓
publish-pypi.yml fires automatically:
  • check tag/version alignment
  • short-circuit if PyPI already has this version
  • build sdist + wheel
  • twine check
  • SLSA build provenance attestation (Sigstore)
  • OIDC publish to PyPI (no long-lived secret)
  • attach wheel + sdist to the GitHub Release
```

**One conscious decision per release.** The "should we ship this?" gate is
*merging the Release Please PR* — that's where you read the proposed
CHANGELOG before clicking. Everything downstream is automated. Doc-only or
site-only changes never trigger a PyPI release; they only refresh the live
site.

The workflow runs inside the `pypi` GitHub Environment. That environment
exists purely as a scoping boundary for PyPI Trusted Publishing (the
OIDC handshake requires the token to assert `environment: pypi`). It has
no required reviewers, so the job runs end-to-end with no human pause.

If you ever want a second human-approval gate (e.g. when adding a
co-maintainer), add required reviewers to the environment in
Settings → Environments → pypi. The workflow needs no changes.

### Dependency updates (also hands-free)

Dependabot opens PRs for dependency updates on a weekly schedule
(`.github/dependabot.yml`). Patch and minor version bumps **auto-merge**
once CI passes (`.github/workflows/dependabot-auto-merge.yml`). Major
version bumps (e.g. `pydantic 2.x → 3.x`) get an automated comment and
wait for maintainer review — they may carry breaking changes.

## Pull Request Process

1. Fork the repo and create a branch
2. Make your changes
3. Use Conventional Commit messages (see above) so Release Please can pick them up
4. Ensure all tests pass locally: `pytest tests/ -v && ruff check src/ && ruff format --check src/`
5. Submit a PR with a clear description
6. Core maintainers will review within 48 hours
