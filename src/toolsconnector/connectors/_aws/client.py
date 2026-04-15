"""AWS base HTTP client with SigV4 signing.

Provides ``AWSBaseClient`` -- a shared async HTTP client that handles
the three AWS API styles:

* **REST** (``request``) -- S3, CloudFront, Route 53, Lambda
* **JSON** (``json_request``) -- ECS, ECR, CloudWatch, Secrets Manager, ACM
* **Query** (``query_request``) -- EC2, ALB/ELBv2, IAM, RDS

All methods perform SigV4 signing automatically using the configured
service name and credentials.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import urllib.parse
from typing import Optional

import httpx

from .auth import AWSCredentials
from .errors import AWSError, format_access_denied_hint, parse_aws_error
from .regions import get_endpoint
from .signing import sign_v4


class AWSBaseClient:
    """Async HTTP client with automatic SigV4 signing for AWS APIs.

    Instantiate with an ``AWSCredentials`` object and a service name.
    The client derives its endpoint URL from the service and region
    unless overridden.

    Args:
        credentials: Parsed ``AWSCredentials`` instance.
        service: AWS service name (lowercase), e.g. ``"ecs"``.
        region: Override the region from *credentials*. Useful when a
            connector needs to talk to a different region than the
            default.
        timeout: HTTP request timeout in seconds.
    """

    def __init__(
        self,
        credentials: AWSCredentials,
        service: str,
        region: Optional[str] = None,
        timeout: float = 30.0,
    ) -> None:
        self._creds = credentials
        self._service = service
        self._region = region or credentials.region
        self._timeout = timeout
        self._endpoint = get_endpoint(service, self._region)
        self._client = httpx.AsyncClient(timeout=timeout)

    # ------------------------------------------------------------------
    # REST-style requests (S3, CloudFront, Route 53, Lambda)
    # ------------------------------------------------------------------

    async def request(
        self,
        method: str,
        url: str,
        *,
        body: bytes = b"",
        headers: Optional[dict[str, str]] = None,
    ) -> httpx.Response:
        """Send a SigV4-signed REST request.

        Adds the required ``x-amz-date``, ``Host``, and
        ``x-amz-content-sha256`` headers, signs the request, and
        sends it.

        Args:
            method: HTTP method (``GET``, ``PUT``, ``POST``, etc.).
            url: Full request URL.
            body: Request body bytes (default empty).
            headers: Additional headers to include.

        Returns:
            ``httpx.Response`` object.

        Raises:
            AWSError: On 4xx/5xx responses.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")

        parsed = urllib.parse.urlparse(url)
        host = parsed.netloc or parsed.hostname or ""

        payload_hash = hashlib.sha256(body).hexdigest()

        req_headers: dict[str, str] = {
            "Host": host,
            "x-amz-date": amz_date,
            "x-amz-content-sha256": payload_hash,
        }
        if headers:
            req_headers.update(headers)

        sign_v4(
            method,
            url,
            req_headers,
            payload_hash,
            self._creds.access_key_id,
            self._creds.secret_access_key,
            self._region,
            self._service,
            session_token=self._creds.session_token,
        )

        resp = await self._client.request(
            method, url, headers=req_headers, content=body,
        )
        if resp.status_code >= 400:
            await self._handle_error(resp)
        return resp

    # ------------------------------------------------------------------
    # JSON API requests (ECS, ECR, CloudWatch, Secrets Manager, ACM)
    # ------------------------------------------------------------------

    async def json_request(
        self,
        target: str,
        payload: dict,
        *,
        target_prefix: str,
        json_version: str = "1.1",
    ) -> dict:
        """Send a JSON API request with ``X-Amz-Target``.

        Used by services that follow the ``X-Amz-Target`` convention
        (ECS, ECR, CloudWatch Logs, Secrets Manager, ACM, etc.).

        Args:
            target: Action name (e.g. ``"ListTasks"``).
            payload: Request body as a Python dict.
            target_prefix: Service-specific target prefix
                (e.g. ``"AmazonEC2ContainerServiceV20141113"``).
            json_version: JSON content-type version (default
                ``"1.1"``). Some services use ``"1.0"``.

        Returns:
            Parsed JSON response body as a dict.

        Raises:
            AWSError: On 4xx/5xx responses.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")

        body_str = json.dumps(payload)
        body_bytes = body_str.encode("utf-8")
        payload_hash = hashlib.sha256(body_bytes).hexdigest()

        endpoint = self._get_endpoint()
        parsed = urllib.parse.urlparse(endpoint)
        host = parsed.netloc or parsed.hostname or ""

        req_headers: dict[str, str] = {
            "Content-Type": f"application/x-amz-json-{json_version}",
            "X-Amz-Target": f"{target_prefix}.{target}",
            "X-Amz-Date": amz_date,
            "Host": host,
            "x-amz-content-sha256": payload_hash,
        }

        # Normalise x-amz-date casing for signing consistency.
        req_headers["x-amz-date"] = amz_date

        sign_v4(
            "POST",
            endpoint + "/",
            req_headers,
            payload_hash,
            self._creds.access_key_id,
            self._creds.secret_access_key,
            self._region,
            self._service,
            session_token=self._creds.session_token,
        )

        resp = await self._client.post(
            endpoint + "/",
            content=body_bytes,
            headers=req_headers,
        )
        if resp.status_code >= 400:
            await self._handle_error(resp, action=target)
        return resp.json()

    # ------------------------------------------------------------------
    # Query API requests (EC2, ALB/ELBv2, IAM, RDS)
    # ------------------------------------------------------------------

    async def query_request(
        self,
        action: str,
        params: dict,
        *,
        api_version: str,
    ) -> str:
        """Send a Query API request.

        Used by services that follow the ``Action=`` / ``Version=``
        form-encoded convention (EC2, ELBv2, IAM, RDS, Auto Scaling,
        etc.).

        Args:
            action: API action name (e.g. ``"DescribeInstances"``).
            params: Additional query parameters as key-value pairs.
            api_version: API version string
                (e.g. ``"2016-11-15"`` for EC2).

        Returns:
            Raw XML response body string.

        Raises:
            AWSError: On 4xx/5xx responses.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")

        form_params: dict[str, str] = {
            "Action": action,
            "Version": api_version,
        }
        form_params.update({k: str(v) for k, v in params.items()})

        body_str = urllib.parse.urlencode(
            sorted(form_params.items()),
            quote_via=urllib.parse.quote,
        )
        body_bytes = body_str.encode("utf-8")
        payload_hash = hashlib.sha256(body_bytes).hexdigest()

        endpoint = self._get_endpoint()
        parsed = urllib.parse.urlparse(endpoint)
        host = parsed.netloc or parsed.hostname or ""

        req_headers: dict[str, str] = {
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
            "Host": host,
            "x-amz-date": amz_date,
            "x-amz-content-sha256": payload_hash,
        }

        sign_v4(
            "POST",
            endpoint + "/",
            req_headers,
            payload_hash,
            self._creds.access_key_id,
            self._creds.secret_access_key,
            self._region,
            self._service,
            session_token=self._creds.session_token,
        )

        resp = await self._client.post(
            endpoint + "/",
            content=body_bytes,
            headers=req_headers,
        )
        if resp.status_code >= 400:
            await self._handle_error(resp, action=action)
        return resp.text

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_endpoint(self) -> str:
        """Get the service endpoint URL.

        Returns:
            Endpoint URL string from the regions module.
        """
        return self._endpoint

    async def _handle_error(
        self,
        response: httpx.Response,
        action: Optional[str] = None,
    ) -> None:
        """Parse an AWS error response and raise ``AWSError``.

        Attempts to parse both JSON and XML error formats, and
        attaches an IAM permission hint when the error is
        access-related.

        Args:
            response: The HTTP response with a 4xx/5xx status.
            action: The API action that caused the error (for IAM hint
                lookup).

        Raises:
            AWSError: Always raised with parsed error details.
        """
        content_type = response.headers.get("content-type", "")
        parsed = parse_aws_error(response.text, content_type)

        error_code = parsed.get("code") or f"HTTP{response.status_code}"
        message = parsed.get("message") or response.text

        # Generate IAM hint for access-denied errors.
        iam_hint: Optional[str] = None
        if error_code and action:
            code_lower = error_code.lower()
            if any(
                term in code_lower
                for term in ("accessdenied", "unauthorized", "forbidden")
            ):
                iam_hint = format_access_denied_hint(self._service, action)

        raise AWSError(
            status_code=response.status_code,
            error_code=error_code,
            message=message,
            iam_hint=iam_hint,
        )

    async def close(self) -> None:
        """Close the underlying HTTP client.

        Should be called when the client is no longer needed to
        release connection resources.
        """
        await self._client.aclose()
