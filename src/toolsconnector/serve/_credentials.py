"""Credential resolution with actionable error messages."""

from __future__ import annotations

import os
from typing import Optional

from toolsconnector.errors import MissingConfigError


def resolve_credentials(
    connector_name: str,
    overrides: Optional[dict[str, str]] = None,
) -> Optional[str]:
    """Resolve credentials for a connector.

    Priority:
        1. Programmatic dict (``overrides``)
        2. ``TC_{NAME}_CREDENTIALS`` env var
        3. ``TC_{NAME}_API_KEY`` env var
        4. ``TC_{NAME}_TOKEN`` env var
        5. ``None`` (no credentials found)

    Args:
        connector_name: Connector name (e.g., ``"gmail"``).
        overrides: Dict of connector_name to credential string.

    Returns:
        Credential string, or ``None`` if not found.
    """
    # 1. Programmatic override
    if overrides and connector_name in overrides:
        return overrides[connector_name]

    # 2-4. Environment variables
    upper = connector_name.upper()
    for suffix in ("CREDENTIALS", "API_KEY", "TOKEN"):
        env_key = f"TC_{upper}_{suffix}"
        value = os.environ.get(env_key)
        if value:
            return value

    return None


def require_credentials(
    connector_name: str,
    overrides: Optional[dict[str, str]] = None,
) -> str:
    """Like ``resolve_credentials`` but raises if not found.

    Args:
        connector_name: Connector name (e.g., ``"gmail"``).
        overrides: Dict of connector_name to credential string.

    Returns:
        Credential string (guaranteed non-``None``).

    Raises:
        MissingConfigError: With actionable suggestion listing all
            supported credential sources.
    """
    cred = resolve_credentials(connector_name, overrides)
    if cred is None:
        upper = connector_name.upper()
        raise MissingConfigError(
            f"No credentials found for '{connector_name}' connector.",
            connector=connector_name,
            suggestion=(
                f"Provide credentials in one of these ways:\n"
                f"  1. ToolKit(credentials={{'{connector_name}': 'your-token'}})\n"
                f"  2. export TC_{upper}_CREDENTIALS=your-token\n"
                f"  3. export TC_{upper}_API_KEY=your-key\n"
                f"  4. export TC_{upper}_TOKEN=your-token"
            ),
        )
    return cred
