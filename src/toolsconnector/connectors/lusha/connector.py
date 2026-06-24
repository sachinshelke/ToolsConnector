"""Lusha connector — B2B contact + company data via Lusha's official V3 API.

BYOK wrapper over **Lusha's own paid API** (the developer brings their Lusha
API key). ToolsConnector performs no scraping — it calls Lusha's documented
endpoints with the user's key; Lusha sources the data and is the data
controller under its own terms.

V3 reveal flow is two-step:
  1. ``search_contacts`` → a non-PII preview + Lusha ``id`` + ``canReveal``
     (what an enrich would return, and its credit cost).
  2. ``enrich_contacts`` (or the one-shot ``search_and_enrich_contacts``) →
     reveals ``emails`` and ``phones``.

Auth: the API key travels in a custom ``api_key`` header (NOT ``Authorization``).
Pricing is credit-based — each response reports real spend in
``billing.creditsCharged`` (email = 1, phone = 5), surfaced on the result.

⚠️ This returns third-party personal data (emails, phone numbers). The caller
is responsible for lawful basis (GDPR legitimate-interest / CCPA), honoring the
``doNotCall`` flag on phones and ``location.isEuContact``, and their own
outreach compliance. See README.

Docs: https://docs.lusha.com (V3). V2 sunsets 2026-11-18 — this targets V3.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from toolsconnector.connectors._helpers import (
    coerce_optional_int,
    raise_typed_for_status,
    safe_int,
    scrub_secret,
    validate_list,
)
from toolsconnector.errors import (
    ConnectionError as ToolsConnectorConnectionError,
)
from toolsconnector.errors import (
    NotFoundError,
    ToolsConnectorError,
    TransportError,
    ValidationError,
)
from toolsconnector.errors import (
    TimeoutError as ToolsConnectorTimeoutError,
)
from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import ConnectorCategory, ProtocolType, RateLimitSpec
from toolsconnector.types import PageState, PaginatedList

from .types import LushaCompany, LushaCompanyResult, LushaContact, LushaContactResult

logger = logging.getLogger("toolsconnector.lusha")

_MAX_BATCH = 100  # Lusha caps batch identifier lists at 100 per request.
_MAX_PAGE_SIZE = 50  # prospecting page size hard cap.
_MIN_PAGE_SIZE = 10  # prospecting floor — Lusha 400s on `pagination.size < 10` (live-verified).


class Lusha(BaseConnector):
    """Look up B2B contacts + companies via Lusha's official V3 API (BYOK).

    Requires a Lusha API key (``credentials``) on a paid plan — generate it in
    the Lusha dashboard (API settings). Sent as the ``api_key`` header.

    The two-step reveal flow keeps you in control of spend: ``search_*`` is a
    cheap preview, ``enrich_*`` is where emails/phones (and credits) happen.
    Read ``credits_charged`` on every result to track cost.

    Returns third-party PII — you own lawful basis + DNC/opt-out handling.
    """

    name = "lusha"
    display_name = "Lusha"
    category = ConnectorCategory.MARKETING
    protocol = ProtocolType.REST
    base_url = "https://api.lusha.com"
    # Tier 1 (live) — verified end-to-end against the PRODUCTION API
    # (api.lusha.com) with a real key on 2026-06-24: 16/20 actions round-tripped
    # with REAL data (actual email + phone reveals via enrich, real firmographics,
    # prospecting, contact signals), spending real credits. Found + fixed 4 live
    # bugs: get_account_usage returned the thin /account/usage instead of the rich
    # /v3/account/usage; prospecting clamped size below Lusha's floor of 10 (→400);
    # get_*_signals omitted the REQUIRED signalTypes (→400); LushaCompany dropped
    # has/canReveal. The other 4 are envelope-verified (request accepted, upstream
    # constraint returned): company-signals is plan-gated (HTTP 402 on free),
    # contact/company lookalikes need >=5 seeds, decision-makers returned empty for
    # the test domain.
    verification_status = "live"
    description = (
        "B2B contact + company data via Lusha's official V3 API (BYOK paid key). "
        "Resolve people by name+company / email / LinkedIn URL and reveal their "
        "work/personal emails + phone numbers (two-step search→enrich, or one-shot "
        "search_and_enrich), enrich companies, and run filter-based prospecting. "
        "Returns third-party PII (honor doNotCall / isEuContact); credit spend is "
        "reported per call. Wraps Lusha's own API — no scraping."
    )
    _rate_limit_config = RateLimitSpec(rate=20, period=1, burst=10)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=self._base_url or self.__class__.base_url,
            headers={
                # Lusha's auth is a custom `api_key` header — NOT Authorization.
                "api_key": str(self._credentials),
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=self._timeout,
        )

    async def _teardown(self) -> None:
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
        json_body: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        try:
            try:
                response = await self._client.request(method, path, json=json_body, params=params)
            except httpx.InvalidURL as exc:
                raise ValidationError(
                    f"Invalid request URL for Lusha {path} (bad path/query value): {exc}",
                    connector=self.name,
                    action=path,
                ) from exc
            except httpx.TimeoutException as exc:
                raise ToolsConnectorTimeoutError(
                    f"Lusha API request timed out after {self._timeout}s",
                    connector=self.name,
                    details={"method": method, "path": path, "underlying": type(exc).__name__},
                ) from exc
            except httpx.ConnectError as exc:
                raise ToolsConnectorConnectionError(
                    "Could not connect to the Lusha API at api.lusha.com",
                    connector=self.name,
                    details={"method": method, "path": path, "underlying": str(exc)},
                ) from exc
            except httpx.TransportError as exc:
                raise TransportError(
                    f"Lusha API transport error: {type(exc).__name__}",
                    connector=self.name,
                    details={"method": method, "path": path, "underlying": str(exc)},
                ) from exc
            except httpx.HTTPError as exc:
                # Any other httpx error not under TransportError (DecodingError,
                # TooManyRedirects, …) — keep it inside the typed boundary.
                raise TransportError(
                    f"Lusha API request error: {type(exc).__name__}",
                    connector=self.name,
                    details={"method": method, "path": path, "underlying": str(exc)},
                ) from exc
            except RuntimeError as exc:
                # e.g. "Cannot send a request, as the client has been closed."
                raise ToolsConnectorConnectionError(
                    "Lusha client is not usable (closed or not initialized)",
                    connector=self.name,
                    details={"method": method, "path": path, "underlying": str(exc)},
                ) from exc
            raise_typed_for_status(response, connector=self.name, action=path)
            if response.status_code == 204:
                return {}
            try:
                body = response.json()
            except ValueError:
                return {}
            return body if isinstance(body, dict) else {}
        except ToolsConnectorError as exc:
            # Scrub the connector's OWN credential if a misbehaving upstream
            # echoed it back (the pattern-based redactor can't know a custom key).
            scrub_secret(exc, self._credentials)
            raise

    @staticmethod
    def _validate_batch(items: list[Any], field: str) -> None:
        if not items:
            raise ValidationError(
                f"{field} must be a non-empty list", connector="lusha", action=field
            )
        if len(items) > _MAX_BATCH:
            raise ValidationError(
                f"{field} accepts at most {_MAX_BATCH} items per request, got {len(items)}",
                connector="lusha",
                action=field,
            )

    @staticmethod
    def _contact_result(body: dict[str, Any]) -> LushaContactResult:
        results = body.get("results")
        results = results if isinstance(results, list) else []
        valid = [r for r in results if isinstance(r, dict) and not r.get("error")]
        billing = body.get("billing") if isinstance(body.get("billing"), dict) else {}
        return LushaContactResult(
            request_id=str(body.get("requestId") or ""),
            contacts=validate_list(LushaContact, valid),
            credits_charged=safe_int(billing.get("creditsCharged"), 0),
        )

    @staticmethod
    def _company_result(body: dict[str, Any]) -> LushaCompanyResult:
        results = body.get("results")
        results = results if isinstance(results, list) else []
        valid = [r for r in results if isinstance(r, dict) and not r.get("error")]
        billing = body.get("billing") if isinstance(body.get("billing"), dict) else {}
        return LushaCompanyResult(
            request_id=str(body.get("requestId") or ""),
            companies=validate_list(LushaCompany, valid),
            credits_charged=safe_int(billing.get("creditsCharged"), 0),
        )

    # ======================================================================
    # CONTACTS
    # ======================================================================

    @action("Search/resolve people and get a non-PII preview (no emails/phones)")
    async def search_contacts(self, contacts: list[dict[str, Any]]) -> LushaContactResult:
        """Resolve people to Lusha ids — step 1 of the reveal flow (no PII, no reveal cost).

        Endpoint: ``POST /v3/contacts/search``.

        Args:
            contacts: Up to 100 identifier objects, each using ONE of:
                ``{"id": ...}``, ``{"linkedinUrl": ...}``, ``{"email": ...}``,
                or ``{"firstName": ..., "lastName": ..., "companyName": ...}``
                (or ``companyDomain``). Optional ``clientReferenceId`` per item
                is echoed back for correlation.

        Returns:
            Preview contacts with ``id`` + ``can_reveal`` (feed the ids to
            ``enrich_contacts``). ``emails``/``phones`` are empty at this step.
        """
        self._validate_batch(contacts, "contacts")
        body = await self._request("POST", "/v3/contacts/search", json_body={"contacts": contacts})
        return self._contact_result(body)

    @action("Reveal emails + phones for contact ids from search_contacts")
    async def enrich_contacts(
        self, ids: list[str], reveal: Optional[list[str]] = None
    ) -> LushaContactResult:
        """Reveal emails and phones for contact ids — step 2 (spends credits).

        Endpoint: ``POST /v3/contacts/enrich``.

        Args:
            ids: Up to 100 contact id strings from ``search_contacts``.
            reveal: Subset of ``["emails", "phones"]``. Omit for both. Each
                revealed email costs 1 credit; each phone, 5.

        Returns:
            Enriched contacts with ``emails`` (type work/private) and ``phones``
            (with the ``do_not_call`` flag). Check ``credits_charged``.
        """
        self._validate_batch(ids, "ids")
        payload: dict[str, Any] = {"ids": ids}
        if reveal is not None:
            payload["reveal"] = reveal
        body = await self._request("POST", "/v3/contacts/enrich", json_body=payload)
        return self._contact_result(body)

    @action("One-call person lookup → reveal emails + phones (search + enrich)")
    async def search_and_enrich_contacts(
        self, contacts: list[dict[str, Any]], reveal: Optional[list[str]] = None
    ) -> LushaContactResult:
        """Resolve + reveal in one call — the classic 'Person API' use case.

        Endpoint: ``POST /v3/contacts/search-and-enrich``. Bills twice (search
        + per revealed datapoint).

        Args:
            contacts: Up to 100 identifier objects (same shape as
                ``search_contacts``: id / linkedinUrl / email / name+company).
            reveal: Subset of ``["emails", "phones"]``; omit for both.

        Returns:
            Enriched contacts (emails + phones) and the credit spend.
        """
        self._validate_batch(contacts, "contacts")
        payload: dict[str, Any] = {"contacts": contacts}
        if reveal is not None:
            payload["reveal"] = reveal
        body = await self._request("POST", "/v3/contacts/search-and-enrich", json_body=payload)
        return self._contact_result(body)

    @action("Find decision-makers at given companies (preview; enrich for PII)")
    async def get_decision_makers(self, companies: list[dict[str, Any]]) -> LushaContactResult:
        """Return ranked decision-makers per company (preview, no PII until enriched).

        Endpoint: ``POST /v3/contacts/decision-makers`` (beta).

        Args:
            companies: Identifier objects, each ONE of ``{"domain": ...}`` or
                ``{"id": ...}``.

        Returns:
            Flattened decision-maker preview contacts (feed ``id`` to
            ``enrich_contacts`` to reveal emails/phones).
        """
        self._validate_batch(companies, "companies")
        body = await self._request(
            "POST", "/v3/contacts/decision-makers", json_body={"companies": companies}
        )
        groups = body.get("results")
        raw_dms: list[Any] = []
        for group in groups if isinstance(groups, list) else []:
            if not isinstance(group, dict):
                continue
            dms = group.get("decisionMakers")
            if isinstance(dms, list):
                raw_dms.extend(dms)
        billing = body.get("billing") if isinstance(body.get("billing"), dict) else {}
        return LushaContactResult(
            request_id=str(body.get("requestId") or ""),
            contacts=validate_list(LushaContact, raw_dms),
            credits_charged=safe_int(billing.get("creditsCharged"), 0),
        )

    # ======================================================================
    # COMPANIES
    # ======================================================================

    @action("Resolve companies and get a firmographic preview")
    async def search_companies(self, companies: list[dict[str, Any]]) -> LushaCompanyResult:
        """Resolve companies to Lusha ids — step 1 of company enrichment.

        Endpoint: ``POST /v3/companies/search``.

        Args:
            companies: Up to 100 identifier objects, each ONE of ``{"id": ...}``,
                ``{"name": ...}``, or ``{"domain": ...}``.

        Returns:
            Company previews with ``id`` (feed to ``enrich_companies``).
        """
        self._validate_batch(companies, "companies")
        body = await self._request(
            "POST", "/v3/companies/search", json_body={"companies": companies}
        )
        return self._company_result(body)

    @action("Reveal full firmographics for company ids from search_companies")
    async def enrich_companies(self, ids: list[str]) -> LushaCompanyResult:
        """Reveal full firmographic data for company ids.

        Endpoint: ``POST /v3/companies/enrich``. Returns company data
        (industry, size, location, funding, technologies, …) — NOT personal
        contact email/phone.

        Args:
            ids: Up to 100 company id strings from ``search_companies``.

        Returns:
            Enriched companies + credit spend.
        """
        self._validate_batch(ids, "ids")
        body = await self._request("POST", "/v3/companies/enrich", json_body={"ids": ids})
        return self._company_result(body)

    @action("One-call company lookup → full firmographics")
    async def search_and_enrich_companies(
        self, companies: list[dict[str, Any]]
    ) -> LushaCompanyResult:
        """Resolve + enrich companies in one call.

        Endpoint: ``POST /v3/companies/search-and-enrich``.

        Args:
            companies: Up to 100 identifier objects (id / name / domain).

        Returns:
            Enriched companies + credit spend.
        """
        self._validate_batch(companies, "companies")
        body = await self._request(
            "POST", "/v3/companies/search-and-enrich", json_body={"companies": companies}
        )
        return self._company_result(body)

    # ======================================================================
    # PROSPECTING  (filter-based discovery, paginated)
    # ======================================================================

    @action("Discover NEW contacts by ICP filters (paginated preview; enrich for PII)")
    async def prospecting_search_contacts(
        self,
        filters: dict[str, Any],
        page: int = 0,
        size: int = 50,
        options: Optional[dict[str, Any]] = None,
    ) -> PaginatedList[LushaContact]:
        """Filter-based discovery of new contacts (the bulk 'Search' API).

        Endpoint: ``POST /v3/contacts/prospecting``. Returns non-PII previews +
        ids — call ``enrich_contacts`` to reveal. Max 50,000 results/query.

        Args:
            filters: The ``filters`` object — ``contacts`` and ``companies``
                ``include``/``exclude`` blocks (departments, locations,
                seniority, jobTitles, company sizes/industries/technologies, …).
            page: 0-based page number.
            size: Page size (1..50).
            options: Optional ``options`` (e.g. ``excludeDnc``,
                ``maxContactsPerCompany``, ``includePartialProfiles``).

        Returns:
            A page of preview contacts; ``collect()`` walks all pages.
        """
        size = max(_MIN_PAGE_SIZE, min(int(size), _MAX_PAGE_SIZE))
        page = max(0, int(page))
        payload: dict[str, Any] = {"pagination": {"page": page, "size": size}, "filters": filters}
        if options:
            payload["options"] = options
        body = await self._request("POST", "/v3/contacts/prospecting", json_body=payload)
        items = validate_list(LushaContact, body.get("results"))
        paging = body.get("pagination") if isinstance(body.get("pagination"), dict) else {}
        total = coerce_optional_int(paging.get("total"))
        # `bool(items)` guards an empty page with total still ahead from spinning collect().
        has_more = bool(items) and total is not None and ((page + 1) * size) < total
        result: PaginatedList[LushaContact] = PaginatedList(
            items=items,
            page_state=PageState(page_number=page, has_more=has_more, total_count=total),
        )
        if has_more:
            nxt = page + 1
            result._fetch_next = lambda p=nxt: self.aprospecting_search_contacts(
                filters=filters, page=p, size=size, options=options
            )
        return result

    @action("Discover NEW companies by firmographic filters (paginated)")
    async def prospecting_search_companies(
        self,
        filters: dict[str, Any],
        page: int = 0,
        size: int = 50,
        options: Optional[dict[str, Any]] = None,
    ) -> PaginatedList[LushaCompany]:
        """Filter-based discovery of new companies.

        Endpoint: ``POST /v3/companies/prospecting``.

        Args:
            filters: The ``filters.companies`` include/exclude block (locations,
                sizes, industries, technologies, revenue, intent, signals).
            page: 0-based page number.
            size: Page size (1..50).
            options: Optional ``options`` block.

        Returns:
            A page of company previews; ``collect()`` walks all pages.
        """
        size = max(_MIN_PAGE_SIZE, min(int(size), _MAX_PAGE_SIZE))
        page = max(0, int(page))
        payload: dict[str, Any] = {"pagination": {"page": page, "size": size}, "filters": filters}
        if options:
            payload["options"] = options
        body = await self._request("POST", "/v3/companies/prospecting", json_body=payload)
        items = validate_list(LushaCompany, body.get("results"))
        paging = body.get("pagination") if isinstance(body.get("pagination"), dict) else {}
        total = coerce_optional_int(paging.get("total"))
        # `bool(items)` guards an empty page with total still ahead from spinning collect().
        has_more = bool(items) and total is not None and ((page + 1) * size) < total
        result: PaginatedList[LushaCompany] = PaginatedList(
            items=items,
            page_state=PageState(page_number=page, has_more=has_more, total_count=total),
        )
        if has_more:
            nxt = page + 1
            result._fetch_next = lambda p=nxt: self.aprospecting_search_companies(
                filters=filters, page=p, size=size, options=options
            )
        return result

    # ======================================================================
    # ACCOUNT
    # ======================================================================

    @action("Get remaining/consumed Lusha credit balances for the account")
    async def get_account_usage(self) -> dict[str, Any]:
        """Report credit usage/quota for the account. Throttled to 5 req/min. No PII.

        Live-verified 2026-06-24: BOTH paths return 200, but with DIFFERENT
        shapes — ``GET /v3/account/usage`` is the RICH one (``{credits,
        rateLimits, plan, pricing}``) while the unversioned ``GET /account/usage``
        returns only ``{usage: {credits: {total, used, remaining}}}``. So we
        prefer the versioned path (and fall back to the unversioned one on 404).

        Returns:
            The raw usage payload — ``credits`` (remaining/used/total), plus
            ``rateLimits`` / ``plan`` / ``pricing`` from the versioned endpoint.
        """
        try:
            return await self._request("GET", "/v3/account/usage")
        except NotFoundError:
            return await self._request("GET", "/account/usage")

    # ======================================================================
    # LOOKALIKES  (find new contacts/companies similar to seeds)
    # ======================================================================

    @action("Find NEW contacts similar to seed people (AI lookalikes)")
    async def find_contact_lookalikes(
        self,
        seeds: dict[str, Any],
        exclude: Optional[dict[str, Any]] = None,
        limit: Optional[int] = None,
        dedupe_session_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Find new contacts similar to seed people (non-PII previews + ids).

        Endpoint: ``POST /v3/contacts/lookalike``. Feed result ``id``s to
        ``enrich_contacts`` to reveal emails/phones.

        Args:
            seeds: Reference people, e.g.
                ``{"linkedinUrls": [...], "emails": [...], "ids": [...]}``.
            exclude: Optional ``{"emails": [...]}`` to exclude.
            limit: Max results to return.
            dedupe_session_id: Pass the ``dedupeSessionId`` from a prior call to
                page further without repeats.

        Returns:
            Raw payload: ``dedupeSessionId``, ``results`` (id/firstName/lastName),
            ``meta`` (returned/hasMore), ``billing.creditsCharged``.
        """
        payload: dict[str, Any] = {"seeds": seeds}
        if exclude is not None:
            payload["exclude"] = exclude
        if limit is not None:
            payload["limit"] = int(limit)
        if dedupe_session_id is not None:
            payload["dedupeSessionId"] = dedupe_session_id
        return await self._request("POST", "/v3/contacts/lookalike", json_body=payload)

    @action("Find NEW companies similar to seed companies (AI lookalikes)")
    async def find_company_lookalikes(
        self,
        seeds: dict[str, Any],
        exclude: Optional[dict[str, Any]] = None,
        limit: Optional[int] = None,
        dedupe_session_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Find new companies similar to seed companies.

        Endpoint: ``POST /v3/companies/lookalike``.

        Args:
            seeds: e.g. ``{"domains": [...], "linkedinUrls": [...]}``.
            exclude: Optional ``{"domains": [...]}``.
            limit: Max results.
            dedupe_session_id: From a prior call, to page without repeats.

        Returns:
            Raw payload: ``dedupeSessionId``, ``results`` (id/name/domain),
            ``meta``, ``billing.creditsCharged``.
        """
        payload: dict[str, Any] = {"seeds": seeds}
        if exclude is not None:
            payload["exclude"] = exclude
        if limit is not None:
            payload["limit"] = int(limit)
        if dedupe_session_id is not None:
            payload["dedupeSessionId"] = dedupe_session_id
        return await self._request("POST", "/v3/companies/lookalike", json_body=payload)

    # ======================================================================
    # SIGNALS  (job-change / buying signals)
    # ======================================================================

    @action("Get job-change / promotion signals for known contact ids")
    async def get_contact_signals(
        self,
        ids: list[str],
        signal_types: Optional[list[str]] = None,
        start_date: Optional[str] = None,
    ) -> dict[str, Any]:
        """Retrieve people signals (promotion, company change) for contact ids.

        Endpoint: ``POST /v3/contacts/signals``.

        Args:
            ids: Up to 100 contact ids.
            signal_types: Subset of ``["allSignals", "promotion", "companyChange"]``
                (see ``get_contact_signal_types``). Defaults to ``["allSignals"]``
                — Lusha REQUIRES ``signalTypes`` and 400s if it's omitted
                (live-verified 2026-06-24).
            start_date: ISO date lower bound (optional).

        Returns:
            Raw payload: ``results`` (per id: ``companyChange`` / ``promotion``
            arrays), ``startDate`` / ``endDate``, ``billing.creditsCharged``.
        """
        self._validate_batch(ids, "ids")
        payload: dict[str, Any] = {"ids": ids, "signalTypes": signal_types or ["allSignals"]}
        if start_date is not None:
            payload["startDate"] = start_date
        return await self._request("POST", "/v3/contacts/signals", json_body=payload)

    @action("Get company signals (hiring, headcount, news, intent) for company ids")
    async def get_company_signals(
        self,
        ids: list[str],
        signal_types: Optional[list[str]] = None,
        start_date: Optional[str] = None,
        max_results_per_signal: Optional[int] = None,
    ) -> dict[str, Any]:
        """Retrieve company signals for company ids.

        Endpoint: ``POST /v3/companies/signals``.

        Args:
            ids: Up to 100 company ids.
            signal_types: Subset from ``get_company_signal_types`` (hiring,
                headcount, IT-spend, traffic, news, …). Defaults to
                ``["allSignals"]`` — Lusha REQUIRES ``signalTypes`` and 400s if
                it's omitted (live-verified 2026-06-24). Company signals are
                plan-gated (free plans get HTTP 402).
            start_date: ISO date lower bound (optional).
            max_results_per_signal: Cap results per signal type (optional).

        Returns:
            Raw signals payload + ``billing.creditsCharged``.
        """
        self._validate_batch(ids, "ids")
        payload: dict[str, Any] = {"ids": ids, "signalTypes": signal_types or ["allSignals"]}
        if start_date is not None:
            payload["startDate"] = start_date
        if max_results_per_signal is not None:
            payload["maxResultsPerSignal"] = int(max_results_per_signal)
        return await self._request("POST", "/v3/companies/signals", json_body=payload)

    @action("List the valid contact signal types")
    async def get_contact_signal_types(self) -> dict[str, Any]:
        """List valid people signal types. Endpoint: ``GET /v3/contacts/signals/types``."""
        return await self._request("GET", "/v3/contacts/signals/types")

    @action("List the valid company signal types")
    async def get_company_signal_types(self) -> dict[str, Any]:
        """List valid company signal types. Endpoint: ``GET /v3/companies/signals/types``."""
        return await self._request("GET", "/v3/companies/signals/types")

    @action("List the available company signal filters")
    async def get_company_signal_filters(self) -> dict[str, Any]:
        """List available company-signal filters (+ whether each needs a query).

        Endpoint: ``GET /v3/companies/signals/filters``.
        """
        return await self._request("GET", "/v3/companies/signals/filters")

    @action("List valid values for a company signal filter")
    async def get_company_signal_filter_values(
        self, filter_type: str, query: Optional[str] = None
    ) -> dict[str, Any]:
        """List valid values for a company-signal filter.

        Endpoint: ``GET /v3/companies/signals/filters/{filterType}``.

        Args:
            filter_type: e.g. ``newsEventTypes`` / ``hiringByDepartments`` /
                ``hiringByLocations`` (see ``get_company_signal_filters``).
            query: Required for query-backed filters (e.g. ``hiringByLocations``);
                2–256 chars.
        """
        params = {"query": query} if query is not None else None
        return await self._request(
            "GET", f"/v3/companies/signals/filters/{filter_type}", params=params
        )

    # ======================================================================
    # PROSPECTING FILTER DISCOVERY
    # ======================================================================

    @action("List valid values for a contact prospecting filter")
    async def get_contact_prospecting_filters(self, filter_type: str) -> dict[str, Any]:
        """List valid values for a contact-prospecting filter (departments,
        seniorities, locations, …) — use to build ``prospecting_search_contacts`` filters.

        Endpoint: ``GET /v3/contacts/prospecting/filters/{filterType}``.
        """
        return await self._request("GET", f"/v3/contacts/prospecting/filters/{filter_type}")

    @action("List valid values for a company prospecting filter")
    async def get_company_prospecting_filters(self, filter_type: str) -> dict[str, Any]:
        """List valid values for a company-prospecting filter (industries, sizes,
        technologies, …) — use to build ``prospecting_search_companies`` filters.

        Endpoint: ``GET /v3/companies/prospecting/filters/{filterType}``.
        """
        return await self._request("GET", f"/v3/companies/prospecting/filters/{filter_type}")
