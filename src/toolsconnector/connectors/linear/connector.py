"""Linear connector -- issues, teams, and projects via the Linear GraphQL API."""

from __future__ import annotations

import time
from typing import Any, Optional

import httpx

from toolsconnector.connectors._helpers import raise_typed_for_status
from toolsconnector.errors import (
    ConnectionError as ToolsConnectorConnectionError,
)
from toolsconnector.errors import (
    RateLimitError,
    TransportError,
)
from toolsconnector.errors import (
    TimeoutError as ToolsConnectorTimeoutError,
)
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

# Linear's GraphQL connection arguments accept a max page size of 250.
# Defensive clamp also coerces None (from ToolKit/MCP synthetic defaults)
# and rejects ≤0 values that would otherwise produce a 400 from the server.
_MAX_PAGE_SIZE = 250
_MIN_PAGE_SIZE = 1


def _clamp_page_size(limit: Optional[int], default: int = 50) -> int:
    """Clamp a paginated-action ``limit`` to Linear's accepted [1, 250] range.

    Args:
        limit: Caller-supplied page size. ``None`` (the ToolKit / MCP
            synthetic default for omitted optional kwargs) is coerced to
            ``default``.
        default: Fallback page size when ``limit is None``. Each action
            passes its own intended default so the MCP path produces the
            same result as a direct Python call without an explicit limit.
    """
    if limit is None:
        limit = default
    return max(_MIN_PAGE_SIZE, min(limit, _MAX_PAGE_SIZE))


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
    # Linear's published rate limits (2026-05, https://linear.app/developers/rate-limiting):
    #   Personal API key:  2,500 requests/hour per user
    #   OAuth application: 5,000 requests/hour per user
    #
    # We target the personal-key cap conservatively. 40 req/min × 60 = 2,400/hour,
    # leaving 100 req/hour headroom against the published 2,500 cap. burst=10
    # accommodates short fan-outs (e.g. paginating through a large project list)
    # without immediately tripping the throttle.
    _rate_limit_config = RateLimitSpec(rate=40, period=60, burst=10)

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
            toolsconnector.errors.APIError (subclass): On any non-2xx response.
                Maps to a typed exception by status: 401 -> InvalidCredentialsError
                or TokenExpiredError; 403 -> PermissionDeniedError; 404 -> NotFoundError;
                409 -> ConflictError; 400/422 -> ValidationError; 429 -> RateLimitError;
                5xx -> ServerError; other 4xx -> APIError. See
                toolsconnector.connectors._helpers.raise_typed_for_status for the full mapping.

            ValueError: If the GraphQL response contains errors.
        """
        url = f"{self._base_url}/graphql"
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        # Wrap the transport-layer httpx errors before they leave _graphql
        # so callers catching ToolsConnectorError see network failures as
        # typed exceptions instead of raw httpx classes. Mirrors the
        # transport-error mapping shipped for Notion in 0.3.7.
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    url,
                    headers=self._headers(),
                    json=payload,
                )
        except httpx.TimeoutException as e:
            raise ToolsConnectorTimeoutError(
                f"Linear API request timed out after {self._timeout}s",
                connector=self.name,
                details={
                    "timeout_seconds": self._timeout,
                    "url": url,
                    "underlying": type(e).__name__,
                },
            ) from e
        except httpx.ConnectError as e:
            raise ToolsConnectorConnectionError(
                f"Could not connect to Linear API at {self._base_url}",
                connector=self.name,
                details={"url": url, "underlying": str(e)},
            ) from e
        except httpx.TransportError as e:
            raise TransportError(
                f"Linear API transport error: {type(e).__name__}",
                connector=self.name,
                details={"url": url, "underlying": str(e)},
            ) from e

        # Linear-specific quirk: rate limits return HTTP 400 (not 429) with
        # the GraphQL errors[] envelope and extensions.code == "RATELIMITED"
        # (per Linear's published rate-limiting docs). The shared
        # raise_typed_for_status helper would map 400 -> ValidationError,
        # losing the rate-limit semantics. Detect the rate-limit envelope
        # FIRST and raise typed RateLimitError; let everything else fall
        # through to the standard status-code mapping.
        result: Any = None
        if response.status_code == 400:
            try:
                result = response.json()
            except ValueError:
                result = None
            self._maybe_raise_linear_rate_limit(response, result)

        raise_typed_for_status(response, connector=self.name)

        # Defensive: Linear normally returns JSON, but CDN 502s / empty
        # bodies can arrive as HTML or zero-length. Surface those as a
        # typed TransportError instead of letting json.JSONDecodeError
        # bubble through.
        if result is None:
            try:
                result = response.json()
            except ValueError as e:
                raise TransportError(
                    f"Linear API returned non-JSON body (HTTP {response.status_code})",
                    connector=self.name,
                    details={
                        "url": url,
                        "status_code": response.status_code,
                        "body_preview": (response.text or "")[:200],
                    },
                ) from e
        if result is None:
            # JSON `null` body — treat as empty success per the same
            # defensiveness shipped for Notion.
            return {}

        if isinstance(result, dict) and result.get("errors"):
            messages = "; ".join(e.get("message", str(e)) for e in result["errors"])
            raise ValueError(f"Linear GraphQL errors: {messages}")

        return result.get("data", {}) if isinstance(result, dict) else {}

    def _maybe_raise_linear_rate_limit(
        self,
        response: httpx.Response,
        body: Optional[Any],
    ) -> None:
        """Raise RateLimitError if the 400 response carries Linear's
        RATELIMITED error envelope.

        Linear's rate-limit semantics differ from most REST APIs:

        - Status code: **HTTP 400**, not 429.
        - Signal: ``errors[].extensions.code == "RATELIMITED"`` in the
          GraphQL response body.
        - Reset time: ``X-RateLimit-Requests-Reset`` header carries the
          epoch-milliseconds timestamp when the quota window resets.
          (Also ``X-RateLimit-Endpoint-Requests-Reset`` and
          ``X-RateLimit-Complexity-Reset`` for per-endpoint and
          complexity-based limits respectively.)

        Source: https://linear.app/developers/rate-limiting
        """
        if not isinstance(body, dict):
            return
        errors = body.get("errors") or []
        if not isinstance(errors, list):
            return
        for err in errors:
            if not isinstance(err, dict):
                continue
            extensions = err.get("extensions") or {}
            code = extensions.get("code") if isinstance(extensions, dict) else None
            if code == "RATELIMITED":
                # Prefer the most-specific reset header. Linear sends:
                #   X-RateLimit-Requests-Reset           (overall quota)
                #   X-RateLimit-Endpoint-Requests-Reset  (per-endpoint)
                #   X-RateLimit-Complexity-Reset         (complexity quota)
                reset_header = (
                    response.headers.get("X-RateLimit-Endpoint-Requests-Reset")
                    or response.headers.get("X-RateLimit-Complexity-Reset")
                    or response.headers.get("X-RateLimit-Requests-Reset")
                )
                retry_after_seconds: Optional[float] = None
                if reset_header:
                    try:
                        reset_epoch_s = int(reset_header) / 1000.0
                        retry_after_seconds = max(0.0, reset_epoch_s - time.time())
                    except (ValueError, TypeError):
                        retry_after_seconds = None
                # Build RateLimitError kwargs — only pass retry_after_seconds
                # when we actually parsed a value, otherwise let the
                # exception's own default (60s) apply.
                kwargs: dict[str, Any] = {
                    "connector": self.name,
                    "upstream_status": response.status_code,
                    "details": {
                        "linear_code": "RATELIMITED",
                        "linear_message": err.get("message", ""),
                        "reset_header": reset_header,
                    },
                }
                if retry_after_seconds is not None:
                    kwargs["retry_after_seconds"] = retry_after_seconds
                raise RateLimitError("Linear API rate limit exceeded", **kwargs)

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
        """Parse a raw Linear project node into a LinearProject model.

        Backwards-compat: the deprecated `Project.state` string field
        was replaced by a nested `Project.status` object. We derive the
        old `state` string from `status.type` so `LinearProject.state`
        keeps working. If the server still returns the old `state`
        field (during the deprecation window), prefer it for an exact
        round-trip; otherwise fall back to `status.type`.
        """
        status = data.get("status") or {}
        state = data.get("state") or status.get("type") or ""
        return LinearProject(
            id=data["id"],
            name=data.get("name", ""),
            description=data.get("description"),
            slug_id=data.get("slugId"),
            state=state,
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
        filter_obj: dict[str, Any] = {}
        if team_id:
            filter_obj["team"] = {"id": {"eq": team_id}}
        if state:
            filter_obj["state"] = {"name": {"eq": state}}

        query = f"""
        query($first: Int!, $after: String, $filter: IssueFilter) {{
            issues(first: $first, after: $after, filter: $filter,
                   orderBy: updatedAt) {{
                nodes {{ {ISSUE_FIELDS} }}
                pageInfo {{ hasNextPage endCursor }}
            }}
        }}
        """
        variables: dict[str, Any] = {"first": _clamp_page_size(limit)}
        if cursor:
            variables["after"] = cursor
        if filter_obj:
            variables["filter"] = filter_obj

        data = await self._graphql(query, variables=variables)
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
        input_obj: dict[str, Any] = {"teamId": team_id, "title": title}
        if description is not None:
            input_obj["description"] = description
        if priority is not None:
            input_obj["priority"] = priority
        if assignee_id:
            input_obj["assigneeId"] = assignee_id

        query = f"""
        mutation($input: IssueCreateInput!) {{
            issueCreate(input: $input) {{
                success issue {{ {ISSUE_FIELDS} }}
            }}
        }}
        """
        data = await self._graphql(query, variables={"input": input_obj})
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
        input_obj: dict[str, Any] = {}
        if title is not None:
            input_obj["title"] = title
        if description is not None:
            input_obj["description"] = description
        if state_id is not None:
            input_obj["stateId"] = state_id
        if priority is not None:
            input_obj["priority"] = priority
        if not input_obj:
            return await self.aget_issue(issue_id)

        query = f"""
        mutation($id: String!, $input: IssueUpdateInput!) {{
            issueUpdate(id: $id, input: $input) {{
                success issue {{ {ISSUE_FIELDS} }}
            }}
        }}
        """
        data = await self._graphql(query, variables={"id": issue_id, "input": input_obj})
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
        # Backwards-compat: `Team.private` was deprecated in favor of
        # `Team.visibility` (enum: "public" | "private" | "secret").
        # We request `visibility` and derive the old boolean. If the
        # server still returns `private` during the deprecation window,
        # prefer it for an exact round-trip.
        return [
            LinearTeam(
                id=t["id"],
                name=t.get("name", ""),
                key=t.get("key", ""),
                description=t.get("description"),
                icon=t.get("icon"),
                color=t.get("color"),
                private=(
                    t["private"] if "private" in t else (t.get("visibility", "public") != "public")
                ),
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
        gql = f"""
        query($first: Int!, $after: String) {{
            projects(first: $first, after: $after) {{
                nodes {{ {PROJECT_FIELDS} }}
                pageInfo {{ hasNextPage endCursor }}
            }}
        }}
        """
        variables: dict[str, Any] = {"first": _clamp_page_size(limit)}
        if cursor:
            variables["after"] = cursor
        data = await self._graphql(gql, variables=variables)
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
        gql = f"""
        mutation($input: CommentCreateInput!) {{
            commentCreate(input: $input) {{
                success comment {{ {COMMENT_FIELDS} }}
            }}
        }}
        """
        data = await self._graphql(
            gql,
            variables={"input": {"issueId": issue_id, "body": body}},
        )
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
        # Linear deprecated `issueSearch(query:)` — replacement is
        # `searchIssues(term:)`. Same response shape (IssueConnection),
        # only the operation name and the search-text argument changed.
        gql = f"""
        query($term: String!, $first: Int!, $after: String) {{
            searchIssues(term: $term, first: $first, after: $after) {{
                nodes {{ {ISSUE_FIELDS} }}
                pageInfo {{ hasNextPage endCursor }}
            }}
        }}
        """
        variables: dict[str, Any] = {
            "term": query,
            "first": _clamp_page_size(limit),
        }
        if cursor:
            variables["after"] = cursor
        data = await self._graphql(gql, variables=variables)
        search_data = data.get("searchIssues", {})
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
        query = """
        mutation($id: String!) {
            issueDelete(id: $id) { success }
        }
        """
        data = await self._graphql(query, variables={"id": issue_id})
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
        filter_obj: dict[str, Any] = {}
        if team_id:
            filter_obj["team"] = {"id": {"eq": team_id}}
        query = """
        query($filter: IssueLabelFilter, $first: Int!) {
            issueLabels(filter: $filter, first: $first) {
                nodes { id name color }
            }
        }
        """
        variables: dict[str, Any] = {"first": _MAX_PAGE_SIZE}
        if filter_obj:
            variables["filter"] = filter_obj
        data = await self._graphql(query, variables=variables)
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
        input_obj: dict[str, Any] = {"teamId": team_id, "name": name}
        if color:
            input_obj["color"] = color
        query = """
        mutation($input: IssueLabelCreateInput!) {
            issueLabelCreate(input: $input) {
                success issueLabel { id name color }
            }
        }
        """
        data = await self._graphql(query, variables={"input": input_obj})
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
        query = """
        query($filter: WorkflowStateFilter!, $first: Int!) {
            workflowStates(filter: $filter, first: $first) {
                nodes { id name type color position }
            }
        }
        """
        variables: dict[str, Any] = {
            "filter": {"team": {"id": {"eq": team_id}}},
            "first": 100,
        }
        data = await self._graphql(query, variables=variables)
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
        filter_obj: dict[str, Any] = {}
        if team_id:
            filter_obj["team"] = {"id": {"eq": team_id}}

        query = f"""
        query($first: Int!, $after: String, $filter: CycleFilter) {{
            cycles(first: $first, after: $after, filter: $filter,
                   orderBy: updatedAt) {{
                nodes {{ {CYCLE_FIELDS} }}
                pageInfo {{ hasNextPage endCursor }}
            }}
        }}
        """
        variables: dict[str, Any] = {"first": _clamp_page_size(limit)}
        if cursor:
            variables["after"] = cursor
        if filter_obj:
            variables["filter"] = filter_obj

        data = await self._graphql(query, variables=variables)
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
        input_obj: dict[str, Any] = {}
        if name is not None:
            input_obj["name"] = name
        if description is not None:
            input_obj["description"] = description
        if state is not None:
            input_obj["state"] = state
        if not input_obj:
            raise ValueError("At least one field must be provided")

        query = f"""
        mutation($id: String!, $input: ProjectUpdateInput!) {{
            projectUpdate(id: $id, input: $input) {{
                success project {{ {PROJECT_FIELDS} }}
            }}
        }}
        """
        data = await self._graphql(query, variables={"id": project_id, "input": input_obj})
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
        query = """
        mutation($id: String!) {
            projectDelete(id: $id) { success }
        }
        """
        data = await self._graphql(query, variables={"id": project_id})
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
        query = f"""
        query($first: Int!, $after: String) {{
            users(first: $first, after: $after) {{
                nodes {{ {USER_FIELDS} }}
                pageInfo {{ hasNextPage endCursor }}
            }}
        }}
        """
        variables: dict[str, Any] = {"first": _clamp_page_size(limit)}
        if cursor:
            variables["after"] = cursor
        data = await self._graphql(query, variables=variables)
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
