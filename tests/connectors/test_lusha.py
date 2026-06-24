"""End-to-end tests for the Lusha connector (V3) using respx.

Pins the V3 contract: the `api_key` auth header (not Authorization), the
two-step search→enrich reveal flow, typed emails/phones (with the doNotCall
flag), credit accounting from billing.creditsCharged, prospecting pagination,
batch-size validation, the error matrix, and transport-error wrapping.
"""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
import respx

from toolsconnector.connectors.lusha import Lusha
from toolsconnector.connectors.lusha.types import LushaContactResult
from toolsconnector.errors import (
    ConnectionError as ToolsConnectorConnectionError,
)
from toolsconnector.errors import (
    InvalidCredentialsError,
    RateLimitError,
    ValidationError,
)
from toolsconnector.spec.connector import ConnectorCategory, ProtocolType

BASE = "https://api.lusha.com"
KEY = "fake-lusha-key"


@pytest_asyncio.fixture
async def lusha() -> Lusha:
    connector = Lusha(credentials=KEY)
    await connector._setup()
    yield connector
    await connector._teardown()


@pytest.mark.asyncio
async def test_search_contacts_preview(lusha: Lusha) -> None:
    """search_contacts returns previews (no PII) + the api_key header."""
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        route = mock.post("/v3/contacts/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "requestId": "req-1",
                    "results": [
                        {
                            "id": "c1",
                            "firstName": "Ada",
                            "lastName": "L",
                            "has": ["emails"],
                            "canReveal": [{"field": "emails", "credits": 1}],
                        }
                    ],
                    "billing": {"creditsCharged": 0, "resultsReturned": 1},
                },
            )
        )
        res = await lusha.asearch_contacts([{"linkedinUrl": "https://linkedin.com/in/ada"}])

    assert isinstance(res, LushaContactResult)
    assert res.credits_charged == 0
    assert res.contacts[0].id == "c1"
    assert res.contacts[0].emails == []  # preview → no PII
    req = route.calls.last.request
    assert req.headers["api_key"] == KEY  # custom auth header, not Authorization
    assert "authorization" not in req.headers


@pytest.mark.asyncio
async def test_enrich_contacts_reveals_typed_email_phone(lusha: Lusha) -> None:
    """enrich_contacts returns typed emails (type) + phones (doNotCall) + credits."""
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        mock.post("/v3/contacts/enrich").mock(
            return_value=httpx.Response(
                200,
                json={
                    "requestId": "req-2",
                    "results": [
                        {
                            "id": "c1",
                            "fullName": "Ada Lovelace",
                            "emails": [
                                {"email": "ada@co.com", "type": "work", "confidence": "A+"},
                                {"email": "ada@gmail.com", "type": "private"},
                            ],
                            "phones": [
                                {"number": "+14155550100", "type": "mobile", "doNotCall": True}
                            ],
                            "location": {"isEuContact": False},
                        }
                    ],
                    "billing": {"creditsCharged": 6},
                },
            )
        )
        res = await lusha.aenrich_contacts(["c1"], reveal=["emails", "phones"])

    c = res.contacts[0]
    assert res.credits_charged == 6
    assert [(e.email, e.type) for e in c.emails] == [
        ("ada@co.com", "work"),
        ("ada@gmail.com", "private"),
    ]
    assert c.phones[0].number == "+14155550100"
    assert c.phones[0].do_not_call is True  # DNC flag surfaced


@pytest.mark.asyncio
async def test_search_and_enrich_one_shot(lusha: Lusha) -> None:
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        route = mock.post("/v3/contacts/search-and-enrich").mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [{"id": "c9", "emails": [{"email": "x@y.com", "type": "work"}]}],
                    "billing": {"creditsCharged": 2},
                },
            )
        )
        res = await lusha.asearch_and_enrich_contacts([{"email": "x@y.com"}], reveal=["emails"])
    assert res.contacts[0].emails[0].email == "x@y.com"
    assert json_body(route)["reveal"] == ["emails"]


@pytest.mark.asyncio
async def test_enrich_companies(lusha: Lusha) -> None:
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        mock.post("/v3/companies/enrich").mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {"id": "co1", "name": "Globex", "domain": "globex.com", "industry": "Tech"}
                    ],
                    "billing": {"creditsCharged": 1},
                },
            )
        )
        res = await lusha.aenrich_companies(["co1"])
    assert res.companies[0].name == "Globex"
    assert res.companies[0].domain == "globex.com"


@pytest.mark.asyncio
async def test_decision_makers_flattened(lusha: Lusha) -> None:
    with respx.mock(base_url=BASE) as mock:
        mock.post("/v3/contacts/decision-makers").mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "companyId": "co1",
                            "decisionMakers": [
                                {"id": "d1", "firstName": "A"},
                                {"id": "d2", "firstName": "B"},
                            ],
                        }
                    ],
                    "billing": {"creditsCharged": 0},
                },
            )
        )
        res = await lusha.aget_decision_makers([{"domain": "globex.com"}])
    assert {c.id for c in res.contacts} == {"d1", "d2"}


@pytest.mark.asyncio
async def test_prospecting_pagination_collects_all(lusha: Lusha) -> None:
    """prospecting_search_contacts paginates by 0-based page; collect() walks all."""

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        page = _json.loads(request.content)["pagination"]["page"]
        # total=12 with size=10 → page 0 has_more (10 < 12), page 1 terminal (20 !< 12)
        if page == 0:
            return httpx.Response(
                200,
                json={
                    "pagination": {"page": 0, "size": 10, "total": 12},
                    "results": [{"id": "a"}, {"id": "b"}],
                },
            )
        return httpx.Response(
            200, json={"pagination": {"page": 1, "size": 10, "total": 12}, "results": [{"id": "c"}]}
        )

    with respx.mock(base_url=BASE) as mock:
        mock.post("/v3/contacts/prospecting").mock(side_effect=handler)
        first = await lusha.aprospecting_search_contacts(filters={"contacts": {}}, page=0, size=10)
        assert first.page_state.has_more is True
        all_items = await first.collect()
    assert [c.id for c in all_items] == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_prospecting_size_clamped_to_min_10(lusha: Lusha) -> None:
    """Lusha 400s on size < 10 (live-verified) — the connector clamps up to 10."""
    with respx.mock(base_url=BASE) as mock:
        route = mock.post("/v3/contacts/prospecting").mock(
            return_value=httpx.Response(
                200, json={"pagination": {"page": 0, "size": 10, "total": 0}, "results": []}
            )
        )
        await lusha.aprospecting_search_contacts(filters={"contacts": {}}, size=2)
    assert json_body(route)["pagination"]["size"] == 10  # clamped up from 2


@pytest.mark.asyncio
async def test_prospecting_size_clamped_to_50(lusha: Lusha) -> None:
    with respx.mock(base_url=BASE) as mock:
        route = mock.post("/v3/companies/prospecting").mock(
            return_value=httpx.Response(
                200, json={"pagination": {"page": 0, "size": 50, "total": 0}, "results": []}
            )
        )
        await lusha.aprospecting_search_companies(filters={"companies": {}}, size=500)
    assert json_body(route)["pagination"]["size"] == 50  # clamped


@pytest.mark.asyncio
async def test_account_usage_prefers_versioned_path(lusha: Lusha) -> None:
    """Account usage hits the RICH /v3/account/usage first (live-verified 2026-06-24:
    both paths 200, but /v3 returns credits+rateLimits+plan+pricing vs the thin
    unversioned {usage:{credits}})."""
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        route = mock.get("/v3/account/usage").mock(
            return_value=httpx.Response(
                200, json={"credits": {"remaining": 100}, "plan": {"category": "free"}}
            )
        )
        usage = await lusha.aget_account_usage()
    assert usage["credits"]["remaining"] == 100
    assert usage["plan"]["category"] == "free"  # rich payload
    assert route.calls.last.request.url.path == "/v3/account/usage"


@pytest.mark.asyncio
async def test_account_usage_falls_back_to_unversioned_on_404(lusha: Lusha) -> None:
    """If /v3/account/usage 404s, fall back to the unversioned /account/usage."""
    with respx.mock(base_url=BASE) as mock:
        mock.get("/v3/account/usage").mock(return_value=httpx.Response(404, json={"message": "nf"}))
        legacy = mock.get("/account/usage").mock(
            return_value=httpx.Response(200, json={"usage": {"credits": {"remaining": 7}}})
        )
        usage = await lusha.aget_account_usage()
    assert usage["usage"]["credits"]["remaining"] == 7
    assert legacy.called


@pytest.mark.asyncio
async def test_lookalikes(lusha: Lusha) -> None:
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        c = mock.post("/v3/contacts/lookalike").mock(
            return_value=httpx.Response(
                200,
                json={
                    "dedupeSessionId": "s1",
                    "results": [{"id": "x", "firstName": "A"}],
                    "meta": {"returned": 1, "hasMore": True},
                    "billing": {"creditsCharged": 0},
                },
            )
        )
        co = mock.post("/v3/companies/lookalike").mock(
            return_value=httpx.Response(200, json={"results": [{"id": "y", "name": "Z"}]})
        )
        res = await lusha.afind_contact_lookalikes(
            seeds={"linkedinUrls": ["https://x"]}, limit=10, dedupe_session_id="s0"
        )
        await lusha.afind_company_lookalikes(seeds={"domains": ["z.com"]})
    body = json_body(c)
    assert body["seeds"] == {"linkedinUrls": ["https://x"]}
    assert body["limit"] == 10 and body["dedupeSessionId"] == "s0"
    assert res["dedupeSessionId"] == "s1" and res["meta"]["hasMore"] is True
    assert co.called


@pytest.mark.asyncio
async def test_signals_and_types(lusha: Lusha) -> None:
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        sig = mock.post("/v3/contacts/signals").mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [{"id": "c1", "promotion": [], "companyChange": []}],
                    "billing": {"creditsCharged": 1},
                },
            )
        )
        mock.get("/v3/companies/signals/types").mock(
            return_value=httpx.Response(200, json={"signalTypes": ["allSignals", "surgeInHiring"]})
        )
        filt = mock.get("/v3/companies/signals/filters/hiringByLocations").mock(
            return_value=httpx.Response(200, json={"values": ["London"]})
        )
        res = await lusha.aget_contact_signals(
            ["c1"], signal_types=["promotion"], start_date="2026-01-01"
        )
        t = await lusha.aget_company_signal_types()
        f = await lusha.aget_company_signal_filter_values("hiringByLocations", query="Lon")
    sbody = json_body(sig)
    assert sbody["ids"] == ["c1"] and sbody["signalTypes"] == ["promotion"]
    assert sbody["startDate"] == "2026-01-01"
    assert res["billing"]["creditsCharged"] == 1
    assert "surgeInHiring" in t["signalTypes"]
    assert filt.calls.last.request.url.params["query"] == "Lon"
    assert f["values"] == ["London"]


@pytest.mark.asyncio
async def test_signals_default_to_all_signals(lusha: Lusha) -> None:
    """signalTypes is REQUIRED by Lusha (omitting it 400s, live-verified) — so the
    connector defaults to ['allSignals'] when the caller passes none."""
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        c = mock.post("/v3/contacts/signals").mock(
            return_value=httpx.Response(200, json={"results": [], "billing": {"creditsCharged": 0}})
        )
        co = mock.post("/v3/companies/signals").mock(
            return_value=httpx.Response(200, json={"results": [], "billing": {"creditsCharged": 0}})
        )
        await lusha.aget_contact_signals(["c1"])
        await lusha.aget_company_signals(["co1"])
    assert json_body(c)["signalTypes"] == ["allSignals"]
    assert json_body(co)["signalTypes"] == ["allSignals"]


@pytest.mark.asyncio
async def test_company_preview_captures_has_and_can_reveal(lusha: Lusha) -> None:
    """LushaCompany now captures the preview's `has` + `canReveal` (live shape 2026-06-24)."""
    with respx.mock(base_url=BASE) as mock:
        mock.post("/v3/companies/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "requestId": "r",
                    "results": [
                        {
                            "id": "co1",
                            "name": "Adecco",
                            "has": ["emails", "phones"],
                            "canReveal": [{"field": "employeesByDepartment", "credits": 1}],
                        }
                    ],
                    "billing": {"creditsCharged": 1},
                },
            )
        )
        res = await lusha.asearch_companies([{"domain": "adeccogroup.com"}])
    co = res.companies[0]
    assert co.has == ["emails", "phones"]
    assert co.can_reveal == [{"field": "employeesByDepartment", "credits": 1}]


@pytest.mark.asyncio
async def test_prospecting_filter_discovery(lusha: Lusha) -> None:
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        route = mock.get("/v3/contacts/prospecting/filters/seniority").mock(
            return_value=httpx.Response(200, json={"values": ["Manager", "Director"]})
        )
        res = await lusha.aget_contact_prospecting_filters("seniority")
    assert res["values"] == ["Manager", "Director"]
    assert route.calls.last.request.url.path == "/v3/contacts/prospecting/filters/seniority"


@pytest.mark.asyncio
async def test_batch_validation(lusha: Lusha) -> None:
    """>100 ids fails client-side, no HTTP call."""
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        route = mock.route(url__regex=r".*").mock(return_value=httpx.Response(200, json={}))
        with pytest.raises(ValidationError):
            await lusha.aenrich_contacts([str(i) for i in range(101)])
        with pytest.raises(ValidationError):
            await lusha.asearch_contacts([])
    assert not route.called


@pytest.mark.asyncio
async def test_error_matrix_and_transport(lusha: Lusha) -> None:
    with respx.mock(base_url=BASE) as mock:
        mock.post("/v3/contacts/enrich").mock(
            return_value=httpx.Response(401, json={"message": "bad key"})
        )
        with pytest.raises(InvalidCredentialsError):
            await lusha.aenrich_contacts(["c1"])
    with respx.mock(base_url=BASE) as mock:
        mock.post("/v3/contacts/enrich").mock(
            return_value=httpx.Response(429, json={"message": "slow"})
        )
        with pytest.raises(RateLimitError):
            await lusha.aenrich_contacts(["c1"])
    with respx.mock(base_url=BASE) as mock:
        mock.post("/v3/contacts/enrich").mock(side_effect=httpx.ConnectError("x"))
        with pytest.raises(ToolsConnectorConnectionError):
            await lusha.aenrich_contacts(["c1"])


def test_spec_metadata() -> None:
    assert Lusha.protocol is ProtocolType.REST
    assert Lusha.category is ConnectorCategory.MARKETING
    # Tier 1 (live) — 16/20 actions round-tripped against the production API with
    # real data 2026-06-24 (4 bugs fixed); rest envelope-verified. See test_spec
    # governance + the connector's verification_status scope comment.
    assert Lusha.verification_status == "live"
    assert len(Lusha.get_actions()) == 20


def json_body(route) -> dict:
    import json as _json

    return _json.loads(route.calls.last.request.content)
