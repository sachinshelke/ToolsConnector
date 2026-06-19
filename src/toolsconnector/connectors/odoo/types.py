"""Typed models for the Odoo connector.

Odoo records are intentionally dynamic: every instance can add models and
fields via custom modules, so individual records are returned as plain
``dict[str, Any]`` (field name -> value) rather than fixed pydantic models.
The one stable, schema-bound payload is the server version handshake, modelled
below. Phase-2 semantic helpers (e.g. typed ``res.partner`` / ``sale.order``
wrappers) can add their own models here.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OdooVersion(BaseModel):
    """Result of the unauthenticated ``common.version`` handshake.

    Attributes:
        server_version: Human-readable version string, e.g. ``"17.0"``.
        server_version_info: Structured version tuple, e.g.
            ``[17, 0, 0, "final", 0, ""]``.
        server_serie: Release series, e.g. ``"17.0"``.
        protocol_version: External-API protocol version integer.
    """

    model_config = ConfigDict(extra="allow", frozen=True)

    server_version: str | None = None
    server_version_info: list[Any] = Field(default_factory=list)
    server_serie: str | None = None
    protocol_version: int | None = None
