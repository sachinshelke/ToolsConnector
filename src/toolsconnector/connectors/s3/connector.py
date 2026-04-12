"""AWS S3 connector — buckets, objects, and metadata operations.

Uses the S3 REST API with AWS Signature Version 4 authentication.
Credentials should be a JSON string or dict containing ``access_key_id``,
``secret_access_key``, and optionally ``region`` (defaults to ``us-east-1``).

S3 responses are XML-formatted and parsed with ``xml.etree.ElementTree``.

.. note::

    The SigV4 implementation is simplified for common operations.
    For production workloads, consider using ``boto3`` via
    ``extras_require``.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any, Optional

import httpx

from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import (
    ConnectorCategory,
    ProtocolType,
    RateLimitSpec,
)
from toolsconnector.types import PageState, PaginatedList

from ._helpers import (
    build_presigned_url,
    build_tagging_xml,
    compute_content_md5,
    extract_user_metadata as _extract_user_metadata,
    find_text as _find_text,
)
from ._signing import sign_v4
from .types import (
    S3Bucket,
    S3BucketLocation,
    S3BucketPolicy,
    S3BucketVersioning,
    S3CopyResult,
    S3MultipartUpload,
    S3Object,
    S3ObjectData,
    S3ObjectMetadata,
    S3ObjectTagSet,
    S3ObjectVersion,
    S3PresignedUrl,
    S3PutResult,
)

logger = logging.getLogger("toolsconnector.s3")

_S3_NS = "http://s3.amazonaws.com/doc/2006-03-01/"


class S3(BaseConnector):
    """Connect to AWS S3 to manage buckets and objects.

    Authenticates using AWS Signature Version 4. Credentials should be
    provided as a JSON string or dict::

        {
            "access_key_id": "AKIA...",
            "secret_access_key": "...",
            "region": "us-east-1"
        }

    For production use, ``boto3`` is recommended via ``extras_require``.
    """

    name = "s3"
    display_name = "AWS S3"
    category = ConnectorCategory.STORAGE
    protocol = ProtocolType.REST
    base_url = "https://s3.us-east-1.amazonaws.com"
    description = (
        "Connect to AWS S3 to list buckets, manage objects, "
        "upload/download files, and copy objects between buckets."
    )
    _rate_limit_config = RateLimitSpec(rate=5500, period=1, burst=1000)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Initialise credentials and httpx client."""
        creds = self._credentials or {}
        if isinstance(creds, str):
            creds = json.loads(creds)

        self._access_key_id: str = creds.get("access_key_id", "")
        self._secret_access_key: str = creds.get("secret_access_key", "")
        self._region: str = creds.get("region", "us-east-1")
        self._host = f"s3.{self._region}.amazonaws.com"

        self._client = httpx.AsyncClient(
            timeout=self._timeout,
            base_url=self._base_url or f"https://{self._host}",
        )

    async def _teardown(self) -> None:
        """Close the httpx client."""
        if hasattr(self, "_client"):
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _bucket_host(self, bucket: str) -> str:
        """Get the virtual-hosted-style host for a bucket.

        Args:
            bucket: S3 bucket name.

        Returns:
            Host string like ``bucket.s3.region.amazonaws.com``.
        """
        return f"{bucket}.s3.{self._region}.amazonaws.com"

    async def _s3_request(
        self,
        method: str,
        path: str,
        *,
        host: Optional[str] = None,
        params: Optional[dict[str, Any]] = None,
        body: bytes = b"",
        extra_headers: Optional[dict[str, str]] = None,
    ) -> httpx.Response:
        """Send a SigV4-signed request to S3.

        Args:
            method: HTTP method.
            path: URL path (e.g. ``/bucket/key``).
            host: Override host header (for bucket-specific requests).
            params: Query parameters.
            body: Request body bytes.
            extra_headers: Additional headers to include.

        Returns:
            httpx.Response object.

        Raises:
            httpx.HTTPStatusError: On 4xx/5xx responses.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        resolved_host = host or self._host
        payload_hash = hashlib.sha256(body).hexdigest()

        headers: dict[str, str] = {
            "Host": resolved_host,
            "x-amz-date": amz_date,
            "x-amz-content-sha256": payload_hash,
        }
        if extra_headers:
            headers.update(extra_headers)

        qs = ""
        if params:
            qs = "?" + urllib.parse.urlencode(
                params, quote_via=urllib.parse.quote,
            )
        full_url = f"https://{resolved_host}{path}{qs}"

        sign_v4(
            method, full_url, headers, payload_hash,
            self._access_key_id, self._secret_access_key, self._region,
        )

        resp = await self._client.request(
            method, full_url, headers=headers, content=body,
        )
        resp.raise_for_status()
        return resp

    # ------------------------------------------------------------------
    # Actions — Buckets
    # ------------------------------------------------------------------

    @action("List all S3 buckets in the account")
    async def list_buckets(self) -> list[S3Bucket]:
        """List all S3 buckets owned by the authenticated account.

        Returns:
            List of S3Bucket objects.
        """
        resp = await self._s3_request("GET", "/")
        root = ET.fromstring(resp.text)

        return [
            S3Bucket(
                name=_find_text(b, "Name") or "",
                creation_date=_find_text(b, "CreationDate"),
                region=self._region,
            )
            for b in root.iter(f"{{{_S3_NS}}}Bucket")
        ]

    @action("Create a new S3 bucket", dangerous=True)
    async def create_bucket(
        self, bucket: str, region: Optional[str] = None,
    ) -> S3Bucket:
        """Create a new S3 bucket.

        Args:
            bucket: Bucket name (must be globally unique).
            region: AWS region for the bucket. Defaults to connector region.

        Returns:
            S3Bucket object for the created bucket.
        """
        target_region = region or self._region
        body = b""
        if target_region != "us-east-1":
            body = (
                f'<CreateBucketConfiguration xmlns="{_S3_NS}">'
                f"<LocationConstraint>{target_region}</LocationConstraint>"
                f"</CreateBucketConfiguration>"
            ).encode("utf-8")

        await self._s3_request(
            "PUT", "/", host=self._bucket_host(bucket), body=body,
        )
        return S3Bucket(name=bucket, region=target_region)

    # ------------------------------------------------------------------
    # Actions — Objects
    # ------------------------------------------------------------------

    @action("List objects in an S3 bucket")
    async def list_objects(
        self,
        bucket: str,
        prefix: Optional[str] = None,
        limit: int = 1000,
        continuation_token: Optional[str] = None,
    ) -> PaginatedList[S3Object]:
        """List objects in a bucket using the ListObjectsV2 API.

        Args:
            bucket: Bucket name.
            prefix: Filter objects by key prefix.
            limit: Maximum number of objects per page (max 1000).
            continuation_token: Token from a previous response.

        Returns:
            Paginated list of S3Object items.
        """
        params: dict[str, Any] = {
            "list-type": "2",
            "max-keys": str(min(limit, 1000)),
        }
        if prefix:
            params["prefix"] = prefix
        if continuation_token:
            params["continuation-token"] = continuation_token

        bhost = self._bucket_host(bucket)
        resp = await self._s3_request("GET", "/", host=bhost, params=params)
        root = ET.fromstring(resp.text)

        items: list[S3Object] = []
        for c in root.iter(f"{{{_S3_NS}}}Contents"):
            sz = _find_text(c, "Size")
            items.append(S3Object(
                key=_find_text(c, "Key") or "",
                size=int(sz) if sz else 0,
                last_modified=_find_text(c, "LastModified"),
                etag=_find_text(c, "ETag"),
                storage_class=_find_text(c, "StorageClass"),
            ))

        is_truncated = _find_text(root, "IsTruncated") == "true"
        next_token = _find_text(root, "NextContinuationToken")
        ps = PageState(has_more=is_truncated, cursor=next_token)

        result = PaginatedList(items=items, page_state=ps)
        result._fetch_next = (
            (lambda t=next_token: self.alist_objects(
                bucket=bucket, prefix=prefix, limit=limit,
                continuation_token=t,
            ))
            if is_truncated else None
        )
        return result

    @action("Download an object from S3")
    async def get_object(self, bucket: str, key: str) -> S3ObjectData:
        """Download an object's content and metadata.

        Args:
            bucket: Bucket name.
            key: Object key.

        Returns:
            S3ObjectData with body bytes and metadata.
        """
        enc_key = urllib.parse.quote(key, safe="/")
        resp = await self._s3_request(
            "GET", f"/{enc_key}", host=self._bucket_host(bucket),
        )
        return S3ObjectData(
            key=key,
            body=resp.content,
            content_type=resp.headers.get("content-type"),
            content_length=len(resp.content),
            etag=resp.headers.get("etag"),
            last_modified=resp.headers.get("last-modified"),
            metadata=_extract_user_metadata(resp.headers),
        )

    @action("Upload an object to S3", dangerous=True)
    async def put_object(
        self,
        bucket: str,
        key: str,
        body: bytes,
        content_type: Optional[str] = None,
    ) -> S3PutResult:
        """Upload an object to a bucket.

        Args:
            bucket: Bucket name.
            key: Object key.
            body: Object content as bytes.
            content_type: MIME type. Defaults to ``application/octet-stream``.

        Returns:
            S3PutResult with etag and version info.
        """
        enc_key = urllib.parse.quote(key, safe="/")
        extra: dict[str, str] = {}
        if content_type:
            extra["Content-Type"] = content_type

        resp = await self._s3_request(
            "PUT", f"/{enc_key}", host=self._bucket_host(bucket),
            body=body, extra_headers=extra,
        )
        return S3PutResult(
            key=key,
            etag=resp.headers.get("etag"),
            version_id=resp.headers.get("x-amz-version-id"),
        )

    @action("Delete an object from S3", dangerous=True)
    async def delete_object(self, bucket: str, key: str) -> None:
        """Delete an object from a bucket.

        Args:
            bucket: Bucket name.
            key: Object key to delete.
        """
        enc_key = urllib.parse.quote(key, safe="/")
        await self._s3_request(
            "DELETE", f"/{enc_key}", host=self._bucket_host(bucket),
        )

    @action("Get object metadata without downloading the content")
    async def head_object(self, bucket: str, key: str) -> S3ObjectMetadata:
        """Retrieve metadata for an object (HEAD request).

        Args:
            bucket: Bucket name.
            key: Object key.

        Returns:
            S3ObjectMetadata with headers-based metadata.
        """
        enc_key = urllib.parse.quote(key, safe="/")
        resp = await self._s3_request(
            "HEAD", f"/{enc_key}", host=self._bucket_host(bucket),
        )
        cl = resp.headers.get("content-length", "0")
        return S3ObjectMetadata(
            key=key,
            content_type=resp.headers.get("content-type"),
            content_length=int(cl),
            etag=resp.headers.get("etag"),
            last_modified=resp.headers.get("last-modified"),
            metadata=_extract_user_metadata(resp.headers),
            storage_class=resp.headers.get("x-amz-storage-class"),
            version_id=resp.headers.get("x-amz-version-id"),
        )

    @action("Copy an object between S3 locations")
    async def copy_object(
        self,
        source_bucket: str,
        source_key: str,
        dest_bucket: str,
        dest_key: str,
    ) -> S3CopyResult:
        """Copy an object from one location to another.

        Args:
            source_bucket: Source bucket name.
            source_key: Source object key.
            dest_bucket: Destination bucket name.
            dest_key: Destination object key.

        Returns:
            S3CopyResult with copy metadata.
        """
        enc_dest = urllib.parse.quote(dest_key, safe="/")
        enc_src = urllib.parse.quote(
            f"/{source_bucket}/{source_key}", safe="/",
        )

        resp = await self._s3_request(
            "PUT", f"/{enc_dest}", host=self._bucket_host(dest_bucket),
            extra_headers={"x-amz-copy-source": enc_src},
        )

        root = ET.fromstring(resp.text)
        return S3CopyResult(
            source_key=f"{source_bucket}/{source_key}",
            dest_key=f"{dest_bucket}/{dest_key}",
            etag=_find_text(root, "ETag"),
            last_modified=_find_text(root, "LastModified"),
        )

    # ------------------------------------------------------------------
    # Actions — Bucket management
    # ------------------------------------------------------------------

    @action("Delete an S3 bucket", dangerous=True)
    async def delete_bucket(self, bucket: str) -> None:
        """Delete an S3 bucket.

        The bucket must be empty before it can be deleted. This action
        is irreversible.

        Args:
            bucket: Bucket name to delete.
        """
        await self._s3_request(
            "DELETE", "/", host=self._bucket_host(bucket),
        )

    @action("Get the bucket policy")
    async def get_bucket_policy(self, bucket: str) -> S3BucketPolicy:
        """Retrieve the bucket policy for an S3 bucket.

        Args:
            bucket: Bucket name.

        Returns:
            S3BucketPolicy with the raw JSON policy document.
        """
        resp = await self._s3_request(
            "GET", "/", host=self._bucket_host(bucket),
            params={"policy": ""},
        )
        return S3BucketPolicy(bucket=bucket, policy=resp.text)

    @action("Set the bucket policy", dangerous=True)
    async def put_bucket_policy(
        self,
        bucket: str,
        policy: str,
    ) -> None:
        """Set or replace the bucket policy for an S3 bucket.

        Args:
            bucket: Bucket name.
            policy: JSON policy document as a string.
        """
        await self._s3_request(
            "PUT",
            "/",
            host=self._bucket_host(bucket),
            params={"policy": ""},
            body=policy.encode("utf-8"),
            extra_headers={"Content-Type": "application/json"},
        )

    # ------------------------------------------------------------------
    # Actions — Object versioning
    # ------------------------------------------------------------------

    @action("List object versions in a bucket")
    async def list_object_versions(
        self,
        bucket: str,
        prefix: Optional[str] = None,
        limit: int = 1000,
        key_marker: Optional[str] = None,
    ) -> PaginatedList[S3ObjectVersion]:
        """List object versions in a versioning-enabled bucket.

        Args:
            bucket: Bucket name.
            prefix: Filter versions by key prefix.
            limit: Maximum versions per page (max 1000).
            key_marker: Key marker from a previous response for pagination.

        Returns:
            Paginated list of S3ObjectVersion items.
        """
        params: dict[str, Any] = {
            "versions": "",
            "max-keys": str(min(limit, 1000)),
        }
        if prefix:
            params["prefix"] = prefix
        if key_marker:
            params["key-marker"] = key_marker

        bhost = self._bucket_host(bucket)
        resp = await self._s3_request("GET", "/", host=bhost, params=params)
        root = ET.fromstring(resp.text)

        items: list[S3ObjectVersion] = []

        # Parse <Version> elements
        for v in root.iter(f"{{{_S3_NS}}}Version"):
            sz = _find_text(v, "Size")
            items.append(S3ObjectVersion(
                key=_find_text(v, "Key") or "",
                version_id=_find_text(v, "VersionId"),
                is_latest=_find_text(v, "IsLatest") == "true",
                last_modified=_find_text(v, "LastModified"),
                etag=_find_text(v, "ETag"),
                size=int(sz) if sz else 0,
                storage_class=_find_text(v, "StorageClass"),
                is_delete_marker=False,
            ))

        # Parse <DeleteMarker> elements
        for dm in root.iter(f"{{{_S3_NS}}}DeleteMarker"):
            items.append(S3ObjectVersion(
                key=_find_text(dm, "Key") or "",
                version_id=_find_text(dm, "VersionId"),
                is_latest=_find_text(dm, "IsLatest") == "true",
                last_modified=_find_text(dm, "LastModified"),
                is_delete_marker=True,
            ))

        is_truncated = _find_text(root, "IsTruncated") == "true"
        next_key_marker = _find_text(root, "NextKeyMarker")

        ps = PageState(has_more=is_truncated, cursor=next_key_marker)
        result = PaginatedList(items=items, page_state=ps)
        if is_truncated:
            result._fetch_next = lambda km=next_key_marker: self.alist_object_versions(
                bucket=bucket, prefix=prefix, limit=limit, key_marker=km,
            )
        return result

    # ------------------------------------------------------------------
    # Actions — Pre-signed URLs
    # ------------------------------------------------------------------

    @action("Generate a pre-signed URL for an S3 object")
    async def generate_presigned_url(
        self,
        bucket: str,
        key: str,
        expiration: int = 3600,
        method: str = "GET",
    ) -> S3PresignedUrl:
        """Generate a pre-signed URL for time-limited access to an S3 object.

        Uses AWS Signature Version 4 query-string authentication to
        create a URL that grants temporary access without requiring
        credentials.

        Args:
            bucket: Bucket name.
            key: Object key.
            expiration: URL validity in seconds (default 3600 = 1 hour,
                max 604800 = 7 days).
            method: HTTP method the URL authorises (``GET`` or ``PUT``).

        Returns:
            S3PresignedUrl with the signed URL string.
        """
        return build_presigned_url(
            bucket=bucket,
            key=key,
            host=self._bucket_host(bucket),
            region=self._region,
            access_key_id=self._access_key_id,
            secret_access_key=self._secret_access_key,
            expiration=expiration,
            method=method,
        )

    # ------------------------------------------------------------------
    # Actions — Object tagging
    # ------------------------------------------------------------------

    @action("Set tags on an S3 object")
    async def set_object_tags(
        self,
        bucket: str,
        key: str,
        tags: dict[str, str],
    ) -> None:
        """Set or replace the tag set on an S3 object.

        Args:
            bucket: Bucket name.
            key: Object key.
            tags: Dictionary of tag key-value pairs (max 10 tags).
        """
        body_xml = build_tagging_xml(tags, _S3_NS)
        enc_key = urllib.parse.quote(key, safe="/")
        md5_b64 = compute_content_md5(body_xml)

        await self._s3_request(
            "PUT",
            f"/{enc_key}",
            host=self._bucket_host(bucket),
            params={"tagging": ""},
            body=body_xml,
            extra_headers={
                "Content-Type": "application/xml",
                "Content-MD5": md5_b64,
            },
        )

    @action("Get tags on an S3 object")
    async def get_object_tags(
        self,
        bucket: str,
        key: str,
        version_id: Optional[str] = None,
    ) -> S3ObjectTagSet:
        """Retrieve the tag set for an S3 object.

        Args:
            bucket: Bucket name.
            key: Object key.
            version_id: Optional version ID to get tags for a specific
                object version.

        Returns:
            S3ObjectTagSet with the key and tag dictionary.
        """
        enc_key = urllib.parse.quote(key, safe="/")
        params: dict[str, Any] = {"tagging": ""}
        if version_id:
            params["versionId"] = version_id

        resp = await self._s3_request(
            "GET", f"/{enc_key}", host=self._bucket_host(bucket),
            params=params,
        )
        root = ET.fromstring(resp.text)

        tags: dict[str, str] = {}
        for tag in root.iter(f"{{{_S3_NS}}}Tag"):
            tag_key = _find_text(tag, "Key")
            tag_val = _find_text(tag, "Value")
            if tag_key is not None:
                tags[tag_key] = tag_val or ""

        return S3ObjectTagSet(
            key=key,
            tags=tags,
            version_id=resp.headers.get("x-amz-version-id"),
        )

    @action("Delete all tags from an S3 object", dangerous=True)
    async def delete_object_tags(
        self,
        bucket: str,
        key: str,
        version_id: Optional[str] = None,
    ) -> None:
        """Remove the entire tag set from an S3 object.

        Args:
            bucket: Bucket name.
            key: Object key.
            version_id: Optional version ID to delete tags for a
                specific object version.
        """
        enc_key = urllib.parse.quote(key, safe="/")
        params: dict[str, Any] = {"tagging": ""}
        if version_id:
            params["versionId"] = version_id

        await self._s3_request(
            "DELETE", f"/{enc_key}", host=self._bucket_host(bucket),
            params=params,
        )

    # ------------------------------------------------------------------
    # Actions — Bucket location
    # ------------------------------------------------------------------

    @action("Get the region (location) of an S3 bucket")
    async def get_bucket_location(self, bucket: str) -> S3BucketLocation:
        """Retrieve the AWS region where a bucket is located.

        Args:
            bucket: Bucket name.

        Returns:
            S3BucketLocation with the region code. Note that buckets
            in ``us-east-1`` may return ``None`` as the location.
        """
        resp = await self._s3_request(
            "GET", "/", host=self._bucket_host(bucket),
            params={"location": ""},
        )
        root = ET.fromstring(resp.text)
        location = root.text  # May be None for us-east-1
        return S3BucketLocation(
            bucket=bucket,
            location=location or "us-east-1",
        )

    # ------------------------------------------------------------------
    # Actions — Multipart uploads
    # ------------------------------------------------------------------

    @action("List in-progress multipart uploads in a bucket")
    async def list_multipart_uploads(
        self,
        bucket: str,
        prefix: Optional[str] = None,
        limit: int = 1000,
        key_marker: Optional[str] = None,
    ) -> PaginatedList[S3MultipartUpload]:
        """List in-progress multipart uploads in a bucket.

        Args:
            bucket: Bucket name.
            prefix: Filter uploads by key prefix.
            limit: Maximum uploads per page (max 1000).
            key_marker: Key marker from a previous response for pagination.

        Returns:
            Paginated list of S3MultipartUpload items.
        """
        params: dict[str, Any] = {
            "uploads": "",
            "max-uploads": str(min(limit, 1000)),
        }
        if prefix:
            params["prefix"] = prefix
        if key_marker:
            params["key-marker"] = key_marker

        bhost = self._bucket_host(bucket)
        resp = await self._s3_request("GET", "/", host=bhost, params=params)
        root = ET.fromstring(resp.text)

        items: list[S3MultipartUpload] = []
        for u in root.iter(f"{{{_S3_NS}}}Upload"):
            initiator = u.find(f"{{{_S3_NS}}}Initiator")
            owner = u.find(f"{{{_S3_NS}}}Owner")
            items.append(S3MultipartUpload(
                key=_find_text(u, "Key") or "",
                upload_id=_find_text(u, "UploadId") or "",
                initiated=_find_text(u, "Initiated"),
                storage_class=_find_text(u, "StorageClass"),
                owner_id=(
                    _find_text(owner, "ID") if owner is not None else None
                ),
                initiator_id=(
                    _find_text(initiator, "ID")
                    if initiator is not None else None
                ),
            ))

        is_truncated = _find_text(root, "IsTruncated") == "true"
        next_key_marker = _find_text(root, "NextKeyMarker")
        ps = PageState(has_more=is_truncated, cursor=next_key_marker)

        result = PaginatedList(items=items, page_state=ps)
        if is_truncated:
            result._fetch_next = (
                lambda km=next_key_marker: self.alist_multipart_uploads(
                    bucket=bucket, prefix=prefix, limit=limit,
                    key_marker=km,
                )
            )
        return result

    # ------------------------------------------------------------------
    # Actions — Bucket versioning configuration
    # ------------------------------------------------------------------

    @action("Get bucket versioning configuration")
    async def get_bucket_versioning(
        self, bucket: str,
    ) -> S3BucketVersioning:
        """Retrieve the versioning state of an S3 bucket.

        Args:
            bucket: Bucket name.

        Returns:
            S3BucketVersioning with status (``Enabled``, ``Suspended``,
            or ``None`` if never enabled) and MFA delete state.
        """
        resp = await self._s3_request(
            "GET", "/", host=self._bucket_host(bucket),
            params={"versioning": ""},
        )
        root = ET.fromstring(resp.text)
        return S3BucketVersioning(
            bucket=bucket,
            status=_find_text(root, "Status"),
            mfa_delete=_find_text(root, "MfaDelete"),
        )

    @action("Set bucket versioning configuration", dangerous=True)
    async def put_bucket_versioning(
        self,
        bucket: str,
        status: str,
    ) -> None:
        """Enable or suspend versioning on an S3 bucket.

        Once versioning is enabled it cannot be removed, only
        suspended. Objects already versioned retain their versions.

        Args:
            bucket: Bucket name.
            status: Versioning status — ``"Enabled"`` or ``"Suspended"``.
        """
        if status not in ("Enabled", "Suspended"):
            raise ValueError(
                f"status must be 'Enabled' or 'Suspended', got {status!r}"
            )
        body = (
            f'<VersioningConfiguration xmlns="{_S3_NS}">'
            f"<Status>{status}</Status>"
            f"</VersioningConfiguration>"
        ).encode("utf-8")

        await self._s3_request(
            "PUT", "/", host=self._bucket_host(bucket),
            params={"versioning": ""},
            body=body,
            extra_headers={"Content-Type": "application/xml"},
        )
