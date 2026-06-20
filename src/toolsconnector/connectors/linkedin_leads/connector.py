"""LinkedIn Lead Sync connector — retrieve consented leads from Lead Gen Forms.

This is the **legitimate** "get people's contact details" surface. It returns
leads (name / email / phone / company / …) that members **voluntarily
submitted** by filling out *your* LinkedIn Lead Gen Forms — first-party,
consented data. It is NOT, and cannot be, an arbitrary "search any LinkedIn
member and get their email/phone" tool: LinkedIn exposes no such API, by
design. The only people returned here are those who opted into one of your
forms.

API surface (LinkedIn Marketing "Lead Sync" API, all under
``api.linkedin.com/rest``)
--------------------------------------------------------------------------
- ``GET /rest/leadForms?q=owner&owner=(...)`` — list your Lead Gen Forms
  (the question templates). Docs:
  https://learn.microsoft.com/en-us/linkedin/marketing/lead-sync/leadsync
- ``GET /rest/leadForms/{id}`` — a single form, with its question definitions.
- ``GET /rest/leadFormResponses?q=owner&owner=(...)&leadType=(leadType:...)``
  — the submitted leads. Answers reference questions by integer
  ``questionId`` only.
- ``GET /rest/leadFormResponses/{id}`` — a single lead by its response id.

Auth / access (verified against the canonical docs, 2026-06-20)
---------------------------------------------------------------
Required scope: ``r_marketing_leadgen_automation`` (granted by the
**Lead Sync API** product — which LinkedIn must *approve*; it is not
self-serve). Discovering ad accounts additionally needs ``r_ads``. The
authenticated member must hold a qualifying role on the owning Ad Account
**and** its associated Company Page (e.g. ``ACCOUNT_MANAGER`` +
``LEAD_GEN_FORMS_MANAGER`` / ``ADMINISTRATOR``) or the API returns 403.

All calls send the versioned header ``Linkedin-Version`` (pinned below) and
``X-Restli-Protocol-Version: 2.0.0``. URNs inside the Rest.li ``owner`` /
``leadType`` query unions are percent-encoded per LinkedIn's wire format.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional
from urllib.parse import quote as url_quote

import httpx

from toolsconnector.connectors._helpers import raise_typed_for_status
from toolsconnector.errors import (
    ConnectionError as ToolsConnectorConnectionError,
)
from toolsconnector.errors import (
    TimeoutError as ToolsConnectorTimeoutError,
)
from toolsconnector.errors import (
    TransportError,
    ValidationError,
)
from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import ConnectorCategory, ProtocolType, RateLimitSpec
from toolsconnector.types import PageState, PaginatedList

from .types import LeadAnswer, LeadForm, LeadFormQuestion, LeadResponse

logger = logging.getLogger("toolsconnector.linkedin_leads")

# LinkedIn Marketing API versions are monthly YYYYMM strings, valid ~12 months.
# 202606 is the current default moniker (li-lms-2026-06) as of 2026-06. When
# bumping, see the Marketing API migrations guide for schema changes.
_LINKEDIN_VERSION = "202606"

# Extracts the numeric leadGenForm id out of a versionedLeadGenForm URN,
# e.g. "urn:li:versionedLeadGenForm:(urn:li:leadGenForm:3162,1)" -> 3162.
_FORM_ID_RE = re.compile(r"leadGenForm:(\d+)")

# LinkedIn's LeadType enum (lead-sync-schema). There is NO "ORGANIC" value:
# organic forms use COMPANY (Company Page), EVENT (Event), or
# ORGANIZATION_PRODUCT (Product Page). leadType is a REQUIRED finder param, and
# the owner kind is bound to it — SPONSORED ↔ sponsoredAccount URN, every other
# type ↔ organization URN.
_LEAD_TYPES = frozenset({"SPONSORED", "COMPANY", "EVENT", "ORGANIZATION_PRODUCT"})


class LinkedInLeads(BaseConnector):
    """Retrieve consented leads from your LinkedIn Lead Gen Forms (Lead Sync API).

    BYOK OAuth 2.0 Bearer token with scope ``r_marketing_leadgen_automation``
    (the **Lead Sync API** product, which LinkedIn must approve). The token's
    member must have a qualifying role on the owning Ad Account / Company
    Page — otherwise reads return ``PermissionDeniedError`` (403).

    Typical flow:
      1. ``list_lead_forms(owner=...)`` to find your forms (``owner`` is your
         ``urn:li:organization:{id}`` or ``urn:li:sponsoredAccount:{id}``).
      2. ``list_leads(owner=...)`` to get submitted leads with their contact
         fields **already resolved** (email/phone/name labeled), or
         ``list_lead_responses(...)`` for the raw, unresolved answers.

    This connector is read-only and returns only first-party, opted-in lead
    data. It deliberately offers no "search arbitrary members" capability —
    LinkedIn provides no such API.
    """

    name = "linkedin_leads"
    display_name = "LinkedIn Lead Sync"
    category = ConnectorCategory.MARKETING
    protocol = ProtocolType.REST
    base_url = "https://api.linkedin.com"
    # Tier 2 (doc) — every endpoint, header, scope, and body shape is
    # cross-checked against LinkedIn's canonical Lead Sync docs (2026-06-20)
    # and respx-pinned. Promote to "live" once verified against real leads
    # (needs an approved Lead Sync product + a form with submissions).
    verification_status = "doc"
    description = (
        "Retrieve consented leads (name, email, phone, company, …) that "
        "members submitted to your LinkedIn Lead Gen Forms, via the Marketing "
        "Lead Sync API. BYOK OAuth 2.0; requires the approved Lead Sync API "
        "product (scope r_marketing_leadgen_automation) and a qualifying role "
        "on the owning ad account/page. Read-only; first-party opt-in data "
        "only — LinkedIn exposes no arbitrary people-search/PII API."
    )
    # Conservative advisory limit; LinkedIn enforces app + member quotas server-side.
    _rate_limit_config = RateLimitSpec(rate=5, period=1, burst=10)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=self._base_url or self.__class__.base_url,
            headers={
                "Authorization": f"Bearer {self._credentials}",
                "Content-Type": "application/json",
                "X-Restli-Protocol-Version": "2.0.0",
                "Linkedin-Version": _LINKEDIN_VERSION,
            },
            timeout=self._timeout,
        )

    async def _teardown(self) -> None:
        if hasattr(self, "_client"):
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get(self, path: str) -> Any:
        """GET ``path`` (already query-built) and return parsed JSON.

        ``path`` carries its own query string with LinkedIn's Rest.li
        encoding already applied — we pass it through untouched so httpx
        does not re-encode the literal union parens.
        """
        try:
            response = await self._client.get(path)
        except httpx.TimeoutException as exc:
            raise ToolsConnectorTimeoutError(
                f"LinkedIn Lead Sync request timed out after {self._timeout}s",
                connector=self.name,
                details={"path": path, "underlying": type(exc).__name__},
            ) from exc
        except httpx.ConnectError as exc:
            raise ToolsConnectorConnectionError(
                "Could not connect to the LinkedIn API at api.linkedin.com",
                connector=self.name,
                details={"path": path, "underlying": str(exc)},
            ) from exc
        except httpx.TransportError as exc:
            raise TransportError(
                f"LinkedIn Lead Sync transport error: {type(exc).__name__}",
                connector=self.name,
                details={"path": path, "underlying": str(exc)},
            ) from exc
        raise_typed_for_status(response, connector=self.name, action=path)
        if response.status_code == 204:
            return None
        try:
            return response.json()
        except ValueError:
            return {}

    @staticmethod
    def _owner_union(owner: str) -> str:
        """Build the Rest.li ``owner`` union, e.g.
        ``(organization:urn%3Ali%3Aorganization%3A123)``.

        The union wrapper + key stay literal; the URN is percent-encoded.
        """
        if ":organization:" in owner:
            key = "organization"
        elif ":sponsoredAccount:" in owner:
            key = "sponsoredAccount"
        else:
            raise ValidationError(
                f"owner must be a urn:li:organization:* or urn:li:sponsoredAccount:* "
                f"URN, got {owner!r}.",
                connector="linkedin_leads",
                action="owner",
            )
        return f"({key}:{url_quote(owner, safe='')})"

    @staticmethod
    def _first_localized(node: Any) -> str:
        """Flatten LinkedIn's ``{'localized': {'en_US': 'text'}}`` to its first value."""
        if isinstance(node, dict):
            loc = node.get("localized")
            if isinstance(loc, dict) and loc:
                return str(next(iter(loc.values())))
        return ""

    @classmethod
    def _parse_form(cls, d: dict[str, Any]) -> LeadForm:
        content = d.get("content") or {}
        questions: list[LeadFormQuestion] = []
        for q in content.get("questions", []) or []:
            qd = q.get("questionDetails") or {}
            mc = qd.get("multipleChoiceQuestionDetails") or {}
            options: dict[int, str] = {}
            for opt in mc.get("options", []) or []:
                oid = opt.get("id")
                if oid is not None:
                    options[oid] = cls._first_localized(opt.get("text")) or str(oid)
            questions.append(
                LeadFormQuestion(
                    question_id=q.get("questionId"),
                    name=q.get("name", "") or "",
                    predefined_field=q.get("predefinedField", "") or "",
                    label=cls._first_localized(q.get("question")),
                    required=bool(q.get("responseRequired", False)),
                    options=options,
                )
            )
        legal = content.get("legalInfo") or {}
        return LeadForm(
            id=d.get("id"),
            name=d.get("name", "") or "",
            owner=d.get("owner", {}) or {},
            state=d.get("state", "") or "",
            version_id=d.get("versionId", 0) or 0,
            created=d.get("created"),
            last_modified=d.get("lastModified"),
            questions=questions,
            hidden_fields=d.get("hiddenFields", []) or [],
            privacy_policy_url=legal.get("privacyPolicyUrl", "") or "",
        )

    @staticmethod
    def _parse_lead(d: dict[str, Any]) -> LeadResponse:
        answers: list[LeadAnswer] = []
        form_response = d.get("formResponse") or {}
        for a in form_response.get("answers", []) or []:
            details = a.get("answerDetails") or {}
            text = None
            options: list[int] = []
            if "textQuestionAnswer" in details:
                text = (details["textQuestionAnswer"] or {}).get("answer")
            elif "multipleChoiceAnswer" in details:
                options = list((details["multipleChoiceAnswer"] or {}).get("options", []) or [])
            answers.append(
                LeadAnswer(
                    question_id=a.get("questionId"),
                    name=a.get("name", "") or "",
                    text=text,
                    options=options,
                )
            )
        campaign = ((d.get("leadMetadata") or {}).get("sponsoredLeadMetadata") or {}).get(
            "campaign"
        )
        return LeadResponse(
            id=d.get("id"),
            owner=d.get("owner", {}) or {},
            submitter=d.get("submitter", "") or "",
            versioned_form_urn=d.get("versionedLeadGenFormUrn", "") or "",
            lead_type=d.get("leadType", "") or "",
            test_lead=bool(d.get("testLead", False)),
            submitted_at=d.get("submittedAt"),
            campaign=campaign,
            answers=answers,
            consent_responses=form_response.get("consentResponses", []) or [],
        )

    @staticmethod
    def _resolve_fields(lead: LeadResponse, form: Optional[LeadForm]) -> dict[str, str]:
        """Join each answer to its form question and label it.

        The join is robust: match the answer's ``question_id`` against the
        form's questions, falling back to the answer's ``name`` (LinkedIn
        echoes the question name on every answer) when the ids don't line up.
        The key prefers ``predefinedField`` (``EMAIL`` / ``PHONE_NUMBER`` / …),
        then the question ``name``, then the answer ``name``, then
        ``question_<id>``. Text answers contribute their value; multiple-choice
        answers are resolved to their option labels (joined with ``", "``).
        """
        questions = form.questions if form else []
        qmap = {q.question_id: q for q in questions}
        qby_name = {q.name: q for q in questions if q.name}
        fields: dict[str, str] = {}
        for a in lead.answers:
            q = qmap.get(a.question_id) or (qby_name.get(a.name) if a.name else None)
            if a.text is not None:
                value: Optional[str] = a.text
            elif a.options:
                value = ", ".join((q.options.get(o) if q else None) or str(o) for o in a.options)
            else:
                value = None
            if value is None:
                continue
            if q and q.predefined_field:
                key = q.predefined_field
            elif q and q.name:
                key = q.name
            elif a.name:
                key = a.name
            else:
                key = f"question_{a.question_id}"
            fields[key] = value
        return fields

    def _page_state(self, body: dict[str, Any], start: int, count: int, n_items: int) -> PageState:
        paging = (body.get("paging") or {}) if isinstance(body, dict) else {}
        total = paging.get("total")
        # `total` (present on leadFormResponses) is authoritative; fall back to
        # the page-full heuristic only when absent (the leadForms finder omits
        # it), so a full final page that exhausts `total` doesn't over-report.
        has_more = (start + n_items) < total if total is not None else n_items >= count
        return PageState(
            offset=start + n_items if has_more else None,
            has_more=has_more,
            total_count=total,
        )

    # ======================================================================
    # LEAD FORMS  (/rest/leadForms)
    # ======================================================================

    @action("List your LinkedIn Lead Gen Forms for an owner (org or ad account)")
    async def list_lead_forms(
        self,
        owner: str,
        count: int = 10,
        start: int = 0,
    ) -> PaginatedList[LeadForm]:
        """List the Lead Gen Forms owned by ``owner``.

        Endpoint: ``GET /rest/leadForms?q=owner&owner=(...)``.
        Required scope: ``r_marketing_leadgen_automation``. (``r_ads`` /
        ``rw_ads`` can read forms too, but they CANNOT read lead responses —
        so the connector as a whole still needs
        ``r_marketing_leadgen_automation``.) 403 if the token's member lacks a
        qualifying role on the owner.

        Args:
            owner: The form owner URN — ``urn:li:organization:{id}`` (organic
                forms / your Company Page) or ``urn:li:sponsoredAccount:{id}``
                (ad-account forms). Get these from Campaign Manager.
            count: Page size (1..100). Defaults to 10.
            start: Zero-based offset for pagination.

        Returns:
            A page of Lead Gen Form definitions, each with its questions.
        """
        count = max(1, min(int(count), 100))
        start = max(0, int(start))
        owner_u = self._owner_union(owner)
        path = f"/rest/leadForms?q=owner&owner={owner_u}&count={count}&start={start}"
        body = await self._get(path)
        elements = body.get("elements", []) if isinstance(body, dict) else []
        items = [self._parse_form(f) for f in elements]
        ps = self._page_state(body, start, count, len(items))
        result: PaginatedList[LeadForm] = PaginatedList(items=items, page_state=ps)
        if ps.has_more and ps.offset is not None:
            off = ps.offset
            result._fetch_next = lambda o=off: self.alist_lead_forms(
                owner=owner, count=count, start=o
            )
        return result

    @action("Get one LinkedIn Lead Gen Form by id (with its question definitions)")
    async def get_lead_form(self, form_id: int) -> LeadForm:
        """Fetch a single Lead Gen Form, including its question definitions.

        Endpoint: ``GET /rest/leadForms/{form_id}``. The returned questions
        carry the ``predefinedField`` (EMAIL / PHONE_NUMBER / …) you need to
        label raw lead answers.

        Args:
            form_id: The numeric Lead Gen Form id (e.g. ``6755260984438374400``).

        Returns:
            The form definition.
        """
        body = await self._get(f"/rest/leadForms/{int(form_id)}")
        return self._parse_form(body if isinstance(body, dict) else {})

    # ======================================================================
    # LEAD RESPONSES  (/rest/leadFormResponses)
    # ======================================================================

    async def _query_lead_responses(
        self,
        owner: str,
        *,
        lead_type: str,
        versioned_form_urn: Optional[str],
        associated_entity: Optional[str],
        submitted_after: Optional[int],
        submitted_before: Optional[int],
        test_only: bool,
        count: int,
        start: int,
    ) -> dict[str, Any]:
        """Build + issue the leadFormResponses finder; return the raw body.

        Validates ``lead_type`` against LinkedIn's enum and enforces the
        owner↔leadType pairing before issuing the request, so a wrong value
        fails fast client-side with a clear message instead of silently
        returning zero leads (the default SPONSORED would otherwise hide every
        organic lead) or an opaque 400.
        """
        lt = (lead_type or "").upper()
        if lt not in _LEAD_TYPES:
            raise ValidationError(
                f"lead_type must be one of {sorted(_LEAD_TYPES)}, got {lead_type!r}. "
                "There is no 'ORGANIC' — organic forms use COMPANY / EVENT / "
                "ORGANIZATION_PRODUCT.",
                connector=self.name,
                action="lead_type",
            )
        owner_is_sponsored = ":sponsoredAccount:" in owner
        if lt == "SPONSORED" and not owner_is_sponsored:
            raise ValidationError(
                "lead_type=SPONSORED requires a urn:li:sponsoredAccount owner (ad-account leads).",
                connector=self.name,
                action="owner",
            )
        if lt != "SPONSORED" and owner_is_sponsored:
            raise ValidationError(
                f"lead_type={lt} requires a urn:li:organization owner (organic leads).",
                connector=self.name,
                action="owner",
            )
        count = max(1, min(int(count), 100))
        start = max(0, int(start))
        parts = [
            "q=owner",
            f"owner={self._owner_union(owner)}",
            f"leadType=(leadType:{lt})",
            f"count={count}",
            f"start={start}",
        ]
        if test_only:
            parts.append("limitedToTestLeads=true")
        if versioned_form_urn:
            parts.append(f"versionedLeadGenFormUrn={url_quote(versioned_form_urn, safe='')}")
        if associated_entity:
            parts.append(f"associatedEntity={url_quote(associated_entity, safe='')}")
        if submitted_after is not None and submitted_before is not None:
            parts.append(
                f"submittedAtTimeRange=(start:{int(submitted_after)},end:{int(submitted_before)})"
            )
        elif submitted_after is not None:
            # Open-ended "since" range — LinkedIn's TimeRange requires `start`,
            # `end` is optional. This is the canonical incremental-sync pattern.
            parts.append(f"submittedAtTimeRange=(start:{int(submitted_after)})")
        elif submitted_before is not None:
            # `end` alone is not a valid open range (start is required) — fail
            # loud instead of silently returning ALL leads as if unfiltered.
            raise ValidationError(
                "submitted_before requires submitted_after — LinkedIn's "
                "submittedAtTimeRange needs a start bound.",
                connector=self.name,
                action="submittedAtTimeRange",
            )
        path = "/rest/leadFormResponses?" + "&".join(parts)
        body = await self._get(path)
        return body if isinstance(body, dict) else {}

    @action("List raw submitted leads for an owner (answers keyed by questionId)")
    async def list_lead_responses(
        self,
        owner: str,
        lead_type: str = "SPONSORED",
        versioned_form_urn: Optional[str] = None,
        associated_entity: Optional[str] = None,
        submitted_after: Optional[int] = None,
        submitted_before: Optional[int] = None,
        test_only: bool = False,
        count: int = 10,
        start: int = 0,
    ) -> PaginatedList[LeadResponse]:
        """List submitted leads, **raw** (answers keyed by ``questionId``).

        Endpoint: ``GET /rest/leadFormResponses?q=owner&owner=(...)&leadType=(leadType:...)``.
        Required scope: ``r_marketing_leadgen_automation``. Use ``list_leads``
        instead if you want the contact fields (email/phone/name) already
        resolved to labels — this method returns the unjoined answers.

        Args:
            owner: ``urn:li:sponsoredAccount:{id}`` (ads) or
                ``urn:li:organization:{id}`` (organic).
            lead_type: The lead surface, one of ``"SPONSORED"`` (ads, default;
                requires a ``sponsoredAccount`` owner), ``"COMPANY"`` (Company
                Page), ``"EVENT"`` (Event), or ``"ORGANIZATION_PRODUCT"``
                (Product Page) — the latter three require an ``organization``
                owner. There is **no** ``"ORGANIC"`` value. An invalid value,
                or an owner that doesn't match the lead type, raises
                ``ValidationError`` before any request is sent.
            versioned_form_urn: Optional filter to one form+version, e.g.
                ``urn:li:versionedLeadGenForm:(urn:li:leadGenForm:3162,1)``.
            associated_entity: Optional filter to the associated entity URN
                (e.g. a ``urn:li:sponsoredCreative:{id}``).
            submitted_after: Optional epoch-millis lower bound (inclusive).
                Must be paired with ``submitted_before``.
            submitted_before: Optional epoch-millis upper bound.
            test_only: If true, return only test leads (generated from
                Campaign Manager) — useful for verifying an integration.
            count: Page size (1..100). Defaults to 10.
            start: Zero-based offset for pagination.

        Returns:
            A page of raw leads. Each ``LeadResponse.answers`` is keyed by
            ``question_id``; ``fields`` is empty (use ``list_leads`` to fill it).
        """
        body = await self._query_lead_responses(
            owner,
            lead_type=lead_type,
            versioned_form_urn=versioned_form_urn,
            associated_entity=associated_entity,
            submitted_after=submitted_after,
            submitted_before=submitted_before,
            test_only=test_only,
            count=count,
            start=start,
        )
        elements = body.get("elements", []) if isinstance(body, dict) else []
        items = [self._parse_lead(x) for x in elements]
        ps = self._page_state(body, max(0, int(start)), count, len(items))
        result: PaginatedList[LeadResponse] = PaginatedList(items=items, page_state=ps)
        if ps.has_more and ps.offset is not None:
            off = ps.offset
            result._fetch_next = lambda o=off: self.alist_lead_responses(
                owner=owner,
                lead_type=lead_type,
                versioned_form_urn=versioned_form_urn,
                associated_entity=associated_entity,
                submitted_after=submitted_after,
                submitted_before=submitted_before,
                test_only=test_only,
                count=count,
                start=o,
            )
        return result

    @action("Get a single lead by its response id, with contact fields resolved")
    async def get_lead_response(self, lead_id: str) -> LeadResponse:
        """Fetch one lead by its response id (raw answers, unresolved).

        Endpoint: ``GET /rest/leadFormResponses/{lead_id}``. The ``lead_id``
        is the response id string (e.g.
        ``aaaabbbb-0000-cccc-1111-dddd2222eeee-5``), not a URN.

        Args:
            lead_id: The lead form response id.

        Returns:
            The lead (raw answers; ``fields`` empty).
        """
        encoded = url_quote(str(lead_id), safe="")
        body = await self._get(f"/rest/leadFormResponses/{encoded}")
        return self._parse_lead(body if isinstance(body, dict) else {})

    # ======================================================================
    # RESOLVED LEADS  (responses joined to their form's field names)
    # ======================================================================

    @action("List submitted leads with contact fields resolved (EMAIL/PHONE_NUMBER/etc.)")
    async def list_leads(
        self,
        owner: str,
        lead_type: str = "SPONSORED",
        versioned_form_urn: Optional[str] = None,
        associated_entity: Optional[str] = None,
        submitted_after: Optional[int] = None,
        submitted_before: Optional[int] = None,
        test_only: bool = False,
        count: int = 10,
        start: int = 0,
    ) -> PaginatedList[LeadResponse]:
        """List submitted leads with their contact fields **resolved**.

        Same finder as ``list_lead_responses``, but for each lead this also
        fetches the owning Lead Gen Form (once per distinct form, cached) and
        joins answers → field names, populating ``LeadResponse.fields`` with a
        clean ``{"EMAIL": "...", "PHONE_NUMBER": "...", "FIRST_NAME": "..."}``
        view. This is the action you want for "get the leads' details".

        Required scope: ``r_marketing_leadgen_automation``. Costs one extra
        ``GET /rest/leadForms/{id}`` per distinct form in the page.

        Args:
            owner: ``urn:li:sponsoredAccount:{id}`` or ``urn:li:organization:{id}``.
            lead_type: Lead surface — one of ``"SPONSORED"`` (default),
                ``"COMPANY"``, ``"EVENT"``, ``"ORGANIZATION_PRODUCT"`` (there is
                no ``"ORGANIC"``).
            versioned_form_urn: Optional single-form+version filter.
            associated_entity: Optional associated-entity URN filter.
            submitted_after: Optional epoch-millis lower bound (with ``submitted_before``).
            submitted_before: Optional epoch-millis upper bound.
            test_only: If true, only test leads.
            count: Page size (1..100). Defaults to 10.
            start: Zero-based offset for pagination.

        Returns:
            A page of leads with ``fields`` resolved to LinkedIn field names.
        """
        body = await self._query_lead_responses(
            owner,
            lead_type=lead_type,
            versioned_form_urn=versioned_form_urn,
            associated_entity=associated_entity,
            submitted_after=submitted_after,
            submitted_before=submitted_before,
            test_only=test_only,
            count=count,
            start=start,
        )
        elements = body.get("elements", []) if isinstance(body, dict) else []
        leads = [self._parse_lead(x) for x in elements]

        form_cache: dict[int, Optional[LeadForm]] = {}
        resolved: list[LeadResponse] = []
        for lead in leads:
            form = await self._form_for_lead(lead, form_cache)
            resolved.append(lead.model_copy(update={"fields": self._resolve_fields(lead, form)}))
        ps = self._page_state(body, max(0, int(start)), count, len(resolved))
        result: PaginatedList[LeadResponse] = PaginatedList(items=resolved, page_state=ps)
        if ps.has_more and ps.offset is not None:
            off = ps.offset
            result._fetch_next = lambda o=off: self.alist_leads(
                owner=owner,
                lead_type=lead_type,
                versioned_form_urn=versioned_form_urn,
                associated_entity=associated_entity,
                submitted_after=submitted_after,
                submitted_before=submitted_before,
                test_only=test_only,
                count=count,
                start=o,
            )
        return result

    async def _form_for_lead(
        self, lead: LeadResponse, cache: dict[int, Optional[LeadForm]]
    ) -> Optional[LeadForm]:
        """Fetch (and cache) the Lead Gen Form a lead was submitted to.

        Returns ``None`` if the form id can't be derived or the form fetch
        fails — resolution then falls back to ``question_<id>`` keys rather
        than dropping the lead.
        """
        match = _FORM_ID_RE.search(lead.versioned_form_urn or "")
        if not match:
            return None
        form_id = int(match.group(1))
        if form_id not in cache:
            try:
                # NB: aget_lead_form (async variant) — self.get_lead_form is the
                # auto-installed *sync* wrapper and is not awaitable.
                cache[form_id] = await self.aget_lead_form(form_id)
            except Exception as exc:  # noqa: BLE001 — best-effort enrichment
                logger.warning("lead-field resolution: form %s fetch failed: %s", form_id, exc)
                cache[form_id] = None
        return cache[form_id]
