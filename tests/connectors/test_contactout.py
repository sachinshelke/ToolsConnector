"""End-to-end tests for the ContactOut connector using respx.

Pins: the `token` auth header (not Authorization), the field-name normalizer
(ContactOut's inconsistent work_email / work_emails / workEmail → canonical
work_emails/personal_emails/phones), search pagination (profiles map keyed by
URL, fixed page size 25), the free pre-flight checks, batch validation, the
error matrix, and transport-error wrapping.
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
async def test_enrich_linkedin_normalizes_singular_arrays(contactout: ContactOut) -> None:
    """The enrich endpoint uses work_email[]/personal_email[]/phone[] (singular)."""
    with respx.mock(base_url=BASE) as mock:
        route = mock.get("/v1/linkedin/enrich").mock(
            return_value=httpx.Response(
                200,
                json={
                    "full_name": "Ada",
                    "work_email": ["ada@co.com"],
                    "personal_email": ["ada@gmail.com"],
                    "phone": ["+1"],
                },
            )
        )
        prof = await contactout.aenrich_linkedin_profile(PROFILE)
    assert prof.work_emails == ["ada@co.com"] and prof.personal_emails == ["ada@gmail.com"]
    assert prof.phones == ["+1"]
    assert route.calls.last.request.url.params["profile"] == PROFILE


@pytest.mark.asyncio
async def test_enrich_by_email_normalizes_camelcase(contactout: ContactOut) -> None:
    """/email/enrich uses camelCase singular workEmail + a string email."""
    with respx.mock(base_url=BASE) as mock:
        mock.get("/v1/email/enrich").mock(
            return_value=httpx.Response(
                200,
                json={
                    "email": "ada@gmail.com",
                    "workEmail": "ada@co.com",
                    "workEmailStatus": "Verified",
                    "phone": "+1",
                },
            )
        )
        prof = await contactout.aenrich_by_email("ada@gmail.com")
    assert prof.work_emails == ["ada@co.com"]
    assert prof.emails == ["ada@gmail.com"]
    assert prof.phones == ["+1"]


@pytest.mark.asyncio
async def test_find_linkedin_by_email(contactout: ContactOut) -> None:
    with respx.mock(base_url=BASE) as mock:
        mock.get("/v1/people/person").mock(
            return_value=httpx.Response(200, json={"email": "ada@x.com", "linkedin": PROFILE})
        )
        res = await contactout.afind_linkedin_by_email("ada@x.com")
    assert res == {"email": "ada@x.com", "linkedin": PROFILE}


@pytest.mark.asyncio
async def test_free_status_checks(contactout: ContactOut) -> None:
    with respx.mock(base_url=BASE) as mock:
        mock.get("/v1/people/linkedin/personal_email_status").mock(
            return_value=httpx.Response(200, json={"email": True})
        )
        mock.get("/v1/people/linkedin/work_email_status").mock(
            return_value=httpx.Response(200, json={"email": True, "email_status": "Verified"})
        )
        mock.get("/v1/people/linkedin/phone_status").mock(
            return_value=httpx.Response(200, json={"phone": False})
        )
        assert await contactout.acheck_personal_email_status(PROFILE) is True
        assert await contactout.acheck_work_email_status(PROFILE) == {
            "email": True,
            "email_status": "Verified",
        }
        assert await contactout.acheck_phone_status(PROFILE) is False


@pytest.mark.asyncio
async def test_verify_email(contactout: ContactOut) -> None:
    with respx.mock(base_url=BASE) as mock:
        mock.get("/v1/email/verify").mock(
            return_value=httpx.Response(200, json={"status": "valid"})
        )
        assert await contactout.averify_email("a@b.com") == {"status": "valid"}


@pytest.mark.asyncio
async def test_bulk_validation_and_enrich_requires_identifier(contactout: ContactOut) -> None:
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        route = mock.route(url__regex=r".*").mock(return_value=httpx.Response(200, json={}))
        with pytest.raises(ValidationError):
            await contactout.aget_linkedin_contact_info_bulk([f"u{i}" for i in range(101)])
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
    assert ContactOut.verification_status == "doc"
    assert len(ContactOut.get_actions()) == 16


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
    p3 = ContactOut._profile({"workEmail": "c@c.com", "email": "c@g.com"})
    assert p3.work_emails == ["c@c.com"] and p3.emails == ["c@g.com"]
    # nested contact_info (search reveal)
    p4 = ContactOut._profile({"contact_info": {"work_emails": ["d@c.com"], "phones": ["+4"]}})
    assert p4.work_emails == ["d@c.com"] and p4.phones == ["+4"]
