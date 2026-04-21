"""Generic Webhook connector -- send HTTP requests to any endpoint."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
from typing import Any, Optional
from xml.etree.ElementTree import Element, SubElement, tostring

import httpx

from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import (
    ConnectorCategory,
    ProtocolType,
    RateLimitSpec,
)

from .types import WebhookBatchResult, WebhookResponse


class Webhook(BaseConnector):
    """Generic connector for sending webhooks and HTTP requests to any endpoint.

    This connector is useful for integrating with tools that do not have
    dedicated connectors.  It supports JSON, form-encoded, XML, and
    GraphQL payloads, as well as HMAC-signed deliveries.

    The ``credentials`` field is optional and can be used as a default
    Bearer token or API key for authenticated endpoints.  The
    ``base_url`` is also optional; when omitted, each action requires
    an absolute URL.
    """

    name = "webhook"
    display_name = "Webhook"
    category = ConnectorCategory.CUSTOM
    protocol = ProtocolType.REST
    base_url = ""
    description = (
        "Generic connector for sending webhooks and HTTP requests to any "
        "endpoint. Supports JSON, form, XML, GraphQL, HMAC signing, and batch."
    )
    _rate_limit_config = RateLimitSpec(rate=120, period=60, burst=30)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Initialise the async HTTP client."""
        headers: dict[str, str] = {
            "Accept": "application/json",
        }
        # If credentials provided, use as default Bearer token
        if self._credentials:
            headers["Authorization"] = f"Bearer {self._credentials}"

        self._client = httpx.AsyncClient(
            headers=headers,
            timeout=self._timeout,
            follow_redirects=True,
        )

    async def _teardown(self) -> None:
        """Close the HTTP client."""
        if hasattr(self, "_client"):
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_response(
        url: str,
        method: str,
        response: httpx.Response,
        elapsed_ms: float,
    ) -> WebhookResponse:
        """Build a WebhookResponse from an httpx response.

        Args:
            url: The target URL.
            method: HTTP method used.
            response: The httpx response object.
            elapsed_ms: Request elapsed time in milliseconds.

        Returns:
            A WebhookResponse model.
        """
        response_body: Optional[str] = None
        try:
            response_body = response.text[:10000]  # Cap at 10KB
        except Exception:
            pass

        return WebhookResponse(
            url=url,
            method=method.upper(),
            status_code=response.status_code,
            success=200 <= response.status_code < 300,
            response_body=response_body,
            response_headers=dict(response.headers),
            elapsed_ms=elapsed_ms,
        )

    @staticmethod
    def _error_response(
        url: str,
        method: str,
        error: str,
    ) -> WebhookResponse:
        """Build an error WebhookResponse.

        Args:
            url: The target URL.
            method: HTTP method attempted.
            error: Error message.

        Returns:
            A WebhookResponse with success=False.
        """
        return WebhookResponse(
            url=url,
            method=method.upper(),
            success=False,
            error=error,
        )

    def _merge_headers(
        self,
        extra: Optional[dict[str, str]] = None,
    ) -> dict[str, str]:
        """Merge extra headers with any defaults.

        Args:
            extra: Additional headers to merge.

        Returns:
            Merged headers dict.
        """
        headers: dict[str, str] = {}
        if extra:
            headers.update(extra)
        return headers

    # ------------------------------------------------------------------
    # Actions -- Core
    # ------------------------------------------------------------------

    @action("Send a webhook request", dangerous=True)
    async def send_webhook(
        self,
        url: str,
        payload: dict[str, Any],
        method: str = "POST",
        headers: Optional[dict[str, str]] = None,
    ) -> WebhookResponse:
        """Send a generic webhook request with a JSON payload.

        Args:
            url: The target URL.
            payload: JSON-serialisable payload dict.
            method: HTTP method (default ``POST``).
            headers: Additional HTTP headers.

        Returns:
            A WebhookResponse with delivery status.
        """
        merged = self._merge_headers(headers)
        start = time.monotonic()
        try:
            response = await self._client.request(
                method.upper(),
                url,
                json=payload,
                headers=merged,
            )
            elapsed = (time.monotonic() - start) * 1000
            return self._build_response(url, method, response, elapsed)
        except Exception as exc:
            return self._error_response(url, method, str(exc))

    @action("Send a JSON payload", dangerous=True)
    async def send_json(
        self,
        url: str,
        data: dict[str, Any],
        headers: Optional[dict[str, str]] = None,
    ) -> WebhookResponse:
        """Send a JSON POST request.

        Args:
            url: The target URL.
            data: JSON-serialisable data dict.
            headers: Additional HTTP headers.

        Returns:
            A WebhookResponse with delivery status.
        """
        merged = self._merge_headers(headers)
        merged.setdefault("Content-Type", "application/json")
        start = time.monotonic()
        try:
            response = await self._client.post(
                url, json=data, headers=merged
            )
            elapsed = (time.monotonic() - start) * 1000
            return self._build_response(url, "POST", response, elapsed)
        except Exception as exc:
            return self._error_response(url, "POST", str(exc))

    @action("Send form-encoded data", dangerous=True)
    async def send_form(
        self,
        url: str,
        data: dict[str, str],
        headers: Optional[dict[str, str]] = None,
    ) -> WebhookResponse:
        """Send a form-encoded POST request.

        Args:
            url: The target URL.
            data: Form fields as key-value string pairs.
            headers: Additional HTTP headers.

        Returns:
            A WebhookResponse with delivery status.
        """
        merged = self._merge_headers(headers)
        start = time.monotonic()
        try:
            response = await self._client.post(
                url, data=data, headers=merged
            )
            elapsed = (time.monotonic() - start) * 1000
            return self._build_response(url, "POST", response, elapsed)
        except Exception as exc:
            return self._error_response(url, "POST", str(exc))

    @action("Send an HMAC-signed webhook", dangerous=True)
    async def send_with_hmac(
        self,
        url: str,
        payload: dict[str, Any],
        secret: str,
        header_name: str = "X-Hub-Signature-256",
    ) -> WebhookResponse:
        """Send a webhook with an HMAC-SHA256 signature header.

        The signature is computed over the raw JSON payload body using
        the provided secret and placed in the specified header.

        Args:
            url: The target URL.
            payload: JSON-serialisable payload dict.
            secret: HMAC shared secret.
            header_name: Header name for the signature
                (default ``X-Hub-Signature-256``).

        Returns:
            A WebhookResponse with delivery status.
        """
        import json as json_mod

        body_bytes = json_mod.dumps(payload, separators=(",", ":")).encode()
        signature = hmac.new(
            secret.encode(),
            body_bytes,
            hashlib.sha256,
        ).hexdigest()

        headers: dict[str, str] = {
            "Content-Type": "application/json",
            header_name: f"sha256={signature}",
        }
        start = time.monotonic()
        try:
            response = await self._client.post(
                url, content=body_bytes, headers=headers
            )
            elapsed = (time.monotonic() - start) * 1000
            return self._build_response(url, "POST", response, elapsed)
        except Exception as exc:
            return self._error_response(url, "POST", str(exc))

    @action("Send a batch of webhooks", dangerous=True)
    async def send_batch(
        self,
        url: str,
        payloads: list[dict[str, Any]],
    ) -> WebhookBatchResult:
        """Send multiple payloads to the same URL sequentially.

        Args:
            url: The target URL.
            payloads: List of JSON-serialisable payload dicts.

        Returns:
            A WebhookBatchResult summarising all deliveries.
        """
        results: list[WebhookResponse] = []
        succeeded = 0
        failed = 0

        for payload in payloads:
            result = await self.send_webhook(url, payload)
            results.append(result)
            if result.success:
                succeeded += 1
            else:
                failed += 1

        return WebhookBatchResult(
            total=len(payloads),
            succeeded=succeeded,
            failed=failed,
            results=results,
        )

    @action("Check if an endpoint is reachable")
    async def check_endpoint(self, url: str) -> WebhookResponse:
        """Send a HEAD request to verify that an endpoint is reachable.

        Args:
            url: The URL to check.

        Returns:
            A WebhookResponse indicating reachability.
        """
        start = time.monotonic()
        try:
            response = await self._client.head(url)
            elapsed = (time.monotonic() - start) * 1000
            return self._build_response(url, "HEAD", response, elapsed)
        except Exception as exc:
            return self._error_response(url, "HEAD", str(exc))

    # ------------------------------------------------------------------
    # Actions -- XML
    # ------------------------------------------------------------------

    @action("Send an XML payload", dangerous=True)
    async def send_xml(
        self,
        url: str,
        data: dict[str, Any],
        headers: Optional[dict[str, str]] = None,
    ) -> WebhookResponse:
        """Send an XML POST request built from a dict.

        The dict is converted to a simple XML structure with a ``<root>``
        element.  Each top-level key becomes a child element.

        Args:
            url: The target URL.
            data: Dict to convert to XML.
            headers: Additional HTTP headers.

        Returns:
            A WebhookResponse with delivery status.
        """
        root = Element("root")
        for key, value in data.items():
            child = SubElement(root, str(key))
            child.text = str(value) if value is not None else ""
        xml_bytes = tostring(root, encoding="unicode", xml_declaration=False)
        xml_payload = f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_bytes}'

        merged = self._merge_headers(headers)
        merged["Content-Type"] = "application/xml"

        start = time.monotonic()
        try:
            response = await self._client.post(
                url, content=xml_payload.encode(), headers=merged
            )
            elapsed = (time.monotonic() - start) * 1000
            return self._build_response(url, "POST", response, elapsed)
        except Exception as exc:
            return self._error_response(url, "POST", str(exc))

    # ------------------------------------------------------------------
    # Actions -- GraphQL
    # ------------------------------------------------------------------

    @action("Send a GraphQL query", dangerous=True)
    async def send_graphql(
        self,
        url: str,
        query: str,
        variables: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> WebhookResponse:
        """Send a GraphQL query or mutation.

        Args:
            url: The GraphQL endpoint URL.
            query: The GraphQL query/mutation string.
            variables: Optional GraphQL variables dict.
            headers: Additional HTTP headers.

        Returns:
            A WebhookResponse with the GraphQL response.
        """
        body: dict[str, Any] = {"query": query}
        if variables:
            body["variables"] = variables

        merged = self._merge_headers(headers)
        merged.setdefault("Content-Type", "application/json")

        start = time.monotonic()
        try:
            response = await self._client.post(
                url, json=body, headers=merged
            )
            elapsed = (time.monotonic() - start) * 1000
            return self._build_response(url, "POST", response, elapsed)
        except Exception as exc:
            return self._error_response(url, "POST", str(exc))

    # ------------------------------------------------------------------
    # Actions -- Retry and Multipart
    # ------------------------------------------------------------------

    @action("Send a webhook with automatic retries", dangerous=True)
    async def send_with_retry(
        self,
        url: str,
        payload: dict[str, Any],
        max_retries: Optional[int] = None,
        delay: Optional[float] = None,
    ) -> WebhookResponse:
        """Send a webhook with exponential backoff retries on failure.

        Args:
            url: The target URL.
            payload: JSON-serialisable payload dict.
            max_retries: Maximum retry attempts (default 3).
            delay: Initial delay between retries in seconds (default 1.0).

        Returns:
            A WebhookResponse from the last attempt.
        """
        retries = max_retries if max_retries is not None else 3
        wait = delay if delay is not None else 1.0

        last_result: Optional[WebhookResponse] = None
        for attempt in range(retries + 1):
            result = await self.send_webhook(url, payload)
            last_result = result
            if result.success:
                return result
            if attempt < retries:
                await asyncio.sleep(wait * (2 ** attempt))

        return last_result  # type: ignore[return-value]

    @action("Send a webhook with HTTP Basic authentication", dangerous=True)
    async def send_with_basic_auth(
        self,
        url: str,
        payload: dict[str, Any],
        username: str,
        password: str,
    ) -> WebhookResponse:
        """Send a webhook using HTTP Basic authentication.

        Args:
            url: The target URL.
            payload: JSON-serialisable payload dict.
            username: Basic auth username.
            password: Basic auth password.

        Returns:
            A WebhookResponse with delivery status.
        """
        import base64 as b64

        auth_str = b64.b64encode(
            f"{username}:{password}".encode()
        ).decode()
        headers: dict[str, str] = {
            "Authorization": f"Basic {auth_str}",
            "Content-Type": "application/json",
        }
        start = time.monotonic()
        try:
            response = await self._client.post(
                url, json=payload, headers=headers,
            )
            elapsed = (time.monotonic() - start) * 1000
            return self._build_response(url, "POST", response, elapsed)
        except Exception as exc:
            return self._error_response(url, "POST", str(exc))

    @action("Send a webhook with API key authentication", dangerous=True)
    async def send_with_api_key(
        self,
        url: str,
        payload: dict[str, Any],
        api_key: str,
        header_name: Optional[str] = None,
    ) -> WebhookResponse:
        """Send a webhook with an API key in a custom header.

        Args:
            url: The target URL.
            payload: JSON-serialisable payload dict.
            api_key: The API key value.
            header_name: Header name for the API key
                (default ``X-API-Key``).

        Returns:
            A WebhookResponse with delivery status.
        """
        key_header = header_name or "X-API-Key"
        headers: dict[str, str] = {
            key_header: api_key,
            "Content-Type": "application/json",
        }
        start = time.monotonic()
        try:
            response = await self._client.post(
                url, json=payload, headers=headers,
            )
            elapsed = (time.monotonic() - start) * 1000
            return self._build_response(url, "POST", response, elapsed)
        except Exception as exc:
            return self._error_response(url, "POST", str(exc))

    @action("Send a multipart form-data request", dangerous=True)
    async def send_multipart(
        self,
        url: str,
        files: dict[str, tuple[str, bytes, str]],
        data: Optional[dict[str, str]] = None,
    ) -> WebhookResponse:
        """Send a multipart/form-data POST request with file uploads.

        Args:
            url: The target URL.
            files: Dict mapping field names to tuples of
                ``(filename, content_bytes, content_type)``.
            data: Optional form fields to include alongside files.

        Returns:
            A WebhookResponse with delivery status.
        """
        multipart_files = {
            name: (fname, content, ctype)
            for name, (fname, content, ctype) in files.items()
        }
        start = time.monotonic()
        try:
            response = await self._client.post(
                url, files=multipart_files, data=data or {},
            )
            elapsed = (time.monotonic() - start) * 1000
            return self._build_response(url, "POST", response, elapsed)
        except Exception as exc:
            return self._error_response(url, "POST", str(exc))
