"""Connector lifecycle error subtree."""

from __future__ import annotations

from typing import Any

from .base import ToolsConnectorError


class ConnectorError(ToolsConnectorError):
    """Base exception for connector lifecycle failures."""

    def __init__(
        self,
        message: str = "A connector error occurred.",
        *,
        connector: str = "",
        action: str | None = None,
        code: str = "CONNECTOR_INIT_FAILED",
        retry_eligible: bool = False,
        retry_after_seconds: float | None = None,
        suggestion: str | None = "Review connector configuration and initialization.",
        details: dict[str, Any] | None = None,
        upstream_status: int | None = None,
    ) -> None:
        super().__init__(
            message,
            connector=connector,
            action=action,
            code=code,
            retry_eligible=retry_eligible,
            retry_after_seconds=retry_after_seconds,
            suggestion=suggestion,
            details=details,
            upstream_status=upstream_status,
        )


class ConnectorNotConfiguredError(ConnectorError):
    """The connector has not been configured with the required credentials or settings."""

    def __init__(
        self,
        message: str = "Connector is not configured.",
        *,
        connector: str = "",
        action: str | None = None,
        code: str = "CONNECTOR_NOT_CONFIGURED",
        retry_eligible: bool = False,
        retry_after_seconds: float | None = None,
        suggestion: str
        | None = "Provide the required credentials or configuration before using this connector.",
        details: dict[str, Any] | None = None,
        upstream_status: int | None = None,
    ) -> None:
        super().__init__(
            message,
            connector=connector,
            action=action,
            code=code,
            retry_eligible=retry_eligible,
            retry_after_seconds=retry_after_seconds,
            suggestion=suggestion,
            details=details,
            upstream_status=upstream_status,
        )


class ConnectorInitError(ConnectorError):
    """The connector failed during initialization (e.g. bad credentials, missing deps)."""

    def __init__(
        self,
        message: str = "Connector initialization failed.",
        *,
        connector: str = "",
        action: str | None = None,
        code: str = "CONNECTOR_INIT_FAILED",
        retry_eligible: bool = False,
        retry_after_seconds: float | None = None,
        suggestion: str
        | None = "Check that all required dependencies are installed and credentials are valid.",
        details: dict[str, Any] | None = None,
        upstream_status: int | None = None,
    ) -> None:
        super().__init__(
            message,
            connector=connector,
            action=action,
            code=code,
            retry_eligible=retry_eligible,
            retry_after_seconds=retry_after_seconds,
            suggestion=suggestion,
            details=details,
            upstream_status=upstream_status,
        )


class ActionNotFoundError(ConnectorError):
    """The requested action does not exist on this connector."""

    def __init__(
        self,
        message: str = "Action not found on this connector.",
        *,
        connector: str = "",
        action: str | None = None,
        code: str = "CONNECTOR_ACTION_NOT_FOUND",
        retry_eligible: bool = False,
        retry_after_seconds: float | None = None,
        suggestion: str
        | None = "Verify the action name. Use connector.list_actions() to see available actions.",
        details: dict[str, Any] | None = None,
        upstream_status: int | None = None,
    ) -> None:
        super().__init__(
            message,
            connector=connector,
            action=action,
            code=code,
            retry_eligible=retry_eligible,
            retry_after_seconds=retry_after_seconds,
            suggestion=suggestion,
            details=details,
            upstream_status=upstream_status,
        )


class PaginationNotWiredError(ConnectorError):
    """A page advertised ``has_more=True`` but carried no way to fetch the next page.

    This is a **connector bug, not a caller mistake**. The connector built a
    :class:`~toolsconnector.types.PaginatedList` whose ``page_state`` says more
    results exist, but never assigned ``_fetch_next``, so
    :meth:`~toolsconnector.types.PaginatedList.anext_page` has no callable to
    invoke.

    Raising here is deliberate. The alternative — returning ``None`` — makes
    ``anext_page()`` and ``collect()`` hand back page one and look complete,
    so a caller (or an agent) silently acts on a truncated result set and has
    no way to tell. A loud failure is strictly better than a quiet wrong
    answer.
    """

    def __init__(
        self,
        message: str = (
            "This page reports more results are available, but the connector did not "
            "provide a way to fetch them. The result set is incomplete."
        ),
        *,
        connector: str = "",
        action: str | None = None,
        code: str = "CONNECTOR_PAGINATION_NOT_WIRED",
        retry_eligible: bool = False,
        retry_after_seconds: float | None = None,
        suggestion: str | None = (
            "Connector bug: the action must set `result._fetch_next` whenever it sets "
            "`has_more=True`. Until it is fixed, page manually by passing the cursor in "
            "`page.page_state` back to the action."
        ),
        details: dict[str, Any] | None = None,
        upstream_status: int | None = None,
    ) -> None:
        super().__init__(
            message,
            connector=connector,
            action=action,
            code=code,
            retry_eligible=retry_eligible,
            retry_after_seconds=retry_after_seconds,
            suggestion=suggestion,
            details=details,
            upstream_status=upstream_status,
        )
