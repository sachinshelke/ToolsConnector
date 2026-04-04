"""Extract connector specs as standalone JSON/YAML files.

This is the foundation for multi-language SDK support. Specs extracted
here can be consumed by TypeScript, Go, Java code generators.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional


def extract_spec(connector_name: str) -> dict[str, Any]:
    """Extract a single connector's spec as a dict.

    Args:
        connector_name: Name of the connector (e.g., "gmail").

    Returns:
        Complete spec as a JSON-serializable dict.
    """
    from toolsconnector.serve._discovery import get_connector_class

    cls = get_connector_class(connector_name)
    spec = cls.get_spec()
    return json.loads(spec.model_dump_json())


def extract_all_specs(
    connector_names: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Extract specs for all connectors.

    Args:
        connector_names: Subset to extract. None = all.

    Returns:
        Dict mapping connector name to spec dict.
    """
    from toolsconnector.serve._discovery import list_connectors

    names = connector_names or list_connectors()
    specs: dict[str, Any] = {}
    for name in names:
        try:
            specs[name] = extract_spec(name)
        except Exception as e:
            specs[name] = {"error": str(e)}
    return specs


def export_to_json(
    output_dir: str,
    connector_names: Optional[list[str]] = None,
) -> list[str]:
    """Export connector specs as individual JSON files.

    Args:
        output_dir: Directory to write JSON files.
        connector_names: Subset to export. None = all.

    Returns:
        List of written file paths.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    specs = extract_all_specs(connector_names)
    written: list[str] = []
    for name, spec in specs.items():
        path = out / f"{name}.connector.json"
        path.write_text(json.dumps(spec, indent=2, default=str))
        written.append(str(path))
    return written


def export_to_yaml(
    output_dir: str,
    connector_names: Optional[list[str]] = None,
) -> list[str]:
    """Export connector specs as individual YAML files.

    Requires pyyaml.

    Args:
        output_dir: Directory to write YAML files.
        connector_names: Subset to export. None = all.

    Returns:
        List of written file paths.

    Raises:
        ImportError: If pyyaml is not installed.
    """
    try:
        import yaml
    except ImportError:
        raise ImportError(
            "YAML export requires pyyaml. Install with: pip install pyyaml"
        )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    specs = extract_all_specs(connector_names)
    written: list[str] = []
    for name, spec in specs.items():
        path = out / f"{name}.connector.yaml"
        path.write_text(
            yaml.dump(spec, default_flow_style=False, sort_keys=False)
        )
        written.append(str(path))
    return written


def generate_openapi(
    connector_names: Optional[list[str]] = None,
    title: str = "ToolsConnector API",
    version: str = "0.1.0",
) -> dict[str, Any]:
    """Generate an OpenAPI 3.0 spec from connector specs.

    This allows non-Python applications to discover and call
    connector actions via the REST API.

    Args:
        connector_names: Connectors to include.
        title: API title.
        version: API version.

    Returns:
        OpenAPI 3.0 spec as dict.
    """
    specs = extract_all_specs(connector_names)

    paths: dict[str, Any] = {}
    for conn_name, spec in specs.items():
        if "error" in spec:
            continue
        for action_name, action in spec.get("actions", {}).items():
            path = f"/api/v1/{conn_name}/{action_name}"
            paths[path] = {
                "post": {
                    "summary": action.get("description", ""),
                    "operationId": f"{conn_name}_{action_name}",
                    "tags": [spec.get("display_name", conn_name)],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": action.get("input_schema", {})
                            }
                        }
                    },
                    "responses": {
                        "200": {"description": "Successful response"},
                        "400": {"description": "Validation error"},
                        "500": {"description": "Connector error"},
                    },
                }
            }

    return {
        "openapi": "3.0.0",
        "info": {"title": title, "version": version},
        "paths": paths,
    }
