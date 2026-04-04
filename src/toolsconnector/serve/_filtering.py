"""Tool filtering and ToolEntry construction."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from typing import Any, Optional

from toolsconnector.spec.connector import ConnectorSpec
from toolsconnector.spec.action import ActionSpec


@dataclass(frozen=True)
class ToolEntry:
    """A single tool available in the ToolKit.

    Combines connector + action info into one flat structure
    used by schema generators, MCP server, and CLI.

    Attributes:
        connector_name: Machine-readable connector name.
        connector_display_name: Human-readable connector name.
        action_name: Method name on the connector class.
        tool_name: Namespaced tool name (``"{connector}_{action}"``).
        description: LLM-optimized description with connector context.
        input_schema: JSON Schema for the action input.
        output_schema: JSON Schema for the action output.
        dangerous: Whether this action has destructive side effects.
        idempotent: Whether this action is safe to retry.
        requires_scope: OAuth scope required, if any.
        tags: Categorization tags.
        rate_limit_weight: How many rate limit tokens this action costs.
    """

    connector_name: str
    connector_display_name: str
    action_name: str
    tool_name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    dangerous: bool = False
    idempotent: bool = False
    requires_scope: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    rate_limit_weight: int = 1

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for API responses."""
        return {
            "connector": self.connector_name,
            "connector_display_name": self.connector_display_name,
            "action": self.action_name,
            "name": self.tool_name,
            "description": self.description,
            "input_schema": self.input_schema,
            "dangerous": self.dangerous,
            "requires_scope": self.requires_scope,
        }


def _build_description(spec: ConnectorSpec, action: ActionSpec) -> str:
    """Build LLM-optimized description with connector context.

    Args:
        spec: The parent connector specification.
        action: The action specification.

    Returns:
        A description string enriched with scope and safety warnings.
    """
    parts = [f"{spec.display_name}: {action.description}"]
    if action.requires_scope:
        parts.append(f"Requires {action.requires_scope} permission.")
    if action.dangerous:
        parts.append("WARNING: This action has destructive side effects.")
    return " ".join(parts)


def build_tool_list(
    connector_classes: list[type],
    *,
    include_actions: Optional[list[str]] = None,
    exclude_actions: Optional[list[str]] = None,
    exclude_dangerous: bool = False,
) -> list[ToolEntry]:
    """Build filtered list of ToolEntry from connector classes.

    Args:
        connector_classes: List of ``BaseConnector`` subclasses.
        include_actions: Glob patterns -- only matching actions included.
            E.g., ``["list_*", "get_*"]`` for read-only actions.
        exclude_actions: Glob patterns -- matching actions excluded.
            E.g., ``["delete_*", "purge_*"]`` to block destructive ops.
        exclude_dangerous: If ``True``, exclude actions marked dangerous.

    Returns:
        Filtered list of ToolEntry objects.
    """
    entries: list[ToolEntry] = []

    for cls in connector_classes:
        spec = cls.get_spec()

        for action_name, action_spec in spec.actions.items():
            # Apply filters
            if exclude_dangerous and action_spec.dangerous:
                continue

            if include_actions:
                if not any(fnmatch.fnmatch(action_name, p) for p in include_actions):
                    continue

            if exclude_actions:
                if any(fnmatch.fnmatch(action_name, p) for p in exclude_actions):
                    continue

            tool_name = f"{spec.name}_{action_name}"
            description = _build_description(spec, action_spec)

            entries.append(ToolEntry(
                connector_name=spec.name,
                connector_display_name=spec.display_name,
                action_name=action_name,
                tool_name=tool_name,
                description=description,
                input_schema=action_spec.input_schema,
                output_schema=action_spec.output_schema,
                dangerous=action_spec.dangerous,
                idempotent=action_spec.idempotent,
                requires_scope=action_spec.requires_scope,
                tags=action_spec.tags,
                rate_limit_weight=action_spec.rate_limit_weight,
            ))

    return entries
