"""Pre-validation of tool arguments against JSON Schema.

Validates arguments before sending to the API, catching common
mistakes early with actionable error messages.
"""

from __future__ import annotations

from typing import Any


def validate_arguments(
    input_schema: dict[str, Any],
    arguments: dict[str, Any],
) -> list[str]:
    """Validate arguments against a JSON Schema.

    Performs lightweight validation without external dependencies.
    Checks: required fields, basic types, enum values.

    Args:
        input_schema: JSON Schema dict for the action input.
        arguments: Arguments dict from the tool call.

    Returns:
        List of validation error strings. Empty = valid.
    """
    errors: list[str] = []
    properties = input_schema.get("properties", {})
    required = input_schema.get("required", [])

    # Check required fields
    for field in required:
        if field not in arguments:
            desc = properties.get(field, {}).get("description", "")
            hint = f" ({desc})" if desc else ""
            errors.append(f"Missing required parameter '{field}'{hint}")

    # Check types for provided fields
    for field, value in arguments.items():
        if field not in properties:
            # Unknown field — warn but don't block
            # (APIs may accept extra fields)
            continue

        expected_type = properties[field].get("type", "")
        if not _check_type(value, expected_type):
            errors.append(
                f"Parameter '{field}' expects {expected_type}, "
                f"got {type(value).__name__}: {repr(value)}"
            )

        # Check enum
        enum_values = properties[field].get("enum")
        if enum_values and value not in enum_values:
            errors.append(f"Parameter '{field}' must be one of {enum_values}, got {repr(value)}")

    return errors


_TYPE_MAP: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list,),
    "object": (dict,),
}


def _check_type(value: Any, expected_type: str) -> bool:
    """Check if a value matches the expected JSON Schema type."""
    if not expected_type or value is None:
        return True  # Nullable or unknown type

    allowed = _TYPE_MAP.get(expected_type)
    if allowed is None:
        return True  # Unknown type, skip check

    return isinstance(value, allowed)
