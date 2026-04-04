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

from .types import (
    JiraComment,
    JiraIssue,
    JiraIssueType,
    JiraPriority,
    JiraProject,
    JiraStatus,
    JiraTransition,
    JiraUser,
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

    # ------------------------------------------------------------------
    # Response parsers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_user(data: Optional[dict[str, Any]]) -> Optional[JiraUser]:
        """Parse a Jira user JSON fragment."""
        if not data:
            return None
        return JiraUser(
            account_id=data.get("accountId", ""),
            display_name=data.get("displayName"),
            email_address=data.get("emailAddress"),
            active=data.get("active", True),
            avatar_url=(data.get("avatarUrls") or {}).get("48x48"),
        )

    @staticmethod
    def _parse_priority(
        data: Optional[dict[str, Any]],
    ) -> Optional[JiraPriority]:
        """Parse a priority JSON fragment."""
        if not data:
            return None
        return JiraPriority(
            id=data.get("id", ""),
            name=data.get("name", ""),
            icon_url=data.get("iconUrl"),
        )

    @staticmethod
    def _parse_status(
        data: Optional[dict[str, Any]],
    ) -> Optional[JiraStatus]:
        """Parse a status JSON fragment."""
        if not data:
            return None
        category = data.get("statusCategory", {})
        return JiraStatus(
            id=data.get("id", ""),
            name=data.get("name", ""),
            category_key=category.get("key"),
        )

    @staticmethod
    def _parse_issue_type(
        data: Optional[dict[str, Any]],
    ) -> Optional[JiraIssueType]:
        """Parse an issue-type JSON fragment."""
        if not data:
            return None
        return JiraIssueType(
            id=data.get("id", ""),
            name=data.get("name", ""),
            subtask=data.get("subtask", False),
            icon_url=data.get("iconUrl"),
        )

    @classmethod
    def _parse_issue(cls, data: dict[str, Any]) -> JiraIssue:
        """Parse a raw Jira issue JSON into a JiraIssue model."""
        fields = data.get("fields", {})
        components = [c.get("name", "") for c in fields.get("components", [])]
        fix_versions = [v.get("name", "") for v in fields.get("fixVersions", [])]
        project = fields.get("project", {})

        return JiraIssue(
            id=data["id"],
            key=data["key"],
            self_url=data.get("self"),
            summary=fields.get("summary", ""),
            description=fields.get("description"),
            status=cls._parse_status(fields.get("status")),
            issue_type=cls._parse_issue_type(fields.get("issuetype")),
            priority=cls._parse_priority(fields.get("priority")),
            assignee=cls._parse_user(fields.get("assignee")),
            reporter=cls._parse_user(fields.get("reporter")),
            project_key=project.get("key", ""),
            created=fields.get("created"),
            updated=fields.get("updated"),
            labels=fields.get("labels", []),
            components=components,
            fix_versions=fix_versions,
        )

    @classmethod
    def _parse_project(cls, data: dict[str, Any]) -> JiraProject:
        """Parse a raw Jira project JSON into a JiraProject model."""
        return JiraProject(
            id=data.get("id", ""),
            key=data.get("key", ""),
            name=data.get("name", ""),
            project_type_key=data.get("projectTypeKey"),
            lead=cls._parse_user(data.get("lead")),
            avatar_url=(data.get("avatarUrls") or {}).get("48x48"),
            self_url=data.get("self"),
        )

    @classmethod
    def _parse_comment(cls, data: dict[str, Any]) -> JiraComment:
        """Parse a Jira comment JSON into a JiraComment model."""
        return JiraComment(
            id=data.get("id", ""),
            body=data.get("body"),
            author=cls._parse_user(data.get("author")),
            created=data.get("created"),
            updated=data.get("updated"),
            self_url=data.get("self"),
        )

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
