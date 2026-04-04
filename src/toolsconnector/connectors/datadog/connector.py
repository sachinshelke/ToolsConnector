"""Datadog connector -- monitors, events, metrics, and dashboards.

Uses the Datadog REST API v1/v2 with dual API-key + application-key auth.
Supports configurable base URL for EU sites (api.datadoghq.eu).
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

from .types import (
    DatadogDashboard,
    DatadogEvent,
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
        "Connect to Datadog to manage monitors, query metrics, "
        "create events, and list dashboards."
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
            httpx.HTTPStatusError: On 4xx/5xx responses.
        """
        resp = await self._client.request(
            method, path, params=params, json=json,
        )
        resp.raise_for_status()
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
