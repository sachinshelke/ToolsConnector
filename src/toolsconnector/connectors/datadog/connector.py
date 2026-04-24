"""Datadog connector -- monitors, events, metrics, and dashboards.

Uses the Datadog REST API v1/v2 with dual API-key + application-key auth.
Supports configurable base URL for EU sites (api.datadoghq.eu).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from toolsconnector.connectors._helpers import raise_typed_for_status
from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import (
    ConnectorCategory,
    ProtocolType,
    RateLimitSpec,
)
from toolsconnector.types import PageState, PaginatedList

from .types import (
    DatadogDashboard,
    DatadogDowntime,
    DatadogEvent,
    DatadogHost,
    DatadogMetric,
    DatadogMetricPoint,
    DatadogMonitor,
)

logger = logging.getLogger("toolsconnector.datadog")


def _parse_monitor(data: dict[str, Any]) -> DatadogMonitor:
    """Parse a DatadogMonitor from API JSON.

    Args:
        data: Raw JSON dict from the Datadog API.

    Returns:
        A DatadogMonitor instance.
    """
    return DatadogMonitor(
        id=data.get("id"),
        name=data.get("name"),
        type=data.get("type"),
        query=data.get("query"),
        message=data.get("message"),
        overall_state=data.get("overall_state"),
        tags=data.get("tags") or [],
        created=data.get("created"),
        modified=data.get("modified"),
        creator=data.get("creator"),
        options=data.get("options"),
        multi=data.get("multi", False),
        priority=data.get("priority"),
    )


def _parse_event(data: dict[str, Any]) -> DatadogEvent:
    """Parse a DatadogEvent from API JSON.

    Args:
        data: Raw JSON dict from the Datadog API.

    Returns:
        A DatadogEvent instance.
    """
    return DatadogEvent(
        id=data.get("id"),
        title=data.get("title"),
        text=data.get("text"),
        date_happened=data.get("date_happened"),
        priority=data.get("priority"),
        host=data.get("host"),
        tags=data.get("tags") or [],
        alert_type=data.get("alert_type"),
        source_type_name=data.get("source_type_name"),
        url=data.get("url"),
    )


def _parse_metric_series(data: dict[str, Any]) -> DatadogMetric:
    """Parse a DatadogMetric from a query response series entry.

    Args:
        data: Raw JSON dict for a single series from the metrics query API.

    Returns:
        A DatadogMetric instance.
    """
    pointlist = [
        DatadogMetricPoint(timestamp=pt[0], value=pt[1] if len(pt) > 1 else None)
        for pt in data.get("pointlist", [])
    ]
    return DatadogMetric(
        metric=data.get("metric"),
        display_name=data.get("display_name"),
        unit=data.get("unit", [None])[0] if data.get("unit") else None,
        scope=data.get("scope"),
        expression=data.get("expression"),
        pointlist=pointlist,
        start=data.get("start"),
        end=data.get("end"),
        interval=data.get("interval"),
    )


def _parse_dashboard(data: dict[str, Any]) -> DatadogDashboard:
    """Parse a DatadogDashboard from API JSON.

    Args:
        data: Raw JSON dict from the Datadog API.

    Returns:
        A DatadogDashboard instance.
    """
    return DatadogDashboard(
        id=data.get("id"),
        title=data.get("title"),
        description=data.get("description"),
        url=data.get("url"),
        layout_type=data.get("layout_type"),
        author_handle=data.get("author_handle"),
        created_at=data.get("created_at"),
        modified_at=data.get("modified_at"),
        is_read_only=data.get("is_read_only", False),
    )


class Datadog(BaseConnector):
    """Connect to Datadog to manage monitors, events, metrics, and dashboards.

    Authenticates via dual-header scheme: ``DD-API-KEY`` and
    ``DD-APPLICATION-KEY``.  Credentials should be provided as
    ``"api_key:app_key"`` (colon-separated).

    Supports configurable ``base_url`` for EU sites
    (e.g., ``https://api.datadoghq.eu/api``).
    """

    name = "datadog"
    display_name = "Datadog"
    category = ConnectorCategory.DEVOPS
    protocol = ProtocolType.REST
    base_url = "https://api.datadoghq.com/api"
    description = (
        "Connect to Datadog to manage monitors, query metrics, create events, and list dashboards."
    )
    _rate_limit_config = RateLimitSpec(rate=300, period=60, burst=30)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Initialise the httpx async client with Datadog auth headers."""
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self._credentials:
            cred_str = str(self._credentials)
            if ":" in cred_str:
                api_key, app_key = cred_str.split(":", 1)
            else:
                api_key = cred_str
                app_key = ""
            headers["DD-API-KEY"] = api_key
            if app_key:
                headers["DD-APPLICATION-KEY"] = app_key

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
    ) -> httpx.Response:
        """Send an authenticated request to the Datadog API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE).
            path: API path relative to base_url.
            params: Query parameters.
            json: JSON body for POST/PUT requests.

        Returns:
            httpx.Response object.

        Raises:
            toolsconnector.errors.APIError (subclass): On any non-2xx response.
                Maps to a typed exception by status: 401 -> InvalidCredentialsError
                or TokenExpiredError; 403 -> PermissionDeniedError; 404 -> NotFoundError;
                409 -> ConflictError; 400/422 -> ValidationError; 429 -> RateLimitError;
                5xx -> ServerError; other 4xx -> APIError. See
                toolsconnector.connectors._helpers.raise_typed_for_status for the full mapping.
        """
        resp = await self._client.request(
            method,
            path,
            params=params,
            json=json,
        )
        raise_typed_for_status(resp, connector=self.name)
        return resp

    # ------------------------------------------------------------------
    # Actions -- Monitors
    # ------------------------------------------------------------------

    @action("List Datadog monitors")
    async def list_monitors(
        self,
        limit: int = 50,
    ) -> PaginatedList[DatadogMonitor]:
        """List monitors from the Datadog account.

        Args:
            limit: Maximum number of monitors to return (max 1000).

        Returns:
            Paginated list of DatadogMonitor objects.
        """
        params: dict[str, Any] = {"page_size": min(limit, 1000)}
        resp = await self._request("GET", "/v1/monitor", params=params)
        items = [_parse_monitor(m) for m in resp.json()]
        return PaginatedList(
            items=items,
            page_state=PageState(has_more=False),
        )

    @action("Get a single Datadog monitor by ID")
    async def get_monitor(self, monitor_id: int) -> DatadogMonitor:
        """Retrieve a single monitor by its ID.

        Args:
            monitor_id: The numeric monitor ID.

        Returns:
            DatadogMonitor object.
        """
        resp = await self._request("GET", f"/v1/monitor/{monitor_id}")
        return _parse_monitor(resp.json())

    @action("Create a Datadog monitor", dangerous=True)
    async def create_monitor(
        self,
        name: str,
        type: str,
        query: str,
        message: Optional[str] = None,
    ) -> DatadogMonitor:
        """Create a new monitor in Datadog.

        Args:
            name: Name of the monitor.
            type: Monitor type (e.g. ``metric alert``, ``service check``).
            query: The monitor query string.
            message: Notification message body.

        Returns:
            The created DatadogMonitor object.
        """
        payload: dict[str, Any] = {
            "name": name,
            "type": type,
            "query": query,
        }
        if message is not None:
            payload["message"] = message

        resp = await self._request("POST", "/v1/monitor", json=payload)
        return _parse_monitor(resp.json())

    @action("Mute a Datadog monitor", dangerous=True)
    async def mute_monitor(self, monitor_id: int) -> DatadogMonitor:
        """Mute a monitor so it stops sending notifications.

        Args:
            monitor_id: The numeric monitor ID to mute.

        Returns:
            The muted DatadogMonitor object.
        """
        resp = await self._request("POST", f"/v1/monitor/{monitor_id}/mute")
        return _parse_monitor(resp.json())

    # ------------------------------------------------------------------
    # Actions -- Metrics
    # ------------------------------------------------------------------

    @action("Query Datadog metrics")
    async def query_metrics(
        self,
        query: str,
        from_ts: int,
        to_ts: int,
    ) -> list[DatadogMetric]:
        """Query time-series metrics from Datadog.

        Args:
            query: Metrics query string (e.g. ``avg:system.cpu.user{*}``).
            from_ts: Start timestamp in epoch seconds.
            to_ts: End timestamp in epoch seconds.

        Returns:
            List of DatadogMetric series results.
        """
        params: dict[str, Any] = {
            "query": query,
            "from": from_ts,
            "to": to_ts,
        }
        resp = await self._request("GET", "/v1/query", params=params)
        body = resp.json()
        return [_parse_metric_series(s) for s in body.get("series", [])]

    # ------------------------------------------------------------------
    # Actions -- Events
    # ------------------------------------------------------------------

    @action("List Datadog events")
    async def list_events(
        self,
        start: int,
        end: int,
        priority: Optional[str] = None,
    ) -> PaginatedList[DatadogEvent]:
        """List events from Datadog within a time range.

        Args:
            start: Start timestamp in epoch seconds.
            end: End timestamp in epoch seconds.
            priority: Filter by priority (``normal`` or ``low``).

        Returns:
            Paginated list of DatadogEvent objects.
        """
        params: dict[str, Any] = {"start": start, "end": end}
        if priority:
            params["priority"] = priority

        resp = await self._request("GET", "/v1/events", params=params)
        body = resp.json()
        items = [_parse_event(e) for e in body.get("events", [])]
        return PaginatedList(
            items=items,
            page_state=PageState(has_more=False),
        )

    @action("Create a Datadog event", dangerous=True)
    async def create_event(
        self,
        title: str,
        text: str,
        priority: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> DatadogEvent:
        """Post a new event to Datadog.

        Args:
            title: Event title.
            text: Event body text. Supports Markdown.
            priority: Event priority (``normal`` or ``low``).
            tags: List of tags to attach (e.g. ``["env:prod"]``).

        Returns:
            The created DatadogEvent object.
        """
        payload: dict[str, Any] = {"title": title, "text": text}
        if priority is not None:
            payload["priority"] = priority
        if tags:
            payload["tags"] = tags

        resp = await self._request("POST", "/v1/events", json=payload)
        body = resp.json()
        return _parse_event(body.get("event", body))

    # ------------------------------------------------------------------
    # Actions -- Dashboards
    # ------------------------------------------------------------------

    @action("List Datadog dashboards")
    async def list_dashboards(self) -> PaginatedList[DatadogDashboard]:
        """List all dashboard summaries from the Datadog account.

        Returns:
            Paginated list of DatadogDashboard objects.
        """
        resp = await self._request("GET", "/v1/dashboard")
        body = resp.json()
        items = [_parse_dashboard(d) for d in body.get("dashboards", [])]
        return PaginatedList(
            items=items,
            page_state=PageState(has_more=False),
        )

    # ------------------------------------------------------------------
    # Actions -- Monitor management (extended)
    # ------------------------------------------------------------------

    @action("Delete a Datadog monitor", dangerous=True)
    async def delete_monitor(self, monitor_id: int) -> bool:
        """Delete a Datadog monitor by ID.

        Args:
            monitor_id: The monitor ID.

        Returns:
            True if the monitor was deleted.
        """
        resp = await self._request("DELETE", f"/v1/monitor/{monitor_id}")
        return resp.status_code == 200

    # ------------------------------------------------------------------
    # Actions -- Metrics
    # ------------------------------------------------------------------

    @action("Get metadata for a metric")
    async def get_metric_metadata(
        self,
        metric_name: str,
    ) -> dict[str, Any]:
        """Retrieve metadata for a specific metric.

        Args:
            metric_name: The fully qualified metric name.

        Returns:
            Dict with metric metadata (type, unit, description, etc.).
        """
        resp = await self._request(
            "GET",
            f"/v1/metrics/{metric_name}",
        )
        return resp.json()

    # ------------------------------------------------------------------
    # Actions -- Hosts
    # ------------------------------------------------------------------

    @action("List hosts reporting to Datadog")
    async def list_hosts(
        self,
        filter: Optional[str] = None,
    ) -> list[DatadogHost]:
        """List hosts, optionally filtered by a search query.

        Args:
            filter: Filter string (e.g. host name or tag).

        Returns:
            List of DatadogHost objects.
        """
        params: dict[str, Any] = {}
        if filter:
            params["filter"] = filter
        resp = await self._request(
            "GET",
            "/v1/hosts",
            params=params or None,
        )
        body = resp.json()
        return [
            DatadogHost(
                name=h.get("name"),
                id=h.get("id"),
                aliases=h.get("aliases", []),
                apps=h.get("apps", []),
                is_muted=h.get("is_muted", False),
                last_reported_time=h.get("last_reported_time"),
                up=h.get("up"),
            )
            for h in body.get("host_list", [])
        ]

    # ------------------------------------------------------------------
    # Actions -- Downtimes
    # ------------------------------------------------------------------

    @action("Schedule a downtime window", dangerous=True)
    async def create_downtime(
        self,
        scope: str,
        start: int,
        end: Optional[int] = None,
    ) -> DatadogDowntime:
        """Schedule a downtime to suppress alerts.

        Args:
            scope: Scope of the downtime (e.g. ``"host:myhost"``).
            start: POSIX timestamp for the start of the downtime.
            end: Optional POSIX timestamp for the end. Omit for indefinite.

        Returns:
            The created DatadogDowntime.
        """
        payload: dict[str, Any] = {
            "scope": scope,
            "start": start,
        }
        if end is not None:
            payload["end"] = end
        resp = await self._request(
            "POST",
            "/v1/downtime",
            json_body=payload,
        )
        data = resp.json()
        return DatadogDowntime(
            id=data.get("id"),
            scope=data.get("scope"),
            start=data.get("start"),
            end=data.get("end"),
            message=data.get("message"),
            active=data.get("active", True),
        )

    # ------------------------------------------------------------------
    # Actions -- Monitor management (unmute, search)
    # ------------------------------------------------------------------

    @action("Unmute a Datadog monitor")
    async def unmute_monitor(self, monitor_id: int) -> DatadogMonitor:
        """Unmute a previously muted monitor so it resumes notifications.

        Args:
            monitor_id: The numeric monitor ID to unmute.

        Returns:
            The unmuted DatadogMonitor object.
        """
        resp = await self._request("POST", f"/v1/monitor/{monitor_id}/unmute")
        return _parse_monitor(resp.json())

    @action("Search Datadog monitors by query")
    async def search_monitors(
        self,
        query: str,
        limit: int = 50,
    ) -> PaginatedList[DatadogMonitor]:
        """Search monitors using a query string.

        Args:
            query: Search query (e.g. ``"tag:env:prod"`` or monitor name).
            limit: Maximum number of monitors to return.

        Returns:
            Paginated list of matching DatadogMonitor objects.
        """
        params: dict[str, Any] = {
            "query": query,
            "page_size": min(limit, 1000),
        }
        resp = await self._request("GET", "/v1/monitor/search", params=params)
        body = resp.json()
        items = [_parse_monitor(m) for m in body.get("monitors", [])]
        return PaginatedList(
            items=items,
            page_state=PageState(has_more=False),
            total_count=body.get("metadata", {}).get("total_count"),
        )

    @action("List scheduled downtimes")
    async def list_downtimes(self) -> PaginatedList[DatadogDowntime]:
        """List all scheduled downtimes in the Datadog account.

        Returns:
            Paginated list of DatadogDowntime objects.
        """
        resp = await self._request("GET", "/v1/downtime")
        body = resp.json()
        items = [
            DatadogDowntime(
                id=d.get("id"),
                scope=d.get("scope"),
                start=d.get("start"),
                end=d.get("end"),
                message=d.get("message"),
                active=d.get("active", True),
            )
            for d in (body if isinstance(body, list) else [])
        ]
        return PaginatedList(
            items=items,
            page_state=PageState(has_more=False),
        )

    @action("Cancel a scheduled downtime", dangerous=True)
    async def cancel_downtime(self, downtime_id: int) -> bool:
        """Cancel a scheduled downtime by its ID.

        This is a destructive action -- the downtime will be removed
        and suppressed alerts will resume immediately.

        Args:
            downtime_id: The numeric downtime ID to cancel.

        Returns:
            True if the downtime was cancelled.
        """
        await self._request("DELETE", f"/v1/downtime/{downtime_id}")

    # ------------------------------------------------------------------
    # Actions — Logs
    # ------------------------------------------------------------------

    @action("Search logs")
    async def search_logs(
        self,
        query: str,
        time_from: str,
        time_to: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Search and filter log events.

        Args:
            query: Log search query (Datadog log search syntax).
            time_from: Start time (ISO 8601 or relative like 'now-1h').
            time_to: End time (ISO 8601 or 'now').
            limit: Maximum log entries to return.

        Returns:
            List of log event dicts.
        """
        data = await self._request(
            "POST",
            "/v2/logs/events/search",
            json={
                "filter": {"query": query, "from": time_from, "to": time_to},
                "page": {"limit": limit},
            },
        )
        return data.get("data", [])

    # ------------------------------------------------------------------
    # Actions — Incidents
    # ------------------------------------------------------------------

    @action("List incidents")
    async def list_incidents(
        self,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List recent incidents.

        Args:
            limit: Maximum incidents to return.

        Returns:
            List of incident dicts.
        """
        data = await self._request(
            "GET",
            "/v2/incidents",
            params={"page[size]": limit},
        )
        return data.get("data", [])

    @action("Create an incident", dangerous=True)
    async def create_incident(
        self,
        title: str,
        severity: str = "SEV-3",
        customer_impact_scope: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create a new incident.

        Args:
            title: Incident title.
            severity: Severity level (SEV-1 through SEV-5).
            customer_impact_scope: Description of customer impact.

        Returns:
            Created incident dict.
        """
        attrs: dict[str, Any] = {
            "title": title,
            "fields": {"severity": {"value": severity}},
        }
        if customer_impact_scope:
            attrs["customer_impact_scope"] = customer_impact_scope
        data = await self._request(
            "POST",
            "/v2/incidents",
            json={"data": {"type": "incidents", "attributes": attrs}},
        )
        return data.get("data", {})

    # ------------------------------------------------------------------
    # Actions — Dashboards (expanded)
    # ------------------------------------------------------------------

    @action("Get a dashboard by ID")
    async def get_dashboard(self, dashboard_id: str) -> dict[str, Any]:
        """Retrieve a single dashboard by ID.

        Args:
            dashboard_id: The dashboard ID.

        Returns:
            Dashboard dict with title, widgets, layout_type.
        """
        data = await self._request("GET", f"/v1/dashboard/{dashboard_id}")
        return data

    @action("Delete a dashboard", dangerous=True)
    async def delete_dashboard(self, dashboard_id: str) -> None:
        """Delete a dashboard.

        Args:
            dashboard_id: The dashboard ID to delete.
        """
        await self._request("DELETE", f"/v1/dashboard/{dashboard_id}")

    # ------------------------------------------------------------------
    # Actions — SLOs
    # ------------------------------------------------------------------

    @action("List SLOs")
    async def list_slos(
        self,
        query: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List Service Level Objectives.

        Args:
            query: Search query to filter SLOs.
            limit: Maximum SLOs to return.

        Returns:
            List of SLO dicts.
        """
        params: dict[str, Any] = {"limit": limit}
        if query:
            params["query"] = query
        data = await self._request("GET", "/v1/slo", params=params)
        return data.get("data", [])
