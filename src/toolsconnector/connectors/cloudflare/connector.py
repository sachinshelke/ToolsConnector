"""Cloudflare connector -- zones, DNS records, cache, and analytics.

Uses the Cloudflare API v4 with Bearer token authentication.
All responses are wrapped in a ``{"success": true, "result": ...}`` envelope.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import (
    ConnectorCategory,
    ProtocolType,
    RateLimitSpec,
)
from toolsconnector.types import PageState, PaginatedList

from .types import CFAnalytics, CFDNSRecord, CFPageRule, CFPurgeResult, CFWorker, CFZone

logger = logging.getLogger("toolsconnector.cloudflare")


def _parse_zone(data: dict[str, Any]) -> CFZone:
    """Parse a CFZone from API JSON.

    Args:
        data: Raw JSON dict from the Cloudflare API result field.

    Returns:
        A CFZone instance.
    """
    return CFZone(
        id=data.get("id"),
        name=data.get("name"),
        status=data.get("status"),
        paused=data.get("paused", False),
        type=data.get("type"),
        development_mode=data.get("development_mode", 0),
        name_servers=data.get("name_servers") or [],
        original_name_servers=data.get("original_name_servers") or [],
        modified_on=data.get("modified_on"),
        created_on=data.get("created_on"),
        activated_on=data.get("activated_on"),
        plan=data.get("plan"),
        account=data.get("account"),
    )


def _parse_dns_record(data: dict[str, Any]) -> CFDNSRecord:
    """Parse a CFDNSRecord from API JSON.

    Args:
        data: Raw JSON dict from the Cloudflare API result field.

    Returns:
        A CFDNSRecord instance.
    """
    return CFDNSRecord(
        id=data.get("id"),
        zone_id=data.get("zone_id"),
        zone_name=data.get("zone_name"),
        name=data.get("name"),
        type=data.get("type"),
        content=data.get("content"),
        proxiable=data.get("proxiable", False),
        proxied=data.get("proxied", False),
        ttl=data.get("ttl", 1),
        locked=data.get("locked", False),
        priority=data.get("priority"),
        created_on=data.get("created_on"),
        modified_on=data.get("modified_on"),
        comment=data.get("comment"),
        tags=data.get("tags") or [],
    )


class Cloudflare(BaseConnector):
    """Connect to Cloudflare to manage zones, DNS records, cache, and analytics.

    Authenticates via Bearer token in the ``Authorization`` header.
    All API responses use the Cloudflare envelope format:
    ``{"success": true, "result": ..., "errors": [], "messages": []}``.
    """

    name = "cloudflare"
    display_name = "Cloudflare"
    category = ConnectorCategory.DEVOPS
    protocol = ProtocolType.REST
    base_url = "https://api.cloudflare.com/client/v4"
    description = (
        "Connect to Cloudflare to manage zones, DNS records, purge cache, and view analytics."
    )
    _rate_limit_config = RateLimitSpec(rate=1200, period=300, burst=50)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Initialise the httpx async client with Bearer auth."""
        headers: dict[str, str] = {
            "Content-Type": "application/json",
        }
        if self._credentials:
            headers["Authorization"] = f"Bearer {self._credentials}"

        self._client = httpx.AsyncClient(
            base_url=self._base_url or self.__class__.base_url,
            headers=headers,
            timeout=self._timeout,
        )

    async def _teardown(self) -> None:
        """Close the httpx client."""
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
        params: Optional[dict[str, Any]] = None,
        json: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Send an authenticated request and unwrap the Cloudflare envelope.

        Args:
            method: HTTP method (GET, POST, PUT, PATCH, DELETE).
            path: API path relative to base_url.
            params: Query parameters.
            json: JSON body for POST/PUT/PATCH requests.

        Returns:
            The full response body dict (contains ``success``, ``result``,
            ``errors``, ``messages``, and optionally ``result_info``).

        Raises:
            httpx.HTTPStatusError: On 4xx/5xx responses.
            RuntimeError: When Cloudflare returns ``success: false``.
        """
        resp = await self._client.request(
            method,
            path,
            params=params,
            json=json,
        )
        resp.raise_for_status()
        body = resp.json()

        if not body.get("success", False):
            errors = body.get("errors", [])
            msg = (
                "; ".join(e.get("message", str(e)) for e in errors)
                if errors
                else "Unknown Cloudflare API error"
            )
            raise RuntimeError(f"Cloudflare API error: {msg}")

        return body

    def _build_page_state(self, body: dict[str, Any]) -> PageState:
        """Build a PageState from Cloudflare result_info pagination.

        Args:
            body: The full API response body.

        Returns:
            PageState with cursor set to next page number if more exists.
        """
        info = body.get("result_info", {})
        page = info.get("page", 1)
        total_pages = info.get("total_pages", 1)
        has_more = page < total_pages
        next_cursor = str(page + 1) if has_more else None
        return PageState(has_more=has_more, cursor=next_cursor)

    # ------------------------------------------------------------------
    # Actions -- Zones
    # ------------------------------------------------------------------

    @action("List Cloudflare zones")
    async def list_zones(
        self,
        limit: int = 20,
        page: Optional[str] = None,
    ) -> PaginatedList[CFZone]:
        """List zones (domains) in the Cloudflare account.

        Args:
            limit: Maximum zones per page (max 50).
            page: Page number string for pagination.

        Returns:
            Paginated list of CFZone objects.
        """
        capped_limit = min(limit, 50)
        params: dict[str, Any] = {"per_page": capped_limit}
        if page:
            params["page"] = int(page)

        body = await self._request("GET", "/zones", params=params)
        items = [_parse_zone(z) for z in body.get("result", [])]
        ps = self._build_page_state(body)

        result = PaginatedList(items=items, page_state=ps)
        if ps.has_more:
            result._fetch_next = lambda c=ps.cursor: self.list_zones(
                limit=capped_limit,
                page=c,
            )
        return result

    @action("Get a single Cloudflare zone by ID")
    async def get_zone(self, zone_id: str) -> CFZone:
        """Retrieve a single zone by its ID.

        Args:
            zone_id: The Cloudflare zone ID.

        Returns:
            CFZone object.
        """
        body = await self._request("GET", f"/zones/{zone_id}")
        return _parse_zone(body.get("result", {}))

    # ------------------------------------------------------------------
    # Actions -- DNS Records
    # ------------------------------------------------------------------

    @action("List DNS records for a Cloudflare zone")
    async def list_dns_records(
        self,
        zone_id: str,
        type: Optional[str] = None,
        name: Optional[str] = None,
        page: Optional[str] = None,
    ) -> PaginatedList[CFDNSRecord]:
        """List DNS records for a zone.

        Args:
            zone_id: The Cloudflare zone ID.
            type: Filter by record type (``A``, ``AAAA``, ``CNAME``, etc.).
            name: Filter by record name.
            page: Page number string for pagination.

        Returns:
            Paginated list of CFDNSRecord objects.
        """
        params: dict[str, Any] = {"per_page": 50}
        if type:
            params["type"] = type
        if name:
            params["name"] = name
        if page:
            params["page"] = int(page)

        body = await self._request(
            "GET",
            f"/zones/{zone_id}/dns_records",
            params=params,
        )
        items = [_parse_dns_record(r) for r in body.get("result", [])]
        ps = self._build_page_state(body)

        result = PaginatedList(items=items, page_state=ps)
        if ps.has_more:
            result._fetch_next = lambda c=ps.cursor: self.list_dns_records(
                zone_id=zone_id,
                type=type,
                name=name,
                page=c,
            )
        return result

    @action("Create a DNS record in a Cloudflare zone", dangerous=True)
    async def create_dns_record(
        self,
        zone_id: str,
        type: str,
        name: str,
        content: str,
        ttl: Optional[int] = None,
    ) -> CFDNSRecord:
        """Create a new DNS record in a zone.

        Args:
            zone_id: The Cloudflare zone ID.
            type: DNS record type (``A``, ``AAAA``, ``CNAME``, ``MX``, etc.).
            name: DNS record name (e.g. ``example.com``).
            content: Record content (e.g. IP address or target).
            ttl: Time to live in seconds. ``1`` means automatic.

        Returns:
            The created CFDNSRecord object.
        """
        payload: dict[str, Any] = {
            "type": type,
            "name": name,
            "content": content,
        }
        if ttl is not None:
            payload["ttl"] = ttl

        body = await self._request(
            "POST",
            f"/zones/{zone_id}/dns_records",
            json=payload,
        )
        return _parse_dns_record(body.get("result", {}))

    @action("Update a DNS record in a Cloudflare zone", dangerous=True)
    async def update_dns_record(
        self,
        zone_id: str,
        record_id: str,
        type: str,
        name: str,
        content: str,
    ) -> CFDNSRecord:
        """Update an existing DNS record.

        Args:
            zone_id: The Cloudflare zone ID.
            record_id: The DNS record ID to update.
            type: DNS record type.
            name: DNS record name.
            content: Updated record content.

        Returns:
            The updated CFDNSRecord object.
        """
        payload: dict[str, Any] = {
            "type": type,
            "name": name,
            "content": content,
        }
        body = await self._request(
            "PUT",
            f"/zones/{zone_id}/dns_records/{record_id}",
            json=payload,
        )
        return _parse_dns_record(body.get("result", {}))

    @action("Delete a DNS record from a Cloudflare zone", dangerous=True)
    async def delete_dns_record(
        self,
        zone_id: str,
        record_id: str,
    ) -> dict[str, Any]:
        """Delete a DNS record. This action is irreversible.

        Args:
            zone_id: The Cloudflare zone ID.
            record_id: The DNS record ID to delete.

        Returns:
            Dict containing the deleted record ID.
        """
        body = await self._request(
            "DELETE",
            f"/zones/{zone_id}/dns_records/{record_id}",
        )
        return body.get("result", {})

    # ------------------------------------------------------------------
    # Actions -- Cache
    # ------------------------------------------------------------------

    @action("Purge Cloudflare cache for a zone", dangerous=True)
    async def purge_cache(
        self,
        zone_id: str,
        files: Optional[list[str]] = None,
    ) -> CFPurgeResult:
        """Purge cached content for a zone.

        When ``files`` is omitted, purges the entire cache for the zone.
        When ``files`` is provided, purges only the specified URLs.

        Args:
            zone_id: The Cloudflare zone ID.
            files: List of specific URLs to purge. If omitted, purges all.

        Returns:
            CFPurgeResult with the purge operation ID.
        """
        if files:
            payload: dict[str, Any] = {"files": files}
        else:
            payload = {"purge_everything": True}

        body = await self._request(
            "POST",
            f"/zones/{zone_id}/purge_cache",
            json=payload,
        )
        result = body.get("result", {})
        return CFPurgeResult(id=result.get("id"))

    # ------------------------------------------------------------------
    # Actions -- Analytics
    # ------------------------------------------------------------------

    @action("Get Cloudflare zone analytics")
    async def get_analytics(
        self,
        zone_id: str,
        since: Optional[str] = None,
    ) -> CFAnalytics:
        """Retrieve analytics data for a zone.

        Args:
            zone_id: The Cloudflare zone ID.
            since: Start of time range. Accepts relative values like
                ``-1440`` (minutes ago) or ISO 8601 timestamps.

        Returns:
            CFAnalytics object with request, bandwidth, and threat data.
        """
        params: dict[str, Any] = {}
        if since:
            params["since"] = since

        body = await self._request(
            "GET",
            f"/zones/{zone_id}/analytics/dashboard",
            params=params,
        )
        result = body.get("result", {})
        totals = result.get("totals", {})
        time_range = result.get("query", {}).get("time_delta", {})

        return CFAnalytics(
            since=time_range.get("since") if isinstance(time_range, dict) else since,
            until=time_range.get("until") if isinstance(time_range, dict) else None,
            requests=totals.get("requests"),
            bandwidth=totals.get("bandwidth"),
            threats=totals.get("threats"),
            pageviews=totals.get("pageviews"),
            uniques=totals.get("uniques"),
        )

    # ------------------------------------------------------------------
    # Actions -- Workers
    # ------------------------------------------------------------------

    @action("List Workers scripts for an account")
    async def list_workers(
        self,
        account_id: str,
    ) -> list[CFWorker]:
        """List all Worker scripts in the account.

        Args:
            account_id: Cloudflare account ID.

        Returns:
            List of CFWorker objects.
        """
        body = await self._cf_request(
            "GET",
            f"/accounts/{account_id}/workers/scripts",
        )
        return [
            CFWorker(
                id=w.get("id"),
                etag=w.get("etag"),
                created_on=w.get("created_on"),
                modified_on=w.get("modified_on"),
                size=w.get("size"),
            )
            for w in body.get("result", [])
        ]

    @action("Get a Worker script by name")
    async def get_worker(
        self,
        account_id: str,
        script_name: str,
    ) -> CFWorker:
        """Get metadata for a specific Worker script.

        Args:
            account_id: Cloudflare account ID.
            script_name: The script name.

        Returns:
            CFWorker with script details.
        """
        body = await self._cf_request(
            "GET",
            f"/accounts/{account_id}/workers/scripts/{script_name}",
        )
        result = body.get("result", {})
        return CFWorker(
            id=result.get("id", script_name),
            etag=result.get("etag"),
            created_on=result.get("created_on"),
            modified_on=result.get("modified_on"),
            size=result.get("size"),
        )

    # ------------------------------------------------------------------
    # Actions -- Page Rules
    # ------------------------------------------------------------------

    @action("Create a page rule for a zone", dangerous=True)
    async def create_page_rule(
        self,
        zone_id: str,
        targets: list[dict[str, Any]],
        actions: list[dict[str, Any]],
    ) -> CFPageRule:
        """Create a page rule for a zone.

        Args:
            zone_id: The zone ID.
            targets: List of target URL pattern dicts.
            actions: List of action configuration dicts.

        Returns:
            The created CFPageRule.
        """
        payload: dict[str, Any] = {
            "targets": targets,
            "actions": actions,
            "status": "active",
        }
        body = await self._cf_request(
            "POST",
            f"/zones/{zone_id}/pagerules",
            json_body=payload,
        )
        r = body.get("result", {})
        return CFPageRule(
            id=r.get("id"),
            status=r.get("status"),
            priority=r.get("priority"),
            targets=r.get("targets", []),
            actions=r.get("actions", []),
            created_on=r.get("created_on"),
            modified_on=r.get("modified_on"),
        )

    # ------------------------------------------------------------------
    # Actions -- Zone management (extended)
    # ------------------------------------------------------------------

    @action("Delete a zone", dangerous=True)
    async def delete_zone(self, zone_id: str) -> bool:
        """Delete a zone from Cloudflare.

        Args:
            zone_id: The zone ID to delete.

        Returns:
            True if the zone was deleted.
        """
        body = await self._cf_request(
            "DELETE",
            f"/zones/{zone_id}",
        )
        return body.get("success", False)

    # ------------------------------------------------------------------
    # Actions -- Firewall & Zone settings
    # ------------------------------------------------------------------

    @action("List firewall rules for a zone")
    async def list_firewall_rules(
        self,
        zone_id: str,
    ) -> list[dict[str, Any]]:
        """List all firewall rules configured for a zone.

        Args:
            zone_id: The Cloudflare zone ID.

        Returns:
            List of firewall rule dicts.
        """
        body = await self._request(
            "GET",
            f"/zones/{zone_id}/firewall/rules",
        )
        return body.get("result", [])

    @action("Get zone settings")
    async def get_zone_settings(
        self,
        zone_id: str,
    ) -> list[dict[str, Any]]:
        """Retrieve all settings for a Cloudflare zone.

        Returns the full list of zone settings including SSL mode,
        security level, caching behaviour, and more.

        Args:
            zone_id: The Cloudflare zone ID.

        Returns:
            List of setting dicts with id, value, and metadata.
        """
        body = await self._request(
            "GET",
            f"/zones/{zone_id}/settings",
        )
        return body.get("result", [])

    @action("Toggle development mode for a zone", dangerous=True)
    async def toggle_development_mode(
        self,
        zone_id: str,
        enable: bool,
    ) -> dict[str, Any]:
        """Enable or disable development mode for a zone.

        Development mode temporarily bypasses the Cloudflare cache,
        allowing changes to be visible immediately. It automatically
        expires after 3 hours.

        Args:
            zone_id: The Cloudflare zone ID.
            enable: True to enable development mode, False to disable.

        Returns:
            Dict with the updated setting value.
        """
        value = "on" if enable else "off"
        body = await self._request(
            "PATCH",
            f"/zones/{zone_id}/settings/development_mode",
            json={"value": value},
        )
        return body.get("result", {})

    # ------------------------------------------------------------------
    # Actions — SSL/TLS
    # ------------------------------------------------------------------

    @action("Get SSL/TLS setting for a zone")
    async def get_ssl_setting(self, zone_id: str) -> dict[str, Any]:
        """Get the SSL/TLS encryption mode for a zone.

        Args:
            zone_id: The zone ID.

        Returns:
            Dict with SSL setting value (off, flexible, full, strict).
        """
        body = await self._request(
            "GET",
            f"/zones/{zone_id}/settings/ssl",
        )
        return body.get("result", {})

    @action("Update SSL/TLS setting", dangerous=True)
    async def update_ssl_setting(self, zone_id: str, value: str) -> dict[str, Any]:
        """Set the SSL/TLS encryption mode for a zone.

        Args:
            zone_id: The zone ID.
            value: SSL mode: 'off', 'flexible', 'full', or 'strict'.

        Returns:
            Updated setting dict.
        """
        body = await self._request(
            "PATCH",
            f"/zones/{zone_id}/settings/ssl",
            json={"value": value},
        )
        return body.get("result", {})

    @action("Create a zone", dangerous=True)
    async def create_zone(self, name: str, account_id: str, type: str = "full") -> dict[str, Any]:
        """Add a new domain to Cloudflare.

        Args:
            name: Domain name (e.g., 'example.com').
            account_id: Cloudflare account ID.
            type: Zone type: 'full' or 'partial'.

        Returns:
            Created zone dict with id, name, status.
        """
        body = await self._request(
            "POST",
            "/zones",
            json={"name": name, "account": {"id": account_id}, "type": type},
        )
        return body.get("result", {})

    @action("List page rules for a zone")
    async def list_page_rules(self, zone_id: str) -> list[dict[str, Any]]:
        """List all page rules for a zone.

        Args:
            zone_id: The zone ID.

        Returns:
            List of page rule dicts.
        """
        body = await self._request("GET", f"/zones/{zone_id}/pagerules")
        return body.get("result", [])

    @action("Delete a page rule", dangerous=True)
    async def delete_page_rule(self, zone_id: str, rule_id: str) -> None:
        """Delete a page rule.

        Args:
            zone_id: The zone ID.
            rule_id: The page rule ID to delete.
        """
        await self._request("DELETE", f"/zones/{zone_id}/pagerules/{rule_id}")

    @action("List WAF rulesets for a zone")
    async def list_waf_rulesets(self, zone_id: str) -> list[dict[str, Any]]:
        """List WAF managed rulesets deployed on a zone.

        Args:
            zone_id: The zone ID.

        Returns:
            List of ruleset dicts.
        """
        body = await self._request("GET", f"/zones/{zone_id}/rulesets")
        return body.get("result", [])

    @action("Deploy a worker script", dangerous=True)
    async def deploy_worker(
        self, account_id: str, script_name: str, script_content: str
    ) -> dict[str, Any]:
        """Upload and deploy a Cloudflare Worker script.

        Args:
            account_id: Cloudflare account ID.
            script_name: Name for the worker script.
            script_content: The JavaScript worker code.

        Returns:
            Deployed worker dict.
        """
        body = await self._request(
            "PUT",
            f"/accounts/{account_id}/workers/scripts/{script_name}",
            content=script_content.encode("utf-8"),
            headers={"Content-Type": "application/javascript"},
        )
        return body.get("result", {})

    @action("Delete a worker script", dangerous=True)
    async def delete_worker(self, account_id: str, script_name: str) -> None:
        """Delete a Cloudflare Worker script.

        Args:
            account_id: Cloudflare account ID.
            script_name: Name of the worker script to delete.
        """
        await self._request(
            "DELETE",
            f"/accounts/{account_id}/workers/scripts/{script_name}",
        )
