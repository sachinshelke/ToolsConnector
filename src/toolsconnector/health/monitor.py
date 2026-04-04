"""Connector health monitor for CI/CD integration.

Provides functions for automated health monitoring:
- Detect which connectors have changed.
- Compare specs between versions.
- Generate health reports in various formats.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class SpecDiff:
    """Difference between two connector specs."""

    connector_name: str
    change_type: str  # "added" | "removed" | "modified" | "unchanged"
    added_actions: list[str] = field(default_factory=list)
    removed_actions: list[str] = field(default_factory=list)
    modified_actions: list[str] = field(default_factory=list)
    details: str = ""


def compare_specs(old_spec: dict[str, Any], new_spec: dict[str, Any]) -> SpecDiff:
    """Compare two connector specs and identify changes.

    Args:
        old_spec: Previous spec as dict.
        new_spec: Current spec as dict.

    Returns:
        SpecDiff describing what changed.
    """
    name = new_spec.get("name", old_spec.get("name", "unknown"))
    old_actions = set(old_spec.get("actions", {}).keys())
    new_actions = set(new_spec.get("actions", {}).keys())

    added = sorted(new_actions - old_actions)
    removed = sorted(old_actions - new_actions)

    # Check for modified actions (same name, different schema)
    modified = []
    for action_name in sorted(old_actions & new_actions):
        old_schema = old_spec["actions"][action_name].get("input_schema", {})
        new_schema = new_spec["actions"][action_name].get("input_schema", {})
        if old_schema != new_schema:
            modified.append(action_name)

    if not added and not removed and not modified:
        return SpecDiff(connector_name=name, change_type="unchanged")

    change_type = "modified"
    if added and not removed:
        change_type = "added"
    elif removed and not added:
        change_type = "removed"

    return SpecDiff(
        connector_name=name,
        change_type=change_type,
        added_actions=added,
        removed_actions=removed,
        modified_actions=modified,
    )


def export_specs(
    connector_names: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Export all connector specs as a JSON-serializable dict.

    Useful for storing baseline specs and comparing across versions.

    Args:
        connector_names: Connectors to export. None = all.

    Returns:
        Dict mapping connector name to spec dict.
    """
    from toolsconnector.serve._discovery import get_connector_class, list_connectors

    names = connector_names or list_connectors()
    specs: dict[str, Any] = {}
    for name in names:
        try:
            cls = get_connector_class(name)
            spec = cls.get_spec()
            specs[name] = json.loads(spec.model_dump_json())
        except Exception:
            continue
    return specs


def generate_health_report_markdown(report: Any) -> str:
    """Generate a Markdown health report.

    Args:
        report: SystemHealthReport instance.

    Returns:
        Markdown-formatted report string.
    """
    lines = [
        "# Connector Health Report",
        "",
        f"**Total:** {report.total} | "
        f"**Healthy:** {report.healthy} | "
        f"**Degraded:** {report.degraded} | "
        f"**Unavailable:** {report.unavailable}",
        "",
        "| Connector | Status | Latency | Actions | Error |",
        "|-----------|--------|---------|---------|-------|",
    ]
    for r in sorted(report.reports, key=lambda x: x.connector_name):
        status = "OK" if r.healthy else "FAIL"
        latency = f"{r.latency_ms}ms" if r.latency_ms else "-"
        error = r.error or "-"
        if len(error) > 50:
            error = error[:47] + "..."
        lines.append(
            f"| {r.connector_name} | {status} | {latency} | "
            f"{r.actions_count} | {error} |"
        )
    return "\n".join(lines)
