"""Asana connector -- tasks, projects, and workspaces via the Asana REST API v1."""

from __future__ import annotations

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
    AsanaComment,
    AsanaProject,
    AsanaTag,
    AsanaTask,
    AsanaUser,
    AsanaWorkspace,
)


class Asana(BaseConnector):
    """Connect to Asana to manage tasks, projects, and workspaces.

    Requires a Personal Access Token (PAT) passed as ``credentials``.
    Uses the Asana REST API v1 with ``{"data": ...}`` response envelopes
    and offset-based pagination via ``next_page.offset``.
    """

    name = "asana"
    display_name = "Asana"
    category = ConnectorCategory.PROJECT_MANAGEMENT
    protocol = ProtocolType.REST
    base_url = "https://app.asana.com/api/1.0"
    description = (
        "Connect to Asana to manage tasks, projects, workspaces, "
        "and comments via the Asana REST API."
    )
    _rate_limit_config = RateLimitSpec(rate=1500, period=60, burst=150)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Initialise the async HTTP client."""
        self._client = httpx.AsyncClient(
            base_url=self._base_url or self.__class__.base_url,
            headers={
                "Authorization": f"Bearer {self._credentials}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=self._timeout,
        )

    async def _teardown(self) -> None:
        """Close the HTTP client."""
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
        json: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Execute an HTTP request against the Asana REST API.

        Args:
            method: HTTP method.
            path: API path relative to ``base_url``.
            json: JSON request body (wrapped in ``{"data": ...}`` by caller).
            params: Query parameters.

        Returns:
            Parsed JSON response dict.

        Raises:
            httpx.HTTPStatusError: On non-2xx responses.
        """
        response = await self._client.request(
            method,
            path,
            json=json,
            params=params,
        )
        response.raise_for_status()
        if response.status_code == 204:
            return {}
        return response.json()

    # ------------------------------------------------------------------
    # Response parsers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_user(data: Optional[dict[str, Any]]) -> Optional[AsanaUser]:
        """Parse an Asana user JSON fragment."""
        if not data:
            return None
        return AsanaUser(
            gid=data.get("gid", ""),
            name=data.get("name"),
            email=data.get("email"),
            resource_type=data.get("resource_type", "user"),
        )

    @staticmethod
    def _parse_workspace(data: Optional[dict[str, Any]]) -> Optional[AsanaWorkspace]:
        """Parse an Asana workspace JSON fragment."""
        if not data:
            return None
        return AsanaWorkspace(
            gid=data.get("gid", ""),
            name=data.get("name", ""),
            resource_type=data.get("resource_type", "workspace"),
            is_organization=data.get("is_organization"),
        )

    @classmethod
    def _parse_project(cls, data: dict[str, Any]) -> AsanaProject:
        """Parse a raw Asana project JSON into an AsanaProject model."""
        return AsanaProject(
            gid=data.get("gid", ""),
            name=data.get("name", ""),
            resource_type=data.get("resource_type", "project"),
            archived=data.get("archived"),
            color=data.get("color"),
            created_at=data.get("created_at"),
            modified_at=data.get("modified_at"),
            notes=data.get("notes"),
            owner=cls._parse_user(data.get("owner")),
            workspace=cls._parse_workspace(data.get("workspace")),
            current_status=data.get("current_status"),
            due_on=data.get("due_on"),
            start_on=data.get("start_on"),
            public=data.get("public"),
        )

    @classmethod
    def _parse_task(cls, data: dict[str, Any]) -> AsanaTask:
        """Parse a raw Asana task JSON into an AsanaTask model."""
        return AsanaTask(
            gid=data.get("gid", ""),
            name=data.get("name", ""),
            resource_type=data.get("resource_type", "task"),
            assignee=cls._parse_user(data.get("assignee")),
            completed=data.get("completed", False),
            completed_at=data.get("completed_at"),
            created_at=data.get("created_at"),
            modified_at=data.get("modified_at"),
            due_on=data.get("due_on"),
            due_at=data.get("due_at"),
            notes=data.get("notes"),
            html_notes=data.get("html_notes"),
            start_on=data.get("start_on"),
            tags=data.get("tags", []),
            projects=data.get("projects", []),
            parent=data.get("parent"),
            permalink_url=data.get("permalink_url"),
            num_subtasks=data.get("num_subtasks"),
        )

    @classmethod
    def _parse_comment(cls, data: dict[str, Any]) -> AsanaComment:
        """Parse an Asana story/comment JSON into an AsanaComment model."""
        return AsanaComment(
            gid=data.get("gid", ""),
            resource_type=data.get("resource_type", "story"),
            text=data.get("text", ""),
            html_text=data.get("html_text"),
            created_at=data.get("created_at"),
            created_by=cls._parse_user(data.get("created_by")),
            type=data.get("type"),
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    @action("List tasks in a project")
    async def list_tasks(
        self,
        project_gid: str,
        limit: int = 50,
        offset: Optional[str] = None,
    ) -> PaginatedList[AsanaTask]:
        """List tasks belonging to a specific Asana project.

        Args:
            project_gid: The globally unique identifier for the project.
            limit: Maximum results per page (max 100).
            offset: Pagination offset token from a previous response.

        Returns:
            Paginated list of AsanaTask objects.
        """
        params: dict[str, Any] = {
            "project": project_gid,
            "limit": min(limit, 100),
            "opt_fields": (
                "name,completed,completed_at,created_at,modified_at,"
                "due_on,due_at,notes,assignee,assignee.name,assignee.email,"
                "tags,tags.name,projects,projects.name,parent,parent.name,"
                "permalink_url,num_subtasks,start_on"
            ),
        }
        if offset:
            params["offset"] = offset

        data = await self._request("GET", "/tasks", params=params)

        tasks = [self._parse_task(t) for t in data.get("data", [])]
        next_page = data.get("next_page")
        next_offset = next_page.get("offset") if next_page else None

        return PaginatedList(
            items=tasks,
            page_state=PageState(
                cursor=next_offset,
                has_more=next_offset is not None,
            ),
        )

    @action("Get a single task by GID")
    async def get_task(self, task_gid: str) -> AsanaTask:
        """Retrieve a single Asana task by its GID.

        Args:
            task_gid: The globally unique identifier for the task.

        Returns:
            The requested AsanaTask.
        """
        params: dict[str, Any] = {
            "opt_fields": (
                "name,completed,completed_at,created_at,modified_at,"
                "due_on,due_at,notes,html_notes,assignee,assignee.name,"
                "assignee.email,tags,tags.name,projects,projects.name,"
                "parent,parent.name,permalink_url,num_subtasks,start_on"
            ),
        }
        data = await self._request("GET", f"/tasks/{task_gid}", params=params)
        return self._parse_task(data.get("data", {}))

    @action("Create a new task", dangerous=True)
    async def create_task(
        self,
        project_gid: str,
        name: str,
        notes: Optional[str] = None,
        assignee: Optional[str] = None,
        due_on: Optional[str] = None,
    ) -> AsanaTask:
        """Create a new task in an Asana project.

        Args:
            project_gid: The project GID to add the task to.
            name: Name/title of the task.
            notes: Plain-text description of the task.
            assignee: GID of the user to assign (or ``"me"``).
            due_on: Due date in ``YYYY-MM-DD`` format.

        Returns:
            The newly created AsanaTask.
        """
        task_data: dict[str, Any] = {
            "name": name,
            "projects": [project_gid],
        }
        if notes is not None:
            task_data["notes"] = notes
        if assignee is not None:
            task_data["assignee"] = assignee
        if due_on is not None:
            task_data["due_on"] = due_on

        body: dict[str, Any] = {"data": task_data}
        data = await self._request("POST", "/tasks", json=body)
        return self._parse_task(data.get("data", {}))

    @action("Update an existing task")
    async def update_task(
        self,
        task_gid: str,
        name: Optional[str] = None,
        notes: Optional[str] = None,
        completed: Optional[bool] = None,
        due_on: Optional[str] = None,
    ) -> AsanaTask:
        """Update fields on an existing Asana task.

        Args:
            task_gid: The task GID to update.
            name: New name/title for the task.
            notes: New plain-text description.
            completed: Whether the task is completed.
            due_on: New due date in ``YYYY-MM-DD`` format.

        Returns:
            The updated AsanaTask.
        """
        task_data: dict[str, Any] = {}
        if name is not None:
            task_data["name"] = name
        if notes is not None:
            task_data["notes"] = notes
        if completed is not None:
            task_data["completed"] = completed
        if due_on is not None:
            task_data["due_on"] = due_on

        body: dict[str, Any] = {"data": task_data}
        data = await self._request("PUT", f"/tasks/{task_gid}", json=body)
        return self._parse_task(data.get("data", {}))

    @action("List projects in a workspace")
    async def list_projects(
        self,
        workspace_gid: str,
        limit: int = 50,
        offset: Optional[str] = None,
    ) -> PaginatedList[AsanaProject]:
        """List projects in an Asana workspace.

        Args:
            workspace_gid: The workspace GID to list projects from.
            limit: Maximum results per page (max 100).
            offset: Pagination offset token from a previous response.

        Returns:
            Paginated list of AsanaProject objects.
        """
        params: dict[str, Any] = {
            "workspace": workspace_gid,
            "limit": min(limit, 100),
            "opt_fields": (
                "name,archived,color,created_at,modified_at,notes,"
                "owner,owner.name,owner.email,workspace,workspace.name,"
                "due_on,start_on,public,current_status"
            ),
        }
        if offset:
            params["offset"] = offset

        data = await self._request("GET", "/projects", params=params)

        projects = [self._parse_project(p) for p in data.get("data", [])]
        next_page = data.get("next_page")
        next_offset = next_page.get("offset") if next_page else None

        return PaginatedList(
            items=projects,
            page_state=PageState(
                cursor=next_offset,
                has_more=next_offset is not None,
            ),
        )

    @action("Get a single project by GID")
    async def get_project(self, project_gid: str) -> AsanaProject:
        """Retrieve a single Asana project by its GID.

        Args:
            project_gid: The globally unique identifier for the project.

        Returns:
            The requested AsanaProject.
        """
        params: dict[str, Any] = {
            "opt_fields": (
                "name,archived,color,created_at,modified_at,notes,"
                "owner,owner.name,owner.email,workspace,workspace.name,"
                "due_on,start_on,public,current_status"
            ),
        }
        data = await self._request(
            "GET", f"/projects/{project_gid}", params=params
        )
        return self._parse_project(data.get("data", {}))

    @action("Add a comment to a task", dangerous=True)
    async def add_comment(
        self,
        task_gid: str,
        text: str,
    ) -> AsanaComment:
        """Add a comment (story) to an Asana task.

        Args:
            task_gid: The task GID to comment on.
            text: The plain-text comment body.

        Returns:
            The created AsanaComment.
        """
        body: dict[str, Any] = {"data": {"text": text}}
        data = await self._request(
            "POST", f"/tasks/{task_gid}/stories", json=body
        )
        return self._parse_comment(data.get("data", {}))

    @action("List workspaces accessible to the user")
    async def list_workspaces(self) -> list[AsanaWorkspace]:
        """List all workspaces visible to the authenticated user.

        Returns:
            List of AsanaWorkspace objects.
        """
        data = await self._request("GET", "/workspaces")
        return [
            AsanaWorkspace(
                gid=w.get("gid", ""),
                name=w.get("name", ""),
                resource_type=w.get("resource_type", "workspace"),
                is_organization=w.get("is_organization"),
            )
            for w in data.get("data", [])
        ]

    # ------------------------------------------------------------------
    # Actions — Task management (extended)
    # ------------------------------------------------------------------

    @action("Delete a task by GID", dangerous=True)
    async def delete_task(self, task_gid: str) -> bool:
        """Permanently delete an Asana task.

        Args:
            task_gid: The globally unique identifier for the task.

        Returns:
            True if the task was deleted successfully.
        """
        await self._request("DELETE", f"/tasks/{task_gid}")
        return True

    @action("List subtasks of a task")
    async def list_subtasks(self, task_gid: str) -> list[AsanaTask]:
        """List all subtasks of an Asana task.

        Args:
            task_gid: The parent task GID.

        Returns:
            List of AsanaTask objects representing the subtasks.
        """
        params: dict[str, Any] = {
            "opt_fields": (
                "name,completed,completed_at,created_at,modified_at,"
                "due_on,due_at,notes,assignee,assignee.name,assignee.email,"
                "tags,tags.name,permalink_url,num_subtasks,start_on"
            ),
        }
        data = await self._request(
            "GET", f"/tasks/{task_gid}/subtasks", params=params,
        )
        return [self._parse_task(t) for t in data.get("data", [])]

    @action("Create a subtask under a parent task", dangerous=True)
    async def create_subtask(
        self, task_gid: str, name: str,
    ) -> AsanaTask:
        """Create a subtask under a parent task.

        Args:
            task_gid: The parent task GID.
            name: Name/title of the subtask.

        Returns:
            The newly created AsanaTask subtask.
        """
        body: dict[str, Any] = {"data": {"name": name}}
        data = await self._request(
            "POST", f"/tasks/{task_gid}/subtasks", json=body,
        )
        return self._parse_task(data.get("data", {}))

    # ------------------------------------------------------------------
    # Actions — Tags
    # ------------------------------------------------------------------

    @action("Add a tag to a task")
    async def add_tag(self, task_gid: str, tag_gid: str) -> bool:
        """Add a tag to a task.

        Args:
            task_gid: The task GID to tag.
            tag_gid: The tag GID to add.

        Returns:
            True if the tag was added successfully.
        """
        body: dict[str, Any] = {"data": {"tag": tag_gid}}
        await self._request(
            "POST", f"/tasks/{task_gid}/addTag", json=body,
        )
        return True

    @action("List tags in a workspace")
    async def list_tags(self, workspace_gid: str) -> list[AsanaTag]:
        """List all tags in a workspace.

        Args:
            workspace_gid: The workspace GID.

        Returns:
            List of AsanaTag objects.
        """
        params: dict[str, Any] = {
            "workspace": workspace_gid,
            "opt_fields": "name,color,created_at",
        }
        data = await self._request("GET", "/tags", params=params)
        return [
            AsanaTag(
                gid=t.get("gid", ""),
                name=t.get("name", ""),
                resource_type=t.get("resource_type", "tag"),
                color=t.get("color"),
                created_at=t.get("created_at"),
            )
            for t in data.get("data", [])
        ]
