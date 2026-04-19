"""LinkedIn connector — post, comment, and react on the authenticated user's feed.

Uses the LinkedIn REST API with OAuth 2.0 Bearer token authentication.

API version strategy
--------------------
LinkedIn maintains two parallel API surfaces. We use them deliberately:

- ``/rest/posts`` (newer, requires ``LinkedIn-Version`` header) — for posts
  CRUD. This is LinkedIn's documented forward path.
- ``/v2/socialActions/{urn}`` (legacy v2) — for comments and reactions.
  No ``/rest`` equivalent exists yet for these endpoints.
- ``/v2/userinfo`` (OIDC) — for fetching the authenticated user's identity.
  Most reliable way to get the person URN across API versions.

Each action's docstring documents which surface it targets.

Out of scope (see README "Not Supported"):
- DMs / Messaging API — requires LinkedIn Partner Program approval (a
  contract with LinkedIn, not OAuth scopes). Not BYOK-accessible.
- Mentions / Notifications — partner-only Notifications API.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from urllib.parse import quote as url_quote

import httpx

from toolsconnector.errors import (
    APIError,
    InvalidCredentialsError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    TokenExpiredError,
    ValidationError,
)
from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import ConnectorCategory, ProtocolType, RateLimitSpec
from toolsconnector.types import PageState, PaginatedList

from .types import LinkedInComment, LinkedInPost, LinkedInProfile

logger = logging.getLogger("toolsconnector.linkedin")

# Pin a stable, well-supported version. LinkedIn versions are YYYYMM strings
# and remain available for ~12 months after release.
_LINKEDIN_VERSION = "202506"

# Substrings in a 401 body indicating the token has expired (vs. invalid format).
_EXPIRED_TOKEN_MARKERS = (
    "EXPIRED_ACCESS_TOKEN",
    "REVOKED_ACCESS_TOKEN",
    "expired access token",
    "revoked access token",
)

# Allowed reaction types per LinkedIn's documented enum.
_REACTION_TYPES = {
    "LIKE",
    "PRAISE",
    "EMPATHY",
    "INTEREST",
    "APPRECIATION",
    "MAYBE",
    "ENTERTAINMENT",
}


class LinkedIn(BaseConnector):
    """Connect to LinkedIn to post, comment, and react on the authenticated feed.

    Requires an OAuth 2.0 Bearer token passed as ``credentials``. The token
    must include scopes appropriate to your use:

    - ``openid profile email`` — for ``get_profile`` (OIDC userinfo).
    - ``w_member_social`` — for posting, deleting, commenting, reacting.
    - ``r_member_social`` — for reading own posts and comments.

    Tokens expire after 60 days. Expired tokens raise
    ``TokenExpiredError`` with a hint to regenerate via the LinkedIn
    Developer App console.

    DMs and mentions are NOT supported — they require LinkedIn Partner
    Program approval (a contract, not OAuth scopes). See README.
    """

    name = "linkedin"
    display_name = "LinkedIn"
    category = ConnectorCategory.SOCIAL
    protocol = ProtocolType.REST
    base_url = "https://api.linkedin.com"
    description = (
        "Post to your LinkedIn personal feed, comment on posts, react. "
        "BYOK OAuth 2.0 access tokens (60-day expiry). DMs and mentions "
        "are not supported (LinkedIn Partner Program required)."
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
                "X-Restli-Protocol-Version": "2.0.0",
                "LinkedIn-Version": _LINKEDIN_VERSION,
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
        extra_headers: Optional[dict[str, str]] = None,
    ) -> Any:
        """Execute an HTTP request against the LinkedIn API.

        Args:
            method: HTTP method (GET, POST, DELETE).
            path: API path (e.g. ``/v2/userinfo`` or ``/rest/posts``).
            params: URL query parameters.
            json_body: JSON request body.
            extra_headers: Additional headers (merged over defaults).

        Returns:
            The parsed JSON response. ``None`` for empty/204 responses.

        Raises:
            TokenExpiredError: 401 with EXPIRED/REVOKED token markers.
            InvalidCredentialsError: 401 (other reasons).
            PermissionDeniedError: 403 (scope/partner restriction).
            NotFoundError: 404.
            ValidationError: 400/422.
            RateLimitError: 429.
            ServerError: 5xx.
            APIError: Any other non-2xx response.
        """
        kwargs: dict[str, Any] = {}
        if params:
            kwargs["params"] = params
        if json_body is not None:
            kwargs["json"] = json_body
        if extra_headers:
            kwargs["headers"] = extra_headers

        response = await self._client.request(method, path, **kwargs)
        status = response.status_code

        # 201 Created on POST often returns the created entity URN in headers
        # rather than a JSON body. We fall through to body parsing below.
        if status == 204:
            return None

        # Parse body (may be empty)
        try:
            body = response.json()
        except Exception:
            body = {}

        if 200 <= status < 300:
            # LinkedIn 201 responses include the created URN in the
            # 'x-restli-id' header. Surface it so create_* actions can use it.
            urn = response.headers.get("x-restli-id") or response.headers.get(
                "X-RestLi-Id"
            )
            if status == 201 and urn and isinstance(body, dict):
                body = dict(body)  # mutate a copy
                body.setdefault("id", urn)
            return body

        # Error mapping — LinkedIn error bodies vary in shape:
        #   v2:    {"message": "...", "status": 401, "code": "..."}
        #   /rest: {"message": "...", "status": 401, "serviceErrorCode": ...}
        error_msg = (
            body.get("message")
            if isinstance(body, dict)
            else None
        ) or f"LinkedIn API error (HTTP {status})"
        raw_text = response.text or ""
        details = {"linkedin_response": body, "http_status": status}

        if status == 401:
            haystack = (raw_text + " " + (error_msg or "")).upper()
            is_expired = any(m.upper() in haystack for m in _EXPIRED_TOKEN_MARKERS)
            if is_expired:
                raise TokenExpiredError(
                    error_msg,
                    connector="linkedin",
                    action=path,
                    suggestion=(
                        "LinkedIn access tokens expire 60 days after issue. "
                        "Generate a new token at "
                        "https://www.linkedin.com/developers/apps and re-authenticate."
                    ),
                    details=details,
                )
            raise InvalidCredentialsError(
                error_msg,
                connector="linkedin",
                action=path,
                suggestion=(
                    "Verify the OAuth 2.0 token is valid and has the required "
                    "scopes (e.g. w_member_social, r_member_social, openid). "
                    "See https://www.linkedin.com/developers/apps."
                ),
                details=details,
            )

        if status == 403:
            raise PermissionDeniedError(
                error_msg,
                connector="linkedin",
                action=path,
                suggestion=(
                    "The token lacks scope for this action, OR this endpoint "
                    "requires LinkedIn Partner Program approval (DMs, "
                    "Notifications, Marketing APIs). See "
                    "https://learn.microsoft.com/linkedin/."
                ),
                details=details,
            )

        if status == 404:
            raise NotFoundError(
                error_msg,
                connector="linkedin",
                action=path,
                details=details,
            )

        if status in (400, 422):
            raise ValidationError(
                error_msg,
                connector="linkedin",
                action=path,
                details=details,
            )

        if status == 429:
            retry_after = float(response.headers.get("Retry-After", "60"))
            raise RateLimitError(
                error_msg,
                connector="linkedin",
                action=path,
                retry_after_seconds=retry_after,
                details=details,
            )

        if status >= 500:
            raise ServerError(
                error_msg,
                connector="linkedin",
                action=path,
                details=details,
                upstream_status=status,
            )

        raise APIError(
            error_msg,
            connector="linkedin",
            action=path,
            details=details,
            upstream_status=status,
        )

    @staticmethod
    def _person_urn_from_sub(sub: str) -> str:
        """Build a person URN from the OIDC ``sub`` claim.

        LinkedIn's OIDC ``sub`` value is the same opaque ID used in
        ``urn:li:person:{sub}``. Most write APIs require the full URN.
        """
        if sub.startswith("urn:li:person:"):
            return sub
        return f"urn:li:person:{sub}"

    # ======================================================================
    # PROFILE  (uses /v2/userinfo — OIDC)
    # ======================================================================

    @action("Get the authenticated LinkedIn user's profile (OIDC userinfo)")
    async def get_profile(self) -> LinkedInProfile:
        """Get the authenticated user's profile via the OIDC userinfo endpoint.

        Required scopes: ``openid profile email``. Most reliable way to
        identify the authenticated user — works regardless of which other
        scopes the token holds.

        The returned ``sub`` field is the user's opaque ID; pass it through
        ``urn:li:person:{sub}`` when calling write APIs that need an author URN.

        Returns:
            The authenticated user's profile.
        """
        body = await self._request("GET", "/v2/userinfo")
        return LinkedInProfile.model_validate(body)

    # ======================================================================
    # POSTS  (uses /rest/posts — newer)
    # ======================================================================

    @action(
        "Publish a post to the authenticated user's LinkedIn feed",
        dangerous=True,
    )
    async def create_post(
        self,
        author: str,
        commentary: str,
        visibility: str = "PUBLIC",
        lifecycle_state: str = "PUBLISHED",
        content: Optional[dict[str, Any]] = None,
    ) -> LinkedInPost:
        """Publish a post via the ``/rest/posts`` API (LinkedIn-Version 202506).

        Args:
            author: The author URN (e.g. ``urn:li:person:abc123``).
                Use ``get_profile()`` then ``urn:li:person:{sub}``.
            commentary: The post text body (supports plain text + LinkedIn
                mention/hashtag markup).
            visibility: ``"PUBLIC"`` (default), ``"CONNECTIONS"``, or
                ``"LOGGED_IN"``.
            lifecycle_state: ``"PUBLISHED"`` (default) or ``"DRAFT"``.
                Sent to LinkedIn as the ``lifecycleState`` field.
            content: Optional content block (article, image, poll, etc.).
                See LinkedIn /rest/posts docs for shape. Omit for a
                text-only post.

        Returns:
            The created post (with URN).
        """
        # LinkedIn's wire format is camelCase; Python params are snake_case.
        payload: dict[str, Any] = {
            "author": author,
            "commentary": commentary,
            "visibility": visibility,
            "lifecycleState": lifecycle_state,
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "isReshareDisabledByAuthor": False,
        }
        if content:
            payload["content"] = content

        body = await self._request("POST", "/rest/posts", json_body=payload)
        # The body may be empty; the URN comes from the x-restli-id header,
        # which _request() folds into body['id'].
        if not isinstance(body, dict):
            body = {}
        body.setdefault("author", author)
        body.setdefault("commentary", commentary)
        body.setdefault("visibility", visibility)
        body.setdefault("lifecycleState", lifecycle_state)
        # Pydantic V2 with populate_by_name=True respects camelCase aliases
        # AND ignores unknown fields by default — no manual filter needed.
        return LinkedInPost.model_validate(body)

    @action(
        "Delete a LinkedIn post you authored",
        dangerous=True,
    )
    async def delete_post(self, urn: str) -> None:
        """Delete a post via ``/rest/posts/{urn}``.

        Only the post's author can delete it.

        Args:
            urn: The post URN (e.g. ``urn:li:share:7012345``).
        """
        encoded = url_quote(urn, safe="")
        await self._request("DELETE", f"/rest/posts/{encoded}")
        return None

    @action("Get a single LinkedIn post by URN")
    async def get_post(self, urn: str) -> LinkedInPost:
        """Fetch a post via ``/rest/posts/{urn}``.

        Args:
            urn: The post URN.

        Returns:
            The post.
        """
        encoded = url_quote(urn, safe="")
        body = await self._request("GET", f"/rest/posts/{encoded}")
        return LinkedInPost.model_validate(body)

    @action("List the authenticated user's recent posts")
    async def list_my_posts(
        self,
        author: str,
        count: int = 10,
        start: int = 0,
    ) -> PaginatedList[LinkedInPost]:
        """List posts authored by ``author`` via ``/rest/posts``.

        LinkedIn paginates with ``start``+``count`` (offset-based).
        ``has_more`` is set when the returned page is full.

        Args:
            author: The author URN to filter by (the authenticated user's
                URN, from ``get_profile()``).
            count: Page size (1..100). Defaults to 10.
            start: Zero-based offset for pagination. Defaults to 0.

        Returns:
            A page of posts.
        """
        count = max(1, min(int(count), 100))
        params = {
            "q": "author",
            "author": author,
            "count": count,
            "start": max(0, int(start)),
        }
        body = await self._request("GET", "/rest/posts", params=params)
        elements = body.get("elements", []) if isinstance(body, dict) else []
        items = [LinkedInPost.model_validate(p) for p in elements]
        # If the page is full we assume more results may exist; LinkedIn
        # also exposes a paging.total when available.
        paging = (body.get("paging") or {}) if isinstance(body, dict) else {}
        total = paging.get("total")
        has_more = (
            (total is not None and (start + len(items)) < total)
            or len(items) >= count
        )
        return PaginatedList(
            items=items,
            page_state=PageState(
                offset=start + len(items) if has_more else None,
                has_more=has_more,
                total_count=total,
            ),
        )

    # ======================================================================
    # COMMENTS  (uses /v2/socialActions/{urn}/comments — legacy v2)
    # ======================================================================

    @action(
        "Post a comment on a LinkedIn post",
        dangerous=True,
    )
    async def create_comment(
        self,
        post_urn: str,
        actor: str,
        text: str,
    ) -> LinkedInComment:
        """Comment on a post via ``/v2/socialActions/{urn}/comments``.

        Args:
            post_urn: The post URN to comment on (e.g. ``urn:li:share:123``).
            actor: The commenter's URN (typically ``urn:li:person:{sub}``).
            text: The comment body (plain text + mention markup).

        Returns:
            The created comment.
        """
        encoded = url_quote(post_urn, safe="")
        payload = {
            "actor": actor,
            "object": post_urn,
            "message": {"text": text},
        }
        body = await self._request(
            "POST",
            f"/v2/socialActions/{encoded}/comments",
            json_body=payload,
        )
        return LinkedInComment.model_validate(body)

    @action("List comments on a LinkedIn post")
    async def list_comments(
        self,
        post_urn: str,
        count: int = 10,
        start: int = 0,
    ) -> PaginatedList[LinkedInComment]:
        """List comments on a post via ``/v2/socialActions/{urn}/comments``.

        Args:
            post_urn: The post URN whose comments to list.
            count: Page size (1..100). Defaults to 10.
            start: Zero-based offset for pagination.

        Returns:
            A page of comments.
        """
        encoded = url_quote(post_urn, safe="")
        count = max(1, min(int(count), 100))
        params = {"count": count, "start": max(0, int(start))}
        body = await self._request(
            "GET",
            f"/v2/socialActions/{encoded}/comments",
            params=params,
        )
        elements = body.get("elements", []) if isinstance(body, dict) else []
        items = [LinkedInComment.model_validate(c) for c in elements]
        paging = (body.get("paging") or {}) if isinstance(body, dict) else {}
        total = paging.get("total")
        has_more = (
            (total is not None and (start + len(items)) < total)
            or len(items) >= count
        )
        return PaginatedList(
            items=items,
            page_state=PageState(
                offset=start + len(items) if has_more else None,
                has_more=has_more,
                total_count=total,
            ),
        )

    # ======================================================================
    # REACTIONS  (uses /v2/reactions — legacy v2)
    # ======================================================================

    @action(
        "React to a LinkedIn post (LIKE / PRAISE / EMPATHY / INTEREST / "
        "APPRECIATION / MAYBE / ENTERTAINMENT)",
        dangerous=True,
    )
    async def react_to_post(
        self,
        post_urn: str,
        actor: str,
        reaction_type: str = "LIKE",
    ) -> None:
        """Add a reaction to a post via ``/v2/reactions``.

        Args:
            post_urn: The post URN (the reaction target).
            actor: The reactor's URN (typically ``urn:li:person:{sub}``).
            reaction_type: One of ``LIKE`` (default), ``PRAISE``, ``EMPATHY``,
                ``INTEREST``, ``APPRECIATION``, ``MAYBE``, ``ENTERTAINMENT``.

        Raises:
            ValidationError: If ``reaction_type`` is not in the documented set.
        """
        rt = reaction_type.upper()
        if rt not in _REACTION_TYPES:
            raise ValidationError(
                f"Unknown reaction_type {reaction_type!r}. "
                f"Allowed: {sorted(_REACTION_TYPES)}",
                connector="linkedin",
                action="/v2/reactions",
            )
        payload = {
            "root": post_urn,
            "reactionType": rt,
            "actor": actor,
        }
        await self._request("POST", "/v2/reactions", json_body=payload)
        return None
