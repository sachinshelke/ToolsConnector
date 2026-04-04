"""GitHub connector — repositories, issues, PRs, commits, and code search.

Uses the GitHub REST API v2022-11-28 with personal access token auth.
Link-header pagination and X-RateLimit header parsing included.
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

from ._parsers import (
    parse_code_search_result,
    parse_comment,
    parse_commit,
    parse_issue,
    parse_link_header,
    parse_repo,
)
from .types import (
    CodeSearchResult,
    Commit,
    Comment,
    Issue,
    PullRequest,
    Repository,
)

logger = logging.getLogger("toolsconnector.github")


class GitHub(BaseConnector):
    """Connect to GitHub to manage repositories, issues, PRs, and code search.

    Supports personal access token (PAT) authentication via
    ``Authorization: Bearer <token>``.  Uses the GitHub REST API
    (version ``2022-11-28``).
    """

    name = "github"
    display_name = "GitHub"
    category = ConnectorCategory.CODE_PLATFORM
    protocol = ProtocolType.REST
    base_url = "https://api.github.com"
    description = "Connect to GitHub to manage repositories, issues, PRs, and code."
    _rate_limit_config = RateLimitSpec(rate=5000, period=3600, burst=100)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Initialise the httpx async client."""
        headers: dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
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
        """Send an authenticated request and handle errors.

        Args:
            method: HTTP method (GET, POST, etc.).
            path: API path relative to base_url.
            params: Query parameters.
            json: JSON body for POST/PATCH/PUT.

        Returns:
            httpx.Response object.

        Raises:
            httpx.HTTPStatusError: On 4xx/5xx responses.
        """
        resp = await self._client.request(
            method, path, params=params, json=json,
        )

        remaining = resp.headers.get("X-RateLimit-Remaining")
        if remaining is not None:
            logger.debug("GitHub rate-limit remaining: %s", remaining)

        resp.raise_for_status()
        return resp

    def _build_page_state(self, resp: httpx.Response) -> PageState:
        """Build a PageState from GitHub Link header pagination.

        Args:
            resp: The HTTP response to extract pagination from.

        Returns:
            PageState with cursor set to the next page URL if present.
        """
        links = parse_link_header(resp.headers.get("Link"))
        next_url = links.get("next")
        return PageState(has_more=next_url is not None, cursor=next_url)

    async def _get_page(
        self,
        path: str,
        params: Optional[dict[str, Any]] = None,
        cursor: Optional[str] = None,
    ) -> httpx.Response:
        """Fetch a page, using a cursor URL when available.

        Args:
            path: API path for the first page.
            params: Query parameters for the first page.
            cursor: Full URL from a previous Link header's ``next`` rel.

        Returns:
            httpx.Response for the requested page.
        """
        if cursor:
            resp = await self._client.get(cursor)
            resp.raise_for_status()
            return resp
        return await self._request("GET", path, params=params)

    # ------------------------------------------------------------------
    # Actions -- Repositories
    # ------------------------------------------------------------------

    @action("List repositories for a user or organisation")
    async def list_repos(
        self,
        org: Optional[str] = None,
        user: Optional[str] = None,
        limit: int = 30,
        page: Optional[str] = None,
    ) -> PaginatedList[Repository]:
        """List repositories for a user or organisation.

        Args:
            org: Organisation login name. Lists org repos when provided.
            user: Username. Lists that user's repos when provided.
                If neither is set, lists the authenticated user's repos.
            limit: Maximum repositories per page (max 100).
            page: Cursor URL for the next page (from a previous response).

        Returns:
            Paginated list of Repository objects.
        """
        if org:
            path = f"/orgs/{org}/repos"
        elif user:
            path = f"/users/{user}/repos"
        else:
            path = "/user/repos"

        resp = await self._get_page(
            path, params={"per_page": min(limit, 100)}, cursor=page,
        )
        items = [parse_repo(r) for r in resp.json()]
        ps = self._build_page_state(resp)

        result = PaginatedList(items=items, page_state=ps)
        if ps.has_more:
            result._fetch_next = lambda c=ps.cursor: self.alist_repos(page=c)
        return result

    @action("Get a single repository by owner and name")
    async def get_repo(self, owner: str, repo: str) -> Repository:
        """Retrieve a single repository.

        Args:
            owner: Repository owner (user or org login).
            repo: Repository name.

        Returns:
            Repository object.
        """
        resp = await self._request("GET", f"/repos/{owner}/{repo}")
        return parse_repo(resp.json())

    # ------------------------------------------------------------------
    # Actions -- Issues
    # ------------------------------------------------------------------

    @action("List issues for a repository")
    async def list_issues(
        self,
        owner: str,
        repo: str,
        state: Optional[str] = None,
        labels: Optional[str] = None,
        limit: int = 30,
        page: Optional[str] = None,
    ) -> PaginatedList[Issue]:
        """List issues for a repository.

        Args:
            owner: Repository owner.
            repo: Repository name.
            state: Filter by state: ``open``, ``closed``, or ``all``.
            labels: Comma-separated list of label names to filter by.
            limit: Maximum issues per page (max 100).
            page: Cursor URL for the next page.

        Returns:
            Paginated list of Issue objects.
        """
        path = f"/repos/{owner}/{repo}/issues"
        params: dict[str, Any] = {"per_page": min(limit, 100)}
        if state:
            params["state"] = state
        if labels:
            params["labels"] = labels

        resp = await self._get_page(path, params=params, cursor=page)
        items = [parse_issue(i) for i in resp.json()]
        ps = self._build_page_state(resp)

        result = PaginatedList(items=items, page_state=ps)
        if ps.has_more:
            result._fetch_next = lambda c=ps.cursor: self.alist_issues(
                owner=owner, repo=repo, page=c,
            )
        return result

    @action("Create an issue in a repository", dangerous=True)
    async def create_issue(
        self,
        owner: str,
        repo: str,
        title: str,
        body: Optional[str] = None,
        labels: Optional[list[str]] = None,
        assignees: Optional[list[str]] = None,
    ) -> Issue:
        """Create a new issue.

        Args:
            owner: Repository owner.
            repo: Repository name.
            title: Issue title.
            body: Issue body in Markdown.
            labels: List of label names to apply.
            assignees: List of usernames to assign.

        Returns:
            The created Issue object.
        """
        payload: dict[str, Any] = {"title": title}
        if body is not None:
            payload["body"] = body
        if labels:
            payload["labels"] = labels
        if assignees:
            payload["assignees"] = assignees

        resp = await self._request(
            "POST", f"/repos/{owner}/{repo}/issues", json=payload,
        )
        return parse_issue(resp.json())

    @action("Get a single issue by number")
    async def get_issue(
        self, owner: str, repo: str, issue_number: int,
    ) -> Issue:
        """Retrieve a single issue.

        Args:
            owner: Repository owner.
            repo: Repository name.
            issue_number: The issue number.

        Returns:
            Issue object.
        """
        resp = await self._request(
            "GET", f"/repos/{owner}/{repo}/issues/{issue_number}",
        )
        return parse_issue(resp.json())

    @action("Create a comment on an issue or pull request", dangerous=True)
    async def create_comment(
        self, owner: str, repo: str, issue_number: int, body: str,
    ) -> Comment:
        """Create a comment on an issue.

        Args:
            owner: Repository owner.
            repo: Repository name.
            issue_number: The issue (or PR) number to comment on.
            body: Comment body in Markdown.

        Returns:
            The created Comment object.
        """
        resp = await self._request(
            "POST",
            f"/repos/{owner}/{repo}/issues/{issue_number}/comments",
            json={"body": body},
        )
        return parse_comment(resp.json())

    # ------------------------------------------------------------------
    # Actions -- Pull Requests
    # ------------------------------------------------------------------

    @action("List pull requests for a repository")
    async def list_pull_requests(
        self,
        owner: str,
        repo: str,
        state: Optional[str] = None,
        limit: int = 30,
        page: Optional[str] = None,
    ) -> PaginatedList[PullRequest]:
        """List pull requests for a repository.

        Args:
            owner: Repository owner.
            repo: Repository name.
            state: Filter by state: ``open``, ``closed``, or ``all``.
            limit: Maximum PRs per page (max 100).
            page: Cursor URL for the next page.

        Returns:
            Paginated list of PullRequest objects.
        """
        path = f"/repos/{owner}/{repo}/pulls"
        params: dict[str, Any] = {"per_page": min(limit, 100)}
        if state:
            params["state"] = state

        resp = await self._get_page(path, params=params, cursor=page)
        items = [PullRequest.from_api(pr) for pr in resp.json()]
        ps = self._build_page_state(resp)

        result = PaginatedList(items=items, page_state=ps)
        if ps.has_more:
            result._fetch_next = lambda c=ps.cursor: self.alist_pull_requests(
                owner=owner, repo=repo, page=c,
            )
        return result

    @action("Get a single pull request by number")
    async def get_pull_request(
        self, owner: str, repo: str, pr_number: int,
    ) -> PullRequest:
        """Retrieve a single pull request with full details.

        Args:
            owner: Repository owner.
            repo: Repository name.
            pr_number: The pull request number.

        Returns:
            PullRequest object with merge/diff statistics.
        """
        resp = await self._request(
            "GET", f"/repos/{owner}/{repo}/pulls/{pr_number}",
        )
        return PullRequest.from_api(resp.json())

    # ------------------------------------------------------------------
    # Actions -- Commits
    # ------------------------------------------------------------------

    @action("List commits for a repository")
    async def list_commits(
        self,
        owner: str,
        repo: str,
        sha: Optional[str] = None,
        limit: int = 30,
        page: Optional[str] = None,
    ) -> PaginatedList[Commit]:
        """List commits for a repository.

        Args:
            owner: Repository owner.
            repo: Repository name.
            sha: Branch name or commit SHA to start listing from.
            limit: Maximum commits per page (max 100).
            page: Cursor URL for the next page.

        Returns:
            Paginated list of Commit objects.
        """
        path = f"/repos/{owner}/{repo}/commits"
        params: dict[str, Any] = {"per_page": min(limit, 100)}
        if sha:
            params["sha"] = sha

        resp = await self._get_page(path, params=params, cursor=page)
        items = [parse_commit(c) for c in resp.json()]
        ps = self._build_page_state(resp)

        result = PaginatedList(items=items, page_state=ps)
        if ps.has_more:
            result._fetch_next = lambda c=ps.cursor: self.alist_commits(
                owner=owner, repo=repo, page=c,
            )
        return result

    # ------------------------------------------------------------------
    # Actions -- Code Search
    # ------------------------------------------------------------------

    @action("Search code across GitHub repositories")
    async def search_code(
        self,
        query: str,
        limit: int = 30,
        page: Optional[str] = None,
    ) -> PaginatedList[CodeSearchResult]:
        """Search for code across GitHub using the search API.

        Args:
            query: GitHub code search query (e.g. ``"addClass in:file
                language:js repo:jquery/jquery"``).
            limit: Maximum results per page (max 100).
            page: Cursor URL for the next page.

        Returns:
            Paginated list of CodeSearchResult objects.
        """
        params: dict[str, Any] = {"q": query, "per_page": min(limit, 100)}

        resp = await self._get_page("/search/code", params=params, cursor=page)
        data = resp.json()

        items = [parse_code_search_result(i) for i in data.get("items", [])]
        ps = self._build_page_state(resp)

        result = PaginatedList(
            items=items,
            page_state=ps,
            total_count=data.get("total_count", 0),
        )
        if ps.has_more:
            result._fetch_next = lambda c=ps.cursor: self.asearch_code(
                query=query, page=c,
            )
        return result
