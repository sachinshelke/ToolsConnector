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
        if page == 0:
            return httpx.Response(
                200,
                json={
                    "pagination": {"page": 0, "size": 2, "total": 3},
                    "results": [{"id": "a"}, {"id": "b"}],
                },
            )
        return httpx.Response(
            200, json={"pagination": {"page": 1, "size": 2, "total": 3}, "results": [{"id": "c"}]}
        )

    with respx.mock(base_url=BASE) as mock:
        mock.post("/v3/contacts/prospecting").mock(side_effect=handler)
        first = await lusha.aprospecting_search_contacts(filters={"contacts": {}}, page=0, size=2)
        assert first.page_state.has_more is True
        all_items = await first.collect()
    assert [c.id for c in all_items] == ["a", "b", "c"]


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
async def test_account_usage(lusha: Lusha) -> None:
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        mock.get("/v3/account/usage").mock(
            return_value=httpx.Response(200, json={"credits": {"remaining": 100}})
        )
        usage = await lusha.aget_account_usage()
    assert usage["credits"]["remaining"] == 100


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
    assert Lusha.verification_status == "doc"
    assert len(Lusha.get_actions()) == 10


def json_body(route) -> dict:
    import json as _json

    return _json.loads(route.calls.last.request.content)
