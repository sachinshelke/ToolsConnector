"""Redis connector via Upstash REST API -- key/value, hash, and list operations.

Uses the Upstash REST-over-Redis pattern where each command is sent
as a POST request with a JSON array body (e.g. ``["SET", "key", "value"]``).

Authentication uses the ``Authorization: Bearer`` header with the
Upstash REST token.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import (
    ConnectorCategory,
    ProtocolType,
    RateLimitSpec,
)

from .types import RedisKeyInfo, RedisResult

logger = logging.getLogger("toolsconnector.redis")


class Redis(BaseConnector):
    """Connect to Redis via the Upstash REST API.

    Credentials should be the Upstash REST token string.  The
    ``base_url`` should point to your Upstash Redis endpoint, e.g.
    ``https://your-redis.upstash.io``.
    """

    name = "redis"
    display_name = "Redis (Upstash)"
    category = ConnectorCategory.DATABASE
    protocol = ProtocolType.REST
    base_url = "https://your-redis.upstash.io"
    description = (
        "Connect to Redis via Upstash to get/set keys, "
        "work with hashes and lists, and manage key expiry."
    )
    _rate_limit_config = RateLimitSpec(rate=1000, period=1, burst=200)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Initialise the httpx client with Bearer auth."""
        token = self._credentials or ""

        headers: dict[str, str] = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        self._client = httpx.AsyncClient(
            base_url=self._base_url or self.__class__.base_url,
            headers=headers,
            timeout=self._timeout,
        )

    async def _teardown(self) -> None:
        """Close the httpx client."""
        if hasattr(self, "_client"):
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _request(
        self, command: list[Any],
    ) -> httpx.Response:
        """Send a Redis command via the Upstash REST API.

        The Upstash REST API accepts a JSON array representing the
        Redis command and its arguments.

        Args:
            command: Redis command as a list (e.g. ``["GET", "mykey"]``).

        Returns:
            httpx.Response object.

        Raises:
            httpx.HTTPStatusError: On 4xx/5xx responses.
        """
        resp = await self._client.post("/", json=command)
        resp.raise_for_status()
        return resp

    def _parse_result(self, resp: httpx.Response) -> Any:
        """Extract the ``result`` field from an Upstash response.

        Args:
            resp: httpx.Response from an Upstash request.

        Returns:
            The ``result`` value from the JSON response.
        """
        data = resp.json()
        return data.get("result")

    # ------------------------------------------------------------------
    # Actions -- String operations
    # ------------------------------------------------------------------

    @action("Get the value of a Redis key")
    async def get(self, key: str) -> RedisResult:
        """Get the value stored at a key.

        Args:
            key: Redis key name.

        Returns:
            RedisResult with the key's value, or None if the key does
            not exist.
        """
        resp = await self._request(["GET", key])
        return RedisResult(result=self._parse_result(resp))

    @action("Set the value of a Redis key")
    async def set(
        self,
        key: str,
        value: str,
        ex: Optional[int] = None,
    ) -> RedisResult:
        """Set a key to a string value with optional expiry.

        Args:
            key: Redis key name.
            value: Value to store.
            ex: Optional expiry time in seconds.

        Returns:
            RedisResult (typically ``"OK"``).
        """
        cmd: list[Any] = ["SET", key, value]
        if ex is not None:
            cmd.extend(["EX", ex])

        resp = await self._request(cmd)
        return RedisResult(result=self._parse_result(resp))

    @action("Delete a Redis key", dangerous=True)
    async def delete(self, key: str) -> RedisResult:
        """Delete a key.

        Args:
            key: Redis key name to delete.

        Returns:
            RedisResult with the number of keys removed (0 or 1).
        """
        resp = await self._request(["DEL", key])
        return RedisResult(result=self._parse_result(resp))

    @action("Find Redis keys matching a pattern")
    async def keys(self, pattern: Optional[str] = None) -> RedisResult:
        """Find all keys matching a glob-style pattern.

        Args:
            pattern: Glob pattern (e.g. ``user:*``).  Defaults to ``*``.

        Returns:
            RedisResult with a list of matching key names.
        """
        pat = pattern or "*"
        resp = await self._request(["KEYS", pat])
        return RedisResult(result=self._parse_result(resp))

    # ------------------------------------------------------------------
    # Actions -- Hash operations
    # ------------------------------------------------------------------

    @action("Get a field from a Redis hash")
    async def hget(self, key: str, field: str) -> RedisResult:
        """Get the value of a hash field.

        Args:
            key: Redis key holding the hash.
            field: Field name within the hash.

        Returns:
            RedisResult with the field value, or None if not found.
        """
        resp = await self._request(["HGET", key, field])
        return RedisResult(result=self._parse_result(resp))

    @action("Set a field in a Redis hash")
    async def hset(
        self, key: str, field: str, value: str,
    ) -> RedisResult:
        """Set the value of a hash field.

        Args:
            key: Redis key holding the hash.
            field: Field name within the hash.
            value: Value to set.

        Returns:
            RedisResult (1 if new field created, 0 if updated).
        """
        resp = await self._request(["HSET", key, field, value])
        return RedisResult(result=self._parse_result(resp))

    # ------------------------------------------------------------------
    # Actions -- List operations
    # ------------------------------------------------------------------

    @action("Push values onto the head of a Redis list")
    async def lpush(
        self, key: str, values: list[str],
    ) -> RedisResult:
        """Push one or more values onto the head (left) of a list.

        Args:
            key: Redis key holding the list.
            values: Values to push (leftmost first).

        Returns:
            RedisResult with the new length of the list.
        """
        cmd: list[Any] = ["LPUSH", key, *values]
        resp = await self._request(cmd)
        return RedisResult(result=self._parse_result(resp))

    @action("Get a range of elements from a Redis list")
    async def lrange(
        self, key: str, start: int, stop: int,
    ) -> RedisResult:
        """Get elements from a list by index range.

        Args:
            key: Redis key holding the list.
            start: Start index (0-based, supports negative).
            stop: Stop index (inclusive, supports negative).

        Returns:
            RedisResult with a list of elements.
        """
        resp = await self._request(["LRANGE", key, start, stop])
        return RedisResult(result=self._parse_result(resp))

    # ------------------------------------------------------------------
    # Actions -- Key management (extended)
    # ------------------------------------------------------------------

    @action("Set a TTL (expiry) on a key")
    async def expire(self, key: str, seconds: int) -> RedisResult:
        """Set a timeout on a key.

        Args:
            key: Redis key to set expiry on.
            seconds: Time to live in seconds.

        Returns:
            RedisResult with 1 if set, 0 if key does not exist.
        """
        resp = await self._request(["EXPIRE", key, seconds])
        return RedisResult(result=self._parse_result(resp))

    @action("Get the remaining TTL of a key")
    async def ttl(self, key: str) -> RedisResult:
        """Get the remaining time to live of a key in seconds.

        Args:
            key: Redis key to check.

        Returns:
            RedisResult with TTL in seconds, -1 if no expiry, -2 if missing.
        """
        resp = await self._request(["TTL", key])
        return RedisResult(result=self._parse_result(resp))

    @action("Increment a key's integer value")
    async def incr(self, key: str) -> RedisResult:
        """Increment the integer value of a key by one.

        Args:
            key: Redis key to increment.

        Returns:
            RedisResult with the new integer value.
        """
        resp = await self._request(["INCR", key])
        return RedisResult(result=self._parse_result(resp))

    @action("Check if one or more keys exist")
    async def exists(self, keys: list[str]) -> RedisResult:
        """Check if keys exist in Redis.

        Args:
            keys: List of keys to check.

        Returns:
            RedisResult with the number of existing keys.
        """
        resp = await self._request(["EXISTS", *keys])
        return RedisResult(result=self._parse_result(resp))

    @action("Get the type of a key")
    async def type(self, key: str) -> RedisResult:
        """Get the type stored at a key.

        Args:
            key: Redis key to check.

        Returns:
            RedisResult with the type (string, list, set, zset, hash, stream).
        """
        resp = await self._request(["TYPE", key])
        return RedisResult(result=self._parse_result(resp))
