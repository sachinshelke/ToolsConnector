"""Vercel connector -- deployments, projects, domains, and env vars.

Uses the Vercel REST API with Bearer token authentication.
Pagination uses cursor-based approach via the ``until`` parameter.
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

from .types import VercelDeployment, VercelDomain, VercelEnvVar, VercelProject

logger = logging.getLogger("toolsconnector.vercel")


def _parse_deployment(data: dict[str, Any]) -> VercelDeployment:
    """Parse a VercelDeployment from API JSON.

    Args:
        data: Raw JSON dict from the Vercel API.

    Returns:
        A VercelDeployment instance.
    """
    return VercelDeployment(
        uid=data.get("uid"),
        name=data.get("name"),
        url=data.get("url"),
        state=data.get("state"),
        type=data.get("type"),
        created=data.get("created"),
        ready=data.get("ready"),
        creator=data.get("creator"),
        meta=data.get("meta"),
        target=data.get("target"),
        alias_assigned=data.get("aliasAssigned"),
        alias_error=data.get("aliasError"),
        inspectorUrl=data.get("inspectorUrl"),
        building_at=data.get("buildingAt"),
        source=data.get("source"),
    )


def _parse_project(data: dict[str, Any]) -> VercelProject:
    """Parse a VercelProject from API JSON.

    Args:
        data: Raw JSON dict from the Vercel API.

    Returns:
        A VercelProject instance.
    """
    return VercelProject(
        id=data.get("id"),
        name=data.get("name"),
        framework=data.get("framework"),
        node_version=data.get("nodeVersion"),
        build_command=data.get("buildCommand"),
        dev_command=data.get("devCommand"),
        install_command=data.get("installCommand"),
        output_directory=data.get("outputDirectory"),
        root_directory=data.get("rootDirectory"),
        created_at=data.get("createdAt"),
        updated_at=data.get("updatedAt"),
        latest_deployments=data.get("latestDeployments") or [],
        live=data.get("live"),
        link=data.get("link"),
        env=data.get("env") or [],
    )


def _parse_domain(data: dict[str, Any]) -> VercelDomain:
    """Parse a VercelDomain from API JSON.

    Args:
        data: Raw JSON dict from the Vercel API.

    Returns:
        A VercelDomain instance.
    """
    return VercelDomain(
        name=data.get("name"),
        apexName=data.get("apexName"),
        redirect=data.get("redirect"),
        redirect_status_code=data.get("redirectStatusCode"),
        git_branch=data.get("gitBranch"),
        updated_at=data.get("updatedAt"),
        created_at=data.get("createdAt"),
        verified=data.get("verified"),
        project_id=data.get("projectId"),
    )


def _parse_env_var(data: dict[str, Any]) -> VercelEnvVar:
    """Parse a VercelEnvVar from API JSON.

    Args:
        data: Raw JSON dict from the Vercel API.

    Returns:
        A VercelEnvVar instance.
    """
    return VercelEnvVar(
        id=data.get("id"),
        key=data.get("key"),
        value=data.get("value"),
        type=data.get("type"),
        target=data.get("target") or [],
        git_branch=data.get("gitBranch"),
        created_at=data.get("createdAt"),
        updated_at=data.get("updatedAt"),
        system=data.get("system"),
        configuration_id=data.get("configurationId"),
    )


class Vercel(BaseConnector):
    """Connect to Vercel to manage deployments, projects, domains, and env vars.

    Authenticates via Bearer token in the ``Authorization`` header.
    Pagination uses cursor-based approach via the ``until`` parameter
    (the ``created`` timestamp of the last item in the previous page).
    """

    name = "vercel"
    display_name = "Vercel"
    category = ConnectorCategory.DEVOPS
    protocol = ProtocolType.REST
    base_url = "https://api.vercel.com"
    description = (
        "Connect to Vercel to manage deployments, projects, domains, "
        "and environment variables."
    )
    _rate_limit_config = RateLimitSpec(rate=500, period=60, burst=50)

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
    ) -> httpx.Response:
        """Send an authenticated request to the Vercel API.

        Args:
            method: HTTP method (GET, POST, DELETE).
            path: API path relative to base_url.
            params: Query parameters.
            json: JSON body for POST requests.

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
    # Actions -- Deployments
    # ------------------------------------------------------------------

    @action("List Vercel deployments")
    async def list_deployments(
        self,
        project_id: Optional[str] = None,
        limit: int = 20,
        page: Optional[str] = None,
    ) -> PaginatedList[VercelDeployment]:
        """List deployments, optionally filtered by project.

        Args:
            project_id: Filter deployments by project ID or name.
            limit: Maximum deployments per page (max 100).
            page: Cursor (``until`` timestamp) for the next page.

        Returns:
            Paginated list of VercelDeployment objects.
        """
        capped_limit = min(limit, 100)
        params: dict[str, Any] = {"limit": capped_limit}
        if project_id:
            params["projectId"] = project_id
        if page:
            params["until"] = page

        resp = await self._request("GET", "/v6/deployments", params=params)
        body = resp.json()
        items = [_parse_deployment(d) for d in body.get("deployments", [])]

        pagination = body.get("pagination", {})
        has_more = pagination.get("count", 0) >= capped_limit
        next_cursor = str(pagination.get("next")) if has_more else None
        ps = PageState(has_more=has_more, cursor=next_cursor)

        result = PaginatedList(items=items, page_state=ps)
        if ps.has_more:
            result._fetch_next = lambda c=ps.cursor: self.list_deployments(
                project_id=project_id, limit=capped_limit, page=c,
            )
        return result

    @action("Get a single Vercel deployment by ID")
    async def get_deployment(self, deployment_id: str) -> VercelDeployment:
        """Retrieve a single deployment by its ID or URL.

        Args:
            deployment_id: The deployment ID or URL.

        Returns:
            VercelDeployment object.
        """
        resp = await self._request(
            "GET", f"/v13/deployments/{deployment_id}",
        )
        return _parse_deployment(resp.json())

    # ------------------------------------------------------------------
    # Actions -- Projects
    # ------------------------------------------------------------------

    @action("List Vercel projects")
    async def list_projects(
        self,
        limit: int = 20,
        page: Optional[str] = None,
    ) -> PaginatedList[VercelProject]:
        """List projects in the Vercel account.

        Args:
            limit: Maximum projects per page (max 100).
            page: Cursor (``until`` timestamp) for the next page.

        Returns:
            Paginated list of VercelProject objects.
        """
        capped_limit = min(limit, 100)
        params: dict[str, Any] = {"limit": capped_limit}
        if page:
            params["until"] = page

        resp = await self._request("GET", "/v9/projects", params=params)
        body = resp.json()
        items = [_parse_project(p) for p in body.get("projects", [])]

        pagination = body.get("pagination", {})
        has_more = pagination.get("count", 0) >= capped_limit
        next_cursor = str(pagination.get("next")) if has_more else None
        ps = PageState(has_more=has_more, cursor=next_cursor)

        result = PaginatedList(items=items, page_state=ps)
        if ps.has_more:
            result._fetch_next = lambda c=ps.cursor: self.list_projects(
                limit=capped_limit, page=c,
            )
        return result

    @action("Get a single Vercel project by ID or name")
    async def get_project(self, project_id: str) -> VercelProject:
        """Retrieve a single project.

        Args:
            project_id: The project ID or name.

        Returns:
            VercelProject object.
        """
        resp = await self._request("GET", f"/v9/projects/{project_id}")
        return _parse_project(resp.json())

    # ------------------------------------------------------------------
    # Actions -- Domains
    # ------------------------------------------------------------------

    @action("List domains for a Vercel project")
    async def list_domains(
        self, project_id: str,
    ) -> list[VercelDomain]:
        """List domains configured for a project.

        Args:
            project_id: The project ID or name.

        Returns:
            List of VercelDomain objects.
        """
        resp = await self._request(
            "GET", f"/v9/projects/{project_id}/domains",
        )
        body = resp.json()
        return [_parse_domain(d) for d in body.get("domains", [])]

    @action("Add a domain to a Vercel project", dangerous=True)
    async def add_domain(
        self, project_id: str, domain: str,
    ) -> VercelDomain:
        """Add a domain to a project.

        Args:
            project_id: The project ID or name.
            domain: The domain name to add.

        Returns:
            The created VercelDomain object.
        """
        payload: dict[str, Any] = {"name": domain}
        resp = await self._request(
            "POST", f"/v10/projects/{project_id}/domains", json=payload,
        )
        return _parse_domain(resp.json())

    # ------------------------------------------------------------------
    # Actions -- Environment Variables
    # ------------------------------------------------------------------

    @action("List environment variables for a Vercel project")
    async def list_env_vars(
        self, project_id: str,
    ) -> list[VercelEnvVar]:
        """List environment variables configured for a project.

        Args:
            project_id: The project ID or name.

        Returns:
            List of VercelEnvVar objects.
        """
        resp = await self._request(
            "GET", f"/v9/projects/{project_id}/env",
        )
        body = resp.json()
        return [_parse_env_var(e) for e in body.get("envs", [])]

    @action("Create an environment variable for a Vercel project", dangerous=True)
    async def create_env_var(
        self,
        project_id: str,
        key: str,
        value: str,
        target: str,
    ) -> VercelEnvVar:
        """Create an environment variable for a project.

        Args:
            project_id: The project ID or name.
            key: The environment variable name.
            value: The environment variable value.
            target: Deployment target(s): ``production``, ``preview``,
                or ``development``. Comma-separate for multiple.

        Returns:
            The created VercelEnvVar object.
        """
        targets = [t.strip() for t in target.split(",")]
        payload: dict[str, Any] = {
            "key": key,
            "value": value,
            "target": targets,
            "type": "encrypted",
        }
        resp = await self._request(
            "POST", f"/v10/projects/{project_id}/env", json=payload,
        )
        return _parse_env_var(resp.json())
