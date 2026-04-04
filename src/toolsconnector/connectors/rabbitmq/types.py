"""Pydantic models for RabbitMQ Management API connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class RabbitQueue(BaseModel):
    """A RabbitMQ queue."""

    model_config = ConfigDict(frozen=True)

    name: str = ""
    vhost: str = "/"
    durable: bool = False
    auto_delete: bool = False
    exclusive: bool = False
    state: str = ""
    messages: int = 0
    messages_ready: int = 0
    messages_unacknowledged: int = 0
    consumers: int = 0
    node: str = ""
    memory: int = 0
    arguments: dict[str, Any] = Field(default_factory=dict)


class RabbitExchange(BaseModel):
    """A RabbitMQ exchange."""

    model_config = ConfigDict(frozen=True)

    name: str = ""
    vhost: str = "/"
    type: str = "direct"
    durable: bool = False
    auto_delete: bool = False
    internal: bool = False
    arguments: dict[str, Any] = Field(default_factory=dict)


class RabbitMessage(BaseModel):
    """A message retrieved from a RabbitMQ queue."""

    model_config = ConfigDict(frozen=True)

    payload: str = ""
    payload_bytes: int = 0
    payload_encoding: str = "string"
    routing_key: str = ""
    exchange: str = ""
    redelivered: bool = False
    properties: dict[str, Any] = Field(default_factory=dict)
    message_count: int = 0


class RabbitConnection(BaseModel):
    """A RabbitMQ connection."""

    model_config = ConfigDict(frozen=True)

    name: str = ""
    node: str = ""
    state: str = ""
    user: str = ""
    vhost: str = "/"
    protocol: str = ""
    host: str = ""
    port: int = 0
    peer_host: str = ""
    peer_port: int = 0
    channels: int = 0
    connected_at: Optional[int] = None
    recv_oct: int = 0
    send_oct: int = 0


class RabbitChannel(BaseModel):
    """A RabbitMQ channel."""

    model_config = ConfigDict(frozen=True)

    name: str = ""
    node: str = ""
    state: str = ""
    connection_details: dict[str, Any] = Field(default_factory=dict)
    number: int = 0
    user: str = ""
    vhost: str = "/"
    consumer_count: int = 0
    messages_unacknowledged: int = 0
    messages_unconfirmed: int = 0
    prefetch_count: int = 0


class RabbitOverview(BaseModel):
    """RabbitMQ cluster overview and stats."""

    model_config = ConfigDict(frozen=True)

    management_version: str = ""
    rabbitmq_version: str = ""
    erlang_version: str = ""
    cluster_name: str = ""
    node: str = ""
    queue_totals: dict[str, int] = Field(default_factory=dict)
    object_totals: dict[str, int] = Field(default_factory=dict)
    message_stats: dict[str, Any] = Field(default_factory=dict)
    listeners: list[dict[str, Any]] = Field(default_factory=list)
