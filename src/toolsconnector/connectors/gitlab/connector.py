"""GitLab connector — projects, issues, merge requests, and CI/CD pipelines.

Uses the GitLab REST API v4 with private token authentication.
Page-number pagination via ``X-Total`` / ``X-Total-Pages`` headers.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from urllib.parse import quote

import httpx

from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import (
    ConnectorCategory,
    ProtocolType,
    RateLimitSpec,
)
from toolsconnector.types import PageState, PaginatedList

from ._parsers import (
    parse_branch,
    parse_comment,
    parse_issue,
    parse_job,
    parse_label,
    parse_member,
    parse_merge_request,
    parse_milestone,
    parse_pipeline,
    parse_project,
    parse_tag,
)
from .types import (
    GitLabBranch,
    GitLabComment,
    GitLabIssue,
    GitLabJob,
    GitLabLabel,
    GitLabMember,
    GitLabMilestone,
    GitLabTag,
    MergeRequest,
    Pipeline,
    Project,
)

logger = logging.getLogger("toolsconnector.gitlab")


def _encode_project_id(project_id: str | int) -> str:
    """URL-encode a project ID for the GitLab API.

    Numeric IDs pass through as-is. Path-style IDs
    (e.g. ``"mygroup/myproject"``) are URL-encoded.

    Args:
        project_id: Numeric project ID or ``namespace/project`` path.

    Returns:
        URL-safe string for inclusion in API paths.
    """
    sid = str(project_id)
    if sid.isdigit():
        return sid
    return quote(sid, safe="")


class GitLab(BaseConnector):
    """Connect to GitLab to manage projects, issues, MRs, and pipelines.

    Supports private token authentication via ``PRIVATE-TOKEN`` header.
    Uses the GitLab REST API v4. The ``base_url`` defaults to
    ``https://gitlab.com/api/v4`` but can be overridden for self-hosted
    instances.
    """

    name = "gitlab"
    display_name = "GitLab"
    category = ConnectorCategory.CODE_PLATFORM
    protocol = ProtocolType.REST
    base_url = "https://gitlab.com/api/v4"
    description = "Connect to GitLab to manage projects, issues, MRs, and pipelines."
    _rate_limit_config = RateLimitSpec(rate=2000, period=60, burst=200)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Initialise the httpx async client."""
        headers: dict[str, str] = {"Accept": "application/json"}
        if self._credentials:
            headers["PRIVATE-TOKEN"] = str(self._credentials)

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
        """Send an authenticated request and handle errors.

        Args:
            method: HTTP method (GET, POST, etc.).
            path: API path relative to base_url.
            params: Query parameters.
            json: JSON body for POST/PUT.

        Returns:
            httpx.Response object.

        Raises:
            httpx.HTTPStatusError: On 4xx/5xx responses.
        """
        resp = await self._client.request(
            method, path, params=params, json=json,
        )

        remaining = resp.headers.get("RateLimit-Remaining")
        if remaining is not None:
            logger.debug("GitLab rate-limit remaining: %s", remaining)

        resp.raise_for_status()
        return resp

    def _build_page_state(
        self, resp: httpx.Response, current_page: int,
    ) -> PageState:
        """Build a PageState from GitLab pagination headers.

        GitLab uses ``X-Total``, ``X-Total-Pages``, ``X-Page``, and
        ``X-Next-Page`` headers for page-number pagination.

        Args:
            resp: The HTTP response to extract pagination from.
            current_page: The page number that was just fetched.

        Returns:
            PageState with page_number and total_count populated.
        """
        total_str = resp.headers.get("X-Total")
        total_pages_str = resp.headers.get("X-Total-Pages")
        next_page_str = resp.headers.get("X-Next-Page")

        total_count = int(total_str) if total_str else None
        total_pages = int(total_pages_str) if total_pages_str else None

        has_more = False
        next_page_num: Optional[int] = None
        if next_page_str and next_page_str.strip():
            next_page_num = int(next_page_str)
            has_more = True
        elif total_pages is not None:
            has_more = current_page < total_pages

        return PageState(
            page_number=next_page_num if has_more else current_page,
            total_count=total_count,
            has_more=has_more,
        )

    # ------------------------------------------------------------------
    # Actions -- Projects
    # ------------------------------------------------------------------

    @action("List GitLab projects")
    async def list_projects(
        self,
        owned: Optional[bool] = None,
        search: Optional[str] = None,
        limit: int = 20,
        page: int = 1,
    ) -> PaginatedList[Project]:
        """List GitLab projects visible to the authenticated user.

        Args:
            owned: If true, only return projects owned by the current user.
            search: Search projects by name.
            limit: Maximum projects per page (max 100).
            page: Page number (1-indexed).

        Returns:
            Paginated list of Project objects.
        """
        params: dict[str, Any] = {"per_page": min(limit, 100), "page": page}
        if owned is not None:
            params["owned"] = str(owned).lower()
        if search:
            params["search"] = search

        resp = await self._request("GET", "/projects", params=params)
        items = [parse_project(p) for p in resp.json()]
        ps = self._build_page_state(resp, page)

        result = PaginatedList(
            items=items, page_state=ps, total_count=ps.total_count,
        )
        if ps.has_more and ps.page_number is not None:
            np = ps.page_number
            result._fetch_next = lambda pg=np: self.alist_projects(
                owned=owned, search=search, limit=limit, page=pg,
            )
        return result

    @action("Get a single project by ID")
    async def get_project(self, project_id: str) -> Project:
        """Retrieve a single project.

        Args:
            project_id: Numeric project ID or URL-encoded
                ``namespace/project`` path.

        Returns:
            Project object.
        """
        encoded = _encode_project_id(project_id)
        resp = await self._request("GET", f"/projects/{encoded}")
        return parse_project(resp.json())

    # ------------------------------------------------------------------
    # Actions -- Issues
    # ------------------------------------------------------------------

    @action("List issues for a GitLab project")
    async def list_issues(
        self,
        project_id: str,
        state: Optional[str] = None,
        labels: Optional[str] = None,
        limit: int = 20,
        page: int = 1,
    ) -> PaginatedList[GitLabIssue]:
        """List issues for a project.

        Args:
            project_id: Numeric project ID or ``namespace/project`` path.
            state: Filter by state: ``opened``, ``closed``, or ``all``.
            labels: Comma-separated list of label names to filter by.
            limit: Maximum issues per page (max 100).
            page: Page number (1-indexed).

        Returns:
            Paginated list of GitLabIssue objects.
        """
        encoded = _encode_project_id(project_id)
        params: dict[str, Any] = {"per_page": min(limit, 100), "page": page}
        if state:
            params["state"] = state
        if labels:
            params["labels"] = labels

        resp = await self._request(
            "GET", f"/projects/{encoded}/issues", params=params,
        )
        items = [parse_issue(i) for i in resp.json()]
        ps = self._build_page_state(resp, page)

        result = PaginatedList(
            items=items, page_state=ps, total_count=ps.total_count,
        )
        if ps.has_more and ps.page_number is not None:
            np = ps.page_number
            result._fetch_next = lambda pg=np: self.alist_issues(
                project_id=project_id, state=state, labels=labels,
                limit=limit, page=pg,
            )
        return result

    @action("Create an issue in a GitLab project", dangerous=True)
    async def create_issue(
        self,
        project_id: str,
        title: str,
        description: Optional[str] = None,
        labels: Optional[str] = None,
    ) -> GitLabIssue:
        """Create a new issue in a project.

        Args:
            project_id: Numeric project ID or ``namespace/project`` path.
            title: Issue title.
            description: Issue description in Markdown.
            labels: Comma-separated list of label names to apply.

        Returns:
            The created GitLabIssue object.
        """
        encoded = _encode_project_id(project_id)
        payload: dict[str, Any] = {"title": title}
        if description is not None:
            payload["description"] = description
        if labels:
            payload["labels"] = labels

        resp = await self._request(
            "POST", f"/projects/{encoded}/issues", json=payload,
        )
        return parse_issue(resp.json())

    # ------------------------------------------------------------------
    # Actions -- Merge Requests
    # ------------------------------------------------------------------

    @action("List merge requests for a GitLab project")
    async def list_merge_requests(
        self,
        project_id: str,
        state: Optional[str] = None,
        limit: int = 20,
        page: int = 1,
    ) -> PaginatedList[MergeRequest]:
        """List merge requests for a project.

        Args:
            project_id: Numeric project ID or ``namespace/project`` path.
            state: Filter by state: ``opened``, ``closed``, ``merged``,
                or ``all``.
            limit: Maximum MRs per page (max 100).
            page: Page number (1-indexed).

        Returns:
            Paginated list of MergeRequest objects.
        """
        encoded = _encode_project_id(project_id)
        params: dict[str, Any] = {"per_page": min(limit, 100), "page": page}
        if state:
            params["state"] = state

        resp = await self._request(
            "GET", f"/projects/{encoded}/merge_requests", params=params,
        )
        items = [parse_merge_request(mr) for mr in resp.json()]
        ps = self._build_page_state(resp, page)

        result = PaginatedList(
            items=items, page_state=ps, total_count=ps.total_count,
        )
        if ps.has_more and ps.page_number is not None:
            np = ps.page_number
            result._fetch_next = lambda pg=np: self.alist_merge_requests(
                project_id=project_id, state=state, limit=limit, page=pg,
            )
        return result

    @action("Create a merge request in a GitLab project", dangerous=True)
    async def create_merge_request(
        self,
        project_id: str,
        source_branch: str,
        target_branch: str,
        title: str,
        description: Optional[str] = None,
    ) -> MergeRequest:
        """Create a new merge request.

        Args:
            project_id: Numeric project ID or ``namespace/project`` path.
            source_branch: The source branch for the MR.
            target_branch: The target branch for the MR.
            title: Merge request title.
            description: Merge request description in Markdown.

        Returns:
            The created MergeRequest object.
        """
        encoded = _encode_project_id(project_id)
        payload: dict[str, Any] = {
            "source_branch": source_branch,
            "target_branch": target_branch,
            "title": title,
        }
        if description is not None:
            payload["description"] = description

        resp = await self._request(
            "POST", f"/projects/{encoded}/merge_requests", json=payload,
        )
        return parse_merge_request(resp.json())

    # ------------------------------------------------------------------
    # Actions -- Pipelines
    # ------------------------------------------------------------------

    @action("List CI/CD pipelines for a GitLab project")
    async def list_pipelines(
        self,
        project_id: str,
        status: Optional[str] = None,
        limit: int = 20,
        page: int = 1,
    ) -> PaginatedList[Pipeline]:
        """List CI/CD pipelines for a project.

        Args:
            project_id: Numeric project ID or ``namespace/project`` path.
            status: Filter by status: ``running``, ``pending``,
                ``success``, ``failed``, ``canceled``, ``skipped``,
                ``created``, ``manual``.
            limit: Maximum pipelines per page (max 100).
            page: Page number (1-indexed).

        Returns:
            Paginated list of Pipeline objects.
        """
        encoded = _encode_project_id(project_id)
        params: dict[str, Any] = {"per_page": min(limit, 100), "page": page}
        if status:
            params["status"] = status

        resp = await self._request(
            "GET", f"/projects/{encoded}/pipelines", params=params,
        )
        items = [parse_pipeline(p) for p in resp.json()]
        ps = self._build_page_state(resp, page)

        result = PaginatedList(
            items=items, page_state=ps, total_count=ps.total_count,
        )
        if ps.has_more and ps.page_number is not None:
            np = ps.page_number
            result._fetch_next = lambda pg=np: self.alist_pipelines(
                project_id=project_id, status=status, limit=limit, page=pg,
            )
        return result

    @action("Get a single pipeline by ID")
    async def get_pipeline(
        self, project_id: str, pipeline_id: int,
    ) -> Pipeline:
        """Retrieve a single pipeline with full details.

        Args:
            project_id: Numeric project ID or ``namespace/project`` path.
            pipeline_id: The pipeline ID.

        Returns:
            Pipeline object with timing and coverage details.
        """
        encoded = _encode_project_id(project_id)
        resp = await self._request(
            "GET", f"/projects/{encoded}/pipelines/{pipeline_id}",
        )
        return parse_pipeline(resp.json())

    # ------------------------------------------------------------------
    # Actions -- Merge Request details
    # ------------------------------------------------------------------

    @action("Get a single merge request by IID")
    async def get_merge_request(
        self,
        project_id: str,
        mr_iid: int,
    ) -> MergeRequest:
        """Retrieve a single merge request with full details.

        Args:
            project_id: Numeric project ID or ``namespace/project`` path.
            mr_iid: The merge request internal ID (IID).

        Returns:
            MergeRequest object.
        """
        encoded = _encode_project_id(project_id)
        resp = await self._request(
            "GET", f"/projects/{encoded}/merge_requests/{mr_iid}",
        )
        return parse_merge_request(resp.json())

    # ------------------------------------------------------------------
    # Actions -- Comments (Notes)
    # ------------------------------------------------------------------

    @action("Create a comment on an issue", dangerous=True)
    async def create_comment(
        self,
        project_id: str,
        issue_iid: int,
        body: str,
    ) -> GitLabComment:
        """Create a new comment (note) on a project issue.

        Args:
            project_id: Numeric project ID or ``namespace/project`` path.
            issue_iid: The issue internal ID (IID).
            body: Comment text in Markdown format.

        Returns:
            The created GitLabComment object.
        """
        encoded = _encode_project_id(project_id)
        payload: dict[str, Any] = {"body": body}
        resp = await self._request(
            "POST",
            f"/projects/{encoded}/issues/{issue_iid}/notes",
            json=payload,
        )
        return parse_comment(resp.json())

    # ------------------------------------------------------------------
    # Actions -- CI/CD Jobs
    # ------------------------------------------------------------------

    @action("List jobs for a pipeline")
    async def list_jobs(
        self,
        project_id: str,
        pipeline_id: int,
    ) -> list[GitLabJob]:
        """List all jobs for a CI/CD pipeline.

        Args:
            project_id: Numeric project ID or ``namespace/project`` path.
            pipeline_id: The pipeline ID.

        Returns:
            List of GitLabJob objects.
        """
        encoded = _encode_project_id(project_id)
        resp = await self._request(
            "GET",
            f"/projects/{encoded}/pipelines/{pipeline_id}/jobs",
            params={"per_page": 100},
        )
        return [parse_job(j) for j in resp.json()]

    @action("Retry a failed pipeline", dangerous=True)
    async def retry_pipeline(
        self,
        project_id: str,
        pipeline_id: int,
    ) -> Pipeline:
        """Retry all failed jobs in a pipeline.

        Args:
            project_id: Numeric project ID or ``namespace/project`` path.
            pipeline_id: The pipeline ID to retry.

        Returns:
            The retried Pipeline object.
        """
        encoded = _encode_project_id(project_id)
        resp = await self._request(
            "POST",
            f"/projects/{encoded}/pipelines/{pipeline_id}/retry",
        )
        return parse_pipeline(resp.json())

    # ------------------------------------------------------------------
    # Actions -- Branches
    # ------------------------------------------------------------------

    @action("List branches for a project")
    async def list_branches(
        self,
        project_id: str,
        search: Optional[str] = None,
        limit: int = 20,
        page: int = 1,
    ) -> list[GitLabBranch]:
        """List repository branches for a project.

        Args:
            project_id: Numeric project ID or ``namespace/project`` path.
            search: Optional search string to filter branch names.
            limit: Maximum branches per page (max 100).
            page: Page number (1-indexed).

        Returns:
            List of GitLabBranch objects.
        """
        encoded = _encode_project_id(project_id)
        params: dict[str, Any] = {"per_page": min(limit, 100), "page": page}
        if search:
            params["search"] = search

        resp = await self._request(
            "GET",
            f"/projects/{encoded}/repository/branches",
            params=params,
        )
        return [parse_branch(b) for b in resp.json()]

    @action("Create a new branch", dangerous=True)
    async def create_branch(
        self,
        project_id: str,
        branch_name: str,
        ref: str,
    ) -> GitLabBranch:
        """Create a new branch in a project repository.

        Args:
            project_id: Numeric project ID or ``namespace/project`` path.
            branch_name: Name for the new branch.
            ref: The branch name or commit SHA to branch from.

        Returns:
            The created GitLabBranch object.
        """
        encoded = _encode_project_id(project_id)
        payload: dict[str, Any] = {"branch": branch_name, "ref": ref}
        resp = await self._request(
            "POST",
            f"/projects/{encoded}/repository/branches",
            json=payload,
        )
        return parse_branch(resp.json())

    # ------------------------------------------------------------------
    # Actions -- Tags
    # ------------------------------------------------------------------

    @action("List tags for a project")
    async def list_tags(
        self,
        project_id: str,
        search: Optional[str] = None,
        limit: int = 20,
        page: int = 1,
    ) -> list[GitLabTag]:
        """List repository tags for a project.

        Args:
            project_id: Numeric project ID or ``namespace/project`` path.
            search: Optional search string to filter tag names.
            limit: Maximum tags per page (max 100).
            page: Page number (1-indexed).

        Returns:
            List of GitLabTag objects.
        """
        encoded = _encode_project_id(project_id)
        params: dict[str, Any] = {"per_page": min(limit, 100), "page": page}
        if search:
            params["search"] = search

        resp = await self._request(
            "GET",
            f"/projects/{encoded}/repository/tags",
            params=params,
        )
        return [parse_tag(t) for t in resp.json()]

    # ------------------------------------------------------------------
    # Actions -- Branch management
    # ------------------------------------------------------------------

    @action("Delete a branch from a project", dangerous=True)
    async def delete_branch(
        self,
        project_id: str,
        branch_name: str,
    ) -> bool:
        """Delete a branch from a project repository.

        Args:
            project_id: Numeric project ID or ``namespace/project`` path.
            branch_name: Name of the branch to delete.

        Returns:
            True if the branch was deleted successfully.
        """
        encoded = _encode_project_id(project_id)
        branch_encoded = quote(branch_name, safe="")
        await self._request(
            "DELETE",
            f"/projects/{encoded}/repository/branches/{branch_encoded}",
        )
        return True

    # ------------------------------------------------------------------
    # Actions -- Project Members
    # ------------------------------------------------------------------

    @action("List project members")
    async def list_project_members(
        self,
        project_id: str,
        query: Optional[str] = None,
        limit: int = 20,
        page: int = 1,
    ) -> PaginatedList[GitLabMember]:
        """List direct members of a project.

        Args:
            project_id: Numeric project ID or ``namespace/project`` path.
            query: Optional search query to filter members by name/username.
            limit: Maximum members per page (max 100).
            page: Page number (1-indexed).

        Returns:
            Paginated list of GitLabMember objects.
        """
        encoded = _encode_project_id(project_id)
        params: dict[str, Any] = {"per_page": min(limit, 100), "page": page}
        if query:
            params["query"] = query

        resp = await self._request(
            "GET", f"/projects/{encoded}/members", params=params,
        )
        items = [parse_member(m) for m in resp.json()]
        ps = self._build_page_state(resp, page)

        result = PaginatedList(
            items=items, page_state=ps, total_count=ps.total_count,
        )
        if ps.has_more and ps.page_number is not None:
            np = ps.page_number
            result._fetch_next = lambda pg=np: self.list_project_members(
                project_id=project_id, query=query, limit=limit, page=pg,
            )
        return result

    # ------------------------------------------------------------------
    # Actions -- Labels
    # ------------------------------------------------------------------

    @action("List labels for a project")
    async def list_labels(
        self,
        project_id: str,
        search: Optional[str] = None,
        limit: int = 20,
        page: int = 1,
    ) -> list[GitLabLabel]:
        """List labels defined on a project.

        Args:
            project_id: Numeric project ID or ``namespace/project`` path.
            search: Optional search string to filter labels by name.
            limit: Maximum labels per page (max 100).
            page: Page number (1-indexed).

        Returns:
            List of GitLabLabel objects.
        """
        encoded = _encode_project_id(project_id)
        params: dict[str, Any] = {"per_page": min(limit, 100), "page": page}
        if search:
            params["search"] = search

        resp = await self._request(
            "GET", f"/projects/{encoded}/labels", params=params,
        )
        return [parse_label(lb) for lb in resp.json()]

    @action("Create a label in a project", dangerous=True)
    async def create_label(
        self,
        project_id: str,
        name: str,
        color: str,
        description: Optional[str] = None,
    ) -> GitLabLabel:
        """Create a new label on a project.

        Args:
            project_id: Numeric project ID or ``namespace/project`` path.
            name: Label name.
            color: Label color in hex format (e.g. ``"#FF0000"``).
            description: Optional label description.

        Returns:
            The created GitLabLabel object.
        """
        encoded = _encode_project_id(project_id)
        payload: dict[str, Any] = {"name": name, "color": color}
        if description is not None:
            payload["description"] = description

        resp = await self._request(
            "POST", f"/projects/{encoded}/labels", json=payload,
        )
        return parse_label(resp.json())

    # ------------------------------------------------------------------
    # Actions -- Milestones
    # ------------------------------------------------------------------

    @action("List milestones for a project")
    async def list_milestones(
        self,
        project_id: str,
        state: Optional[str] = None,
        limit: int = 20,
        page: int = 1,
    ) -> list[GitLabMilestone]:
        """List milestones for a project.

        Args:
            project_id: Numeric project ID or ``namespace/project`` path.
            state: Filter by state: ``active`` or ``closed``.
            limit: Maximum milestones per page (max 100).
            page: Page number (1-indexed).

        Returns:
            List of GitLabMilestone objects.
        """
        encoded = _encode_project_id(project_id)
        params: dict[str, Any] = {"per_page": min(limit, 100), "page": page}
        if state:
            params["state"] = state

        resp = await self._request(
            "GET", f"/projects/{encoded}/milestones", params=params,
        )
        return [parse_milestone(m) for m in resp.json()]

    @action("Create a milestone in a project", dangerous=True)
    async def create_milestone(
        self,
        project_id: str,
        title: str,
        description: Optional[str] = None,
        due_date: Optional[str] = None,
        start_date: Optional[str] = None,
    ) -> GitLabMilestone:
        """Create a new milestone on a project.

        Args:
            project_id: Numeric project ID or ``namespace/project`` path.
            title: Milestone title.
            description: Optional milestone description.
            due_date: Due date in ``YYYY-MM-DD`` format.
            start_date: Start date in ``YYYY-MM-DD`` format.

        Returns:
            The created GitLabMilestone object.
        """
        encoded = _encode_project_id(project_id)
        payload: dict[str, Any] = {"title": title}
        if description is not None:
            payload["description"] = description
        if due_date is not None:
            payload["due_date"] = due_date
        if start_date is not None:
            payload["start_date"] = start_date

        resp = await self._request(
            "POST", f"/projects/{encoded}/milestones", json=payload,
        )
        return parse_milestone(resp.json())
