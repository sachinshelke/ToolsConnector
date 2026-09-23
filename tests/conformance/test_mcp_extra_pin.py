"""Release gate for the ``[mcp]`` extra's version specifier.

This exists because ``mcp = ["mcp>=1.0"]`` broke every fresh install:
PyPI's current ``mcp`` is 2.x, where ``mcp.server.fastmcp`` is a tombstone
that raises ModuleNotFoundError (FastMCP was renamed to
``mcp.server.mcpserver.MCPServer``). ``serve/mcp.py`` still imports
FastMCP, so an unpinned resolve produced::

    $ pip install "toolsconnector[mcp]"
    $ tc serve mcp gmail
    Error: MCP server requires the 'mcp' package. Install with: pip install "toolsconnector[mcp]"

...telling the user to run the command they had just run.

The floor matters too. ``FastMCP.tool()`` gained ``annotations=`` in 1.7.0
and ``structured_output=`` in 1.10.0 (verified by inspecting the published
wheels). Without a floor, a resolver is free to pick 1.2.0 and silently
strip the ability to emit tool annotations or suppress the auto-generated
outputSchema. ``>=1.10`` is the minimum that makes both reachable.

These assertions are on the *specifier*, not on whatever happens to be
installed, so they run without ``mcp`` present.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - pre-3.11 interpreters (tomli ships with pytest there)
    tomllib = pytest.importorskip(
        "tomli",
        reason="needs tomllib (3.11+) or tomli to parse pyproject.toml",
    )

from packaging.specifiers import SpecifierSet
from packaging.version import Version

_ROOT = Path(__file__).resolve().parents[2]

# mcp 2.x removed ``mcp.server.fastmcp``. Any of these must be rejected.
_FORBIDDEN = ("2.0.0", "2.2.0", "3.0.0")
# Below 1.10.0 loses ``structured_output=``; 1.10.0+ has both kwargs.
_TOO_OLD = ("1.0.0", "1.2.0", "1.5.0", "1.9.4")
_REQUIRED = ("1.10.0", "1.30.0")


def _load(path: Path) -> dict:
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _split_marker(requirement: str) -> tuple[str, str]:
    """Split ``"mcp>=1.10,<2; python_version>='3.10'"`` into
    ``("mcp>=1.10,<2", "python_version>='3.10'")``."""
    head, _, marker = requirement.partition(";")
    return head.strip(), marker.strip()


def _specifier_of(requirement: str) -> SpecifierSet:
    head, _ = _split_marker(requirement)
    assert head.startswith("mcp"), f"not an mcp requirement: {requirement!r}"
    return SpecifierSet(head[len("mcp") :].strip())


def _mcp_requirements() -> list[tuple[str, str]]:
    """Every place the ``mcp`` dependency is declared, as (label, requirement)."""
    root = _load(_ROOT / "pyproject.toml")
    extras = root["project"]["optional-dependencies"]["mcp"]
    assert len(extras) == 1, f"expected one mcp requirement, got {extras!r}"

    sub = _load(_ROOT / "toolsconnector-mcp" / "pyproject.toml")
    sub_mcp = [
        d for d in sub["project"]["dependencies"] if d.split(";")[0].strip().startswith("mcp")
    ]
    assert len(sub_mcp) == 1, f"expected one mcp dep, got {sub_mcp!r}"

    return [
        ("pyproject.toml [mcp] extra", extras[0]),
        ("toolsconnector-mcp/pyproject.toml dependencies", sub_mcp[0]),
    ]


@pytest.mark.parametrize("label,requirement", _mcp_requirements())
def test_mcp_specifier_excludes_2x(label: str, requirement: str) -> None:
    spec = _specifier_of(requirement)
    for bad in _FORBIDDEN:
        assert not spec.contains(Version(bad)), (
            f"{label}: {requirement!r} admits mcp {bad}, but mcp 2.x removed "
            "'mcp.server.fastmcp' (FastMCP -> mcp.server.mcpserver.MCPServer). "
            "serve/mcp.py imports FastMCP, so this breaks every fresh install. "
            "Pin a '<2' ceiling."
        )


@pytest.mark.parametrize("label,requirement", _mcp_requirements())
def test_mcp_specifier_requires_at_least_1_10(label: str, requirement: str) -> None:
    spec = _specifier_of(requirement)
    for old in _TOO_OLD:
        assert not spec.contains(Version(old)), (
            f"{label}: {requirement!r} admits mcp {old}, which predates "
            "FastMCP.tool(structured_output=...) (added 1.10.0). Without a "
            "'>=1.10' floor a resolver may silently strip the ability to emit "
            "tool annotations and suppress the generated outputSchema."
        )
    for ok in _REQUIRED:
        assert spec.contains(Version(ok)), (
            f"{label}: {requirement!r} rejects mcp {ok}, which is inside the "
            "supported >=1.10,<2 range."
        )


def test_subpackage_floor_matches_mcp_requirement() -> None:
    """``toolsconnector-mcp`` is nothing but an MCP server, so it must not
    claim to support a Python that ``mcp`` itself refuses to install on."""
    sub = _load(_ROOT / "toolsconnector-mcp" / "pyproject.toml")
    requires_python = sub["project"]["requires-python"]
    assert SpecifierSet(requires_python).contains(Version("3.10"))
    assert not SpecifierSet(requires_python).contains(Version("3.9")), (
        f"toolsconnector-mcp declares requires-python={requires_python!r}, but "
        "its mandatory 'mcp' dependency requires Python >=3.10. Raise the floor."
    )
