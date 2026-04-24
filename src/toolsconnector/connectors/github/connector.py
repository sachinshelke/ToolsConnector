"""GitHub connector — full GitHub REST API coverage.

Covers repositories, issues, pull requests, commits, branches, releases,
file content, labels, workflows, gists, code search, and user management.

Uses the GitHub REST API v2022-11-28 with personal access token auth.
Link-header pagination and X-RateLimit header parsing included.
"""

from __future__ import annotations

import logging
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

from ._parsers import (
    parse_branch,
    parse_code_search_result,
    parse_comment,
    parse_commit,
    parse_file_content,
    parse_gist,
    parse_issue,
    parse_link_header,
    parse_release,
    parse_repo,
    parse_workflow,
    parse_workflow_run,
)
from .types import (
    Branch,
    CodeSearchResult,
    Comment,
    Commit,
    FileContent,
    GitHubGist,
    Issue,
    PullRequest,
    Release,
    Repository,
    Workflow,
    WorkflowRun,
)

logger = logging.getLogger("toolsconnector.github")


class GitHub(BaseConnector):
    """Connect to GitHub with full REST API coverage.

    Supports personal access token (PAT) authentication via
    ``Authorization: Bearer <token>``.  Uses the GitHub REST API
    (version ``2022-11-28``).

    Covers: repositories, issues, pull requests, commits, branches,
    releases, file content, labels, workflows, gists, and search.
    """

    name = "github"
    display_name = "GitHub"
    category = ConnectorCategory.CODE_PLATFORM
    protocol = ProtocolType.REST
    base_url = "https://api.github.com"
    description = (
        "Connect to GitHub — manage repositories, issues, PRs, branches, "
        "releases, workflows, files, gists, and more."
    )
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
        """Send an authenticated request and handle errors."""
        resp = await self._client.request(
            method,
            path,
            params=params,
            json=json,
        )
        remaining = resp.headers.get("X-RateLimit-Remaining")
        if remaining is not None:
            logger.debug("GitHub rate-limit remaining: %s", remaining)
        raise_typed_for_status(resp, connector=self.name)
        return resp

    def _build_page_state(self, resp: httpx.Response) -> PageState:
        """Build a PageState from GitHub Link header pagination."""
        links = parse_link_header(resp.headers.get("Link"))
        next_url = links.get("next")
        return PageState(has_more=next_url is not None, cursor=next_url)

    async def _get_page(
        self,
        path: str,
        params: Optional[dict[str, Any]] = None,
        cursor: Optional[str] = None,
    ) -> httpx.Response:
        """Fetch a page, using a cursor URL when available."""
        if cursor:
            resp = await self._client.get(cursor)
            raise_typed_for_status(resp, connector=self.name)
            return resp
        return await self._request("GET", path, params=params)

    # ======================================================================
    # REPOSITORIES
    # ======================================================================

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
            path,
            params={"per_page": min(limit, 100)},
            cursor=page,
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

    @action("Create a new repository", dangerous=True)
    async def create_repo(
        self,
        name: str,
        description: Optional[str] = None,
        private: bool = False,
        auto_init: bool = False,
        org: Optional[str] = None,
    ) -> Repository:
        """Create a new repository for the authenticated user or an org.

        Args:
            name: Repository name.
            description: Short description.
            private: If ``True``, create a private repository.
            auto_init: If ``True``, initialize with a README.
            org: Create under this organisation instead of the user.

        Returns:
            The created Repository object.
        """
        payload: dict[str, Any] = {
            "name": name,
            "private": private,
            "auto_init": auto_init,
        }
        if description:
            payload["description"] = description

        path = f"/orgs/{org}/repos" if org else "/user/repos"
        resp = await self._request("POST", path, json=payload)
        return parse_repo(resp.json())

    @action("Fork a repository", dangerous=True)
    async def fork_repo(
        self,
        owner: str,
        repo: str,
        organization: Optional[str] = None,
    ) -> Repository:
        """Fork a repository to your account or an organisation.

        Args:
            owner: Source repository owner.
            repo: Source repository name.
            organization: Optional org to fork into.

        Returns:
            The forked Repository object.
        """
        payload: dict[str, Any] = {}
        if organization:
            payload["organization"] = organization

        resp = await self._request(
            "POST",
            f"/repos/{owner}/{repo}/forks",
            json=payload,
        )
        return parse_repo(resp.json())

    # ======================================================================
    # ISSUES
    # ======================================================================

    @action("List issues for a repository")
    async def list_issues(
        self,
        owner: str,
        repo: str,
        state: Optional[str] = None,
        labels: Optional[str] = None,
        assignee: Optional[str] = None,
        limit: int = 30,
        page: Optional[str] = None,
    ) -> PaginatedList[Issue]:
        """List issues for a repository.

        Args:
            owner: Repository owner.
            repo: Repository name.
            state: Filter by state: ``open``, ``closed``, or ``all``.
            labels: Comma-separated list of label names to filter by.
            assignee: Filter by assignee username, or ``none`` / ``*``.
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
        if assignee:
            params["assignee"] = assignee

        resp = await self._get_page(path, params=params, cursor=page)
        items = [parse_issue(i) for i in resp.json()]
        ps = self._build_page_state(resp)

        result = PaginatedList(items=items, page_state=ps)
        if ps.has_more:
            result._fetch_next = lambda c=ps.cursor: self.alist_issues(
                owner=owner,
                repo=repo,
                page=c,
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
            "POST",
            f"/repos/{owner}/{repo}/issues",
            json=payload,
        )
        return parse_issue(resp.json())

    @action("Get a single issue by number")
    async def get_issue(
        self,
        owner: str,
        repo: str,
        issue_number: int,
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
            "GET",
            f"/repos/{owner}/{repo}/issues/{issue_number}",
        )
        return parse_issue(resp.json())

    @action("Update an existing issue")
    async def update_issue(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        title: Optional[str] = None,
        body: Optional[str] = None,
        state: Optional[str] = None,
        labels: Optional[list[str]] = None,
        assignees: Optional[list[str]] = None,
    ) -> Issue:
        """Update an existing issue's title, body, state, labels, or assignees.

        Args:
            owner: Repository owner.
            repo: Repository name.
            issue_number: The issue number.
            title: New title.
            body: New body in Markdown.
            state: New state: ``open`` or ``closed``.
            labels: Replace all labels with this list.
            assignees: Replace all assignees with this list.

        Returns:
            The updated Issue object.
        """
        payload: dict[str, Any] = {}
        if title is not None:
            payload["title"] = title
        if body is not None:
            payload["body"] = body
        if state is not None:
            payload["state"] = state
        if labels is not None:
            payload["labels"] = labels
        if assignees is not None:
            payload["assignees"] = assignees

        resp = await self._request(
            "PATCH",
            f"/repos/{owner}/{repo}/issues/{issue_number}",
            json=payload,
        )
        return parse_issue(resp.json())

    @action("Add labels to an issue")
    async def add_labels(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        labels: list[str],
    ) -> list[dict[str, Any]]:
        """Add labels to an issue (without removing existing ones).

        Args:
            owner: Repository owner.
            repo: Repository name.
            issue_number: The issue number.
            labels: List of label names to add.

        Returns:
            List of all labels now on the issue.
        """
        resp = await self._request(
            "POST",
            f"/repos/{owner}/{repo}/issues/{issue_number}/labels",
            json={"labels": labels},
        )
        return resp.json()

    @action("Remove a label from an issue", dangerous=True)
    async def remove_label(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        label_name: str,
    ) -> None:
        """Remove a single label from an issue.

        Args:
            owner: Repository owner.
            repo: Repository name.
            issue_number: The issue number.
            label_name: Name of the label to remove.
        """
        await self._request(
            "DELETE",
            f"/repos/{owner}/{repo}/issues/{issue_number}/labels/{label_name}",
        )

    # ======================================================================
    # COMMENTS
    # ======================================================================

    @action("Create a comment on an issue or pull request", dangerous=True)
    async def create_comment(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        body: str,
    ) -> Comment:
        """Create a comment on an issue or PR.

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

    @action("List comments on an issue")
    async def list_comments(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        limit: int = 30,
        page: Optional[str] = None,
    ) -> PaginatedList[Comment]:
        """List comments on an issue or pull request.

        Args:
            owner: Repository owner.
            repo: Repository name.
            issue_number: The issue (or PR) number.
            limit: Maximum comments per page (max 100).
            page: Cursor URL for the next page.

        Returns:
            Paginated list of Comment objects.
        """
        path = f"/repos/{owner}/{repo}/issues/{issue_number}/comments"
        resp = await self._get_page(
            path,
            params={"per_page": min(limit, 100)},
            cursor=page,
        )
        items = [parse_comment(c) for c in resp.json()]
        ps = self._build_page_state(resp)
        result = PaginatedList(items=items, page_state=ps)
        if ps.has_more:
            result._fetch_next = lambda c=ps.cursor: self.alist_comments(
                owner=owner,
                repo=repo,
                issue_number=issue_number,
                page=c,
            )
        return result

    # ======================================================================
    # PULL REQUESTS
    # ======================================================================

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
                owner=owner,
                repo=repo,
                page=c,
            )
        return result

    @action("Get a single pull request by number")
    async def get_pull_request(
        self,
        owner: str,
        repo: str,
        pr_number: int,
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
            "GET",
            f"/repos/{owner}/{repo}/pulls/{pr_number}",
        )
        return PullRequest.from_api(resp.json())

    @action("Create a pull request", dangerous=True)
    async def create_pull_request(
        self,
        owner: str,
        repo: str,
        title: str,
        head: str,
        base: str,
        body: Optional[str] = None,
        draft: bool = False,
    ) -> PullRequest:
        """Create a new pull request.

        Args:
            owner: Repository owner.
            repo: Repository name.
            title: PR title.
            head: Branch (or ``user:branch``) containing your changes.
            base: Branch you want to merge into (e.g. ``main``).
            body: PR description in Markdown.
            draft: If ``True``, create as a draft PR.

        Returns:
            The created PullRequest object.
        """
        payload: dict[str, Any] = {
            "title": title,
            "head": head,
            "base": base,
            "draft": draft,
        }
        if body is not None:
            payload["body"] = body

        resp = await self._request(
            "POST",
            f"/repos/{owner}/{repo}/pulls",
            json=payload,
        )
        return PullRequest.from_api(resp.json())

    @action("Merge a pull request", dangerous=True)
    async def merge_pull_request(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        merge_method: str = "merge",
        commit_title: Optional[str] = None,
        commit_message: Optional[str] = None,
    ) -> dict[str, Any]:
        """Merge a pull request.

        Args:
            owner: Repository owner.
            repo: Repository name.
            pr_number: The pull request number.
            merge_method: ``merge``, ``squash``, or ``rebase``.
            commit_title: Custom merge commit title.
            commit_message: Custom merge commit message.

        Returns:
            Dict with ``sha``, ``merged``, and ``message`` keys.
        """
        payload: dict[str, Any] = {"merge_method": merge_method}
        if commit_title:
            payload["commit_title"] = commit_title
        if commit_message:
            payload["commit_message"] = commit_message

        resp = await self._request(
            "PUT",
            f"/repos/{owner}/{repo}/pulls/{pr_number}/merge",
            json=payload,
        )
        return resp.json()

    # ======================================================================
    # COMMITS
    # ======================================================================

    @action("List commits for a repository")
    async def list_commits(
        self,
        owner: str,
        repo: str,
        sha: Optional[str] = None,
        path: Optional[str] = None,
        author: Optional[str] = None,
        limit: int = 30,
        page: Optional[str] = None,
    ) -> PaginatedList[Commit]:
        """List commits for a repository.

        Args:
            owner: Repository owner.
            repo: Repository name.
            sha: Branch name or commit SHA to start listing from.
            path: Only commits containing this file path.
            author: GitHub login or email to filter by.
            limit: Maximum commits per page (max 100).
            page: Cursor URL for the next page.

        Returns:
            Paginated list of Commit objects.
        """
        api_path = f"/repos/{owner}/{repo}/commits"
        params: dict[str, Any] = {"per_page": min(limit, 100)}
        if sha:
            params["sha"] = sha
        if path:
            params["path"] = path
        if author:
            params["author"] = author

        resp = await self._get_page(api_path, params=params, cursor=page)
        items = [parse_commit(c) for c in resp.json()]
        ps = self._build_page_state(resp)

        result = PaginatedList(items=items, page_state=ps)
        if ps.has_more:
            result._fetch_next = lambda c=ps.cursor: self.alist_commits(
                owner=owner,
                repo=repo,
                page=c,
            )
        return result

    # ======================================================================
    # BRANCHES
    # ======================================================================

    @action("List branches in a repository")
    async def list_branches(
        self,
        owner: str,
        repo: str,
        limit: int = 30,
        page: Optional[str] = None,
    ) -> PaginatedList[Branch]:
        """List branches in a repository.

        Args:
            owner: Repository owner.
            repo: Repository name.
            limit: Maximum branches per page (max 100).
            page: Cursor URL for the next page.

        Returns:
            Paginated list of Branch objects.
        """
        resp = await self._get_page(
            f"/repos/{owner}/{repo}/branches",
            params={"per_page": min(limit, 100)},
            cursor=page,
        )
        items = [parse_branch(b) for b in resp.json()]
        ps = self._build_page_state(resp)
        result = PaginatedList(items=items, page_state=ps)
        if ps.has_more:
            result._fetch_next = lambda c=ps.cursor: self.alist_branches(
                owner=owner,
                repo=repo,
                page=c,
            )
        return result

    @action("Get a single branch")
    async def get_branch(
        self,
        owner: str,
        repo: str,
        branch: str,
    ) -> Branch:
        """Get details for a single branch including protection status.

        Args:
            owner: Repository owner.
            repo: Repository name.
            branch: Branch name.

        Returns:
            Branch object.
        """
        resp = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/branches/{branch}",
        )
        return parse_branch(resp.json())

    # ======================================================================
    # RELEASES
    # ======================================================================

    @action("List releases for a repository")
    async def list_releases(
        self,
        owner: str,
        repo: str,
        limit: int = 30,
        page: Optional[str] = None,
    ) -> PaginatedList[Release]:
        """List releases for a repository (newest first).

        Args:
            owner: Repository owner.
            repo: Repository name.
            limit: Maximum releases per page (max 100).
            page: Cursor URL for the next page.

        Returns:
            Paginated list of Release objects.
        """
        resp = await self._get_page(
            f"/repos/{owner}/{repo}/releases",
            params={"per_page": min(limit, 100)},
            cursor=page,
        )
        items = [parse_release(r) for r in resp.json()]
        ps = self._build_page_state(resp)
        result = PaginatedList(items=items, page_state=ps)
        if ps.has_more:
            result._fetch_next = lambda c=ps.cursor: self.alist_releases(
                owner=owner,
                repo=repo,
                page=c,
            )
        return result

    @action("Get the latest release")
    async def get_latest_release(
        self,
        owner: str,
        repo: str,
    ) -> Release:
        """Get the latest published release (excludes drafts and prereleases).

        Args:
            owner: Repository owner.
            repo: Repository name.

        Returns:
            The latest Release object.
        """
        resp = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/releases/latest",
        )
        return parse_release(resp.json())

    @action("Create a release", dangerous=True)
    async def create_release(
        self,
        owner: str,
        repo: str,
        tag_name: str,
        name: Optional[str] = None,
        body: Optional[str] = None,
        draft: bool = False,
        prerelease: bool = False,
        target_commitish: Optional[str] = None,
    ) -> Release:
        """Create a new release on a repository.

        Args:
            owner: Repository owner.
            repo: Repository name.
            tag_name: Git tag for the release.
            name: Release title.
            body: Release notes in Markdown.
            draft: If ``True``, create as a draft.
            prerelease: If ``True``, mark as pre-release.
            target_commitish: Branch or commit SHA to tag (defaults
                to default branch).

        Returns:
            The created Release object.
        """
        payload: dict[str, Any] = {
            "tag_name": tag_name,
            "draft": draft,
            "prerelease": prerelease,
        }
        if name:
            payload["name"] = name
        if body:
            payload["body"] = body
        if target_commitish:
            payload["target_commitish"] = target_commitish

        resp = await self._request(
            "POST",
            f"/repos/{owner}/{repo}/releases",
            json=payload,
        )
        return parse_release(resp.json())

    # ======================================================================
    # FILE CONTENT
    # ======================================================================

    @action("Get file or directory contents from a repository")
    async def get_content(
        self,
        owner: str,
        repo: str,
        path: str,
        ref: Optional[str] = None,
    ) -> FileContent:
        """Get the contents of a file or directory in a repository.

        For files, returns base64-encoded ``content``. For directories,
        returns a listing (use ``type`` field to distinguish).

        Args:
            owner: Repository owner.
            repo: Repository name.
            path: Path to file or directory (e.g. ``src/main.py``).
            ref: Branch, tag, or commit SHA (defaults to default branch).

        Returns:
            FileContent object.
        """
        params: dict[str, Any] = {}
        if ref:
            params["ref"] = ref

        resp = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/contents/{path}",
            params=params,
        )
        return parse_file_content(resp.json())

    @action("Create or update a file in a repository", dangerous=True)
    async def create_or_update_file(
        self,
        owner: str,
        repo: str,
        path: str,
        content: str,
        message: str,
        sha: Optional[str] = None,
        branch: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create or update a file in a repository.

        To update an existing file, you must provide its current ``sha``.
        To create a new file, omit ``sha``.

        Args:
            owner: Repository owner.
            repo: Repository name.
            path: Path for the file (e.g. ``docs/README.md``).
            content: File content, **base64-encoded**.
            message: Commit message.
            sha: Current blob SHA of the file (required for updates).
            branch: Branch to commit to (defaults to default branch).

        Returns:
            Dict with ``content`` and ``commit`` keys from the API.
        """
        payload: dict[str, Any] = {
            "message": message,
            "content": content,
        }
        if sha:
            payload["sha"] = sha
        if branch:
            payload["branch"] = branch

        resp = await self._request(
            "PUT",
            f"/repos/{owner}/{repo}/contents/{path}",
            json=payload,
        )
        return resp.json()

    @action("Delete a file from a repository", dangerous=True)
    async def delete_file(
        self,
        owner: str,
        repo: str,
        path: str,
        sha: str,
        message: str,
        branch: Optional[str] = None,
    ) -> dict[str, Any]:
        """Delete a file from a repository.

        Args:
            owner: Repository owner.
            repo: Repository name.
            path: Path to the file to delete.
            sha: Current blob SHA of the file (required).
            message: Commit message.
            branch: Branch to commit to.

        Returns:
            Dict with ``commit`` key from the API.
        """
        payload: dict[str, Any] = {
            "message": message,
            "sha": sha,
        }
        if branch:
            payload["branch"] = branch

        resp = await self._request(
            "DELETE",
            f"/repos/{owner}/{repo}/contents/{path}",
            json=payload,
        )
        return resp.json()

    # ======================================================================
    # WORKFLOWS (GitHub Actions)
    # ======================================================================

    @action("List workflows in a repository")
    async def list_workflows(
        self,
        owner: str,
        repo: str,
        limit: int = 30,
        page: Optional[str] = None,
    ) -> PaginatedList[Workflow]:
        """List GitHub Actions workflows defined in a repository.

        Args:
            owner: Repository owner.
            repo: Repository name.
            limit: Maximum workflows per page (max 100).
            page: Cursor URL for the next page.

        Returns:
            Paginated list of Workflow objects.
        """
        resp = await self._get_page(
            f"/repos/{owner}/{repo}/actions/workflows",
            params={"per_page": min(limit, 100)},
            cursor=page,
        )
        data = resp.json()
        items = [parse_workflow(w) for w in data.get("workflows", [])]
        ps = self._build_page_state(resp)
        result = PaginatedList(
            items=items,
            page_state=ps,
            total_count=data.get("total_count", 0),
        )
        if ps.has_more:
            result._fetch_next = lambda c=ps.cursor: self.alist_workflows(
                owner=owner,
                repo=repo,
                page=c,
            )
        return result

    @action("List workflow runs for a repository")
    async def list_workflow_runs(
        self,
        owner: str,
        repo: str,
        workflow_id: Optional[int] = None,
        branch: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 30,
        page: Optional[str] = None,
    ) -> PaginatedList[WorkflowRun]:
        """List GitHub Actions workflow runs.

        Args:
            owner: Repository owner.
            repo: Repository name.
            workflow_id: Filter to a specific workflow. If omitted,
                returns runs for all workflows.
            branch: Filter by branch name.
            status: Filter by status: ``queued``, ``in_progress``,
                ``completed``, ``success``, ``failure``, etc.
            limit: Maximum runs per page (max 100).
            page: Cursor URL for the next page.

        Returns:
            Paginated list of WorkflowRun objects.
        """
        if workflow_id:
            path = f"/repos/{owner}/{repo}/actions/workflows/{workflow_id}/runs"
        else:
            path = f"/repos/{owner}/{repo}/actions/runs"

        params: dict[str, Any] = {"per_page": min(limit, 100)}
        if branch:
            params["branch"] = branch
        if status:
            params["status"] = status

        resp = await self._get_page(path, params=params, cursor=page)
        data = resp.json()
        items = [parse_workflow_run(r) for r in data.get("workflow_runs", [])]
        ps = self._build_page_state(resp)
        result = PaginatedList(
            items=items,
            page_state=ps,
            total_count=data.get("total_count", 0),
        )
        if ps.has_more:
            result._fetch_next = lambda c=ps.cursor: self.alist_workflow_runs(
                owner=owner,
                repo=repo,
                page=c,
            )
        return result

    @action("Trigger a workflow dispatch", dangerous=True)
    async def trigger_workflow(
        self,
        owner: str,
        repo: str,
        workflow_id: int,
        ref: str = "main",
        inputs: Optional[dict[str, str]] = None,
    ) -> None:
        """Trigger a GitHub Actions workflow via the workflow_dispatch event.

        Args:
            owner: Repository owner.
            repo: Repository name.
            workflow_id: Workflow ID or filename (e.g. ``ci.yml``).
            ref: Git ref (branch or tag) to run the workflow on.
            inputs: Optional workflow input parameters.
        """
        payload: dict[str, Any] = {"ref": ref}
        if inputs:
            payload["inputs"] = inputs

        await self._request(
            "POST",
            f"/repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches",
            json=payload,
        )

    # ======================================================================
    # GISTS
    # ======================================================================

    @action("List gists for the authenticated user")
    async def list_gists(
        self,
        limit: int = 30,
        page: Optional[str] = None,
    ) -> PaginatedList[GitHubGist]:
        """List gists for the authenticated user.

        Args:
            limit: Maximum gists per page (max 100).
            page: Cursor URL for the next page.

        Returns:
            Paginated list of GitHubGist objects.
        """
        resp = await self._get_page(
            "/gists",
            params={"per_page": min(limit, 100)},
            cursor=page,
        )
        items = [parse_gist(g) for g in resp.json()]
        ps = self._build_page_state(resp)
        result = PaginatedList(items=items, page_state=ps)
        if ps.has_more:
            result._fetch_next = lambda c=ps.cursor: self.alist_gists(page=c)
        return result

    @action("Create a gist", dangerous=True)
    async def create_gist(
        self,
        files: dict[str, str],
        description: Optional[str] = None,
        public: bool = True,
    ) -> GitHubGist:
        """Create a new gist with one or more files.

        Args:
            files: Mapping of filename to file content.
                E.g. ``{"hello.py": "print('hello')"}``.
            description: Gist description.
            public: If ``True``, create a public gist.

        Returns:
            The created GitHubGist object.
        """
        payload: dict[str, Any] = {
            "files": {name: {"content": content} for name, content in files.items()},
            "public": public,
        }
        if description:
            payload["description"] = description

        resp = await self._request("POST", "/gists", json=payload)
        return parse_gist(resp.json())

    # ======================================================================
    # SEARCH
    # ======================================================================

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
                query=query,
                page=c,
            )
        return result

    @action("Search repositories on GitHub")
    async def search_repos(
        self,
        query: str,
        sort: Optional[str] = None,
        order: str = "desc",
        limit: int = 30,
        page: Optional[str] = None,
    ) -> PaginatedList[Repository]:
        """Search for repositories on GitHub.

        Args:
            query: Search query (e.g. ``"language:python stars:>1000"``).
            sort: Sort field: ``stars``, ``forks``, ``help-wanted-issues``,
                or ``updated``. Defaults to best match.
            order: Sort order: ``asc`` or ``desc``.
            limit: Maximum results per page (max 100).
            page: Cursor URL for the next page.

        Returns:
            Paginated list of Repository objects.
        """
        params: dict[str, Any] = {
            "q": query,
            "order": order,
            "per_page": min(limit, 100),
        }
        if sort:
            params["sort"] = sort

        resp = await self._get_page("/search/repositories", params=params, cursor=page)
        data = resp.json()
        items = [parse_repo(r) for r in data.get("items", [])]
        ps = self._build_page_state(resp)
        result = PaginatedList(
            items=items,
            page_state=ps,
            total_count=data.get("total_count", 0),
        )
        if ps.has_more:
            result._fetch_next = lambda c=ps.cursor: self.asearch_repos(
                query=query,
                page=c,
            )
        return result

    @action("Search issues and pull requests on GitHub")
    async def search_issues(
        self,
        query: str,
        sort: Optional[str] = None,
        order: str = "desc",
        limit: int = 30,
        page: Optional[str] = None,
    ) -> PaginatedList[Issue]:
        """Search for issues and pull requests across GitHub.

        Args:
            query: Search query (e.g. ``"is:issue is:open label:bug"``).
            sort: Sort field: ``comments``, ``reactions``, ``created``,
                or ``updated``. Defaults to best match.
            order: Sort order: ``asc`` or ``desc``.
            limit: Maximum results per page (max 100).
            page: Cursor URL for the next page.

        Returns:
            Paginated list of Issue objects.
        """
        params: dict[str, Any] = {
            "q": query,
            "order": order,
            "per_page": min(limit, 100),
        }
        if sort:
            params["sort"] = sort

        resp = await self._get_page(
            "/search/issues",
            params=params,
            cursor=page,
        )
        data = resp.json()
        items = [parse_issue(i) for i in data.get("items", [])]
        ps = self._build_page_state(resp)
        result = PaginatedList(
            items=items,
            page_state=ps,
            total_count=data.get("total_count", 0),
        )
        if ps.has_more:
            result._fetch_next = lambda c=ps.cursor: self.asearch_issues(
                query=query,
                page=c,
            )
        return result

    # ======================================================================
    # USER / RATE LIMIT
    # ======================================================================

    @action("Get the authenticated user's profile")
    async def get_authenticated_user(self) -> dict[str, Any]:
        """Get profile information for the authenticated user.

        Returns:
            Dict with user profile fields (login, name, email, bio,
            public_repos, followers, etc.).
        """
        resp = await self._request("GET", "/user")
        return resp.json()

    @action("Get the current rate limit status")
    async def get_rate_limit(self) -> dict[str, Any]:
        """Check the current API rate limit status.

        Returns:
            Dict with ``resources`` (core, search, graphql limits)
            and ``rate`` (overall) sections.
        """
        resp = await self._request("GET", "/rate_limit")
        return resp.json()

    @action("Star a repository", dangerous=True)
    async def star_repo(self, owner: str, repo: str) -> None:
        """Star a repository for the authenticated user.

        Args:
            owner: Repository owner.
            repo: Repository name.
        """
        await self._request("PUT", f"/user/starred/{owner}/{repo}")

    @action("Unstar a repository", dangerous=True)
    async def unstar_repo(self, owner: str, repo: str) -> None:
        """Remove a star from a repository.

        Args:
            owner: Repository owner.
            repo: Repository name.
        """
        await self._request("DELETE", f"/user/starred/{owner}/{repo}")
