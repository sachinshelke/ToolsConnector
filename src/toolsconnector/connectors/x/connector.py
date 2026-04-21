"""X (formerly Twitter) connector — post tweets, threads, replies, DMs.

Uses the X API v2 (base URL ``https://api.x.com``) with OAuth 2.0
Bearer token authentication (user-context tokens for write actions;
either user or app-only tokens for some read endpoints).

Reference: https://docs.x.com/x-api/introduction

Endpoints
---------
All endpoints below are under ``api.x.com/2``:

- ``GET /users/me`` — get_me. Scopes: ``tweet.read users.read``.
- ``POST /tweets`` — create_tweet, reply_to_tweet, create_thread.
  Scopes: ``tweet.read tweet.write users.read``.
- ``DELETE /tweets/{id}`` — delete_tweet. Same write scopes; only the
  authenticated author can delete.
- ``POST /users/{id}/likes`` — like_tweet. Body: ``{tweet_id}``.
  Scopes: ``like.write``. ``id`` MUST be the authenticated user's ID.
- ``DELETE /users/{id}/likes/{tweet_id}`` — unlike_tweet.
  Scopes: ``like.write``. Same authenticated-user constraint.
- ``GET /users/{id}/mentions`` — list_mentions. Scopes:
  ``tweet.read users.read``. Cursor pagination via
  ``meta.next_token`` ↔ ``pagination_token`` query param.
- ``POST /dm_conversations/with/{participant_id}/messages`` — send_dm.
  Scopes: ``dm.write tweet.read users.read``. Body: ``{text}``.

Tier requirements
-----------------
The X API has a tiered access model (Free / Basic / Pro / Enterprise).
The exact endpoint-to-tier mapping changes over time and is not formally
specified per-endpoint in the OpenAPI docs. Historically:

- Free tier covers all write actions (tweet, reply, thread, like, unlike,
  delete, send_dm in some accounts) but is heavily quota-limited
  (~1,500 writes/month).
- Basic tier ($100/mo) adds full read access (mentions, search, lookup).
- Pro/Enterprise raise quotas significantly.

When an X endpoint requires a higher tier than the user's token allows,
X returns HTTP 403 with reason ``client-not-enrolled``, ``usage cap``,
or similar. The ``_request`` error mapper translates these into
``PermissionDeniedError`` with a clear suggestion pointing at
https://developer.x.com/en/products/twitter-api so the LLM agent can
surface a friendly upgrade hint to the end user.

This connector exposes the full surface; X's server-side enforcement
is the source of truth for what your specific tier allows.
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
from toolsconnector.types import PageState, PaginatedList

from .types import Tweet, XDirectMessage, XUser

logger = logging.getLogger("toolsconnector.x")

# X API tier-related 403 reasons (case-insensitive substring match)
_TIER_GATED_REASONS = (
    "client-not-enrolled",
    "client-forbidden",
    "usage-cap",
    "usage cap",
    "subscription",
    "access level",
)


class X(BaseConnector):
    """Connect to X (Twitter) to post tweets, threads, replies, likes, mentions, DMs.

    Requires an OAuth 2.0 user-context Bearer token passed as
    ``credentials``. Build the token in the X Developer Portal with
    only the scopes you need:

    - ``tweet.read users.read`` — minimum for ``get_me``,
      ``list_mentions``.
    - ``tweet.write`` (plus the two above) — required for
      ``create_tweet``, ``delete_tweet``, ``reply_to_tweet``,
      ``create_thread``.
    - ``like.write`` — required for ``like_tweet``, ``unlike_tweet``.
    - ``dm.write`` — required for ``send_dm``.
    - ``offline.access`` — optional; only needed if you want a refresh
      token alongside the access token.

    Tier requirements per action are advisory (see module docstring).
    The X API enforces tiers server-side; insufficient-tier 403s are
    mapped to ``PermissionDeniedError`` with a clear suggestion.
    """

    name = "x"
    display_name = "X (Twitter)"
    category = ConnectorCategory.SOCIAL
    protocol = ProtocolType.REST
    # Per https://docs.x.com/x-api/introduction the documented base is
    # api.x.com. (api.twitter.com still resolves but is no longer the
    # canonical host in the OpenAPI spec.)
    base_url = "https://api.x.com/2"
    description = (
        "Post tweets, threads, replies. Like and unlike. Read mentions. "
        "Send DMs. BYOK OAuth 2.0 Bearer tokens. Some endpoints may "
        "require X API Basic tier ($100/mo) per X's tier policies — "
        "tier-gated 403s are mapped to PermissionDeniedError."
    )
    _rate_limit_config = RateLimitSpec(rate=1, period=2, burst=5)

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
                "User-Agent": (
                    "ToolsConnector/0.3.0 (+https://github.com/sachinshelke/ToolsConnector)"
                ),
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
        """Execute an HTTP request against the X API v2.

        Args:
            method: HTTP method (GET, POST, DELETE).
            path: API path (e.g. ``/tweets``).
            params: URL query parameters.
            json_body: JSON request body.

        Returns:
            The parsed JSON response. For 204 responses, ``None``.

        Raises:
            InvalidCredentialsError: Token invalid or missing scopes (HTTP 401).
            PermissionDeniedError: Tier-gated endpoint or forbidden (HTTP 403).
                When the X 403 reason matches a known tier-gating reason
                (``client-not-enrolled``, ``usage-cap`` etc.), the suggestion
                field tells the caller which tier is required.
            NotFoundError: Resource not found (HTTP 404).
            ValidationError: Bad request (HTTP 400).
            RateLimitError: Rate limited (HTTP 429), with ``x-rate-limit-reset``.
            ServerError: Upstream 5xx.
            APIError: Any other non-2xx response.
        """
        kwargs: dict[str, Any] = {}
        if params:
            kwargs["params"] = params
        if json_body is not None:
            kwargs["json"] = json_body

        response = await self._client.request(method, path, **kwargs)
        status = response.status_code

        if status == 204:
            return None

        try:
            body = response.json()
        except Exception:
            body = {}

        if 200 <= status < 300:
            return body

        # X v2 errors: top-level "errors" list and/or "title"/"detail"/"reason"
        error_msg = (
            body.get("detail")
            or body.get("title")
            or body.get("error")
            or f"X API error (HTTP {status})"
        )
        details = {"x_response": body}

        if status == 401:
            raise InvalidCredentialsError(
                error_msg,
                connector="x",
                action=path,
                suggestion=(
                    "Verify the OAuth 2.0 Bearer token is valid and includes "
                    "the required scopes (e.g. tweet.write, users.read). "
                    "See https://developer.x.com/en/portal/dashboard."
                ),
                details=details,
            )

        if status == 403:
            # Detect tier-gated 403s (most common cause: free-tier hitting
            # Basic-only endpoints like list_mentions / send_dm).
            reason_text = " ".join(
                str(v).lower()
                for v in (body.get("reason"), body.get("detail"), body.get("title"))
                if v
            )
            is_tier_gated = any(r in reason_text for r in _TIER_GATED_REASONS)
            suggestion = (
                "This X API endpoint requires Basic tier ($100/mo) or higher. "
                "See https://developer.x.com/en/products/twitter-api"
                if is_tier_gated
                else (
                    "The token lacks permission for this action. Check the "
                    "OAuth scopes attached to your token."
                )
            )
            raise PermissionDeniedError(
                error_msg,
                connector="x",
                action=path,
                suggestion=suggestion,
                details=details,
            )

        if status == 404:
            raise NotFoundError(
                error_msg,
                connector="x",
                action=path,
                details=details,
            )

        if status == 400:
            raise ValidationError(
                error_msg,
                connector="x",
                action=path,
                details=details,
            )

        if status == 429:
            # X uses x-rate-limit-reset (epoch seconds)
            reset = response.headers.get("x-rate-limit-reset")
            try:
                # Convert reset epoch to seconds-from-now
                import time as _time

                retry_after = max(1.0, float(reset) - _time.time()) if reset else 60.0
            except (TypeError, ValueError):
                retry_after = 60.0
            raise RateLimitError(
                error_msg,
                connector="x",
                action=path,
                retry_after_seconds=retry_after,
                details=details,
            )

        if status >= 500:
            raise ServerError(
                error_msg,
                connector="x",
                action=path,
                details=details,
                upstream_status=status,
            )

        raise APIError(
            error_msg,
            connector="x",
            action=path,
            details=details,
            upstream_status=status,
        )

    def _parse_tweet(self, raw: dict[str, Any]) -> Tweet:
        """Parse an X v2 tweet dict into a Tweet model.

        Some endpoints return the tweet under ``data``, others return it
        directly. This helper accepts either shape.
        """
        if "data" in raw and isinstance(raw["data"], dict):
            raw = raw["data"]
        return Tweet.model_validate(raw)

    # ======================================================================
    # USER
    # ======================================================================

    @action("Get the authenticated X user's profile")
    async def get_me(self) -> XUser:
        """Get the authenticated X user (``GET /2/users/me``).

        Required scopes: ``tweet.read users.read``. The lowest X tier
        that includes user-context calls is sufficient.

        Returns:
            The authenticated user's profile, including ``id`` (the
            user URN suffix needed by ``like_tweet``, ``unlike_tweet``,
            and ``list_mentions``).
        """
        body = await self._request(
            "GET",
            "/users/me",
            params={
                "user.fields": (
                    "id,name,username,description,verified,"
                    "profile_image_url,created_at,public_metrics"
                )
            },
        )
        data = body.get("data", body)
        return XUser.model_validate(data)

    # ======================================================================
    # TWEETS — write
    # ======================================================================

    @action("Post a tweet on behalf of the authenticated user", dangerous=True)
    async def create_tweet(
        self,
        text: str,
        reply_to_tweet_id: Optional[str] = None,
        quote_tweet_id: Optional[str] = None,
    ) -> Tweet:
        """Post a single tweet via ``POST /2/tweets``.

        Required scopes: ``tweet.read tweet.write users.read``. Each
        tweet counts against the authenticated user's monthly write
        quota (varies by tier — see X's developer pricing page).

        Args:
            text: Tweet text (max 280 chars on Free; longer thresholds
                apply on X Premium / Verified accounts).
            reply_to_tweet_id: If provided, posts as a reply by setting
                ``reply.in_reply_to_tweet_id`` on the X request body.
            quote_tweet_id: If provided, posts as a quote-tweet of this
                tweet ID. Mutually exclusive with media/poll/card_uri
                per X's API rules.

        Returns:
            The created tweet (``id`` and ``text``).
        """
        payload: dict[str, Any] = {"text": text}
        if reply_to_tweet_id:
            payload["reply"] = {"in_reply_to_tweet_id": reply_to_tweet_id}
        if quote_tweet_id:
            payload["quote_tweet_id"] = quote_tweet_id

        body = await self._request("POST", "/tweets", json_body=payload)
        return self._parse_tweet(body)

    @action("Delete a tweet you authored", dangerous=True)
    async def delete_tweet(self, tweet_id: str) -> bool:
        """Delete a tweet via ``DELETE /2/tweets/{id}``.

        Required scopes: ``tweet.read tweet.write users.read``. X only
        permits deleting tweets the authenticated user authored.

        Args:
            tweet_id: The tweet's ID (numeric string).

        Returns:
            ``True`` if X confirmed deletion (``data.deleted == true``),
            ``False`` otherwise. The X API returns this boolean on
            success; this action surfaces it directly.
        """
        body = await self._request("DELETE", f"/tweets/{tweet_id}")
        if isinstance(body, dict):
            data = body.get("data") or {}
            return bool(data.get("deleted", False))
        return False

    @action("Reply to a tweet", dangerous=True)
    async def reply_to_tweet(self, tweet_id: str, text: str) -> Tweet:
        """Reply to an existing tweet via ``POST /2/tweets``.

        Required scopes: ``tweet.read tweet.write users.read``.

        Args:
            tweet_id: The tweet to reply to.
            text: Reply text (max 280 chars on Free).

        Returns:
            The reply tweet.
        """
        return await self.create_tweet(text=text, reply_to_tweet_id=tweet_id)

    @action(
        "Post a thread of tweets sequentially",
        dangerous=True,
    )
    async def create_thread(self, texts: list[str]) -> list[Tweet]:
        """Post a thread by chaining tweets as sequential replies.

        This is a client-side composition over ``POST /2/tweets`` — X
        has no first-class "thread" endpoint. Each tweet in the thread
        counts against the authenticated user's monthly write quota.

        **Partial-failure semantics**: This action makes N sequential
        POST requests. If one fails (e.g. rate limit, 5xx), the
        previously posted tweets remain published — there is no
        rollback. The exception is re-raised, but the partial result
        is preserved on ``e.details['posted_tweets']`` so the caller
        can decide whether to accept a half-published thread or attempt
        to repost the missing tail.

        Args:
            texts: List of tweet texts in order. Must be non-empty.

        Returns:
            A list of the successfully-posted tweets, in order.

        Raises:
            ValidationError: If ``texts`` is empty.
        """
        if not texts:
            raise ValidationError(
                "create_thread requires at least one tweet text",
                connector="x",
                action="/tweets",
            )

        posted: list[Tweet] = []
        reply_to: Optional[str] = None
        for text in texts:
            try:
                tw = await self.create_tweet(text=text, reply_to_tweet_id=reply_to)
            except Exception as e:
                # Attach partial result so the caller can recover.
                if hasattr(e, "details") and isinstance(e.details, dict):
                    e.details["posted_tweets"] = [t.model_dump() for t in posted]
                raise
            posted.append(tw)
            reply_to = tw.id
        return posted

    @action("Like a tweet on behalf of the authenticated user", dangerous=True)
    async def like_tweet(self, user_id: str, tweet_id: str) -> None:
        """Like a tweet via ``POST /2/users/{id}/likes``.

        Required scope: ``like.write``. Per X's API, ``id`` MUST be
        the authenticated user's ID (the API does not allow liking
        on behalf of other users).

        Args:
            user_id: The authenticated user's ID (from ``get_me``).
            tweet_id: The ID of the tweet to like (numeric string).
        """
        await self._request(
            "POST",
            f"/users/{user_id}/likes",
            json_body={"tweet_id": tweet_id},
        )
        return None

    @action("Unlike a previously-liked tweet", dangerous=True)
    async def unlike_tweet(self, user_id: str, tweet_id: str) -> None:
        """Remove a like via ``DELETE /2/users/{id}/likes/{tweet_id}``.

        Required scope: ``like.write``. ``user_id`` must be the
        authenticated user's ID.

        Args:
            user_id: The authenticated user's ID (from ``get_me``).
            tweet_id: The tweet to unlike.
        """
        await self._request("DELETE", f"/users/{user_id}/likes/{tweet_id}")
        return None

    # ======================================================================
    # MENTIONS — read
    # ======================================================================

    @action("List recent tweets that mention the user")
    async def list_mentions(
        self,
        user_id: str,
        max_results: int = 10,
        pagination_token: Optional[str] = None,
    ) -> PaginatedList[Tweet]:
        """List recent tweets mentioning the user via
        ``GET /2/users/{id}/mentions``.

        Required scopes: ``tweet.read users.read``. Note: read endpoints
        on X are typically gated behind paid tiers (Basic $100/mo or
        higher) by X's own policy; Free-tier tokens will get a 403
        ``client-not-enrolled`` mapped to ``PermissionDeniedError``.

        Args:
            user_id: The user ID whose mentions to fetch (from
                ``get_me``).
            max_results: Page size. X enforces 5..100. Defaults to 10.
            pagination_token: Cursor from a previous response's
                ``meta.next_token``. Pass to fetch the next page.

        Returns:
            A page of mention tweets, with ``page_state.cursor`` set to
            the next ``meta.next_token`` (None if no more pages).
        """
        params: dict[str, Any] = {
            "max_results": max(5, min(int(max_results), 100)),
            "tweet.fields": (
                "id,text,author_id,created_at,conversation_id,"
                "in_reply_to_user_id,lang,public_metrics,entities,"
                "referenced_tweets,edit_history_tweet_ids"
            ),
        }
        if pagination_token:
            params["pagination_token"] = pagination_token

        body = await self._request("GET", f"/users/{user_id}/mentions", params=params)
        items = [Tweet.model_validate(t) for t in body.get("data", [])]
        meta = body.get("meta", {}) or {}
        next_token = meta.get("next_token")
        return PaginatedList(
            items=items,
            page_state=PageState(
                cursor=next_token,
                has_more=bool(next_token),
                total_count=meta.get("result_count"),
            ),
        )

    # ======================================================================
    # DMs — write (Basic tier required)
    # ======================================================================

    @action(
        "Send a direct message to another X user",
        dangerous=True,
    )
    async def send_dm(self, participant_id: str, text: str) -> XDirectMessage:
        """Send a one-to-one direct message via
        ``POST /2/dm_conversations/with/{participant_id}/messages``.

        Required scopes: ``dm.write tweet.read users.read``. DMs are
        typically gated to paid X tiers (Basic and above) per X's policy;
        Free-tier tokens will get a 403 ``client-not-enrolled`` mapped
        to ``PermissionDeniedError``.

        Args:
            participant_id: The recipient's X user ID (numeric string).
            text: Message text. Required if no ``attachments`` are given
                (this connector exposes the text-only path).

        Returns:
            The created DM envelope: ``dm_conversation_id`` (use this to
            continue the conversation) and ``dm_event_id`` (this message's
            unique event ID).
        """
        body = await self._request(
            "POST",
            f"/dm_conversations/with/{participant_id}/messages",
            json_body={"text": text},
        )
        data = body.get("data", body)
        return XDirectMessage(
            dm_conversation_id=data.get("dm_conversation_id", ""),
            dm_event_id=data.get("dm_event_id", ""),
        )
