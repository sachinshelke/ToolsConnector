"""Okta connector -- manage users, groups, and applications via the Okta API.

Uses the Okta REST API v1 with SSWS API token authentication.
Credentials should be ``"api_token:domain"`` format where domain is the
Okta subdomain (e.g. ``"dev-12345"`` for ``dev-12345.okta.com``).
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
from toolsconnector.types import PaginatedList, PageState

from .types import OktaApplication, OktaGroup, OktaLogEvent, OktaProfile, OktaUser

logger = logging.getLogger("toolsconnector.okta")


def _parse_link_header(link_header: str) -> Optional[str]:
    """Parse the Link header to extract the 'next' page URL.

    Args:
        link_header: The raw Link header value.

    Returns:
        The URL for the next page, or None if not present.
    """
    for part in link_header.split(","):
        part = part.strip()
        if 'rel="next"' in part:
            # Extract URL from <url>
            url_start = part.index("<") + 1
            url_end = part.index(">")
            return part[url_start:url_end]
    return None


class Okta(BaseConnector):
    """Connect to Okta to manage users, groups, and applications.

    Credentials format: ``"api_token:domain"``
    where domain is the Okta subdomain (e.g. ``dev-12345``).

    Authentication uses the SSWS scheme:
    ``Authorization: SSWS {api_token}``
    """

    name = "okta"
    display_name = "Okta"
    category = ConnectorCategory.SECURITY
    protocol = ProtocolType.REST
    base_url = "https://{domain}.okta.com/api/v1"
    description = (
        "Connect to Okta identity management to list and manage "
        "users, groups, and application integrations."
    )
    _rate_limit_config = RateLimitSpec(rate=100, period=60, burst=50)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Parse credentials and initialise the HTTP client."""
        creds = str(self._credentials)
        parts = creds.split(":", 1)
        if len(parts) < 2:
            raise ValueError("Okta credentials must be 'api_token:domain'")

        self._api_token = parts[0]
        self._domain = parts[1]
        resolved_url = (
            self._base_url
            or f"https://{self._domain}.okta.com/api/v1"
        )
        # Replace the {domain} placeholder if using the class default
        resolved_url = resolved_url.replace("{domain}", self._domain)

        self._client = httpx.AsyncClient(
            base_url=resolved_url,
            headers={
                "Authorization": f"SSWS {self._api_token}",
                "Accept": "application/json",
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
    ) -> tuple[Any, Optional[str]]:
        """Execute an HTTP request against the Okta API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE).
            path: API path relative to base URL.
            params: URL query parameters.
            json_body: JSON request body.

        Returns:
            Tuple of (parsed JSON response, next_page_url or None).

        Raises:
            NotFoundError: If the resource is not found (404).
            RateLimitError: If rate limited (429).
            ValidationError: If the request is invalid (400).
            APIError: For any other API error.
        """
        kwargs: dict[str, Any] = {}
        if params:
            kwargs["params"] = params
        if json_body is not None:
            kwargs["json"] = json_body

        response = await self._client.request(method, path, **kwargs)

        if response.status_code >= 400:
            try:
                err_body = response.json()
            except Exception:
                err_body = {"errorSummary": response.text}

            err_summary = err_body.get("errorSummary", "Unknown error")
            err_msg = f"Okta API error ({response.status_code}): {err_summary}"

            if response.status_code == 404:
                raise NotFoundError(
                    err_msg, connector="okta", action=path, details=err_body,
                )
            if response.status_code == 429:
                retry_after = float(
                    response.headers.get("x-rate-limit-reset", "60")
                )
                raise RateLimitError(
                    err_msg,
                    connector="okta",
                    action=path,
                    retry_after_seconds=retry_after,
                )
            if response.status_code in (400, 422):
                raise ValidationError(
                    err_msg, connector="okta", action=path, details=err_body,
                )
            raise APIError(
                err_msg,
                connector="okta",
                action=path,
                upstream_status=response.status_code,
                details=err_body,
            )

        # Parse Link header for pagination
        link_header = response.headers.get("link", "")
        next_url = _parse_link_header(link_header) if link_header else None

        if response.status_code == 204:
            return None, next_url

        return response.json(), next_url

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    @action("List users in the Okta organization")
    async def list_users(
        self,
        search: Optional[str] = None,
        filter: Optional[str] = None,
        limit: int = 200,
    ) -> PaginatedList[OktaUser]:
        """List users in the Okta organization.

        Args:
            search: Search expression (e.g. ``profile.email eq "user@example.com"``).
            filter: Filter expression using Okta filter syntax.
            limit: Maximum number of users to return (max 200).

        Returns:
            Paginated list of OktaUser objects.
        """
        params: dict[str, Any] = {"limit": min(limit, 200)}
        if search:
            params["search"] = search
        if filter:
            params["filter"] = filter

        data, next_url = await self._request("GET", "/users", params=params)

        users = []
        for u in (data or []):
            profile_data = u.get("profile", {})
            profile = OktaProfile(
                firstName=profile_data.get("firstName"),
                lastName=profile_data.get("lastName"),
                email=profile_data.get("email"),
                login=profile_data.get("login"),
                mobilePhone=profile_data.get("mobilePhone"),
                secondEmail=profile_data.get("secondEmail"),
                displayName=profile_data.get("displayName"),
                title=profile_data.get("title"),
                department=profile_data.get("department"),
                organization=profile_data.get("organization"),
            )
            users.append(
                OktaUser(
                    id=u.get("id", ""),
                    status=u.get("status", ""),
                    created=u.get("created"),
                    activated=u.get("activated"),
                    lastLogin=u.get("lastLogin"),
                    lastUpdated=u.get("lastUpdated"),
                    statusChanged=u.get("statusChanged"),
                    profile=profile,
                )
            )

        has_more = next_url is not None
        return PaginatedList(
            items=users,
            page_state=PageState(
                cursor=next_url if has_more else None,
                has_more=has_more,
            ),
        )

    @action("Get a single user by ID")
    async def get_user(self, user_id: str) -> OktaUser:
        """Retrieve a single Okta user by their ID or login.

        Args:
            user_id: The user's Okta ID or login (email).

        Returns:
            The requested OktaUser.
        """
        data, _ = await self._request("GET", f"/users/{user_id}")
        profile_data = data.get("profile", {})
        profile = OktaProfile(
            firstName=profile_data.get("firstName"),
            lastName=profile_data.get("lastName"),
            email=profile_data.get("email"),
            login=profile_data.get("login"),
            mobilePhone=profile_data.get("mobilePhone"),
            secondEmail=profile_data.get("secondEmail"),
            displayName=profile_data.get("displayName"),
            title=profile_data.get("title"),
            department=profile_data.get("department"),
            organization=profile_data.get("organization"),
        )
        return OktaUser(
            id=data.get("id", ""),
            status=data.get("status", ""),
            created=data.get("created"),
            activated=data.get("activated"),
            lastLogin=data.get("lastLogin"),
            lastUpdated=data.get("lastUpdated"),
            statusChanged=data.get("statusChanged"),
            profile=profile,
        )

    @action("Create a new user in Okta")
    async def create_user(
        self,
        profile: dict[str, Any],
        credentials: Optional[dict[str, Any]] = None,
    ) -> OktaUser:
        """Create a new user in the Okta organization.

        Args:
            profile: User profile fields (firstName, lastName, email, login).
            credentials: Optional credentials (password, recovery_question).

        Returns:
            The created OktaUser.
        """
        body: dict[str, Any] = {"profile": profile}
        if credentials:
            body["credentials"] = credentials

        data, _ = await self._request("POST", "/users", json_body=body)
        profile_data = data.get("profile", {})
        okta_profile = OktaProfile(
            firstName=profile_data.get("firstName"),
            lastName=profile_data.get("lastName"),
            email=profile_data.get("email"),
            login=profile_data.get("login"),
            mobilePhone=profile_data.get("mobilePhone"),
            secondEmail=profile_data.get("secondEmail"),
            displayName=profile_data.get("displayName"),
            title=profile_data.get("title"),
            department=profile_data.get("department"),
            organization=profile_data.get("organization"),
        )
        return OktaUser(
            id=data.get("id", ""),
            status=data.get("status", ""),
            created=data.get("created"),
            activated=data.get("activated"),
            profile=okta_profile,
        )

    @action("Update an existing user's profile in Okta")
    async def update_user(
        self,
        user_id: str,
        profile: dict[str, Any],
    ) -> OktaUser:
        """Update a user's profile in Okta.

        Args:
            user_id: The user's Okta ID.
            profile: Profile fields to update.

        Returns:
            The updated OktaUser.
        """
        data, _ = await self._request(
            "POST", f"/users/{user_id}", json_body={"profile": profile},
        )
        profile_data = data.get("profile", {})
        okta_profile = OktaProfile(
            firstName=profile_data.get("firstName"),
            lastName=profile_data.get("lastName"),
            email=profile_data.get("email"),
            login=profile_data.get("login"),
            mobilePhone=profile_data.get("mobilePhone"),
            secondEmail=profile_data.get("secondEmail"),
            displayName=profile_data.get("displayName"),
            title=profile_data.get("title"),
            department=profile_data.get("department"),
            organization=profile_data.get("organization"),
        )
        return OktaUser(
            id=data.get("id", ""),
            status=data.get("status", ""),
            created=data.get("created"),
            activated=data.get("activated"),
            lastUpdated=data.get("lastUpdated"),
            profile=okta_profile,
        )

    @action("Deactivate a user in Okta", dangerous=True)
    async def deactivate_user(self, user_id: str) -> None:
        """Deactivate a user in Okta. This revokes all active sessions.

        Args:
            user_id: The user's Okta ID.
        """
        await self._request("POST", f"/users/{user_id}/lifecycle/deactivate")

    @action("List groups in the Okta organization")
    async def list_groups(
        self,
        search: Optional[str] = None,
        limit: int = 200,
    ) -> PaginatedList[OktaGroup]:
        """List groups in the Okta organization.

        Args:
            search: Search query to filter groups by name.
            limit: Maximum number of groups to return (max 200).

        Returns:
            Paginated list of OktaGroup objects.
        """
        params: dict[str, Any] = {"limit": min(limit, 200)}
        if search:
            params["q"] = search

        data, next_url = await self._request(
            "GET", "/groups", params=params,
        )

        groups = []
        for g in (data or []):
            gp = g.get("profile", {})
            groups.append(
                OktaGroup(
                    id=g.get("id", ""),
                    created=g.get("created"),
                    lastUpdated=g.get("lastUpdated"),
                    lastMembershipUpdated=g.get("lastMembershipUpdated"),
                    type=g.get("type", ""),
                    name=gp.get("name", ""),
                    description=gp.get("description", ""),
                    profile=gp,
                )
            )

        has_more = next_url is not None
        return PaginatedList(
            items=groups,
            page_state=PageState(
                cursor=next_url if has_more else None,
                has_more=has_more,
            ),
        )

    @action("Add a user to an Okta group")
    async def add_user_to_group(
        self,
        group_id: str,
        user_id: str,
    ) -> None:
        """Add a user to a group in Okta.

        Args:
            group_id: The group's Okta ID.
            user_id: The user's Okta ID.
        """
        await self._request(
            "PUT", f"/groups/{group_id}/users/{user_id}",
        )

    @action("List applications in the Okta organization")
    async def list_applications(
        self,
        limit: int = 200,
    ) -> PaginatedList[OktaApplication]:
        """List application integrations in the Okta organization.

        Args:
            limit: Maximum number of applications to return (max 200).

        Returns:
            Paginated list of OktaApplication objects.
        """
        params: dict[str, Any] = {"limit": min(limit, 200)}

        data, next_url = await self._request(
            "GET", "/apps", params=params,
        )

        apps = [
            OktaApplication(
                id=a.get("id", ""),
                name=a.get("name", ""),
                label=a.get("label", ""),
                status=a.get("status", ""),
                created=a.get("created"),
                lastUpdated=a.get("lastUpdated"),
                signOnMode=a.get("signOnMode"),
                features=a.get("features", []),
                visibility=a.get("visibility", {}),
            )
            for a in (data or [])
        ]

        has_more = next_url is not None
        return PaginatedList(
            items=apps,
            page_state=PageState(
                cursor=next_url if has_more else None,
                has_more=has_more,
            ),
        )

    # ------------------------------------------------------------------
    # Actions -- User lifecycle (extended)
    # ------------------------------------------------------------------

    @action("Activate a user in Okta")
    async def activate_user(self, user_id: str) -> bool:
        """Activate a deactivated user in Okta.

        Args:
            user_id: The user's Okta ID.

        Returns:
            True if the activation was successful.
        """
        await self._request(
            "POST", f"/users/{user_id}/lifecycle/activate",
            params={"sendEmail": "false"},
        )
        return True

    @action("Reset a user's password")
    async def reset_password(self, user_id: str) -> dict[str, Any]:
        """Trigger a password reset for a user.

        Args:
            user_id: The user's Okta ID.

        Returns:
            Dict with the reset password URL.
        """
        data, _ = await self._request(
            "POST", f"/users/{user_id}/lifecycle/reset_password",
            params={"sendEmail": "false"},
        )
        return data if isinstance(data, dict) else {}

    @action("List groups a user belongs to")
    async def list_user_groups(
        self, user_id: str,
    ) -> list[OktaGroup]:
        """List all groups a user is a member of.

        Args:
            user_id: The user's Okta ID.

        Returns:
            List of OktaGroup objects.
        """
        data, _ = await self._request(
            "GET", f"/users/{user_id}/groups",
        )
        groups: list[OktaGroup] = []
        for g in (data or []):
            gp = g.get("profile", {})
            groups.append(OktaGroup(
                id=g.get("id", ""),
                created=g.get("created"),
                lastUpdated=g.get("lastUpdated"),
                type=g.get("type", ""),
                name=gp.get("name", ""),
                description=gp.get("description", ""),
                profile=gp,
            ))
        return groups

    @action("Remove a user from a group")
    async def remove_user_from_group(
        self, group_id: str, user_id: str,
    ) -> bool:
        """Remove a user from a group.

        Args:
            group_id: The group's Okta ID.
            user_id: The user's Okta ID.

        Returns:
            True if the removal was successful.
        """
        await self._request(
            "DELETE", f"/groups/{group_id}/users/{user_id}",
        )
        return True

    # ------------------------------------------------------------------
    # Actions -- User applications
    # ------------------------------------------------------------------

    @action("List applications assigned to a user")
    async def list_user_apps(
        self, user_id: str,
    ) -> list[OktaApplication]:
        """List all applications assigned to a specific user.

        Args:
            user_id: The user's Okta ID.

        Returns:
            List of OktaApplication objects assigned to the user.
        """
        data, _ = await self._request(
            "GET", f"/users/{user_id}/appLinks",
        )
        return [
            OktaApplication(
                id=a.get("appInstanceId", a.get("id", "")),
                name=a.get("appName", ""),
                label=a.get("label", ""),
                status=a.get("status", "ACTIVE"),
                created=a.get("created"),
                signOnMode=a.get("credentialsType"),
            )
            for a in (data or [])
        ]

    # ------------------------------------------------------------------
    # Actions -- Suspend / Unsuspend
    # ------------------------------------------------------------------

    @action("Suspend a user in Okta", dangerous=True)
    async def suspend_user(self, user_id: str) -> bool:
        """Suspend a user in Okta. The user cannot sign in while suspended.

        Unlike deactivation, suspension is reversible and does not
        remove the user's sessions or application assignments.

        Args:
            user_id: The user's Okta ID.

        Returns:
            True if the suspension was successful.
        """
        await self._request(
            "POST", f"/users/{user_id}/lifecycle/suspend",
        )
        return True

    @action("Unsuspend a user in Okta")
    async def unsuspend_user(self, user_id: str) -> bool:
        """Unsuspend a previously suspended user in Okta.

        Args:
            user_id: The user's Okta ID.

        Returns:
            True if the unsuspension was successful.
        """
        await self._request(
            "POST", f"/users/{user_id}/lifecycle/unsuspend",
        )
        return True

    # ------------------------------------------------------------------
    # Actions -- Group details
    # ------------------------------------------------------------------

    @action("Get a single group by ID")
    async def get_group(self, group_id: str) -> OktaGroup:
        """Retrieve a single Okta group by its ID.

        Args:
            group_id: The group's Okta ID.

        Returns:
            OktaGroup object.
        """
        data, _ = await self._request("GET", f"/groups/{group_id}")
        gp = data.get("profile", {})
        return OktaGroup(
            id=data.get("id", ""),
            created=data.get("created"),
            lastUpdated=data.get("lastUpdated"),
            lastMembershipUpdated=data.get("lastMembershipUpdated"),
            type=data.get("type", ""),
            name=gp.get("name", ""),
            description=gp.get("description", ""),
            profile=gp,
        )

    # ------------------------------------------------------------------
    # Actions -- Group members
    # ------------------------------------------------------------------

    @action("List members of a group")
    async def list_group_members(
        self,
        group_id: str,
        limit: int = 200,
    ) -> PaginatedList[OktaUser]:
        """List all users that are members of a group.

        Args:
            group_id: The group's Okta ID.
            limit: Maximum number of members to return (max 200).

        Returns:
            Paginated list of OktaUser objects in the group.
        """
        params: dict[str, Any] = {"limit": min(limit, 200)}
        data, next_url = await self._request(
            "GET", f"/groups/{group_id}/users", params=params,
        )

        users: list[OktaUser] = []
        for u in (data or []):
            profile_data = u.get("profile", {})
            profile = OktaProfile(
                firstName=profile_data.get("firstName"),
                lastName=profile_data.get("lastName"),
                email=profile_data.get("email"),
                login=profile_data.get("login"),
                mobilePhone=profile_data.get("mobilePhone"),
                secondEmail=profile_data.get("secondEmail"),
                displayName=profile_data.get("displayName"),
                title=profile_data.get("title"),
                department=profile_data.get("department"),
                organization=profile_data.get("organization"),
            )
            users.append(OktaUser(
                id=u.get("id", ""),
                status=u.get("status", ""),
                created=u.get("created"),
                activated=u.get("activated"),
                lastLogin=u.get("lastLogin"),
                lastUpdated=u.get("lastUpdated"),
                statusChanged=u.get("statusChanged"),
                profile=profile,
            ))

        has_more = next_url is not None
        return PaginatedList(
            items=users,
            page_state=PageState(
                cursor=next_url if has_more else None,
                has_more=has_more,
            ),
        )

    # ------------------------------------------------------------------
    # Actions -- Group CRUD
    # ------------------------------------------------------------------

    @action("Create a new group in Okta")
    async def create_group(
        self,
        name: str,
        description: Optional[str] = None,
    ) -> OktaGroup:
        """Create a new OKTA_GROUP in the organization.

        Args:
            name: The group name.
            description: Optional group description.

        Returns:
            The created OktaGroup.
        """
        profile: dict[str, Any] = {"name": name}
        if description is not None:
            profile["description"] = description

        data, _ = await self._request(
            "POST", "/groups", json_body={"profile": profile},
        )
        gp = data.get("profile", {})
        return OktaGroup(
            id=data.get("id", ""),
            created=data.get("created"),
            lastUpdated=data.get("lastUpdated"),
            lastMembershipUpdated=data.get("lastMembershipUpdated"),
            type=data.get("type", ""),
            name=gp.get("name", ""),
            description=gp.get("description", ""),
            profile=gp,
        )

    @action("Delete a group from Okta", dangerous=True)
    async def delete_group(self, group_id: str) -> bool:
        """Delete an OKTA_GROUP from the organization.

        Only groups with OKTA_GROUP type can be deleted.  Deleting a
        group does not delete the users in that group.

        Args:
            group_id: The group's Okta ID.

        Returns:
            True if the group was deleted.
        """
        await self._request("DELETE", f"/groups/{group_id}")
        return True

    # ------------------------------------------------------------------
    # Actions -- Application user assignment
    # ------------------------------------------------------------------

    @action("Assign a user to an application")
    async def assign_user_to_app(
        self,
        app_id: str,
        user_id: str,
        profile: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Assign a user to an application for SSO and provisioning.

        Args:
            app_id: The application's Okta ID.
            user_id: The user's Okta ID.
            profile: Optional app-specific profile attributes for the
                user (e.g. SSO username mappings).

        Returns:
            Dict with the application user assignment details.
        """
        body: dict[str, Any] = {
            "id": user_id,
            "scope": "USER",
        }
        if profile is not None:
            body["profile"] = profile

        data, _ = await self._request(
            "POST", f"/apps/{app_id}/users", json_body=body,
        )
        return data if isinstance(data, dict) else {}

    # ------------------------------------------------------------------
    # Actions -- System Log
    # ------------------------------------------------------------------

    @action("List system log events")
    async def list_system_logs(
        self,
        since: Optional[str] = None,
        until: Optional[str] = None,
        filter: Optional[str] = None,
        q: Optional[str] = None,
        limit: int = 100,
    ) -> PaginatedList[OktaLogEvent]:
        """Query the Okta System Log for audit events.

        The System Log records authentication events, user lifecycle
        changes, policy evaluations, and administrator actions.

        Args:
            since: Lower time bound (ISO 8601, e.g.
                ``2024-01-01T00:00:00Z``).
            until: Upper time bound (ISO 8601).
            filter: SCIM filter expression (e.g.
                ``eventType eq "user.session.start"``).
            q: Free-text search query across log event fields.
            limit: Maximum events to return (max 1000, default 100).

        Returns:
            Paginated list of OktaLogEvent objects.
        """
        params: dict[str, Any] = {"limit": min(limit, 1000)}
        if since:
            params["since"] = since
        if until:
            params["until"] = until
        if filter:
            params["filter"] = filter
        if q:
            params["q"] = q

        data, next_url = await self._request(
            "GET", "/logs", params=params,
        )

        events: list[OktaLogEvent] = []
        for e in (data or []):
            events.append(OktaLogEvent(
                uuid=e.get("uuid", ""),
                published=e.get("published"),
                eventType=e.get("eventType"),
                severity=e.get("severity"),
                displayMessage=e.get("displayMessage"),
                actor=e.get("actor"),
                client=e.get("client"),
                outcome=e.get("outcome"),
                target=e.get("target") or [],
                transaction=e.get("transaction"),
                debugContext=e.get("debugContext"),
                authenticationContext=e.get("authenticationContext"),
            ))

        has_more = next_url is not None
        return PaginatedList(
            items=events,
            page_state=PageState(
                cursor=next_url if has_more else None,
                has_more=has_more,
            ),
        )
