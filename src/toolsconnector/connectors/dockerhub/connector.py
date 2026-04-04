"""Docker Hub connector -- repos, tags, users, and organisations.

Uses the Docker Hub REST API v2 with JWT-based authentication.
Credentials should be provided as ``"username:password"`` and the
connector exchanges them for a Bearer token via ``POST /users/login``.
Pagination uses ``next`` URL in the response body.
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

from .types import DockerOrg, DockerRepo, DockerTag, DockerUser

logger = logging.getLogger("toolsconnector.dockerhub")


def _parse_repo(data: dict[str, Any]) -> DockerRepo:
    """Parse a DockerRepo from API JSON.

    Args:
        data: Raw JSON dict from the Docker Hub API.

    Returns:
        A DockerRepo instance.
    """
    return DockerRepo(
        name=data.get("name"),
        namespace=data.get("namespace"),
        repository_type=data.get("repository_type"),
        status=data.get("status", 0),
        status_description=data.get("status_description"),
        description=data.get("description"),
        is_private=data.get("is_private", False),
        star_count=data.get("star_count", 0),
        pull_count=data.get("pull_count", 0),
        last_updated=data.get("last_updated"),
        date_registered=data.get("date_registered"),
        affiliation=data.get("affiliation"),
        media_types=data.get("media_types") or [],
        content_types=data.get("content_types") or [],
        full_description=data.get("full_description"),
    )


def _parse_tag(data: dict[str, Any]) -> DockerTag:
    """Parse a DockerTag from API JSON.

    Args:
        data: Raw JSON dict from the Docker Hub API.

    Returns:
        A DockerTag instance.
    """
    return DockerTag(
        id=data.get("id"),
        name=data.get("name"),
        full_size=data.get("full_size"),
        v2=data.get("v2"),
        tag_status=data.get("tag_status"),
        tag_last_pulled=data.get("tag_last_pulled"),
        tag_last_pushed=data.get("tag_last_pushed"),
        last_updated=data.get("last_updated"),
        digest=data.get("digest"),
        images=data.get("images") or [],
        creator=data.get("creator"),
        last_updater=data.get("last_updater"),
        repository=data.get("repository"),
    )


def _parse_user(data: dict[str, Any]) -> DockerUser:
    """Parse a DockerUser from API JSON.

    Args:
        data: Raw JSON dict from the Docker Hub API.

    Returns:
        A DockerUser instance.
    """
    return DockerUser(
        id=data.get("id"),
        username=data.get("username"),
        full_name=data.get("full_name"),
        location=data.get("location"),
        company=data.get("company"),
        profile_url=data.get("profile_url"),
        date_joined=data.get("date_joined"),
        gravatar_url=data.get("gravatar_url"),
        gravatar_email=data.get("gravatar_email"),
        type=data.get("type"),
    )


def _parse_org(data: dict[str, Any]) -> DockerOrg:
    """Parse a DockerOrg from API JSON.

    Args:
        data: Raw JSON dict from the Docker Hub API.

    Returns:
        A DockerOrg instance.
    """
    return DockerOrg(
        id=data.get("id"),
        orgname=data.get("orgname"),
        full_name=data.get("full_name"),
        location=data.get("location"),
        company=data.get("company"),
        profile_url=data.get("profile_url"),
        date_joined=data.get("date_joined"),
        gravatar_url=data.get("gravatar_url"),
        gravatar_email=data.get("gravatar_email"),
        type=data.get("type"),
    )


class DockerHub(BaseConnector):
    """Connect to Docker Hub to search repos, list tags, and manage images.

    Authenticates via JWT token obtained by exchanging credentials
    (``username:password``) at the ``/users/login`` endpoint.  The
    resulting token is used as a Bearer token for subsequent requests.
    """

    name = "dockerhub"
    display_name = "Docker Hub"
    category = ConnectorCategory.DEVOPS
    protocol = ProtocolType.REST
    base_url = "https://hub.docker.com/v2"
    description = (
        "Connect to Docker Hub to search repositories, list tags, "
        "view users and organisations."
    )
    _rate_limit_config = RateLimitSpec(rate=300, period=60, burst=30)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Initialise the httpx client and obtain a JWT if credentials provided.

        Credentials format: ``"username:password"`` or a pre-existing
        Bearer token string.
        """
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        self._client = httpx.AsyncClient(
            base_url=self._base_url or self.__class__.base_url,
            headers=headers,
            timeout=self._timeout,
        )

        if self._credentials:
            cred_str = str(self._credentials)
            if ":" in cred_str:
                username, password = cred_str.split(":", 1)
                token = await self._login(username, password)
            else:
                # Assume it is already a token
                token = cred_str

            self._client.headers["Authorization"] = f"Bearer {token}"

    async def _login(self, username: str, password: str) -> str:
        """Exchange username/password for a JWT token.

        Args:
            username: Docker Hub username.
            password: Docker Hub password or personal access token.

        Returns:
            JWT token string.

        Raises:
            httpx.HTTPStatusError: On authentication failure.
        """
        resp = await self._client.post(
            "/users/login",
            json={"username": username, "password": password},
        )
        resp.raise_for_status()
        return resp.json().get("token", "")

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
        """Send an authenticated request to the Docker Hub API.

        Args:
            method: HTTP method (GET, POST).
            path: API path relative to base_url.
            params: Query parameters.
            json: JSON body for POST requests.

        Returns:
            httpx.Response object.

        Raises:
            httpx.HTTPStatusError: On 4xx/5xx responses.
        """
        resp = await self._client.request(
            method, path, params=params, json=json,
        )
        resp.raise_for_status()
        return resp

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
            cursor: Full URL from a previous response's ``next`` field.

        Returns:
            httpx.Response for the requested page.
        """
        if cursor:
            resp = await self._client.get(cursor)
            resp.raise_for_status()
            return resp
        return await self._request("GET", path, params=params)

    def _build_page_state(self, body: dict[str, Any]) -> PageState:
        """Build a PageState from Docker Hub next-URL pagination.

        Args:
            body: The response body dict.

        Returns:
            PageState with cursor set to the next URL if present.
        """
        next_url = body.get("next")
        return PageState(
            has_more=next_url is not None,
            cursor=next_url,
        )

    # ------------------------------------------------------------------
    # Actions -- Search
    # ------------------------------------------------------------------

    @action("Search Docker Hub repositories")
    async def search_repos(
        self,
        query: str,
        limit: int = 25,
        page: Optional[str] = None,
    ) -> PaginatedList[DockerRepo]:
        """Search for repositories on Docker Hub.

        Args:
            query: Search query string.
            limit: Maximum results per page (max 100).
            page: Cursor URL for the next page.

        Returns:
            Paginated list of DockerRepo objects.
        """
        capped_limit = min(limit, 100)
        params: dict[str, Any] = {
            "q": query,
            "page_size": capped_limit,
        }

        resp = await self._get_page(
            "/search/repositories/", params=params, cursor=page,
        )
        body = resp.json()
        items = [_parse_repo(r) for r in body.get("results", [])]
        ps = self._build_page_state(body)

        result = PaginatedList(
            items=items,
            page_state=ps,
            total_count=body.get("count"),
        )
        if ps.has_more:
            result._fetch_next = lambda c=ps.cursor: self.search_repos(
                query=query, limit=capped_limit, page=c,
            )
        return result

    # ------------------------------------------------------------------
    # Actions -- Repositories
    # ------------------------------------------------------------------

    @action("Get a Docker Hub repository")
    async def get_repo(
        self, namespace: str, repo: str,
    ) -> DockerRepo:
        """Retrieve a single repository.

        Args:
            namespace: Repository namespace (user or org).
            repo: Repository name.

        Returns:
            DockerRepo object.
        """
        resp = await self._request(
            "GET", f"/repositories/{namespace}/{repo}/",
        )
        return _parse_repo(resp.json())

    @action("List repositories for a Docker Hub namespace")
    async def list_repos(
        self,
        namespace: str,
        limit: int = 25,
        page: Optional[str] = None,
    ) -> PaginatedList[DockerRepo]:
        """List repositories under a namespace (user or org).

        Args:
            namespace: Repository namespace.
            limit: Maximum results per page (max 100).
            page: Cursor URL for the next page.

        Returns:
            Paginated list of DockerRepo objects.
        """
        capped_limit = min(limit, 100)
        params: dict[str, Any] = {"page_size": capped_limit}

        resp = await self._get_page(
            f"/repositories/{namespace}/", params=params, cursor=page,
        )
        body = resp.json()
        items = [_parse_repo(r) for r in body.get("results", [])]
        ps = self._build_page_state(body)

        result = PaginatedList(
            items=items,
            page_state=ps,
            total_count=body.get("count"),
        )
        if ps.has_more:
            result._fetch_next = lambda c=ps.cursor: self.list_repos(
                namespace=namespace, limit=capped_limit, page=c,
            )
        return result

    # ------------------------------------------------------------------
    # Actions -- Tags
    # ------------------------------------------------------------------

    @action("List tags for a Docker Hub repository")
    async def list_tags(
        self,
        namespace: str,
        repo: str,
        limit: int = 25,
        page: Optional[str] = None,
    ) -> PaginatedList[DockerTag]:
        """List tags for a repository.

        Args:
            namespace: Repository namespace.
            repo: Repository name.
            limit: Maximum tags per page (max 100).
            page: Cursor URL for the next page.

        Returns:
            Paginated list of DockerTag objects.
        """
        capped_limit = min(limit, 100)
        params: dict[str, Any] = {"page_size": capped_limit}

        resp = await self._get_page(
            f"/repositories/{namespace}/{repo}/tags/",
            params=params,
            cursor=page,
        )
        body = resp.json()
        items = [_parse_tag(t) for t in body.get("results", [])]
        ps = self._build_page_state(body)

        result = PaginatedList(
            items=items,
            page_state=ps,
            total_count=body.get("count"),
        )
        if ps.has_more:
            result._fetch_next = lambda c=ps.cursor: self.list_tags(
                namespace=namespace, repo=repo, limit=capped_limit, page=c,
            )
        return result

    @action("Get a single Docker Hub repository tag")
    async def get_tag(
        self, namespace: str, repo: str, tag: str,
    ) -> DockerTag:
        """Retrieve a single tag for a repository.

        Args:
            namespace: Repository namespace.
            repo: Repository name.
            tag: Tag name (e.g. ``latest``).

        Returns:
            DockerTag object.
        """
        resp = await self._request(
            "GET", f"/repositories/{namespace}/{repo}/tags/{tag}/",
        )
        return _parse_tag(resp.json())

    # ------------------------------------------------------------------
    # Actions -- Users and Orgs
    # ------------------------------------------------------------------

    @action("Get a Docker Hub user profile")
    async def get_user(self, username: str) -> DockerUser:
        """Retrieve a user profile.

        Args:
            username: Docker Hub username.

        Returns:
            DockerUser object.
        """
        resp = await self._request("GET", f"/users/{username}/")
        return _parse_user(resp.json())

    @action("List Docker Hub organisations for the authenticated user")
    async def list_orgs(self) -> list[DockerOrg]:
        """List organisations the authenticated user belongs to.

        Returns:
            List of DockerOrg objects.
        """
        resp = await self._request("GET", "/user/orgs/")
        body = resp.json()
        return [_parse_org(o) for o in body.get("results", [])]

    @action("Get a Docker Hub organisation")
    async def get_org(self, orgname: str) -> DockerOrg:
        """Retrieve an organisation profile.

        Args:
            orgname: Organisation name.

        Returns:
            DockerOrg object.
        """
        resp = await self._request("GET", f"/orgs/{orgname}/")
        return _parse_org(resp.json())
