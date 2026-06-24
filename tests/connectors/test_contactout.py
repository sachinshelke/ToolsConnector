"""End-to-end tests for the ContactOut connector using respx.

Pins the AUTHORITATIVE v1/v2 contract verified against the live docs:
- the `token` auth header (not Authorization);
- single-profile responses nest data under a `"profile"` key (search/decision-
  makers instead use a top-level `profiles` map keyed by URL);
- the field-name normalizer (work_email / work_emails / workEmail, plus the
  camelCase `personalEmail` from /email/enrich) → canonical lists;
- search pagination (fixed page size 25), free pre-flight checks, async bulk
  reveal + job poll + bulk verify, batch validation, error matrix, transport
  wrapping.
"""

from __future__ import annotations

import json

import httpx
import pytest
import pytest_asyncio
import respx

from toolsconnector.connectors.contactout import ContactOut
from toolsconnector.errors import (
    ConnectionError as ToolsConnectorConnectionError,
)
from toolsconnector.errors import (
    NotFoundError,
    RateLimitError,
    ValidationError,
)
from toolsconnector.spec.connector import ConnectorCategory, ProtocolType

BASE = "https://api.contactout.com"
KEY = "fake-contactout-token"
PROFILE = "https://www.linkedin.com/in/ada"


@pytest_asyncio.fixture
async def contactout() -> ContactOut:
    connector = ContactOut(credentials=KEY)
    await connector._setup()
    yield connector
    await connector._teardown()


@pytest.mark.asyncio
async def test_search_people_paginates_and_uses_token_header(contactout: ContactOut) -> None:
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        route = mock.post("/v1/people/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "status_code": 200,
                    "metadata": {"page": 1, "page_size": 25, "total_results": 40},
                    # search uses a TOP-LEVEL profiles map keyed by URL (no "profile" wrapper)
                    "profiles": {
                        PROFILE: {
                            "full_name": "Ada",
                            "title": "CEO",
                            "contact_availability": {"work_email": True},
                        },
                    },
                },
            )
        )
        page = await contactout.asearch_people(filters={"job_title": ["CEO"]}, page=1)

    req = route.calls.last.request
    assert req.headers["token"] == KEY  # custom auth header
    assert "authorization" not in req.headers
    body = json.loads(req.content)
    assert body["page"] == 1 and body["reveal_info"] is False
    assert page.items[0].linkedin_url == PROFILE
    assert page.items[0].full_name == "Ada"
    assert page.page_state.has_more is True  # 1*25 < 40
    assert page.page_state.total_count == 40


@pytest.mark.asyncio
async def test_search_reveal_info_normalizes_contact_info(contactout: ContactOut) -> None:
    with respx.mock(base_url=BASE) as mock:
        mock.post("/v1/people/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "metadata": {"page": 1, "page_size": 25, "total_results": 1},
                    "profiles": {
                        PROFILE: {
                            "full_name": "Ada",
                            "contact_info": {
                                "work_emails": ["ada@co.com"],
                                "personal_emails": ["ada@gmail.com"],
                                "phones": ["+14155550100"],
                            },
                        }
                    },
                },
            )
        )
        page = await contactout.asearch_people(filters={}, page=1, reveal_info=True)
    p = page.items[0]
    assert p.work_emails == ["ada@co.com"]
    assert p.personal_emails == ["ada@gmail.com"]
    assert p.phones == ["+14155550100"]


@pytest.mark.asyncio
async def test_count_people_is_int(contactout: ContactOut) -> None:
    with respx.mock(base_url=BASE) as mock:
        mock.post("/v1/people/count").mock(
            return_value=httpx.Response(200, json={"total_results": 1234})
        )
        assert await contactout.acount_people({"company": ["Acme"]}) == 1234


@pytest.mark.asyncio
async def test_enrich_linkedin_unwraps_profile_and_normalizes(contactout: ContactOut) -> None:
    """The enrich response NESTS data under "profile"; fields are singular arrays."""
    with respx.mock(base_url=BASE) as mock:
        route = mock.get("/v1/linkedin/enrich").mock(
            return_value=httpx.Response(
                200,
                json={
                    "status_code": 200,
                    "profile": {
                        "full_name": "Ada",
                        "work_email": ["ada@co.com"],
                        "personal_email": ["ada@gmail.com"],
                        "phone": ["+1"],
                    },
                },
            )
        )
        prof = await contactout.aenrich_linkedin_profile(PROFILE)
    assert prof.work_emails == ["ada@co.com"] and prof.personal_emails == ["ada@gmail.com"]
    assert prof.phones == ["+1"]
    assert route.calls.last.request.url.params["profile"] == PROFILE


@pytest.mark.asyncio
async def test_get_linkedin_contact_info_unwraps_profile(contactout: ContactOut) -> None:
    with respx.mock(base_url=BASE) as mock:
        mock.get("/v1/people/linkedin").mock(
            return_value=httpx.Response(
                200,
                json={
                    "profile": {
                        "work_email": ["ada@co.com"],
                        "phone": ["+1"],
                        "work_email_status": {"ada@co.com": "Verified"},
                    }
                },
            )
        )
        prof = await contactout.aget_linkedin_contact_info(PROFILE)
    assert prof.work_emails == ["ada@co.com"]
    assert prof.work_email_status == {"ada@co.com": "Verified"}


@pytest.mark.asyncio
async def test_enrich_by_email_unwraps_and_normalizes_camelcase(contactout: ContactOut) -> None:
    """/email/enrich nests under "profile" and uses camelCase across the board.

    Live shape (2026-06-24): besides workEmail/personalEmail, this endpoint also
    returns fullName / linkedinUrl / profilePictureUrl / jobFunction / workStatus
    in camelCase — all previously dropped, leaving full_name + linkedin_url empty.
    """
    with respx.mock(base_url=BASE) as mock:
        mock.get("/v1/email/enrich").mock(
            return_value=httpx.Response(
                200,
                json={
                    "profile": {
                        "email": "ada@gmail.com",
                        "workEmail": "ada@co.com",
                        "workEmailStatus": "Verified",
                        "personalEmail": "ada2@gmail.com",
                        "phone": "+1",
                        "fullName": "Ada Lovelace",
                        "linkedinUrl": "https://www.linkedin.com/in/ada",
                        "industry": "Software",
                        "twitter": "ada_tw",
                        "jobFunction": "Engineering",
                        "workStatus": "open_to_work",
                        "profilePictureUrl": "https://img/ada.png",
                        "updatedAt": "2024-01-01 00:00:00",
                    }
                },
            )
        )
        prof = await contactout.aenrich_by_email("ada@gmail.com")
    assert prof.work_emails == ["ada@co.com"]
    assert prof.personal_emails == ["ada2@gmail.com"]  # camelCase personalEmail captured
    assert prof.emails == ["ada@gmail.com"]
    assert prof.phones == ["+1"]
    # camelCase fields that USED to be dropped:
    assert prof.full_name == "Ada Lovelace"
    assert prof.linkedin_url == "https://www.linkedin.com/in/ada"
    assert prof.twitter == ["ada_tw"]
    assert prof.industry == "Software"
    assert prof.job_function == "Engineering"
    assert prof.work_status == "open_to_work"
    assert prof.profile_picture_url == "https://img/ada.png"


@pytest.mark.asyncio
async def test_enrich_people_forwards_all_params_and_unwraps(contactout: ContactOut) -> None:
    with respx.mock(base_url=BASE) as mock:
        route = mock.post("/v1/people/enrich").mock(
            return_value=httpx.Response(200, json={"profile": {"work_email": ["x@y.com"]}})
        )
        prof = await contactout.aenrich_people(
            first_name="Ada",
            last_name="Lovelace",
            company="Globex",
            company_domain="globex.com",
            job_title="CEO",
            location="London",
            education="Oxford",
            include=["work_email"],
        )
    body = json.loads(route.calls.last.request.content)
    assert body["first_name"] == "Ada" and body["last_name"] == "Lovelace"
    assert body["company"] == ["Globex"]  # scalar wrapped to list
    assert body["company_domain"] == ["globex.com"]
    assert body["education"] == ["Oxford"]
    assert body["job_title"] == "CEO" and body["location"] == "London"
    assert prof.work_emails == ["x@y.com"]  # unwrapped from "profile"


@pytest.mark.asyncio
async def test_find_linkedin_by_email_unwraps(contactout: ContactOut) -> None:
    with respx.mock(base_url=BASE) as mock:
        mock.get("/v1/people/person").mock(
            return_value=httpx.Response(
                200, json={"profile": {"email": "ada@x.com", "linkedin": PROFILE}}
            )
        )
        res = await contactout.afind_linkedin_by_email("ada@x.com")
    assert res == {"email": "ada@x.com", "linkedin": PROFILE}


@pytest.mark.asyncio
async def test_free_status_checks_unwrap_profile(contactout: ContactOut) -> None:
    with respx.mock(base_url=BASE) as mock:
        mock.get("/v1/people/linkedin/personal_email_status").mock(
            return_value=httpx.Response(200, json={"profile": {"email": True}})
        )
        mock.get("/v1/people/linkedin/work_email_status").mock(
            return_value=httpx.Response(
                200, json={"profile": {"email": True, "email_status": "Verified"}}
            )
        )
        mock.get("/v1/people/linkedin/phone_status").mock(
            return_value=httpx.Response(200, json={"profile": {"phone": False}})
        )
        assert await contactout.acheck_personal_email_status(PROFILE) is True
        assert await contactout.acheck_work_email_status(PROFILE) == {
            "email": True,
            "email_status": "Verified",
        }
        assert await contactout.acheck_phone_status(PROFILE) is False


@pytest.mark.asyncio
async def test_verify_email_unwraps_data(contactout: ContactOut) -> None:
    """Live shape (2026-06-24): /v1/email/verify nests the verdict under `data`."""
    with respx.mock(base_url=BASE) as mock:
        mock.get("/v1/email/verify").mock(
            return_value=httpx.Response(200, json={"status_code": 200, "data": {"status": "valid"}})
        )
        assert await contactout.averify_email("a@b.com") == {"status": "valid"}


@pytest.mark.asyncio
async def test_verify_email_tolerates_flat_shape(contactout: ContactOut) -> None:
    """Fallback: if a future response flattens the verdict, still read it."""
    with respx.mock(base_url=BASE) as mock:
        mock.get("/v1/email/verify").mock(
            return_value=httpx.Response(200, json={"status": "invalid"})
        )
        assert await contactout.averify_email("a@b.com") == {"status": "invalid"}


@pytest.mark.asyncio
async def test_bulk_v1_handles_profiles_wrapper(contactout: ContactOut) -> None:
    with respx.mock(base_url=BASE) as mock:
        mock.post("/v1/people/linkedin/batch").mock(
            return_value=httpx.Response(
                200,
                json={
                    "status_code": 200,
                    "profiles": {PROFILE: {"work_emails": ["a@co.com"], "phones": ["+1"]}},
                },
            )
        )
        out = await contactout.aget_linkedin_contact_info_bulk([PROFILE])
    assert len(out) == 1
    assert out[0].linkedin_url == PROFILE and out[0].work_emails == ["a@co.com"]


@pytest.mark.asyncio
async def test_async_bulk_reveal_and_job_poll(contactout: ContactOut) -> None:
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        post = mock.post("/v2/people/linkedin/batch").mock(
            return_value=httpx.Response(200, json={"status": "QUEUED", "job_id": "job-1"})
        )
        get = mock.get("/v2/people/linkedin/batch/job-1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "uuid": "job-1",
                        "status": "SENT",
                        "result": {PROFILE: {"emails": ["a@b.com"]}},
                    }
                },
            )
        )
        queued = await contactout.aenrich_linkedin_bulk_async([PROFILE], callback_url="https://cb")
        job = await contactout.aget_bulk_reveal_job("job-1")
    assert queued == {"status": "QUEUED", "job_id": "job-1"}
    assert job["data"]["status"] == "SENT"
    assert json.loads(post.calls.last.request.content)["callback_url"] == "https://cb"
    assert get.called


@pytest.mark.asyncio
async def test_verify_emails_bulk(contactout: ContactOut) -> None:
    with respx.mock(base_url=BASE) as mock:
        mock.post("/v1/email/verify/batch").mock(
            return_value=httpx.Response(200, json={"status": "QUEUED", "job_id": "vb-1"})
        )
        res = await contactout.averify_emails_bulk(["a@b.com", "c@d.com"])
    assert res == {"status": "QUEUED", "job_id": "vb-1"}


@pytest.mark.asyncio
async def test_validation_caps_and_required_identifiers(contactout: ContactOut) -> None:
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        route = mock.route(url__regex=r".*").mock(return_value=httpx.Response(200, json={}))
        with pytest.raises(ValidationError):
            await contactout.aget_linkedin_contact_info_bulk([f"u{i}" for i in range(101)])
        with pytest.raises(ValidationError):
            await contactout.aenrich_linkedin_bulk_async([f"u{i}" for i in range(1001)])
        with pytest.raises(ValidationError):
            await contactout.averify_emails_bulk([f"e{i}@x.com" for i in range(101)])
        with pytest.raises(ValidationError):
            await contactout.aenrich_people()  # no identifier
        with pytest.raises(ValidationError):
            await contactout.aget_decision_makers()  # none of domain/linkedin/name
    assert not route.called


@pytest.mark.asyncio
async def test_error_matrix_and_transport(contactout: ContactOut) -> None:
    with respx.mock(base_url=BASE) as mock:
        mock.get("/v1/linkedin/enrich").mock(
            return_value=httpx.Response(404, json={"status_code": 404, "message": "Not Found"})
        )
        with pytest.raises(NotFoundError):
            await contactout.aenrich_linkedin_profile(PROFILE)
    with respx.mock(base_url=BASE) as mock:
        mock.get("/v1/linkedin/enrich").mock(
            return_value=httpx.Response(429, json={"message": "slow"})
        )
        with pytest.raises(RateLimitError):
            await contactout.aenrich_linkedin_profile(PROFILE)
    with respx.mock(base_url=BASE) as mock:
        mock.get("/v1/linkedin/enrich").mock(side_effect=httpx.ConnectError("x"))
        with pytest.raises(ToolsConnectorConnectionError):
            await contactout.aenrich_linkedin_profile(PROFILE)


def test_spec_metadata() -> None:
    assert ContactOut.protocol is ProtocolType.REST
    assert ContactOut.category is ConnectorCategory.MARKETING
    # Tier 1 (live) — all 19 actions round-tripped against the production API
    # 2026-06-24 (contract-scoped; the test key returns sample DATA). See the
    # verification_status scope comment in the connector + test_spec governance.
    assert ContactOut.verification_status == "live"
    assert len(ContactOut.get_actions()) == 19


def test_normalizer_handles_all_field_variants() -> None:
    """The _profile normalizer maps every documented field-name variant."""
    # plural arrays (search/v2-batch)
    p1 = ContactOut._profile(
        {"work_emails": ["a@c.com"], "personal_emails": ["a@g.com"], "phones": ["+1"]}
    )
    assert p1.work_emails == ["a@c.com"] and p1.phones == ["+1"]
    # singular arrays (linkedin enrich)
    p2 = ContactOut._profile({"work_email": ["b@c.com"], "phone": ["+2"]})
    assert p2.work_emails == ["b@c.com"] and p2.phones == ["+2"]
    # camelCase singular string (email enrich)
    p3 = ContactOut._profile(
        {"workEmail": "c@c.com", "personalEmail": "c@g.com", "email": "c@x.com"}
    )
    assert (
        p3.work_emails == ["c@c.com"]
        and p3.personal_emails == ["c@g.com"]
        and p3.emails == ["c@x.com"]
    )
    # nested contact_info (search reveal)
    p4 = ContactOut._profile({"contact_info": {"work_emails": ["d@c.com"], "phones": ["+4"]}})
    assert p4.work_emails == ["d@c.com"] and p4.phones == ["+4"]


def test_unwrap_helper() -> None:
    assert ContactOut._unwrap({"profile": {"a": 1}}) == {"a": 1}
    assert ContactOut._unwrap({"a": 1}) == {"a": 1}  # no wrapper → passthrough


@pytest.mark.asyncio
async def test_get_usage_hits_stats_endpoint(contactout: ContactOut) -> None:
    """get_usage must call GET /v1/stats — the documented /v1/usage 404s live.

    Regression for the live-verified path bug (2026-06-24): the ContactOut
    usage/credit endpoint is /v1/stats, returning {period, usage: {...}}.
    Mocking ONLY /v1/stats (assert_all_called) proves we hit the right route —
    a request to /v1/usage would raise instead.
    """
    stats_body = {
        "status_code": 200,
        "period": {"start": "2026-06-01", "end": "2026-06-30"},
        "usage": {
            "count": 12,
            "quota": 200,
            "remaining": 188,
            "over_quota": 0,
            "phone_count": 3,
            "phone_quota": 50,
            "phone_remaining": 47,
            "search_count": 7,
            "search_quota": 500,
            "search_remaining": 493,
        },
    }
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        route = mock.get("/v1/stats").mock(return_value=httpx.Response(200, json=stats_body))
        usage = await contactout.aget_usage()

    assert route.called
    assert route.calls.last.request.headers["token"] == KEY
    assert usage["usage"]["remaining"] == 188
    assert usage["usage"]["phone_remaining"] == 47


def test_profile_captures_full_enrich_field_set() -> None:
    """The normalizer captures the FULL profile field set the live /linkedin/enrich
    envelope returns (verified 2026-06-24) — not just emails/phones."""
    raw = {
        "url": "https://www.linkedin.com/in/example-person",
        "work_email": ["w@co.com"],
        "personal_email": ["p@gmail.com"],
        "phone": ["+1"],
        "github": ["gh"],
        "twitter": ["tw"],
        "full_name": "Example Person",
        "headline": "Manager at OBM",
        "industry": "Broadcast Media",
        "company": {"name": "Legros", "domain": "legros.com"},
        "location": "Bermuda",
        "country": "United States",
        "seniority": "Manager",
        "job_function": "Design",
        "work_status": "open_to_work",
        "summary": "experienced pro",
        "followers": 1000,
        "profile_picture_url": "https://img/x.png",
        "updated_at": "2024-01-01 00:00:00",
        "experience": [{"title": "Manager", "company_name": "OBM", "is_current": False}],
        "education": [{"degree": "Journalism", "school_name": "George Brown"}],
        "skills": ["Marketing"],
        "languages": [{"name": "English", "proficiency": "Full"}],
        "certifications": [{"name": "PMP", "authority": "PMI"}],
        "publications": [{"title": "Future of Marketing"}],
        "projects": [{"title": "Website Redesign"}],
        "volunteering_experiences": [{"role": "Career Coach"}],
    }
    p = ContactOut._profile(raw)
    assert p.full_name == "Example Person" and p.linkedin_url.endswith("example-person")
    assert p.twitter == ["tw"] and p.github == ["gh"]
    assert p.industry == "Broadcast Media" and p.seniority == "Manager"
    assert p.job_function == "Design" and p.work_status == "open_to_work"
    assert p.country == "United States" and p.summary == "experienced pro"
    assert p.followers == 1000 and p.profile_picture_url == "https://img/x.png"
    assert isinstance(p.company, dict) and p.company["name"] == "Legros"
    assert p.experience[0]["title"] == "Manager" and p.education[0]["degree"] == "Journalism"
    assert p.languages[0]["name"] == "English" and p.certifications[0]["name"] == "PMP"
    assert p.publications and p.projects and p.volunteering_experiences


def test_profile_preserves_string_experience_from_search() -> None:
    """Search / decision-makers return experience+education as STRINGS — keep them
    (wrapped as {"summary": ...}) instead of silently dropping via dict_list."""
    p = ContactOut._profile(
        {
            "full_name": "Rob",
            "experience": ["CEO / Founder at ContactOut in 2015 - Present"],
            "education": ["UNSW in 2008 - 2011"],
        }
    )
    assert p.experience == [{"summary": "CEO / Founder at ContactOut in 2015 - Present"}]
    assert p.education == [{"summary": "UNSW in 2008 - 2011"}]


def test_followers_rejects_non_int() -> None:
    """followers stays None on a bad type (and bool is not an int here)."""
    assert ContactOut._profile({"followers": "lots"}).followers is None
    assert ContactOut._profile({"followers": True}).followers is None
    assert ContactOut._profile({"followers": 5}).followers == 5
