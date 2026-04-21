"""Auth0 connector -- manage users, connections, and roles via the Management API.

Uses the Auth0 Management API v2.  Credentials should be
``"client_id:client_secret:domain"`` format, where domain includes the
full host (e.g. ``"dev-abc123.us.auth0.com"``).

The connector automatically obtains a Management API access token during
``_setup()`` using the client_credentials grant.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from toolsconnector.errors import (
    APIError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)
from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import (
    ConnectorCategory,
    ProtocolType,
    RateLimitSpec,
)
from toolsconnector.types import PageState, PaginatedList

from .types import Auth0Connection, Auth0Role, Auth0User

logger = logging.getLogger("toolsconnector.auth0")


class Auth0(BaseConnector):
    """Connect to Auth0 to manage users, connections, and roles.

    Credentials format: ``"client_id:client_secret:domain"``
    where domain is the full Auth0 tenant domain
    (e.g. ``dev-abc123.us.auth0.com``).

    The connector obtains a Management API token automatically during
    setup using the ``client_credentials`` grant.
    """

    name = "auth0"
    display_name = "Auth0"
    category = ConnectorCategory.SECURITY
    protocol = ProtocolType.REST
    base_url = "https://{domain}/api/v2"
    description = (
        "Connect to Auth0 identity platform to manage users, "
        "connections, and role-based access control."
    )
    _rate_limit_config = RateLimitSpec(rate=10, period=1, burst=30)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Parse credentials, obtain management token, and initialise client."""
        creds = str(self._credentials)
        parts = creds.split(":", 2)
        if len(parts) < 3:
            raise ValueError("Auth0 credentials must be 'client_id:client_secret:domain'")

        self._client_id = parts[0]
        self._client_secret = parts[1]
        self._domain = parts[2]
        resolved_url = f"https://{self._domain}/api/v2"

        # Obtain management API token
        token_url = f"https://{self._domain}/oauth/token"
        async with httpx.AsyncClient(timeout=self._timeout) as tmp_client:
            token_resp = await tmp_client.post(
                token_url,
                json={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "audience": f"https://{self._domain}/api/v2/",
                    "grant_type": "client_credentials",
                },
            )
            if token_resp.status_code >= 400:
                raise APIError(
                    f"Auth0 token exchange failed ({token_resp.status_code}): {token_resp.text}",
                    connector="auth0",
                    action="_setup",
                    upstream_status=token_resp.status_code,
                )
            token_data = token_resp.json()
            self._access_token = token_data["access_token"]

        self._client = httpx.AsyncClient(
            base_url=resolved_url,
            headers={
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json",
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
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[dict[str, Any]] = None,
    ) -> Any:
        """Execute an HTTP request against the Auth0 Management API.

        Args:
            method: HTTP method (GET, POST, PATCH, DELETE).
            path: API path relative to base URL.
            params: URL query parameters.
            json_body: JSON request body.

        Returns:
            Parsed JSON response.

        Raises:
            NotFoundError: If the resource is not found (404).
            RateLimitError: If rate limited (429).
            ValidationError: If the request is invalid (400/422).
            APIError: For any other API error.
        """
        kwargs: dict[str, Any] = {}
        if params:
            kwargs["params"] = params
        if json_body is not None:
            kwargs["json"] = json_body

        response = await self._client.request(method, path, **kwargs)

        if response.status_code == 204:
            return None

        if response.status_code >= 400:
            try:
                err_body = response.json()
            except Exception:
                err_body = {"message": response.text}

            err_msg_str = err_body.get(
                "message", err_body.get("error_description", "Unknown error")
            )
            err_msg = f"Auth0 API error ({response.status_code}): {err_msg_str}"

            if response.status_code == 404:
                raise NotFoundError(
                    err_msg,
                    connector="auth0",
                    action=path,
                    details=err_body,
                )
            if response.status_code == 429:
                retry_after = float(response.headers.get("x-ratelimit-reset", "60"))
                raise RateLimitError(
                    err_msg,
                    connector="auth0",
                    action=path,
                    retry_after_seconds=retry_after,
                )
            if response.status_code in (400, 422):
                raise ValidationError(
                    err_msg,
                    connector="auth0",
                    action=path,
                    details=err_body,
                )
            raise APIError(
                err_msg,
                connector="auth0",
                action=path,
                upstream_status=response.status_code,
                details=err_body,
            )

        return response.json()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    @action("List users in the Auth0 tenant")
    async def list_users(
        self,
        search: Optional[str] = None,
        limit: int = 50,
        page: int = 0,
    ) -> PaginatedList[Auth0User]:
        """List users in the Auth0 tenant.

        Args:
            search: Lucene query string for user search.
            limit: Number of users per page (max 100).
            page: Page index (zero-based).

        Returns:
            Paginated list of Auth0User objects.
        """
        params: dict[str, Any] = {
            "per_page": min(limit, 100),
            "page": page,
            "include_totals": "true",
        }
        if search:
            params["q"] = search
            params["search_engine"] = "v3"

        data = await self._request("GET", "/users", params=params)

        total = data.get("total", 0)
        users_data = data.get("users", data if isinstance(data, list) else [])

        users = [
            Auth0User(
                user_id=u.get("user_id", ""),
                email=u.get("email", ""),
                email_verified=u.get("email_verified", False),
                name=u.get("name", ""),
                nickname=u.get("nickname", ""),
                picture=u.get("picture", ""),
                created_at=u.get("created_at"),
                updated_at=u.get("updated_at"),
                last_login=u.get("last_login"),
                last_ip=u.get("last_ip"),
                logins_count=u.get("logins_count", 0),
                blocked=u.get("blocked", False),
                identities=u.get("identities", []),
                app_metadata=u.get("app_metadata", {}),
                user_metadata=u.get("user_metadata", {}),
            )
            for u in users_data
        ]

        fetched_so_far = (page + 1) * min(limit, 100)
        has_more = fetched_so_far < total

        return PaginatedList(
            items=users,
            total_count=total,
            page_state=PageState(
                page_number=page,
                total_count=total,
                has_more=has_more,
            ),
        )

    @action("Get a single user by ID")
    async def get_user(self, user_id: str) -> Auth0User:
        """Retrieve a single Auth0 user by their user_id.

        Args:
            user_id: The user's Auth0 ID (e.g. ``auth0|abc123``).

        Returns:
            The requested Auth0User.
        """
        data = await self._request("GET", f"/users/{user_id}")
        return Auth0User(
            user_id=data.get("user_id", ""),
            email=data.get("email", ""),
            email_verified=data.get("email_verified", False),
            name=data.get("name", ""),
            nickname=data.get("nickname", ""),
            picture=data.get("picture", ""),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            last_login=data.get("last_login"),
            last_ip=data.get("last_ip"),
            logins_count=data.get("logins_count", 0),
            blocked=data.get("blocked", False),
            identities=data.get("identities", []),
            app_metadata=data.get("app_metadata", {}),
            user_metadata=data.get("user_metadata", {}),
        )

    @action("Create a new user in Auth0")
    async def create_user(
        self,
        email: str,
        password: str,
        connection: str,
    ) -> Auth0User:
        """Create a new user in Auth0.

        Args:
            email: The user's email address.
            password: The user's password.
            connection: Database connection name (e.g. ``Username-Password-Authentication``).

        Returns:
            The created Auth0User.
        """
        data = await self._request(
            "POST",
            "/users",
            json_body={
                "email": email,
                "password": password,
                "connection": connection,
            },
        )
        return Auth0User(
            user_id=data.get("user_id", ""),
            email=data.get("email", ""),
            email_verified=data.get("email_verified", False),
            name=data.get("name", ""),
            nickname=data.get("nickname", ""),
            picture=data.get("picture", ""),
            created_at=data.get("created_at"),
            identities=data.get("identities", []),
        )

    @action("Update an existing user in Auth0")
    async def update_user(
        self,
        user_id: str,
        fields: dict[str, Any],
    ) -> Auth0User:
        """Update a user's attributes in Auth0.

        Args:
            user_id: The user's Auth0 ID.
            fields: Fields to update (e.g. name, email, blocked, etc.).

        Returns:
            The updated Auth0User.
        """
        data = await self._request(
            "PATCH",
            f"/users/{user_id}",
            json_body=fields,
        )
        return Auth0User(
            user_id=data.get("user_id", ""),
            email=data.get("email", ""),
            email_verified=data.get("email_verified", False),
            name=data.get("name", ""),
            nickname=data.get("nickname", ""),
            picture=data.get("picture", ""),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            last_login=data.get("last_login"),
            logins_count=data.get("logins_count", 0),
            blocked=data.get("blocked", False),
            identities=data.get("identities", []),
            app_metadata=data.get("app_metadata", {}),
            user_metadata=data.get("user_metadata", {}),
        )

    @action("Delete a user from Auth0", dangerous=True)
    async def delete_user(self, user_id: str) -> None:
        """Permanently delete a user from Auth0.

        Args:
            user_id: The user's Auth0 ID.
        """
        await self._request("DELETE", f"/users/{user_id}")

    @action("List connections in the Auth0 tenant")
    async def list_connections(
        self,
        limit: int = 50,
    ) -> PaginatedList[Auth0Connection]:
        """List identity provider connections.

        Args:
            limit: Maximum number of connections to return (max 100).

        Returns:
            Paginated list of Auth0Connection objects.
        """
        params: dict[str, Any] = {"per_page": min(limit, 100)}

        data = await self._request("GET", "/connections", params=params)
        connections = [
            Auth0Connection(
                id=c.get("id", ""),
                name=c.get("name", ""),
                display_name=c.get("display_name"),
                strategy=c.get("strategy", ""),
                enabled_clients=c.get("enabled_clients", []),
                is_domain_connection=c.get("is_domain_connection", False),
                realms=c.get("realms", []),
                metadata=c.get("metadata", {}),
            )
            for c in (data or [])
        ]
        return PaginatedList(
            items=connections,
            page_state=PageState(has_more=False),
        )

    @action("List roles in the Auth0 tenant")
    async def list_roles(
        self,
        limit: int = 50,
    ) -> PaginatedList[Auth0Role]:
        """List roles defined in the Auth0 tenant.

        Args:
            limit: Maximum number of roles to return (max 100).

        Returns:
            Paginated list of Auth0Role objects.
        """
        params: dict[str, Any] = {"per_page": min(limit, 100)}

        data = await self._request("GET", "/roles", params=params)
        roles_data = data.get("roles", data if isinstance(data, list) else [])

        roles = [
            Auth0Role(
                id=r.get("id", ""),
                name=r.get("name", ""),
                description=r.get("description", ""),
            )
            for r in roles_data
        ]
        return PaginatedList(
            items=roles,
            page_state=PageState(has_more=False),
        )

    @action("Assign roles to a user")
    async def assign_role(
        self,
        user_id: str,
        role_ids: list[str],
    ) -> None:
        """Assign one or more roles to a user.

        Args:
            user_id: The user's Auth0 ID.
            role_ids: List of role IDs to assign.
        """
        await self._request(
            "POST",
            f"/users/{user_id}/roles",
            json_body={"roles": role_ids},
        )

    # ------------------------------------------------------------------
    # Actions -- User management (extended)
    # ------------------------------------------------------------------

    @action("Block a user", dangerous=True)
    async def block_user(self, user_id: str) -> Auth0User:
        """Block a user from logging in.

        Args:
            user_id: The user's Auth0 ID.

        Returns:
            The updated Auth0User with blocked=True.
        """
        data = await self._request(
            "PATCH",
            f"/users/{user_id}",
            json_body={"blocked": True},
        )
        return Auth0User(
            user_id=data.get("user_id", ""),
            email=data.get("email", ""),
            email_verified=data.get("email_verified", False),
            name=data.get("name", ""),
            nickname=data.get("nickname", ""),
            picture=data.get("picture", ""),
            blocked=True,
        )

    @action("Unblock a user")
    async def unblock_user(self, user_id: str) -> Auth0User:
        """Unblock a previously blocked user.

        Args:
            user_id: The user's Auth0 ID.

        Returns:
            The updated Auth0User with blocked=False.
        """
        data = await self._request(
            "PATCH",
            f"/users/{user_id}",
            json_body={"blocked": False},
        )
        return Auth0User(
            user_id=data.get("user_id", ""),
            email=data.get("email", ""),
            email_verified=data.get("email_verified", False),
            name=data.get("name", ""),
            nickname=data.get("nickname", ""),
            picture=data.get("picture", ""),
            blocked=False,
        )

    @action("List roles assigned to a user")
    async def list_user_roles(
        self,
        user_id: str,
    ) -> list[Auth0Role]:
        """List all roles assigned to a user.

        Args:
            user_id: The user's Auth0 ID.

        Returns:
            List of Auth0Role objects.
        """
        data = await self._request(
            "GET",
            f"/users/{user_id}/roles",
        )
        roles_data = data if isinstance(data, list) else data.get("roles", [])
        return [
            Auth0Role(
                id=r.get("id", ""),
                name=r.get("name", ""),
                description=r.get("description", ""),
            )
            for r in roles_data
        ]

    @action("List organizations in the tenant")
    async def list_organizations(
        self,
        limit: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        """List organizations in the Auth0 tenant.

        Args:
            limit: Maximum number of organizations to return.

        Returns:
            List of organization dicts.
        """
        params: dict[str, Any] = {}
        if limit is not None:
            params["per_page"] = min(limit, 100)
        data = await self._request(
            "GET",
            "/organizations",
            params=params or None,
        )
        return data.get("organizations", data if isinstance(data, list) else [])

    # ------------------------------------------------------------------
    # Actions -- Permissions
    # ------------------------------------------------------------------

    @action("Get permissions assigned to a user")
    async def get_user_permissions(
        self,
        user_id: str,
    ) -> list[dict[str, Any]]:
        """List all permissions directly assigned to a user.

        Args:
            user_id: The user's Auth0 ID.

        Returns:
            List of permission dicts with permission_name, description,
            and resource_server_identifier.
        """
        data = await self._request(
            "GET",
            f"/users/{user_id}/permissions",
        )
        perms = data if isinstance(data, list) else data.get("permissions", [])
        return perms

    @action("Assign permissions to a user", dangerous=True)
    async def assign_permissions(
        self,
        user_id: str,
        permissions: list[dict[str, str]],
    ) -> None:
        """Assign permissions directly to a user.

        Each permission dict should contain ``permission_name`` and
        ``resource_server_identifier``.

        Args:
            user_id: The user's Auth0 ID.
            permissions: List of permission dicts to assign.
        """
        await self._request(
            "POST",
            f"/users/{user_id}/permissions",
            json_body={"permissions": permissions},
        )

    # ------------------------------------------------------------------
    # Actions -- Clients (Applications)
    # ------------------------------------------------------------------

    @action("List clients (applications) in the tenant")
    async def list_clients(
        self,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List all client applications in the Auth0 tenant.

        Args:
            limit: Maximum number of clients to return (max 100).

        Returns:
            List of client dicts with id, name, app_type, etc.
        """
        params: dict[str, Any] = {"per_page": min(limit, 100)}
        data = await self._request(
            "GET",
            "/clients",
            params=params,
        )
        return data if isinstance(data, list) else data.get("clients", [])

    @action("Get a single client by ID")
    async def get_client(self, client_id: str) -> dict[str, Any]:
        """Retrieve a single client application by its ID.

        Args:
            client_id: The Auth0 client/application ID.

        Returns:
            Dict with client details (name, app_type, callbacks, etc.).
        """
        data = await self._request("GET", f"/clients/{client_id}")
        return data if isinstance(data, dict) else {}

    # ------------------------------------------------------------------
    # Actions — Roles CRUD
    # ------------------------------------------------------------------

    @action("Get a role by ID")
    async def get_role(self, role_id: str) -> Auth0Role:
        """Retrieve a single role by ID.

        Args:
            role_id: The role ID.

        Returns:
            Auth0Role with id, name, description.
        """
        data = await self._request("GET", f"/roles/{role_id}")
        return Auth0Role(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description"),
        )

    @action("Create a role", dangerous=True)
    async def create_role(
        self,
        name: str,
        description: Optional[str] = None,
    ) -> Auth0Role:
        """Create a new role.

        Args:
            name: Role name.
            description: Role description.

        Returns:
            Created Auth0Role.
        """
        payload: dict[str, Any] = {"name": name}
        if description:
            payload["description"] = description
        data = await self._request("POST", "/roles", json=payload)
        return Auth0Role(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description"),
        )

    @action("Delete a role", dangerous=True)
    async def delete_role(self, role_id: str) -> None:
        """Delete a role.

        Args:
            role_id: The role ID to delete.
        """
        await self._request("DELETE", f"/roles/{role_id}")

    @action("List users assigned to a role")
    async def list_role_users(
        self,
        role_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List users assigned to a specific role.

        Args:
            role_id: The role ID.
            limit: Maximum users to return.

        Returns:
            List of user dicts assigned to this role.
        """
        data = await self._request(
            "GET",
            f"/roles/{role_id}/users",
            params={"per_page": limit},
        )
        return data if isinstance(data, list) else []

    # ------------------------------------------------------------------
    # Actions — Connections CRUD
    # ------------------------------------------------------------------

    @action("Get a connection by ID")
    async def get_connection(self, connection_id: str) -> Auth0Connection:
        """Retrieve a single connection by ID.

        Args:
            connection_id: The connection ID.

        Returns:
            Auth0Connection with id, name, strategy.
        """
        data = await self._request("GET", f"/connections/{connection_id}")
        return Auth0Connection(
            id=data.get("id", ""),
            name=data.get("name", ""),
            strategy=data.get("strategy", ""),
        )

    @action("Create a connection", dangerous=True)
    async def create_connection(
        self,
        name: str,
        strategy: str,
        enabled_clients: Optional[list[str]] = None,
    ) -> Auth0Connection:
        """Create a new connection.

        Args:
            name: Connection name.
            strategy: Connection strategy (e.g., 'auth0', 'google-oauth2').
            enabled_clients: Client IDs allowed to use this connection.

        Returns:
            Created Auth0Connection.
        """
        payload: dict[str, Any] = {"name": name, "strategy": strategy}
        if enabled_clients:
            payload["enabled_clients"] = enabled_clients
        data = await self._request("POST", "/connections", json=payload)
        return Auth0Connection(
            id=data.get("id", ""),
            name=data.get("name", ""),
            strategy=data.get("strategy", ""),
        )

    @action("Delete a connection", dangerous=True)
    async def delete_connection(self, connection_id: str) -> None:
        """Delete a connection.

        Args:
            connection_id: The connection ID to delete.
        """
        await self._request("DELETE", f"/connections/{connection_id}")

    # ------------------------------------------------------------------
    # Actions — Logs
    # ------------------------------------------------------------------

    @action("List log events")
    async def list_logs(
        self,
        per_page: int = 50,
        page: int = 0,
        query: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """List log events from the tenant.

        Args:
            per_page: Number of log entries per page.
            page: Page number (0-based).
            query: Lucene query string to filter logs.

        Returns:
            List of log event dicts.
        """
        params: dict[str, Any] = {"per_page": per_page, "page": page}
        if query:
            params["q"] = query
        data = await self._request("GET", "/logs", params=params)
        return data if isinstance(data, list) else []

    @action("Get a log event by ID")
    async def get_log(self, log_id: str) -> dict[str, Any]:
        """Retrieve a single log event.

        Args:
            log_id: The log event ID.

        Returns:
            Log event dict.
        """
        data = await self._request("GET", f"/logs/{log_id}")
        return data if isinstance(data, dict) else {}

    # ------------------------------------------------------------------
    # Actions — Tenant
    # ------------------------------------------------------------------

    @action("Get tenant settings")
    async def get_tenant_settings(self) -> dict[str, Any]:
        """Get the current tenant's settings.

        Returns:
            Dict with tenant settings (friendly_name, support_email,
            session_lifetime, idle_session_lifetime, etc.).
        """
        data = await self._request("GET", "/tenants/settings")
        return data if isinstance(data, dict) else {}

    # ------------------------------------------------------------------
    # Actions — Stats
    # ------------------------------------------------------------------

    @action("Get daily stats")
    async def get_daily_stats(
        self,
        from_date: str,
        to_date: str,
    ) -> list[dict[str, Any]]:
        """Get daily active user stats for a date range.

        Args:
            from_date: Start date (YYYYMMDD format).
            to_date: End date (YYYYMMDD format).

        Returns:
            List of daily stat dicts with date and logins.
        """
        data = await self._request(
            "GET",
            "/stats/daily",
            params={"from": from_date, "to": to_date},
        )
        return data if isinstance(data, list) else []
