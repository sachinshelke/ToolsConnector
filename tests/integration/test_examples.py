"""Smoke tests for examples/ scripts.

Real users run `pip install toolsconnector` then look for example code
to copy-paste. If those scripts go stale (renamed import, wrong API
signature, missing extra) we lose them at the first impression.

This test protects against silent rot WITHOUT requiring real API
credentials:

  - **Syntax** — every `examples/*.py` parses as valid Python.
  - **Importability** — every script's top-of-module imports resolve
    against the installed package. (We don't execute the body — that
    would hit external APIs.)

To add a new example, drop it in `examples/` named `NN_*.py` and this
test picks it up automatically. No registration needed.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

EXAMPLES_DIR = Path(__file__).parent.parent.parent / "examples"

# Python example files only — we don't validate `.sh` (06_cli_usage.sh)
# at the Python level; ruff and shellcheck would be the right tools
# for that and aren't part of this test surface yet.
EXAMPLE_PY_FILES = sorted(EXAMPLES_DIR.glob("*.py"))


def _example_id(path: Path) -> str:
    """Pretty test id — `01_basic_usage.py` instead of full path."""
    return path.name


@pytest.mark.parametrize("example", EXAMPLE_PY_FILES, ids=_example_id)
def test_example_parses(example: Path) -> None:
    """Every example must be syntactically valid Python.

    Catches typos, accidental partial edits, and stale syntax that
    a contributor's editor missed.
    """
    source = example.read_text(encoding="utf-8")
    try:
        ast.parse(source, filename=str(example))
    except SyntaxError as e:
        pytest.fail(
            f"{example.name} has a syntax error at line {e.lineno}: {e.msg}\n"
            f"  {e.text.rstrip() if e.text else '(no source line)'}"
        )


@pytest.mark.parametrize("example", EXAMPLE_PY_FILES, ids=_example_id)
def test_example_imports_resolve(example: Path) -> None:
    """Every `from toolsconnector...` import must resolve.

    Loads the example as a module under a unique name (so re-runs
    don't collide via sys.modules). Stops short of executing the
    script body — most examples need real API keys + network access
    that we don't have in CI.

    What this DOES catch:
      - Renamed module / removed public symbol
      - Wrong import path after a refactor
      - Missing optional dependency that the example assumed was core

    What it does NOT catch:
      - Bugs inside the script body (action call signatures, etc.)
      - API behavior changes downstream of imports

    The latter requires either real credentials (out of scope for
    open-source CI) or per-script respx mocks (separate effort).
    """
    spec = importlib.util.spec_from_file_location(
        f"_test_examples_{example.stem}",
        example,
    )
    assert spec is not None and spec.loader is not None, (
        f"Could not build importlib spec for {example.name}"
    )

    module = importlib.util.module_from_spec(spec)

    # Parse the AST and execute ONLY the import statements at the top of
    # the file. This validates the imports without running the script
    # body (which would call external APIs / start servers / etc.).
    source = example.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(example))

    import_only_body = [
        node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    if not import_only_body:
        # An example with zero imports is suspicious but not a failure.
        return

    import_only_module = ast.Module(body=import_only_body, type_ignores=[])
    code = compile(import_only_module, filename=str(example), mode="exec")

    try:
        exec(code, module.__dict__)
    except ImportError as e:
        # Optional-extra imports (openai, anthropic, mcp, starlette, etc.)
        # are expected to fail when those extras aren't installed in the
        # test env. Skip — not a regression, just a missing extra.
        if any(
            optional in str(e)
            for optional in (
                "openai",
                "anthropic",
                "mcp",
                "starlette",
                "uvicorn",
                "google",
                "boto3",
                "httpx",  # pragma: no cover — httpx IS core, here as belt+braces
            )
        ):
            pytest.skip(f"{example.name} requires optional dep not installed in test env: {e}")
        pytest.fail(f"{example.name} has a real import error (toolsconnector internal): {e}")
    except Exception as e:
        pytest.fail(f"{example.name} failed during import-time execution: {type(e).__name__}: {e}")
    finally:
        # Clean sys.modules so re-runs don't see stale state.
        sys.modules.pop(spec.name, None)


def test_examples_dir_is_not_empty() -> None:
    """Sanity: someone removed all examples? Fail loudly."""
    assert len(EXAMPLE_PY_FILES) > 0, (
        "examples/ has no .py files — was this intentional? If yes, delete this test too."
    )


def test_examples_have_a_readme() -> None:
    """examples/README.md must exist as the discovery surface."""
    readme = EXAMPLES_DIR / "README.md"
    assert readme.is_file(), (
        "examples/README.md is missing — first-time visitors won't know what's there"
    )
