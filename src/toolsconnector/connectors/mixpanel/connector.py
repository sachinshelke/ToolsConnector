"""Mixpanel connector -- track events, query analytics, funnels, and retention.

Uses httpx for direct HTTP calls against the Mixpanel API.
Expects Basic auth with service account credentials (username:secret)
passed as ``credentials`` in the format ``username:secret``.
"""

from __future__ import annotations

import base64
import json
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
    FunnelStep,
    MixpanelEvent,
    MixpanelEventCount,
    MixpanelEventName,
    MixpanelFunnel,
    MixpanelProfile,
    MixpanelRetention,
    MixpanelTrackResult,
    RetentionCohort,
)

logger = logging.getLogger("toolsconnector.mixpanel")

_TRACKING_URL = "https://api.mixpanel.com"
_QUERY_URL = "https://mixpanel.com/api"
_DATA_EXPORT_URL = "https://data.mixpanel.com/api/2.0"


class Mixpanel(BaseConnector):
    """Connect to Mixpanel for event tracking, analytics queries, and user profiles.

    Supports Basic auth with service account credentials. Pass
    credentials as a colon-separated string ``username:secret``
    when instantiating. The tracking endpoint uses project token
    authentication, while query endpoints use Basic auth.
    """

    name = "mixpanel"
    display_name = "Mixpanel"
    category = ConnectorCategory.ANALYTICS
    protocol = ProtocolType.REST
    base_url = "https://mixpanel.com/api"
    description = (
        "Connect to Mixpanel for event tracking, analytics queries, "
        "funnel analysis, retention metrics, and user profiles."
    )
    _rate_limit_config = RateLimitSpec(rate=60, period=60, burst=20)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_basic_auth_header(self) -> str:
        """Build Base64-encoded Basic auth value from credentials.

        Returns:
            Base64-encoded string of username:secret.
        """
        creds = str(self._credentials)
        encoded = base64.b64encode(creds.encode("utf-8")).decode("ascii")
        return f"Basic {encoded}"

    def _get_query_headers(self) -> dict[str, str]:
        """Build headers for Mixpanel query API requests.

        Returns:
            Dict with Authorization and Accept headers.
        """
        return {
            "Authorization": self._get_basic_auth_header(),
            "Accept": "application/json",
        }

    async def _query_request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> Any:
        """Execute an authenticated request against a Mixpanel API endpoint.

        Args:
            method: HTTP method (GET, POST, etc.).
            url: Full URL for the request.
            **kwargs: Additional keyword arguments passed to httpx.

        Returns:
            Parsed JSON response.

        Raises:
            httpx.HTTPStatusError: If the API returns a non-2xx status.
        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.request(
                method,
                url,
                headers=self._get_query_headers(),
                **kwargs,
            )
            response.raise_for_status()
            if response.status_code == 204 or not response.content:
                return {}
            return response.json()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    @action("Track an event")
    async def track_event(
        self,
        event: str,
        properties: dict[str, Any],
        distinct_id: str,
    ) -> MixpanelTrackResult:
        """Track an event in Mixpanel.

        Args:
            event: Name of the event to track.
            properties: Event properties as key-value pairs.
            distinct_id: Unique identifier for the user performing the event.

        Returns:
            MixpanelTrackResult indicating success or failure.
        """
        event_data = {
            "event": event,
            "properties": {
                **properties,
                "distinct_id": distinct_id,
            },
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{_TRACKING_URL}/track",
                headers={
                    "Authorization": self._get_basic_auth_header(),
                    "Content-Type": "application/json",
                    "Accept": "text/plain",
                },
                json=[event_data],
            )
            response.raise_for_status()

            # Mixpanel track returns 1 for success, 0 for failure
            try:
                result = response.json()
                status = result if isinstance(result, int) else result.get("status", 1)
                error = result.get("error") if isinstance(result, dict) else None
            except Exception:
                status = 1 if response.text.strip() == "1" else 0
                error = None

        return MixpanelTrackResult(status=status, error=error)

    @action("Query events within a date range", idempotent=True)
    async def query_events(
        self,
        from_date: str,
        to_date: str,
        event: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> PaginatedList[MixpanelEvent]:
        """Query events from the Mixpanel data export API.

        Args:
            from_date: Start date in YYYY-MM-DD format.
            to_date: End date in YYYY-MM-DD format.
            event: Filter by specific event name.
            limit: Maximum number of events to return.

        Returns:
            Paginated list of MixpanelEvent objects.
        """
        params: dict[str, Any] = {
            "from_date": from_date,
            "to_date": to_date,
        }
        if event is not None:
            params["event"] = json.dumps([event])
        if limit is not None:
            params["limit"] = limit

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(
                f"{_DATA_EXPORT_URL}/export",
                headers=self._get_query_headers(),
                params=params,
            )
            response.raise_for_status()

        # Export API returns JSONL (one JSON object per line)
        events: list[MixpanelEvent] = []
        for line in response.text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                event_data = json.loads(line)
                events.append(
                    MixpanelEvent(
                        event=event_data.get("event", ""),
                        properties=event_data.get("properties", {}),
                    )
                )
            except json.JSONDecodeError:
                logger.warning("Failed to parse event line: %s", line[:100])
                continue

        return PaginatedList(
            items=events,
            page_state=PageState(has_more=False),
        )

    @action("Get funnel analysis", idempotent=True)
    async def get_funnels(
        self,
        funnel_id: int,
        from_date: str,
        to_date: str,
    ) -> MixpanelFunnel:
        """Get funnel analysis data for a specific funnel.

        Args:
            funnel_id: The ID of the funnel to analyze.
            from_date: Start date in YYYY-MM-DD format.
            to_date: End date in YYYY-MM-DD format.

        Returns:
            MixpanelFunnel with step-by-step conversion data.
        """
        params: dict[str, Any] = {
            "funnel_id": funnel_id,
            "from_date": from_date,
            "to_date": to_date,
        }

        data = await self._query_request(
            "GET",
            f"{_QUERY_URL}/2.0/funnels",
            params=params,
        )

        # Parse funnel steps from the response
        steps: list[FunnelStep] = []
        funnel_data = data.get("data", {})

        # Mixpanel returns funnel data keyed by date ranges
        # Aggregate across dates for overall funnel
        if isinstance(funnel_data, dict):
            for _date_key, date_data in funnel_data.items():
                if isinstance(date_data, dict) and "steps" in date_data:
                    for step_data in date_data["steps"]:
                        steps.append(
                            FunnelStep(
                                count=step_data.get("count", 0),
                                step_conv_ratio=step_data.get("step_conv_ratio", 0.0),
                                overall_conv_ratio=step_data.get("overall_conv_ratio", 0.0),
                                avg_time=step_data.get("avg_time"),
                                event=step_data.get("event", ""),
                            )
                        )
                    break  # Use the first date range

        return MixpanelFunnel(
            funnel_id=funnel_id,
            name=data.get("meta", {}).get("name", ""),
            steps=steps,
            meta=data.get("meta", {}),
        )

    @action("Get retention analysis", idempotent=True)
    async def get_retention(
        self,
        from_date: str,
        to_date: str,
        event: str,
    ) -> MixpanelRetention:
        """Get retention analysis for a specific event.

        Args:
            from_date: Start date in YYYY-MM-DD format.
            to_date: End date in YYYY-MM-DD format.
            event: The event to measure retention for.

        Returns:
            MixpanelRetention with cohort-based retention data.
        """
        params: dict[str, Any] = {
            "from_date": from_date,
            "to_date": to_date,
            "born_event": json.dumps(event),
            "event": json.dumps(event),
        }

        data = await self._query_request(
            "GET",
            f"{_QUERY_URL}/2.0/retention",
            params=params,
        )

        cohorts: list[RetentionCohort] = []
        results = data.get("results", {})
        if isinstance(results, dict):
            for date_str, cohort_data in results.items():
                if isinstance(cohort_data, dict):
                    counts = cohort_data.get("counts", [])
                    first_count = counts[0] if counts else 0
                    percentages = [
                        (c / first_count * 100.0) if first_count > 0 else 0.0
                        for c in counts
                    ]
                    cohorts.append(
                        RetentionCohort(
                            date=date_str,
                            count=first_count,
                            percentages=percentages,
                        )
                    )

        return MixpanelRetention(
            cohorts=cohorts,
            meta=data.get("meta", {}),
        )

    @action("Export raw event data", idempotent=True)
    async def export_data(
        self,
        from_date: str,
        to_date: str,
        event: Optional[str] = None,
    ) -> list[MixpanelEvent]:
        """Export raw event data from Mixpanel.

        Args:
            from_date: Start date in YYYY-MM-DD format.
            to_date: End date in YYYY-MM-DD format.
            event: Filter by specific event name.

        Returns:
            List of MixpanelEvent objects with full event data.
        """
        params: dict[str, Any] = {
            "from_date": from_date,
            "to_date": to_date,
        }
        if event is not None:
            params["event"] = json.dumps([event])

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(
                f"{_DATA_EXPORT_URL}/export",
                headers=self._get_query_headers(),
                params=params,
            )
            response.raise_for_status()

        events: list[MixpanelEvent] = []
        for line in response.text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                event_data = json.loads(line)
                events.append(
                    MixpanelEvent(
                        event=event_data.get("event", ""),
                        properties=event_data.get("properties", {}),
                    )
                )
            except json.JSONDecodeError:
                continue

        return events

    @action("List all event names", idempotent=True)
    async def list_event_names(self) -> list[MixpanelEventName]:
        """List all tracked event names in the project.

        Returns:
            List of MixpanelEventName objects.
        """
        data = await self._query_request(
            "GET",
            f"{_QUERY_URL}/2.0/events/names",
        )

        names = data if isinstance(data, list) else []
        return [
            MixpanelEventName(name=name if isinstance(name, str) else str(name))
            for name in names
        ]

    @action("Get top events by volume", idempotent=True)
    async def get_top_events(
        self,
        limit: Optional[int] = None,
    ) -> list[MixpanelEventCount]:
        """Get the most frequently tracked events.

        Args:
            limit: Maximum number of events to return.

        Returns:
            List of MixpanelEventCount with event names and counts.
        """
        params: dict[str, Any] = {"type": "general"}
        if limit is not None:
            params["limit"] = limit

        data = await self._query_request(
            "GET",
            f"{_QUERY_URL}/2.0/events/top",
            params=params,
        )

        events: list[MixpanelEventCount] = []
        event_list = data.get("events", [])
        for event_data in event_list:
            events.append(
                MixpanelEventCount(
                    event=event_data.get("event", ""),
                    count=event_data.get("count", 0),
                )
            )

        return events

    @action("Get a user profile by distinct ID", idempotent=True)
    async def get_user_profile(
        self,
        distinct_id: str,
    ) -> MixpanelProfile:
        """Get a user's profile data from Mixpanel.

        Args:
            distinct_id: The unique identifier for the user.

        Returns:
            MixpanelProfile with user properties and metadata.
        """
        params: dict[str, Any] = {
            "distinct_id": distinct_id,
        }

        data = await self._query_request(
            "GET",
            f"{_QUERY_URL}/2.0/engage",
            params=params,
        )

        # The engage endpoint returns results array
        results = data.get("results", [])
        if results:
            profile_data = results[0]
            properties = profile_data.get("$properties", {})
            return MixpanelProfile(
                distinct_id=profile_data.get("$distinct_id", distinct_id),
                properties=properties,
                last_seen=properties.get("$last_seen"),
            )

        return MixpanelProfile(distinct_id=distinct_id)

    # ------------------------------------------------------------------
    # Actions -- Profile management (extended)
    # ------------------------------------------------------------------

    @action("Delete a user profile", dangerous=True)
    async def delete_profile(
        self, distinct_id: str,
    ) -> bool:
        """Delete a user profile from Mixpanel.

        Args:
            distinct_id: The user's distinct ID.

        Returns:
            True if the delete request was sent.
        """
        payload: dict[str, Any] = {
            "$distinct_id": distinct_id,
            "$delete": "",
            "$ignore_alias": True,
        }
        resp = await self._engage_request([payload])
        return resp.status_code == 200

    # ------------------------------------------------------------------
    # Actions -- Cohorts
    # ------------------------------------------------------------------

    @action("List cohorts in Mixpanel")
    async def list_cohorts(self) -> list[dict[str, Any]]:
        """List all defined cohorts.

        Returns:
            List of cohort dicts with id, name, count, etc.
        """
        resp = await self._data_request("GET", "/cohorts/list")
        return resp.json() if isinstance(resp.json(), list) else []

    # ------------------------------------------------------------------
    # Actions -- Segmentation
    # ------------------------------------------------------------------

    @action("Get segmentation data for an event")
    async def get_segmentation(
        self,
        event: str,
        from_date: str,
        to_date: str,
        segment_property: Optional[str] = None,
    ) -> dict[str, Any]:
        """Get segmentation (event count breakdown) data.

        Args:
            event: The event name to segment.
            from_date: Start date in YYYY-MM-DD format.
            to_date: End date in YYYY-MM-DD format.
            segment_property: Optional property to segment by.

        Returns:
            Dict with segmentation data series.
        """
        params: dict[str, Any] = {
            "event": event,
            "from_date": from_date,
            "to_date": to_date,
        }
        if segment_property:
            params["on"] = f'properties["{segment_property}"]'
        resp = await self._data_request(
            "GET", "/segmentation", params=params,
        )
        return resp.json()

    # ------------------------------------------------------------------
    # Actions -- Property values
    # ------------------------------------------------------------------

    @action("Get property values for an event", idempotent=True)
    async def get_property_values(
        self,
        event: str,
        property: str,
        limit: Optional[int] = None,
    ) -> list[Any]:
        """Get the top values for a specific property on an event.

        Args:
            event: The event name.
            property: The property name to get values for.
            limit: Maximum number of values to return.

        Returns:
            List of property values (strings, numbers, etc.).
        """
        params: dict[str, Any] = {
            "event": event,
            "name": property,
            "type": "general",
        }
        if limit is not None:
            params["limit"] = limit

        data = await self._query_request(
            "GET",
            f"{_QUERY_URL}/2.0/events/properties/values",
            params=params,
        )
        return data if isinstance(data, list) else []

    # ------------------------------------------------------------------
    # Actions -- Event counts
    # ------------------------------------------------------------------

    @action("Get event count for a date range", idempotent=True)
    async def get_event_count(
        self,
        event: str,
        from_date: str,
        to_date: str,
    ) -> dict[str, Any]:
        """Get total event counts for a specific event in a date range.

        Args:
            event: The event name to count.
            from_date: Start date in YYYY-MM-DD format.
            to_date: End date in YYYY-MM-DD format.

        Returns:
            Dict with event count data keyed by date.
        """
        params: dict[str, Any] = {
            "event": json.dumps([event]),
            "from_date": from_date,
            "to_date": to_date,
            "type": "general",
            "unit": "day",
        }

        data = await self._query_request(
            "GET",
            f"{_QUERY_URL}/2.0/events",
            params=params,
        )
        return data

    # ------------------------------------------------------------------
    # Actions -- Annotations
    # ------------------------------------------------------------------

    @action("Create an annotation in Mixpanel", dangerous=True)
    async def create_annotation(
        self,
        date: str,
        description: str,
    ) -> dict[str, Any]:
        """Create a time-stamped annotation (e.g. deploy marker).

        Annotations appear on Mixpanel charts to mark significant
        events like deployments, launches, or incidents.

        Args:
            date: Annotation date in YYYY-MM-DD format.
            description: Description text for the annotation.

        Returns:
            Dict with the created annotation details.
        """
        data = await self._query_request(
            "POST",
            f"{_QUERY_URL}/2.0/annotations",
            params={
                "date": date,
                "description": description,
            },
        )
        return data if isinstance(data, dict) else {}
