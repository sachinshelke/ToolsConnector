"""Authenticate a connector via its declared OAuth scopes.

Bridges a connector's declared OAuth2 scopes -- the single source of truth in
its spec -- to the acquisition flow, so callers authenticate *by connector*
without re-listing scopes::

    import asyncio
    from toolsconnector.connectors.gmail import Gmail
    from toolsconnector.runtime.auth import login_for

    creds = asyncio.run(login_for(Gmail, client_id="...apps.googleusercontent.com"))

For the web flow, pair :func:`begin_for` with
:func:`~toolsconnector.runtime.auth.flows.complete`. Works for any connector that
declares an OAUTH2 provider; the 6 Google Tier A connectors all do. Endpoints
come from *preset* (Google by default).

This lives on the connector-facing side of the auth runtime: it imports the
abstract :class:`BaseConnector` (same layer) and takes a connector *class*, so it
never imports a concrete connector and creates no layering cycle.
"""

from __future__ import annotations

from typing import Optional

from toolsconnector.runtime.base import BaseConnector
from toolsconnector.spec.auth import AuthType
from toolsconnector.types.credentials import CredentialSet

from .flows import GOOGLE, OAuthFlowError, PendingAuth, ProviderPreset, begin
from .loopback import login


def oauth_scopes(connector: type[BaseConnector]) -> list[str]:
    """Return *connector*'s declared OAuth2 scopes (its single source of truth).

    Raises:
        OAuthFlowError: If the connector declares no OAuth2 provider/scopes.
    """
    for provider in connector.get_spec().auth.supported:
        if provider.type == AuthType.OAUTH2:
            scopes = provider.extra.get("scopes")
            if scopes:
                return list(scopes)
    raise OAuthFlowError(f"{connector.__name__} declares no OAuth2 scopes to request.")


def scopes_for(*connectors: type[BaseConnector]) -> list[str]:
    """Union of declared scopes across *connectors*, de-duplicated, order-preserving.

    Use to authorize several connectors in one consent, e.g.
    ``scopes_for(Gmail, GoogleDrive)``.
    """
    merged: list[str] = []
    for connector in connectors:
        for scope in oauth_scopes(connector):
            if scope not in merged:
                merged.append(scope)
    return merged


def _incremental_params(incremental: bool) -> Optional[dict[str, str]]:
    # Google incremental authorization: return a token covering previously
    # granted scopes plus the newly requested ones.
    return {"include_granted_scopes": "true"} if incremental else None


def begin_for(
    connector: type[BaseConnector],
    *,
    client_id: str,
    redirect_uri: str,
    scopes: Optional[list[str]] = None,
    preset: ProviderPreset = GOOGLE,
    state: Optional[str] = None,
    incremental: bool = False,
) -> PendingAuth:
    """:func:`begin` for a connector (web flow).

    Args:
        scopes: Override the requested scopes (subset, or a custom/combined set
            e.g. from :func:`scopes_for`). Defaults to the connector's full
            declared set.
        incremental: Request Google incremental auth so a later consent adds to
            the previously granted scopes instead of replacing them.
    """
    return begin(
        preset,
        client_id=client_id,
        redirect_uri=redirect_uri,
        scopes=scopes if scopes is not None else oauth_scopes(connector),
        state=state,
        extra_params=_incremental_params(incremental),
    )


async def login_for(
    connector: type[BaseConnector],
    *,
    client_id: str,
    scopes: Optional[list[str]] = None,
    client_secret: Optional[str] = None,
    preset: ProviderPreset = GOOGLE,
    incremental: bool = False,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
    state: Optional[str] = None,
    timeout: float = 180.0,
) -> CredentialSet:
    """:func:`login` (desktop loopback) for a connector.

    Args:
        scopes: Override the requested scopes (subset or custom/combined set).
            Defaults to the connector's full declared set.
        incremental: Request Google incremental auth (add to prior grant).
    """
    return await login(
        preset,
        client_id=client_id,
        scopes=scopes if scopes is not None else oauth_scopes(connector),
        client_secret=client_secret,
        host=host,
        port=port,
        open_browser=open_browser,
        state=state,
        extra_params=_incremental_params(incremental),
        timeout=timeout,
    )
