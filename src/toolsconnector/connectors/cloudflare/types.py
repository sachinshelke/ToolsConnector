"""Pydantic models for Cloudflare connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class CFZone(BaseModel):
    """A Cloudflare zone (domain)."""

    model_config = ConfigDict(frozen=True)

    id: Optional[str] = None
    name: Optional[str] = None
    status: Optional[str] = None
    paused: bool = False
    type: Optional[str] = None
    development_mode: int = 0
    name_servers: list[str] = Field(default_factory=list)
    original_name_servers: list[str] = Field(default_factory=list)
    modified_on: Optional[str] = None
    created_on: Optional[str] = None
    activated_on: Optional[str] = None
    plan: Optional[dict[str, Any]] = None
    account: Optional[dict[str, Any]] = None


class CFDNSRecord(BaseModel):
    """A Cloudflare DNS record."""

    model_config = ConfigDict(frozen=True)

    id: Optional[str] = None
    zone_id: Optional[str] = None
    zone_name: Optional[str] = None
    name: Optional[str] = None
    type: Optional[str] = None
    content: Optional[str] = None
    proxiable: bool = False
    proxied: bool = False
    ttl: int = 1
    locked: bool = False
    priority: Optional[int] = None
    created_on: Optional[str] = None
    modified_on: Optional[str] = None
    comment: Optional[str] = None
    tags: list[str] = Field(default_factory=list)


class CFAnalytics(BaseModel):
    """Cloudflare zone analytics data."""

    model_config = ConfigDict(frozen=True)

    since: Optional[str] = None
    until: Optional[str] = None
    requests: Optional[dict[str, Any]] = None
    bandwidth: Optional[dict[str, Any]] = None
    threats: Optional[dict[str, Any]] = None
    pageviews: Optional[dict[str, Any]] = None
    uniques: Optional[dict[str, Any]] = None


class CFPurgeResult(BaseModel):
    """Result of a Cloudflare cache purge operation."""

    model_config = ConfigDict(frozen=True)

    id: Optional[str] = None


class CFWorker(BaseModel):
    """A Cloudflare Worker script."""

    model_config = ConfigDict(frozen=True)

    id: Optional[str] = None
    etag: Optional[str] = None
    created_on: Optional[str] = None
    modified_on: Optional[str] = None
    size: Optional[int] = None


class CFPageRule(BaseModel):
    """A Cloudflare Page Rule."""

    model_config = ConfigDict(frozen=True)

    id: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[int] = None
    targets: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    created_on: Optional[str] = None
    modified_on: Optional[str] = None
