"""AWS Lambda connector -- deploy, invoke, and manage serverless functions.

Uses the Lambda REST API with SigV4-signed requests. Credentials should be
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

from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import (
    ConnectorCategory,
    ProtocolType,
    RateLimitSpec,
)
from toolsconnector.errors import APIError, NotFoundError

from toolsconnector.connectors._aws.signing import sign_v4

from .types import (
    LambdaAlias,
    LambdaFunction,
    LambdaFunctionVersion,
    LambdaInvocationResult,
)

logger = logging.getLogger("toolsconnector.lambda_connector")

# Lambda REST API version prefix
_API_VERSION = "2015-03-31"


def _parse_function(data: dict[str, Any]) -> LambdaFunction:
    """Map a Lambda API PascalCase response to a ``LambdaFunction``."""
    env = data.get("Environment", {})
    env_vars = env.get("Variables", {}) if isinstance(env, dict) else {}

    layers_raw = data.get("Layers", [])
    layer_arns = [
        layer.get("Arn", "") for layer in layers_raw if isinstance(layer, dict)
    ]

    return LambdaFunction(
        function_name=data.get("FunctionName", ""),
        function_arn=data.get("FunctionArn", ""),
        runtime=data.get("Runtime", ""),
        role=data.get("Role", ""),
        handler=data.get("Handler", ""),
        code_size=data.get("CodeSize", 0),
        description=data.get("Description", ""),
        timeout=data.get("Timeout", 0),
        memory_size=data.get("MemorySize", 0),
        last_modified=data.get("LastModified", ""),
        version=data.get("Version", ""),
        state=data.get("State", ""),
        state_reason=data.get("StateReason", ""),
        architectures=data.get("Architectures", []),
        environment=env_vars,
        layers=layer_arns,
        package_type=data.get("PackageType", ""),
    )


def _parse_version(data: dict[str, Any]) -> LambdaFunctionVersion:
    """Map a Lambda API PascalCase response to a ``LambdaFunctionVersion``."""
    return LambdaFunctionVersion(
        function_name=data.get("FunctionName", ""),
        function_arn=data.get("FunctionArn", ""),
        version=data.get("Version", ""),
        description=data.get("Description", ""),
        runtime=data.get("Runtime", ""),
        handler=data.get("Handler", ""),
        code_size=data.get("CodeSize", 0),
        last_modified=data.get("LastModified", ""),
    )


def _parse_alias(data: dict[str, Any]) -> LambdaAlias:
    """Map a Lambda API PascalCase response to a ``LambdaAlias``."""
    return LambdaAlias(
        alias_arn=data.get("AliasArn", ""),
        name=data.get("Name", ""),
        function_version=data.get("FunctionVersion", ""),
        description=data.get("Description", ""),
    )


class Lambda(BaseConnector):
    """Connect to AWS Lambda to deploy, invoke, and manage serverless functions.

    Credentials format: ``"access_key_id:secret_access_key:region"``
    Uses the Lambda REST API with SigV4 signing.

    .. note::

        SigV4 signing is simplified. For production, use ``boto3``.
    """

    name = "lambda_connector"
    display_name = "AWS Lambda"
    category = ConnectorCategory.COMPUTE
    protocol = ProtocolType.REST
    base_url = "https://lambda.us-east-1.amazonaws.com"
    description = "Deploy, invoke, and manage serverless functions."
    _rate_limit_config = RateLimitSpec(rate=100, period=1, burst=500)

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
        self._host = f"lambda.{self._region}.amazonaws.com"
        self._endpoint = f"https://{self._host}"

        self._client = httpx.AsyncClient(timeout=self._timeout)

    async def _teardown(self) -> None:
        """Close the HTTP client."""
        if hasattr(self, "_client"):
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _lambda_request(
        self,
        method: str,
        path: str,
        body: dict | bytes | None = None,
    ) -> httpx.Response:
        """Send a SigV4-signed REST request to the Lambda API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE).
            path: API path (e.g. ``/2015-03-31/functions``).
            body: Optional JSON dict or raw bytes for the request body.

        Returns:
            The httpx Response object.

        Raises:
            NotFoundError: If the function or resource is not found.
            APIError: For any Lambda API error.
        """
        url = f"{self._endpoint}{path}"

        if isinstance(body, dict):
            body_bytes = json.dumps(body).encode()
            content_type = "application/json"
        elif isinstance(body, bytes):
            body_bytes = body
            content_type = "application/octet-stream"
        else:
            body_bytes = b""
            content_type = "application/json"

        payload_hash = hashlib.sha256(body_bytes).hexdigest()
        now = datetime.datetime.now(datetime.timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")

        headers: dict[str, str] = {
            "host": self._host,
            "x-amz-date": amz_date,
            "x-amz-content-sha256": payload_hash,
        }
        if body_bytes:
            headers["content-type"] = content_type

        sign_v4(
            method,
            url,
            headers,
            payload_hash,
            self._access_key,
            self._secret_key,
            self._region,
            service="lambda",
            session_token=self._session_token,
        )

        resp = await self._client.request(
            method, url, content=body_bytes, headers=headers,
        )

        if resp.status_code >= 400:
            try:
                err_body = resp.json()
            except Exception:
                err_body = {"message": resp.text}

            err_type = err_body.get("Type", err_body.get("__type", ""))
            err_msg = err_body.get("Message", err_body.get("message", ""))
            full_msg = f"Lambda {method} {path} error: {err_type} - {err_msg}"

            if "ResourceNotFoundException" in err_type or "NotFound" in err_type:
                raise NotFoundError(
                    full_msg,
                    connector="lambda_connector",
                    action=f"{method} {path}",
                    details=err_body,
                )
            raise APIError(
                full_msg,
                connector="lambda_connector",
                action=f"{method} {path}",
                upstream_status=resp.status_code,
                details=err_body,
            )

        return resp

    # ------------------------------------------------------------------
    # Actions -- Function management
    # ------------------------------------------------------------------

    @action("Create a Lambda function", dangerous=True)
    async def create_function(
        self,
        function_name: str,
        runtime: str = "python3.12",
        role: str = "",
        handler: str = "lambda_function.handler",
        zip_file_base64: str = "",
        s3_bucket: str = "",
        s3_key: str = "",
        description: str = "",
        timeout: int = 30,
        memory_size: int = 128,
        environment: Optional[dict] = None,
        architectures: Optional[list[str]] = None,
    ) -> LambdaFunction:
        """Create a new Lambda function.

        Args:
            function_name: Name for the new function.
            runtime: Runtime identifier (e.g. python3.12, nodejs20.x).
            role: IAM role ARN for the function's execution role.
            handler: Function entry point (module.function).
            zip_file_base64: Base64-encoded ZIP deployment package.
            s3_bucket: S3 bucket containing the deployment package.
            s3_key: S3 key of the deployment package.
            description: Description of the function.
            timeout: Execution timeout in seconds (1-900).
            memory_size: Memory allocation in MB (128-10240).
            environment: Environment variables as key-value pairs.
            architectures: Instruction set architectures (x86_64, arm64).

        Returns:
            LambdaFunction with the created function details.
        """
        code: dict[str, Any] = {}
        if zip_file_base64:
            code["ZipFile"] = zip_file_base64
        elif s3_bucket and s3_key:
            code["S3Bucket"] = s3_bucket
            code["S3Key"] = s3_key

        payload: dict[str, Any] = {
            "FunctionName": function_name,
            "Runtime": runtime,
            "Role": role,
            "Handler": handler,
            "Code": code,
            "Description": description,
            "Timeout": timeout,
            "MemorySize": memory_size,
        }

        if environment:
            payload["Environment"] = {"Variables": environment}
        if architectures:
            payload["Architectures"] = architectures

        resp = await self._lambda_request(
            "POST", f"/{_API_VERSION}/functions", body=payload,
        )
        return _parse_function(resp.json())

    @action("Get a Lambda function")
    async def get_function(self, function_name: str) -> LambdaFunction:
        """Get details of a Lambda function.

        Args:
            function_name: Name or ARN of the function.

        Returns:
            LambdaFunction with the function details.
        """
        resp = await self._lambda_request(
            "GET", f"/{_API_VERSION}/functions/{function_name}",
        )
        data = resp.json()
        # GET function returns {"Configuration": {...}, "Code": {...}, ...}
        config = data.get("Configuration", data)
        return _parse_function(config)

    @action("List Lambda functions")
    async def list_functions(self, max_items: int = 50) -> list[LambdaFunction]:
        """List Lambda functions in the account.

        Args:
            max_items: Maximum number of functions to return.

        Returns:
            List of LambdaFunction objects.
        """
        resp = await self._lambda_request(
            "GET", f"/{_API_VERSION}/functions?MaxItems={max_items}",
        )
        data = resp.json()
        functions = data.get("Functions", [])
        return [_parse_function(f) for f in functions]

    @action("Update function code")
    async def update_function_code(
        self,
        function_name: str,
        s3_bucket: str = "",
        s3_key: str = "",
        zip_file_base64: str = "",
        architectures: Optional[list[str]] = None,
    ) -> LambdaFunction:
        """Update a function's deployment package.

        Args:
            function_name: Name or ARN of the function.
            s3_bucket: S3 bucket containing the new deployment package.
            s3_key: S3 key of the new deployment package.
            zip_file_base64: Base64-encoded ZIP deployment package.
            architectures: Instruction set architectures (x86_64, arm64).

        Returns:
            LambdaFunction with the updated function details.
        """
        payload: dict[str, Any] = {"FunctionName": function_name}

        if zip_file_base64:
            payload["ZipFile"] = zip_file_base64
        elif s3_bucket and s3_key:
            payload["S3Bucket"] = s3_bucket
            payload["S3Key"] = s3_key

        if architectures:
            payload["Architectures"] = architectures

        resp = await self._lambda_request(
            "PUT",
            f"/{_API_VERSION}/functions/{function_name}/code",
            body=payload,
        )
        return _parse_function(resp.json())

    @action("Update function configuration")
    async def update_function_configuration(
        self,
        function_name: str,
        runtime: str = "",
        handler: str = "",
        description: str = "",
        timeout: int = 0,
        memory_size: int = 0,
        environment: Optional[dict] = None,
        role: str = "",
    ) -> LambdaFunction:
        """Update a function's configuration settings.

        Args:
            function_name: Name or ARN of the function.
            runtime: Runtime identifier to update.
            handler: New function entry point.
            description: New description.
            timeout: New timeout in seconds (0 means no change).
            memory_size: New memory allocation in MB (0 means no change).
            environment: New environment variables (replaces existing).
            role: New IAM role ARN.

        Returns:
            LambdaFunction with the updated configuration.
        """
        payload: dict[str, Any] = {}

        if runtime:
            payload["Runtime"] = runtime
        if handler:
            payload["Handler"] = handler
        if description:
            payload["Description"] = description
        if timeout:
            payload["Timeout"] = timeout
        if memory_size:
            payload["MemorySize"] = memory_size
        if environment is not None:
            payload["Environment"] = {"Variables": environment}
        if role:
            payload["Role"] = role

        resp = await self._lambda_request(
            "PUT",
            f"/{_API_VERSION}/functions/{function_name}/configuration",
            body=payload,
        )
        return _parse_function(resp.json())

    @action("Delete a Lambda function", dangerous=True)
    async def delete_function(self, function_name: str) -> dict:
        """Delete a Lambda function.

        Args:
            function_name: Name or ARN of the function to delete.

        Returns:
            Empty dict on success.
        """
        await self._lambda_request(
            "DELETE", f"/{_API_VERSION}/functions/{function_name}",
        )
        return {}

    @action("Get function configuration")
    async def get_function_configuration(
        self, function_name: str,
    ) -> LambdaFunction:
        """Get the configuration of a Lambda function.

        Args:
            function_name: Name or ARN of the function.

        Returns:
            LambdaFunction with the function configuration.
        """
        resp = await self._lambda_request(
            "GET",
            f"/{_API_VERSION}/functions/{function_name}/configuration",
        )
        return _parse_function(resp.json())

    # ------------------------------------------------------------------
    # Actions -- Invocation
    # ------------------------------------------------------------------

    @action("Invoke a Lambda function")
    async def invoke(
        self,
        function_name: str,
        payload: str = "{}",
        invocation_type: str = "RequestResponse",
        log_type: str = "None",
    ) -> LambdaInvocationResult:
        """Invoke a Lambda function.

        Args:
            function_name: Name or ARN of the function to invoke.
            payload: JSON string to send as the function input.
            invocation_type: Invocation type (RequestResponse, Event,
                or DryRun).
            log_type: Log type (None or Tail). Tail returns the last
                4 KB of execution logs.

        Returns:
            LambdaInvocationResult with the invocation response.
        """
        path = f"/{_API_VERSION}/functions/{function_name}/invocations"
        url = f"{self._endpoint}{path}"
        body_bytes = payload.encode()

        payload_hash = hashlib.sha256(body_bytes).hexdigest()
        now = datetime.datetime.now(datetime.timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")

        headers: dict[str, str] = {
            "host": self._host,
            "x-amz-date": amz_date,
            "x-amz-content-sha256": payload_hash,
            "content-type": "application/json",
            "X-Amz-Invocation-Type": invocation_type,
            "X-Amz-Log-Type": log_type,
        }

        sign_v4(
            "POST",
            url,
            headers,
            payload_hash,
            self._access_key,
            self._secret_key,
            self._region,
            service="lambda",
            session_token=self._session_token,
        )

        resp = await self._client.request(
            "POST", url, content=body_bytes, headers=headers,
        )

        if resp.status_code >= 400:
            try:
                err_body = resp.json()
            except Exception:
                err_body = {"message": resp.text}

            err_type = err_body.get("Type", err_body.get("__type", ""))
            err_msg = err_body.get("Message", err_body.get("message", ""))
            full_msg = f"Lambda invoke error: {err_type} - {err_msg}"

            raise APIError(
                full_msg,
                connector="lambda_connector",
                action="invoke",
                upstream_status=resp.status_code,
                details=err_body,
            )

        # Response payload may be raw text, not JSON
        response_payload = resp.text

        return LambdaInvocationResult(
            status_code=resp.status_code,
            payload=response_payload,
            function_error=resp.headers.get("X-Amz-Function-Error"),
            log_result=resp.headers.get("X-Amz-Log-Result"),
            executed_version=resp.headers.get("X-Amz-Executed-Version"),
        )

    # ------------------------------------------------------------------
    # Actions -- Versions
    # ------------------------------------------------------------------

    @action("Publish a function version")
    async def publish_version(
        self,
        function_name: str,
        description: str = "",
    ) -> LambdaFunctionVersion:
        """Publish a new version of a Lambda function.

        Args:
            function_name: Name or ARN of the function.
            description: Description for the new version.

        Returns:
            LambdaFunctionVersion with the published version details.
        """
        payload: dict[str, Any] = {}
        if description:
            payload["Description"] = description

        resp = await self._lambda_request(
            "POST",
            f"/{_API_VERSION}/functions/{function_name}/versions",
            body=payload,
        )
        return _parse_version(resp.json())

    @action("List function versions")
    async def list_versions_by_function(
        self, function_name: str,
    ) -> list[LambdaFunctionVersion]:
        """List all published versions of a Lambda function.

        Args:
            function_name: Name or ARN of the function.

        Returns:
            List of LambdaFunctionVersion objects.
        """
        resp = await self._lambda_request(
            "GET",
            f"/{_API_VERSION}/functions/{function_name}/versions",
        )
        data = resp.json()
        versions = data.get("Versions", [])
        return [_parse_version(v) for v in versions]

    # ------------------------------------------------------------------
    # Actions -- Aliases
    # ------------------------------------------------------------------

    @action("Create a function alias")
    async def create_alias(
        self,
        function_name: str,
        name: str,
        function_version: str,
        description: str = "",
    ) -> LambdaAlias:
        """Create an alias for a Lambda function version.

        Args:
            function_name: Name or ARN of the function.
            name: Name for the alias.
            function_version: Function version the alias points to.
            description: Description for the alias.

        Returns:
            LambdaAlias with the created alias details.
        """
        payload: dict[str, Any] = {
            "Name": name,
            "FunctionVersion": function_version,
        }
        if description:
            payload["Description"] = description

        resp = await self._lambda_request(
            "POST",
            f"/{_API_VERSION}/functions/{function_name}/aliases",
            body=payload,
        )
        return _parse_alias(resp.json())

    @action("Get a function alias")
    async def get_alias(
        self,
        function_name: str,
        name: str,
    ) -> LambdaAlias:
        """Get details of a Lambda function alias.

        Args:
            function_name: Name or ARN of the function.
            name: Name of the alias.

        Returns:
            LambdaAlias with the alias details.
        """
        resp = await self._lambda_request(
            "GET",
            f"/{_API_VERSION}/functions/{function_name}/aliases/{name}",
        )
        return _parse_alias(resp.json())

    @action("List function aliases")
    async def list_aliases(
        self, function_name: str,
    ) -> list[LambdaAlias]:
        """List all aliases for a Lambda function.

        Args:
            function_name: Name or ARN of the function.

        Returns:
            List of LambdaAlias objects.
        """
        resp = await self._lambda_request(
            "GET",
            f"/{_API_VERSION}/functions/{function_name}/aliases",
        )
        data = resp.json()
        aliases = data.get("Aliases", [])
        return [_parse_alias(a) for a in aliases]

    # ------------------------------------------------------------------
    # Actions -- Permissions
    # ------------------------------------------------------------------

    @action("Add a permission to a function's resource policy")
    async def add_permission(
        self,
        function_name: str,
        statement_id: str,
        action_name: str = "lambda:InvokeFunction",
        principal: str = "",
        source_arn: str = "",
    ) -> dict:
        """Add a permission statement to a function's resource-based policy.

        Args:
            function_name: Name or ARN of the function.
            statement_id: Unique identifier for the policy statement.
            action_name: Lambda action to allow (e.g. lambda:InvokeFunction).
            principal: AWS service or account to grant access.
            source_arn: ARN of the resource triggering the function.

        Returns:
            Dict with the policy statement.
        """
        payload: dict[str, Any] = {
            "StatementId": statement_id,
            "Action": action_name,
            "Principal": principal,
        }
        if source_arn:
            payload["SourceArn"] = source_arn

        resp = await self._lambda_request(
            "POST",
            f"/{_API_VERSION}/functions/{function_name}/policy",
            body=payload,
        )
        return resp.json()

    @action("Remove a permission from a function's resource policy")
    async def remove_permission(
        self,
        function_name: str,
        statement_id: str,
    ) -> dict:
        """Remove a permission statement from a function's resource-based policy.

        Args:
            function_name: Name or ARN of the function.
            statement_id: Identifier of the statement to remove.

        Returns:
            Empty dict on success.
        """
        await self._lambda_request(
            "DELETE",
            f"/{_API_VERSION}/functions/{function_name}/policy/{statement_id}",
        )
        return {}
