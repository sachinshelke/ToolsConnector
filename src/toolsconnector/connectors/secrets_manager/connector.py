"""AWS Secrets Manager connector -- store, rotate, and retrieve secrets.

Uses the Secrets Manager JSON API with ``X-Amz-Target`` headers.  Credentials
should be ``"access_key:secret_key:region"`` format or any format accepted by
``parse_credentials``.

.. note::

    The SigV4 signing implementation is simplified.  For production
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
    SMSecret,
    SMSecretValue,
)

logger = logging.getLogger("toolsconnector.secrets_manager")

_TARGET_PREFIX = "secretsmanager"


class SecretsManager(BaseConnector):
    """Connect to AWS Secrets Manager to store, rotate, and retrieve secrets.

    Credentials format: ``"access_key_id:secret_access_key:region"``
    Uses the Secrets Manager JSON API
    (``X-Amz-Target: secretsmanager.{Action}``).

    .. note::

        SigV4 signing is simplified.  For production, use ``boto3``.
    """

    name = "secrets_manager"
    display_name = "AWS Secrets Manager"
    category = ConnectorCategory.SECURITY
    protocol = ProtocolType.REST
    base_url = "https://secretsmanager.us-east-1.amazonaws.com"
    description = "Store, rotate, and retrieve database credentials, API keys, and other secrets."
    _rate_limit_config = RateLimitSpec(rate=50, period=1, burst=100)

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
        self._host = f"secretsmanager.{self._region}.amazonaws.com"
        self._base_url = f"https://{self._host}"

        self._client = httpx.AsyncClient(timeout=self._timeout)

    async def _teardown(self) -> None:
        """Close the HTTP client."""
        if hasattr(self, "_client"):
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _sm_request(
        self,
        target_action: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a signed Secrets Manager JSON API request.

        Args:
            target_action: Secrets Manager action name
                (e.g. ``GetSecretValue``).
            payload: JSON request body dict.

        Returns:
            Parsed JSON response body.

        Raises:
            NotFoundError: If the secret is not found.
            APIError: For any Secrets Manager API error.
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
            service="secretsmanager",
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
            full_msg = f"SecretsManager {target_action} error: {err_type} - {err_msg}"

            if "ResourceNotFoundException" in err_type or "NotFound" in err_type:
                raise NotFoundError(
                    full_msg,
                    connector="secrets_manager",
                    action=target_action,
                    details=err_body,
                )
            raise APIError(
                full_msg,
                connector="secrets_manager",
                action=target_action,
                upstream_status=response.status_code,
                details=err_body,
            )

        return response.json()

    # ------------------------------------------------------------------
    # Helpers -- parse response models
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_secret(data: dict[str, Any]) -> SMSecret:
        """Parse an API response dict into an SMSecret model."""
        raw_tags = data.get("Tags", [])
        tags: dict[str, str] = {}
        if isinstance(raw_tags, list):
            for t in raw_tags:
                tags[t.get("Key", "")] = t.get("Value", "")
        return SMSecret(
            arn=data.get("ARN", ""),
            name=data.get("Name", ""),
            description=data.get("Description", ""),
            kms_key_id=data.get("KmsKeyId", ""),
            rotation_enabled=data.get("RotationEnabled", False),
            last_rotated_date=(
                str(data["LastRotatedDate"]) if data.get("LastRotatedDate") else None
            ),
            last_changed_date=(
                str(data["LastChangedDate"]) if data.get("LastChangedDate") else None
            ),
            last_accessed_date=(
                str(data["LastAccessedDate"]) if data.get("LastAccessedDate") else None
            ),
            tags=tags,
            created_date=(str(data["CreatedDate"]) if data.get("CreatedDate") else None),
        )

    # ------------------------------------------------------------------
    # Actions -- Secret management
    # ------------------------------------------------------------------

    @action("Create a new secret")
    async def create_secret(
        self,
        name: str,
        secret_string: str = "",
        description: str = "",
        tags: Optional[dict[str, str]] = None,
    ) -> SMSecret:
        """Create a new secret in AWS Secrets Manager.

        Args:
            name: Name for the new secret.
            secret_string: The secret value to store.
            description: Description of the secret.
            tags: Optional dict of tags to apply (key-value pairs).

        Returns:
            SMSecret with the created secret details.
        """
        payload: dict[str, Any] = {"Name": name}
        if secret_string:
            payload["SecretString"] = secret_string
        if description:
            payload["Description"] = description
        if tags:
            payload["Tags"] = [{"Key": k, "Value": v} for k, v in tags.items()]

        body = await self._sm_request("CreateSecret", payload)
        return SMSecret(
            arn=body.get("ARN", ""),
            name=body.get("Name", ""),
            description=description,
            created_date=(str(body["CreatedDate"]) if body.get("CreatedDate") else None),
        )

    @action("Get the value of a secret")
    async def get_secret_value(
        self,
        secret_id: str,
        version_id: str = "",
        version_stage: str = "AWSCURRENT",
    ) -> SMSecretValue:
        """Retrieve the value of a secret.

        Args:
            secret_id: ARN or name of the secret.
            version_id: Specific version ID to retrieve.
            version_stage: Version stage (default: AWSCURRENT).

        Returns:
            SMSecretValue with the secret contents.
        """
        payload: dict[str, Any] = {"SecretId": secret_id}
        if version_id:
            payload["VersionId"] = version_id
        if version_stage:
            payload["VersionStage"] = version_stage

        body = await self._sm_request("GetSecretValue", payload)
        return SMSecretValue(
            arn=body.get("ARN", ""),
            name=body.get("Name", ""),
            version_id=body.get("VersionId", ""),
            secret_string=body.get("SecretString", ""),
            secret_binary=body.get("SecretBinary"),
            version_stages=body.get("VersionStages", []),
            created_date=(str(body["CreatedDate"]) if body.get("CreatedDate") else None),
        )

    @action("Update the value of a secret")
    async def put_secret_value(
        self,
        secret_id: str,
        secret_string: str,
    ) -> dict:
        """Update the value of an existing secret.

        Args:
            secret_id: ARN or name of the secret.
            secret_string: The new secret value.

        Returns:
            Dict with ARN, Name, VersionId, and VersionStages.
        """
        payload: dict[str, Any] = {
            "SecretId": secret_id,
            "SecretString": secret_string,
        }

        body = await self._sm_request("PutSecretValue", payload)
        return {
            "arn": body.get("ARN", ""),
            "name": body.get("Name", ""),
            "version_id": body.get("VersionId", ""),
            "version_stages": body.get("VersionStages", []),
        }

    @action("Update secret metadata")
    async def update_secret(
        self,
        secret_id: str,
        description: str = "",
        kms_key_id: str = "",
    ) -> dict:
        """Update secret metadata (description or KMS key).

        Args:
            secret_id: ARN or name of the secret.
            description: New description for the secret.
            kms_key_id: New KMS key ID for encryption.

        Returns:
            Dict with ARN and Name.
        """
        payload: dict[str, Any] = {"SecretId": secret_id}
        if description:
            payload["Description"] = description
        if kms_key_id:
            payload["KmsKeyId"] = kms_key_id

        body = await self._sm_request("UpdateSecret", payload)
        return {
            "arn": body.get("ARN", ""),
            "name": body.get("Name", ""),
        }

    @action("Delete a secret", dangerous=True)
    async def delete_secret(
        self,
        secret_id: str,
        recovery_window_in_days: int = 30,
        force_delete: bool = False,
    ) -> dict:
        """Delete a secret (with optional recovery window).

        Args:
            secret_id: ARN or name of the secret.
            recovery_window_in_days: Number of days before permanent
                deletion (7-30). Ignored if force_delete is True.
            force_delete: If True, delete immediately without recovery.

        Returns:
            Dict with ARN, Name, and DeletionDate.
        """
        payload: dict[str, Any] = {"SecretId": secret_id}
        if force_delete:
            payload["ForceDeleteWithoutRecovery"] = True
        else:
            payload["RecoveryWindowInDays"] = recovery_window_in_days

        body = await self._sm_request("DeleteSecret", payload)
        return {
            "arn": body.get("ARN", ""),
            "name": body.get("Name", ""),
            "deletion_date": (str(body["DeletionDate"]) if body.get("DeletionDate") else None),
        }

    @action("Restore a deleted secret")
    async def restore_secret(
        self,
        secret_id: str,
    ) -> dict:
        """Restore a previously deleted secret.

        Args:
            secret_id: ARN or name of the secret to restore.

        Returns:
            Dict with ARN and Name.
        """
        payload: dict[str, Any] = {"SecretId": secret_id}

        body = await self._sm_request("RestoreSecret", payload)
        return {
            "arn": body.get("ARN", ""),
            "name": body.get("Name", ""),
        }

    @action("Describe a secret")
    async def describe_secret(
        self,
        secret_id: str,
    ) -> SMSecret:
        """Get metadata about a secret (not the value).

        Args:
            secret_id: ARN or name of the secret.

        Returns:
            SMSecret with full metadata.
        """
        payload: dict[str, Any] = {"SecretId": secret_id}

        body = await self._sm_request("DescribeSecret", payload)
        return self._parse_secret(body)

    @action("List secrets")
    async def list_secrets(
        self,
        max_results: int = 100,
    ) -> list[SMSecret]:
        """List all secrets in the account.

        Args:
            max_results: Maximum number of secrets to return (1-100).

        Returns:
            List of SMSecret objects.
        """
        payload: dict[str, Any] = {"MaxResults": max_results}

        body = await self._sm_request("ListSecrets", payload)
        secrets = body.get("SecretList", [])
        return [self._parse_secret(s) for s in secrets]

    # ------------------------------------------------------------------
    # Actions -- Rotation
    # ------------------------------------------------------------------

    @action("Trigger secret rotation")
    async def rotate_secret(
        self,
        secret_id: str,
        rotation_lambda_arn: str = "",
    ) -> dict:
        """Trigger rotation for a secret.

        Args:
            secret_id: ARN or name of the secret.
            rotation_lambda_arn: ARN of the Lambda function that
                performs the rotation. Required for first rotation.

        Returns:
            Dict with ARN, Name, and VersionId.
        """
        payload: dict[str, Any] = {"SecretId": secret_id}
        if rotation_lambda_arn:
            payload["RotationLambdaARN"] = rotation_lambda_arn

        body = await self._sm_request("RotateSecret", payload)
        return {
            "arn": body.get("ARN", ""),
            "name": body.get("Name", ""),
            "version_id": body.get("VersionId", ""),
        }

    # ------------------------------------------------------------------
    # Actions -- Tagging
    # ------------------------------------------------------------------

    @action("Add tags to a secret")
    async def tag_resource(
        self,
        secret_id: str,
        tags: list[dict],
    ) -> dict:
        """Add tags to a secret.

        Args:
            secret_id: ARN or name of the secret to tag.
            tags: List of tag dicts, each with Key and Value.

        Returns:
            Empty dict on success.
        """
        payload: dict[str, Any] = {
            "SecretId": secret_id,
            "Tags": tags,
        }

        await self._sm_request("TagResource", payload)
        return {}

    @action("Remove tags from a secret")
    async def untag_resource(
        self,
        secret_id: str,
        tag_keys: list[str],
    ) -> dict:
        """Remove tags from a secret.

        Args:
            secret_id: ARN or name of the secret to untag.
            tag_keys: List of tag keys to remove.

        Returns:
            Empty dict on success.
        """
        payload: dict[str, Any] = {
            "SecretId": secret_id,
            "TagKeys": tag_keys,
        }

        await self._sm_request("UntagResource", payload)
        return {}

    # ------------------------------------------------------------------
    # Actions -- Utilities
    # ------------------------------------------------------------------

    @action("Generate a random password")
    async def get_random_password(
        self,
        password_length: int = 32,
        exclude_characters: str = "",
        exclude_numbers: bool = False,
        exclude_punctuation: bool = False,
        exclude_uppercase: bool = False,
        exclude_lowercase: bool = False,
    ) -> str:
        """Generate a random password using AWS Secrets Manager.

        Args:
            password_length: Length of the password (default: 32).
            exclude_characters: Characters to exclude.
            exclude_numbers: If True, exclude digits.
            exclude_punctuation: If True, exclude punctuation.
            exclude_uppercase: If True, exclude uppercase letters.
            exclude_lowercase: If True, exclude lowercase letters.

        Returns:
            The generated random password string.
        """
        payload: dict[str, Any] = {
            "PasswordLength": password_length,
        }
        if exclude_characters:
            payload["ExcludeCharacters"] = exclude_characters
        if exclude_numbers:
            payload["ExcludeNumbers"] = True
        if exclude_punctuation:
            payload["ExcludePunctuation"] = True
        if exclude_uppercase:
            payload["ExcludeUppercase"] = True
        if exclude_lowercase:
            payload["ExcludeLowercase"] = True

        body = await self._sm_request("GetRandomPassword", payload)
        return body.get("RandomPassword", "")
