"""AWS ECR connector -- manage container image repositories and lifecycle policies.

Uses the ECR JSON API with ``X-Amz-Target`` headers. Credentials should be
``"access_key:secret_key:region"`` format or any format accepted by
``parse_credentials``.

.. note::

    The SigV4 signing implementation is simplified. For production
    workloads, ``boto3`` is strongly recommended.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
from typing import Any, Optional

import httpx

from toolsconnector.connectors._aws.signing import sign_v4
from toolsconnector.errors import APIError, NotFoundError
from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import (
    ConnectorCategory,
    ProtocolType,
    RateLimitSpec,
)

from .types import (
    ECRAuthorizationData,
    ECRBatchDeleteResult,
    ECRImage,
    ECRLifecyclePolicy,
    ECRRepository,
)

logger = logging.getLogger("toolsconnector.ecr")

_TARGET_PREFIX = "AmazonEC2ContainerRegistry_V20150921"


class ECR(BaseConnector):
    """Connect to AWS ECR to manage container image repositories.

    Credentials format: ``"access_key_id:secret_access_key:region"``
    Uses the ECR JSON API (``X-Amz-Target: AmazonEC2ContainerRegistry_V20150921.{Action}``).

    .. note::

        SigV4 signing is simplified. For production, use ``boto3``.
    """

    name = "ecr"
    display_name = "AWS ECR"
    category = ConnectorCategory.DEVOPS
    protocol = ProtocolType.REST
    base_url = "https://api.ecr.us-east-1.amazonaws.com"
    description = (
        "Manage container image repositories, push/pull authorization, and lifecycle policies."
    )
    _rate_limit_config = RateLimitSpec(rate=100, period=1, burst=200)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Parse credentials and initialise the HTTP client."""
        from toolsconnector.connectors._aws.auth import parse_credentials

        creds = parse_credentials(self._credentials)
        self._access_key = creds.access_key_id
        self._secret_key = creds.secret_access_key
        self._region = creds.region
        self._session_token = creds.session_token
        self._host = f"api.ecr.{self._region}.amazonaws.com"
        self._base_url = f"https://{self._host}"

        self._client = httpx.AsyncClient(timeout=self._timeout)

    async def _teardown(self) -> None:
        """Close the HTTP client."""
        if hasattr(self, "_client"):
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _ecr_request(
        self,
        target_action: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a signed ECR JSON API request.

        Args:
            target_action: ECR action name (e.g. ``CreateRepository``).
            payload: JSON request body dict.

        Returns:
            Parsed JSON response body.

        Raises:
            NotFoundError: If the repository is not found.
            APIError: For any ECR API error.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        body = json.dumps(payload)
        payload_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()

        headers: dict[str, str] = {
            "Content-Type": "application/x-amz-json-1.1",
            "X-Amz-Target": f"{_TARGET_PREFIX}.{target_action}",
            "x-amz-date": amz_date,
            "Host": self._host,
        }

        sign_v4(
            "POST",
            self._base_url + "/",
            headers,
            payload_hash,
            self._access_key,
            self._secret_key,
            self._region,
            service="ecr",
            session_token=self._session_token,
        )

        response = await self._client.post(
            self._base_url + "/",
            content=body,
            headers=headers,
        )

        if response.status_code >= 400:
            try:
                err_body = response.json()
            except Exception:
                err_body = {"message": response.text}

            err_type = err_body.get("__type", "")
            err_msg = err_body.get("message", err_body.get("Message", ""))
            full_msg = f"ECR {target_action} error: {err_type} - {err_msg}"

            if "RepositoryNotFoundException" in err_type or "NotFound" in err_type:
                raise NotFoundError(
                    full_msg,
                    connector="ecr",
                    action=target_action,
                    details=err_body,
                )
            raise APIError(
                full_msg,
                connector="ecr",
                action=target_action,
                upstream_status=response.status_code,
                details=err_body,
            )

        return response.json()

    # ------------------------------------------------------------------
    # Actions -- Repository management
    # ------------------------------------------------------------------

    @action("Create a new ECR repository")
    async def create_repository(
        self,
        repository_name: str,
        image_tag_mutability: str = "MUTABLE",
        scan_on_push: bool = False,
    ) -> ECRRepository:
        """Create a new ECR repository.

        Args:
            repository_name: Name for the new repository.
            image_tag_mutability: Tag mutability setting (MUTABLE or IMMUTABLE).
            scan_on_push: Whether to scan images on push.

        Returns:
            ECRRepository with the created repository details.
        """
        payload: dict[str, Any] = {
            "repositoryName": repository_name,
            "imageTagMutability": image_tag_mutability,
            "imageScanningConfiguration": {"scanOnPush": scan_on_push},
        }

        body = await self._ecr_request("CreateRepository", payload)
        repo = body.get("repository", {})
        return ECRRepository(
            repository_name=repo.get("repositoryName", ""),
            repository_arn=repo.get("repositoryArn", ""),
            registry_id=repo.get("registryId", ""),
            repository_uri=repo.get("repositoryUri", ""),
            created_at=str(repo.get("createdAt", "")) if repo.get("createdAt") else None,
            image_scanning_configuration=repo.get("imageScanningConfiguration", {}),
            image_tag_mutability=repo.get("imageTagMutability", "MUTABLE"),
        )

    @action("Delete an ECR repository", dangerous=True)
    async def delete_repository(
        self,
        repository_name: str,
        force: bool = False,
    ) -> ECRRepository:
        """Delete an ECR repository.

        Args:
            repository_name: Name of the repository to delete.
            force: If True, delete the repository even if it contains images.

        Returns:
            ECRRepository with the deleted repository details.
        """
        payload: dict[str, Any] = {
            "repositoryName": repository_name,
            "force": force,
        }

        body = await self._ecr_request("DeleteRepository", payload)
        repo = body.get("repository", {})
        return ECRRepository(
            repository_name=repo.get("repositoryName", ""),
            repository_arn=repo.get("repositoryArn", ""),
            registry_id=repo.get("registryId", ""),
            repository_uri=repo.get("repositoryUri", ""),
            created_at=str(repo.get("createdAt", "")) if repo.get("createdAt") else None,
            image_scanning_configuration=repo.get("imageScanningConfiguration", {}),
            image_tag_mutability=repo.get("imageTagMutability", "MUTABLE"),
        )

    @action("List ECR repositories")
    async def describe_repositories(
        self,
        repository_names: Optional[list[str]] = None,
    ) -> list[ECRRepository]:
        """List ECR repositories, optionally filtered by name.

        Args:
            repository_names: Optional list of repository names to describe.

        Returns:
            List of ECRRepository objects.
        """
        payload: dict[str, Any] = {}
        if repository_names:
            payload["repositoryNames"] = repository_names

        body = await self._ecr_request("DescribeRepositories", payload)
        repos = body.get("repositories", [])
        return [
            ECRRepository(
                repository_name=r.get("repositoryName", ""),
                repository_arn=r.get("repositoryArn", ""),
                registry_id=r.get("registryId", ""),
                repository_uri=r.get("repositoryUri", ""),
                created_at=str(r.get("createdAt", "")) if r.get("createdAt") else None,
                image_scanning_configuration=r.get("imageScanningConfiguration", {}),
                image_tag_mutability=r.get("imageTagMutability", "MUTABLE"),
            )
            for r in repos
        ]

    # ------------------------------------------------------------------
    # Actions -- Image management
    # ------------------------------------------------------------------

    @action("List images in an ECR repository")
    async def list_images(
        self,
        repository_name: str,
        tag_status: str = "ANY",
    ) -> list[dict]:
        """List images in an ECR repository.

        Args:
            repository_name: Name of the repository.
            tag_status: Filter by tag status (TAGGED, UNTAGGED, or ANY).

        Returns:
            List of image identifier dicts with imageDigest and imageTag.
        """
        payload: dict[str, Any] = {
            "repositoryName": repository_name,
        }
        if tag_status != "ANY":
            payload["filter"] = {"tagStatus": tag_status}

        body = await self._ecr_request("ListImages", payload)
        return body.get("imageIds", [])

    @action("Describe images in an ECR repository")
    async def describe_images(
        self,
        repository_name: str,
        image_ids: Optional[list[dict]] = None,
    ) -> list[ECRImage]:
        """Describe images in an ECR repository.

        Args:
            repository_name: Name of the repository.
            image_ids: Optional list of image identifier dicts to describe.
                Each dict may contain imageDigest and/or imageTag.

        Returns:
            List of ECRImage objects with detailed image metadata.
        """
        payload: dict[str, Any] = {
            "repositoryName": repository_name,
        }
        if image_ids:
            payload["imageIds"] = image_ids

        body = await self._ecr_request("DescribeImages", payload)
        details = body.get("imageDetails", [])
        return [
            ECRImage(
                image_digest=d.get("imageDigest", ""),
                image_tags=d.get("imageTags", []),
                image_pushed_at=(
                    str(d.get("imagePushedAt", "")) if d.get("imagePushedAt") else None
                ),
                image_size_in_bytes=d.get("imageSizeInBytes"),
                image_manifest_media_type=d.get("imageManifestMediaType"),
            )
            for d in details
        ]

    @action("Batch delete images from a repository", dangerous=True)
    async def batch_delete_image(
        self,
        repository_name: str,
        image_ids: list[dict],
    ) -> ECRBatchDeleteResult:
        """Batch delete images from an ECR repository.

        Args:
            repository_name: Name of the repository.
            image_ids: List of image identifier dicts to delete. Each dict
                should contain imageDigest and/or imageTag.

        Returns:
            ECRBatchDeleteResult with deleted image IDs and any failures.
        """
        payload: dict[str, Any] = {
            "repositoryName": repository_name,
            "imageIds": image_ids,
        }

        body = await self._ecr_request("BatchDeleteImage", payload)
        return ECRBatchDeleteResult(
            image_ids=body.get("imageIds", []),
            failures=body.get("failures", []),
        )

    # ------------------------------------------------------------------
    # Actions -- Authorization
    # ------------------------------------------------------------------

    @action("Get an authorization token for Docker login")
    async def get_authorization_token(self) -> ECRAuthorizationData:
        """Get an authorization token for Docker login to ECR.

        The token is valid for 12 hours and can be used with
        ``docker login``.

        Returns:
            ECRAuthorizationData with the base64-encoded token and
            proxy endpoint.
        """
        body = await self._ecr_request("GetAuthorizationToken", {})
        auth_data = body.get("authorizationData", [{}])
        first = auth_data[0] if auth_data else {}
        return ECRAuthorizationData(
            authorization_token=first.get("authorizationToken", ""),
            expires_at=(str(first.get("expiresAt", "")) if first.get("expiresAt") else None),
            proxy_endpoint=first.get("proxyEndpoint", ""),
        )

    # ------------------------------------------------------------------
    # Actions -- Lifecycle policies
    # ------------------------------------------------------------------

    @action("Set the lifecycle policy for a repository")
    async def put_lifecycle_policy(
        self,
        repository_name: str,
        lifecycle_policy_text: str,
    ) -> ECRLifecyclePolicy:
        """Set the lifecycle policy for an ECR repository.

        Args:
            repository_name: Name of the repository.
            lifecycle_policy_text: JSON lifecycle policy document as a string.

        Returns:
            ECRLifecyclePolicy with the applied policy details.
        """
        payload: dict[str, Any] = {
            "repositoryName": repository_name,
            "lifecyclePolicyText": lifecycle_policy_text,
        }

        body = await self._ecr_request("PutLifecyclePolicy", payload)
        return ECRLifecyclePolicy(
            registry_id=body.get("registryId", ""),
            repository_name=body.get("repositoryName", ""),
            lifecycle_policy_text=body.get("lifecyclePolicyText", ""),
        )

    @action("Get the lifecycle policy for a repository")
    async def get_lifecycle_policy(
        self,
        repository_name: str,
    ) -> ECRLifecyclePolicy:
        """Get the lifecycle policy for an ECR repository.

        Args:
            repository_name: Name of the repository.

        Returns:
            ECRLifecyclePolicy with the current policy details.
        """
        payload: dict[str, Any] = {
            "repositoryName": repository_name,
        }

        body = await self._ecr_request("GetLifecyclePolicy", payload)
        return ECRLifecyclePolicy(
            registry_id=body.get("registryId", ""),
            repository_name=body.get("repositoryName", ""),
            lifecycle_policy_text=body.get("lifecyclePolicyText", ""),
        )

    # ------------------------------------------------------------------
    # Actions -- Repository policies
    # ------------------------------------------------------------------

    @action("Set the repository policy")
    async def set_repository_policy(
        self,
        repository_name: str,
        policy_text: str,
    ) -> dict:
        """Set the access policy for an ECR repository.

        Args:
            repository_name: Name of the repository.
            policy_text: JSON policy document as a string.

        Returns:
            Dict with registryId, repositoryName, and policyText.
        """
        payload: dict[str, Any] = {
            "repositoryName": repository_name,
            "policyText": policy_text,
        }

        body = await self._ecr_request("SetRepositoryPolicy", payload)
        return {
            "registry_id": body.get("registryId", ""),
            "repository_name": body.get("repositoryName", ""),
            "policy_text": body.get("policyText", ""),
        }

    # ------------------------------------------------------------------
    # Actions -- Tagging
    # ------------------------------------------------------------------

    @action("Add tags to an ECR resource")
    async def tag_resource(
        self,
        resource_arn: str,
        tags: list[dict],
    ) -> dict:
        """Add tags to an ECR resource.

        Args:
            resource_arn: The ARN of the ECR resource to tag.
            tags: List of tag dicts, each with Key and Value.

        Returns:
            Empty dict on success.
        """
        payload: dict[str, Any] = {
            "resourceArn": resource_arn,
            "tags": tags,
        }

        await self._ecr_request("TagResource", payload)
        return {}

    @action("Remove tags from an ECR resource")
    async def untag_resource(
        self,
        resource_arn: str,
        tag_keys: list[str],
    ) -> dict:
        """Remove tags from an ECR resource.

        Args:
            resource_arn: The ARN of the ECR resource to untag.
            tag_keys: List of tag keys to remove.

        Returns:
            Empty dict on success.
        """
        payload: dict[str, Any] = {
            "resourceArn": resource_arn,
            "tagKeys": tag_keys,
        }

        await self._ecr_request("UntagResource", payload)
        return {}
