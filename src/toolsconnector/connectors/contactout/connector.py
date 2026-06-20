"""ContactOut connector — B2B contact enrichment via ContactOut's official API.

BYOK wrapper over **ContactOut's own API** (the developer brings their
ContactOut API key on a Team/API plan). ToolsConnector performs no scraping —
it calls ContactOut's documented endpoints with the user's key; ContactOut
sources the data and is the data controller under its own terms.

Capabilities: people search by filters, enrich a LinkedIn profile / email /
name+company into work + personal emails and phone numbers, find decision
makers, reverse-lookup a LinkedIn URL from an email, plus free pre-flight
"does a contact exist?" checks and email verification.

Auth: the API key travels in a custom ``token`` header (NOT ``Authorization``).
Billing is success-based across four credit pools (email / phone / search /
verifier); reveal is gated by ``reveal_info`` on search so you can browse
profiles without spending email/phone credits. The free endpoints
(``count_people``, the ``check_*_status`` checks, ``get_usage``) spend nothing.

⚠️ Returns third-party personal data (emails, phone numbers). The caller is
responsible for lawful basis (GDPR legitimate-interest / CCPA) and opt-out /
data-subject rights. See README.

Docs: https://api.contactout.com (no public OpenAPI; v1 endpoints are stable).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

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

from .types import ContactOutProfile

logger = logging.getLogger("toolsconnector.contactout")

_SEARCH_PAGE_SIZE = 25  # ContactOut search page size is fixed at 25.


def _as_list(value: Any) -> list[str]:
    """Normalize None / str / list into a list of strings."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        return [v for v in value if isinstance(v, str)]
    return []


class ContactOut(BaseConnector):
    """Enrich B2B contacts via ContactOut's official API (BYOK).

    Requires a ContactOut API key (``credentials``) on a Team/API plan — sent
    as the ``token`` header. Reveal actions spend credits; use the free
    ``count_people`` / ``check_*_status`` to pre-flight. Returns third-party
    PII — you own lawful basis + opt-out handling.
    """

    name = "contactout"
    display_name = "ContactOut"
    category = ConnectorCategory.MARKETING
    protocol = ProtocolType.REST
    base_url = "https://api.contactout.com"
    # Tier 2 (doc) — built against ContactOut's documented v1 API + respx-pinned.
    # Promote to "live" once verified with a real Team/API-plan key.
    verification_status = "doc"
    description = (
        "B2B contact enrichment via ContactOut's official API (BYOK Team/API key). "
        "Search people by filters and enrich a LinkedIn URL / email / name+company "
        "into work + personal emails and phone numbers, find decision-makers, and "
        "reverse-lookup a LinkedIn profile from an email. Free pre-flight existence "
        "checks + email verification. Returns third-party PII; reveal spends credits. "
        "Wraps ContactOut's own API — no scraping."
    )
    _rate_limit_config = RateLimitSpec(rate=1, period=1, burst=3)  # search is 60/min; advisory

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=self._base_url or self.__class__.base_url,
            headers={
                # ContactOut's auth is a custom `token` header — NOT Authorization.
                "token": str(self._credentials),
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
            response = await self._client.request(method, path, json=json_body, params=params)
        except httpx.TimeoutException as exc:
            raise ToolsConnectorTimeoutError(
                f"ContactOut API request timed out after {self._timeout}s",
                connector=self.name,
                details={"method": method, "path": path, "underlying": type(exc).__name__},
            ) from exc
        except httpx.ConnectError as exc:
            raise ToolsConnectorConnectionError(
                "Could not connect to the ContactOut API at api.contactout.com",
                connector=self.name,
                details={"method": method, "path": path, "underlying": str(exc)},
            ) from exc
        except httpx.TransportError as exc:
            raise TransportError(
                f"ContactOut API transport error: {type(exc).__name__}",
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

    @staticmethod
    def _unwrap(resp: dict[str, Any]) -> dict[str, Any]:
        """ContactOut nests single-profile responses under a ``profile`` key."""
        inner = resp.get("profile")
        return inner if isinstance(inner, dict) else resp

    @staticmethod
    def _profile(raw: dict[str, Any], linkedin_url: str = "") -> ContactOutProfile:
        """Normalize one of ContactOut's varied profile shapes into the canonical one."""
        ci = raw.get("contact_info") if isinstance(raw.get("contact_info"), dict) else {}
        work = (
            _as_list(ci.get("work_emails"))
            or _as_list(raw.get("work_emails"))
            or _as_list(raw.get("work_email"))
            or _as_list(raw.get("workEmail"))
        )
        personal = (
            _as_list(ci.get("personal_emails"))
            or _as_list(raw.get("personal_emails"))
            or _as_list(raw.get("personal_email"))
            or _as_list(raw.get("personalEmail"))
        )
        emails = (
            _as_list(ci.get("emails")) or _as_list(raw.get("emails")) or _as_list(raw.get("email"))
        )
        phones = (
            _as_list(ci.get("phones")) or _as_list(raw.get("phones")) or _as_list(raw.get("phone"))
        )
        status = (
            ci.get("work_email_status")
            or raw.get("work_email_status")
            or raw.get("workEmailStatus")
            or {}
        )
        return ContactOutProfile(
            linkedin_url=linkedin_url or raw.get("url") or raw.get("li_vanity") or "",
            full_name=raw.get("full_name") or raw.get("name") or "",
            headline=raw.get("headline") or "",
            title=raw.get("title") or "",
            company=raw.get("company") or "",
            location=raw.get("location") or "",
            emails=emails,
            work_emails=work,
            personal_emails=personal,
            phones=phones,
            work_email_status=status if isinstance(status, dict) else {},
            github=_as_list(raw.get("github")),
            experience=raw.get("experience") or [],
            education=raw.get("education") or [],
            skills=_as_list(raw.get("skills")),
        )

    def _profiles_page(
        self, body: dict[str, Any], page: int, fetch
    ) -> PaginatedList[ContactOutProfile]:
        """Build a PaginatedList from a search-style response (profiles map keyed by URL)."""
        profiles_map = body.get("profiles")
        items: list[ContactOutProfile] = []
        if isinstance(profiles_map, dict):
            items = [
                self._profile(v, linkedin_url=url)
                for url, v in profiles_map.items()
                if isinstance(v, dict)
            ]
        elif isinstance(profiles_map, list):
            items = [self._profile(v) for v in profiles_map if isinstance(v, dict)]
        meta = body.get("metadata") or {}
        total = meta.get("total_results")
        size = meta.get("page_size", _SEARCH_PAGE_SIZE) or _SEARCH_PAGE_SIZE
        has_more = total is not None and (page * size) < total
        result: PaginatedList[ContactOutProfile] = PaginatedList(
            items=items,
            page_state=PageState(page_number=page, has_more=has_more, total_count=total),
        )
        if has_more:
            nxt = page + 1
            result._fetch_next = lambda p=nxt: fetch(p)
        return result

    # ======================================================================
    # PEOPLE SEARCH
    # ======================================================================

    @action(
        "Search people by filters (paginated); set reveal_info to spend credits for emails/phones"
    )
    async def search_people(
        self, filters: dict[str, Any], page: int = 1, reveal_info: bool = False
    ) -> PaginatedList[ContactOutProfile]:
        """Search people by filters. Returns LinkedIn profiles; optionally reveals contact info.

        Endpoint: ``POST /v1/people/search`` (page size fixed at 25).

        Args:
            filters: The filter object — any of: ``name``, ``job_title[]``,
                ``job_function[]``, ``seniority[]``, ``skills[]``, ``location[]``,
                ``company[]``, ``industry[]``, ``company_size[]``,
                ``years_of_experience[]``, plus options like
                ``current_titles_only``, ``match_experience``.
            page: 1-based page number.
            reveal_info: If ``False`` (default), returns profiles with
                contact-availability booleans only (no credit spend). If
                ``True``, reveals + **bills** work/personal emails + phones.

        Returns:
            A page of profiles; ``collect()`` walks all pages (mind the credits
            if ``reveal_info=True``). Use ``count_people`` first to size a query
            for free.
        """
        page = max(1, int(page))
        body = {**(filters or {}), "page": page, "reveal_info": bool(reveal_info)}
        resp = await self._request("POST", "/v1/people/search", json_body=body)
        return self._profiles_page(
            resp,
            page,
            lambda p: self.asearch_people(filters=filters, page=p, reveal_info=reveal_info),
        )

    @action("Free dry-run: count how many people match a search (no credits, no contact data)")
    async def count_people(self, filters: dict[str, Any]) -> int:
        """Return the total match count for a search — FREE, spends no credits.

        Endpoint: ``POST /v1/people/count``. Use before ``search_people`` to
        size a query without paying.

        Args:
            filters: Same filter object as ``search_people``.

        Returns:
            The total number of matching profiles.
        """
        resp = await self._request("POST", "/v1/people/count", json_body=dict(filters or {}))
        return int(resp.get("total_results", 0) or 0)

    @action("Find decision-makers for a company (by domain / LinkedIn / name); paginated")
    async def get_decision_makers(
        self,
        domain: Optional[str] = None,
        linkedin_url: Optional[str] = None,
        name: Optional[str] = None,
        reveal_info: bool = False,
        page: int = 1,
    ) -> PaginatedList[ContactOutProfile]:
        """Find a company's decision-makers.

        Endpoint: ``GET /v1/people/decision-makers``. Provide at least one of
        ``domain`` / ``linkedin_url`` / ``name``. ``reveal_info=True`` reveals +
        bills emails/phones.

        Returns:
            A page of decision-maker profiles.
        """
        if not (domain or linkedin_url or name):
            raise ValidationError(
                "provide at least one of domain / linkedin_url / name",
                connector="contactout",
                action="/v1/people/decision-makers",
            )
        page = max(1, int(page))
        params: dict[str, Any] = {"page": page, "reveal_info": str(bool(reveal_info)).lower()}
        if domain:
            params["domain"] = domain
        if linkedin_url:
            params["linkedin_url"] = linkedin_url
        if name:
            params["name"] = name
        resp = await self._request("GET", "/v1/people/decision-makers", params=params)
        return self._profiles_page(
            resp,
            page,
            lambda p: self.aget_decision_makers(
                domain=domain, linkedin_url=linkedin_url, name=name, reveal_info=reveal_info, page=p
            ),
        )

    # ======================================================================
    # ENRICH / LOOKUP  (single person)
    # ======================================================================

    @action("Enrich a LinkedIn profile URL into full profile + contact data")
    async def enrich_linkedin_profile(self, profile: str) -> ContactOutProfile:
        """Full enrichment of one LinkedIn profile URL (profile + emails + phones).

        Endpoint: ``GET /v1/linkedin/enrich``. Spends credits when contact data
        is found.

        Args:
            profile: A LinkedIn profile URL.

        Returns:
            The normalized profile (``work_emails`` / ``personal_emails`` / ``phones``).
        """
        resp = await self._request("GET", "/v1/linkedin/enrich", params={"profile": profile})
        return self._profile(self._unwrap(resp), linkedin_url=profile)

    @action("Reveal contact info (emails/phone) for one LinkedIn profile URL")
    async def get_linkedin_contact_info(
        self, profile: str, include_phone: bool = True, email_type: str = "both"
    ) -> ContactOutProfile:
        """Reveal contact info for a LinkedIn profile (lighter than full enrich).

        Endpoint: ``GET /v1/people/linkedin``.

        Args:
            profile: A LinkedIn profile URL.
            include_phone: If true, reveal phone numbers (spends phone credits).
            email_type: ``"personal"`` | ``"work"`` | ``"both"`` | ``"none"``.

        Returns:
            The normalized profile.
        """
        params = {
            "profile": profile,
            "include_phone": str(bool(include_phone)).lower(),
            "email_type": email_type,
        }
        resp = await self._request("GET", "/v1/people/linkedin", params=params)
        return self._profile(self._unwrap(resp), linkedin_url=profile)

    @action("Reveal contact info for up to 100 LinkedIn profile URLs in one call")
    async def get_linkedin_contact_info_bulk(
        self, profiles: list[str], include_phone: bool = True, email_type: str = "both"
    ) -> list[ContactOutProfile]:
        """Synchronous bulk contact reveal for up to 100 LinkedIn URLs.

        Endpoint: ``POST /v1/people/linkedin/batch``.

        Args:
            profiles: Up to 100 LinkedIn profile URLs.
            include_phone: Reveal phones (spends phone credits).
            email_type: ``"personal"`` | ``"work"`` | ``"both"`` | ``"none"``.

        Returns:
            One normalized profile per input URL that resolved.
        """
        if not profiles:
            raise ValidationError(
                "profiles must be non-empty", connector="contactout", action="batch"
            )
        if len(profiles) > 100:
            raise ValidationError(
                f"at most 100 profiles per call, got {len(profiles)}",
                connector="contactout",
                action="batch",
            )
        body = {
            "profiles": profiles,
            "include_phone": bool(include_phone),
            "email_type": email_type,
        }
        resp = await self._request("POST", "/v1/people/linkedin/batch", json_body=body)
        # The batch payload is keyed by LinkedIn URL, sometimes under a "profiles" wrapper.
        data = resp.get("profiles") if isinstance(resp.get("profiles"), dict) else resp
        out: list[ContactOutProfile] = []
        for key, value in data.items():
            if key in ("status_code", "metadata"):
                continue
            if isinstance(value, dict):
                out.append(self._profile(value, linkedin_url=key))
            elif isinstance(value, list):
                out.append(ContactOutProfile(linkedin_url=key, emails=_as_list(value)))
        return out

    @action("Enrich a person by LinkedIn URL / email / phone / name+company")
    async def enrich_people(
        self,
        linkedin_url: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        full_name: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        company: Optional[Any] = None,
        company_domain: Optional[Any] = None,
        job_title: Optional[str] = None,
        location: Optional[str] = None,
        education: Optional[Any] = None,
        include: Optional[list[str]] = None,
    ) -> ContactOutProfile:
        """Flexible person enrichment by any identifier (or name + company).

        Endpoint: ``POST /v1/people/enrich``.

        Args:
            linkedin_url / email / phone: A primary identifier (any one).
            full_name (or first_name + last_name) + company / company_domain:
                Name-based lookup. ``company`` / ``company_domain`` / ``education``
                accept a string or a list (max 10 each).
            job_title / location: Optional disambiguators for a name-based lookup.
            include: Subset of ``["work_email", "personal_email", "phone"]`` to
                reveal (spends credits accordingly).

        Returns:
            The normalized profile.
        """
        body: dict[str, Any] = {}
        for key, val in (
            ("linkedin_url", linkedin_url),
            ("email", email),
            ("phone", phone),
            ("full_name", full_name),
            ("first_name", first_name),
            ("last_name", last_name),
            ("job_title", job_title),
            ("location", location),
        ):
            if val:
                body[key] = val
        for key, val in (
            ("company", company),
            ("company_domain", company_domain),
            ("education", education),
        ):
            if val:
                body[key] = val if isinstance(val, list) else [val]
        if include:
            body["include"] = include
        if not body:
            raise ValidationError(
                "provide at least one identifier (linkedin_url / email / phone / "
                "full_name / first_name+last_name / company)",
                connector="contactout",
                action="/v1/people/enrich",
            )
        resp = await self._request("POST", "/v1/people/enrich", json_body=body)
        return self._profile(self._unwrap(resp), linkedin_url=linkedin_url or "")

    @action("Reverse-enrich a person from an email address")
    async def enrich_by_email(
        self, email: str, include_work_email: bool = False
    ) -> ContactOutProfile:
        """Look up a person from an email address.

        Endpoint: ``GET /v1/email/enrich``.

        Args:
            email: The email to reverse-enrich.
            include_work_email: If true, fetch a real-time work email (slower).

        Returns:
            The normalized profile.
        """
        params: dict[str, Any] = {"email": email}
        if include_work_email:
            params["include"] = "work_email"
        resp = await self._request("GET", "/v1/email/enrich", params=params)
        return self._profile(self._unwrap(resp))

    @action("Resolve an email address to its LinkedIn profile URL")
    async def find_linkedin_by_email(self, email: str) -> dict[str, Any]:
        """Resolve an email to a LinkedIn profile URL.

        Endpoint: ``GET /v1/people/person``.

        Returns:
            ``{"email": ..., "linkedin": <url or None>}``.
        """
        resp = await self._request("GET", "/v1/people/person", params={"email": email})
        prof = self._unwrap(resp)
        return {"email": prof.get("email", email), "linkedin": prof.get("linkedin")}

    # ======================================================================
    # COMPANIES
    # ======================================================================

    @action("Enrich company firmographics from domains (up to 30)")
    async def enrich_domain(self, domains: list[str]) -> dict[str, Any]:
        """Company/firmographic enrichment from domains.

        Endpoint: ``POST /v1/domain/enrich`` (max 30 domains).

        Returns:
            The raw company-firmographics payload (name, size, industry,
            revenue, funding, …). No personal email/phone.
        """
        if not domains:
            raise ValidationError(
                "domains must be non-empty", connector="contactout", action="domain"
            )
        if len(domains) > 30:
            raise ValidationError(
                f"at most 30 domains per call, got {len(domains)}",
                connector="contactout",
                action="domain",
            )
        return await self._request("POST", "/v1/domain/enrich", json_body={"domains": domains})

    @action("Search companies by firmographic filters")
    async def search_companies(self, filters: dict[str, Any]) -> dict[str, Any]:
        """Company/firmographic search by filters.

        Endpoint: ``POST /v1/company/search``. Filters: ``name[]``, ``domain[]``,
        ``size[]``, ``location[]``, ``industries[]``, revenue/founded ranges.

        Returns:
            The raw company-search payload. No personal email/phone.
        """
        return await self._request("POST", "/v1/company/search", json_body=dict(filters or {}))

    # ======================================================================
    # FREE PRE-FLIGHT CHECKS + VERIFICATION
    # ======================================================================

    @action("FREE check: does a personal email exist for a LinkedIn profile? (no reveal)")
    async def check_personal_email_status(self, profile: str) -> bool:
        """Free existence check for a personal email (spends no credits).

        Endpoint: ``GET /v1/people/linkedin/personal_email_status``.
        """
        resp = await self._request(
            "GET", "/v1/people/linkedin/personal_email_status", params={"profile": profile}
        )
        return bool(self._unwrap(resp).get("email", False))

    @action("FREE check: does a work email exist (+ verification status) for a profile?")
    async def check_work_email_status(self, profile: str) -> dict[str, Any]:
        """Free existence + verification check for a work email (no credits).

        Endpoint: ``GET /v1/people/linkedin/work_email_status``.

        Returns:
            ``{"email": <bool>, "email_status": Verified|Unverified|None}``.
        """
        resp = await self._request(
            "GET", "/v1/people/linkedin/work_email_status", params={"profile": profile}
        )
        prof = self._unwrap(resp)
        return {"email": bool(prof.get("email", False)), "email_status": prof.get("email_status")}

    @action("FREE check: does a phone exist for a LinkedIn profile? (no reveal)")
    async def check_phone_status(self, profile: str) -> bool:
        """Free existence check for a phone number (spends no credits).

        Endpoint: ``GET /v1/people/linkedin/phone_status``.
        """
        resp = await self._request(
            "GET", "/v1/people/linkedin/phone_status", params={"profile": profile}
        )
        return bool(self._unwrap(resp).get("phone", False))

    @action("Verify deliverability of an email address")
    async def verify_email(self, email: str) -> dict[str, Any]:
        """Verify an email's deliverability (spends a verifier credit on a result).

        Endpoint: ``GET /v1/email/verify``.

        Returns:
            ``{"status": valid|invalid|accept_all|disposable|unknown}``.
        """
        resp = await self._request("GET", "/v1/email/verify", params={"email": email})
        return {"status": resp.get("status")}

    @action("Async bulk reveal: queue up to 1000 LinkedIn URLs (returns a job id)")
    async def enrich_linkedin_bulk_async(
        self,
        profiles: list[str],
        callback_url: Optional[str] = None,
        include_phone: bool = True,
        email_type: str = "both",
    ) -> dict[str, Any]:
        """Queue an asynchronous bulk contact reveal for up to 1000 LinkedIn URLs.

        Endpoint: ``POST /v2/people/linkedin/batch``. Returns immediately with a
        ``job_id``; poll ``get_bulk_reveal_job`` or supply ``callback_url`` to
        receive results via webhook. Higher cap than the sync
        ``get_linkedin_contact_info_bulk`` (100).

        Args:
            profiles: Up to 1000 LinkedIn profile URLs.
            callback_url: Optional webhook to POST results to on completion.
            include_phone: Reveal phones (spends phone credits).
            email_type: ``"personal"`` | ``"work"`` | ``"both"`` | ``"none"``.

        Returns:
            ``{"status": "QUEUED", "job_id": <uuid>}``.
        """
        if not profiles:
            raise ValidationError(
                "profiles must be non-empty", connector="contactout", action="batch_async"
            )
        if len(profiles) > 1000:
            raise ValidationError(
                f"at most 1000 profiles per async batch, got {len(profiles)}",
                connector="contactout",
                action="batch_async",
            )
        body: dict[str, Any] = {
            "profiles": profiles,
            "include_phone": bool(include_phone),
            "email_type": email_type,
        }
        if callback_url:
            body["callback_url"] = callback_url
        return await self._request("POST", "/v2/people/linkedin/batch", json_body=body)

    @action("Poll an async bulk-reveal job by id for status + results")
    async def get_bulk_reveal_job(self, job_id: str) -> dict[str, Any]:
        """Fetch the status + results of an async bulk-reveal job.

        Endpoint: ``GET /v2/people/linkedin/batch/{job_id}``.

        Returns:
            ``{"data": {"uuid", "status", "result": {<url>: {emails,
            personal_emails, work_emails, phones}}}}``.
        """
        return await self._request("GET", f"/v2/people/linkedin/batch/{job_id}")

    @action("Async bulk email verification: queue up to 100 emails (returns a job id)")
    async def verify_emails_bulk(
        self, emails: list[str], callback_url: Optional[str] = None
    ) -> dict[str, Any]:
        """Queue an asynchronous bulk email verification for up to 100 emails.

        Endpoint: ``POST /v1/email/verify/batch``.

        Args:
            emails: Up to 100 email addresses.
            callback_url: Optional webhook to POST results to on completion.

        Returns:
            ``{"status": "QUEUED", "job_id": <uuid>}``.
        """
        if not emails:
            raise ValidationError(
                "emails must be non-empty", connector="contactout", action="verify_batch"
            )
        if len(emails) > 100:
            raise ValidationError(
                f"at most 100 emails per batch, got {len(emails)}",
                connector="contactout",
                action="verify_batch",
            )
        body: dict[str, Any] = {"emails": emails}
        if callback_url:
            body["callback_url"] = callback_url
        return await self._request("POST", "/v1/email/verify/batch", json_body=body)

    @action("Get remaining/consumed ContactOut credit balances (free)")
    async def get_usage(self) -> dict[str, Any]:
        """Report credit balances per pool (email / phone / search / verifier). FREE.

        Endpoint: ``GET /v1/usage``.
        """
        return await self._request("GET", "/v1/usage")
