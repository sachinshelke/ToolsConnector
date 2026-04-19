"""Medium connector — publish articles to Medium profiles and publications.

Uses the Medium REST API (https://github.com/Medium/medium-api-docs)
with Bearer integration token authentication.

⚠️ DEPRECATION NOTICE
---------------------
Medium stopped issuing new integration tokens in 2023. This connector works
only for users who already hold a legacy integration token from before the
deprecation. New users cannot obtain a token, and the underlying API has
NOT received public updates since.

Out of scope (see README "Not Supported"):
- Comments — Medium API has no comments endpoint and never has.
- Listing posts — Medium API exposes no user-posts list endpoint.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from toolsconnector.errors import (
    APIError,
    InvalidCredentialsError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    ValidationError,
)
from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import ConnectorCategory, ProtocolType, RateLimitSpec

from .types import MediumPost, MediumPublication, MediumUser

logger = logging.getLogger("toolsconnector.medium")


class Medium(BaseConnector):
    """Connect to Medium to publish articles to your profile and publications.

    Requires a Medium integration token passed as ``credentials``.

    NOTE: Medium stopped issuing new integration tokens in 2023. Only users
    with existing legacy tokens can use this connector. New users cannot
    obtain a token. See README for details.
    """

    name = "medium"
    display_name = "Medium"
    category = ConnectorCategory.SOCIAL
    protocol = ProtocolType.REST
    base_url = "https://api.medium.com/v1"
    description = (
        "Publish articles to your Medium profile and publications. "
        "NOTE: Medium API was deprecated in 2023 — only legacy "
        "integration tokens still work."
    )
    _rate_limit_config = RateLimitSpec(rate=1, period=2, burst=3)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Initialise the async HTTP client."""
        self._client = httpx.AsyncClient(
            base_url=self._base_url or self.__class__.base_url,
            headers={
                "Authorization": f"Bearer {self._credentials}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Accept-Charset": "utf-8",
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
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[dict[str, Any]] = None,
    ) -> Any:
        """Execute an HTTP request against the Medium REST API.

        The Medium API wraps successful responses in ``{"data": ...}`` and
        errors in ``{"errors": [{"message": ..., "code": ...}]}``.

        Args:
            method: HTTP method (GET, POST).
            path: API path (e.g. ``/me``).
            params: URL query parameters.
            json_body: JSON request body.

        Returns:
            The unwrapped ``data`` payload (dict, list, or None for 204).

        Raises:
            InvalidCredentialsError: If the token is invalid (HTTP 401).
            PermissionDeniedError: If the token lacks permission (HTTP 403).
            NotFoundError: If the resource is not found (HTTP 404).
            ValidationError: If the request is malformed (HTTP 400/422).
            RateLimitError: If the API returns HTTP 429.
            ServerError: If Medium returns a 5xx error.
            APIError: For any other non-2xx response.
        """
        kwargs: dict[str, Any] = {}
        if params:
            kwargs["params"] = params
        if json_body is not None:
            kwargs["json"] = json_body

        response = await self._client.request(method, path, **kwargs)
        status = response.status_code

        # 204 No Content
        if status == 204:
            return None

        try:
            body = response.json()
        except Exception:
            body = {}

        # Success — unwrap "data" envelope
        if 200 <= status < 300:
            if isinstance(body, dict) and "data" in body:
                return body["data"]
            return body

        # Error mapping
        errors = body.get("errors") if isinstance(body, dict) else None
        if errors and isinstance(errors, list) and errors:
            err = errors[0]
            error_msg = err.get("message", f"Medium API error (HTTP {status})")
            error_code = err.get("code", 0)
        else:
            error_msg = f"Medium API error (HTTP {status})"
            error_code = 0

        details = {"medium_code": error_code, "response": body}

        if status == 401:
            raise InvalidCredentialsError(
                error_msg,
                connector="medium",
                action=path,
                suggestion=(
                    "Medium integration tokens cannot be reissued (API "
                    "deprecated in 2023). Verify the token is still valid "
                    "via https://medium.com/me/settings."
                ),
                details=details,
            )
        if status == 403:
            raise PermissionDeniedError(
                error_msg,
                connector="medium",
                action=path,
                details=details,
            )
        if status == 404:
            raise NotFoundError(
                error_msg,
                connector="medium",
                action=path,
                details=details,
            )
        if status in (400, 422):
            raise ValidationError(
                error_msg,
                connector="medium",
                action=path,
                details=details,
            )
        if status == 429:
            retry_after = float(response.headers.get("Retry-After", "60"))
            raise RateLimitError(
                error_msg,
                connector="medium",
                action=path,
                retry_after_seconds=retry_after,
                details=details,
            )
        if status >= 500:
            raise ServerError(
                error_msg,
                connector="medium",
                action=path,
                details=details,
                upstream_status=status,
            )

        raise APIError(
            error_msg,
            connector="medium",
            action=path,
            details=details,
            upstream_status=status,
        )

    # ======================================================================
    # USER
    # ======================================================================

    @action("Get the authenticated Medium user's profile")
    async def get_me(self) -> MediumUser:
        """Get the authenticated Medium user's profile.

        This is typically the first call you make — the returned ``id`` is
        required for ``create_user_post`` and ``list_publications``.

        Returns:
            The authenticated user's profile.
        """
        data = await self._request("GET", "/me")
        return MediumUser(**data)

    # ======================================================================
    # PUBLICATIONS
    # ======================================================================

    @action("List publications the user is allowed to write to")
    async def list_publications(self, userId: str) -> list[MediumPublication]:
        """List publications the user contributes to or owns.

        The Medium API returns all publications in a single response (no
        pagination is supported by this endpoint).

        Args:
            userId: The Medium user ID (from ``get_me``).

        Returns:
            A list of publications the user is associated with.
        """
        data = await self._request("GET", f"/users/{userId}/publications")
        return [MediumPublication(**pub) for pub in data]

    # ======================================================================
    # POSTS
    # ======================================================================

    @action(
        "Publish an article to the authenticated user's personal Medium feed",
        dangerous=True,
    )
    async def create_user_post(
        self,
        userId: str,
        title: str,
        contentFormat: str,
        content: str,
        tags: Optional[list[str]] = None,
        canonicalUrl: Optional[str] = None,
        publishStatus: str = "public",
        license: Optional[str] = None,
        notifyFollowers: bool = False,
    ) -> MediumPost:
        """Publish an article to the user's personal Medium feed.

        Args:
            userId: The Medium user ID (from ``get_me``).
            title: The post title (used in the URL slug).
            contentFormat: Either ``"html"`` or ``"markdown"``.
            content: The post body in the chosen format.
            tags: Up to 5 tags (each <= 25 chars).
            canonicalUrl: Original URL if this is a republished post.
            publishStatus: ``"public"``, ``"draft"``, or ``"unlisted"``.
                Defaults to ``"public"``.
            license: Content license (e.g. ``"all-rights-reserved"``,
                ``"cc-40-by"``, ``"cc-40-by-sa"``).
            notifyFollowers: Whether to notify the author's followers.

        Returns:
            The created post.
        """
        payload: dict[str, Any] = {
            "title": title,
            "contentFormat": contentFormat,
            "content": content,
            "publishStatus": publishStatus,
            "notifyFollowers": notifyFollowers,
        }
        if tags:
            payload["tags"] = tags
        if canonicalUrl:
            payload["canonicalUrl"] = canonicalUrl
        if license:
            payload["license"] = license

        data = await self._request("POST", f"/users/{userId}/posts", json_body=payload)
        return MediumPost(**data)

    @action(
        "Publish an article to a Medium publication",
        dangerous=True,
    )
    async def create_publication_post(
        self,
        publicationId: str,
        title: str,
        contentFormat: str,
        content: str,
        tags: Optional[list[str]] = None,
        canonicalUrl: Optional[str] = None,
        publishStatus: str = "public",
        license: Optional[str] = None,
        notifyFollowers: bool = False,
    ) -> MediumPost:
        """Publish an article to a Medium publication.

        Call ``list_publications`` first to discover publication IDs the
        authenticated user is allowed to publish to.

        Args:
            publicationId: The publication ID (from ``list_publications``).
            title: The post title (used in the URL slug).
            contentFormat: Either ``"html"`` or ``"markdown"``.
            content: The post body in the chosen format.
            tags: Up to 5 tags (each <= 25 chars).
            canonicalUrl: Original URL if this is a republished post.
            publishStatus: ``"public"``, ``"draft"``, or ``"unlisted"``.
                Defaults to ``"public"``.
            license: Content license (e.g. ``"all-rights-reserved"``,
                ``"cc-40-by"``, ``"cc-40-by-sa"``).
            notifyFollowers: Whether to notify the author's followers.

        Returns:
            The created post.
        """
        payload: dict[str, Any] = {
            "title": title,
            "contentFormat": contentFormat,
            "content": content,
            "publishStatus": publishStatus,
            "notifyFollowers": notifyFollowers,
        }
        if tags:
            payload["tags"] = tags
        if canonicalUrl:
            payload["canonicalUrl"] = canonicalUrl
        if license:
            payload["license"] = license

        data = await self._request(
            "POST", f"/publications/{publicationId}/posts", json_body=payload
        )
        return MediumPost(**data)
