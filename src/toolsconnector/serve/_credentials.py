"""Credential resolution with actionable error messages."""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from toolsconnector.errors import MissingConfigError


def credential_contract(connector_cls: type) -> Optional[dict[str, Any]]:
    """Return the credential contract a connector declares, if it needs one.

    The contract is the ``extra`` of the first declared auth provider whose
    ``credential_format`` is not ``"none"``: format, fields, separator/order,
    ``obtain_url`` and ``env_var``. Connectors that need no credentials, or
    declare no auth at all, return ``None``.

    Args:
        connector_cls: A ``BaseConnector`` subclass.

    Returns:
        The contract dict, or ``None`` if no credentials are required.
    """
    build = getattr(connector_cls, "_build_auth_spec", None)
    if build is None:
        return None
    for provider in build().supported:
        extra = provider.extra or {}
        if extra.get("credential_format", "none") != "none":
            return extra
    return None


def _format_hint(contract: dict[str, Any]) -> str:
    """Render the credential's expected shape, e.g. ``<sid>:<token>``."""
    names = [f["name"] for f in contract.get("fields", []) if f.get("name")]
    fmt = contract.get("credential_format")
    if fmt == "delimited":
        order = contract.get("order") or names
        return str(contract.get("separator", ":")).join(f"<{n}>" for n in order)
    if fmt == "json":
        return json.dumps({n: "..." for n in names})
    return f"<{names[0]}>" if names else "<token>"


def _is_blank(cred: Any) -> bool:
    return cred is None or (isinstance(cred, str) and not cred.strip())


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
    *,
    contract: Optional[dict[str, Any]] = None,
) -> str:
    """Like ``resolve_credentials`` but raises if not found or blank.

    Args:
        connector_name: Connector name (e.g., ``"gmail"``).
        overrides: Dict of connector_name to credential string.
        contract: The connector's credential contract (see
            :func:`credential_contract`). When given, the error shows the
            real credential shape and where to obtain it.

    Returns:
        Credential string (guaranteed non-blank).

    Raises:
        MissingConfigError: With actionable suggestion listing all
            supported credential sources.
    """
    cred = resolve_credentials(connector_name, overrides)
    if cred is not None and not _is_blank(cred):
        return cred

    upper = connector_name.upper()
    contract = contract or {}
    env_var = contract.get("env_var", f"TC_{upper}_CREDENTIALS")
    value = _format_hint(contract) if contract else "<token>"
    suggestion = (
        f"Provide credentials in one of these ways:\n"
        f"  1. ToolKit(credentials={{'{connector_name}': '{value}'}})\n"
        f"  2. export {env_var}='{value}'\n"
        f"  3. export TC_{upper}_API_KEY or TC_{upper}_TOKEN (same value)\n"
        f'  4. MCP clients: set {env_var} in the server\'s "env" config'
    )
    if contract.get("obtain_url"):
        suggestion += f"\nGet one at: {contract['obtain_url']}"
    raise MissingConfigError(
        f"No credentials found for '{connector_name}' connector.",
        connector=connector_name,
        suggestion=suggestion,
    )
