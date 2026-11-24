"""Release gate for the supported-Python range.

Decision D00000G raised the floor from 3.9 to 3.10: 3.9 reached EOL in
October 2025, and every ``mcp`` release requires 3.10+, so on 3.9 the
``[mcp]`` extra could not resolve and the MCP serving path was never
exercised there.

The floor is declared in several places that drift independently —
``requires-python``, the trove classifiers, the CI test matrix, mypy's
target, and environment-marked dependencies. The first test pins the
decision itself; the rest keep every other declaration consistent with
``requires-python`` so a future floor change only has to edit that
one assertion.
"""

from __future__ import annotations

import re
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

from packaging.markers import Marker
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import Version

_ROOT = Path(__file__).resolve().parents[2]
_CLASSIFIER = re.compile(r"^Programming Language :: Python :: (3\.\d+)$")


def _project() -> dict:
    with (_ROOT / "pyproject.toml").open("rb") as fh:
        return tomllib.load(fh)


def _floor(project: dict) -> Version:
    spec = SpecifierSet(project["project"]["requires-python"])
    lower = [Version(s.version) for s in spec if s.operator == ">="]
    assert len(lower) == 1, f"expected one '>=' bound in requires-python, got {spec}"
    return lower[0]


def _classifier_versions(project: dict) -> set[str]:
    return {m.group(1) for c in project["project"]["classifiers"] if (m := _CLASSIFIER.match(c))}


def _ci_matrix_versions() -> set[str]:
    """Every Python version the CI test matrix can run.

    The matrix is a ``fromJSON(...)`` expression (PRs get a subset), so
    collect every quoted version on the ``python-version:`` line that
    defines ``matrix.python-version``.
    """
    ci = (_ROOT / ".github" / "workflows" / "ci.yml").read_text()
    lines = [
        ln
        for ln in ci.splitlines()
        if ln.strip().startswith("python-version:") and "fromJSON" in ln
    ]
    assert len(lines) == 1, f"expected one matrix python-version line, got {lines!r}"
    return set(re.findall(r"""["'](3\.\d+)["']""", lines[0]))


def test_requires_python_is_310_plus() -> None:
    """D00000G: Python 3.9 is no longer supported."""
    spec = SpecifierSet(_project()["project"]["requires-python"])
    assert not spec.contains("3.9.18"), (
        f"requires-python={spec} still admits Python 3.9, which D00000G dropped"
    )
    assert spec.contains("3.10.0"), f"requires-python={spec} rejects Python 3.10"


def test_classifiers_match_requires_python() -> None:
    project = _project()
    floor = _floor(project)
    versions = _classifier_versions(project)
    below = sorted(v for v in versions if Version(v) < floor)
    assert not below, f"classifiers advertise Python {below}, below requires-python's floor {floor}"
    assert f"{floor.major}.{floor.minor}" in versions, (
        f"no classifier for the floor version {floor}"
    )


def test_ci_matrix_matches_classifiers() -> None:
    """CI must test exactly the versions the package claims to support."""
    classifiers = _classifier_versions(_project())
    matrix = _ci_matrix_versions()
    assert matrix == classifiers, (
        f"CI matrix {sorted(matrix)} != classifiers {sorted(classifiers)}. "
        "Either CI tests a version we don't claim, or we claim one CI never runs."
    )


def test_mypy_targets_the_floor() -> None:
    project = _project()
    floor = _floor(project)
    target = str(project["tool"]["mypy"]["python_version"])
    assert Version(target) == floor, (
        f"[tool.mypy] python_version={target!r} but requires-python's floor is {floor}"
    )


def test_no_dependency_is_dead_on_every_supported_python() -> None:
    """A marker that is false on every supported version is a leftover shim.

    ``eval_type_backport; python_version < '3.10'`` is the case this was
    written for: once the floor is 3.10 pip can never install it, and the
    line only misleads readers into thinking 3.9 still matters.
    """
    project = _project()
    supported = sorted(_classifier_versions(project), key=Version)
    extras = project["project"].get("optional-dependencies", {})
    declared = [("dependencies", d) for d in project["project"]["dependencies"]] + [
        (f"optional-dependencies.{name}", d) for name, deps in extras.items() for d in deps
    ]

    dead = []
    for where, dep in declared:
        req = Requirement(dep)
        if req.marker is None or "python_version" not in str(req.marker):
            continue
        marker = Marker(str(req.marker))
        if not any(
            marker.evaluate({"python_version": v, "python_full_version": f"{v}.0"})
            for v in supported
        ):
            dead.append(f"{where}: {dep!r}")

    assert not dead, f"dependencies that never install on any supported Python {supported}: {dead}"
