"""End-to-end tests for the LinkedIn connector using respx.

LinkedIn is our Tier-1 ``social`` connector: a BYOK OAuth-2 surface where
only 3 of 8 actions are reachable by a standard self-serve token and the
other 5 are gated behind the LinkedIn Partner Program. This suite pins both
halves of that reality — plus the LinkedIn-specific wire quirks that respx
is uniquely good at catching:

  - **Versioned headers**: every ``/rest/*`` call must carry
    ``Linkedin-Version: 202604`` + ``X-Restli-Protocol-Version: 2.0.0``.
  - **URN URL-encoding**: post/comment URNs are path segments, so the
    raw ``urn:li:share:123`` must travel as ``urn%3Ali%3Ashare%3A123``
    or LinkedIn 400s.
  - **``x-restli-id`` folding**: a 201 from ``POST /rest/posts`` carries
    the new URN in a *header*, not the body — the connector folds it into
    ``post.id``.
  - **``actor`` as a query parameter** on ``POST /rest/reactions`` (NOT a
    body field — this is a documented LinkedIn idiosyncrasy).
  - **Partner gating**: the 5 gated actions each return a distinct
    ``partnerApi*`` 403. The exact ``serviceErrorCode`` strings below were
    observed live against the real API on 2026-06-20 and map to
    ``PermissionDeniedError``.

Tests ``await`` the ``a*``-prefixed async methods (BaseConnector installs a
sync wrapper *and* an ``a<name>`` async variant for every ``@action``);
respx intercepts at the httpx transport layer either way.
"""

from __future__ import annotations

import json

import httpx
import pytest
import pytest_asyncio
import respx

from toolsconnector.connectors.linkedin import LinkedIn
from toolsconnector.connectors.linkedin.types import LinkedInPost, LinkedInProfile
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
from toolsconnector.errors import (
    ConnectionError as ToolsConnectorConnectionError,
)
from toolsconnector.spec.connector import ConnectorCategory, ProtocolType

BASE = "https://api.linkedin.com"
TOKEN = "fake-linkedin-access-token"
SUB = "XFXieqbIYi"
AUTHOR = f"urn:li:person:{SUB}"
POST_URN = "urn:li:share:7473999644516200448"
ENCODED_POST_URN = "urn%3Ali%3Ashare%3A7473999644516200448"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def linkedin() -> LinkedIn:
    """LinkedIn connector with a fake token; respx intercepts every request."""
    connector = LinkedIn(credentials=TOKEN)
    await connector._setup()
    yield connector
    await connector._teardown()


# ---------------------------------------------------------------------------
# 1. Happy path — the 3 BYOK actions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_profile_happy_path(linkedin: LinkedIn) -> None:
    """get_profile: OIDC userinfo → LinkedInProfile, person URN derivable."""
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        route = mock.get("/v2/userinfo").mock(
            return_value=httpx.Response(
                200,
                json={
                    "sub": SUB,
                    "name": "Ada Lovelace",
                    "given_name": "Ada",
                    "family_name": "Lovelace",
                    "email": "ada@example.com",
                    "email_verified": True,
                },
            )
        )
        profile = await linkedin.aget_profile()

    assert isinstance(profile, LinkedInProfile)
    assert profile.sub == SUB
    assert profile.name == "Ada Lovelace"
    assert profile.email == "ada@example.com"
    # Bearer auth travels on the userinfo call.
    assert route.calls.last.request.headers["authorization"] == f"Bearer {TOKEN}"


@pytest.mark.asyncio
async def test_create_post_request_shape_and_headers(linkedin: LinkedIn) -> None:
    """create_post: POST /rest/posts with versioned headers + camelCase body."""
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        route = mock.post("/rest/posts").mock(
            return_value=httpx.Response(
                201,
                headers={"x-restli-id": POST_URN},
                json={},
            )
        )
        post = await linkedin.acreate_post(
            author=AUTHOR,
            commentary="Shipping ToolsConnector 🚀",
            visibility="PUBLIC",
        )

    req = route.calls.last.request
    # Versioned-API headers are mandatory on /rest/*.
    assert req.headers["linkedin-version"] == "202604"
    assert req.headers["x-restli-protocol-version"] == "2.0.0"
    assert req.headers["content-type"] == "application/json"

    body = json.loads(req.content)
    assert body["author"] == AUTHOR
    assert body["commentary"] == "Shipping ToolsConnector 🚀"
    assert body["visibility"] == "PUBLIC"
    assert body["lifecycleState"] == "PUBLISHED"
    assert body["distribution"]["feedDistribution"] == "MAIN_FEED"
    assert body["isReshareDisabledByAuthor"] is False

    # The created URN comes from the x-restli-id *header*, folded into id.
    assert isinstance(post, LinkedInPost)
    assert post.id == POST_URN
    assert post.commentary == "Shipping ToolsConnector 🚀"


@pytest.mark.asyncio
async def test_create_post_draft_and_content_block(linkedin: LinkedIn) -> None:
    """create_post: lifecycle_state=DRAFT + an article content block wire through."""
    content = {"article": {"source": "https://x.test", "title": "T", "description": "D"}}
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        route = mock.post("/rest/posts").mock(
            return_value=httpx.Response(201, headers={"x-restli-id": POST_URN}, json={})
        )
        await linkedin.acreate_post(
            author=AUTHOR,
            commentary="draft",
            visibility="CONNECTIONS",
            lifecycle_state="DRAFT",
            content=content,
        )
    body = json.loads(route.calls.last.request.content)
    assert body["lifecycleState"] == "DRAFT"
    assert body["visibility"] == "CONNECTIONS"
    assert body["content"] == content


@pytest.mark.asyncio
async def test_delete_post_encodes_urn_and_returns_none(linkedin: LinkedIn) -> None:
    """delete_post: DELETE /rest/posts/{percent-encoded urn}; 204 → None."""
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        route = mock.delete(url__startswith=f"{BASE}/rest/posts/").mock(
            return_value=httpx.Response(204)
        )
        result = await linkedin.adelete_post(POST_URN)

    assert result is None
    # The colons in the URN must be percent-encoded in the path segment.
    raw_path = route.calls.last.request.url.raw_path.decode()
    assert ENCODED_POST_URN in raw_path
    assert ":" not in raw_path.split("/rest/posts/")[1]


# ---------------------------------------------------------------------------
# 2. Partner-gated surface — the 5 actions a standard token cannot reach.
#    serviceErrorCodes captured live against the real API on 2026-06-20.
# ---------------------------------------------------------------------------

_GATED = [
    ("get_post", "partnerApiPostsExternal.GET", lambda li: li.aget_post(POST_URN)),
    (
        "list_my_posts",
        "partnerApiPostsExternal.FINDER-author",
        lambda li: li.alist_my_posts(author=AUTHOR),
    ),
    (
        "list_comments",
        "partnerApiSocialActions.GET_ALL",
        lambda li: li.alist_comments(post_urn=POST_URN),
    ),
    (
        "create_comment",
        "partnerApiSocialActions.CREATE",
        lambda li: li.acreate_comment(post_urn=POST_URN, actor=AUTHOR, text="hi"),
    ),
    (
        "react_to_post",
        "partnerApiReactions.CREATE",
        lambda li: li.areact_to_post(post_urn=POST_URN, actor=AUTHOR, reaction_type="LIKE"),
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("name,service_code,call", _GATED, ids=[g[0] for g in _GATED])
async def test_partner_gated_action_maps_403_to_permission_denied(
    linkedin: LinkedIn, name: str, service_code: str, call
) -> None:
    """Each gated action's real 403 → PermissionDeniedError, code preserved."""
    body = {
        "message": f"Not enough permissions to access: {service_code}.20260401",
        "status": 403,
        "serviceErrorCode": 100,
        "code": "ACCESS_DENIED",
    }
    with respx.mock(base_url=BASE) as mock:
        mock.route(url__regex=r".*").mock(return_value=httpx.Response(403, json=body))
        with pytest.raises(PermissionDeniedError) as exc_info:
            await call(linkedin)

    err = exc_info.value
    assert err.details["http_status"] == 403
    assert service_code in str(err)
    assert err.connector == "linkedin"


# ---------------------------------------------------------------------------
# 3. Error matrix — vendor responses → typed exception hierarchy.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_401_expired_token_maps_to_token_expired(linkedin: LinkedIn) -> None:
    """A 401 carrying EXPIRED_ACCESS_TOKEN → TokenExpiredError (regenerate hint)."""
    with respx.mock(base_url=BASE) as mock:
        mock.get("/v2/userinfo").mock(
            return_value=httpx.Response(
                401, json={"message": "EXPIRED_ACCESS_TOKEN", "status": 401}
            )
        )
        with pytest.raises(TokenExpiredError) as exc_info:
            await linkedin.aget_profile()
    assert "60 days" in (exc_info.value.suggestion or "")


@pytest.mark.asyncio
async def test_401_generic_maps_to_invalid_credentials(linkedin: LinkedIn) -> None:
    """A 401 without an expiry marker → InvalidCredentialsError."""
    with respx.mock(base_url=BASE) as mock:
        mock.get("/v2/userinfo").mock(
            return_value=httpx.Response(
                401, json={"message": "Invalid access token", "status": 401}
            )
        )
        with pytest.raises(InvalidCredentialsError):
            await linkedin.aget_profile()


@pytest.mark.asyncio
async def test_404_maps_to_not_found(linkedin: LinkedIn) -> None:
    with respx.mock(base_url=BASE) as mock:
        mock.route(url__regex=r".*").mock(
            return_value=httpx.Response(404, json={"message": "Not found", "status": 404})
        )
        with pytest.raises(NotFoundError):
            await linkedin.aget_post(POST_URN)


@pytest.mark.asyncio
async def test_400_maps_to_validation_error(linkedin: LinkedIn) -> None:
    with respx.mock(base_url=BASE) as mock:
        mock.post("/rest/posts").mock(
            return_value=httpx.Response(400, json={"message": "Invalid commentary", "status": 400})
        )
        with pytest.raises(ValidationError):
            await linkedin.acreate_post(author=AUTHOR, commentary="")


@pytest.mark.asyncio
async def test_429_maps_to_rate_limit_with_retry_after(linkedin: LinkedIn) -> None:
    """429 + Retry-After → RateLimitError carrying retry_after_seconds."""
    with respx.mock(base_url=BASE) as mock:
        mock.post("/rest/posts").mock(
            return_value=httpx.Response(
                429,
                headers={"Retry-After": "120"},
                json={"message": "Throttled", "status": 429},
            )
        )
        with pytest.raises(RateLimitError) as exc_info:
            await linkedin.acreate_post(author=AUTHOR, commentary="hi")
    assert exc_info.value.retry_after_seconds == 120.0


@pytest.mark.asyncio
async def test_500_maps_to_server_error(linkedin: LinkedIn) -> None:
    with respx.mock(base_url=BASE) as mock:
        mock.post("/rest/posts").mock(
            return_value=httpx.Response(503, json={"message": "Upstream down", "status": 503})
        )
        with pytest.raises(ServerError) as exc_info:
            await linkedin.acreate_post(author=AUTHOR, commentary="hi")
    assert exc_info.value.upstream_status == 503


# ---------------------------------------------------------------------------
# 4. Reactions wire quirk + client-side validation.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_react_to_post_puts_actor_in_query_not_body(linkedin: LinkedIn) -> None:
    """POST /rest/reactions: actor is a QUERY param; body is {root, reactionType}.

    Even though the live API gates this with a 403, respx records the
    outgoing request — so we can pin that the connector *builds* it per
    LinkedIn's spec regardless of the server's entitlement check.
    """
    with respx.mock(base_url=BASE) as mock:
        route = mock.post(url__startswith=f"{BASE}/rest/reactions").mock(
            return_value=httpx.Response(403, json={"message": "partnerApiReactions.CREATE"})
        )
        with pytest.raises(PermissionDeniedError):
            await linkedin.areact_to_post(post_urn=POST_URN, actor=AUTHOR, reaction_type="PRAISE")

    req = route.calls.last.request
    assert req.url.params["actor"] == AUTHOR  # actor in the query string
    body = json.loads(req.content)
    assert body == {"root": POST_URN, "reactionType": "PRAISE"}
    assert "actor" not in body  # explicitly NOT in the body


@pytest.mark.asyncio
async def test_react_to_post_rejects_unknown_reaction_type(linkedin: LinkedIn) -> None:
    """An invalid reaction_type fails client-side — no HTTP call is made."""
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        route = mock.route(url__regex=r".*").mock(return_value=httpx.Response(201))
        with pytest.raises(ValidationError) as exc_info:
            await linkedin.areact_to_post(post_urn=POST_URN, actor=AUTHOR, reaction_type="MAYBE")
    assert "MAYBE" in str(exc_info.value)
    assert not route.called  # validation happened before any network I/O


@pytest.mark.asyncio
async def test_create_comment_request_shape(linkedin: LinkedIn) -> None:
    """create_comment: POST /rest/socialActions/{encoded}/comments, encoded URN."""
    with respx.mock(base_url=BASE) as mock:
        route = mock.post(url__regex=r".*/socialActions/.*/comments$").mock(
            return_value=httpx.Response(403, json={"message": "partnerApiSocialActions.CREATE"})
        )
        with pytest.raises(PermissionDeniedError):
            await linkedin.acreate_comment(post_urn=POST_URN, actor=AUTHOR, text="nice")

    req = route.calls.last.request
    assert ENCODED_POST_URN in req.url.raw_path.decode()
    body = json.loads(req.content)
    assert body == {"actor": AUTHOR, "object": POST_URN, "message": {"text": "nice"}}


# ---------------------------------------------------------------------------
# 5. Pagination — list_my_posts offset math (respx-mocked 200s).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_my_posts_pagination_with_total(linkedin: LinkedIn) -> None:
    """A full page + a server total → has_more True and next offset = start+len."""
    with respx.mock(base_url=BASE) as mock:
        mock.get("/rest/posts").mock(
            return_value=httpx.Response(
                200,
                json={
                    "elements": [
                        {"id": "urn:li:share:1", "commentary": "a"},
                        {"id": "urn:li:share:2", "commentary": "b"},
                    ],
                    "paging": {"start": 0, "count": 2, "total": 5},
                },
            )
        )
        page = await linkedin.alist_my_posts(author=AUTHOR, count=2, start=0)

    assert len(page.items) == 2
    assert page.page_state.total_count == 5
    assert page.page_state.has_more is True
    assert page.page_state.offset == 2


@pytest.mark.asyncio
async def test_list_my_posts_last_page_terminates(linkedin: LinkedIn) -> None:
    """A short final page with no total → has_more False, offset None."""
    with respx.mock(base_url=BASE) as mock:
        route = mock.get("/rest/posts").mock(
            return_value=httpx.Response(
                200, json={"elements": [{"id": "urn:li:share:9", "commentary": "z"}]}
            )
        )
        page = await linkedin.alist_my_posts(author=AUTHOR, count=10, start=0)

    assert len(page.items) == 1
    assert page.page_state.has_more is False
    assert page.page_state.offset is None
    # The author finder params travel as query string.
    params = route.calls.last.request.url.params
    assert params["q"] == "author"
    assert params["author"] == AUTHOR
    assert params["count"] == "10"


# ---------------------------------------------------------------------------
# 6. Spec metadata — Tier-1 surface contract.
# ---------------------------------------------------------------------------


def test_spec_metadata_and_tier() -> None:
    """Protocol, category, live tier, and the full 8-action surface."""
    assert LinkedIn.protocol is ProtocolType.REST
    assert LinkedIn.category is ConnectorCategory.SOCIAL
    assert LinkedIn.verification_status == "live"  # live-verified 2026-06-20
    assert LinkedIn.get_spec().verification_status == "live"
    assert set(LinkedIn.get_actions().keys()) == {
        "get_profile",
        "create_post",
        "delete_post",
        "get_post",
        "list_my_posts",
        "create_comment",
        "list_comments",
        "react_to_post",
        "upload_image",
        "upload_document",
        "upload_video",
        "create_media_post",
    }


def test_dangerous_write_actions_flagged() -> None:
    """Feed-mutating actions carry the dangerous flag for MCP gating."""
    actions = LinkedIn.get_actions()
    for name in (
        "create_post",
        "delete_post",
        "create_comment",
        "react_to_post",
        "create_media_post",
    ):
        assert actions[name].dangerous is True, f"{name} should be dangerous"
    assert actions["get_profile"].dangerous is False
    # Uploads register a private asset (no public side effect) → not dangerous.
    for name in ("upload_image", "upload_document", "upload_video"):
        assert actions[name].dangerous is False, f"{name} should not be dangerous"


# ---------------------------------------------------------------------------
# 7. Media uploads (Images / Documents / Videos APIs)
# ---------------------------------------------------------------------------

_UPLOAD_URL = "https://www.linkedin.com/dms-uploads/fake/0"


@pytest.mark.asyncio
async def test_upload_image(linkedin: LinkedIn, tmp_path) -> None:
    f = tmp_path / "pic.png"
    f.write_bytes(b"\x89PNG-fake-bytes")
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        init = mock.post(url__regex=r".*/rest/images").mock(
            return_value=httpx.Response(
                200, json={"value": {"uploadUrl": _UPLOAD_URL, "image": "urn:li:image:ABC"}}
            )
        )
        put = mock.put(_UPLOAD_URL).mock(
            return_value=httpx.Response(201, headers={"etag": '"img-etag"'})
        )
        urn = await linkedin.aupload_image(owner=AUTHOR, file_path=str(f))

    assert urn == "urn:li:image:ABC"
    assert json.loads(init.calls.last.request.content) == {
        "initializeUploadRequest": {"owner": AUTHOR}
    }
    preq = put.calls.last.request
    assert preq.content == b"\x89PNG-fake-bytes"  # raw bytes streamed
    assert preq.headers["content-type"] == "application/octet-stream"  # not application/json
    assert "linkedin-version" not in preq.headers  # bare upload client, no versioned headers


@pytest.mark.asyncio
async def test_upload_document(linkedin: LinkedIn, tmp_path) -> None:
    f = tmp_path / "deck.pdf"
    f.write_bytes(b"%PDF-fake")
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        mock.post(url__regex=r".*/rest/documents").mock(
            return_value=httpx.Response(
                200, json={"value": {"uploadUrl": _UPLOAD_URL, "document": "urn:li:document:DOC"}}
            )
        )
        mock.put(_UPLOAD_URL).mock(return_value=httpx.Response(201))
        urn = await linkedin.aupload_document(owner=AUTHOR, file_path=str(f))
    assert urn == "urn:li:document:DOC"


@pytest.mark.asyncio
async def test_upload_video_multipart(linkedin: LinkedIn, tmp_path) -> None:
    """Video: declares byte size, PUTs each part by byte-range, finalizes with ETags."""
    f = tmp_path / "v.mp4"
    f.write_bytes(b"AAAAABBBBB")  # 10 bytes → two 5-byte parts
    part0 = "https://www.linkedin.com/dms-uploads/v/0"
    part1 = "https://www.linkedin.com/dms-uploads/v/1"
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        init = mock.post("/rest/videos", params={"action": "initializeUpload"}).mock(
            return_value=httpx.Response(
                200,
                json={
                    "value": {
                        "video": "urn:li:video:VID",
                        "uploadToken": "TOK",
                        "uploadInstructions": [
                            {"uploadUrl": part0, "firstByte": 0, "lastByte": 4},
                            {"uploadUrl": part1, "firstByte": 5, "lastByte": 9},
                        ],
                    }
                },
            )
        )
        fin = mock.post("/rest/videos", params={"action": "finalizeUpload"}).mock(
            return_value=httpx.Response(200, json={})
        )
        p0 = mock.put(part0).mock(return_value=httpx.Response(200, headers={"etag": '"etag0"'}))
        p1 = mock.put(part1).mock(return_value=httpx.Response(200, headers={"etag": '"etag1"'}))
        urn = await linkedin.aupload_video(owner=AUTHOR, file_path=str(f))

    assert urn == "urn:li:video:VID"
    assert (
        json.loads(init.calls.last.request.content)["initializeUploadRequest"]["fileSizeBytes"]
        == 10
    )
    assert p0.calls.last.request.content == b"AAAAA"  # bytes 0..4
    assert p1.calls.last.request.content == b"BBBBB"  # bytes 5..9
    fbody = json.loads(fin.calls.last.request.content)["finalizeUploadRequest"]
    assert fbody["video"] == "urn:li:video:VID"
    assert fbody["uploadToken"] == "TOK"
    assert fbody["uploadedPartIds"] == ["etag0", "etag1"]  # ordered, quotes stripped


@pytest.mark.asyncio
async def test_create_media_post_builds_content_block(linkedin: LinkedIn) -> None:
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        route = mock.post("/rest/posts").mock(
            return_value=httpx.Response(201, headers={"x-restli-id": "urn:li:share:99"}, json={})
        )
        post = await linkedin.acreate_media_post(
            author=AUTHOR,
            commentary="see the deck",
            media_urn="urn:li:document:DOC",
            title="Deck.pdf",
        )
    body = json.loads(route.calls.last.request.content)
    assert body["content"] == {"media": {"id": "urn:li:document:DOC", "title": "Deck.pdf"}}
    assert body["author"] == AUTHOR
    assert post.id == "urn:li:share:99"


@pytest.mark.asyncio
async def test_upload_missing_file_raises_validation(linkedin: LinkedIn) -> None:
    with pytest.raises(ValidationError):
        await linkedin.aupload_image(owner=AUTHOR, file_path="/nope/does-not-exist.png")


# ---------------------------------------------------------------------------
# 8. Hardening (transport wrapping, redaction, validation, pagination boundary)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transport_error_wrapped_to_typed(linkedin: LinkedIn) -> None:
    """A bare httpx.ConnectError becomes the typed ConnectionError (catchable as ToolsConnectorError)."""
    with respx.mock(base_url=BASE) as mock:
        mock.get("/v2/userinfo").mock(side_effect=httpx.ConnectError("refused"))
        with pytest.raises(ToolsConnectorConnectionError):
            await linkedin.aget_profile()


@pytest.mark.asyncio
async def test_error_body_redacts_reflected_bearer_token(linkedin: LinkedIn) -> None:
    """A token echoed in an error body must not survive into err.details / str(err)."""
    token = "AQVfakefakefakefakefake1234567890"
    with respx.mock(base_url=BASE) as mock:
        mock.get("/v2/userinfo").mock(
            return_value=httpx.Response(403, json={"message": f"denied Bearer {token}"})
        )
        with pytest.raises(PermissionDeniedError) as exc_info:
            await linkedin.aget_profile()
    blob = json.dumps(exc_info.value.details) + str(exc_info.value)
    assert token not in blob  # the live token is redacted out


@pytest.mark.asyncio
async def test_empty_access_token_is_invalid_credentials(linkedin: LinkedIn) -> None:
    """A *missing* token (EMPTY_ACCESS_TOKEN) → InvalidCredentials, not TokenExpired."""
    with respx.mock(base_url=BASE) as mock:
        mock.get("/v2/userinfo").mock(
            return_value=httpx.Response(401, json={"message": "EMPTY_ACCESS_TOKEN"})
        )
        with pytest.raises(InvalidCredentialsError):
            await linkedin.aget_profile()


@pytest.mark.asyncio
async def test_retry_after_http_date_does_not_crash(linkedin: LinkedIn) -> None:
    """An HTTP-date Retry-After must not crash the 429 path; falls back to the default."""
    with respx.mock(base_url=BASE) as mock:
        mock.post("/rest/posts").mock(
            return_value=httpx.Response(
                429,
                headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"},
                json={"message": "slow"},
            )
        )
        with pytest.raises(RateLimitError) as exc_info:
            await linkedin.acreate_post(author=AUTHOR, commentary="x")
    assert exc_info.value.retry_after_seconds == 60.0


@pytest.mark.asyncio
async def test_pagination_boundary_full_final_page(linkedin: LinkedIn) -> None:
    """A full final page that exactly exhausts `total` → has_more False (no wasted fetch)."""
    with respx.mock(base_url=BASE) as mock:
        mock.get("/rest/posts").mock(
            return_value=httpx.Response(
                200,
                json={
                    "elements": [{"id": "urn:li:share:4"}, {"id": "urn:li:share:5"}],
                    "paging": {"total": 5},
                },
            )
        )
        page = await linkedin.alist_my_posts(author=AUTHOR, count=2, start=3)
    assert page.page_state.has_more is False
    assert page.page_state.offset is None


@pytest.mark.asyncio
async def test_upload_rejects_bad_extension(linkedin: LinkedIn, tmp_path) -> None:
    f = tmp_path / "notanimage.txt"
    f.write_bytes(b"x")
    with pytest.raises(ValidationError):
        await linkedin.aupload_image(owner=AUTHOR, file_path=str(f))


@pytest.mark.asyncio
async def test_upload_refuses_non_linkedin_url(linkedin: LinkedIn, tmp_path) -> None:
    """SSRF guard: a tampered initializeUpload pointing off-LinkedIn is refused."""
    f = tmp_path / "pic.png"
    f.write_bytes(b"x")
    with respx.mock(base_url=BASE) as mock:
        mock.post(url__regex=r".*/rest/images").mock(
            return_value=httpx.Response(
                200,
                json={
                    "value": {"uploadUrl": "https://evil.example.com/up", "image": "urn:li:image:X"}
                },
            )
        )
        with pytest.raises(APIError) as exc_info:
            await linkedin.aupload_image(owner=AUTHOR, file_path=str(f))
    assert "non-LinkedIn" in str(exc_info.value)


@pytest.mark.asyncio
async def test_video_missing_etag_raises(linkedin: LinkedIn, tmp_path) -> None:
    """A video part PUT with no ETag must fail loud, not finalize with an empty id."""
    f = tmp_path / "v.mp4"
    f.write_bytes(b"AAAAA")
    url = "https://www.linkedin.com/dms-uploads/v/0"
    with respx.mock(base_url=BASE) as mock:
        mock.post("/rest/videos", params={"action": "initializeUpload"}).mock(
            return_value=httpx.Response(
                200,
                json={
                    "value": {
                        "video": "urn:li:video:V",
                        "uploadToken": "T",
                        "uploadInstructions": [{"uploadUrl": url, "firstByte": 0, "lastByte": 4}],
                    }
                },
            )
        )
        mock.put(url).mock(return_value=httpx.Response(200))  # NO etag header
        with pytest.raises(APIError) as exc_info:
            await linkedin.aupload_video(owner=AUTHOR, file_path=str(f))
    assert "no ETag" in str(exc_info.value)
