"""LinkedIn connector — post, comment, and react on the authenticated user's feed.

Uses the LinkedIn REST API with OAuth 2.0 Bearer token authentication.

Endpoint surfaces
-----------------
This connector calls three LinkedIn API surfaces, all under
``api.linkedin.com``:

- ``/rest/posts`` (Versioned API) — Posts API for create/get/list/delete.
  Requires the ``Linkedin-Version`` header (we pin ``202604``, the latest
  in the documented support range as of 2026-04). Replaces the legacy
  ``/v2/ugcPosts`` API.
  Docs: https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api

- ``/rest/socialActions/{urn}/comments`` (Versioned API) — Comments API.
  Same ``Linkedin-Version`` header. Same wire-protocol headers
  (``X-Restli-Protocol-Version: 2.0.0``).
  Docs: https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/comments-api

- ``/rest/reactions`` (Versioned API) — Reactions API. Note that ``actor``
  is a **query parameter**, not a body field, on POST.
  Docs: https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/reactions-api

- ``/v2/userinfo`` (OIDC) — for fetching the authenticated user's identity.
  Standard OIDC userinfo endpoint, no version header needed.
  Docs: https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/sign-in-with-linkedin-v2

Scope tiers
-----------
LinkedIn splits read and write scopes:

- WRITE scopes (open via standard "Share on LinkedIn" + "Sign In with LinkedIn"
  products, available to any developer):
  ``openid profile email`` — get_profile.
  ``w_member_social`` — create_post, delete_post, create_comment, react_to_post.

- READ scope (RESTRICTED — granted to LinkedIn-approved developers only):
  ``r_member_social`` — get_post, list_my_posts, list_comments.

Standard apps without ``r_member_social`` will get HTTP 403 ``ACCESS_DENIED``
on the read endpoints, mapped here to ``PermissionDeniedError`` with a clear
hint.

Out of scope (see README "Not Supported"):
- DMs / Messaging API — requires LinkedIn Partner Program approval (a
  contract with LinkedIn, not OAuth scopes). Not BYOK-accessible.
- Mentions / Notifications — partner-only Notifications API.
- Image / video / document uploads — require a separate multi-step
  upload flow (Images API / Videos API / Documents API) not implemented
  here. Use ``content`` parameter on ``create_post`` with a pre-uploaded
  asset URN if you have one.
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
# and remain available for ~12 months after release. As of 2026-04, the
# supported range is 202505..202604; we target 202604 as the latest.
# Source: https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api
_LINKEDIN_VERSION = "202604"

# Substrings in a 401 body indicating the token has expired or is missing.
# Per LinkedIn's documented error codes, EMPTY_ACCESS_TOKEN is the value
# returned when the token is missing entirely; EXPIRED/REVOKED indicate
# a stale token that needs regeneration.
_EXPIRED_TOKEN_MARKERS = (
    "EXPIRED_ACCESS_TOKEN",
    "REVOKED_ACCESS_TOKEN",
    "EMPTY_ACCESS_TOKEN",
    "expired access token",
    "revoked access token",
)

# Allowed reaction types per LinkedIn's documented Reactions API enum.
# NOTE: MAYBE ("Curious" in UI) is deprecated since version 202307 and
# will return 400 if sent — omitted here.
# Source: https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/reactions-api
_REACTION_TYPES = {
    "LIKE",          # "Like"
    "PRAISE",        # "Celebrate"
    "EMPATHY",       # "Love"
    "INTEREST",      # "Insightful"
    "APPRECIATION",  # "Support"
    "ENTERTAINMENT", # "Funny"
}


class LinkedIn(BaseConnector):
    """Connect to LinkedIn to post, comment, and react on the authenticated feed.

    Requires an OAuth 2.0 Bearer token passed as ``credentials``. The token
    must include scopes appropriate to your use:

    - ``openid profile email`` — for ``get_profile`` (OIDC userinfo).
      Granted by the **Sign in with LinkedIn using OpenID Connect** product.
    - ``w_member_social`` — for ``create_post``, ``delete_post``,
      ``create_comment``, ``react_to_post``.
      Granted by the **Share on LinkedIn** product.
    - ``r_member_social`` — for ``get_post``, ``list_my_posts``,
      ``list_comments``. **RESTRICTED**: this scope is granted to
      approved developers only. Standard apps cannot call read endpoints.

    Tokens expire after 60 days (default for LinkedIn member tokens).
    Missing/expired tokens raise ``TokenExpiredError`` with a hint to
    regenerate via the LinkedIn Developer App console.

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
        "BYOK OAuth 2.0 access tokens (60-day expiry). Read endpoints "
        "(get_post, list_my_posts, list_comments) require the restricted "
        "r_member_social scope (approved developers only). DMs and "
        "mentions require LinkedIn Partner Program approval."
    )
    # Standard Share-on-LinkedIn rate limit is ~150 calls/day per member
    # (UTC daily window). This advisory limit is intentionally well under
    # that — server-side enforcement is the source of truth.
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
                # Header name canonicalization per LinkedIn docs:
                # https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api
                "Linkedin-Version": _LINKEDIN_VERSION,
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
        """Publish a post via the LinkedIn Posts API.

        Endpoint: ``POST /rest/posts`` (Linkedin-Version 202604).
        Required scope: ``w_member_social`` (granted by the "Share on
        LinkedIn" product). Subject to LinkedIn's daily share quota.

        Args:
            author: The author URN (e.g. ``urn:li:person:abc123``).
                Use ``get_profile()`` then build ``urn:li:person:{sub}``.
                For organization posts, use ``urn:li:organization:{id}``
                — note that organization posting requires the
                ``w_organization_social`` scope and an admin role on the
                page.
            commentary: The post text body. Supports LinkedIn's "little"
                text format with mention markup like
                ``"Hello @[Name](urn:li:person:abc)"`` and hashtags
                like ``#topic``.
            visibility: ``"PUBLIC"`` (default — anyone on LinkedIn) or
                ``"CONNECTIONS"`` (1st-degree connections only).
            lifecycle_state: ``"PUBLISHED"`` (default — visible
                immediately) or ``"DRAFT"``. Sent to LinkedIn as
                ``lifecycleState``.
            content: Optional content block. Examples:
                - Article:
                  ``{"article": {"source": "https://...",
                  "thumbnail": "urn:li:image:...",
                  "title": "...", "description": "..."}}``
                - Media (image/video):
                  ``{"media": {"id": "urn:li:image:...", "title": "..."}}``
                Image/video URNs come from the Images/Videos APIs which
                require a separate upload flow not implemented here.
                Omit for a text-only post.

        Returns:
            The created post. The URN is exposed via ``post.id``,
            populated from the LinkedIn ``x-restli-id`` response header.
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
        """Delete a post via the LinkedIn Posts API.

        Endpoint: ``DELETE /rest/posts/{encoded urn}``.
        Required scope: ``w_member_social``. Only the post's author can
        delete it. Returns 204 on success; deletion is idempotent
        (deleting an already-deleted post also returns 204).

        Args:
            urn: The post URN (e.g. ``urn:li:share:7012345`` or
                ``urn:li:ugcPost:...``).
        """
        encoded = url_quote(urn, safe="")
        await self._request("DELETE", f"/rest/posts/{encoded}")
        return None

    @action("Get a single LinkedIn post by URN (RESTRICTED scope)")
    async def get_post(self, urn: str) -> LinkedInPost:
        """Fetch a post via the LinkedIn Posts API.

        Endpoint: ``GET /rest/posts/{encoded urn}``.
        Required scope: ``r_member_social`` — **RESTRICTED**, granted
        to LinkedIn-approved developers only. Standard "Share on
        LinkedIn" apps will get a 403 ``ACCESS_DENIED`` here, mapped
        to ``PermissionDeniedError`` with a clear hint.

        Args:
            urn: The post URN.

        Returns:
            The post.
        """
        encoded = url_quote(urn, safe="")
        body = await self._request("GET", f"/rest/posts/{encoded}")
        return LinkedInPost.model_validate(body)

    @action("List the authenticated user's recent posts (RESTRICTED scope)")
    async def list_my_posts(
        self,
        author: str,
        count: int = 10,
        start: int = 0,
    ) -> PaginatedList[LinkedInPost]:
        """List posts authored by ``author`` via the LinkedIn Posts API.

        Endpoint: ``GET /rest/posts?q=author&author={urn}``.
        Required scope: ``r_member_social`` — **RESTRICTED**, granted to
        LinkedIn-approved developers only. Standard "Share on LinkedIn"
        apps will get a 403 ``ACCESS_DENIED`` here, mapped to
        ``PermissionDeniedError`` with a clear hint.

        LinkedIn paginates with ``start``+``count`` (offset-based).
        ``has_more`` is set when the returned page is full or when
        the server-reported ``paging.total`` indicates more remain.

        Args:
            author: The author URN to filter by (the authenticated user's
                URN, derived from ``get_profile()``).
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
    # COMMENTS  (uses /rest/socialActions/{urn}/comments — Versioned API)
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
        """Comment on a post via the LinkedIn Comments API.

        Endpoint: ``POST /rest/socialActions/{encoded post_urn}/comments``.
        Required scope: ``w_member_social`` (Share on LinkedIn product
        grants this — same scope used for posting).

        Args:
            post_urn: The post URN to comment on (e.g.
                ``urn:li:share:7012345`` or ``urn:li:ugcPost:...``).
            actor: The commenter's URN (typically derived from
                ``get_profile()`` as ``urn:li:person:{sub}``).
            text: The comment body. Supports LinkedIn's text format
                with mention markup.

        Returns:
            The created comment. The composite comment URN is in
            ``comment.id`` (or via the response header).
        """
        encoded = url_quote(post_urn, safe="")
        payload = {
            "actor": actor,
            "object": post_urn,
            "message": {"text": text},
        }
        body = await self._request(
            "POST",
            f"/rest/socialActions/{encoded}/comments",
            json_body=payload,
        )
        return LinkedInComment.model_validate(body)

    @action("List comments on a LinkedIn post (RESTRICTED scope)")
    async def list_comments(
        self,
        post_urn: str,
        count: int = 10,
        start: int = 0,
    ) -> PaginatedList[LinkedInComment]:
        """List comments on a post via the LinkedIn Comments API.

        Endpoint: ``GET /rest/socialActions/{encoded post_urn}/comments``.
        Required scope: ``r_member_social`` — **RESTRICTED**, granted to
        LinkedIn-approved developers only. Standard "Share on LinkedIn"
        apps will get a 403 ``ACCESS_DENIED`` here, mapped to
        ``PermissionDeniedError`` with a clear hint.

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
            f"/rest/socialActions/{encoded}/comments",
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
    # REACTIONS  (uses /rest/reactions — Versioned API)
    # ======================================================================

    @action(
        "React to a LinkedIn post (LIKE / PRAISE / EMPATHY / INTEREST / "
        "APPRECIATION / ENTERTAINMENT)",
        dangerous=True,
    )
    async def react_to_post(
        self,
        post_urn: str,
        actor: str,
        reaction_type: str = "LIKE",
    ) -> None:
        """Add a reaction to a post via the LinkedIn Reactions API.

        Endpoint: ``POST /rest/reactions?actor={encoded actor URN}``.
        Required scope: ``w_member_social``. Note that LinkedIn's
        Reactions API takes ``actor`` as a **query parameter**, not a
        body field. The body carries only ``root`` (the entity being
        reacted to) and ``reactionType``.

        Args:
            post_urn: The reaction target URN. Can be a share URN, ugcPost
                URN, activity URN, or comment URN (composite form).
            actor: The reactor's URN (typically ``urn:li:person:{sub}``,
                derived from ``get_profile()``). LinkedIn returns 201
                with the new reaction's composite URN.
            reaction_type: One of ``LIKE`` (default — "Like" in UI),
                ``PRAISE`` ("Celebrate"), ``EMPATHY`` ("Love"),
                ``INTEREST`` ("Insightful"), ``APPRECIATION``
                ("Support"), or ``ENTERTAINMENT`` ("Funny").
                The ``MAYBE`` reaction (formerly "Curious") was
                deprecated in version 202307 and is no longer accepted.

        Raises:
            ValidationError: If ``reaction_type`` is not in the
                supported set.
        """
        rt = reaction_type.upper()
        if rt not in _REACTION_TYPES:
            raise ValidationError(
                f"Unknown reaction_type {reaction_type!r}. "
                f"Allowed: {sorted(_REACTION_TYPES)} "
                f"(MAYBE was deprecated in LinkedIn-Version 202307).",
                connector="linkedin",
                action="/rest/reactions",
            )
        # actor goes in the QUERY STRING per LinkedIn's spec, not the body.
        encoded_actor = url_quote(actor, safe="")
        payload = {
            "root": post_urn,
            "reactionType": rt,
        }
        await self._request(
            "POST",
            f"/rest/reactions?actor={encoded_actor}",
            json_body=payload,
        )
        return None
