"""End-to-end tests for the LinkedIn Lead Sync connector using respx.

The contract that makes Lead Sync fiddly — and that respx pins here:

  - **Rest.li union query encoding**: ``owner`` and ``leadType`` travel as
    ``(key:value)`` unions where the wrapper parens + key stay *literal* but
    the URN inside is percent-encoded (``urn%3Ali%3A...``). httpx must NOT
    re-encode the literal parens. ``versionedLeadGenFormUrn`` is the opposite
    — a bare URN value, fully encoded (parens → ``%28``).
  - **Versioned headers**: every call carries ``Linkedin-Version`` +
    ``X-Restli-Protocol-Version: 2.0.0``.
  - **The answer↔question join**: a lead's answers are keyed by integer
    ``questionId``; the EMAIL/PHONE meaning lives on the form. ``list_leads``
    fetches the form (once, cached) and resolves ``fields``.

Sample payloads mirror LinkedIn's published Lead Sync docs.
"""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
import respx

from toolsconnector.connectors.linkedin_leads import LinkedInLeads
from toolsconnector.connectors.linkedin_leads.types import LeadForm, LeadResponse
from toolsconnector.errors import (
    InvalidCredentialsError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    TokenExpiredError,
    ValidationError,
)
from toolsconnector.spec.connector import ConnectorCategory, ProtocolType

BASE = "https://api.linkedin.com"
TOKEN = "fake-leadsync-token"
ORG = "urn:li:organization:5509810"
ACCT = "urn:li:sponsoredAccount:522529623"
FORM_URN = "urn:li:versionedLeadGenForm:(urn:li:leadGenForm:3162,1)"

# A form whose questions give answers their meaning.
_FORM_BODY = {
    "id": 3162,
    "name": "Nimbus 2000 lead form",
    "owner": {"organization": ORG},
    "state": "PUBLISHED",
    "versionId": 1,
    "created": 1610579725356,
    "lastModified": 1610579725356,
    "content": {
        "questions": [
            {
                "questionId": 10548,
                "question": {"localized": {"en_US": "First Name"}},
                "name": "firstName",
                "predefinedField": "FIRST_NAME",
                "responseRequired": True,
            },
            {
                "questionId": 10549,
                "question": {"localized": {"en_US": "Email"}},
                "name": "email",
                "predefinedField": "EMAIL",
                "responseRequired": True,
            },
            {
                "questionId": 10550,
                "question": {"localized": {"en_US": "Phone"}},
                "name": "phone",
                "predefinedField": "PHONE_NUMBER",
                "responseRequired": False,
            },
        ],
        "legalInfo": {"privacyPolicyUrl": "https://example.com/privacy"},
    },
}


def _lead(lead_id: str, answers: list[dict]) -> dict:
    return {
        "id": lead_id,
        "owner": {"sponsoredAccount": ACCT},
        "submitter": "urn:li:person:MpGcnvaU_p",
        "versionedLeadGenFormUrn": FORM_URN,
        "leadType": "SPONSORED",
        "testLead": False,
        "submittedAt": 1686182358881,
        "leadMetadata": {
            "sponsoredLeadMetadata": {"campaign": "urn:li:sponsoredCampaign:367378525"}
        },
        "formResponse": {
            "answers": answers,
            "consentResponses": [{"accepted": True, "consentId": 4}],
        },
    }


def _text(qid: int, value: str) -> dict:
    return {"answerDetails": {"textQuestionAnswer": {"answer": value}}, "questionId": qid}


@pytest_asyncio.fixture
async def leads() -> LinkedInLeads:
    connector = LinkedInLeads(credentials=TOKEN)
    await connector._setup()
    yield connector
    await connector._teardown()


# ---------------------------------------------------------------------------
# 1. Lead forms
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_lead_forms_request_shape(leads: LinkedInLeads) -> None:
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        # The live leadForms finder returns paging WITHOUT a `total` (unlike
        # leadFormResponses) — so total_count is honestly None here.
        route = mock.get("/rest/leadForms").mock(
            return_value=httpx.Response(
                200, json={"elements": [_FORM_BODY], "paging": {"start": 0, "count": 5}}
            )
        )
        page = await leads.alist_lead_forms(owner=ORG, count=5)

    req = route.calls.last.request
    assert req.headers["linkedin-version"] == "202606"
    assert req.headers["x-restli-protocol-version"] == "2.0.0"
    q = req.url.query.decode()
    assert "q=owner" in q
    # Union wrapper parens stay literal; URN colons percent-encoded.
    assert "owner=(organization:urn%3Ali%3Aorganization%3A5509810)" in q
    assert len(page.items) == 1
    # No `total` on the forms finder → unknown count, terminate via short page.
    assert page.page_state.total_count is None
    assert page.page_state.has_more is False
    form = page.items[0]
    assert form.id == 3162
    assert form.question_map()[10549].predefined_field == "EMAIL"
    assert form.question_map()[10548].label == "First Name"


@pytest.mark.asyncio
async def test_get_lead_form_parses_questions(leads: LinkedInLeads) -> None:
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        mock.get("/rest/leadForms/3162").mock(return_value=httpx.Response(200, json=_FORM_BODY))
        form = await leads.aget_lead_form(3162)

    assert isinstance(form, LeadForm)
    assert form.name == "Nimbus 2000 lead form"
    assert form.privacy_policy_url == "https://example.com/privacy"
    preds = {q.predefined_field for q in form.questions}
    assert preds == {"FIRST_NAME", "EMAIL", "PHONE_NUMBER"}


# ---------------------------------------------------------------------------
# 2. Raw lead responses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_lead_responses_query_encoding(leads: LinkedInLeads) -> None:
    """owner + leadType unions encode correctly; optional filters wire through."""
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        route = mock.get("/rest/leadFormResponses").mock(
            return_value=httpx.Response(
                200,
                json={
                    "elements": [_lead("lead-1", [_text(10549, "ada@example.com")])],
                    "paging": {"total": 1},
                },
            )
        )
        page = await leads.alist_lead_responses(
            owner=ACCT,
            lead_type="SPONSORED",
            versioned_form_urn=FORM_URN,
            submitted_after=1686100000000,
            submitted_before=1686200000000,
            test_only=True,
            count=20,
        )

    q = route.calls.last.request.url.query.decode()
    assert "q=owner" in q
    assert "owner=(sponsoredAccount:urn%3Ali%3AsponsoredAccount%3A522529623)" in q
    assert "leadType=(leadType:SPONSORED)" in q
    assert "limitedToTestLeads=true" in q
    # versionedLeadGenFormUrn is a bare URN value → FULLY encoded (parens %28/%29).
    assert (
        "versionedLeadGenFormUrn=urn%3Ali%3AversionedLeadGenForm%3A%28urn%3Ali%3AleadGenForm%3A3162%2C1%29"
        in q
    )
    assert "submittedAtTimeRange=(start:1686100000000,end:1686200000000)" in q

    lead = page.items[0]
    assert isinstance(lead, LeadResponse)
    assert lead.submitter == "urn:li:person:MpGcnvaU_p"
    assert lead.campaign == "urn:li:sponsoredCampaign:367378525"
    assert lead.text_answers() == {10549: "ada@example.com"}
    assert lead.fields == {}  # raw finder does NOT resolve


@pytest.mark.asyncio
async def test_list_lead_responses_parses_multiple_choice(leads: LinkedInLeads) -> None:
    answers = [
        _text(10549, "ada@example.com"),
        {"answerDetails": {"multipleChoiceAnswer": {"options": [1, 3]}}, "questionId": 99},
    ]
    with respx.mock(base_url=BASE) as mock:
        mock.get("/rest/leadFormResponses").mock(
            return_value=httpx.Response(200, json={"elements": [_lead("lead-mc", answers)]})
        )
        page = await leads.alist_lead_responses(owner=ACCT)

    answers_by_q = {a.question_id: a for a in page.items[0].answers}
    assert answers_by_q[10549].text == "ada@example.com"
    assert answers_by_q[99].options == [1, 3]
    assert answers_by_q[99].text is None


@pytest.mark.asyncio
async def test_get_lead_response_encodes_id(leads: LinkedInLeads) -> None:
    lead_id = "aaaabbbb-0000-cccc-1111-dddd2222eeee-5"
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        route = mock.get(url__startswith=f"{BASE}/rest/leadFormResponses/").mock(
            return_value=httpx.Response(200, json=_lead(lead_id, [_text(10549, "x@y.com")]))
        )
        lead = await leads.aget_lead_response(lead_id)

    assert lead.id == lead_id
    assert f"/rest/leadFormResponses/{lead_id}" in route.calls.last.request.url.raw_path.decode()


# ---------------------------------------------------------------------------
# 3. Resolved leads (the answer↔form join)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_leads_resolves_fields_and_caches_form(leads: LinkedInLeads) -> None:
    """list_leads joins answers→field names and fetches each form only once."""
    lead_a = _lead(
        "lead-a",
        [_text(10548, "Ada"), _text(10549, "ada@example.com"), _text(10550, "+1-555-0100")],
    )
    lead_b = _lead("lead-b", [_text(10548, "Bob"), _text(10549, "bob@example.com")])
    with respx.mock(base_url=BASE, assert_all_called=True) as mock:
        mock.get("/rest/leadFormResponses").mock(
            return_value=httpx.Response(
                200, json={"elements": [lead_a, lead_b], "paging": {"total": 2}}
            )
        )
        form_route = mock.get("/rest/leadForms/3162").mock(
            return_value=httpx.Response(200, json=_FORM_BODY)
        )
        page = await leads.alist_leads(owner=ACCT)

    # Both leads reference the same form → fetched exactly once (cached).
    assert form_route.call_count == 1
    a, b = page.items
    assert a.fields == {
        "FIRST_NAME": "Ada",
        "EMAIL": "ada@example.com",
        "PHONE_NUMBER": "+1-555-0100",
    }
    assert b.fields == {"FIRST_NAME": "Bob", "EMAIL": "bob@example.com"}


@pytest.mark.asyncio
async def test_list_leads_falls_back_when_form_unavailable(leads: LinkedInLeads) -> None:
    """If the form fetch 403s, resolution degrades to question_<id> keys, not a crash."""
    lead = _lead("lead-x", [_text(10549, "ada@example.com")])
    with respx.mock(base_url=BASE) as mock:
        mock.get("/rest/leadFormResponses").mock(
            return_value=httpx.Response(200, json={"elements": [lead]})
        )
        mock.get("/rest/leadForms/3162").mock(
            return_value=httpx.Response(403, json={"message": "no access to form"})
        )
        page = await leads.alist_leads(owner=ACCT)

    assert page.items[0].fields == {"question_10549": "ada@example.com"}


# ---------------------------------------------------------------------------
# 4. Pagination
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pagination_offset_and_terminate(leads: LinkedInLeads) -> None:
    with respx.mock(base_url=BASE) as mock:
        mock.get("/rest/leadFormResponses").mock(
            return_value=httpx.Response(
                200, json={"elements": [_lead("l1", []), _lead("l2", [])], "paging": {"total": 5}}
            )
        )
        page = await leads.alist_lead_responses(owner=ACCT, count=2, start=0)
    assert page.page_state.has_more is True
    assert page.page_state.offset == 2
    assert page.page_state.total_count == 5

    with respx.mock(base_url=BASE) as mock:
        mock.get("/rest/leadFormResponses").mock(
            return_value=httpx.Response(200, json={"elements": [_lead("l9", [])]})
        )
        page = await leads.alist_lead_responses(owner=ACCT, count=10, start=0)
    assert page.page_state.has_more is False
    assert page.page_state.offset is None


# ---------------------------------------------------------------------------
# 5. Validation + error matrix
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bad_owner_urn_raises_validation_before_io(leads: LinkedInLeads) -> None:
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        route = mock.get(url__regex=r".*").mock(return_value=httpx.Response(200, json={}))
        with pytest.raises(ValidationError):
            await leads.alist_lead_forms(owner="urn:li:person:abc")
    assert not route.called


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,body,exc",
    [
        (401, {"message": "EXPIRED_ACCESS_TOKEN"}, TokenExpiredError),
        (401, {"message": "invalid token"}, InvalidCredentialsError),
        (403, {"message": "no role on owner"}, PermissionDeniedError),
        (404, {"message": "not found"}, NotFoundError),
        (400, {"message": "bad leadType"}, ValidationError),
        (429, {"message": "throttled"}, RateLimitError),
        (503, {"message": "down"}, ServerError),
    ],
)
async def test_error_matrix(leads: LinkedInLeads, status: int, body: dict, exc: type) -> None:
    with respx.mock(base_url=BASE) as mock:
        mock.get("/rest/leadFormResponses").mock(return_value=httpx.Response(status, json=body))
        with pytest.raises(exc):
            await leads.alist_lead_responses(owner=ACCT)


@pytest.mark.asyncio
async def test_429_carries_retry_after(leads: LinkedInLeads) -> None:
    with respx.mock(base_url=BASE) as mock:
        mock.get("/rest/leadFormResponses").mock(
            return_value=httpx.Response(
                429, headers={"Retry-After": "30"}, json={"message": "slow"}
            )
        )
        with pytest.raises(RateLimitError) as ei:
            await leads.alist_lead_responses(owner=ACCT)
    assert ei.value.retry_after_seconds == 30.0


# ---------------------------------------------------------------------------
# 6. Spec metadata
# ---------------------------------------------------------------------------


def test_spec_metadata() -> None:
    assert LinkedInLeads.protocol is ProtocolType.REST
    assert LinkedInLeads.category is ConnectorCategory.MARKETING
    assert LinkedInLeads.verification_status == "doc"  # Tier 2 until live-verified
    assert set(LinkedInLeads.get_actions().keys()) == {
        "list_lead_forms",
        "get_lead_form",
        "list_lead_responses",
        "get_lead_response",
        "list_leads",
    }


def test_read_only_no_dangerous_actions() -> None:
    """Lead Sync is read-only — no action should be flagged dangerous."""
    assert all(not a.dangerous for a in LinkedInLeads.get_actions().values())


# ---------------------------------------------------------------------------
# 7. leadType enum + owner↔leadType pairing (audit-driven)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lead_type_rejects_nonexistent_organic(leads: LinkedInLeads) -> None:
    """There is no 'ORGANIC' leadType — it must fail client-side, no HTTP."""
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        route = mock.route(url__regex=r".*").mock(return_value=httpx.Response(200, json={}))
        with pytest.raises(ValidationError) as ei:
            await leads.alist_lead_responses(owner=ORG, lead_type="ORGANIC")
    assert "ORGANIC" in str(ei.value)
    assert not route.called


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "owner,lead_type",
    [
        (ORG, "SPONSORED"),  # SPONSORED requires a sponsoredAccount owner
        (ACCT, "COMPANY"),  # organic types require an organization owner
    ],
)
async def test_owner_leadtype_pairing_enforced(leads: LinkedInLeads, owner, lead_type) -> None:
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        route = mock.route(url__regex=r".*").mock(return_value=httpx.Response(200, json={}))
        with pytest.raises(ValidationError):
            await leads.alist_lead_responses(owner=owner, lead_type=lead_type)
    assert not route.called


@pytest.mark.asyncio
async def test_organic_company_lead_type_builds_query(leads: LinkedInLeads) -> None:
    """An organic COMPANY leadType with an organization owner wires through."""
    with respx.mock(base_url=BASE) as mock:
        route = mock.get("/rest/leadFormResponses").mock(
            return_value=httpx.Response(200, json={"elements": []})
        )
        await leads.alist_lead_responses(owner=ORG, lead_type="COMPANY")
    q = route.calls.last.request.url.query.decode()
    assert "leadType=(leadType:COMPANY)" in q
    assert "owner=(organization:urn%3Ali%3Aorganization%3A5509810)" in q


# ---------------------------------------------------------------------------
# 8. Multiple-choice resolution + name-based join fallback (audit-driven)
# ---------------------------------------------------------------------------

_FORM7000_URN = "urn:li:versionedLeadGenForm:(urn:li:leadGenForm:7000,1)"
_FORM_WITH_PICKLIST = {
    "id": 7000,
    "name": "Form with a dropdown",
    "owner": {"sponsoredAccount": ACCT},
    "state": "PUBLISHED",
    "content": {
        "questions": [
            {
                "questionId": 1,
                "predefinedField": "EMAIL",
                "name": "email",
                "question": {"localized": {"en_US": "Email"}},
            },
            {
                "questionId": 2,
                "predefinedField": "",
                "name": "companySize",
                "question": {"localized": {"en_US": "Company size"}},
                "questionDetails": {
                    "multipleChoiceQuestionDetails": {
                        "options": [
                            {"id": 1, "text": {"localized": {"en_US": "1-10"}}},
                            {"id": 2, "text": {"localized": {"en_US": "11-50"}}},
                            {"id": 3, "text": {"localized": {"en_US": "51-200"}}},
                        ]
                    }
                },
            },
        ],
    },
}


def _lead7000(answers: list[dict]) -> dict:
    return {
        "id": "lead-pick",
        "owner": {"sponsoredAccount": ACCT},
        "submitter": "urn:li:person:X",
        "versionedLeadGenFormUrn": _FORM7000_URN,
        "leadType": "SPONSORED",
        "submittedAt": 1,
        "formResponse": {"answers": answers},
    }


@pytest.mark.asyncio
async def test_list_leads_resolves_multiple_choice_label(leads: LinkedInLeads) -> None:
    """A picklist answer resolves to its option LABEL in fields, not a bare id."""
    answers = [
        {
            "answerDetails": {"textQuestionAnswer": {"answer": "ada@x.io"}},
            "questionId": 1,
            "name": "email",
        },
        {
            "answerDetails": {"multipleChoiceAnswer": {"options": [2]}},
            "questionId": 2,
            "name": "companySize",
        },
    ]
    with respx.mock(base_url=BASE) as mock:
        mock.get("/rest/leadFormResponses").mock(
            return_value=httpx.Response(200, json={"elements": [_lead7000(answers)]})
        )
        mock.get("/rest/leadForms/7000").mock(
            return_value=httpx.Response(200, json=_FORM_WITH_PICKLIST)
        )
        page = await leads.alist_leads(owner=ACCT)
    assert page.items[0].fields == {"EMAIL": "ada@x.io", "companySize": "11-50"}


@pytest.mark.asyncio
async def test_list_leads_name_join_fallback(leads: LinkedInLeads) -> None:
    """If answer.questionId doesn't match the form, the join falls back to answer.name."""
    # questionId 999 is absent from the form, but the answer's name ('email') matches.
    answers = [
        {
            "answerDetails": {"textQuestionAnswer": {"answer": "grace@y.io"}},
            "questionId": 999,
            "name": "email",
        }
    ]
    with respx.mock(base_url=BASE) as mock:
        mock.get("/rest/leadFormResponses").mock(
            return_value=httpx.Response(200, json={"elements": [_lead7000(answers)]})
        )
        mock.get("/rest/leadForms/7000").mock(
            return_value=httpx.Response(200, json=_FORM_WITH_PICKLIST)
        )
        page = await leads.alist_leads(owner=ACCT)
    assert page.items[0].fields == {"EMAIL": "grace@y.io"}


# ---------------------------------------------------------------------------
# 9. Pagination traversal + time-range + transport (audit-driven hardening)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_collect_traverses_all_pages(leads: LinkedInLeads) -> None:
    """collect() must follow _fetch_next, not silently stop at page 1."""
    page1 = {"elements": [_lead("l1", []), _lead("l2", [])], "paging": {"total": 3}}
    page2 = {"elements": [_lead("l3", [])], "paging": {"total": 3}}
    seen_starts: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        start = request.url.params.get("start")
        seen_starts.append(start)
        return httpx.Response(200, json=page2 if start == "2" else page1)

    with respx.mock(base_url=BASE) as mock:
        mock.get("/rest/leadFormResponses").mock(side_effect=handler)
        first = await leads.alist_lead_responses(owner=ACCT, count=2)
        all_items = await first.collect()

    assert len(all_items) == 3  # both pages, not just the first
    assert "2" in seen_starts  # the second page was actually fetched


@pytest.mark.asyncio
async def test_pagination_total_known_full_page_terminates(leads: LinkedInLeads) -> None:
    """A full page that exactly exhausts a known total → has_more False."""
    with respx.mock(base_url=BASE) as mock:
        mock.get("/rest/leadFormResponses").mock(
            return_value=httpx.Response(
                200, json={"elements": [_lead("a", []), _lead("b", [])], "paging": {"total": 2}}
            )
        )
        page = await leads.alist_lead_responses(owner=ACCT, count=2, start=0)
    assert page.page_state.has_more is False
    assert page.page_state.offset is None


@pytest.mark.asyncio
async def test_submitted_after_only_emits_open_range(leads: LinkedInLeads) -> None:
    """A lone submitted_after is the incremental-sync case → open (start:N) range."""
    with respx.mock(base_url=BASE) as mock:
        route = mock.get("/rest/leadFormResponses").mock(
            return_value=httpx.Response(200, json={"elements": []})
        )
        await leads.alist_lead_responses(owner=ACCT, submitted_after=1700000000000)
    assert (
        "submittedAtTimeRange=(start:1700000000000)" in route.calls.last.request.url.query.decode()
    )


@pytest.mark.asyncio
async def test_submitted_before_only_raises(leads: LinkedInLeads) -> None:
    """before-only is not a valid open range (start is required) → fail loud, no request."""
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        route = mock.route(url__regex=r".*").mock(return_value=httpx.Response(200, json={}))
        with pytest.raises(ValidationError):
            await leads.alist_lead_responses(owner=ACCT, submitted_before=1700000000000)
    assert not route.called


@pytest.mark.asyncio
async def test_transport_error_wrapped_to_typed(leads: LinkedInLeads) -> None:
    from toolsconnector.errors import ConnectionError as ToolsConnectorConnectionError

    with respx.mock(base_url=BASE) as mock:
        mock.get("/rest/leadFormResponses").mock(side_effect=httpx.ConnectError("refused"))
        with pytest.raises(ToolsConnectorConnectionError):
            await leads.alist_lead_responses(owner=ACCT)
