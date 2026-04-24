"""Asana connector -- tasks, projects, and workspaces via the Asana REST API v1."""

from __future__ import annotations

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
    AsanaComment,
    AsanaProject,
    AsanaSection,
    AsanaStory,
    AsanaTag,
    AsanaTask,
    AsanaTeam,
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
        raise_typed_for_status(response, connector=self.name)
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
        data = await self._request("GET", f"/projects/{project_gid}", params=params)
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
        data = await self._request("POST", f"/tasks/{task_gid}/stories", json=body)
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
            "GET",
            f"/tasks/{task_gid}/subtasks",
            params=params,
        )
        return [self._parse_task(t) for t in data.get("data", [])]

    @action("Create a subtask under a parent task", dangerous=True)
    async def create_subtask(
        self,
        task_gid: str,
        name: str,
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
            "POST",
            f"/tasks/{task_gid}/subtasks",
            json=body,
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
            "POST",
            f"/tasks/{task_gid}/addTag",
            json=body,
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

    # ------------------------------------------------------------------
    # Actions -- Sections
    # ------------------------------------------------------------------

    @action("List sections in a project")
    async def list_sections(
        self,
        project_gid: str,
    ) -> list[AsanaSection]:
        """List all sections in an Asana project.

        Args:
            project_gid: The project GID.

        Returns:
            List of AsanaSection objects.
        """
        params: dict[str, Any] = {
            "opt_fields": "name,created_at,project,project.name",
        }
        data = await self._request(
            "GET",
            f"/projects/{project_gid}/sections",
            params=params,
        )
        return [
            AsanaSection(
                gid=s.get("gid", ""),
                name=s.get("name", ""),
                resource_type=s.get("resource_type", "section"),
                created_at=s.get("created_at"),
                project=s.get("project"),
            )
            for s in data.get("data", [])
        ]

    @action("Create a section in a project", dangerous=True)
    async def create_section(
        self,
        project_gid: str,
        name: str,
    ) -> dict[str, Any]:
        """Create a new section in an Asana project.

        Args:
            project_gid: The project GID to add the section to.
            name: Name of the new section.

        Returns:
            Dict with the created section data including ``gid``
            and ``name``.
        """
        body: dict[str, Any] = {"data": {"name": name}}
        data = await self._request(
            "POST",
            f"/projects/{project_gid}/sections",
            json=body,
        )
        return data.get("data", {})

    @action("Add a task to a section", dangerous=True)
    async def add_task_to_section(
        self,
        section_gid: str,
        task_gid: str,
    ) -> None:
        """Move a task into a specific section within a project.

        Args:
            section_gid: The section GID to add the task to.
            task_gid: The task GID to move.
        """
        body: dict[str, Any] = {"data": {"task": task_gid}}
        await self._request(
            "POST",
            f"/sections/{section_gid}/addTask",
            json=body,
        )

    # ------------------------------------------------------------------
    # Actions -- Stories (activity / comments)
    # ------------------------------------------------------------------

    @action("List stories (activity) on a task")
    async def list_stories(
        self,
        task_gid: str,
    ) -> list[AsanaStory]:
        """List all stories (activity entries and comments) on a task.

        Args:
            task_gid: The task GID.

        Returns:
            List of AsanaStory objects.
        """
        params: dict[str, Any] = {
            "opt_fields": (
                "text,html_text,type,resource_subtype,created_at,"
                "created_by,created_by.name,created_by.email"
            ),
        }
        data = await self._request(
            "GET",
            f"/tasks/{task_gid}/stories",
            params=params,
        )
        return [
            AsanaStory(
                gid=s.get("gid", ""),
                resource_type=s.get("resource_type", "story"),
                text=s.get("text", ""),
                html_text=s.get("html_text"),
                type=s.get("type"),
                created_at=s.get("created_at"),
                created_by=self._parse_user(s.get("created_by")),
                resource_subtype=s.get("resource_subtype"),
            )
            for s in data.get("data", [])
        ]

    # ------------------------------------------------------------------
    # Actions -- Project management (extended)
    # ------------------------------------------------------------------

    @action("Update a project", dangerous=True)
    async def update_project(
        self,
        project_gid: str,
        name: Optional[str] = None,
        notes: Optional[str] = None,
        color: Optional[str] = None,
    ) -> AsanaProject:
        """Update fields on an existing Asana project.

        Args:
            project_gid: The project GID to update.
            name: New name for the project.
            notes: New description/notes for the project.
            color: New colour tag (e.g. ``"dark-green"``).

        Returns:
            The updated AsanaProject.
        """
        project_data: dict[str, Any] = {}
        if name is not None:
            project_data["name"] = name
        if notes is not None:
            project_data["notes"] = notes
        if color is not None:
            project_data["color"] = color

        body: dict[str, Any] = {"data": project_data}
        data = await self._request(
            "PUT",
            f"/projects/{project_gid}",
            json=body,
        )
        return self._parse_project(data.get("data", {}))

    @action("Create a new project", dangerous=True)
    async def create_project(
        self,
        workspace_gid: str,
        name: str,
        notes: Optional[str] = None,
    ) -> AsanaProject:
        """Create a new project in an Asana workspace.

        Args:
            workspace_gid: The workspace GID to create the project in.
            name: Name of the new project.
            notes: Optional description/notes for the project.

        Returns:
            The newly created AsanaProject.
        """
        project_data: dict[str, Any] = {
            "workspace": workspace_gid,
            "name": name,
        }
        if notes is not None:
            project_data["notes"] = notes

        body: dict[str, Any] = {"data": project_data}
        data = await self._request("POST", "/projects", json=body)
        return self._parse_project(data.get("data", {}))

    # ------------------------------------------------------------------
    # Actions -- Teams
    # ------------------------------------------------------------------

    @action("List teams in a workspace")
    async def list_teams(
        self,
        workspace_gid: str,
    ) -> list[AsanaTeam]:
        """List all teams in an Asana workspace/organization.

        Args:
            workspace_gid: The workspace or organization GID.

        Returns:
            List of AsanaTeam objects.
        """
        params: dict[str, Any] = {
            "opt_fields": "name,description,organization,organization.name",
        }
        data = await self._request(
            "GET",
            f"/organizations/{workspace_gid}/teams",
            params=params,
        )
        return [
            AsanaTeam(
                gid=t.get("gid", ""),
                name=t.get("name", ""),
                resource_type=t.get("resource_type", "team"),
                description=t.get("description"),
                organization=t.get("organization"),
            )
            for t in data.get("data", [])
        ]

    # ------------------------------------------------------------------
    # Actions -- Workspace details
    # ------------------------------------------------------------------

    @action("Get a workspace by GID")
    async def get_workspace(
        self,
        workspace_gid: str,
    ) -> AsanaWorkspace:
        """Retrieve a single Asana workspace by its GID.

        Args:
            workspace_gid: The workspace GID.

        Returns:
            The requested AsanaWorkspace.
        """
        params: dict[str, Any] = {
            "opt_fields": "name,is_organization",
        }
        data = await self._request(
            "GET",
            f"/workspaces/{workspace_gid}",
            params=params,
        )
        ws = data.get("data", {})
        return AsanaWorkspace(
            gid=ws.get("gid", ""),
            name=ws.get("name", ""),
            resource_type=ws.get("resource_type", "workspace"),
            is_organization=ws.get("is_organization"),
        )

    # ------------------------------------------------------------------
    # Actions — Users
    # ------------------------------------------------------------------

    @action("Get the current user")
    async def get_me(self) -> dict[str, Any]:
        """Get the authenticated user's profile.

        Returns:
            User dict with gid, name, email, workspaces.
        """
        data = await self._request("GET", "/users/me")
        return data.get("data", data)

    @action("List users in a workspace")
    async def list_users(
        self,
        workspace_gid: str,
        limit: int = 50,
        offset: Optional[str] = None,
    ) -> PaginatedList[dict[str, Any]]:
        """List users in a workspace.

        Args:
            workspace_gid: The workspace GID.
            limit: Maximum users to return.
            offset: Pagination offset token.

        Returns:
            Paginated list of user dicts.
        """
        params: dict[str, Any] = {"limit": limit}
        if offset:
            params["offset"] = offset
        data = await self._request(
            "GET",
            f"/workspaces/{workspace_gid}/users",
            params=params,
        )
        users = data.get("data", [])
        next_page = data.get("next_page")
        return PaginatedList(
            items=users,
            page_state=PageState(
                cursor=next_page.get("offset") if next_page else None,
                has_more=next_page is not None,
            ),
        )

    @action("Get a user by ID")
    async def get_user(self, user_gid: str) -> dict[str, Any]:
        """Get a user's profile by GID.

        Args:
            user_gid: The user GID.

        Returns:
            User dict with gid, name, email, workspaces.
        """
        data = await self._request("GET", f"/users/{user_gid}")
        return data.get("data", data)

    # ------------------------------------------------------------------
    # Actions — Search
    # ------------------------------------------------------------------

    @action("Search tasks in a workspace")
    async def search_tasks(
        self,
        workspace_gid: str,
        text: Optional[str] = None,
        assignee: Optional[str] = None,
        completed: Optional[bool] = None,
        is_subtask: Optional[bool] = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search tasks in a workspace using various filters.

        Args:
            workspace_gid: The workspace GID to search in.
            text: Text to search in task names and descriptions.
            assignee: Filter by assignee GID or 'me'.
            completed: Filter by completion status.
            is_subtask: Filter subtasks vs top-level tasks.
            limit: Maximum results to return.

        Returns:
            List of matching task dicts.
        """
        params: dict[str, Any] = {"limit": limit}
        if text:
            params["text"] = text
        if assignee:
            params["assignee.any"] = assignee
        if completed is not None:
            params["completed"] = str(completed).lower()
        if is_subtask is not None:
            params["is_subtask"] = str(is_subtask).lower()
        data = await self._request(
            "GET",
            f"/workspaces/{workspace_gid}/tasks/search",
            params=params,
        )
        return data.get("data", [])

    # ------------------------------------------------------------------
    # Actions — Task operations
    # ------------------------------------------------------------------

    @action("Duplicate a task", dangerous=True)
    async def duplicate_task(
        self,
        task_gid: str,
        name: Optional[str] = None,
        include: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Duplicate a task.

        Args:
            task_gid: The task GID to duplicate.
            name: Name for the new task. Defaults to 'Copy of {original}'.
            include: What to include: 'notes', 'assignee', 'subtasks',
                'attachments', 'tags', 'followers', 'projects', 'dates',
                'dependencies', 'parent'.

        Returns:
            The new job dict (duplication runs async).
        """
        payload: dict[str, Any] = {}
        if name:
            payload["name"] = name
        if include:
            payload["include"] = ",".join(include)
        data = await self._request(
            "POST",
            f"/tasks/{task_gid}/duplicate",
            json={"data": payload},
        )
        return data.get("data", data)

    @action("Set parent for a task", dangerous=True)
    async def set_parent(
        self,
        task_gid: str,
        parent: str,
    ) -> dict[str, Any]:
        """Move a task under a new parent (make it a subtask).

        Args:
            task_gid: The task GID to move.
            parent: Parent task GID, or empty string to make top-level.

        Returns:
            Updated task dict.
        """
        data = await self._request(
            "POST",
            f"/tasks/{task_gid}/setParent",
            json={"data": {"parent": parent or None}},
        )
        return data.get("data", data)

    @action("Add followers to a task", dangerous=True)
    async def add_followers(
        self,
        task_gid: str,
        followers: list[str],
    ) -> dict[str, Any]:
        """Add followers (watchers) to a task.

        Args:
            task_gid: The task GID.
            followers: List of user GIDs to add as followers.

        Returns:
            Updated task dict.
        """
        data = await self._request(
            "POST",
            f"/tasks/{task_gid}/addFollowers",
            json={"data": {"followers": followers}},
        )
        return data.get("data", data)

    @action("Add task dependencies", dangerous=True)
    async def add_dependencies(
        self,
        task_gid: str,
        dependencies: list[str],
    ) -> dict[str, Any]:
        """Add dependencies to a task (tasks that must complete first).

        Args:
            task_gid: The task GID.
            dependencies: List of dependency task GIDs.

        Returns:
            Empty dict on success.
        """
        data = await self._request(
            "POST",
            f"/tasks/{task_gid}/addDependencies",
            json={"data": {"dependencies": dependencies}},
        )
        return data.get("data", {})

    # ------------------------------------------------------------------
    # Actions — Project operations
    # ------------------------------------------------------------------

    @action("Delete a project", dangerous=True)
    async def delete_project(self, project_gid: str) -> None:
        """Permanently delete a project.

        Args:
            project_gid: The project GID to delete.
        """
        await self._request("DELETE", f"/projects/{project_gid}")

    @action("Get task count for a project")
    async def get_task_count(self, project_gid: str) -> dict[str, int]:
        """Get the number of tasks in a project.

        Args:
            project_gid: The project GID.

        Returns:
            Dict with num_tasks, num_incomplete_tasks, num_completed_tasks.
        """
        data = await self._request(
            "GET",
            f"/projects/{project_gid}/task_counts",
        )
        return data.get("data", data)

    # ------------------------------------------------------------------
    # Actions — Tags
    # ------------------------------------------------------------------

    @action("Create a tag", dangerous=True)
    async def create_tag(
        self,
        workspace_gid: str,
        name: str,
        color: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create a new tag in a workspace.

        Args:
            workspace_gid: The workspace GID.
            name: Tag name.
            color: Tag color (e.g., 'dark-pink', 'dark-green').

        Returns:
            Created tag dict.
        """
        payload: dict[str, Any] = {"workspace": workspace_gid, "name": name}
        if color:
            payload["color"] = color
        data = await self._request("POST", "/tags", json={"data": payload})
        return data.get("data", data)

    @action("Delete a tag", dangerous=True)
    async def delete_tag(self, tag_gid: str) -> None:
        """Delete a tag.

        Args:
            tag_gid: The tag GID to delete.
        """
        await self._request("DELETE", f"/tags/{tag_gid}")

    # ------------------------------------------------------------------
    # Actions — Attachments
    # ------------------------------------------------------------------

    @action("List attachments on a task")
    async def list_attachments(self, task_gid: str) -> list[dict[str, Any]]:
        """List all attachments on a task.

        Args:
            task_gid: The task GID.

        Returns:
            List of attachment dicts with gid, name, resource_type.
        """
        data = await self._request(
            "GET",
            "/attachments",
            params={"parent": task_gid},
        )
        return data.get("data", [])

    # ------------------------------------------------------------------
    # Actions — Webhooks
    # ------------------------------------------------------------------

    @action("List webhooks")
    async def list_webhooks(
        self,
        workspace_gid: str,
    ) -> list[dict[str, Any]]:
        """List all webhooks in a workspace.

        Args:
            workspace_gid: The workspace GID.

        Returns:
            List of webhook dicts.
        """
        data = await self._request(
            "GET",
            "/webhooks",
            params={"workspace": workspace_gid},
        )
        return data.get("data", [])

    @action("Create a webhook", dangerous=True)
    async def create_webhook(
        self,
        resource: str,
        target: str,
    ) -> dict[str, Any]:
        """Create a webhook to receive notifications about changes.

        Args:
            resource: The GID of the resource to watch (task, project, etc.).
            target: The URL to receive webhook notifications.

        Returns:
            Created webhook dict.
        """
        data = await self._request(
            "POST",
            "/webhooks",
            json={"data": {"resource": resource, "target": target}},
        )
        return data.get("data", data)

    @action("Delete a webhook", dangerous=True)
    async def delete_webhook(self, webhook_gid: str) -> None:
        """Delete a webhook.

        Args:
            webhook_gid: The webhook GID to delete.
        """
        await self._request("DELETE", f"/webhooks/{webhook_gid}")

    # ------------------------------------------------------------------
    # Actions — Custom Fields
    # ------------------------------------------------------------------

    @action("List custom fields in a workspace")
    async def list_custom_fields(
        self,
        workspace_gid: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List custom fields available in a workspace.

        Args:
            workspace_gid: The workspace GID.
            limit: Maximum fields to return.

        Returns:
            List of custom field dicts.
        """
        data = await self._request(
            "GET",
            f"/workspaces/{workspace_gid}/custom_fields",
            params={"limit": limit},
        )
        return data.get("data", [])
