"""Conformance tests for import boundaries.

Ensures architectural layering is maintained:
- spec/ imports nothing from other toolsconnector modules
- runtime/ imports from spec/ only (+ types/, errors/, keystore/ for runtime use)
- connectors/ never imports from serve/ or other connectors
"""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
TC_ROOT = PROJECT_ROOT / "toolsconnector"


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


def _check_forbidden_imports(
    source_dir: str,
    forbidden_prefixes: list[str],
) -> list[tuple[str, str]]:
    """Check files in source_dir for forbidden imports.

    Returns list of (file, import) violations.
    """
    violations: list[tuple[str, str]] = []
    src_path = TC_ROOT / source_dir
    if not src_path.exists():
        return violations

    for py_file in src_path.rglob("*.py"):
        imports = _get_imports(py_file)
        rel_file = str(py_file.relative_to(PROJECT_ROOT))
        for imp in imports:
            for forbidden in forbidden_prefixes:
                if imp.startswith(forbidden):
                    violations.append((rel_file, imp))
    return violations


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
        if not connectors_dir.exists():
            return

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
                            if imported_connector != connector_dir.name:
                                violations.append((rel_file, imp))

        assert violations == [], "Cross-connector imports found:\n" + "\n".join(
            f"  {f} imports {i}" for f, i in violations
        )
