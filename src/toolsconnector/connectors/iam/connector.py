"""AWS IAM connector -- manage IAM roles, policies, users, and access keys.

Uses the IAM Query API with ``Action`` and ``Version`` parameters in
form-encoded POST bodies. Credentials should be a JSON string or dict
containing ``access_key_id``, ``secret_access_key``, and optionally
``session_token``.

IAM is a **global** service -- the endpoint is always
``https://iam.amazonaws.com`` and SigV4 signing uses region ``us-east-1``.

IAM responses are XML-formatted with the namespace
``https://iam.amazonaws.com/doc/2010-05-08/``.

.. note::

    The SigV4 signing implementation is simplified. For production
    workloads, ``boto3`` is strongly recommended.
"""

from __future__ import annotations

import datetime
import hashlib
import logging
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import (
    ConnectorCategory,
    ProtocolType,
    RateLimitSpec,
)
from toolsconnector.errors import APIError, NotFoundError

from toolsconnector.connectors._aws.signing import sign_v4

from .types import (
    IAMAccessKey,
    IAMAttachedPolicy,
    IAMInstanceProfile,
    IAMPolicy,
    IAMRole,
    IAMUser,
)

logger = logging.getLogger("toolsconnector.iam")

# IAM XML namespace for API version 2010-05-08.
_NS = "https://iam.amazonaws.com/doc/2010-05-08/"


# ------------------------------------------------------------------
# XML namespace helpers
# ------------------------------------------------------------------


def _find(elem: ET.Element, tag: str) -> str:
    """Find a direct child element's text by tag name within the IAM namespace.

    Args:
        elem: Parent XML element.
        tag: Tag name without namespace prefix.

    Returns:
        Element text or empty string if not found.
    """
    return elem.findtext(f"{{{_NS}}}{tag}", default="")


def _findall(elem: ET.Element, tag: str) -> list[ET.Element]:
    """Find all child elements by tag name within the IAM namespace.

    Args:
        elem: Parent XML element.
        tag: Tag name without namespace prefix.

    Returns:
        List of matching elements.
    """
    return elem.findall(f"{{{_NS}}}{tag}")


# ------------------------------------------------------------------
# Tag parsing helper
# ------------------------------------------------------------------


def _parse_tags(item: ET.Element) -> dict[str, str]:
    """Extract tags from an IAM XML element's Tags/member list.

    IAM uses ``<Tags><member><Key/><Value/></member>...</Tags>`` unlike
    EC2's ``<tagSet><item>`` pattern.

    Args:
        item: XML element containing a ``Tags`` child.

    Returns:
        Dict mapping tag keys to values.
    """
    tags: dict[str, str] = {}
    tags_elem = item.find(f"{{{_NS}}}Tags")
    if tags_elem is not None:
        for member in _findall(tags_elem, "member"):
            key = _find(member, "Key")
            val = _find(member, "Value")
            if key:
                tags[key] = val
    return tags


class IAM(BaseConnector):
    """Connect to AWS IAM to manage roles, policies, users, and access keys.

    Authenticates using AWS Signature Version 4. Credentials should be
    provided as a JSON string or dict::

        {
            "access_key_id": "AKIA...",
            "secret_access_key": "..."
        }

    Uses the IAM Query API (``Action=X&Version=2010-05-08``) with
    form-encoded POST requests. IAM is a global service -- signing
    always uses ``us-east-1``.

    .. note::

        SigV4 signing is simplified. For production, use ``boto3``.
    """

    name = "iam"
    display_name = "AWS IAM"
    category = ConnectorCategory.SECURITY
    protocol = ProtocolType.REST
    base_url = "https://iam.amazonaws.com"
    description = (
        "Manage IAM roles, policies, instance profiles, and access keys."
    )
    _rate_limit_config = RateLimitSpec(rate=15, period=1, burst=30)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Parse credentials and initialise the HTTP client."""
        from toolsconnector.connectors._aws.auth import parse_credentials

        creds = parse_credentials(self._credentials)
        self._access_key_id = creds.access_key_id
        self._secret_access_key = creds.secret_access_key
        self._session_token = creds.session_token
        # IAM is global -- always sign with us-east-1.
        self._region = "us-east-1"
        self._host = "iam.amazonaws.com"
        self._endpoint = "https://iam.amazonaws.com"
        self._api_version = "2010-05-08"

        self._client = httpx.AsyncClient(timeout=self._timeout)

    async def _teardown(self) -> None:
        """Close the HTTP client."""
        if hasattr(self, "_client"):
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _iam_request(
        self,
        iam_action: str,
        params: dict[str, str] | None = None,
    ) -> ET.Element:
        """Send a Query API request to IAM.

        Args:
            iam_action: IAM API action name (e.g. ``ListRoles``).
            params: Additional form parameters for the request.

        Returns:
            Parsed XML root element of the response.

        Raises:
            NotFoundError: If the resource is not found.
            APIError: For any IAM API error.
        """
        form_params: dict[str, str] = {
            "Action": iam_action,
            "Version": self._api_version,
        }
        if params:
            form_params.update(params)

        body = urllib.parse.urlencode(form_params)
        payload_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()

        now = datetime.datetime.now(datetime.timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")

        headers: dict[str, str] = {
            "Host": self._host,
            "x-amz-date": amz_date,
            "content-type": "application/x-www-form-urlencoded",
            "x-amz-content-sha256": payload_hash,
        }

        sign_v4(
            "POST",
            self._endpoint + "/",
            headers,
            payload_hash,
            self._access_key_id,
            self._secret_access_key,
            self._region,
            "iam",
            session_token=self._session_token,
        )

        resp = await self._client.post(
            self._endpoint + "/",
            content=body,
            headers=headers,
        )

        if resp.status_code >= 400:
            error_msg = f"IAM {iam_action} error"
            error_code = ""
            try:
                err_root = ET.fromstring(resp.text)
                # IAM error XML: <ErrorResponse><Error><Code/><Message/></Error></ErrorResponse>
                for err_elem in err_root.iter("Error"):
                    error_code = err_elem.findtext("Code", default="")
                    error_msg = err_elem.findtext("Message", default=error_msg)
                    break
                # Also try with namespace
                for err_elem in err_root.iter(f"{{{_NS}}}Error"):
                    error_code = _find(err_elem, "Code") or error_code
                    error_msg = _find(err_elem, "Message") or error_msg
                    break
            except ET.ParseError:
                error_msg = resp.text[:500]

            full_msg = f"IAM {iam_action}: {error_code} - {error_msg}"

            if "NoSuchEntity" in error_code or "NotFound" in error_code:
                raise NotFoundError(
                    full_msg,
                    connector="iam",
                    action=iam_action,
                    details={"code": error_code, "message": error_msg},
                )
            raise APIError(
                full_msg,
                connector="iam",
                action=iam_action,
                upstream_status=resp.status_code,
                details={"code": error_code, "message": error_msg},
            )

        return ET.fromstring(resp.text)

    # ------------------------------------------------------------------
    # Model parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_role(item: ET.Element) -> IAMRole:
        """Parse an IAM role XML element into an IAMRole model.

        Args:
            item: XML element representing a role.

        Returns:
            IAMRole model.
        """
        max_dur_raw = _find(item, "MaxSessionDuration")
        assume_doc = _find(item, "AssumeRolePolicyDocument")
        # IAM returns URL-encoded policy documents
        if assume_doc:
            assume_doc = urllib.parse.unquote(assume_doc)
        return IAMRole(
            role_name=_find(item, "RoleName"),
            role_id=_find(item, "RoleId"),
            arn=_find(item, "Arn"),
            path=_find(item, "Path"),
            create_date=_find(item, "CreateDate") or None,
            assume_role_policy_document=assume_doc,
            description=_find(item, "Description"),
            max_session_duration=int(max_dur_raw) if max_dur_raw else 3600,
            tags=_parse_tags(item),
        )

    @staticmethod
    def _parse_policy(item: ET.Element) -> IAMPolicy:
        """Parse an IAM policy XML element into an IAMPolicy model.

        Args:
            item: XML element representing a managed policy.

        Returns:
            IAMPolicy model.
        """
        attach_raw = _find(item, "AttachmentCount")
        return IAMPolicy(
            policy_name=_find(item, "PolicyName"),
            policy_id=_find(item, "PolicyId"),
            arn=_find(item, "Arn"),
            path=_find(item, "Path"),
            default_version_id=_find(item, "DefaultVersionId"),
            attachment_count=int(attach_raw) if attach_raw else 0,
            is_attachable=_find(item, "IsAttachable") == "true",
            create_date=_find(item, "CreateDate") or None,
            update_date=_find(item, "UpdateDate") or None,
            description=_find(item, "Description"),
        )

    @staticmethod
    def _parse_instance_profile(item: ET.Element) -> IAMInstanceProfile:
        """Parse an IAM instance profile XML element.

        Args:
            item: XML element representing an instance profile.

        Returns:
            IAMInstanceProfile model.
        """
        roles: list[str] = []
        roles_elem = item.find(f"{{{_NS}}}Roles")
        if roles_elem is not None:
            for member in _findall(roles_elem, "member"):
                rn = _find(member, "RoleName")
                if rn:
                    roles.append(rn)
        return IAMInstanceProfile(
            instance_profile_name=_find(item, "InstanceProfileName"),
            instance_profile_id=_find(item, "InstanceProfileId"),
            arn=_find(item, "Arn"),
            path=_find(item, "Path"),
            roles=roles,
            create_date=_find(item, "CreateDate") or None,
        )

    @staticmethod
    def _parse_access_key(item: ET.Element) -> IAMAccessKey:
        """Parse an IAM access key XML element.

        Args:
            item: XML element representing an access key.

        Returns:
            IAMAccessKey model.
        """
        return IAMAccessKey(
            access_key_id=_find(item, "AccessKeyId"),
            status=_find(item, "Status"),
            create_date=_find(item, "CreateDate") or None,
            user_name=_find(item, "UserName"),
        )

    @staticmethod
    def _parse_user(item: ET.Element) -> IAMUser:
        """Parse an IAM user XML element into an IAMUser model.

        Args:
            item: XML element representing a user.

        Returns:
            IAMUser model.
        """
        return IAMUser(
            user_name=_find(item, "UserName"),
            user_id=_find(item, "UserId"),
            arn=_find(item, "Arn"),
            path=_find(item, "Path"),
            create_date=_find(item, "CreateDate") or None,
            tags=_parse_tags(item),
        )

    @staticmethod
    def _parse_attached_policy(item: ET.Element) -> IAMAttachedPolicy:
        """Parse an attached policy XML element.

        Args:
            item: XML element representing an attached policy.

        Returns:
            IAMAttachedPolicy model.
        """
        return IAMAttachedPolicy(
            policy_name=_find(item, "PolicyName"),
            policy_arn=_find(item, "PolicyArn"),
        )

    # ==================================================================
    # Actions -- Roles
    # ==================================================================

    @action("Create an IAM role")
    async def create_role(
        self,
        role_name: str,
        assume_role_policy_document: str,
        description: str = "",
        path: str = "/",
    ) -> IAMRole:
        """Create a new IAM role.

        Args:
            role_name: Name for the role.
            assume_role_policy_document: JSON trust policy document.
            description: Description of the role.
            path: Path prefix for the role.

        Returns:
            The created IAMRole.
        """
        params: dict[str, str] = {
            "RoleName": role_name,
            "AssumeRolePolicyDocument": urllib.parse.quote(
                assume_role_policy_document, safe="",
            ),
            "Path": path,
        }
        if description:
            params["Description"] = description

        root = await self._iam_request("CreateRole", params)

        # Response: <CreateRoleResponse><CreateRoleResult><Role>...</Role></CreateRoleResult></CreateRoleResponse>
        result = root.find(f"{{{_NS}}}CreateRoleResult")
        if result is None:
            raise APIError(
                "IAM CreateRole: missing CreateRoleResult",
                connector="iam",
                action="CreateRole",
            )
        role_elem = result.find(f"{{{_NS}}}Role")
        if role_elem is None:
            raise APIError(
                "IAM CreateRole: missing Role element",
                connector="iam",
                action="CreateRole",
            )
        return self._parse_role(role_elem)

    @action("Delete an IAM role", dangerous=True)
    async def delete_role(self, role_name: str) -> dict[str, Any]:
        """Delete an IAM role.

        The role must not have any attached policies or instance profiles.

        Args:
            role_name: Name of the role to delete.

        Returns:
            Confirmation dict with role_name and status.
        """
        await self._iam_request("DeleteRole", {"RoleName": role_name})
        return {"role_name": role_name, "status": "deleted"}

    @action("List IAM roles")
    async def list_roles(self, path_prefix: str = "/") -> list[IAMRole]:
        """List IAM roles, optionally filtered by path prefix.

        Args:
            path_prefix: Path prefix to filter roles (default ``/``).

        Returns:
            List of IAMRole objects.
        """
        params: dict[str, str] = {"PathPrefix": path_prefix}
        root = await self._iam_request("ListRoles", params)

        roles: list[IAMRole] = []
        result = root.find(f"{{{_NS}}}ListRolesResult")
        if result is not None:
            members = result.find(f"{{{_NS}}}Roles")
            if members is not None:
                for member in _findall(members, "member"):
                    roles.append(self._parse_role(member))
        return roles

    @action("Get an IAM role")
    async def get_role(self, role_name: str) -> IAMRole:
        """Get details of a specific IAM role.

        Args:
            role_name: Name of the role to retrieve.

        Returns:
            IAMRole object.
        """
        root = await self._iam_request("GetRole", {"RoleName": role_name})

        result = root.find(f"{{{_NS}}}GetRoleResult")
        if result is None:
            raise NotFoundError(
                f"IAM GetRole: role {role_name!r} not found",
                connector="iam",
                action="GetRole",
            )
        role_elem = result.find(f"{{{_NS}}}Role")
        if role_elem is None:
            raise NotFoundError(
                f"IAM GetRole: role {role_name!r} not found",
                connector="iam",
                action="GetRole",
            )
        return self._parse_role(role_elem)

    @action("Attach a managed policy to a role")
    async def attach_role_policy(
        self,
        role_name: str,
        policy_arn: str,
    ) -> dict[str, Any]:
        """Attach a managed policy to an IAM role.

        Args:
            role_name: Name of the role.
            policy_arn: ARN of the policy to attach.

        Returns:
            Confirmation dict.
        """
        await self._iam_request("AttachRolePolicy", {
            "RoleName": role_name,
            "PolicyArn": policy_arn,
        })
        return {
            "role_name": role_name,
            "policy_arn": policy_arn,
            "status": "attached",
        }

    @action("Detach a managed policy from a role")
    async def detach_role_policy(
        self,
        role_name: str,
        policy_arn: str,
    ) -> dict[str, Any]:
        """Detach a managed policy from an IAM role.

        Args:
            role_name: Name of the role.
            policy_arn: ARN of the policy to detach.

        Returns:
            Confirmation dict.
        """
        await self._iam_request("DetachRolePolicy", {
            "RoleName": role_name,
            "PolicyArn": policy_arn,
        })
        return {
            "role_name": role_name,
            "policy_arn": policy_arn,
            "status": "detached",
        }

    @action("List managed policies attached to a role")
    async def list_attached_role_policies(
        self,
        role_name: str,
    ) -> list[IAMAttachedPolicy]:
        """List managed policies attached to a role.

        Args:
            role_name: Name of the role.

        Returns:
            List of IAMAttachedPolicy objects.
        """
        root = await self._iam_request(
            "ListAttachedRolePolicies",
            {"RoleName": role_name},
        )

        policies: list[IAMAttachedPolicy] = []
        result = root.find(f"{{{_NS}}}ListAttachedRolePoliciesResult")
        if result is not None:
            members = result.find(f"{{{_NS}}}AttachedPolicies")
            if members is not None:
                for member in _findall(members, "member"):
                    policies.append(self._parse_attached_policy(member))
        return policies

    # ==================================================================
    # Actions -- Policies
    # ==================================================================

    @action("Create an IAM policy")
    async def create_policy(
        self,
        policy_name: str,
        policy_document: str,
        description: str = "",
        path: str = "/",
    ) -> IAMPolicy:
        """Create a new IAM managed policy.

        Args:
            policy_name: Name for the policy.
            policy_document: JSON policy document.
            description: Description of the policy.
            path: Path prefix for the policy.

        Returns:
            The created IAMPolicy.
        """
        params: dict[str, str] = {
            "PolicyName": policy_name,
            "PolicyDocument": urllib.parse.quote(policy_document, safe=""),
            "Path": path,
        }
        if description:
            params["Description"] = description

        root = await self._iam_request("CreatePolicy", params)

        result = root.find(f"{{{_NS}}}CreatePolicyResult")
        if result is None:
            raise APIError(
                "IAM CreatePolicy: missing CreatePolicyResult",
                connector="iam",
                action="CreatePolicy",
            )
        policy_elem = result.find(f"{{{_NS}}}Policy")
        if policy_elem is None:
            raise APIError(
                "IAM CreatePolicy: missing Policy element",
                connector="iam",
                action="CreatePolicy",
            )
        return self._parse_policy(policy_elem)

    @action("Delete an IAM policy", dangerous=True)
    async def delete_policy(self, policy_arn: str) -> dict[str, Any]:
        """Delete an IAM managed policy.

        All policy versions other than the default must be deleted first.

        Args:
            policy_arn: ARN of the policy to delete.

        Returns:
            Confirmation dict with policy_arn and status.
        """
        await self._iam_request("DeletePolicy", {"PolicyArn": policy_arn})
        return {"policy_arn": policy_arn, "status": "deleted"}

    @action("List IAM policies")
    async def list_policies(
        self,
        scope: str = "Local",
        only_attached: bool = False,
    ) -> list[IAMPolicy]:
        """List IAM managed policies.

        Args:
            scope: Scope filter -- ``Local`` for customer-managed,
                ``AWS`` for AWS-managed, or ``All``.
            only_attached: If True, only return policies attached to an
                IAM entity.

        Returns:
            List of IAMPolicy objects.
        """
        params: dict[str, str] = {
            "Scope": scope,
            "OnlyAttached": "true" if only_attached else "false",
        }
        root = await self._iam_request("ListPolicies", params)

        policies: list[IAMPolicy] = []
        result = root.find(f"{{{_NS}}}ListPoliciesResult")
        if result is not None:
            members = result.find(f"{{{_NS}}}Policies")
            if members is not None:
                for member in _findall(members, "member"):
                    policies.append(self._parse_policy(member))
        return policies

    @action("Get an IAM policy")
    async def get_policy(self, policy_arn: str) -> IAMPolicy:
        """Get details of a specific IAM managed policy.

        Args:
            policy_arn: ARN of the policy to retrieve.

        Returns:
            IAMPolicy object.
        """
        root = await self._iam_request("GetPolicy", {"PolicyArn": policy_arn})

        result = root.find(f"{{{_NS}}}GetPolicyResult")
        if result is None:
            raise NotFoundError(
                f"IAM GetPolicy: policy {policy_arn!r} not found",
                connector="iam",
                action="GetPolicy",
            )
        policy_elem = result.find(f"{{{_NS}}}Policy")
        if policy_elem is None:
            raise NotFoundError(
                f"IAM GetPolicy: policy {policy_arn!r} not found",
                connector="iam",
                action="GetPolicy",
            )
        return self._parse_policy(policy_elem)

    # ==================================================================
    # Actions -- Instance Profiles
    # ==================================================================

    @action("Create an instance profile")
    async def create_instance_profile(
        self,
        instance_profile_name: str,
        path: str = "/",
    ) -> IAMInstanceProfile:
        """Create a new IAM instance profile.

        Args:
            instance_profile_name: Name for the instance profile.
            path: Path prefix for the instance profile.

        Returns:
            The created IAMInstanceProfile.
        """
        params: dict[str, str] = {
            "InstanceProfileName": instance_profile_name,
            "Path": path,
        }
        root = await self._iam_request("CreateInstanceProfile", params)

        result = root.find(f"{{{_NS}}}CreateInstanceProfileResult")
        if result is None:
            raise APIError(
                "IAM CreateInstanceProfile: missing result",
                connector="iam",
                action="CreateInstanceProfile",
            )
        ip_elem = result.find(f"{{{_NS}}}InstanceProfile")
        if ip_elem is None:
            raise APIError(
                "IAM CreateInstanceProfile: missing InstanceProfile element",
                connector="iam",
                action="CreateInstanceProfile",
            )
        return self._parse_instance_profile(ip_elem)

    @action("Add a role to an instance profile")
    async def add_role_to_instance_profile(
        self,
        instance_profile_name: str,
        role_name: str,
    ) -> dict[str, Any]:
        """Add an IAM role to an instance profile.

        Args:
            instance_profile_name: Name of the instance profile.
            role_name: Name of the role to add.

        Returns:
            Confirmation dict.
        """
        await self._iam_request("AddRoleToInstanceProfile", {
            "InstanceProfileName": instance_profile_name,
            "RoleName": role_name,
        })
        return {
            "instance_profile_name": instance_profile_name,
            "role_name": role_name,
            "status": "added",
        }

    @action("Remove a role from an instance profile")
    async def remove_role_from_instance_profile(
        self,
        instance_profile_name: str,
        role_name: str,
    ) -> dict[str, Any]:
        """Remove an IAM role from an instance profile.

        Args:
            instance_profile_name: Name of the instance profile.
            role_name: Name of the role to remove.

        Returns:
            Confirmation dict.
        """
        await self._iam_request("RemoveRoleFromInstanceProfile", {
            "InstanceProfileName": instance_profile_name,
            "RoleName": role_name,
        })
        return {
            "instance_profile_name": instance_profile_name,
            "role_name": role_name,
            "status": "removed",
        }

    @action("List instance profiles")
    async def list_instance_profiles(
        self,
        path_prefix: str = "/",
    ) -> list[IAMInstanceProfile]:
        """List IAM instance profiles, optionally filtered by path.

        Args:
            path_prefix: Path prefix to filter (default ``/``).

        Returns:
            List of IAMInstanceProfile objects.
        """
        params: dict[str, str] = {"PathPrefix": path_prefix}
        root = await self._iam_request("ListInstanceProfiles", params)

        profiles: list[IAMInstanceProfile] = []
        result = root.find(f"{{{_NS}}}ListInstanceProfilesResult")
        if result is not None:
            members = result.find(f"{{{_NS}}}InstanceProfiles")
            if members is not None:
                for member in _findall(members, "member"):
                    profiles.append(self._parse_instance_profile(member))
        return profiles

    # ==================================================================
    # Actions -- Access Keys
    # ==================================================================

    @action("Create an access key for a user")
    async def create_access_key(self, user_name: str = "") -> IAMAccessKey:
        """Create a new access key for an IAM user.

        Args:
            user_name: IAM user name. If empty, creates a key for the
                calling user.

        Returns:
            The created IAMAccessKey (includes the secret in the
            response -- handle securely).
        """
        params: dict[str, str] = {}
        if user_name:
            params["UserName"] = user_name

        root = await self._iam_request("CreateAccessKey", params)

        result = root.find(f"{{{_NS}}}CreateAccessKeyResult")
        if result is None:
            raise APIError(
                "IAM CreateAccessKey: missing result",
                connector="iam",
                action="CreateAccessKey",
            )
        key_elem = result.find(f"{{{_NS}}}AccessKey")
        if key_elem is None:
            raise APIError(
                "IAM CreateAccessKey: missing AccessKey element",
                connector="iam",
                action="CreateAccessKey",
            )
        return self._parse_access_key(key_elem)

    @action("Delete an access key", dangerous=True)
    async def delete_access_key(
        self,
        access_key_id: str,
        user_name: str = "",
    ) -> dict[str, Any]:
        """Delete an IAM access key.

        Args:
            access_key_id: Access key ID to delete.
            user_name: IAM user name. If empty, defaults to the
                calling user.

        Returns:
            Confirmation dict.
        """
        params: dict[str, str] = {"AccessKeyId": access_key_id}
        if user_name:
            params["UserName"] = user_name

        await self._iam_request("DeleteAccessKey", params)
        return {"access_key_id": access_key_id, "status": "deleted"}

    @action("List access keys for a user")
    async def list_access_keys(
        self,
        user_name: str = "",
    ) -> list[IAMAccessKey]:
        """List access keys for an IAM user.

        Args:
            user_name: IAM user name. If empty, lists keys for the
                calling user.

        Returns:
            List of IAMAccessKey objects.
        """
        params: dict[str, str] = {}
        if user_name:
            params["UserName"] = user_name

        root = await self._iam_request("ListAccessKeys", params)

        keys: list[IAMAccessKey] = []
        result = root.find(f"{{{_NS}}}ListAccessKeysResult")
        if result is not None:
            members = result.find(f"{{{_NS}}}AccessKeyMetadata")
            if members is not None:
                for member in _findall(members, "member"):
                    keys.append(self._parse_access_key(member))
        return keys

    # ==================================================================
    # Actions -- Users
    # ==================================================================

    @action("Get the current IAM user")
    async def get_user(self, user_name: str = "") -> IAMUser:
        """Get details of an IAM user.

        Args:
            user_name: IAM user name. If empty, returns the calling user.

        Returns:
            IAMUser object.
        """
        params: dict[str, str] = {}
        if user_name:
            params["UserName"] = user_name

        root = await self._iam_request("GetUser", params)

        result = root.find(f"{{{_NS}}}GetUserResult")
        if result is None:
            raise NotFoundError(
                f"IAM GetUser: user {user_name!r} not found",
                connector="iam",
                action="GetUser",
            )
        user_elem = result.find(f"{{{_NS}}}User")
        if user_elem is None:
            raise NotFoundError(
                f"IAM GetUser: user {user_name!r} not found",
                connector="iam",
                action="GetUser",
            )
        return self._parse_user(user_elem)

    @action("List IAM users")
    async def list_users(self, path_prefix: str = "/") -> list[IAMUser]:
        """List IAM users, optionally filtered by path prefix.

        Args:
            path_prefix: Path prefix to filter users (default ``/``).

        Returns:
            List of IAMUser objects.
        """
        params: dict[str, str] = {"PathPrefix": path_prefix}
        root = await self._iam_request("ListUsers", params)

        users: list[IAMUser] = []
        result = root.find(f"{{{_NS}}}ListUsersResult")
        if result is not None:
            members = result.find(f"{{{_NS}}}Users")
            if members is not None:
                for member in _findall(members, "member"):
                    users.append(self._parse_user(member))
        return users
