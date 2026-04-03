"""HTTP transport backed by ``httpx.AsyncClient``.

Provides a concrete :class:`HttpTransport` that satisfies the
:class:`~toolsconnector.runtime.transport.base.Transport` protocol using
``httpx`` for non-blocking HTTP requests.

All ``httpx``-specific exceptions are caught and re-raised as the
appropriate :mod:`toolsconnector.errors` subtypes so that callers never
need to depend on ``httpx`` directly.
"""

from __future__ import annotations

from typing import Any, Optional

import httpx

from toolsconnector.errors import ConnectionError, DNSError, TimeoutError, TransportError

from .base import TransportResponse

_DEFAULT_TIMEOUT: float = 30.0


class HttpTransport:
    """Async HTTP transport using :class:`httpx.AsyncClient`.

    Args:
        base_url: Optional base URL prepended to every request path.
        timeout: Default request timeout in seconds.
        headers: Default headers included in every request.
        verify_ssl: Whether to verify TLS certificates.
    """

    def __init__(
        self,
        *,
        base_url: str = "",
        timeout: float = _DEFAULT_TIMEOUT,
        headers: Optional[dict[str, str]] = None,
        verify_ssl: bool = True,
    ) -> None:
        self._base_url = base_url
        self._default_timeout = timeout
        self._default_headers = headers or {}
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(timeout),
            headers=self._default_headers,
            verify=verify_ssl,
        )

    # ------------------------------------------------------------------
    # Transport protocol
    # ------------------------------------------------------------------

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[dict[str, str]] = None,
        params: Optional[dict[str, Any]] = None,
        json: Any = None,
        content: Optional[bytes] = None,
        timeout: Optional[float] = None,
    ) -> TransportResponse:
        """Send an HTTP request via ``httpx``.

        Args:
            method: HTTP method (``GET``, ``POST``, etc.).
            url: Absolute or relative URL.  When relative, the *base_url*
                provided at construction time is prepended.
            headers: Per-request headers merged with the defaults.
            params: URL query-string parameters.
            json: JSON-serializable request body.
            content: Raw bytes request body.
            timeout: Per-request timeout override in seconds.

        Returns:
            A :class:`TransportResponse` populated from the ``httpx``
            response.

        Raises:
            toolsconnector.errors.TimeoutError: The request exceeded its
                timeout.
            toolsconnector.errors.ConnectionError: A TCP/TLS connection
                could not be established.
            toolsconnector.errors.DNSError: Hostname resolution failed.
            toolsconnector.errors.TransportError: Any other ``httpx``
                transport-level failure.
        """
        effective_timeout = (
            httpx.Timeout(timeout) if timeout is not None else httpx.USE_CLIENT_DEFAULT
        )

        try:
            response = await self._client.request(
                method,
                url,
                headers=headers,
                params=params,
                json=json,
                content=content,
                timeout=effective_timeout,
            )
        except httpx.TimeoutException as exc:
            raise TimeoutError(
                message=f"Request to {method} {url} timed out.",
                details={"method": method, "url": url},
            ) from exc
        except httpx.ConnectError as exc:
            error_msg = str(exc)
            # httpx wraps DNS failures inside ConnectError; detect via message.
            if "Name or service not known" in error_msg or "getaddrinfo" in error_msg:
                raise DNSError(
                    message=f"DNS resolution failed for {url}.",
                    details={"method": method, "url": url},
                ) from exc
            raise ConnectionError(
                message=f"Connection to {url} failed.",
                details={"method": method, "url": url},
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise TransportError(
                message=f"HTTP error {exc.response.status_code} for {method} {url}.",
                code="TRANSPORT_HTTP_ERROR",
                details={
                    "method": method,
                    "url": url,
                    "status_code": exc.response.status_code,
                },
                upstream_status=exc.response.status_code,
            ) from exc
        except httpx.HTTPError as exc:
            raise TransportError(
                message=f"Transport error during {method} {url}: {exc}",
                details={"method": method, "url": url},
            ) from exc

        return TransportResponse(
            status_code=response.status_code,
            headers=dict(response.headers),
            body=response.content,
        )

    async def close(self) -> None:
        """Close the underlying ``httpx.AsyncClient``."""
        await self._client.aclose()

    # ------------------------------------------------------------------
    # Context-manager support
    # ------------------------------------------------------------------

    async def __aenter__(self) -> HttpTransport:
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.close()
