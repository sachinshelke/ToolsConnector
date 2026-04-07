"""Google Tasks connector -- manage task lists and tasks via the Tasks API v1.

Uses httpx for direct HTTP calls against the Google Tasks REST API.
Expects an OAuth 2.0 access token passed as ``credentials``.
"""

from __future__ import annotations

from typing import Any, Optional

import httpx

from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import ConnectorCategory, ProtocolType, RateLimitSpec
from toolsconnector.types import PageState, PaginatedList

from .types import GoogleTask, TaskList


def _parse_task_list(data: dict[str, Any]) -> TaskList:
    """Parse a Tasks API tasklist resource into a TaskList model.

    Args:
        data: Raw JSON dict from the Tasks API.

    Returns:
        Parsed TaskList instance.
    """
    return TaskList(
        id=data.get("id", ""),
        title=data.get("title", ""),
        updated=data.get("updated"),
    )


def _parse_task(data: dict[str, Any]) -> GoogleTask:
    """Parse a Tasks API task resource into a GoogleTask model.

    Args:
        data: Raw JSON dict from the Tasks API.

    Returns:
        Parsed GoogleTask instance.
    """
    return GoogleTask(
        id=data.get("id", ""),
        title=data.get("title", ""),
        notes=data.get("notes"),
        status=data.get("status", "needsAction"),
        due=data.get("due"),
        completed=data.get("completed"),
        parent=data.get("parent"),
        position=data.get("position"),
        links=data.get("links", []),
    )


class GoogleTasks(BaseConnector):
    """Connect to Google Tasks to manage task lists and tasks.

    Supports OAuth 2.0 authentication. Pass an access token as
    ``credentials`` when instantiating. Uses the Tasks REST API v1
    via direct httpx calls.
    """

    name = "gtasks"
    display_name = "Google Tasks"
    category = ConnectorCategory.PRODUCTIVITY
    protocol = ProtocolType.REST
    base_url = "https://tasks.googleapis.com/tasks/v1"
    description = "Connect to Google Tasks to manage task lists and tasks."
    _rate_limit_config = RateLimitSpec(rate=300, period=60, burst=60)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_headers(self) -> dict[str, str]:
        """Build authorization headers for Tasks API requests.

        Returns:
            Dict with Authorization bearer header.
        """
        return {"Authorization": f"Bearer {self._credentials}"}

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """Execute an authenticated HTTP request against the Tasks API.

        Args:
            method: HTTP method (GET, POST, PUT, PATCH, DELETE).
            path: API path relative to base_url.
            **kwargs: Additional keyword arguments passed to httpx.

        Returns:
            Parsed JSON response as a dict.

        Raises:
            httpx.HTTPStatusError: If the API returns a non-2xx status.
        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.request(
                method,
                f"{self._base_url}{path}",
                headers=self._get_headers(),
                **kwargs,
            )
            response.raise_for_status()
            if response.status_code == 204 or not response.content:
                return {}
            return response.json()

    # ------------------------------------------------------------------
    # Actions — Task Lists
    # ------------------------------------------------------------------

    @action("List all task lists", requires_scope="read")
    async def list_task_lists(
        self,
        limit: Optional[int] = None,
        page_token: Optional[str] = None,
    ) -> PaginatedList[TaskList]:
        """List all task lists for the authenticated user.

        Args:
            limit: Maximum number of task lists to return (max 100).
            page_token: Token for fetching the next page of results.

        Returns:
            Paginated list of TaskList objects.
        """
        params: dict[str, Any] = {}
        if limit is not None:
            params["maxResults"] = min(limit, 100)
        if page_token:
            params["pageToken"] = page_token

        data = await self._request(
            "GET",
            "/users/@me/lists",
            params=params,
        )

        items = [_parse_task_list(tl) for tl in data.get("items", [])]
        next_token = data.get("nextPageToken")

        return PaginatedList(
            items=items,
            page_state=PageState(
                cursor=next_token,
                has_more=next_token is not None,
            ),
        )

    @action("Get a task list by ID", requires_scope="read")
    async def get_task_list(self, task_list_id: str) -> TaskList:
        """Retrieve a specific task list by its ID.

        Args:
            task_list_id: The ID of the task list.

        Returns:
            The requested TaskList object.
        """
        data = await self._request(
            "GET",
            f"/users/@me/lists/{task_list_id}",
        )
        return _parse_task_list(data)

    @action("Create a new task list", requires_scope="write", dangerous=True)
    async def create_task_list(self, title: str) -> TaskList:
        """Create a new task list.

        Args:
            title: Title for the new task list.

        Returns:
            The created TaskList object.
        """
        body: dict[str, Any] = {"title": title}
        data = await self._request(
            "POST",
            "/users/@me/lists",
            json=body,
        )
        return _parse_task_list(data)

    @action("Delete a task list", requires_scope="write", dangerous=True)
    async def delete_task_list(self, task_list_id: str) -> None:
        """Delete a task list and all its tasks.

        Args:
            task_list_id: The ID of the task list to delete.

        Warning:
            This permanently deletes the task list and all tasks within it.
        """
        await self._request(
            "DELETE",
            f"/users/@me/lists/{task_list_id}",
        )

    # ------------------------------------------------------------------
    # Actions — Tasks
    # ------------------------------------------------------------------

    @action("List tasks in a task list", requires_scope="read")
    async def list_tasks(
        self,
        task_list_id: str,
        completed: Optional[bool] = None,
        due_min: Optional[str] = None,
        due_max: Optional[str] = None,
        show_hidden: Optional[bool] = None,
        page_token: Optional[str] = None,
    ) -> PaginatedList[GoogleTask]:
        """List tasks in a specific task list.

        Args:
            task_list_id: The ID of the task list.
            completed: If True, include only completed tasks. If False,
                include only incomplete tasks. If None, include all.
            due_min: Lower bound for task due date (RFC 3339 timestamp).
            due_max: Upper bound for task due date (RFC 3339 timestamp).
            show_hidden: Whether to show hidden and deleted tasks.
            page_token: Token for fetching the next page.

        Returns:
            Paginated list of GoogleTask objects.
        """
        params: dict[str, Any] = {}
        if completed is not None:
            # completedMin/completedMax or showCompleted
            params["showCompleted"] = str(completed).lower()
        if due_min:
            params["dueMin"] = due_min
        if due_max:
            params["dueMax"] = due_max
        if show_hidden is not None:
            params["showHidden"] = str(show_hidden).lower()
        if page_token:
            params["pageToken"] = page_token

        data = await self._request(
            "GET",
            f"/lists/{task_list_id}/tasks",
            params=params,
        )

        items = [_parse_task(t) for t in data.get("items", [])]
        next_token = data.get("nextPageToken")

        return PaginatedList(
            items=items,
            page_state=PageState(
                cursor=next_token,
                has_more=next_token is not None,
            ),
        )

    @action("Get a task by ID", requires_scope="read")
    async def get_task(self, task_list_id: str, task_id: str) -> GoogleTask:
        """Retrieve a specific task by its ID.

        Args:
            task_list_id: The ID of the task list containing the task.
            task_id: The ID of the task.

        Returns:
            The requested GoogleTask object.
        """
        data = await self._request(
            "GET",
            f"/lists/{task_list_id}/tasks/{task_id}",
        )
        return _parse_task(data)

    @action("Create a new task", requires_scope="write", dangerous=True)
    async def create_task(
        self,
        task_list_id: str,
        title: str,
        notes: Optional[str] = None,
        due: Optional[str] = None,
    ) -> GoogleTask:
        """Create a new task in a task list.

        Args:
            task_list_id: The ID of the task list to add the task to.
            title: Title for the new task.
            notes: Optional notes/description for the task.
            due: Optional due date as RFC 3339 timestamp.

        Returns:
            The created GoogleTask object.
        """
        body: dict[str, Any] = {"title": title}
        if notes is not None:
            body["notes"] = notes
        if due is not None:
            body["due"] = due

        data = await self._request(
            "POST",
            f"/lists/{task_list_id}/tasks",
            json=body,
        )
        return _parse_task(data)

    @action("Update a task", requires_scope="write", dangerous=True)
    async def update_task(
        self,
        task_list_id: str,
        task_id: str,
        title: Optional[str] = None,
        notes: Optional[str] = None,
        status: Optional[str] = None,
        due: Optional[str] = None,
    ) -> GoogleTask:
        """Update an existing task.

        Only provided fields will be updated. Uses PATCH semantics.

        Args:
            task_list_id: The ID of the task list containing the task.
            task_id: The ID of the task to update.
            title: New title for the task.
            notes: New notes/description for the task.
            status: New status (``'needsAction'`` or ``'completed'``).
            due: New due date as RFC 3339 timestamp.

        Returns:
            The updated GoogleTask object.
        """
        body: dict[str, Any] = {}
        if title is not None:
            body["title"] = title
        if notes is not None:
            body["notes"] = notes
        if status is not None:
            body["status"] = status
        if due is not None:
            body["due"] = due

        data = await self._request(
            "PATCH",
            f"/lists/{task_list_id}/tasks/{task_id}",
            json=body,
        )
        return _parse_task(data)

    @action("Delete a task", requires_scope="write", dangerous=True)
    async def delete_task(self, task_list_id: str, task_id: str) -> None:
        """Delete a task from a task list.

        Args:
            task_list_id: The ID of the task list containing the task.
            task_id: The ID of the task to delete.

        Warning:
            This permanently deletes the task.
        """
        await self._request(
            "DELETE",
            f"/lists/{task_list_id}/tasks/{task_id}",
        )

    @action("Complete a task", requires_scope="write", dangerous=True)
    async def complete_task(self, task_list_id: str, task_id: str) -> GoogleTask:
        """Mark a task as completed.

        Convenience method that patches the task status to ``'completed'``.

        Args:
            task_list_id: The ID of the task list containing the task.
            task_id: The ID of the task to complete.

        Returns:
            The updated GoogleTask object with ``status='completed'``.
        """
        data = await self._request(
            "PATCH",
            f"/lists/{task_list_id}/tasks/{task_id}",
            json={"status": "completed"},
        )
        return _parse_task(data)

    @action("Move a task", requires_scope="write")
    async def move_task(
        self,
        task_list_id: str,
        task_id: str,
        parent: Optional[str] = None,
        previous: Optional[str] = None,
    ) -> GoogleTask:
        """Move a task to a new position within a task list.

        Can be used to re-parent a task (make it a subtask) or reorder
        it relative to other tasks.

        Args:
            task_list_id: The ID of the task list.
            task_id: The ID of the task to move.
            parent: Optional parent task ID to nest under (makes it a
                subtask). Pass ``None`` to move to the top level.
            previous: Optional ID of the task to position after. If
                omitted, the task is moved to the first position.

        Returns:
            The moved GoogleTask object with updated position.
        """
        params: dict[str, Any] = {}
        if parent is not None:
            params["parent"] = parent
        if previous is not None:
            params["previous"] = previous

        data = await self._request(
            "POST",
            f"/lists/{task_list_id}/tasks/{task_id}/move",
            params=params,
        )
        return _parse_task(data)
