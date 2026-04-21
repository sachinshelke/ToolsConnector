"""AWS CloudWatch connector -- metrics, alarms, dashboards, and log management.

Uses two AWS JSON APIs:

* **CloudWatch Metrics/Alarms/Dashboards** at
  ``monitoring.{region}.amazonaws.com`` with
  ``X-Amz-Target: GraniteServiceVersion20100801.{Action}``
  and ``application/x-amz-json-1.0``.

* **CloudWatch Logs** at ``logs.{region}.amazonaws.com`` with
  ``X-Amz-Target: Logs_20140328.{Action}``
  and ``application/x-amz-json-1.1``.

Credentials should be ``"access_key:secret_key:region"`` format or any
format accepted by ``parse_credentials``.

.. note::

    The SigV4 signing implementation is simplified. For production
    workloads, ``boto3`` is strongly recommended.
"""

from __future__ import annotations

import datetime
import hashlib
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
from toolsconnector.errors import APIError, NotFoundError

from toolsconnector.connectors._aws.signing import sign_v4

from .types import (
    CWDashboard,
    CWLogEvent,
    CWLogGroup,
    CWLogStream,
    CWMetric,
    CWMetricAlarm,
    CWMetricDataResult,
)

logger = logging.getLogger("toolsconnector.cloudwatch")

_CW_TARGET_PREFIX = "GraniteServiceVersion20100801"
_LOGS_TARGET_PREFIX = "Logs_20140328"


class CloudWatch(BaseConnector):
    """Connect to AWS CloudWatch for metrics, alarms, dashboards, and logs.

    Credentials format: ``"access_key_id:secret_access_key:region"``

    Uses two JSON APIs:

    * **Metrics/Alarms/Dashboards** --
      ``X-Amz-Target: GraniteServiceVersion20100801.{Action}``
    * **Logs** --
      ``X-Amz-Target: Logs_20140328.{Action}``

    .. note::

        SigV4 signing is simplified. For production, use ``boto3``.
    """

    name = "cloudwatch"
    display_name = "AWS CloudWatch"
    category = ConnectorCategory.DEVOPS
    protocol = ProtocolType.REST
    base_url = "https://monitoring.us-east-1.amazonaws.com"
    description = (
        "Monitor AWS resources with metrics, alarms, dashboards, "
        "and log management."
    )
    _rate_limit_config = RateLimitSpec(rate=50, period=1, burst=100)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Parse credentials and initialise the HTTP client."""
        from toolsconnector.connectors._aws.auth import parse_credentials

        creds = parse_credentials(self._credentials)
        self._access_key = creds.access_key_id
        self._secret_key = creds.secret_access_key
        self._region = creds.region
        self._session_token = creds.session_token

        # CloudWatch Metrics / Alarms / Dashboards endpoint
        self._cw_host = f"monitoring.{self._region}.amazonaws.com"
        self._cw_endpoint = f"https://{self._cw_host}"

        # CloudWatch Logs endpoint
        self._logs_host = f"logs.{self._region}.amazonaws.com"
        self._logs_endpoint = f"https://{self._logs_host}"

        self._client = httpx.AsyncClient(timeout=self._timeout)

    async def _teardown(self) -> None:
        """Close the HTTP client."""
        if hasattr(self, "_client"):
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _cw_request(
        self,
        target_action: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a signed CloudWatch Metrics/Alarms/Dashboards API request.

        Args:
            target_action: CloudWatch action name (e.g. ``DescribeAlarms``).
            payload: JSON request body dict.

        Returns:
            Parsed JSON response body.

        Raises:
            NotFoundError: If the requested resource is not found.
            APIError: For any CloudWatch API error.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        body = json.dumps(payload)
        payload_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()

        headers: dict[str, str] = {
            "Content-Type": "application/x-amz-json-1.0",
            "X-Amz-Target": f"{_CW_TARGET_PREFIX}.{target_action}",
            "x-amz-date": amz_date,
            "Host": self._cw_host,
        }

        sign_v4(
            "POST",
            self._cw_endpoint + "/",
            headers,
            payload_hash,
            self._access_key,
            self._secret_key,
            self._region,
            service="monitoring",
            session_token=self._session_token,
        )

        response = await self._client.post(
            self._cw_endpoint + "/",
            content=body,
            headers=headers,
        )

        if response.status_code >= 400:
            try:
                err_body = response.json()
            except Exception:
                err_body = {"message": response.text}

            err_type = err_body.get("__type", "")
            err_msg = err_body.get("message", err_body.get("Message", ""))
            full_msg = f"CloudWatch {target_action} error: {err_type} - {err_msg}"

            if "NotFound" in err_type or "ResourceNotFoundException" in err_type:
                raise NotFoundError(
                    full_msg,
                    connector="cloudwatch",
                    action=target_action,
                    details=err_body,
                )
            raise APIError(
                full_msg,
                connector="cloudwatch",
                action=target_action,
                upstream_status=response.status_code,
                details=err_body,
            )

        return response.json()

    async def _logs_request(
        self,
        target_action: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a signed CloudWatch Logs API request.

        Args:
            target_action: Logs action name (e.g. ``DescribeLogGroups``).
            payload: JSON request body dict.

        Returns:
            Parsed JSON response body.

        Raises:
            NotFoundError: If the requested resource is not found.
            APIError: For any CloudWatch Logs API error.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        body = json.dumps(payload)
        payload_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()

        headers: dict[str, str] = {
            "Content-Type": "application/x-amz-json-1.1",
            "X-Amz-Target": f"{_LOGS_TARGET_PREFIX}.{target_action}",
            "x-amz-date": amz_date,
            "Host": self._logs_host,
        }

        sign_v4(
            "POST",
            self._logs_endpoint + "/",
            headers,
            payload_hash,
            self._access_key,
            self._secret_key,
            self._region,
            service="logs",
            session_token=self._session_token,
        )

        response = await self._client.post(
            self._logs_endpoint + "/",
            content=body,
            headers=headers,
        )

        if response.status_code >= 400:
            try:
                err_body = response.json()
            except Exception:
                err_body = {"message": response.text}

            err_type = err_body.get("__type", "")
            err_msg = err_body.get("message", err_body.get("Message", ""))
            full_msg = f"CloudWatch Logs {target_action} error: {err_type} - {err_msg}"

            if "NotFound" in err_type or "ResourceNotFoundException" in err_type:
                raise NotFoundError(
                    full_msg,
                    connector="cloudwatch",
                    action=target_action,
                    details=err_body,
                )
            raise APIError(
                full_msg,
                connector="cloudwatch",
                action=target_action,
                upstream_status=response.status_code,
                details=err_body,
            )

        return response.json()

    # ------------------------------------------------------------------
    # Actions -- Metrics
    # ------------------------------------------------------------------

    @action("Get metric data for a specific time range")
    async def get_metric_data(
        self,
        metric_data_queries: list[dict],
        start_time: str,
        end_time: str,
    ) -> list[CWMetricDataResult]:
        """Get metric data for a specific time range.

        Args:
            metric_data_queries: List of MetricDataQuery dicts defining
                which metrics to retrieve.
            start_time: ISO 8601 start time for the query range.
            end_time: ISO 8601 end time for the query range.

        Returns:
            List of CWMetricDataResult with timestamps and values.
        """
        payload: dict[str, Any] = {
            "MetricDataQueries": metric_data_queries,
            "StartTime": start_time,
            "EndTime": end_time,
        }

        body = await self._cw_request("GetMetricData", payload)
        results = body.get("MetricDataResults", [])
        return [
            CWMetricDataResult(
                id=r.get("Id", ""),
                label=r.get("Label", ""),
                timestamps=[str(t) for t in r.get("Timestamps", [])],
                values=r.get("Values", []),
                status_code=r.get("StatusCode", ""),
            )
            for r in results
        ]

    @action("List available CloudWatch metrics")
    async def list_metrics(
        self,
        namespace: str = "",
        metric_name: str = "",
    ) -> list[CWMetric]:
        """List available CloudWatch metrics.

        Args:
            namespace: Filter by AWS namespace (e.g. AWS/EC2).
            metric_name: Filter by metric name.

        Returns:
            List of CWMetric descriptors.
        """
        payload: dict[str, Any] = {}
        if namespace:
            payload["Namespace"] = namespace
        if metric_name:
            payload["MetricName"] = metric_name

        body = await self._cw_request("ListMetrics", payload)
        metrics = body.get("Metrics", [])
        return [
            CWMetric(
                namespace=m.get("Namespace", ""),
                metric_name=m.get("MetricName", ""),
                dimensions=m.get("Dimensions", []),
            )
            for m in metrics
        ]

    @action("Get metric statistics")
    async def get_metric_statistics(
        self,
        namespace: str,
        metric_name: str,
        start_time: str,
        end_time: str,
        period: int = 300,
        statistics: Optional[list[str]] = None,
    ) -> dict:
        """Get metric statistics for a CloudWatch metric.

        Args:
            namespace: AWS namespace (e.g. AWS/EC2).
            metric_name: Name of the metric.
            start_time: ISO 8601 start time.
            end_time: ISO 8601 end time.
            period: Aggregation period in seconds.
            statistics: List of statistics to retrieve
                (e.g. Average, Sum, Maximum).

        Returns:
            Dict with Label and Datapoints from the API response.
        """
        payload: dict[str, Any] = {
            "Namespace": namespace,
            "MetricName": metric_name,
            "StartTime": start_time,
            "EndTime": end_time,
            "Period": period,
            "Statistics": statistics or ["Average"],
        }

        body = await self._cw_request("GetMetricStatistics", payload)
        return {
            "label": body.get("Label", ""),
            "datapoints": body.get("Datapoints", []),
        }

    @action("Publish custom metric data")
    async def put_metric_data(
        self,
        namespace: str,
        metric_data: list[dict],
    ) -> dict:
        """Publish custom metric data to CloudWatch.

        Args:
            namespace: Custom namespace for the metrics.
            metric_data: List of MetricDatum dicts with MetricName,
                Value, Unit, etc.

        Returns:
            Empty dict on success.
        """
        payload: dict[str, Any] = {
            "Namespace": namespace,
            "MetricData": metric_data,
        }

        await self._cw_request("PutMetricData", payload)
        return {}

    # ------------------------------------------------------------------
    # Actions -- Alarms
    # ------------------------------------------------------------------

    @action("Describe CloudWatch alarms")
    async def describe_alarms(
        self,
        alarm_names: Optional[list[str]] = None,
        state_value: str = "",
    ) -> list[CWMetricAlarm]:
        """Describe CloudWatch alarms.

        Args:
            alarm_names: Optional list of alarm names to describe.
            state_value: Filter by alarm state (OK, ALARM,
                INSUFFICIENT_DATA).

        Returns:
            List of CWMetricAlarm objects.
        """
        payload: dict[str, Any] = {}
        if alarm_names:
            payload["AlarmNames"] = alarm_names
        if state_value:
            payload["StateValue"] = state_value

        body = await self._cw_request("DescribeAlarms", payload)
        alarms = body.get("MetricAlarms", [])
        return [
            CWMetricAlarm(
                alarm_name=a.get("AlarmName", ""),
                alarm_arn=a.get("AlarmArn", ""),
                state_value=a.get("StateValue", ""),
                state_reason=a.get("StateReason", ""),
                metric_name=a.get("MetricName", ""),
                namespace=a.get("Namespace", ""),
                statistic=a.get("Statistic", ""),
                period=a.get("Period", 0),
                evaluation_periods=a.get("EvaluationPeriods", 0),
                threshold=a.get("Threshold", 0.0),
                comparison_operator=a.get("ComparisonOperator", ""),
                actions_enabled=a.get("ActionsEnabled", False),
                alarm_actions=a.get("AlarmActions", []),
                dimensions=a.get("Dimensions", []),
            )
            for a in alarms
        ]

    @action("Create or update a metric alarm")
    async def put_metric_alarm(
        self,
        alarm_name: str,
        metric_name: str,
        namespace: str,
        statistic: str = "Average",
        period: int = 300,
        evaluation_periods: int = 1,
        threshold: float = 0.0,
        comparison_operator: str = "GreaterThanThreshold",
        alarm_actions: Optional[list[str]] = None,
    ) -> dict:
        """Create or update a CloudWatch metric alarm.

        Args:
            alarm_name: Name of the alarm.
            metric_name: Name of the metric to alarm on.
            namespace: AWS namespace for the metric.
            statistic: Statistic to apply (Average, Sum, etc.).
            period: Evaluation period in seconds.
            evaluation_periods: Number of periods to evaluate.
            threshold: Threshold value for the alarm.
            comparison_operator: Comparison operator
                (e.g. GreaterThanThreshold).
            alarm_actions: List of ARNs to notify when alarm triggers.

        Returns:
            Empty dict on success.
        """
        payload: dict[str, Any] = {
            "AlarmName": alarm_name,
            "MetricName": metric_name,
            "Namespace": namespace,
            "Statistic": statistic,
            "Period": period,
            "EvaluationPeriods": evaluation_periods,
            "Threshold": threshold,
            "ComparisonOperator": comparison_operator,
        }
        if alarm_actions:
            payload["AlarmActions"] = alarm_actions

        await self._cw_request("PutMetricAlarm", payload)
        return {}

    @action("Delete CloudWatch alarms", dangerous=True)
    async def delete_alarms(
        self,
        alarm_names: list[str],
    ) -> dict:
        """Delete one or more CloudWatch alarms.

        Args:
            alarm_names: List of alarm names to delete.

        Returns:
            Empty dict on success.
        """
        payload: dict[str, Any] = {
            "AlarmNames": alarm_names,
        }

        await self._cw_request("DeleteAlarms", payload)
        return {}

    @action("Set an alarm state manually")
    async def set_alarm_state(
        self,
        alarm_name: str,
        state_value: str,
        state_reason: str,
    ) -> dict:
        """Set the state of a CloudWatch alarm manually.

        Args:
            alarm_name: Name of the alarm to update.
            state_value: New state (OK, ALARM, or INSUFFICIENT_DATA).
            state_reason: Human-readable reason for the state change.

        Returns:
            Empty dict on success.
        """
        payload: dict[str, Any] = {
            "AlarmName": alarm_name,
            "StateValue": state_value,
            "StateReason": state_reason,
        }

        await self._cw_request("SetAlarmState", payload)
        return {}

    @action("Describe alarm history")
    async def describe_alarm_history(
        self,
        alarm_name: str = "",
        history_item_type: str = "",
    ) -> list[dict]:
        """Describe the history of CloudWatch alarms.

        Args:
            alarm_name: Filter by alarm name.
            history_item_type: Filter by history item type
                (ConfigurationUpdate, StateUpdate, Action).

        Returns:
            List of alarm history item dicts.
        """
        payload: dict[str, Any] = {}
        if alarm_name:
            payload["AlarmName"] = alarm_name
        if history_item_type:
            payload["HistoryItemType"] = history_item_type

        body = await self._cw_request("DescribeAlarmHistory", payload)
        return body.get("AlarmHistoryItems", [])

    # ------------------------------------------------------------------
    # Actions -- Dashboards
    # ------------------------------------------------------------------

    @action("List CloudWatch dashboards")
    async def list_dashboards(
        self,
        dashboard_name_prefix: str = "",
    ) -> list[CWDashboard]:
        """List CloudWatch dashboards.

        Args:
            dashboard_name_prefix: Filter dashboards by name prefix.

        Returns:
            List of CWDashboard objects.
        """
        payload: dict[str, Any] = {}
        if dashboard_name_prefix:
            payload["DashboardNamePrefix"] = dashboard_name_prefix

        body = await self._cw_request("ListDashboards", payload)
        entries = body.get("DashboardEntries", [])
        return [
            CWDashboard(
                dashboard_name=d.get("DashboardName", ""),
                dashboard_arn=d.get("DashboardArn", ""),
                last_modified=(
                    str(d.get("LastModified", ""))
                    if d.get("LastModified") else None
                ),
                size=d.get("Size", 0),
            )
            for d in entries
        ]

    @action("Get a CloudWatch dashboard")
    async def get_dashboard(
        self,
        dashboard_name: str,
    ) -> dict:
        """Get a CloudWatch dashboard definition.

        Args:
            dashboard_name: Name of the dashboard to retrieve.

        Returns:
            Dict with dashboard_name, dashboard_arn, and dashboard_body.
        """
        payload: dict[str, Any] = {
            "DashboardName": dashboard_name,
        }

        body = await self._cw_request("GetDashboard", payload)
        return {
            "dashboard_name": body.get("DashboardName", ""),
            "dashboard_arn": body.get("DashboardArn", ""),
            "dashboard_body": body.get("DashboardBody", ""),
        }

    @action("Create or update a CloudWatch dashboard")
    async def put_dashboard(
        self,
        dashboard_name: str,
        dashboard_body: str,
    ) -> dict:
        """Create or update a CloudWatch dashboard.

        Args:
            dashboard_name: Name of the dashboard.
            dashboard_body: JSON string defining the dashboard widgets.

        Returns:
            Dict with any dashboard_validation_messages.
        """
        payload: dict[str, Any] = {
            "DashboardName": dashboard_name,
            "DashboardBody": dashboard_body,
        }

        body = await self._cw_request("PutDashboard", payload)
        return {
            "dashboard_validation_messages": body.get(
                "DashboardValidationMessages", []
            ),
        }

    @action("Delete CloudWatch dashboards", dangerous=True)
    async def delete_dashboards(
        self,
        dashboard_names: list[str],
    ) -> dict:
        """Delete one or more CloudWatch dashboards.

        Args:
            dashboard_names: List of dashboard names to delete.

        Returns:
            Empty dict on success.
        """
        payload: dict[str, Any] = {
            "DashboardNames": dashboard_names,
        }

        await self._cw_request("DeleteDashboards", payload)
        return {}

    # ------------------------------------------------------------------
    # Actions -- Logs
    # ------------------------------------------------------------------

    @action("Describe log groups")
    async def describe_log_groups(
        self,
        log_group_name_prefix: str = "",
    ) -> list[CWLogGroup]:
        """Describe CloudWatch Logs log groups.

        Args:
            log_group_name_prefix: Filter by log group name prefix.

        Returns:
            List of CWLogGroup objects.
        """
        payload: dict[str, Any] = {}
        if log_group_name_prefix:
            payload["logGroupNamePrefix"] = log_group_name_prefix

        body = await self._logs_request("DescribeLogGroups", payload)
        groups = body.get("logGroups", [])
        return [
            CWLogGroup(
                log_group_name=g.get("logGroupName", ""),
                log_group_arn=g.get("arn", ""),
                creation_time=g.get("creationTime"),
                retention_in_days=g.get("retentionInDays"),
                stored_bytes=g.get("storedBytes"),
            )
            for g in groups
        ]

    @action("Create a log group")
    async def create_log_group(
        self,
        log_group_name: str,
        retention_in_days: int = 0,
    ) -> dict:
        """Create a CloudWatch Logs log group.

        Args:
            log_group_name: Name for the new log group.
            retention_in_days: Number of days to retain log events.
                Set to 0 for indefinite retention.

        Returns:
            Empty dict on success.
        """
        payload: dict[str, Any] = {
            "logGroupName": log_group_name,
        }

        await self._logs_request("CreateLogGroup", payload)

        # Set retention separately if specified.
        if retention_in_days > 0:
            await self._logs_request(
                "PutRetentionPolicy",
                {
                    "logGroupName": log_group_name,
                    "retentionInDays": retention_in_days,
                },
            )

        return {}

    @action("Delete a log group", dangerous=True)
    async def delete_log_group(
        self,
        log_group_name: str,
    ) -> dict:
        """Delete a CloudWatch Logs log group.

        Args:
            log_group_name: Name of the log group to delete.

        Returns:
            Empty dict on success.
        """
        payload: dict[str, Any] = {
            "logGroupName": log_group_name,
        }

        await self._logs_request("DeleteLogGroup", payload)
        return {}

    @action("Describe log streams in a log group")
    async def describe_log_streams(
        self,
        log_group_name: str,
        log_stream_name_prefix: str = "",
        order_by: str = "LastEventTime",
        descending: bool = True,
    ) -> list[CWLogStream]:
        """Describe log streams within a log group.

        Args:
            log_group_name: Name of the log group.
            log_stream_name_prefix: Filter by stream name prefix.
            order_by: Order by LastEventTime or LogStreamName.
            descending: Whether to sort in descending order.

        Returns:
            List of CWLogStream objects.
        """
        payload: dict[str, Any] = {
            "logGroupName": log_group_name,
            "orderBy": order_by,
            "descending": descending,
        }
        if log_stream_name_prefix:
            payload["logStreamNamePrefix"] = log_stream_name_prefix

        body = await self._logs_request("DescribeLogStreams", payload)
        streams = body.get("logStreams", [])
        return [
            CWLogStream(
                log_stream_name=s.get("logStreamName", ""),
                creation_time=s.get("creationTime"),
                first_event_timestamp=s.get("firstEventTimestamp"),
                last_event_timestamp=s.get("lastEventTimestamp"),
                last_ingestion_time=s.get("lastIngestionTime"),
                stored_bytes=s.get("storedBytes"),
            )
            for s in streams
        ]

    @action("Get log events from a log stream")
    async def get_log_events(
        self,
        log_group_name: str,
        log_stream_name: str,
        start_time: int = 0,
        end_time: int = 0,
        limit: int = 100,
    ) -> list[CWLogEvent]:
        """Get log events from a specific log stream.

        Args:
            log_group_name: Name of the log group.
            log_stream_name: Name of the log stream.
            start_time: Start of the time range as epoch milliseconds.
                Set to 0 to omit.
            end_time: End of the time range as epoch milliseconds.
                Set to 0 to omit.
            limit: Maximum number of events to return.

        Returns:
            List of CWLogEvent objects.
        """
        payload: dict[str, Any] = {
            "logGroupName": log_group_name,
            "logStreamName": log_stream_name,
            "limit": limit,
        }
        if start_time > 0:
            payload["startTime"] = start_time
        if end_time > 0:
            payload["endTime"] = end_time

        body = await self._logs_request("GetLogEvents", payload)
        events = body.get("events", [])
        return [
            CWLogEvent(
                timestamp=e.get("timestamp"),
                message=e.get("message", ""),
                ingestion_time=e.get("ingestionTime"),
            )
            for e in events
        ]

    @action("Filter log events across log streams")
    async def filter_log_events(
        self,
        log_group_name: str,
        filter_pattern: str = "",
        start_time: int = 0,
        end_time: int = 0,
        limit: int = 100,
    ) -> list[CWLogEvent]:
        """Filter log events across log streams in a log group.

        Args:
            log_group_name: Name of the log group.
            filter_pattern: CloudWatch Logs filter pattern syntax.
            start_time: Start of the time range as epoch milliseconds.
                Set to 0 to omit.
            end_time: End of the time range as epoch milliseconds.
                Set to 0 to omit.
            limit: Maximum number of events to return.

        Returns:
            List of CWLogEvent objects matching the filter.
        """
        payload: dict[str, Any] = {
            "logGroupName": log_group_name,
            "limit": limit,
        }
        if filter_pattern:
            payload["filterPattern"] = filter_pattern
        if start_time > 0:
            payload["startTime"] = start_time
        if end_time > 0:
            payload["endTime"] = end_time

        body = await self._logs_request("FilterLogEvents", payload)
        events = body.get("events", [])
        return [
            CWLogEvent(
                timestamp=e.get("timestamp"),
                message=e.get("message", ""),
                ingestion_time=e.get("ingestionTime"),
            )
            for e in events
        ]

    @action("Put log events to a log stream")
    async def put_log_events(
        self,
        log_group_name: str,
        log_stream_name: str,
        log_events: list[dict],
    ) -> dict:
        """Put log events into a CloudWatch Logs log stream.

        Args:
            log_group_name: Name of the log group.
            log_stream_name: Name of the log stream.
            log_events: List of log event dicts with timestamp and
                message keys.

        Returns:
            Dict with nextSequenceToken on success.
        """
        payload: dict[str, Any] = {
            "logGroupName": log_group_name,
            "logStreamName": log_stream_name,
            "logEvents": log_events,
        }

        body = await self._logs_request("PutLogEvents", payload)
        return {
            "next_sequence_token": body.get("nextSequenceToken", ""),
        }
