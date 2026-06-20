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

Scope tiers (live-verified against the real API, 2026-06-20)
------------------------------------------------------------
LinkedIn's public docs claim ``w_member_social`` covers posts, comments,
and reactions. **Live testing proves only a subset is actually available
to standard BYOK developers** — comments, reactions, and every read action
are additionally gated behind the LinkedIn Partner Program and return
HTTP 403 ``partnerApi*`` regardless of OAuth scope. Re-verified end-to-end
on 2026-06-20 with a real member token (scope
``openid profile email w_member_social``): the 3 BYOK actions round-tripped
(create → delete) and the 5 gated actions each returned the exact 403 below.

WORKS for any developer with "Sign In with LinkedIn using OpenID Connect"
+ "Share on LinkedIn" products enabled (default self-serve):
  - ``get_profile``    — OIDC ``/v2/userinfo`` (``openid profile email``)
  - ``create_post``    — ``POST /rest/posts``        (``w_member_social``)
  - ``delete_post``    — ``DELETE /rest/posts/{urn}`` (``w_member_social``)

REQUIRES LinkedIn Partner Program approval — standard tokens get HTTP 403
with these exact ``serviceErrorCode`` partner gates (observed 2026-06-20):
  - ``get_post``       — ``partnerApiPostsExternal.GET``
  - ``list_my_posts``  — ``partnerApiPostsExternal.FINDER-author``
  - ``list_comments``  — ``partnerApiSocialActions.GET_ALL``
  - ``create_comment`` — ``partnerApiSocialActions.CREATE``
  - ``react_to_post``  — ``partnerApiReactions.CREATE``

Note: the read actions (``get_post``, ``list_my_posts``, ``list_comments``)
were previously documented as ``r_member_social``-restricted; live testing
2026-06-20 shows LinkedIn now gates them through the same ``partnerApi*``
entitlement as the write social actions. The caller-visible behaviour is
unchanged — all five raise ``PermissionDeniedError`` with a hint pointing
at the Partner Program.

All partner-gated endpoints are still exposed by this connector — they
return ``PermissionDeniedError`` with a hint pointing at the LinkedIn
Partner Program when called without approval. This matches the X-tier
pattern where the connector reaches the full API surface and lets X's
server-side enforcement decide what the user's account can do.

Out of scope (see README "Not Supported"):
- DMs / Messaging API — requires LinkedIn Partner Program approval (a
  contract with LinkedIn, not OAuth scopes). Not BYOK-accessible.
- Mentions / Notifications — partner-only Notifications API.
- Image / video / document uploads — implemented via ``upload_image`` /
  ``upload_document`` / ``upload_video`` (the Images / Documents / Videos
  multi-step upload flow on the versioned ``/rest/*`` gateway), then attach
  the returned asset URN with ``create_media_post`` (or
  ``create_post(content=...)``). Member-owned uploads use the self-serve
  ``w_member_social`` scope. Doc-verified against LinkedIn's canonical
  Images/Documents/Videos API docs (2026-06); not yet live-exercised.
"""

from __future__ import annotations

import logging
import pathlib
from typing import Any, Optional
from urllib.parse import quote as url_quote
from urllib.parse import urlparse

import httpx

from toolsconnector.connectors._helpers import parse_retry_after, redact_credentials
from toolsconnector.errors import (
    APIError,
    InvalidCredentialsError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    TokenExpiredError,
    TransportError,
    ValidationError,
)
from toolsconnector.errors import (
    ConnectionError as ToolsConnectorConnectionError,
)
from toolsconnector.errors import (
    TimeoutError as ToolsConnectorTimeoutError,
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

# Substrings in a 401 body indicating the token has EXPIRED/REVOKED (a stale
# token that needs regeneration) → TokenExpiredError. A *missing* token
# (EMPTY_ACCESS_TOKEN) is deliberately NOT here: that's a credential-construction
# problem, so it falls through to InvalidCredentialsError, whose hint ("check the
# token is valid + has the right scopes") is the correct remediation.
_EXPIRED_TOKEN_MARKERS = (
    "EXPIRED_ACCESS_TOKEN",
    "REVOKED_ACCESS_TOKEN",
    "expired access token",
    "revoked access token",
)

# Allowed reaction types per LinkedIn's documented Reactions API enum.
# NOTE: MAYBE ("Curious" in UI) is deprecated since version 202307 and
# will return 400 if sent — omitted here.
# Source: https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/reactions-api
_REACTION_TYPES = {
    "LIKE",  # "Like"
    "PRAISE",  # "Celebrate"
    "EMPATHY",  # "Love"
    "INTEREST",  # "Insightful"
    "APPRECIATION",  # "Support"
    "ENTERTAINMENT",  # "Funny"
}


class LinkedIn(BaseConnector):
    """Connect to LinkedIn to post, comment, and react on the authenticated feed.

    Requires an OAuth 2.0 Bearer token passed as ``credentials``.

    Scopes you can request via the standard self-serve products:

    - ``openid profile email`` (Sign In with LinkedIn using OpenID Connect)
      → ``get_profile``.
    - ``w_member_social`` (Share on LinkedIn product)
      → ``create_post``, ``delete_post``, and media uploads
      (``upload_image`` / ``upload_document`` / ``upload_video`` +
      ``create_media_post``).

    Everything else (``create_comment``, ``react_to_post``,
    ``list_comments``, ``get_post``, ``list_my_posts``) requires
    **LinkedIn Partner Program approval**. Standard self-serve tokens
    hit ``partnerApi*`` gating and get HTTP 403, which this connector
    maps to ``PermissionDeniedError`` with a clear hint. This is a
    LinkedIn commercial policy — documented here based on LIVE testing
    against the real API, not inferred from LinkedIn's public docs
    (which incorrectly imply ``w_member_social`` is sufficient).

    Tokens expire after 60 days (default for LinkedIn member tokens).
    Missing/expired tokens raise ``TokenExpiredError`` with a hint to
    regenerate via the LinkedIn Developer App console.

    DMs and mentions also require Partner Program approval and are
    not included at all.
    """

    name = "linkedin"
    display_name = "LinkedIn"
    category = ConnectorCategory.SOCIAL
    protocol = ProtocolType.REST
    base_url = "https://api.linkedin.com"
    # Tier 1 — live-verified 2026-06-20 against the real API with a member
    # token: get_profile / create_post / delete_post round-tripped; the 5
    # partner-gated actions each returned their documented ``partnerApi*`` 403.
    verification_status = "live"
    description = (
        "Post to your LinkedIn personal feed (incl. image/video/document "
        "uploads), comment, and react. BYOK "
        "OAuth 2.0 access tokens (60-day expiry). The 3 self-serve actions "
        "(get_profile, create_post, delete_post) are live-verified; reads "
        "(get_post, list_my_posts, list_comments), comments, and reactions "
        "require LinkedIn Partner Program approval and return 403 on "
        "standard tokens. DMs and mentions are partner-only too."
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

        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise ToolsConnectorTimeoutError(
                f"LinkedIn API request timed out after {self._timeout}s",
                connector="linkedin",
                details={"method": method, "path": path, "underlying": type(exc).__name__},
            ) from exc
        except httpx.ConnectError as exc:
            raise ToolsConnectorConnectionError(
                "Could not connect to the LinkedIn API at api.linkedin.com",
                connector="linkedin",
                details={"method": method, "path": path, "underlying": str(exc)},
            ) from exc
        except httpx.TransportError as exc:
            raise TransportError(
                f"LinkedIn API transport error: {type(exc).__name__}",
                connector="linkedin",
                details={"method": method, "path": path, "underlying": str(exc)},
            ) from exc
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
            urn = response.headers.get("x-restli-id") or response.headers.get("X-RestLi-Id")
            if status == 201 and urn and isinstance(body, dict):
                body = dict(body)  # mutate a copy
                body.setdefault("id", urn)
            return body

        # Error mapping — LinkedIn error bodies vary in shape:
        #   v2:    {"message": "...", "status": 401, "code": "..."}
        #   /rest: {"message": "...", "status": 401, "serviceErrorCode": ...}
        error_msg = (
            body.get("message") if isinstance(body, dict) else None
        ) or f"LinkedIn API error (HTTP {status})"
        raw_text = response.text or ""
        # Redact any reflected credential (e.g. a Bearer token echoed in the
        # error body) and truncate before storing on the exception — the same
        # defense-in-depth the shared raise_typed_for_status applies fleet-wide,
        # so a token in an error envelope can't leak into logs via err.details.
        error_msg = redact_credentials(error_msg)
        details = {"body_preview": redact_credentials(raw_text[:500]), "http_status": status}

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
            # parse_retry_after tolerates a non-numeric (e.g. HTTP-date) header
            # by returning None instead of crashing the error path with a
            # ValueError; fall back to the connector default in that case.
            retry_after = parse_retry_after(response.headers.get("Retry-After"))
            raise RateLimitError(
                error_msg,
                connector="linkedin",
                action=path,
                retry_after_seconds=retry_after if retry_after is not None else 60.0,
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

    @action("Get a single LinkedIn post by URN (PARTNER APPROVAL REQUIRED)")
    async def get_post(self, urn: str) -> LinkedInPost:
        """Fetch a post via the LinkedIn Posts API.

        Endpoint: ``GET /rest/posts/{encoded urn}``.
        **Requires LinkedIn Partner Program approval.** Live testing
        2026-06-20 shows standard "Share on LinkedIn" tokens get HTTP 403
        ``partnerApiPostsExternal.GET`` here, mapped to
        ``PermissionDeniedError`` with a hint pointing at the Partner
        Program. (Previously documented as ``r_member_social``-gated.)

        Args:
            urn: The post URN.

        Returns:
            The post.
        """
        encoded = url_quote(urn, safe="")
        body = await self._request("GET", f"/rest/posts/{encoded}")
        return LinkedInPost.model_validate(body)

    @action("List the authenticated user's recent posts (PARTNER APPROVAL REQUIRED)")
    async def list_my_posts(
        self,
        author: str,
        count: int = 10,
        start: int = 0,
    ) -> PaginatedList[LinkedInPost]:
        """List posts authored by ``author`` via the LinkedIn Posts API.

        Endpoint: ``GET /rest/posts?q=author&author={urn}``.
        **Requires LinkedIn Partner Program approval.** Live testing
        2026-06-20 shows standard "Share on LinkedIn" tokens get HTTP 403
        ``partnerApiPostsExternal.FINDER-author`` here, mapped to
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
        # `total`, when LinkedIn reports it, is authoritative — fall back to the
        # page-full heuristic only when it's absent, so a full final page that
        # exactly exhausts `total` doesn't over-report has_more (wasted fetch).
        has_more = (start + len(items)) < total if total is not None else len(items) >= count
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
        "Post a comment on a LinkedIn post (PARTNER APPROVAL REQUIRED)",
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

        Required scope (per LinkedIn public docs): ``w_member_social``.
        However, **live testing 2026-04 shows this endpoint is gated
        behind the LinkedIn Partner Program** (partnerApiSocialActions).
        Standard self-serve tokens return 403 here, mapped to
        ``PermissionDeniedError`` with a hint pointing at the Partner
        Program.

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

    @action("List comments on a LinkedIn post (PARTNER APPROVAL REQUIRED)")
    async def list_comments(
        self,
        post_urn: str,
        count: int = 10,
        start: int = 0,
    ) -> PaginatedList[LinkedInComment]:
        """List comments on a post via the LinkedIn Comments API.

        Endpoint: ``GET /rest/socialActions/{encoded post_urn}/comments``.
        **Requires LinkedIn Partner Program approval.** Live testing
        2026-06-20 shows standard "Share on LinkedIn" tokens get HTTP 403
        ``partnerApiSocialActions.GET_ALL`` here, mapped to
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
        # `total`, when LinkedIn reports it, is authoritative — fall back to the
        # page-full heuristic only when it's absent, so a full final page that
        # exactly exhausts `total` doesn't over-report has_more (wasted fetch).
        has_more = (start + len(items)) < total if total is not None else len(items) >= count
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
        "React to a LinkedIn post (PARTNER APPROVAL REQUIRED) — "
        "LIKE / PRAISE / EMPATHY / INTEREST / APPRECIATION / ENTERTAINMENT",
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

        Required scope (per LinkedIn public docs): ``w_member_social``.
        However, **live testing 2026-04 shows this endpoint is gated
        behind the LinkedIn Partner Program** (partnerApiReactions).
        Standard self-serve tokens return 403 here, mapped to
        ``PermissionDeniedError`` with a hint pointing at the Partner
        Program.

        LinkedIn's Reactions API takes ``actor`` as a **query parameter**,
        not a body field. The body carries only ``root`` (the entity
        being reacted to) and ``reactionType``.

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

    # ======================================================================
    # MEDIA  (Images / Documents / Videos APIs — multi-step asset upload)
    #
    # Member-owned uploads (urn:li:person:) use the self-serve
    # ``w_member_social`` scope. Each upload registers the asset
    # (``initializeUpload``), PUTs the bytes to a pre-signed URL on
    # ``www.linkedin.com``, then (video only) finalizes with the part ETags.
    # The returned asset URN is attached to a post via ``create_media_post``.
    # ======================================================================

    # Allowed extensions + size ceilings per LinkedIn's documented media limits.
    # Min-size / pixel / page / duration bounds are left to server-side
    # enforcement (a clean 400); only the format + the ceiling (so we don't
    # upload a multi-GB file just to be rejected) are checked client-side.
    _IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".gif"})
    _DOC_EXTS = frozenset({".ppt", ".pptx", ".doc", ".docx", ".pdf"})
    _DOC_MAX_BYTES = 100 * 1024 * 1024
    _VIDEO_MAX_BYTES = 5 * 1024 * 1024 * 1024

    @staticmethod
    def _resolve_upload_path(file_path: str, allowed_exts: frozenset, *, kind: str) -> pathlib.Path:
        """Validate a local upload path: must exist and have an allowed extension."""
        path = pathlib.Path(file_path)
        if not path.is_file():
            raise ValidationError(
                f"file not found: {file_path!r}", connector="linkedin", action="upload"
            )
        if path.suffix.lower() not in allowed_exts:
            raise ValidationError(
                f"{kind} must be one of {sorted(allowed_exts)}, got {path.suffix or '(none)'!r}",
                connector="linkedin",
                action="upload",
            )
        return path

    @staticmethod
    def _unquote_etag(etag: str) -> str:
        """Strip an optional weak-validator prefix + a single matched quote pair."""
        etag = etag.strip()
        if etag.startswith("W/"):
            etag = etag[2:]
        if len(etag) >= 2 and etag[0] == '"' and etag[-1] == '"':
            etag = etag[1:-1]
        return etag

    async def _put_binary(self, upload_url: str, content: Any) -> Optional[str]:
        """PUT bytes (or a streaming file object) to a pre-signed URL; return the ETag.

        The upload URL is a pre-signed link on ``www.linkedin.com`` (not the API
        host). Hardening applied here:

        - **SSRF guard** — the URL must be ``https`` on a ``*.linkedin.com``
          host, and redirects are disabled, so a tampered ``initializeUpload``
          response can't redirect our bytes + Bearer token to an attacker host.
        - **Write phase uncapped** — the 30 s API timeout would abort a 100 MB
          document / large video part mid-stream; connect/read stay bounded.
        - **Typed transport errors** + credential redaction on any error body.
        """
        parsed = urlparse(upload_url)
        host = parsed.hostname or ""
        if parsed.scheme != "https" or not (
            host == "linkedin.com" or host.endswith(".linkedin.com")
        ):
            raise APIError(
                f"refusing to upload to a non-LinkedIn URL ({parsed.scheme}://{host})",
                connector="linkedin",
                action="upload",
            )
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout, write=None, pool=None),
                follow_redirects=False,
            ) as up:
                resp = await up.put(
                    upload_url,
                    content=content,
                    headers={
                        "Authorization": f"Bearer {self._credentials}",
                        "Content-Type": "application/octet-stream",
                    },
                )
        except httpx.TimeoutException as exc:
            raise ToolsConnectorTimeoutError(
                "LinkedIn media upload timed out",
                connector="linkedin",
                details={"underlying": type(exc).__name__},
            ) from exc
        except httpx.TransportError as exc:
            raise TransportError(
                f"LinkedIn media upload transport error: {type(exc).__name__}",
                connector="linkedin",
                details={"underlying": str(exc)},
            ) from exc
        if resp.status_code not in (200, 201):
            raise APIError(
                f"LinkedIn media upload failed (HTTP {resp.status_code})",
                connector="linkedin",
                action="upload",
                details={
                    "http_status": resp.status_code,
                    "body": redact_credentials(resp.text[:300]),
                },
                upstream_status=resp.status_code,
            )
        etag = resp.headers.get("etag") or resp.headers.get("ETag")
        return self._unquote_etag(etag) if etag else None

    @action("Upload an image and return its urn:li:image asset URN for posting")
    async def upload_image(self, owner: str, file_path: str) -> str:
        """Upload a local image (Images API) and return its asset URN.

        Two-step flow: ``POST /rest/images?action=initializeUpload`` →
        ``PUT`` the bytes to the returned upload URL. Required scope:
        ``w_member_social`` (a ``urn:li:person`` owner — yourself) or
        ``w_organization_social`` (a ``urn:li:organization`` page you admin).
        Formats: JPG, GIF (≤250 frames), PNG; under 36,152,320 pixels.

        Args:
            owner: The asset owner URN — ``urn:li:person:{id}`` or
                ``urn:li:organization:{id}``.
            file_path: Local path to the image file.

        Returns:
            The image asset URN (``urn:li:image:...``). Pass it to
            ``create_media_post`` (or
            ``create_post(content={"media": {"id": urn}})``).
        """
        path = self._resolve_upload_path(file_path, self._IMAGE_EXTS, kind="image")
        init = await self._request(
            "POST",
            "/rest/images?action=initializeUpload",
            json_body={"initializeUploadRequest": {"owner": owner}},
        )
        value = (init or {}).get("value") or {}
        upload_url = value.get("uploadUrl")
        image_urn = value.get("image")
        if not upload_url or not image_urn:
            raise APIError(
                "Images API initializeUpload returned no uploadUrl/image URN",
                connector="linkedin",
                action="/rest/images",
                details={"response": init},
            )
        await self._put_binary(upload_url, path.read_bytes())
        return image_urn

    @action("Upload a document (PDF/PPT/DOC) and return its urn:li:document URN")
    async def upload_document(self, owner: str, file_path: str) -> str:
        """Upload a local document (Documents API) and return its asset URN.

        ``POST /rest/documents?action=initializeUpload`` → ``PUT`` the bytes.
        Required scope: ``w_member_social`` / ``w_organization_social``.
        Formats: PPT, PPTX, DOC, DOCX, PDF; up to 100MB and 300 pages.

        Args:
            owner: ``urn:li:person:{id}`` or ``urn:li:organization:{id}``.
            file_path: Local path to the document file.

        Returns:
            The document asset URN (``urn:li:document:...``). Attach it with
            ``create_media_post(..., title="MyDeck.pdf")``.
        """
        path = self._resolve_upload_path(file_path, self._DOC_EXTS, kind="document")
        if path.stat().st_size > self._DOC_MAX_BYTES:
            raise ValidationError(
                "document exceeds LinkedIn's 100MB limit",
                connector="linkedin",
                action="upload",
            )
        init = await self._request(
            "POST",
            "/rest/documents?action=initializeUpload",
            json_body={"initializeUploadRequest": {"owner": owner}},
        )
        value = (init or {}).get("value") or {}
        upload_url = value.get("uploadUrl")
        doc_urn = value.get("document")
        if not upload_url or not doc_urn:
            raise APIError(
                "Documents API initializeUpload returned no uploadUrl/document URN",
                connector="linkedin",
                action="/rest/documents",
                details={"response": init},
            )
        await self._put_binary(upload_url, path.read_bytes())
        return doc_urn

    @action("Upload a video (multi-part) and return its urn:li:video asset URN")
    async def upload_video(self, owner: str, file_path: str) -> str:
        """Upload a local MP4 video (Videos API) and return its asset URN.

        Three-step multi-part flow:
        ``POST /rest/videos?action=initializeUpload`` (declares the byte size,
        which determines the part count) → ``PUT`` each part to its upload URL
        (sliced by the server-provided ``firstByte``/``lastByte`` range),
        collecting the ETag of each → ``POST /rest/videos?action=finalizeUpload``
        with the ordered ETags + the upload token. Required scope:
        ``w_member_social`` / ``w_organization_social``. MP4 only;
        75 KB – 500 MB (hard max 5 GB); 3 s – 30 min.

        Args:
            owner: ``urn:li:person:{id}`` or ``urn:li:organization:{id}``.
            file_path: Local path to the MP4 file.

        Returns:
            The video asset URN (``urn:li:video:...``). LinkedIn processes
            video asynchronously, so it may be ``PROCESSING`` briefly after
            upload before it can serve in a post.
        """
        path = self._resolve_upload_path(file_path, frozenset({".mp4"}), kind="video")
        size = path.stat().st_size
        if size > self._VIDEO_MAX_BYTES:
            raise ValidationError(
                "video exceeds LinkedIn's 5GB hard limit",
                connector="linkedin",
                action="upload",
            )
        init = await self._request(
            "POST",
            "/rest/videos?action=initializeUpload",
            json_body={
                "initializeUploadRequest": {
                    "owner": owner,
                    "fileSizeBytes": size,
                    "uploadCaptions": False,
                    "uploadThumbnail": False,
                }
            },
        )
        value = (init or {}).get("value") or {}
        video_urn = value.get("video")
        upload_token = value.get("uploadToken", "")
        instructions = value.get("uploadInstructions") or []
        if not video_urn or not instructions:
            raise APIError(
                "Videos API initializeUpload returned no video URN / uploadInstructions",
                connector="linkedin",
                action="/rest/videos",
                details={"response": init},
            )
        multi_part = len(instructions) > 1
        part_ids: list[str] = []
        # Stream each part straight off disk (seek+read) — peak memory is one
        # ~4MB part, never the whole (up-to-5GB) file.
        with path.open("rb") as fh:
            for inst in instructions:
                upload_url = inst.get("uploadUrl")
                if not upload_url:
                    raise APIError(
                        "Videos API uploadInstructions entry missing uploadUrl",
                        connector="linkedin",
                        action="/rest/videos",
                        details={"instruction": inst},
                    )
                if multi_part and ("firstByte" not in inst or "lastByte" not in inst):
                    raise APIError(
                        "Videos API multi-part instruction missing firstByte/lastByte",
                        connector="linkedin",
                        action="/rest/videos",
                        details={"instruction": inst},
                    )
                first = int(inst.get("firstByte", 0))
                last = int(inst.get("lastByte", size - 1))
                fh.seek(first)
                etag = await self._put_binary(upload_url, fh.read(last - first + 1))
                if not etag:
                    raise APIError(
                        f"LinkedIn returned no ETag for video part {len(part_ids)}; "
                        "cannot finalize the multipart upload",
                        connector="linkedin",
                        action="/rest/videos",
                        upstream_status=200,
                    )
                part_ids.append(etag)
        await self._request(
            "POST",
            "/rest/videos?action=finalizeUpload",
            json_body={
                "finalizeUploadRequest": {
                    "video": video_urn,
                    "uploadToken": upload_token,
                    "uploadedPartIds": part_ids,
                }
            },
        )
        return video_urn

    @action(
        "Publish a post with an uploaded image/document/video attached",
        dangerous=True,
    )
    async def create_media_post(
        self,
        author: str,
        commentary: str,
        media_urn: str,
        title: Optional[str] = None,
        alt_text: Optional[str] = None,
        visibility: str = "PUBLIC",
        lifecycle_state: str = "PUBLISHED",
    ) -> LinkedInPost:
        """Publish a post with a single uploaded asset attached.

        Convenience over ``create_post``: builds the ``content.media`` block
        from an asset URN returned by ``upload_image`` / ``upload_document`` /
        ``upload_video``.

        Args:
            author: The author URN (``urn:li:person:{id}`` or
                ``urn:li:organization:{id}``).
            commentary: The post text.
            media_urn: The asset URN (``urn:li:image:`` / ``:document:`` /
                ``:video:``) to attach.
            title: Title for the media (used for documents and videos).
            alt_text: Alt text for accessibility (used for images).
            visibility: ``"PUBLIC"`` or ``"CONNECTIONS"``.
            lifecycle_state: ``"PUBLISHED"`` or ``"DRAFT"``.

        Returns:
            The created post (URN exposed via ``post.id``).
        """
        media: dict[str, Any] = {"id": media_urn}
        if alt_text:
            media["altText"] = alt_text
        if title:
            media["title"] = title
        return await self.acreate_post(
            author=author,
            commentary=commentary,
            visibility=visibility,
            lifecycle_state=lifecycle_state,
            content={"media": media},
        )
