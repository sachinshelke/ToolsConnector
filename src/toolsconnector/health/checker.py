"""Connector health checker.

Validates that connectors can connect to their APIs,
detects credential issues, and reports health status.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("toolsconnector.health")


@dataclass
class HealthReport:
    """Health report for a single connector."""

    connector_name: str
    healthy: bool
    latency_ms: Optional[float] = None
    error: Optional[str] = None
    suggestion: Optional[str] = None
    checked_at: Optional[str] = None  # ISO timestamp
    actions_count: int = 0
    spec_valid: bool = True


@dataclass
class SystemHealthReport:
    """Health report for all connectors."""

    total: int = 0
    healthy: int = 0
    degraded: int = 0
    unavailable: int = 0
    reports: list[HealthReport] = field(default_factory=list)

    @property
    def all_healthy(self) -> bool:
        """Return True if every connector is healthy."""
        return self.healthy == self.total


class HealthChecker:
    """Checks health of connectors.

    Validates:
        1. Connector class imports correctly.
        2. ``get_spec()`` returns a valid spec.
        3. Connector can be instantiated with credentials.
        4. ``_health_check()`` passes (if implemented).
    """

    def __init__(self, connectors: Optional[list[str]] = None) -> None:
        """Initialize health checker.

        Args:
            connectors: List of connector names to check.
                If None, checks all registered connectors.
        """
        from toolsconnector.serve._discovery import list_connectors

        self._connector_names = connectors or list_connectors()

    async def check_all(
        self,
        credentials: Optional[dict[str, str]] = None,
        timeout: float = 10.0,
    ) -> SystemHealthReport:
        """Check health of all configured connectors.

        Args:
            credentials: Optional credentials dict for live health checks.
            timeout: Timeout per connector check in seconds.

        Returns:
            SystemHealthReport with per-connector results.
        """
        report = SystemHealthReport(total=len(self._connector_names))

        tasks = [self._check_one(name, credentials, timeout) for name in self._connector_names]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            # asyncio.gather(return_exceptions=True) returns
            # list[T | BaseException] — wider than just Exception so narrow
            # against BaseException to fully exhaust the union for mypy.
            if isinstance(result, BaseException):
                report.unavailable += 1
                report.reports.append(
                    HealthReport(
                        connector_name="unknown",
                        healthy=False,
                        error=str(result),
                    )
                )
            elif result.healthy:
                report.healthy += 1
                report.reports.append(result)
            else:
                report.degraded += 1
                report.reports.append(result)

        return report

    async def _check_one(
        self,
        name: str,
        credentials: Optional[dict[str, str]],
        timeout: float,
    ) -> HealthReport:
        """Check a single connector's health.

        Args:
            name: Connector name to check.
            credentials: Optional credentials dict keyed by connector name.
            timeout: Timeout for live health checks in seconds.

        Returns:
            HealthReport for the connector.
        """
        from datetime import datetime, timezone

        checked_at = datetime.now(timezone.utc).isoformat()
        start = time.monotonic()

        # Step 1: Import check
        try:
            from toolsconnector.serve._discovery import get_connector_class

            cls = get_connector_class(name)
        except Exception as e:
            return HealthReport(
                connector_name=name,
                healthy=False,
                error=f"Import failed: {e}",
                suggestion=f'pip install "toolsconnector[{name}]"',
                checked_at=checked_at,
            )

        # Step 2: Spec validation
        try:
            spec = cls.get_spec()
            if not spec.name or not spec.actions:
                return HealthReport(
                    connector_name=name,
                    healthy=False,
                    error="Invalid spec: missing name or actions",
                    checked_at=checked_at,
                )
        except Exception as e:
            return HealthReport(
                connector_name=name,
                healthy=False,
                error=f"Spec generation failed: {e}",
                checked_at=checked_at,
            )

        # Step 3: Instantiation check (if credentials available)
        cred = None
        if credentials:
            cred = credentials.get(name)

        if cred:
            try:
                instance = cls(credentials=cred)
                await asyncio.wait_for(instance._setup(), timeout=timeout)
                health = await asyncio.wait_for(instance._health_check(), timeout=timeout)
                latency = (time.monotonic() - start) * 1000
                await instance._teardown()

                return HealthReport(
                    connector_name=name,
                    healthy=health.healthy,
                    latency_ms=round(latency, 1),
                    error=health.message if not health.healthy else None,
                    checked_at=checked_at,
                    actions_count=len(spec.actions),
                    spec_valid=True,
                )
            except asyncio.TimeoutError:
                return HealthReport(
                    connector_name=name,
                    healthy=False,
                    error=f"Health check timed out after {timeout}s",
                    checked_at=checked_at,
                    actions_count=len(spec.actions),
                )
            except Exception as e:
                return HealthReport(
                    connector_name=name,
                    healthy=False,
                    error=f"Health check failed: {e}",
                    checked_at=checked_at,
                    actions_count=len(spec.actions),
                )

        # No credentials -- just verify spec is valid
        latency = (time.monotonic() - start) * 1000
        return HealthReport(
            connector_name=name,
            healthy=True,
            latency_ms=round(latency, 1),
            checked_at=checked_at,
            actions_count=len(spec.actions),
            spec_valid=True,
        )

    def check_all_sync(
        self,
        credentials: Optional[dict[str, str]] = None,
        timeout: float = 10.0,
    ) -> SystemHealthReport:
        """Sync version of check_all.

        Args:
            credentials: Optional credentials dict for live health checks.
            timeout: Timeout per connector check in seconds.

        Returns:
            SystemHealthReport with per-connector results.
        """
        return asyncio.run(self.check_all(credentials, timeout))
