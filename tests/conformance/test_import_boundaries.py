"""Conformance tests for import boundaries.

Ensures architectural layering is maintained:
- spec/ imports nothing from other toolsconnector modules
- runtime/ imports from spec/ only (+ types/, errors/, keystore/ for runtime use)
- connectors/ never imports from serve/ or other connectors
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
TC_ROOT = PROJECT_ROOT / "src" / "toolsconnector"

# Shared packages under connectors/ that any connector may import. They are
# not connectors (the serve/_discovery.py registry omits them), and
# CONTRIBUTING.md tells connector authors to import _helpers. Adding a name
# here widens the cross-connector rule, so do it deliberately.
SHARED_CONNECTOR_PACKAGES = frozenset({"_aws", "_helpers"})


def _get_imports(filepath: Path) -> list[str]:
    """Extract all import module names from a Python file."""
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
    except SyntaxError:
        return []

    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def _py_files(directory: Path) -> list[Path]:
    """Return every .py file under directory, failing if there are none.

    A missing or empty directory would let a boundary check pass without
    scanning a single file, so it is an error, not an empty result.
    """
    assert directory.is_dir(), f"{directory} does not exist; is TC_ROOT right?"
    files = list(directory.rglob("*.py"))
    assert files, f"no .py files under {directory}; the check would pass vacuously"
    return files


def _check_forbidden_imports(
    source_dir: str,
    forbidden_prefixes: list[str],
) -> list[tuple[str, str]]:
    """Check files in source_dir for forbidden imports.

    Returns list of (file, import) violations.
    """
    violations: list[tuple[str, str]] = []
    for py_file in _py_files(TC_ROOT / source_dir):
        imports = _get_imports(py_file)
        rel_file = str(py_file.relative_to(PROJECT_ROOT))
        for imp in imports:
            for forbidden in forbidden_prefixes:
                if imp.startswith(forbidden):
                    violations.append((rel_file, imp))
    return violations


class TestScannerCoverage:
    """The boundary checks must scan real files, or they pass vacuously."""

    @pytest.mark.parametrize("source_dir", ["spec", "connectors"])
    def test_scanner_finds_python_files(self, source_dir: str) -> None:
        assert len(_py_files(TC_ROOT / source_dir)) > 0


class TestSpecImportBoundary:
    """spec/ must not import from any other toolsconnector module."""

    def test_spec_imports_nothing_from_toolsconnector(self):
        violations = _check_forbidden_imports(
            "spec",
            [
                "toolsconnector.runtime",
                "toolsconnector.types",
                "toolsconnector.errors",
                "toolsconnector.keystore",
                "toolsconnector.connectors",
                "toolsconnector.serve",
                "toolsconnector.codegen",
                "toolsconnector.health",
            ],
        )
        assert violations == [], "spec/ has forbidden imports:\n" + "\n".join(
            f"  {f} imports {i}" for f, i in violations
        )


class TestConnectorImportBoundary:
    """connectors/ must not import from serve/ or other connectors."""

    def test_connectors_dont_import_serve(self):
        violations = _check_forbidden_imports(
            "connectors",
            ["toolsconnector.serve"],
        )
        assert violations == [], "connectors/ imports serve/:\n" + "\n".join(
            f"  {f} imports {i}" for f, i in violations
        )

    def test_connectors_dont_cross_import(self):
        """Each connector should only import from its own directory."""
        connectors_dir = TC_ROOT / "connectors"
        assert connectors_dir.is_dir(), f"{connectors_dir} does not exist; is TC_ROOT right?"

        violations: list[tuple[str, str]] = []
        for connector_dir in connectors_dir.iterdir():
            if not connector_dir.is_dir() or connector_dir.name.startswith("_"):
                continue
            for py_file in connector_dir.rglob("*.py"):
                imports = _get_imports(py_file)
                rel_file = str(py_file.relative_to(PROJECT_ROOT))
                for imp in imports:
                    if imp.startswith("toolsconnector.connectors."):
                        # Extract the connector name from the import
                        parts = imp.split(".")
                        if len(parts) >= 3:
                            imported_connector = parts[2]
                            if (
                                imported_connector != connector_dir.name
                                and imported_connector not in SHARED_CONNECTOR_PACKAGES
                            ):
                                violations.append((rel_file, imp))

        assert violations == [], "Cross-connector imports found:\n" + "\n".join(
            f"  {f} imports {i}" for f, i in violations
        )
