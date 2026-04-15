"""AWS CloudFront connector -- CDN distributions, invalidations, and cache management.

Uses the CloudFront REST API with AWS Signature Version 4 authentication.
Credentials should be a JSON string or dict containing ``access_key_id``,
``secret_access_key``, and optionally ``region`` (ignored -- CloudFront
always uses ``us-east-1``).

CloudFront responses are XML-formatted and parsed with
``xml.etree.ElementTree``.
"""

from __future__ import annotations

import datetime
import hashlib
import logging
import urllib.parse
import uuid
import xml.etree.ElementTree as ET
from typing import Any, Optional

import httpx

from toolsconnector.connectors._aws.auth import parse_credentials
from toolsconnector.connectors._aws.errors import AWSError
from toolsconnector.connectors._aws.signing import sign_v4
from toolsconnector.connectors._aws.xml_helpers import find_text, iter_elements
from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import (
    ConnectorCategory,
    ProtocolType,
    RateLimitSpec,
)

from .types import (
    CFDistribution,
    CFDistributionSummary,
    CFInvalidation,
)

logger = logging.getLogger("toolsconnector.cloudfront")

_API_VERSION = "2020-05-31"
_CF_NS = "http://cloudfront.amazonaws.com/doc/2020-05-31/"


class CloudFront(BaseConnector):
    """Connect to AWS CloudFront to manage CDN distributions and invalidations.

    Authenticates using AWS Signature Version 4. Credentials should be
    provided as a JSON string or dict::

        {
            "access_key_id": "AKIA...",
            "secret_access_key": "...",
        }

    The region is always ``us-east-1`` for CloudFront (a global service).
    """

    name = "cloudfront"
    display_name = "AWS CloudFront"
    category = ConnectorCategory.NETWORKING
    protocol = ProtocolType.REST
    base_url = "https://cloudfront.amazonaws.com"
    description = (
        "Manage CloudFront CDN distributions, cache invalidations, "
        "and origin configs."
    )
    _rate_limit_config = RateLimitSpec(rate=100, period=1, burst=200)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Initialise credentials and httpx client."""
        creds = parse_credentials(self._credentials)
        self._access_key_id = creds.access_key_id
        self._secret_access_key = creds.secret_access_key
        self._session_token = creds.session_token
        # CloudFront is a global service -- always us-east-1.
        self._region = "us-east-1"
        self._host = "cloudfront.amazonaws.com"

        self._client = httpx.AsyncClient(
            timeout=self._timeout,
        )

    async def _teardown(self) -> None:
        """Close the httpx client."""
        if hasattr(self, "_client"):
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _cf_request(
        self,
        method: str,
        path: str,
        *,
        body: bytes = b"",
        params: Optional[dict[str, str]] = None,
        extra_headers: Optional[dict[str, str]] = None,
    ) -> httpx.Response:
        """Send a SigV4-signed request to CloudFront.

        Builds the full URL from the API version prefix, signs the
        request with SigV4 (service ``cloudfront``, region
        ``us-east-1``), and returns the raw response.

        Args:
            method: HTTP method (``GET``, ``POST``, ``PUT``, ``DELETE``).
            path: API path *after* the version prefix (e.g.
                ``distribution`` or ``distribution/{id}/invalidation``).
            body: Request body bytes.
            params: Query string parameters.
            extra_headers: Additional headers to include.

        Returns:
            ``httpx.Response`` object.

        Raises:
            AWSError: On 4xx/5xx responses.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        payload_hash = hashlib.sha256(body).hexdigest()

        headers: dict[str, str] = {
            "Host": self._host,
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
        full_url = f"https://{self._host}/{_API_VERSION}/{path}{qs}"

        sign_v4(
            method,
            full_url,
            headers,
            payload_hash,
            self._access_key_id,
            self._secret_access_key,
            self._region,
            service="cloudfront",
            session_token=self._session_token,
        )

        resp = await self._client.request(
            method, full_url, headers=headers, content=body,
        )
        if resp.status_code >= 400:
            _raise_cf_error(resp)
        return resp

    # ------------------------------------------------------------------
    # XML parsing helpers
    # ------------------------------------------------------------------

    def _parse_distribution_summary(
        self, elem: ET.Element,
    ) -> CFDistributionSummary:
        """Parse a ``<DistributionSummary>`` element.

        Args:
            elem: XML element for a single distribution summary.

        Returns:
            CFDistributionSummary instance.
        """
        enabled_text = find_text(elem, "Enabled", _CF_NS) or "false"
        return CFDistributionSummary(
            id=find_text(elem, "Id", _CF_NS) or "",
            arn=find_text(elem, "ARN", _CF_NS) or "",
            domain_name=find_text(elem, "DomainName", _CF_NS) or "",
            status=find_text(elem, "Status", _CF_NS) or "",
            enabled=enabled_text.lower() == "true",
            comment=find_text(elem, "Comment", _CF_NS) or "",
        )

    def _parse_distribution(
        self, root: ET.Element,
    ) -> CFDistribution:
        """Parse a ``<Distribution>`` element.

        Args:
            root: XML element for a full distribution response.

        Returns:
            CFDistribution instance.
        """
        config = root.find(f"{{{_CF_NS}}}DistributionConfig")
        if config is None:
            config = root.find("DistributionConfig")

        enabled_text = "false"
        comment = ""
        last_modified = find_text(root, "LastModifiedTime", _CF_NS)
        origins_list: list[dict[str, Any]] = []
        default_cache: dict[str, Any] = {}

        if config is not None:
            enabled_text = find_text(config, "Enabled", _CF_NS) or "false"
            comment = find_text(config, "Comment", _CF_NS) or ""

            # Parse origins
            origins_elem = config.find(f"{{{_CF_NS}}}Origins")
            if origins_elem is None:
                origins_elem = config.find("Origins")
            if origins_elem is not None:
                for origin in iter_elements(origins_elem, "Origin", _CF_NS):
                    origins_list.append({
                        "id": find_text(origin, "Id", _CF_NS) or "",
                        "domain_name": find_text(
                            origin, "DomainName", _CF_NS,
                        ) or "",
                        "origin_path": find_text(
                            origin, "OriginPath", _CF_NS,
                        ) or "",
                    })

            # Parse default cache behavior
            dcb = config.find(f"{{{_CF_NS}}}DefaultCacheBehavior")
            if dcb is None:
                dcb = config.find("DefaultCacheBehavior")
            if dcb is not None:
                default_cache = {
                    "target_origin_id": find_text(
                        dcb, "TargetOriginId", _CF_NS,
                    ) or "",
                    "viewer_protocol_policy": find_text(
                        dcb, "ViewerProtocolPolicy", _CF_NS,
                    ) or "",
                }

        return CFDistribution(
            id=find_text(root, "Id", _CF_NS) or "",
            arn=find_text(root, "ARN", _CF_NS) or "",
            domain_name=find_text(root, "DomainName", _CF_NS) or "",
            status=find_text(root, "Status", _CF_NS) or "",
            enabled=enabled_text.lower() == "true",
            comment=comment,
            last_modified=last_modified,
            origins=origins_list,
            default_cache_behavior=default_cache,
        )

    def _parse_invalidation(
        self, elem: ET.Element,
    ) -> CFInvalidation:
        """Parse an ``<Invalidation>`` or ``<InvalidationSummary>`` element.

        Args:
            elem: XML element for an invalidation.

        Returns:
            CFInvalidation instance.
        """
        batch: dict[str, Any] = {}
        batch_elem = elem.find(f"{{{_CF_NS}}}InvalidationBatch")
        if batch_elem is None:
            batch_elem = elem.find("InvalidationBatch")
        if batch_elem is not None:
            paths_elem = batch_elem.find(f"{{{_CF_NS}}}Paths")
            if paths_elem is None:
                paths_elem = batch_elem.find("Paths")
            if paths_elem is not None:
                path_items: list[str] = []
                for p in iter_elements(paths_elem, "Path", _CF_NS):
                    if p.text:
                        path_items.append(p.text)
                batch["paths"] = path_items
            caller_ref = find_text(
                batch_elem, "CallerReference", _CF_NS,
            )
            if caller_ref:
                batch["caller_reference"] = caller_ref

        return CFInvalidation(
            id=find_text(elem, "Id", _CF_NS) or "",
            status=find_text(elem, "Status", _CF_NS) or "",
            create_time=find_text(elem, "CreateTime", _CF_NS),
            invalidation_batch=batch,
        )

    # ------------------------------------------------------------------
    # Actions -- Distributions
    # ------------------------------------------------------------------

    @action("List all CloudFront distributions")
    async def list_distributions(self) -> list[CFDistributionSummary]:
        """List all CloudFront distributions in the account.

        Returns:
            List of CFDistributionSummary objects.
        """
        resp = await self._cf_request("GET", "distribution")
        root = ET.fromstring(resp.text)

        items: list[CFDistributionSummary] = []
        for elem in iter_elements(root, "DistributionSummary", _CF_NS):
            items.append(self._parse_distribution_summary(elem))
        return items

    @action("Get a CloudFront distribution by ID")
    async def get_distribution(
        self, distribution_id: str,
    ) -> CFDistribution:
        """Retrieve a single distribution by its ID.

        Args:
            distribution_id: The CloudFront distribution ID.

        Returns:
            CFDistribution object with full details.
        """
        resp = await self._cf_request(
            "GET", f"distribution/{distribution_id}",
        )
        root = ET.fromstring(resp.text)
        return self._parse_distribution(root)

    @action("Get the configuration of a CloudFront distribution")
    async def get_distribution_config(
        self, distribution_id: str,
    ) -> dict[str, Any]:
        """Retrieve the configuration of a CloudFront distribution.

        Returns the raw configuration as a dict along with the ETag
        needed for update operations.

        Args:
            distribution_id: The CloudFront distribution ID.

        Returns:
            Dict with ``config`` (parsed XML fields) and ``etag``
            (the ETag header for conditional updates).
        """
        resp = await self._cf_request(
            "GET", f"distribution/{distribution_id}/config",
        )
        root = ET.fromstring(resp.text)
        etag = resp.headers.get("etag", "")

        config: dict[str, Any] = {
            "caller_reference": find_text(
                root, "CallerReference", _CF_NS,
            ) or "",
            "comment": find_text(root, "Comment", _CF_NS) or "",
            "enabled": (
                find_text(root, "Enabled", _CF_NS) or "false"
            ).lower() == "true",
            "default_root_object": find_text(
                root, "DefaultRootObject", _CF_NS,
            ) or "",
        }

        return {"config": config, "etag": etag}

    @action("Create a new CloudFront distribution", dangerous=True)
    async def create_distribution(
        self,
        origin_domain: str,
        comment: str = "",
        enabled: bool = True,
        default_root_object: str = "index.html",
    ) -> CFDistribution:
        """Create a new CloudFront distribution.

        Creates a minimal distribution with a single origin and
        ``allow-all`` viewer protocol policy.

        Args:
            origin_domain: The domain name of the origin server
                (e.g. ``mybucket.s3.amazonaws.com``).
            comment: Optional description for the distribution.
            enabled: Whether the distribution should be enabled.
            default_root_object: Default root object (e.g.
                ``index.html``).

        Returns:
            The created CFDistribution object.
        """
        caller_ref = str(uuid.uuid4())
        enabled_str = "true" if enabled else "false"
        escaped_comment = _xml_escape(comment)
        escaped_domain = _xml_escape(origin_domain)
        escaped_root = _xml_escape(default_root_object)

        body_xml = (
            f'<DistributionConfig xmlns="{_CF_NS}">'
            f"<CallerReference>{caller_ref}</CallerReference>"
            f"<Comment>{escaped_comment}</Comment>"
            f"<Enabled>{enabled_str}</Enabled>"
            f"<DefaultRootObject>{escaped_root}</DefaultRootObject>"
            f"<Origins>"
            f"<Quantity>1</Quantity>"
            f"<Items>"
            f"<Origin>"
            f"<Id>origin-1</Id>"
            f"<DomainName>{escaped_domain}</DomainName>"
            f"<OriginPath></OriginPath>"
            f"<S3OriginConfig>"
            f"<OriginAccessIdentity></OriginAccessIdentity>"
            f"</S3OriginConfig>"
            f"</Origin>"
            f"</Items>"
            f"</Origins>"
            f"<DefaultCacheBehavior>"
            f"<TargetOriginId>origin-1</TargetOriginId>"
            f"<ViewerProtocolPolicy>allow-all</ViewerProtocolPolicy>"
            f"<ForwardedValues>"
            f"<QueryString>false</QueryString>"
            f"<Cookies><Forward>none</Forward></Cookies>"
            f"</ForwardedValues>"
            f"<TrustedSigners>"
            f"<Enabled>false</Enabled>"
            f"<Quantity>0</Quantity>"
            f"</TrustedSigners>"
            f"<MinTTL>0</MinTTL>"
            f"</DefaultCacheBehavior>"
            f"</DistributionConfig>"
        ).encode("utf-8")

        resp = await self._cf_request(
            "POST",
            "distribution",
            body=body_xml,
            extra_headers={"Content-Type": "application/xml"},
        )
        root = ET.fromstring(resp.text)
        return self._parse_distribution(root)

    @action("Delete a CloudFront distribution", dangerous=True)
    async def delete_distribution(
        self,
        distribution_id: str,
        if_match: str = "",
    ) -> dict[str, Any]:
        """Delete a CloudFront distribution.

        The distribution must be disabled before deletion. The
        ``if_match`` parameter should be the ETag from the most recent
        GET request (use ``get_distribution_config`` to obtain it).

        Args:
            distribution_id: The CloudFront distribution ID.
            if_match: The ETag value for conditional deletion.
                Required by CloudFront to prevent concurrent
                modifications.

        Returns:
            Dict with ``deleted`` status.
        """
        extra: dict[str, str] = {}
        if if_match:
            extra["If-Match"] = if_match

        await self._cf_request(
            "DELETE",
            f"distribution/{distribution_id}",
            extra_headers=extra,
        )
        return {"deleted": True, "distribution_id": distribution_id}

    # ------------------------------------------------------------------
    # Actions -- Invalidations
    # ------------------------------------------------------------------

    @action("Create a cache invalidation")
    async def create_invalidation(
        self,
        distribution_id: str,
        paths: list[str],
    ) -> CFInvalidation:
        """Create a cache invalidation for a CloudFront distribution.

        Invalidates cached objects at the specified paths so that
        CloudFront fetches fresh content from the origin on the
        next request.

        Args:
            distribution_id: The CloudFront distribution ID.
            paths: List of URL paths to invalidate (e.g.
                ``["/images/*", "/index.html"]``).

        Returns:
            CFInvalidation with the invalidation status.
        """
        caller_ref = str(uuid.uuid4())
        quantity = len(paths)
        path_items = "".join(
            f"<Path>{_xml_escape(p)}</Path>" for p in paths
        )

        body_xml = (
            f"<InvalidationBatch>"
            f"<Paths>"
            f"<Quantity>{quantity}</Quantity>"
            f"<Items>{path_items}</Items>"
            f"</Paths>"
            f"<CallerReference>{caller_ref}</CallerReference>"
            f"</InvalidationBatch>"
        ).encode("utf-8")

        resp = await self._cf_request(
            "POST",
            f"distribution/{distribution_id}/invalidation",
            body=body_xml,
            extra_headers={"Content-Type": "application/xml"},
        )
        root = ET.fromstring(resp.text)
        return self._parse_invalidation(root)

    @action("Get an invalidation status")
    async def get_invalidation(
        self,
        distribution_id: str,
        invalidation_id: str,
    ) -> CFInvalidation:
        """Retrieve the status of a cache invalidation.

        Args:
            distribution_id: The CloudFront distribution ID.
            invalidation_id: The invalidation ID.

        Returns:
            CFInvalidation with current status.
        """
        resp = await self._cf_request(
            "GET",
            f"distribution/{distribution_id}/invalidation/{invalidation_id}",
        )
        root = ET.fromstring(resp.text)
        return self._parse_invalidation(root)

    @action("List invalidations for a distribution")
    async def list_invalidations(
        self,
        distribution_id: str,
    ) -> list[CFInvalidation]:
        """List all invalidations for a CloudFront distribution.

        Args:
            distribution_id: The CloudFront distribution ID.

        Returns:
            List of CFInvalidation objects.
        """
        resp = await self._cf_request(
            "GET",
            f"distribution/{distribution_id}/invalidation",
        )
        root = ET.fromstring(resp.text)

        items: list[CFInvalidation] = []
        for elem in iter_elements(
            root, "InvalidationSummary", _CF_NS,
        ):
            items.append(self._parse_invalidation(elem))
        return items

    # ------------------------------------------------------------------
    # Actions -- Distribution management
    # ------------------------------------------------------------------

    @action("Enable or disable a CloudFront distribution")
    async def update_distribution_enabled(
        self,
        distribution_id: str,
        enabled: bool,
    ) -> CFDistribution:
        """Enable or disable a CloudFront distribution.

        Fetches the current configuration, updates the ``Enabled``
        flag, and PUTs the updated config back using the ETag for
        conditional updates.

        Args:
            distribution_id: The CloudFront distribution ID.
            enabled: True to enable, False to disable.

        Returns:
            Updated CFDistribution object.
        """
        # Step 1: GET current config and ETag.
        config_resp = await self._cf_request(
            "GET", f"distribution/{distribution_id}/config",
        )
        etag = config_resp.headers.get("etag", "")
        config_xml = config_resp.text

        # Step 2: Update the Enabled flag in the XML.
        enabled_str = "true" if enabled else "false"
        # Replace the Enabled element value.
        updated_xml = _replace_xml_value(
            config_xml, "Enabled", enabled_str,
        )

        # Step 3: PUT the updated config.
        resp = await self._cf_request(
            "PUT",
            f"distribution/{distribution_id}/config",
            body=updated_xml.encode("utf-8"),
            extra_headers={
                "Content-Type": "application/xml",
                "If-Match": etag,
            },
        )
        root = ET.fromstring(resp.text)

        # The PUT config response is a Distribution element.
        return self._parse_distribution(root)

    # ------------------------------------------------------------------
    # Actions -- Tagging
    # ------------------------------------------------------------------

    @action("List CloudFront distribution tags")
    async def list_tags(
        self,
        resource_arn: str,
    ) -> dict[str, Any]:
        """List tags for a CloudFront resource.

        Args:
            resource_arn: The ARN of the CloudFront resource
                (e.g. ``arn:aws:cloudfront::123456789012:distribution/EDFDVBD6EXAMPLE``).

        Returns:
            Dict with ``tags`` key containing a dict of tag
            key-value pairs.
        """
        resp = await self._cf_request(
            "GET",
            "tagging",
            params={"Resource": resource_arn},
        )
        root = ET.fromstring(resp.text)

        tags: dict[str, str] = {}
        for item in iter_elements(root, "Tag", _CF_NS):
            key = find_text(item, "Key", _CF_NS)
            value = find_text(item, "Value", _CF_NS)
            if key is not None:
                tags[key] = value or ""

        return {"tags": tags}


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _xml_escape(text: str) -> str:
    """Escape special XML characters in text content.

    Args:
        text: Raw string to escape.

    Returns:
        XML-safe string.
    """
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _replace_xml_value(xml_text: str, tag: str, new_value: str) -> str:
    """Replace the text content of the first occurrence of an XML element.

    A simple string-based replacement that avoids the need for full
    XML round-tripping (which can alter namespace prefixes and element
    ordering).

    Args:
        xml_text: Raw XML string.
        tag: Element tag name to find.
        new_value: New text content for the element.

    Returns:
        Updated XML string.
    """
    # Match both namespaced and bare tags.
    for pattern_start in (f"<{tag}>", f"<{tag} "):
        start_idx = xml_text.find(f"<{tag}>")
        if start_idx == -1:
            # Try namespace-qualified version.
            ns_tag = f"{{{_CF_NS}}}{tag}"
            start_idx = xml_text.find(f"<{ns_tag}>")
            if start_idx != -1:
                tag = ns_tag

        if start_idx != -1:
            open_tag = f"<{tag}>"
            close_tag = f"</{tag}>"
            content_start = start_idx + len(open_tag)
            end_idx = xml_text.find(close_tag, content_start)
            if end_idx != -1:
                return (
                    xml_text[:content_start]
                    + new_value
                    + xml_text[end_idx:]
                )
    return xml_text


def _raise_cf_error(resp: httpx.Response) -> None:
    """Parse a CloudFront error response and raise AWSError.

    Args:
        resp: The HTTP response with a 4xx/5xx status.

    Raises:
        AWSError: Always raised with parsed error details.
    """
    from toolsconnector.connectors._aws.xml_helpers import parse_xml_error

    parsed = parse_xml_error(resp.text)
    raise AWSError(
        status_code=resp.status_code,
        error_code=parsed.get("code") or f"HTTP{resp.status_code}",
        message=parsed.get("message") or resp.text,
    )
