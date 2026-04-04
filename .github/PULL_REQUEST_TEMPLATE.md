## Description

Brief description of what this PR does.

## Type of Change

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New connector
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to change)
- [ ] Documentation update
- [ ] Test improvement

## Connector Checklist (if adding a connector)

- [ ] All `@action` methods are `async def`
- [ ] All parameters have type hints (no bare `Any`)
- [ ] Google-style docstrings with Args/Returns
- [ ] `connector.py` under 500 lines
- [ ] Types use `ConfigDict(frozen=True)`
- [ ] Uses `from __future__ import annotations`
- [ ] Uses `Optional[X]` for Pydantic fields (Python 3.9 compat)
- [ ] Dangerous actions marked with `dangerous=True`
- [ ] Rate limits declared
- [ ] No credentials hardcoded
- [ ] `get_spec()` works without instantiation
- [ ] Registered in `serve/_discovery.py`
- [ ] Added to `pyproject.toml` extras

## General Checklist

- [ ] Tests pass: `pytest tests/ -v`
- [ ] Linting passes: `ruff check src/`
- [ ] No new dependencies added to core (only extras)
- [ ] Documentation updated if needed
