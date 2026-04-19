"""X (formerly Twitter) connector — post tweets, threads, replies, DMs.

Uses the X API v2 (https://developer.x.com/en/docs/x-api) with OAuth 2.0
Bearer token authentication (user context).

Tier requirements
-----------------
The X API has a tiered access model. This connector exposes endpoints
across tiers; **per-action docstrings prefix the required tier**.

- Free tier: write actions (create/delete/like/reply/thread) plus
  ``get_me``. ~1,500 writes/month.
- Basic tier ($100/mo): adds ``list_mentions`` and ``send_dm``.
- Pro / Enterprise: same surface, higher quotas.

When an action requires a higher tier than the user's token allows, the
X API returns HTTP 403 with reason ``client-not-enrolled`` or similar.
The ``_request`` error mapper translates this into a
``PermissionDeniedError`` with a clear suggestion field.
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
    """Connect to X (Twitter) to post tweets, threads, replies, DMs.

    Requires an OAuth 2.0 Bearer token (user context) passed as
    ``credentials``. The token must include scopes appropriate to the
    actions you intend to call:

    - ``tweet.write tweet.read users.read offline.access`` — for tweets,
      threads, replies, likes, ``get_me``.
    - ``dm.write dm.read`` — for ``send_dm`` (Basic tier required).
    - ``tweet.read users.read`` — for ``list_mentions`` (Basic tier
      required).

    Tier requirements per action are documented in each method's
    docstring. Free-tier accounts hitting Basic-only endpoints get a
    ``PermissionDeniedError`` with a clear suggestion.
    """

    name = "x"
    display_name = "X (Twitter)"
    category = ConnectorCategory.SOCIAL
    protocol = ProtocolType.REST
    base_url = "https://api.twitter.com/2"
    description = (
        "Post tweets, threads, replies. Like, reply, mention. Send DMs "
        "(Basic tier $100/mo). BYOK OAuth 2.0 Bearer tokens."
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
                    "ToolsConnector/0.3.0 "
                    "(+https://github.com/sachinshelke/ToolsConnector)"
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

    @action("Get the authenticated X user's profile (Free tier)")
    async def get_me(self) -> XUser:
        """Get the authenticated X user.

        Tier: Free.

        Returns:
            The authenticated user's profile.
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

    @action("Post a tweet (Free tier)", dangerous=True)
    async def create_tweet(
        self,
        text: str,
        reply_to_tweet_id: Optional[str] = None,
        quote_tweet_id: Optional[str] = None,
    ) -> Tweet:
        """Post a single tweet to the authenticated user's timeline.

        Tier: Free. Each tweet counts against the user's monthly write quota.

        Args:
            text: Tweet text (max 280 chars on Free, longer on Premium).
            reply_to_tweet_id: If provided, posts as a reply to this tweet ID.
            quote_tweet_id: If provided, posts as a quote-tweet of this tweet ID.

        Returns:
            The created tweet.
        """
        payload: dict[str, Any] = {"text": text}
        if reply_to_tweet_id:
            payload["reply"] = {"in_reply_to_tweet_id": reply_to_tweet_id}
        if quote_tweet_id:
            payload["quote_tweet_id"] = quote_tweet_id

        body = await self._request("POST", "/tweets", json_body=payload)
        return self._parse_tweet(body)

    @action("Delete a tweet you authored (Free tier)", dangerous=True)
    async def delete_tweet(self, tweet_id: str) -> None:
        """Delete a tweet authored by the authenticated user.

        Tier: Free. The X API only permits deleting tweets you authored.

        Args:
            tweet_id: The tweet's ID.
        """
        await self._request("DELETE", f"/tweets/{tweet_id}")
        return None

    @action(
        "Reply to a tweet (Free tier)",
        dangerous=True,
    )
    async def reply_to_tweet(self, tweet_id: str, text: str) -> Tweet:
        """Reply to an existing tweet.

        Tier: Free.

        Args:
            tweet_id: The tweet to reply to.
            text: Reply text (max 280 chars on Free).

        Returns:
            The reply tweet.
        """
        return await self.create_tweet(text=text, reply_to_tweet_id=tweet_id)

    @action(
        "Post a thread of tweets sequentially (Free tier)",
        dangerous=True,
    )
    async def create_thread(self, texts: list[str]) -> list[Tweet]:
        """Post a thread by chaining tweets as sequential replies.

        Tier: Free. Each tweet in the thread counts against the user's
        monthly write quota — a 10-tweet thread uses 10 writes.

        **Partial-failure semantics**: This action makes N sequential POST
        requests. If one fails (e.g. rate limit, 5xx), the previously
        posted tweets remain published — there is no rollback. The exception
        is re-raised, but the partial result is preserved on
        ``e.details['posted_tweets']`` so the caller can decide whether to
        accept a half-published thread or attempt to repost the missing tail.

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

    @action("Like a tweet on behalf of the authenticated user (Free tier)", dangerous=True)
    async def like_tweet(self, user_id: str, tweet_id: str) -> None:
        """Like a tweet.

        Tier: Free. Note: ``user_id`` must be the authenticated user's ID
        (from ``get_me``); the X API does not allow liking on behalf of others.

        Args:
            user_id: The authenticated user's ID (from ``get_me``).
            tweet_id: The ID of the tweet to like.
        """
        await self._request(
            "POST",
            f"/users/{user_id}/likes",
            json_body={"tweet_id": tweet_id},
        )
        return None

    @action("Unlike a previously-liked tweet (Free tier)", dangerous=True)
    async def unlike_tweet(self, user_id: str, tweet_id: str) -> None:
        """Remove a like from a tweet.

        Tier: Free. ``user_id`` must be the authenticated user's ID.

        Args:
            user_id: The authenticated user's ID (from ``get_me``).
            tweet_id: The tweet to unlike.
        """
        await self._request("DELETE", f"/users/{user_id}/likes/{tweet_id}")
        return None

    # ======================================================================
    # MENTIONS — read (Basic tier required)
    # ======================================================================

    @action("List recent tweets that mention the user (Basic tier required)")
    async def list_mentions(
        self,
        user_id: str,
        max_results: int = 10,
        pagination_token: Optional[str] = None,
    ) -> PaginatedList[Tweet]:
        """List recent tweets mentioning the user.

        Tier: **Basic ($100/mo) or higher.** Free-tier accounts will
        receive a ``PermissionDeniedError`` with a hint to upgrade.

        Args:
            user_id: The user ID whose mentions to fetch (from ``get_me``).
            max_results: Page size (5..100). Defaults to 10.
            pagination_token: Cursor from a previous response's
                ``meta.next_token`` to fetch the next page.

        Returns:
            A page of mention tweets.
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

        body = await self._request(
            "GET", f"/users/{user_id}/mentions", params=params
        )
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
        "Send a direct message to another X user (Basic tier required)",
        dangerous=True,
    )
    async def send_dm(self, participant_id: str, text: str) -> XDirectMessage:
        """Send a one-to-one direct message.

        Tier: **Basic ($100/mo) or higher.** Free-tier accounts will
        receive a ``PermissionDeniedError`` with a hint to upgrade.

        Args:
            participant_id: The recipient's X user ID.
            text: Message text.

        Returns:
            The created direct message envelope (conversation + event IDs).
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
