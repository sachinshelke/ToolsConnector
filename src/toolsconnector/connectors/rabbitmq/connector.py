"""RabbitMQ connector -- manage queues, exchanges, and messages via Management API.

Uses the RabbitMQ Management HTTP API (default: ``http://localhost:15672/api``).
Credentials should be ``"username:password"`` format.
"""

from __future__ import annotations

import base64
import logging
import urllib.parse
from typing import Any, Optional

import httpx

from toolsconnector.errors import APIError, NotFoundError, RateLimitError
from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import (
    ConnectorCategory,
    ProtocolType,
    RateLimitSpec,
)
from toolsconnector.types import PaginatedList, PageState

from .types import (
    RabbitChannel,
    RabbitConnection,
    RabbitExchange,
    RabbitMessage,
    RabbitOverview,
    RabbitQueue,
)

logger = logging.getLogger("toolsconnector.rabbitmq")


class RabbitMQ(BaseConnector):
    """Connect to RabbitMQ via the Management HTTP API.

    Credentials format: ``"username:password"``
    Base URL defaults to ``http://localhost:15672/api`` and is configurable
    via the ``base_url`` constructor parameter.
    """

    name = "rabbitmq"
    display_name = "RabbitMQ"
    category = ConnectorCategory.MESSAGE_QUEUE
    protocol = ProtocolType.REST
    base_url = "http://localhost:15672/api"
    description = (
        "Connect to RabbitMQ Management API to list queues, publish "
        "messages, and monitor broker health."
    )
    _rate_limit_config = RateLimitSpec(rate=60, period=1, burst=30)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Parse credentials and initialise the HTTP client."""
        creds = str(self._credentials)
        parts = creds.split(":", 1)
        if len(parts) < 2:
            raise ValueError(
                "RabbitMQ credentials must be 'username:password'"
            )
        self._username = parts[0]
        self._password = parts[1]

        auth_str = base64.b64encode(
            f"{self._username}:{self._password}".encode()
        ).decode()

        self._client = httpx.AsyncClient(
            base_url=self._base_url or self.__class__.base_url,
            headers={
                "Authorization": f"Basic {auth_str}",
                "Content-Type": "application/json",
            },
            timeout=self._timeout,
        )

    async def _teardown(self) -> None:
        """Close the HTTP client."""
        if hasattr(self, "_client"):
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
    ) -> Any:
        """Execute an HTTP request against the RabbitMQ Management API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE).
            path: API path relative to base URL.
            json_body: JSON request body.
            params: URL query parameters.

        Returns:
            Parsed JSON response or None for 204 responses.

        Raises:
            NotFoundError: If the resource is not found (404).
            RateLimitError: If rate limited (429).
            APIError: For any other API error.
        """
        kwargs: dict[str, Any] = {}
        if json_body is not None:
            kwargs["json"] = json_body
        if params is not None:
            kwargs["params"] = params

        response = await self._client.request(method, path, **kwargs)

        if response.status_code == 204:
            return None

        if response.status_code >= 400:
            try:
                err_body = response.json()
            except Exception:
                err_body = {"reason": response.text}

            err_msg = f"RabbitMQ API error ({response.status_code}): {err_body}"

            if response.status_code == 404:
                raise NotFoundError(
                    err_msg,
                    connector="rabbitmq",
                    action=path,
                    details=err_body if isinstance(err_body, dict) else {},
                )
            if response.status_code == 429:
                raise RateLimitError(
                    err_msg,
                    connector="rabbitmq",
                    action=path,
                )
            raise APIError(
                err_msg,
                connector="rabbitmq",
                action=path,
                upstream_status=response.status_code,
                details=err_body if isinstance(err_body, dict) else {},
            )

        return response.json()

    @staticmethod
    def _encode_vhost(vhost: str) -> str:
        """URL-encode a vhost name for the Management API path.

        Args:
            vhost: Virtual host name.

        Returns:
            URL-encoded vhost string.
        """
        return urllib.parse.quote(vhost, safe="")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    @action("List queues in the RabbitMQ broker")
    async def list_queues(
        self,
        vhost: Optional[str] = None,
    ) -> PaginatedList[RabbitQueue]:
        """List all queues, optionally filtered by virtual host.

        Args:
            vhost: Filter queues by virtual host name.

        Returns:
            Paginated list of RabbitQueue objects.
        """
        if vhost:
            path = f"/queues/{self._encode_vhost(vhost)}"
        else:
            path = "/queues"

        data = await self._request("GET", path)
        queues = [RabbitQueue(**q) for q in (data or [])]
        return PaginatedList(
            items=queues,
            page_state=PageState(has_more=False),
        )

    @action("Get details for a specific queue")
    async def get_queue(
        self,
        vhost: str,
        queue_name: str,
    ) -> RabbitQueue:
        """Get detailed information about a specific queue.

        Args:
            vhost: Virtual host containing the queue.
            queue_name: Name of the queue.

        Returns:
            RabbitQueue with full details.
        """
        path = (
            f"/queues/{self._encode_vhost(vhost)}"
            f"/{urllib.parse.quote(queue_name, safe='')}"
        )
        data = await self._request("GET", path)
        return RabbitQueue(**data)

    @action("Publish a message to an exchange")
    async def publish_message(
        self,
        vhost: str,
        exchange: str,
        routing_key: str,
        payload: str,
    ) -> bool:
        """Publish a message to an exchange with a routing key.

        Args:
            vhost: Virtual host containing the exchange.
            exchange: Exchange name (use ``""`` for the default exchange).
            routing_key: Routing key for the message.
            payload: Message body as a string.

        Returns:
            True if the message was routed successfully.
        """
        encoded_vhost = self._encode_vhost(vhost)
        encoded_exchange = urllib.parse.quote(exchange, safe="")
        path = f"/exchanges/{encoded_vhost}/{encoded_exchange}/publish"

        body = {
            "properties": {},
            "routing_key": routing_key,
            "payload": payload,
            "payload_encoding": "string",
        }
        data = await self._request("POST", path, json_body=body)
        return data.get("routed", False) if data else False

    @action("Get messages from a queue")
    async def get_messages(
        self,
        vhost: str,
        queue_name: str,
        count: int = 1,
        ack_mode: str = "ack_requeue_true",
    ) -> list[RabbitMessage]:
        """Retrieve messages from a queue without consuming them.

        Args:
            vhost: Virtual host containing the queue.
            queue_name: Name of the queue.
            count: Number of messages to retrieve (default 1).
            ack_mode: Acknowledgement mode. One of ``ack_requeue_true``,
                ``ack_requeue_false``, or ``reject_requeue_true``.

        Returns:
            List of RabbitMessage objects.
        """
        encoded_vhost = self._encode_vhost(vhost)
        encoded_queue = urllib.parse.quote(queue_name, safe="")
        path = f"/queues/{encoded_vhost}/{encoded_queue}/get"

        body = {
            "count": count,
            "ackmode": ack_mode,
            "encoding": "auto",
        }
        data = await self._request("POST", path, json_body=body)
        return [RabbitMessage(**m) for m in (data or [])]

    @action("List exchanges in the RabbitMQ broker")
    async def list_exchanges(
        self,
        vhost: Optional[str] = None,
    ) -> PaginatedList[RabbitExchange]:
        """List all exchanges, optionally filtered by virtual host.

        Args:
            vhost: Filter exchanges by virtual host name.

        Returns:
            Paginated list of RabbitExchange objects.
        """
        if vhost:
            path = f"/exchanges/{self._encode_vhost(vhost)}"
        else:
            path = "/exchanges"

        data = await self._request("GET", path)
        exchanges = [RabbitExchange(**e) for e in (data or [])]
        return PaginatedList(
            items=exchanges,
            page_state=PageState(has_more=False),
        )

    @action("List active connections to the broker")
    async def list_connections(self) -> PaginatedList[RabbitConnection]:
        """List all active connections to the RabbitMQ broker.

        Returns:
            Paginated list of RabbitConnection objects.
        """
        data = await self._request("GET", "/connections")
        connections = [RabbitConnection(**c) for c in (data or [])]
        return PaginatedList(
            items=connections,
            page_state=PageState(has_more=False),
        )

    @action("List active channels in the broker")
    async def list_channels(self) -> PaginatedList[RabbitChannel]:
        """List all active channels across connections.

        Returns:
            Paginated list of RabbitChannel objects.
        """
        data = await self._request("GET", "/channels")
        channels = [RabbitChannel(**c) for c in (data or [])]
        return PaginatedList(
            items=channels,
            page_state=PageState(has_more=False),
        )

    @action("Get broker overview and cluster statistics")
    async def get_overview(self) -> RabbitOverview:
        """Get an overview of the RabbitMQ broker including version info
        and aggregate statistics.

        Returns:
            RabbitOverview with cluster-wide stats.
        """
        data = await self._request("GET", "/overview")
        return RabbitOverview(
            management_version=data.get("management_version", ""),
            rabbitmq_version=data.get("rabbitmq_version", ""),
            erlang_version=data.get("erlang_version", ""),
            cluster_name=data.get("cluster_name", ""),
            node=data.get("node", ""),
            queue_totals=data.get("queue_totals", {}),
            object_totals=data.get("object_totals", {}),
            message_stats=data.get("message_stats", {}),
            listeners=data.get("listeners", []),
        )

    # ------------------------------------------------------------------
    # Actions -- Queue management (extended)
    # ------------------------------------------------------------------

    @action("Create a new queue", dangerous=True)
    async def create_queue(
        self,
        vhost: str,
        queue_name: str,
        durable: Optional[bool] = None,
    ) -> bool:
        """Create a new queue in a vhost.

        Args:
            vhost: The virtual host name (use ``%2F`` for the default ``/``).
            queue_name: The name for the new queue.
            durable: Whether the queue survives broker restart.

        Returns:
            True if the queue was created.
        """
        body: dict[str, Any] = {}
        if durable is not None:
            body["durable"] = durable
        await self._request(
            "PUT", f"/queues/{vhost}/{queue_name}", json_body=body,
        )
        return True

    @action("Delete a queue", dangerous=True)
    async def delete_queue(
        self, vhost: str, queue_name: str,
    ) -> bool:
        """Delete a queue from a vhost.

        Args:
            vhost: The virtual host name.
            queue_name: The queue name to delete.

        Returns:
            True if the queue was deleted.
        """
        await self._request(
            "DELETE", f"/queues/{vhost}/{queue_name}",
        )
        return True

    # ------------------------------------------------------------------
    # Actions -- Exchange management (extended)
    # ------------------------------------------------------------------

    @action("Create a new exchange", dangerous=True)
    async def create_exchange(
        self,
        vhost: str,
        name: str,
        type: str,
    ) -> bool:
        """Create a new exchange in a vhost.

        Args:
            vhost: The virtual host name.
            name: The exchange name.
            type: Exchange type (``direct``, ``fanout``, ``topic``, ``headers``).

        Returns:
            True if the exchange was created.
        """
        body: dict[str, Any] = {"type": type, "durable": True}
        await self._request(
            "PUT", f"/exchanges/{vhost}/{name}", json_body=body,
        )
        return True

    @action("Delete an exchange", dangerous=True)
    async def delete_exchange(
        self, vhost: str, name: str,
    ) -> bool:
        """Delete an exchange from a vhost.

        Args:
            vhost: The virtual host name.
            name: The exchange name to delete.

        Returns:
            True if the exchange was deleted.
        """
        await self._request(
            "DELETE", f"/exchanges/{vhost}/{name}",
        )
        return True

    # ------------------------------------------------------------------
    # Actions -- Exchange details
    # ------------------------------------------------------------------

    @action("Get details for a specific exchange")
    async def get_exchange(
        self,
        vhost: str,
        name: str,
    ) -> RabbitExchange:
        """Get detailed information about a specific exchange.

        Args:
            vhost: Virtual host containing the exchange.
            name: Name of the exchange.

        Returns:
            RabbitExchange with full details.
        """
        encoded_vhost = self._encode_vhost(vhost)
        encoded_name = urllib.parse.quote(name, safe="")
        path = f"/exchanges/{encoded_vhost}/{encoded_name}"
        data = await self._request("GET", path)
        return RabbitExchange(**data)

    # ------------------------------------------------------------------
    # Actions -- Bindings
    # ------------------------------------------------------------------

    @action("List bindings in a virtual host")
    async def list_bindings(
        self,
        vhost: str,
    ) -> list[dict[str, Any]]:
        """List all bindings in a virtual host.

        Bindings connect exchanges to queues or other exchanges
        with routing keys.

        Args:
            vhost: Virtual host name.

        Returns:
            List of binding dicts with source, destination, routing_key, etc.
        """
        encoded_vhost = self._encode_vhost(vhost)
        data = await self._request(
            "GET", f"/bindings/{encoded_vhost}",
        )
        return data if isinstance(data, list) else []

    # ------------------------------------------------------------------
    # Actions -- Queue purge
    # ------------------------------------------------------------------

    @action("Purge all messages from a queue", dangerous=True)
    async def purge_queue(
        self,
        vhost: str,
        queue_name: str,
    ) -> bool:
        """Purge all messages from a queue without deleting the queue.

        This is a destructive action -- all messages in the queue
        will be permanently removed.

        Args:
            vhost: Virtual host containing the queue.
            queue_name: Name of the queue to purge.

        Returns:
            True if the queue was purged.
        """
        encoded_vhost = self._encode_vhost(vhost)
        encoded_queue = urllib.parse.quote(queue_name, safe="")
        await self._request(
            "DELETE",
            f"/queues/{encoded_vhost}/{encoded_queue}/contents",
        )
        return True

    # ------------------------------------------------------------------
    # Actions -- Node info
    # ------------------------------------------------------------------

    @action("Get information about a broker node")
    async def get_node_info(self) -> list[dict[str, Any]]:
        """Get information about all nodes in the RabbitMQ cluster.

        Returns:
            List of node dicts with name, type, memory, disk, etc.
        """
        data = await self._request("GET", "/nodes")
        return data if isinstance(data, list) else []
