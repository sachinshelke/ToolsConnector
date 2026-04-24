"""Linear connector -- issues, teams, and projects via the Linear GraphQL API."""

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

from ._queries import (
    COMMENT_FIELDS,
    CYCLE_FIELDS,
    ISSUE_FIELDS,
    PROJECT_FIELDS,
    TEAM_FIELDS,
    USER_FIELDS,
)
from .types import (
    LinearComment,
    LinearCycle,
    LinearIssue,
    LinearLabel,
    LinearProject,
    LinearState,
    LinearTeam,
    LinearUser,
)


class Linear(BaseConnector):
    """Connect to Linear to manage issues, teams, and projects.

    Uses the Linear GraphQL API at ``https://api.linear.app/graphql``.
    Credentials should be a Linear API key (string).
    """

    name = "linear"
    display_name = "Linear"
    category = ConnectorCategory.PROJECT_MANAGEMENT
    protocol = ProtocolType.GRAPHQL
    base_url = "https://api.linear.app"
    description = (
        "Connect to Linear to search, create, and manage issues, projects, and teams via GraphQL."
    )
    _rate_limit_config = RateLimitSpec(rate=250, period=60, burst=50)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        """Build standard request headers for the Linear API."""
        return {
            "Authorization": str(self._credentials),
            "Content-Type": "application/json",
        }

    async def _graphql(
        self,
        query: str,
        variables: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Execute a GraphQL request against the Linear API.

        Args:
            query: GraphQL query or mutation string.
            variables: Variables to pass to the query.

        Returns:
            The ``data`` key from the GraphQL response.

        Raises:
            httpx.HTTPStatusError: On non-2xx responses.
            ValueError: If the GraphQL response contains errors.
        """
        url = f"{self._base_url}/graphql"
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                url,
                headers=self._headers(),
                json=payload,
            )
            raise_typed_for_status(response, connector=self.name)
            result = response.json()

        if "errors" in result and result["errors"]:
            messages = "; ".join(e.get("message", str(e)) for e in result["errors"])
            raise ValueError(f"Linear GraphQL errors: {messages}")

        return result.get("data", {})

    # ------------------------------------------------------------------
    # Response parsers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_user(data: Optional[dict[str, Any]]) -> Optional[LinearUser]:
        """Parse a Linear user JSON fragment."""
        if not data:
            return None
        return LinearUser(
            id=data["id"],
            name=data.get("name"),
            display_name=data.get("displayName"),
            email=data.get("email"),
            avatar_url=data.get("avatarUrl"),
            active=data.get("active", True),
        )

    @staticmethod
    def _parse_state(data: Optional[dict[str, Any]]) -> Optional[LinearState]:
        """Parse a workflow state JSON fragment."""
        if not data:
            return None
        return LinearState(
            id=data["id"],
            name=data.get("name", ""),
            type=data.get("type", ""),
            color=data.get("color"),
            position=data.get("position"),
        )

    @classmethod
    def _parse_issue(cls, data: dict[str, Any]) -> LinearIssue:
        """Parse a raw Linear issue node into a LinearIssue model."""
        labels_data = data.get("labels", {}).get("nodes", [])
        labels = [
            LinearLabel(
                id=lbl["id"],
                name=lbl.get("name", ""),
                color=lbl.get("color"),
            )
            for lbl in labels_data
        ]
        team_data = data.get("team")
        project_data = data.get("project")

        return LinearIssue(
            id=data["id"],
            identifier=data.get("identifier", ""),
            title=data.get("title", ""),
            description=data.get("description"),
            priority=data.get("priority", 0),
            priority_label=data.get("priorityLabel", ""),
            state=cls._parse_state(data.get("state")),
            assignee=cls._parse_user(data.get("assignee")),
            creator=cls._parse_user(data.get("creator")),
            team_id=team_data["id"] if team_data else None,
            project_id=project_data["id"] if project_data else None,
            url=data.get("url"),
            created_at=data.get("createdAt"),
            updated_at=data.get("updatedAt"),
            completed_at=data.get("completedAt"),
            canceled_at=data.get("canceledAt"),
            due_date=data.get("dueDate"),
            estimate=data.get("estimate"),
            labels=labels,
        )

    @classmethod
    def _parse_project(cls, data: dict[str, Any]) -> LinearProject:
        """Parse a raw Linear project node into a LinearProject model."""
        return LinearProject(
            id=data["id"],
            name=data.get("name", ""),
            description=data.get("description"),
            slug_id=data.get("slugId"),
            state=data.get("state", ""),
            url=data.get("url"),
            created_at=data.get("createdAt"),
            updated_at=data.get("updatedAt"),
            started_at=data.get("startedAt"),
            target_date=data.get("targetDate"),
            progress=data.get("progress", 0.0),
            lead=cls._parse_user(data.get("lead")),
        )

    @staticmethod
    def _parse_cycle(data: dict[str, Any]) -> LinearCycle:
        """Parse a raw Linear cycle node into a LinearCycle model."""
        team_data = data.get("team")
        return LinearCycle(
            id=data["id"],
            number=data.get("number"),
            name=data.get("name"),
            description=data.get("description"),
            starts_at=data.get("startsAt"),
            ends_at=data.get("endsAt"),
            completed_at=data.get("completedAt"),
            progress=data.get("progress", 0.0),
            scope_count=data.get("scopeCount"),
            completed_scope_count=data.get("completedScopeCount"),
            team_id=team_data["id"] if team_data else None,
        )

    @classmethod
    def _parse_comment(cls, data: dict[str, Any]) -> LinearComment:
        """Parse a raw Linear comment node into a LinearComment model."""
        issue_data = data.get("issue")
        return LinearComment(
            id=data["id"],
            body=data.get("body", ""),
            user=cls._parse_user(data.get("user")),
            issue_id=issue_data["id"] if issue_data else None,
            created_at=data.get("createdAt"),
            updated_at=data.get("updatedAt"),
            url=data.get("url"),
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    @action("List issues with optional team and state filters")
    async def list_issues(
        self,
        team_id: Optional[str] = None,
        state: Optional[str] = None,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> PaginatedList[LinearIssue]:
        """List Linear issues, optionally filtered by team or state name.

        Args:
            team_id: Filter to issues belonging to this team ID.
            state: Filter to issues in this workflow state name.
            limit: Maximum results per page (max 250).
            cursor: Pagination cursor from a previous response.

        Returns:
            Paginated list of LinearIssue objects.
        """
        filters: list[str] = []
        if team_id:
            filters.append(f'team: {{ id: {{ eq: "{team_id}" }} }}')
        if state:
            filters.append(f'state: {{ name: {{ eq: "{state}" }} }}')

        filter_arg = f"filter: {{ {', '.join(filters)} }}," if filters else ""
        after_arg = f', after: "{cursor}"' if cursor else ""

        query = f"""
        query {{ issues(first: {min(limit, 250)}, {filter_arg}
            orderBy: updatedAt {after_arg}) {{
            nodes {{ {ISSUE_FIELDS} }}
            pageInfo {{ hasNextPage endCursor }}
        }} }}
        """
        data = await self._graphql(query)
        issues_data = data.get("issues", {})
        nodes = issues_data.get("nodes", [])
        page_info = issues_data.get("pageInfo", {})

        return PaginatedList(
            items=[self._parse_issue(n) for n in nodes],
            page_state=PageState(
                cursor=page_info.get("endCursor"),
                has_more=page_info.get("hasNextPage", False),
            ),
        )

    @action("Get a single issue by ID")
    async def get_issue(self, issue_id: str) -> LinearIssue:
        """Retrieve a Linear issue by its UUID.

        Args:
            issue_id: The UUID of the issue.

        Returns:
            The requested LinearIssue.
        """
        query = f"""
        query($id: String!) {{ issue(id: $id) {{ {ISSUE_FIELDS} }} }}
        """
        data = await self._graphql(query, variables={"id": issue_id})
        return self._parse_issue(data["issue"])

    @action("Create a new issue", dangerous=True)
    async def create_issue(
        self,
        team_id: str,
        title: str,
        description: Optional[str] = None,
        priority: Optional[int] = None,
        assignee_id: Optional[str] = None,
    ) -> LinearIssue:
        """Create a new Linear issue.

        Args:
            team_id: UUID of the team to create the issue in.
            title: Issue title.
            description: Markdown description of the issue.
            priority: Priority level (0=none, 1=urgent, 2=high,
                3=medium, 4=low).
            assignee_id: UUID of the user to assign.

        Returns:
            The newly created LinearIssue.
        """
        inp: list[str] = [f'teamId: "{team_id}"', f'title: "{title}"']
        if description is not None:
            esc = description.replace("\\", "\\\\").replace('"', '\\"')
            cleaned = esc.replace("\n", "\\n")
            inp.append(f'description: "{cleaned}"')
        if priority is not None:
            inp.append(f"priority: {priority}")
        if assignee_id:
            inp.append(f'assigneeId: "{assignee_id}"')

        query = f"""
        mutation {{ issueCreate(input: {{ {", ".join(inp)} }}) {{
            success issue {{ {ISSUE_FIELDS} }}
        }} }}
        """
        data = await self._graphql(query)
        result = data.get("issueCreate", {})
        if not result.get("success"):
            raise ValueError("Linear issue creation failed")
        return self._parse_issue(result["issue"])

    @action("Update an existing issue")
    async def update_issue(
        self,
        issue_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        state_id: Optional[str] = None,
        priority: Optional[int] = None,
    ) -> LinearIssue:
        """Update fields on an existing Linear issue.

        Args:
            issue_id: UUID of the issue to update.
            title: New title (if changing).
            description: New description (if changing).
            state_id: UUID of the new workflow state (if changing).
            priority: New priority level (if changing).

        Returns:
            The updated LinearIssue.
        """
        inp: list[str] = []
        if title is not None:
            inp.append(f'title: "{title}"')
        if description is not None:
            esc = description.replace("\\", "\\\\").replace('"', '\\"')
            cleaned = esc.replace("\n", "\\n")
            inp.append(f'description: "{cleaned}"')
        if state_id is not None:
            inp.append(f'stateId: "{state_id}"')
        if priority is not None:
            inp.append(f"priority: {priority}")
        if not inp:
            return await self.aget_issue(issue_id)

        query = f"""
        mutation {{ issueUpdate(id: "{issue_id}",
            input: {{ {", ".join(inp)} }}) {{
            success issue {{ {ISSUE_FIELDS} }}
        }} }}
        """
        data = await self._graphql(query)
        result = data.get("issueUpdate", {})
        if not result.get("success"):
            raise ValueError("Linear issue update failed")
        return self._parse_issue(result["issue"])

    @action("List all teams in the workspace")
    async def list_teams(self) -> list[LinearTeam]:
        """List all teams in the Linear workspace.

        Returns:
            List of LinearTeam objects.
        """
        query = f"""
        query {{ teams {{ nodes {{ {TEAM_FIELDS} }} }} }}
        """
        data = await self._graphql(query)
        return [
            LinearTeam(
                id=t["id"],
                name=t.get("name", ""),
                key=t.get("key", ""),
                description=t.get("description"),
                icon=t.get("icon"),
                color=t.get("color"),
                private=t.get("private", False),
            )
            for t in data.get("teams", {}).get("nodes", [])
        ]

    @action("List projects with pagination")
    async def list_projects(
        self,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> PaginatedList[LinearProject]:
        """List projects in the Linear workspace.

        Args:
            limit: Maximum results per page (max 250).
            cursor: Pagination cursor from a previous response.

        Returns:
            Paginated list of LinearProject objects.
        """
        after_arg = f', after: "{cursor}"' if cursor else ""
        query = f"""
        query {{ projects(first: {min(limit, 250)} {after_arg}) {{
            nodes {{ {PROJECT_FIELDS} }}
            pageInfo {{ hasNextPage endCursor }}
        }} }}
        """
        data = await self._graphql(query)
        proj_data = data.get("projects", {})
        page_info = proj_data.get("pageInfo", {})

        return PaginatedList(
            items=[self._parse_project(n) for n in proj_data.get("nodes", [])],
            page_state=PageState(
                cursor=page_info.get("endCursor"),
                has_more=page_info.get("hasNextPage", False),
            ),
        )

    @action("Add a comment to an issue", dangerous=True)
    async def add_comment(self, issue_id: str, body: str) -> LinearComment:
        """Add a comment to a Linear issue.

        Args:
            issue_id: UUID of the issue to comment on.
            body: Comment body in Markdown format.

        Returns:
            The created LinearComment.
        """
        esc = body.replace("\\", "\\\\").replace('"', '\\"')
        esc = esc.replace("\n", "\\n")
        query = f"""
        mutation {{ commentCreate(input: {{
            issueId: "{issue_id}", body: "{esc}"
        }}) {{
            success comment {{ {COMMENT_FIELDS} }}
        }} }}
        """
        data = await self._graphql(query)
        result = data.get("commentCreate", {})
        if not result.get("success"):
            raise ValueError("Linear comment creation failed")
        return self._parse_comment(result["comment"])

    @action("Search issues by text query")
    async def search_issues(
        self,
        query: str,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> PaginatedList[LinearIssue]:
        """Search for Linear issues using a text query.

        Args:
            query: Search text to match against issue titles and
                descriptions.
            limit: Maximum results per page (max 250).
            cursor: Pagination cursor from a previous response.

        Returns:
            Paginated list of matching LinearIssue objects.
        """
        after_arg = f', after: "{cursor}"' if cursor else ""
        escaped = query.replace("\\", "\\\\").replace('"', '\\"')

        gql = f"""
        query {{ issueSearch(query: "{escaped}",
            first: {min(limit, 250)} {after_arg}) {{
            nodes {{ {ISSUE_FIELDS} }}
            pageInfo {{ hasNextPage endCursor }}
        }} }}
        """
        data = await self._graphql(gql)
        search_data = data.get("issueSearch", {})
        page_info = search_data.get("pageInfo", {})

        return PaginatedList(
            items=[self._parse_issue(n) for n in search_data.get("nodes", [])],
            page_state=PageState(
                cursor=page_info.get("endCursor"),
                has_more=page_info.get("hasNextPage", False),
            ),
        )

    # ------------------------------------------------------------------
    # Actions — Issue management (extended)
    # ------------------------------------------------------------------

    @action("Delete an issue by ID", dangerous=True)
    async def delete_issue(self, issue_id: str) -> bool:
        """Permanently delete a Linear issue.

        Args:
            issue_id: UUID of the issue to delete.

        Returns:
            True if the issue was deleted successfully.
        """
        query = f"""
        mutation {{ issueDelete(id: "{issue_id}") {{ success }} }}
        """
        data = await self._graphql(query)
        return data.get("issueDelete", {}).get("success", False)

    # ------------------------------------------------------------------
    # Actions — Labels
    # ------------------------------------------------------------------

    @action("List issue labels, optionally filtered by team")
    async def list_labels(
        self,
        team_id: Optional[str] = None,
    ) -> list[LinearLabel]:
        """List issue labels in the workspace or for a specific team.

        Args:
            team_id: Optional team UUID to filter labels by.

        Returns:
            List of LinearLabel objects.
        """
        filter_arg = ""
        if team_id:
            filter_arg = f'filter: {{ team: {{ id: {{ eq: "{team_id}" }} }} }},'
        query = f"""
        query {{ issueLabels({filter_arg} first: 250) {{
            nodes {{ id name color }}
        }} }}
        """
        data = await self._graphql(query)
        return [
            LinearLabel(
                id=lbl["id"],
                name=lbl.get("name", ""),
                color=lbl.get("color"),
            )
            for lbl in data.get("issueLabels", {}).get("nodes", [])
        ]

    @action("Create a new issue label", dangerous=True)
    async def create_label(
        self,
        team_id: str,
        name: str,
        color: Optional[str] = None,
    ) -> LinearLabel:
        """Create a new issue label for a team.

        Args:
            team_id: UUID of the team to create the label in.
            name: Label name.
            color: Hex colour string (e.g. ``#ff0000``).

        Returns:
            The created LinearLabel.
        """
        inp = [f'teamId: "{team_id}"', f'name: "{name}"']
        if color:
            inp.append(f'color: "{color}"')
        query = f"""
        mutation {{ issueLabelCreate(input: {{ {", ".join(inp)} }}) {{
            success issueLabel {{ id name color }}
        }} }}
        """
        data = await self._graphql(query)
        result = data.get("issueLabelCreate", {})
        if not result.get("success"):
            raise ValueError("Linear label creation failed")
        lbl = result["issueLabel"]
        return LinearLabel(
            id=lbl["id"],
            name=lbl.get("name", ""),
            color=lbl.get("color"),
        )

    # ------------------------------------------------------------------
    # Actions — Workflow states
    # ------------------------------------------------------------------

    @action("Get workflow states for a team")
    async def get_workflow_states(self, team_id: str) -> list[LinearState]:
        """List all workflow states for a team.

        Args:
            team_id: UUID of the team.

        Returns:
            List of LinearState objects ordered by position.
        """
        query = f"""
        query {{ workflowStates(
            filter: {{ team: {{ id: {{ eq: "{team_id}" }} }} }},
            first: 100
        ) {{
            nodes {{ id name type color position }}
        }} }}
        """
        data = await self._graphql(query)
        return [
            LinearState(
                id=s["id"],
                name=s.get("name", ""),
                type=s.get("type", ""),
                color=s.get("color"),
                position=s.get("position"),
            )
            for s in data.get("workflowStates", {}).get("nodes", [])
        ]

    # ------------------------------------------------------------------
    # Actions -- Cycles
    # ------------------------------------------------------------------

    @action("List cycles, optionally filtered by team")
    async def list_cycles(
        self,
        team_id: Optional[str] = None,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> PaginatedList[LinearCycle]:
        """List cycles (sprints) in the Linear workspace.

        Args:
            team_id: Optional team UUID to filter cycles by.
            limit: Maximum results per page (max 250).
            cursor: Pagination cursor from a previous response.

        Returns:
            Paginated list of LinearCycle objects.
        """
        filter_arg = ""
        if team_id:
            filter_arg = f'filter: {{ team: {{ id: {{ eq: "{team_id}" }} }} }},'
        after_arg = f', after: "{cursor}"' if cursor else ""

        query = f"""
        query {{ cycles(first: {min(limit, 250)},
            {filter_arg} orderBy: updatedAt {after_arg}) {{
            nodes {{ {CYCLE_FIELDS} }}
            pageInfo {{ hasNextPage endCursor }}
        }} }}
        """
        data = await self._graphql(query)
        cycles_data = data.get("cycles", {})
        page_info = cycles_data.get("pageInfo", {})

        return PaginatedList(
            items=[self._parse_cycle(n) for n in cycles_data.get("nodes", [])],
            page_state=PageState(
                cursor=page_info.get("endCursor"),
                has_more=page_info.get("hasNextPage", False),
            ),
        )

    @action("Get a single cycle by ID")
    async def get_cycle(self, cycle_id: str) -> LinearCycle:
        """Retrieve a Linear cycle by its UUID.

        Args:
            cycle_id: The UUID of the cycle.

        Returns:
            The requested LinearCycle.
        """
        query = f"""
        query($id: String!) {{ cycle(id: $id) {{ {CYCLE_FIELDS} }} }}
        """
        data = await self._graphql(query, variables={"id": cycle_id})
        return self._parse_cycle(data["cycle"])

    # ------------------------------------------------------------------
    # Actions -- Issue comments
    # ------------------------------------------------------------------

    @action("List comments on an issue")
    async def list_issue_comments(
        self,
        issue_id: str,
    ) -> list[LinearComment]:
        """List all comments on a Linear issue.

        Args:
            issue_id: UUID of the issue.

        Returns:
            List of LinearComment objects.
        """
        query = f"""
        query($id: String!) {{ issue(id: $id) {{
            comments {{ nodes {{ {COMMENT_FIELDS} }} }}
        }} }}
        """
        data = await self._graphql(query, variables={"id": issue_id})
        comments_data = data.get("issue", {}).get("comments", {}).get("nodes", [])
        return [self._parse_comment(c) for c in comments_data]

    # ------------------------------------------------------------------
    # Actions -- Project management (extended)
    # ------------------------------------------------------------------

    @action("Update an existing project", dangerous=True)
    async def update_project(
        self,
        project_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        state: Optional[str] = None,
    ) -> LinearProject:
        """Update fields on an existing Linear project.

        Args:
            project_id: UUID of the project to update.
            name: New name (if changing).
            description: New description (if changing).
            state: New state (e.g. ``"planned"``, ``"started"``,
                ``"paused"``, ``"completed"``, ``"canceled"``).

        Returns:
            The updated LinearProject.
        """
        inp: list[str] = []
        if name is not None:
            inp.append(f'name: "{name}"')
        if description is not None:
            esc = description.replace("\\", "\\\\").replace('"', '\\"')
            cleaned = esc.replace("\n", "\\n")
            inp.append(f'description: "{cleaned}"')
        if state is not None:
            inp.append(f'state: "{state}"')
        if not inp:
            raise ValueError("At least one field must be provided")

        query = f"""
        mutation {{ projectUpdate(id: "{project_id}",
            input: {{ {", ".join(inp)} }}) {{
            success project {{ {PROJECT_FIELDS} }}
        }} }}
        """
        data = await self._graphql(query)
        result = data.get("projectUpdate", {})
        if not result.get("success"):
            raise ValueError("Linear project update failed")
        return self._parse_project(result["project"])

    @action("Delete a project by ID", dangerous=True)
    async def delete_project(self, project_id: str) -> bool:
        """Permanently delete a Linear project.

        Args:
            project_id: UUID of the project to delete.

        Returns:
            True if the project was deleted successfully.
        """
        query = f"""
        mutation {{ projectDelete(id: "{project_id}") {{ success }} }}
        """
        data = await self._graphql(query)
        return data.get("projectDelete", {}).get("success", False)

    # ------------------------------------------------------------------
    # Actions -- Users
    # ------------------------------------------------------------------

    @action("List all users in the workspace")
    async def list_users(
        self,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> PaginatedList[LinearUser]:
        """List all users in the Linear workspace.

        Args:
            limit: Maximum results per page (max 250).
            cursor: Pagination cursor from a previous response.

        Returns:
            Paginated list of LinearUser objects.
        """
        after_arg = f', after: "{cursor}"' if cursor else ""
        query = f"""
        query {{ users(first: {min(limit, 250)} {after_arg}) {{
            nodes {{ {USER_FIELDS} }}
            pageInfo {{ hasNextPage endCursor }}
        }} }}
        """
        data = await self._graphql(query)
        users_data = data.get("users", {})
        page_info = users_data.get("pageInfo", {})

        return PaginatedList(
            items=[self._parse_user(n) for n in users_data.get("nodes", []) if n is not None],
            page_state=PageState(
                cursor=page_info.get("endCursor"),
                has_more=page_info.get("hasNextPage", False),
            ),
        )

    @action("Get a single user by ID")
    async def get_user(self, user_id: str) -> LinearUser:
        """Retrieve a Linear user by their UUID.

        Args:
            user_id: The UUID of the user.

        Returns:
            The requested LinearUser.
        """
        query = f"""
        query($id: String!) {{ user(id: $id) {{ {USER_FIELDS} }} }}
        """
        data = await self._graphql(query, variables={"id": user_id})
        user = self._parse_user(data["user"])
        if user is None:
            raise ValueError(f"User {user_id} not found")
        return user
