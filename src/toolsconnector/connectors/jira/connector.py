"""Jira connector -- issues, projects, and workflows via the Jira REST API v3."""

from __future__ import annotations

import base64
from typing import Any, Optional

import httpx

from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import (
    ConnectorCategory,
    ProtocolType,
    RateLimitSpec,
)
from toolsconnector.types import PageState, PaginatedList

from ._helpers import (
    parse_comment,
    parse_issue,
    parse_issue_type,
    parse_priority,
    parse_project,
    parse_resolution,
    parse_status,
    parse_user,
    parse_worklog,
)
from .types import (
    JiraAttachment,
    JiraBoard,
    JiraComment,
    JiraIssue,
    JiraIssueType,
    JiraPriority,
    JiraProject,
    JiraResolution,
    JiraSprint,
    JiraTransition,
    JiraUser,
    JiraWorklog,
)


class Jira(BaseConnector):
    """Connect to Jira to manage issues, projects, and workflows.

    Supports Basic auth (``email:api_token``) and Bearer token auth.
    Pass credentials as ``"email:api_token"`` for Basic auth or a raw
    Bearer token string. The ``base_url`` must point to your Jira
    instance (e.g., ``https://your-domain.atlassian.net/rest/api/3``).
    """

    name = "jira"
    display_name = "Jira"
    category = ConnectorCategory.PROJECT_MANAGEMENT
    protocol = ProtocolType.REST
    base_url = "https://your-domain.atlassian.net/rest/api/3"
    description = (
        "Connect to Jira to search, create, and manage issues, "
        "projects, and workflow transitions."
    )
    _rate_limit_config = RateLimitSpec(rate=100, period=60, burst=20)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        """Build authorization and content-type headers.

        If credentials contain ``:``, treat as ``email:token`` for
        Basic auth.  Otherwise, use as a Bearer token.
        """
        creds = str(self._credentials)
        if ":" in creds:
            encoded = base64.b64encode(creds.encode()).decode()
            auth_header = f"Basic {encoded}"
        else:
            auth_header = f"Bearer {creds}"

        return {
            "Authorization": auth_header,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Execute an HTTP request against the Jira REST API.

        Args:
            method: HTTP method.
            path: API path relative to ``base_url``.
            json: JSON request body.
            params: Query parameters.

        Returns:
            Parsed JSON response dict.

        Raises:
            httpx.HTTPStatusError: On non-2xx responses.
        """
        url = f"{self._base_url}{path}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.request(
                method,
                url,
                headers=self._headers(),
                json=json,
                params=params,
            )
            response.raise_for_status()
            if response.status_code == 204:
                return {}
            return response.json()

    def _agile_base_url(self) -> str:
        """Derive the Jira Agile REST API base URL from the configured base_url.

        Replaces ``/rest/api/3`` (or ``/rest/api/2``) with
        ``/rest/agile/1.0``.

        Returns:
            The Agile API base URL string.
        """
        base = str(self._base_url)
        for suffix in ("/rest/api/3", "/rest/api/2"):
            if base.endswith(suffix):
                return base[: -len(suffix)] + "/rest/agile/1.0"
        # Fallback: append agile path to domain root
        from urllib.parse import urlparse
        parsed = urlparse(base)
        return f"{parsed.scheme}://{parsed.netloc}/rest/agile/1.0"

    async def _agile_request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Execute an HTTP request against the Jira Agile REST API.

        Args:
            method: HTTP method.
            path: API path relative to the Agile base URL.
            params: Query parameters.

        Returns:
            Parsed JSON response dict.

        Raises:
            httpx.HTTPStatusError: On non-2xx responses.
        """
        url = f"{self._agile_base_url()}{path}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.request(
                method,
                url,
                headers=self._headers(),
                params=params,
            )
            response.raise_for_status()
            if response.status_code == 204:
                return {}
            return response.json()

    # ------------------------------------------------------------------
    # Response parsers (delegated to _helpers module)
    # ------------------------------------------------------------------

    _parse_user = staticmethod(parse_user)
    _parse_status = staticmethod(parse_status)
    _parse_issue = staticmethod(parse_issue)
    _parse_project = staticmethod(parse_project)
    _parse_comment = staticmethod(parse_comment)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    @action("Search issues using JQL")
    async def search_issues(
        self,
        jql: str,
        limit: int = 50,
        start_at: int = 0,
    ) -> PaginatedList[JiraIssue]:
        """Search for Jira issues using JQL (Jira Query Language).

        Args:
            jql: JQL query string (e.g., ``"project = PROJ AND status = Open"``).
            limit: Maximum results per page (max 100).
            start_at: Index of the first result to return (0-based offset).

        Returns:
            Paginated list of matching JiraIssue objects.
        """
        params: dict[str, Any] = {
            "jql": jql,
            "maxResults": min(limit, 100),
            "startAt": start_at,
        }
        data = await self._request("GET", "/search", params=params)

        issues = [self._parse_issue(i) for i in data.get("issues", [])]
        total = data.get("total", 0)
        returned = len(issues)
        next_offset = start_at + returned

        return PaginatedList(
            items=issues,
            page_state=PageState(
                offset=next_offset,
                total_count=total,
                has_more=next_offset < total,
            ),
            total_count=total,
        )

    @action("Get a single issue by key")
    async def get_issue(self, issue_key: str) -> JiraIssue:
        """Retrieve a Jira issue by its key (e.g., ``PROJ-123``).

        Args:
            issue_key: The issue key or ID.

        Returns:
            The requested JiraIssue.
        """
        data = await self._request("GET", f"/issue/{issue_key}")
        return self._parse_issue(data)

    @action("Create a new issue", dangerous=True)
    async def create_issue(
        self,
        project_key: str,
        summary: str,
        issue_type: str = "Task",
        description: Optional[str] = None,
        priority: Optional[str] = None,
        assignee: Optional[str] = None,
    ) -> JiraIssue:
        """Create a new Jira issue.

        Args:
            project_key: Key of the project (e.g., ``"PROJ"``).
            summary: One-line summary of the issue.
            issue_type: Issue type name (e.g., ``"Task"``, ``"Bug"``, ``"Story"``).
            description: Detailed description in Atlassian Document Format
                or plain text.
            priority: Priority name (e.g., ``"High"``, ``"Medium"``).
            assignee: Account ID of the assignee.

        Returns:
            The newly created JiraIssue (fetched after creation).
        """
        fields: dict[str, Any] = {
            "project": {"key": project_key},
            "summary": summary,
            "issuetype": {"name": issue_type},
        }

        if description:
            # Atlassian Document Format (ADF) wrapper for plain text
            fields["description"] = {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {"type": "text", "text": description}
                        ],
                    }
                ],
            }

        if priority:
            fields["priority"] = {"name": priority}
        if assignee:
            fields["assignee"] = {"accountId": assignee}

        body: dict[str, Any] = {"fields": fields}
        data = await self._request("POST", "/issue", json=body)

        # Jira returns minimal data on create; fetch the full issue.
        return await self.aget_issue(data["key"])

    @action("Update an existing issue")
    async def update_issue(
        self,
        issue_key: str,
        fields: dict[str, Any],
    ) -> JiraIssue:
        """Update fields on an existing Jira issue.

        Args:
            issue_key: The issue key (e.g., ``"PROJ-123"``).
            fields: Dict of field names to new values following the
                Jira field schema.

        Returns:
            The updated JiraIssue (re-fetched after update).
        """
        body: dict[str, Any] = {"fields": fields}
        await self._request("PUT", f"/issue/{issue_key}", json=body)

        # PUT returns 204; re-fetch the issue.
        return await self.aget_issue(issue_key)

    @action("Add a comment to an issue", dangerous=True)
    async def add_comment(
        self,
        issue_key: str,
        body: str,
    ) -> JiraComment:
        """Add a comment to a Jira issue.

        Args:
            issue_key: The issue key (e.g., ``"PROJ-123"``).
            body: Comment text. Sent as ADF (Atlassian Document Format).

        Returns:
            The created JiraComment.
        """
        adf_body: dict[str, Any] = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": body}],
                    }
                ],
            }
        }
        data = await self._request(
            "POST", f"/issue/{issue_key}/comment", json=adf_body
        )
        return self._parse_comment(data)

    @action("Transition an issue to a new status", dangerous=True)
    async def transition_issue(
        self,
        issue_key: str,
        transition_id: str,
    ) -> None:
        """Move an issue through a workflow transition.

        Args:
            issue_key: The issue key (e.g., ``"PROJ-123"``).
            transition_id: The ID of the transition to execute. Use
                ``get_transitions`` to discover available transitions.
        """
        body: dict[str, Any] = {
            "transition": {"id": transition_id}
        }
        await self._request(
            "POST", f"/issue/{issue_key}/transitions", json=body
        )

    @action("List projects accessible to the user")
    async def list_projects(
        self,
        limit: int = 50,
        start_at: int = 0,
    ) -> PaginatedList[JiraProject]:
        """List Jira projects visible to the authenticated user.

        Args:
            limit: Maximum projects per page (max 50).
            start_at: Offset for pagination (0-based).

        Returns:
            Paginated list of JiraProject objects.
        """
        params: dict[str, Any] = {
            "maxResults": min(limit, 50),
            "startAt": start_at,
        }
        data = await self._request("GET", "/project/search", params=params)

        projects = [
            self._parse_project(p) for p in data.get("values", [])
        ]
        total = data.get("total", 0)
        returned = len(projects)
        next_offset = start_at + returned

        return PaginatedList(
            items=projects,
            page_state=PageState(
                offset=next_offset,
                total_count=total,
                has_more=next_offset < total,
            ),
            total_count=total,
        )

    @action("Get available transitions for an issue")
    async def get_transitions(
        self,
        issue_key: str,
    ) -> list[JiraTransition]:
        """List the workflow transitions available for an issue.

        Args:
            issue_key: The issue key (e.g., ``"PROJ-123"``).

        Returns:
            List of available JiraTransition objects.
        """
        data = await self._request(
            "GET", f"/issue/{issue_key}/transitions"
        )

        transitions: list[JiraTransition] = []
        for t in data.get("transitions", []):
            to_status = t.get("to")
            transitions.append(
                JiraTransition(
                    id=t["id"],
                    name=t.get("name", ""),
                    to_status=self._parse_status(to_status),
                    has_screen=t.get("hasScreen", False),
                )
            )
        return transitions

    # ------------------------------------------------------------------
    # Actions — Issue management (continued)
    # ------------------------------------------------------------------

    @action("Delete an issue", dangerous=True)
    async def delete_issue(self, issue_key: str) -> None:
        """Permanently delete a Jira issue.

        Args:
            issue_key: The issue key (e.g., ``"PROJ-123"``).

        Warning:
            This action permanently deletes the issue and all its data
            including comments, attachments, and worklogs.
        """
        await self._request("DELETE", f"/issue/{issue_key}")

    @action("Assign an issue to a user")
    async def assign_issue(
        self,
        issue_key: str,
        assignee_account_id: str,
    ) -> None:
        """Assign an issue to a user.

        Args:
            issue_key: The issue key (e.g., ``"PROJ-123"``).
            assignee_account_id: The Atlassian account ID of the user
                to assign. Pass ``"-1"`` to set unassigned.
        """
        body: dict[str, Any] = {"accountId": assignee_account_id}
        await self._request("PUT", f"/issue/{issue_key}/assignee", json=body)

    @action("List comments on an issue")
    async def list_comments(self, issue_key: str) -> list[JiraComment]:
        """List all comments on a Jira issue.

        Args:
            issue_key: The issue key (e.g., ``"PROJ-123"``).

        Returns:
            List of JiraComment objects.
        """
        data = await self._request(
            "GET", f"/issue/{issue_key}/comment"
        )
        return [
            self._parse_comment(c)
            for c in data.get("comments", [])
        ]

    @action("Delete a comment from an issue", dangerous=True)
    async def delete_comment(
        self,
        issue_key: str,
        comment_id: str,
    ) -> None:
        """Delete a comment from a Jira issue.

        Args:
            issue_key: The issue key (e.g., ``"PROJ-123"``).
            comment_id: The ID of the comment to delete.

        Warning:
            This permanently deletes the comment.
        """
        await self._request(
            "DELETE", f"/issue/{issue_key}/comment/{comment_id}"
        )

    @action("Add a watcher to an issue")
    async def add_watcher(
        self,
        issue_key: str,
        account_id: str,
    ) -> None:
        """Add a user as a watcher on an issue.

        Args:
            issue_key: The issue key (e.g., ``"PROJ-123"``).
            account_id: The Atlassian account ID of the user to add
                as a watcher.
        """
        # Jira REST API v3 expects the account ID as a raw JSON string
        url = f"{self._base_url}/issue/{issue_key}/watchers"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                url,
                headers=self._headers(),
                json=account_id,
            )
            response.raise_for_status()

    # ------------------------------------------------------------------
    # Actions — Agile (Boards & Sprints)
    # ------------------------------------------------------------------

    @action("List sprints for a board")
    async def list_sprints(
        self,
        board_id: int,
        state: Optional[str] = None,
        limit: int = 50,
        start_at: int = 0,
    ) -> PaginatedList[JiraSprint]:
        """List sprints for a given Agile board.

        Args:
            board_id: The ID of the Agile board.
            state: Filter by sprint state: ``active``, ``closed``,
                or ``future``. Omit to list all.
            limit: Maximum sprints per page (max 50).
            start_at: Offset for pagination (0-based).

        Returns:
            Paginated list of JiraSprint objects.
        """
        params: dict[str, Any] = {
            "maxResults": min(limit, 50),
            "startAt": start_at,
        }
        if state:
            params["state"] = state

        data = await self._agile_request(
            "GET", f"/board/{board_id}/sprint", params=params,
        )

        sprints: list[JiraSprint] = []
        for s in data.get("values", []):
            sprints.append(
                JiraSprint(
                    id=s["id"],
                    name=s.get("name", ""),
                    state=s.get("state"),
                    start_date=s.get("startDate"),
                    end_date=s.get("endDate"),
                    complete_date=s.get("completeDate"),
                    board_id=s.get("originBoardId"),
                    goal=s.get("goal"),
                    self_url=s.get("self"),
                )
            )

        total = data.get("total", len(sprints))
        returned = len(sprints)
        next_offset = start_at + returned

        return PaginatedList(
            items=sprints,
            page_state=PageState(
                offset=next_offset,
                total_count=total,
                has_more=data.get("isLast") is False,
            ),
            total_count=total,
        )

    @action("Get an Agile board by ID")
    async def get_board(self, board_id: int) -> JiraBoard:
        """Retrieve a single Agile board.

        Args:
            board_id: The ID of the board to retrieve.

        Returns:
            JiraBoard object.
        """
        data = await self._agile_request("GET", f"/board/{board_id}")
        location = data.get("location", {})
        return JiraBoard(
            id=data["id"],
            name=data.get("name", ""),
            type=data.get("type"),
            project_key=location.get("projectKey"),
            self_url=data.get("self"),
        )

    @action("List Agile boards")
    async def list_boards(
        self,
        project_key: Optional[str] = None,
        limit: int = 50,
        start_at: int = 0,
    ) -> PaginatedList[JiraBoard]:
        """List Agile boards with optional project filter.

        Args:
            project_key: Filter boards by project key.
            limit: Maximum boards per page (max 50).
            start_at: Offset for pagination (0-based).

        Returns:
            Paginated list of JiraBoard objects.
        """
        params: dict[str, Any] = {
            "maxResults": min(limit, 50),
            "startAt": start_at,
        }
        if project_key:
            params["projectKeyOrId"] = project_key

        data = await self._agile_request(
            "GET", "/board", params=params,
        )

        boards: list[JiraBoard] = []
        for b in data.get("values", []):
            location = b.get("location", {})
            boards.append(
                JiraBoard(
                    id=b["id"],
                    name=b.get("name", ""),
                    type=b.get("type"),
                    project_key=location.get("projectKey"),
                    self_url=b.get("self"),
                )
            )

        total = data.get("total", len(boards))
        returned = len(boards)
        next_offset = start_at + returned

        return PaginatedList(
            items=boards,
            page_state=PageState(
                offset=next_offset,
                total_count=total,
                has_more=data.get("isLast") is False,
            ),
            total_count=total,
        )

    # ------------------------------------------------------------------
    # Actions — Attachments
    # ------------------------------------------------------------------

    @action("Add an attachment to an issue", dangerous=True)
    async def add_attachment(
        self,
        issue_key: str,
        filename: str,
        content: bytes,
    ) -> JiraAttachment:
        """Upload a file attachment to a Jira issue.

        Args:
            issue_key: The issue key (e.g., ``"PROJ-123"``).
            filename: The name of the file being uploaded.
            content: Raw file content as bytes.

        Returns:
            The created JiraAttachment object.
        """
        url = f"{self._base_url}/issue/{issue_key}/attachments"
        headers = self._headers()
        # Jira requires this header for attachment uploads
        headers["X-Atlassian-Token"] = "no-check"
        # Remove Content-Type so httpx sets it for multipart
        headers.pop("Content-Type", None)

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                url,
                headers=headers,
                files={"file": (filename, content)},
            )
            response.raise_for_status()
            attachments = response.json()

        # Jira returns a list; take the first (and usually only) item
        att = attachments[0] if attachments else {}
        return JiraAttachment(
            id=att.get("id", ""),
            filename=att.get("filename", filename),
            mime_type=att.get("mimeType"),
            size=att.get("size"),
            author=self._parse_user(att.get("author")),
            created=att.get("created"),
            content_url=att.get("content"),
            self_url=att.get("self"),
        )

    # ------------------------------------------------------------------
    # Actions — Users
    # ------------------------------------------------------------------

    @action("Get a Jira user by account ID")
    async def get_user(self, account_id: str) -> JiraUser:
        """Retrieve a Jira user by their Atlassian account ID.

        Args:
            account_id: The Atlassian account ID of the user.

        Returns:
            JiraUser object with profile details.
        """
        data = await self._request(
            "GET",
            "/user",
            params={"accountId": account_id},
        )
        user = self._parse_user(data)
        if user is None:
            return JiraUser(account_id=account_id)
        return user

    # ------------------------------------------------------------------
    # Actions — Projects (extended)
    # ------------------------------------------------------------------

    @action("Create a new project", dangerous=True)
    async def create_project(
        self,
        name: str,
        key: str,
        project_type_key: str,
        lead_account_id: str,
    ) -> JiraProject:
        """Create a new Jira project.

        Args:
            name: Display name for the project.
            key: Unique project key (e.g., ``"PROJ"``).  Must be uppercase
                alphanumeric, 2-10 characters.
            project_type_key: The type of project (e.g., ``"software"``,
                ``"service_desk"``, ``"business"``).
            lead_account_id: Atlassian account ID of the project lead.

        Returns:
            The newly created JiraProject.
        """
        body: dict[str, Any] = {
            "name": name,
            "key": key,
            "projectTypeKey": project_type_key,
            "leadAccountId": lead_account_id,
        }
        data = await self._request("POST", "/project", json=body)
        # Jira returns minimal data; fetch the full project.
        return self._parse_project(
            await self._request("GET", f"/project/{data.get('key', key)}")
        )

    # ------------------------------------------------------------------
    # Actions — Issue types & metadata
    # ------------------------------------------------------------------

    @action("List issue types available in the instance")
    async def list_issue_types(
        self,
        project_id: Optional[str] = None,
    ) -> list[JiraIssueType]:
        """List issue types, optionally filtered by project.

        Args:
            project_id: Optional project ID to scope the issue types to
                a specific project.  When omitted, returns all global
                issue types.

        Returns:
            List of JiraIssueType objects.
        """
        if project_id:
            data = await self._request(
                "GET",
                "/issuetype/project",
                params={"projectId": project_id},
            )
        else:
            data = await self._request("GET", "/issuetype")

        # data is a list when fetching all issue types
        items = data if isinstance(data, list) else data.get("issueTypes", data)
        return [parse_issue_type(it) for it in items if it]

    @action("List available priorities")
    async def list_priorities(self) -> list[JiraPriority]:
        """List all issue priorities configured in the Jira instance.

        Returns:
            List of JiraPriority objects ordered by sequence.
        """
        data = await self._request("GET", "/priority")
        items = data if isinstance(data, list) else data.get("values", [])
        return [parse_priority(p) for p in items if p]

    @action("List available resolutions")
    async def list_resolutions(self) -> list[JiraResolution]:
        """List all issue resolutions configured in the Jira instance.

        Returns:
            List of JiraResolution objects.
        """
        data = await self._request("GET", "/resolution")
        items = data if isinstance(data, list) else data.get("values", [])
        return [parse_resolution(r) for r in items if r]

    # ------------------------------------------------------------------
    # Actions — Worklogs
    # ------------------------------------------------------------------

    @action("Add a worklog entry to an issue", dangerous=True)
    async def add_worklog(
        self,
        issue_key: str,
        time_spent: str,
        comment: Optional[str] = None,
    ) -> JiraWorklog:
        """Log time spent on a Jira issue.

        Args:
            issue_key: The issue key (e.g., ``"PROJ-123"``).
            time_spent: Time spent in Jira duration format
                (e.g., ``"2h 30m"``, ``"1d"``, ``"45m"``).
            comment: Optional plain-text comment describing the work done.

        Returns:
            The created JiraWorklog entry.
        """
        body: dict[str, Any] = {"timeSpent": time_spent}
        if comment:
            body["comment"] = {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": comment}],
                    }
                ],
            }

        data = await self._request(
            "POST", f"/issue/{issue_key}/worklog", json=body
        )
        return parse_worklog(data)

    @action("List worklog entries on an issue")
    async def list_worklogs(self, issue_key: str) -> list[JiraWorklog]:
        """List all worklog entries on a Jira issue.

        Args:
            issue_key: The issue key (e.g., ``"PROJ-123"``).

        Returns:
            List of JiraWorklog entries.
        """
        data = await self._request(
            "GET", f"/issue/{issue_key}/worklog"
        )
        return [
            parse_worklog(w) for w in data.get("worklogs", [])
        ]

    # ------------------------------------------------------------------
    # Actions — Watchers (extended)
    # ------------------------------------------------------------------

    @action("List watchers on an issue")
    async def list_watchers(self, issue_key: str) -> list[JiraUser]:
        """List all users watching a Jira issue.

        Args:
            issue_key: The issue key (e.g., ``"PROJ-123"``).

        Returns:
            List of JiraUser objects watching the issue.
        """
        data = await self._request(
            "GET", f"/issue/{issue_key}/watchers"
        )
        watchers: list[JiraUser] = []
        for w in data.get("watchers", []):
            user = self._parse_user(w)
            if user is not None:
                watchers.append(user)
        return watchers

    @action("Remove a watcher from an issue")
    async def remove_watcher(
        self,
        issue_key: str,
        account_id: str,
    ) -> None:
        """Remove a user from an issue's watcher list.

        Args:
            issue_key: The issue key (e.g., ``"PROJ-123"``).
            account_id: The Atlassian account ID of the user to remove.
        """
        await self._request(
            "DELETE",
            f"/issue/{issue_key}/watchers",
            params={"accountId": account_id},
        )

    # ------------------------------------------------------------------
    # Actions — Issue links
    # ------------------------------------------------------------------

    @action("Create a link between two issues", dangerous=True)
    async def link_issues(
        self,
        inward_key: str,
        outward_key: str,
        link_type: str,
    ) -> None:
        """Create a link between two Jira issues.

        Args:
            inward_key: The issue key for the inward issue
                (e.g., ``"PROJ-100"``).
            outward_key: The issue key for the outward issue
                (e.g., ``"PROJ-200"``).
            link_type: The name of the link type (e.g., ``"Blocks"``,
                ``"Duplicate"``, ``"Relates"``).
        """
        body: dict[str, Any] = {
            "type": {"name": link_type},
            "inwardIssue": {"key": inward_key},
            "outwardIssue": {"key": outward_key},
        }
        await self._request("POST", "/issueLink", json=body)

    # ------------------------------------------------------------------
    # Actions — User search
    # ------------------------------------------------------------------

    @action("Search for Jira users")
    async def search_users(
        self,
        query: str,
        limit: int = 50,
    ) -> list[JiraUser]:
        """Search for Jira users by display name or email address.

        Args:
            query: The search string to match against user display names
                and email addresses.
            limit: Maximum number of results to return (max 1000).

        Returns:
            List of matching JiraUser objects.
        """
        params: dict[str, Any] = {
            "query": query,
            "maxResults": min(limit, 1000),
        }
        data = await self._request("GET", "/user/search", params=params)
        # /user/search returns a bare list
        items = data if isinstance(data, list) else []
        users: list[JiraUser] = []
        for u in items:
            user = self._parse_user(u)
            if user is not None:
                users.append(user)
        return users
