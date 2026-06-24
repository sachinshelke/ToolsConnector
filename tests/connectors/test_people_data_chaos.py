"""Chaos / resilience tests for the contactout + lusha connectors.

These pin the connectors' behavior under ADVERSARIAL conditions that happy-path
respx tests don't exercise: transport failures, the full HTTP error matrix,
malformed / misshapen response bodies, hostile inputs, a server echoing the
connector's own API key back, pagination loops, and lifecycle misuse.

Contract under chaos: every failure surfaces as a typed ``ToolsConnectorError``
or a graceful (possibly empty) result — never a raw ``TypeError`` / ``ValueError``
/ ``pydantic.ValidationError`` / ``httpx.*`` / hang, and never a leaked secret.

Discovered + fixed via a chaos-probe sweep (see ROADMAP "Chaos-hardening").
"""

from __future__ import annotations

import json

import httpx
import pytest
import pytest_asyncio
import respx

from toolsconnector.connectors.contactout import ContactOut
from toolsconnector.connectors.lusha import Lusha
from toolsconnector.errors import (
    ConnectionError as TCConnectionError,
)
from toolsconnector.errors import (
    TimeoutError as TCTimeoutError,
)
from toolsconnector.errors import (
    ToolsConnectorError,
    TransportError,
    ValidationError,
)

CO_BASE = "https://api.contactout.com"
LU_BASE = "https://api.lusha.com"
SECRET = (
    "co_live_8fA3kLmn92QxRtVbN1pZ7w-SECRET"  # not a recognized pattern → only self-scrub catches it
)
PROFILE = "https://www.linkedin.com/in/ada"


@pytest_asyncio.fixture
async def co() -> ContactOut:
    c = ContactOut(credentials=SECRET)
    await c._setup()
    yield c
    await c._teardown()


@pytest_asyncio.fixture
async def lu() -> Lusha:
    c = Lusha(credentials=SECRET)
    await c._setup()
    yield c
    await c._teardown()


# --------------------------------------------------------------------------
# Transport-layer failures → typed errors (no raw httpx escaping)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc,expected",
    [
        (httpx.ReadTimeout("x"), TCTimeoutError),
        (httpx.PoolTimeout("x"), TCTimeoutError),
        (httpx.WriteTimeout("x"), TCTimeoutError),
        (httpx.ConnectError("x"), TCConnectionError),
        (httpx.ReadError("x"), TransportError),
        (httpx.RemoteProtocolError("x"), TransportError),
    ],
)
@pytest.mark.asyncio
async def test_co_transport_errors_are_typed(co, exc, expected):
    with respx.mock(base_url=CO_BASE) as m:
        m.get("/v1/linkedin/enrich").mock(side_effect=exc)
        with pytest.raises(expected):
            await co.aenrich_linkedin_profile(PROFILE)


@pytest.mark.asyncio
async def test_lu_transport_error_is_typed(lu):
    with respx.mock(base_url=LU_BASE) as m:
        m.post("/v3/contacts/enrich").mock(side_effect=httpx.RemoteProtocolError("x"))
        with pytest.raises(TransportError):
            await lu.aenrich_contacts(["1"])


@pytest.mark.asyncio
async def test_invalid_url_from_control_chars_is_typed():
    """A path param with control chars must raise a typed ValidationError, not raw httpx.InvalidURL."""
    co = ContactOut(credentials=SECRET)
    await co._setup()
    lu = Lusha(credentials=SECRET)
    await lu._setup()
    try:
        with pytest.raises(ValidationError):
            await co.aget_bulk_reveal_job("bad id\nwith\ttabs")
        with pytest.raises(ValidationError):
            await lu.aget_company_signal_filter_values("bad\ntype")
    finally:
        await co._teardown()
        await lu._teardown()


# --------------------------------------------------------------------------
# HTTP status matrix → typed errors
# --------------------------------------------------------------------------


@pytest.mark.parametrize("code", [400, 401, 403, 404, 409, 422, 423, 429, 451, 500, 502, 503, 504])
@pytest.mark.asyncio
async def test_co_status_matrix_is_typed(co, code):
    with respx.mock(base_url=CO_BASE) as m:
        m.get("/v1/linkedin/enrich").mock(return_value=httpx.Response(code, json={"message": "x"}))
        with pytest.raises(ToolsConnectorError):
            await co.aenrich_linkedin_profile(PROFILE)


@pytest.mark.asyncio
async def test_co_302_redirect_not_followed_graceful(co):
    """follow_redirects is off → a 302 yields a graceful empty result, not a crash/leak."""
    with respx.mock(base_url=CO_BASE) as m:
        m.get("/v1/linkedin/enrich").mock(
            return_value=httpx.Response(302, headers={"location": "https://evil/x"})
        )
        prof = await co.aenrich_linkedin_profile(PROFILE)
    assert prof.work_emails == [] and prof.personal_emails == []


# --------------------------------------------------------------------------
# Malformed bodies on a 200 → graceful empty
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "resp",
    [
        httpx.Response(200, content=b""),
        httpx.Response(200, content=b"<html>oops</html>"),
        httpx.Response(200, json=[]),
        httpx.Response(200, json=None),
        httpx.Response(200, json=42),
    ],
)
@pytest.mark.asyncio
async def test_co_malformed_body_is_graceful(co, resp):
    with respx.mock(base_url=CO_BASE) as m:
        m.get("/v1/linkedin/enrich").mock(return_value=resp)
        prof = await co.aenrich_linkedin_profile(PROFILE)
    assert prof.work_emails == []  # no crash, empty profile


# --------------------------------------------------------------------------
# Wrong response SHAPE → graceful (no TypeError / pydantic crash)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_co_malformed_list_fields_graceful(co):
    with respx.mock(base_url=CO_BASE) as m:
        m.get("/v1/linkedin/enrich").mock(
            return_value=httpx.Response(
                200,
                json={
                    "profile": {
                        "experience": "notalist",  # bare string, not a list → dropped
                        "education": [1, 2, 3],  # non-str/non-dict items → dropped
                        "work_email": 12345,  # int, not a list → dropped
                    }
                },
            )
        )
        prof = await co.aenrich_linkedin_profile(PROFILE)
    # No crash; truly-malformed shapes drop to empty. (A list of STRINGS is NOT
    # malformed — search returns experience/education that way — so it's kept.)
    assert prof.experience == [] and prof.education == [] and prof.work_emails == []


@pytest.mark.asyncio
async def test_co_string_total_results_graceful(co):
    with respx.mock(base_url=CO_BASE) as m:
        m.post("/v1/people/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "metadata": {"total_results": "many", "page_size": "x"},
                    "profiles": {PROFILE: {"full_name": "A"}},
                },
            )
        )
        page = await co.asearch_people(filters={})
    assert page.items[0].full_name == "A"
    assert page.page_state.has_more is False  # non-numeric total → paging disabled, no TypeError


@pytest.mark.asyncio
async def test_lu_string_credits_and_bad_emails_graceful(lu):
    with respx.mock(base_url=LU_BASE) as m:
        m.post("/v3/contacts/enrich").mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {"id": "1", "emails": {"email": "a@b.com"}},  # emails as dict
                        {"id": "2", "emails": [{"email": "ok@b.com", "type": "work"}]},
                    ],
                    "billing": {"creditsCharged": "abc"},
                },  # non-numeric credits
            )
        )
        res = await lu.aenrich_contacts(["1", "2"])
    assert res.credits_charged == 0  # non-numeric → default, no ValueError
    # contact 1 (malformed emails) dropped; contact 2 survives
    assert [c.id for c in res.contacts] == ["2"]


@pytest.mark.asyncio
async def test_lu_nonlist_results_and_nondict_billing_graceful(lu):
    with respx.mock(base_url=LU_BASE) as m:
        m.post("/v3/contacts/enrich").mock(
            return_value=httpx.Response(200, json={"results": 5, "billing": "n/a"})
        )
        res = await lu.aenrich_contacts(["1"])
    assert res.contacts == [] and res.credits_charged == 0


@pytest.mark.asyncio
async def test_lu_prospecting_string_total_graceful(lu):
    with respx.mock(base_url=LU_BASE) as m:
        m.post("/v3/contacts/prospecting").mock(
            return_value=httpx.Response(200, json={"pagination": {"total": "9"}, "results": []})
        )
        page = await lu.aprospecting_search_contacts(filters={"contacts": {}})
    assert page.page_state.has_more is False  # no TypeError on '<' int vs str


# --------------------------------------------------------------------------
# Hostile caller input → typed ValidationError (not TypeError)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_co_nondict_filters_raise_validation(co):
    with respx.mock(base_url=CO_BASE, assert_all_called=False) as m:
        route = m.route(url__regex=r".*").mock(return_value=httpx.Response(200, json={}))
        with pytest.raises(ValidationError):
            await co.asearch_people(filters="not-a-dict")
        with pytest.raises(ValidationError):
            await co.acount_people("not-a-dict")
        with pytest.raises(ValidationError):
            await co.asearch_companies("not-a-dict")
    assert not route.called  # rejected before any HTTP call


# --------------------------------------------------------------------------
# CREDENTIAL LEAK — the connector's own key echoed back must NOT surface
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_co_credential_not_leaked_when_echoed(co):
    with respx.mock(base_url=CO_BASE) as m:
        m.get("/v1/linkedin/enrich").mock(
            return_value=httpx.Response(
                401, json={"message": f"invalid token {SECRET}", "echo": SECRET}
            )
        )
        with pytest.raises(ToolsConnectorError) as ei:
            await co.aenrich_linkedin_profile(PROFILE)
    _assert_no_secret(ei.value)


@pytest.mark.asyncio
async def test_lu_credential_not_leaked_when_echoed(lu):
    with respx.mock(base_url=LU_BASE) as m:
        m.post("/v3/contacts/enrich").mock(
            return_value=httpx.Response(403, json={"message": f"bad api_key {SECRET}"})
        )
        with pytest.raises(ToolsConnectorError) as ei:
            await lu.aenrich_contacts(["1"])
    _assert_no_secret(ei.value)


def _assert_no_secret(exc: ToolsConnectorError) -> None:
    haystack = str(exc) + json.dumps(exc.to_dict(), default=str)
    assert SECRET not in haystack, f"secret leaked in {type(exc).__name__}"
    assert "[REDACTED]" in haystack  # confirms it WAS present and got scrubbed


# --------------------------------------------------------------------------
# Pagination loop guard — empty page must not spin collect() forever
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_co_empty_page_does_not_loop(co):
    """An empty page with a huge total must set has_more=False (no infinite collect())."""
    with respx.mock(base_url=CO_BASE) as m:
        m.post("/v1/people/search").mock(
            return_value=httpx.Response(
                200, json={"metadata": {"page_size": 25, "total_results": 10**9}, "profiles": {}}
            )
        )
        page = await co.asearch_people(filters={})
        items = await page.collect()  # must terminate
    assert items == []
    assert page.page_state.has_more is False


@pytest.mark.asyncio
async def test_lu_empty_prospecting_page_does_not_loop(lu):
    with respx.mock(base_url=LU_BASE) as m:
        m.post("/v3/contacts/prospecting").mock(
            return_value=httpx.Response(
                200, json={"pagination": {"size": 50, "total": 50000}, "results": []}
            )
        )
        page = await lu.aprospecting_search_contacts(filters={"contacts": {}})
        items = await page.collect()
    assert items == []
    assert page.page_state.has_more is False


# --------------------------------------------------------------------------
# Lifecycle misuse → typed error, not raw RuntimeError
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_co_action_after_teardown_is_typed():
    c = ContactOut(credentials=SECRET)
    await c._setup()
    await c._teardown()
    with respx.mock(base_url=CO_BASE), pytest.raises(TCConnectionError):
        await c.aenrich_linkedin_profile(PROFILE)
