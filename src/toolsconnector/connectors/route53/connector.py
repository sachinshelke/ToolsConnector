"""AWS Route 53 connector -- DNS hosted zones, record sets, and health checks.

Uses the Route 53 REST XML API with AWS Signature Version 4 authentication.
Credentials should be a JSON string or dict containing ``access_key_id``,
``secret_access_key``, and optionally ``region`` (ignored -- Route 53
always uses ``us-east-1`` for signing).

Route 53 responses are XML-formatted and parsed with
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
    R53ChangeInfo,
    R53HealthCheck,
    R53HostedZone,
    R53RecordSet,
)

logger = logging.getLogger("toolsconnector.route53")

_R53_NS = "https://route53.amazonaws.com/doc/2013-04-01/"
_API_PREFIX = "2013-04-01"


class Route53(BaseConnector):
    """Connect to AWS Route 53 to manage DNS hosted zones and record sets.

    Authenticates using AWS Signature Version 4. Credentials should be
    provided as a JSON string or dict::

        {
            "access_key_id": "AKIA...",
            "secret_access_key": "...",
        }

    The region is always ``us-east-1`` for Route 53 (a global service).
    """

    name = "route53"
    display_name = "AWS Route 53"
    category = ConnectorCategory.NETWORKING
    protocol = ProtocolType.REST
    base_url = "https://route53.amazonaws.com"
    description = "Manage DNS hosted zones, record sets, and health checks."
    _rate_limit_config = RateLimitSpec(rate=5, period=1, burst=10)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Initialise credentials and httpx client."""
        creds = parse_credentials(self._credentials)
        self._access_key_id = creds.access_key_id
        self._secret_access_key = creds.secret_access_key
        self._session_token = creds.session_token
        # Route 53 is a global service -- always us-east-1.
        self._region = "us-east-1"
        self._host = "route53.amazonaws.com"

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

    async def _r53_request(
        self,
        method: str,
        path: str,
        *,
        body: bytes = b"",
        params: Optional[dict[str, str]] = None,
        extra_headers: Optional[dict[str, str]] = None,
    ) -> httpx.Response:
        """Send a SigV4-signed request to Route 53.

        Builds the full URL from the API version prefix, signs the
        request with SigV4 (service ``route53``, region
        ``us-east-1``), and returns the raw response.

        Args:
            method: HTTP method (``GET``, ``POST``, ``PUT``, ``DELETE``).
            path: API path *after* the version prefix (e.g.
                ``hostedzone`` or ``hostedzone/{id}/rrset``).
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
        full_url = f"https://{self._host}/{_API_PREFIX}/{path}{qs}"

        sign_v4(
            method,
            full_url,
            headers,
            payload_hash,
            self._access_key_id,
            self._secret_access_key,
            self._region,
            service="route53",
            session_token=self._session_token,
        )

        resp = await self._client.request(
            method, full_url, headers=headers, content=body,
        )
        if resp.status_code >= 400:
            _raise_r53_error(resp)
        return resp

    # ------------------------------------------------------------------
    # XML parsing helpers
    # ------------------------------------------------------------------

    def _parse_hosted_zone(self, elem: ET.Element) -> R53HostedZone:
        """Parse a ``<HostedZone>`` element.

        Args:
            elem: XML element for a hosted zone.

        Returns:
            R53HostedZone instance.
        """
        zone_id = find_text(elem, "Id", _R53_NS) or ""
        # Strip the /hostedzone/ prefix that AWS returns.
        if zone_id.startswith("/hostedzone/"):
            zone_id = zone_id[len("/hostedzone/"):]

        config: dict[str, Any] = {}
        config_elem = elem.find(f"{{{_R53_NS}}}Config")
        if config_elem is None:
            config_elem = elem.find("Config")
        if config_elem is not None:
            comment = find_text(config_elem, "Comment", _R53_NS)
            private_zone = find_text(config_elem, "PrivateZone", _R53_NS)
            if comment is not None:
                config["comment"] = comment
            if private_zone is not None:
                config["private_zone"] = private_zone.lower() == "true"

        count_text = find_text(elem, "ResourceRecordSetCount", _R53_NS)
        count = int(count_text) if count_text else 0

        return R53HostedZone(
            id=zone_id,
            name=find_text(elem, "Name", _R53_NS) or "",
            caller_reference=find_text(elem, "CallerReference", _R53_NS) or "",
            config=config,
            resource_record_set_count=count,
        )

    def _parse_record_set(self, elem: ET.Element) -> R53RecordSet:
        """Parse a ``<ResourceRecordSet>`` element.

        Args:
            elem: XML element for a resource record set.

        Returns:
            R53RecordSet instance.
        """
        ttl_text = find_text(elem, "TTL", _R53_NS)
        ttl = int(ttl_text) if ttl_text else None

        records: list[str] = []
        rr_elem = elem.find(f"{{{_R53_NS}}}ResourceRecords")
        if rr_elem is None:
            rr_elem = elem.find("ResourceRecords")
        if rr_elem is not None:
            for rr in iter_elements(rr_elem, "ResourceRecord", _R53_NS):
                value = find_text(rr, "Value", _R53_NS)
                if value:
                    records.append(value)

        alias_target: Optional[dict[str, Any]] = None
        alias_elem = elem.find(f"{{{_R53_NS}}}AliasTarget")
        if alias_elem is None:
            alias_elem = elem.find("AliasTarget")
        if alias_elem is not None:
            eth_text = find_text(
                alias_elem, "EvaluateTargetHealth", _R53_NS,
            ) or "false"
            alias_target = {
                "hosted_zone_id": find_text(
                    alias_elem, "HostedZoneId", _R53_NS,
                ) or "",
                "dns_name": find_text(
                    alias_elem, "DNSName", _R53_NS,
                ) or "",
                "evaluate_target_health": eth_text.lower() == "true",
            }

        return R53RecordSet(
            name=find_text(elem, "Name", _R53_NS) or "",
            type=find_text(elem, "Type", _R53_NS) or "",
            ttl=ttl,
            resource_records=records,
            alias_target=alias_target,
        )

    def _parse_change_info(self, elem: ET.Element) -> R53ChangeInfo:
        """Parse a ``<ChangeInfo>`` element.

        Args:
            elem: XML element for change info.

        Returns:
            R53ChangeInfo instance.
        """
        change_id = find_text(elem, "Id", _R53_NS) or ""
        if change_id.startswith("/change/"):
            change_id = change_id[len("/change/"):]

        return R53ChangeInfo(
            id=change_id,
            status=find_text(elem, "Status", _R53_NS) or "",
            submitted_at=find_text(elem, "SubmittedAt", _R53_NS),
        )

    def _parse_health_check(self, elem: ET.Element) -> R53HealthCheck:
        """Parse a ``<HealthCheck>`` element.

        Args:
            elem: XML element for a health check.

        Returns:
            R53HealthCheck instance.
        """
        hc_config: dict[str, Any] = {}
        config_elem = elem.find(f"{{{_R53_NS}}}HealthCheckConfig")
        if config_elem is None:
            config_elem = elem.find("HealthCheckConfig")
        if config_elem is not None:
            for child in config_elem:
                tag = child.tag
                # Strip namespace from tag.
                if tag.startswith(f"{{{_R53_NS}}}"):
                    tag = tag[len(f"{{{_R53_NS}}}"):]
                if child.text:
                    hc_config[tag] = child.text

        version_text = find_text(elem, "HealthCheckVersion", _R53_NS)
        version = int(version_text) if version_text else 0

        return R53HealthCheck(
            id=find_text(elem, "Id", _R53_NS) or "",
            caller_reference=find_text(elem, "CallerReference", _R53_NS) or "",
            health_check_config=hc_config,
            health_check_version=version,
        )

    # ------------------------------------------------------------------
    # Actions -- Hosted Zones
    # ------------------------------------------------------------------

    @action("List hosted zones")
    async def list_hosted_zones(self) -> list[R53HostedZone]:
        """List all Route 53 hosted zones in the account.

        Returns:
            List of R53HostedZone objects.
        """
        resp = await self._r53_request("GET", "hostedzone")
        root = ET.fromstring(resp.text)

        items: list[R53HostedZone] = []
        for elem in iter_elements(root, "HostedZone", _R53_NS):
            items.append(self._parse_hosted_zone(elem))
        return items

    @action("Get a hosted zone")
    async def get_hosted_zone(
        self, hosted_zone_id: str,
    ) -> R53HostedZone:
        """Retrieve a single hosted zone by its ID.

        Args:
            hosted_zone_id: The Route 53 hosted zone ID.

        Returns:
            R53HostedZone object with full details.
        """
        resp = await self._r53_request(
            "GET", f"hostedzone/{hosted_zone_id}",
        )
        root = ET.fromstring(resp.text)

        zone_elem = root.find(f"{{{_R53_NS}}}HostedZone")
        if zone_elem is None:
            zone_elem = root.find("HostedZone")
        if zone_elem is None:
            zone_elem = root
        return self._parse_hosted_zone(zone_elem)

    @action("Create a hosted zone")
    async def create_hosted_zone(
        self,
        name: str,
        caller_reference: str = "",
        comment: str = "",
    ) -> R53HostedZone:
        """Create a new Route 53 hosted zone.

        Args:
            name: The domain name for the hosted zone (e.g.
                ``example.com``).
            caller_reference: A unique string to identify the request.
                Auto-generated if not provided.
            comment: Optional comment for the hosted zone.

        Returns:
            The created R53HostedZone object.
        """
        if not caller_reference:
            caller_reference = str(uuid.uuid4())

        comment_xml = ""
        if comment:
            comment_xml = (
                "<HostedZoneConfig>"
                f"<Comment>{_xml_escape(comment)}</Comment>"
                "</HostedZoneConfig>"
            )

        body_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<CreateHostedZoneRequest xmlns="{_R53_NS}">'
            f"<Name>{_xml_escape(name)}</Name>"
            f"<CallerReference>{_xml_escape(caller_reference)}</CallerReference>"
            f"{comment_xml}"
            f"</CreateHostedZoneRequest>"
        ).encode()

        resp = await self._r53_request(
            "POST",
            "hostedzone",
            body=body_xml,
            extra_headers={"Content-Type": "application/xml"},
        )
        root = ET.fromstring(resp.text)

        zone_elem = root.find(f"{{{_R53_NS}}}HostedZone")
        if zone_elem is None:
            zone_elem = root.find("HostedZone")
        if zone_elem is None:
            zone_elem = root
        return self._parse_hosted_zone(zone_elem)

    @action("Delete a hosted zone", dangerous=True)
    async def delete_hosted_zone(
        self, hosted_zone_id: str,
    ) -> R53ChangeInfo:
        """Delete a Route 53 hosted zone.

        The zone must not contain any non-default record sets (SOA
        and NS records are automatically removed).

        Args:
            hosted_zone_id: The hosted zone ID to delete.

        Returns:
            R53ChangeInfo with the deletion status.
        """
        resp = await self._r53_request(
            "DELETE", f"hostedzone/{hosted_zone_id}",
        )
        root = ET.fromstring(resp.text)

        ci_elem = root.find(f"{{{_R53_NS}}}ChangeInfo")
        if ci_elem is None:
            ci_elem = root.find("ChangeInfo")
        if ci_elem is None:
            ci_elem = root
        return self._parse_change_info(ci_elem)

    # ------------------------------------------------------------------
    # Actions -- Records
    # ------------------------------------------------------------------

    @action("List resource record sets")
    async def list_resource_record_sets(
        self,
        hosted_zone_id: str,
        record_type: str = "",
        record_name: str = "",
    ) -> list[R53RecordSet]:
        """List resource record sets in a hosted zone.

        Args:
            hosted_zone_id: The hosted zone ID.
            record_type: Optional filter by record type (e.g. ``A``,
                ``CNAME``, ``MX``).
            record_name: Optional filter by record name.

        Returns:
            List of R53RecordSet objects.
        """
        params: dict[str, str] = {}
        if record_type:
            params["type"] = record_type
        if record_name:
            params["name"] = record_name

        resp = await self._r53_request(
            "GET",
            f"hostedzone/{hosted_zone_id}/rrset",
            params=params or None,
        )
        root = ET.fromstring(resp.text)

        items: list[R53RecordSet] = []
        for elem in iter_elements(root, "ResourceRecordSet", _R53_NS):
            items.append(self._parse_record_set(elem))
        return items

    @action("Create or update a DNS record")
    async def upsert_record(
        self,
        hosted_zone_id: str,
        name: str,
        record_type: str,
        ttl: int = 300,
        values: Optional[list[str]] = None,
        alias_target: Optional[dict] = None,
    ) -> R53ChangeInfo:
        """Create or update a DNS record in a hosted zone.

        For standard records, provide ``values`` (list of record values).
        For alias records, provide ``alias_target`` dict with
        ``hosted_zone_id``, ``dns_name``, and optionally
        ``evaluate_target_health``.

        Args:
            hosted_zone_id: The hosted zone ID.
            name: The DNS record name (e.g. ``www.example.com``).
            record_type: The record type (e.g. ``A``, ``CNAME``,
                ``MX``, ``TXT``).
            ttl: Time to live in seconds (ignored for alias records).
            values: List of record values for standard records.
            alias_target: Alias target configuration dict for alias
                records.

        Returns:
            R53ChangeInfo with the change status.
        """
        return await self._change_record(
            hosted_zone_id, "UPSERT", name, record_type,
            ttl=ttl, values=values, alias_target=alias_target,
        )

    @action("Delete a DNS record", dangerous=True)
    async def delete_record(
        self,
        hosted_zone_id: str,
        name: str,
        record_type: str,
        ttl: int = 300,
        values: Optional[list[str]] = None,
    ) -> R53ChangeInfo:
        """Delete a DNS record from a hosted zone.

        The record values and TTL must exactly match the existing
        record for deletion to succeed.

        Args:
            hosted_zone_id: The hosted zone ID.
            name: The DNS record name.
            record_type: The record type.
            ttl: Time to live (must match the existing record).
            values: Record values (must match the existing record).

        Returns:
            R53ChangeInfo with the change status.
        """
        return await self._change_record(
            hosted_zone_id, "DELETE", name, record_type,
            ttl=ttl, values=values,
        )

    async def _change_record(
        self,
        hosted_zone_id: str,
        change_action: str,
        name: str,
        record_type: str,
        *,
        ttl: int = 300,
        values: Optional[list[str]] = None,
        alias_target: Optional[dict] = None,
    ) -> R53ChangeInfo:
        """Build and submit a ChangeBatch request.

        Args:
            hosted_zone_id: The hosted zone ID.
            change_action: ``UPSERT``, ``CREATE``, or ``DELETE``.
            name: The DNS record name.
            record_type: The record type.
            ttl: Time to live in seconds.
            values: Record values for standard records.
            alias_target: Alias target dict for alias records.

        Returns:
            R53ChangeInfo with the change status.
        """
        if alias_target:
            eth = alias_target.get("evaluate_target_health", False)
            eth_str = "true" if eth else "false"
            rrset_xml = (
                f"<Name>{_xml_escape(name)}</Name>"
                f"<Type>{_xml_escape(record_type)}</Type>"
                f"<AliasTarget>"
                f"<HostedZoneId>{_xml_escape(alias_target.get('hosted_zone_id', ''))}</HostedZoneId>"
                f"<DNSName>{_xml_escape(alias_target.get('dns_name', ''))}</DNSName>"
                f"<EvaluateTargetHealth>{eth_str}</EvaluateTargetHealth>"
                f"</AliasTarget>"
            )
        else:
            rr_items = ""
            for v in (values or []):
                rr_items += f"<ResourceRecord><Value>{_xml_escape(v)}</Value></ResourceRecord>"
            rrset_xml = (
                f"<Name>{_xml_escape(name)}</Name>"
                f"<Type>{_xml_escape(record_type)}</Type>"
                f"<TTL>{ttl}</TTL>"
                f"<ResourceRecords>{rr_items}</ResourceRecords>"
            )

        body_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<ChangeResourceRecordSetsRequest xmlns="{_R53_NS}">'
            f"<ChangeBatch>"
            f"<Changes>"
            f"<Change>"
            f"<Action>{change_action}</Action>"
            f"<ResourceRecordSet>"
            f"{rrset_xml}"
            f"</ResourceRecordSet>"
            f"</Change>"
            f"</Changes>"
            f"</ChangeBatch>"
            f"</ChangeResourceRecordSetsRequest>"
        ).encode()

        resp = await self._r53_request(
            "POST",
            f"hostedzone/{hosted_zone_id}/rrset",
            body=body_xml,
            extra_headers={"Content-Type": "application/xml"},
        )
        root = ET.fromstring(resp.text)

        ci_elem = root.find(f"{{{_R53_NS}}}ChangeInfo")
        if ci_elem is None:
            ci_elem = root.find("ChangeInfo")
        if ci_elem is None:
            ci_elem = root
        return self._parse_change_info(ci_elem)

    # ------------------------------------------------------------------
    # Actions -- Health Checks
    # ------------------------------------------------------------------

    @action("Create a health check")
    async def create_health_check(
        self,
        fqdn: str,
        port: int = 443,
        type: str = "HTTPS",
        resource_path: str = "/",
        request_interval: int = 30,
        failure_threshold: int = 3,
    ) -> R53HealthCheck:
        """Create a Route 53 health check.

        Args:
            fqdn: Fully qualified domain name to check.
            port: Port number for the health check.
            type: Health check type (``HTTP``, ``HTTPS``, ``TCP``,
                ``HTTP_STR_MATCH``, ``HTTPS_STR_MATCH``).
            resource_path: Path for HTTP/HTTPS checks.
            request_interval: Seconds between health checks (10 or 30).
            failure_threshold: Number of consecutive failures before
                unhealthy (1-10).

        Returns:
            The created R53HealthCheck object.
        """
        caller_ref = str(uuid.uuid4())

        body_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<CreateHealthCheckRequest xmlns="{_R53_NS}">'
            f"<CallerReference>{caller_ref}</CallerReference>"
            f"<HealthCheckConfig>"
            f"<FullyQualifiedDomainName>{_xml_escape(fqdn)}</FullyQualifiedDomainName>"
            f"<Port>{port}</Port>"
            f"<Type>{_xml_escape(type)}</Type>"
            f"<ResourcePath>{_xml_escape(resource_path)}</ResourcePath>"
            f"<RequestInterval>{request_interval}</RequestInterval>"
            f"<FailureThreshold>{failure_threshold}</FailureThreshold>"
            f"</HealthCheckConfig>"
            f"</CreateHealthCheckRequest>"
        ).encode()

        resp = await self._r53_request(
            "POST",
            "healthcheck",
            body=body_xml,
            extra_headers={"Content-Type": "application/xml"},
        )
        root = ET.fromstring(resp.text)

        hc_elem = root.find(f"{{{_R53_NS}}}HealthCheck")
        if hc_elem is None:
            hc_elem = root.find("HealthCheck")
        if hc_elem is None:
            hc_elem = root
        return self._parse_health_check(hc_elem)

    @action("List health checks")
    async def list_health_checks(self) -> list[R53HealthCheck]:
        """List all Route 53 health checks.

        Returns:
            List of R53HealthCheck objects.
        """
        resp = await self._r53_request("GET", "healthcheck")
        root = ET.fromstring(resp.text)

        items: list[R53HealthCheck] = []
        for elem in iter_elements(root, "HealthCheck", _R53_NS):
            items.append(self._parse_health_check(elem))
        return items

    @action("Get a health check")
    async def get_health_check(
        self, health_check_id: str,
    ) -> R53HealthCheck:
        """Retrieve a single health check by its ID.

        Args:
            health_check_id: The health check ID.

        Returns:
            R53HealthCheck with full details.
        """
        resp = await self._r53_request(
            "GET", f"healthcheck/{health_check_id}",
        )
        root = ET.fromstring(resp.text)

        hc_elem = root.find(f"{{{_R53_NS}}}HealthCheck")
        if hc_elem is None:
            hc_elem = root.find("HealthCheck")
        if hc_elem is None:
            hc_elem = root
        return self._parse_health_check(hc_elem)

    @action("Delete a health check", dangerous=True)
    async def delete_health_check(
        self, health_check_id: str,
    ) -> dict:
        """Delete a Route 53 health check.

        Args:
            health_check_id: The health check ID to delete.

        Returns:
            Dict with ``deleted`` status.
        """
        await self._r53_request(
            "DELETE", f"healthcheck/{health_check_id}",
        )
        return {"deleted": True, "health_check_id": health_check_id}

    # ------------------------------------------------------------------
    # Actions -- Utility
    # ------------------------------------------------------------------

    @action("Test a DNS answer")
    async def test_dns_answer(
        self,
        hosted_zone_id: str,
        record_name: str,
        record_type: str,
    ) -> dict:
        """Test DNS resolution for a record in a hosted zone.

        Uses the Route 53 test DNS answer API to return what Route 53
        would respond with for a given query.

        Args:
            hosted_zone_id: The hosted zone ID.
            record_name: The DNS name to query.
            record_type: The record type to query (e.g. ``A``, ``AAAA``).

        Returns:
            Dict with ``nameserver``, ``record_name``, ``record_type``,
            ``response_code``, and ``record_data``.
        """
        resp = await self._r53_request(
            "GET",
            "testdnsanswer",
            params={
                "hostedzoneid": hosted_zone_id,
                "recordname": record_name,
                "recordtype": record_type,
            },
        )
        root = ET.fromstring(resp.text)

        record_data: list[str] = []
        for rd_elem in iter_elements(root, "RecordData", _R53_NS):
            for val_elem in iter_elements(rd_elem, "Value", _R53_NS):
                if val_elem.text:
                    record_data.append(val_elem.text)

        return {
            "nameserver": find_text(root, "Nameserver", _R53_NS) or "",
            "record_name": find_text(root, "RecordName", _R53_NS) or "",
            "record_type": find_text(root, "RecordType", _R53_NS) or "",
            "response_code": find_text(root, "ResponseCode", _R53_NS) or "",
            "record_data": record_data,
        }

    # ------------------------------------------------------------------
    # Actions -- Tags
    # ------------------------------------------------------------------

    @action("List tags for a resource")
    async def list_tags_for_resource(
        self,
        resource_type: str,
        resource_id: str,
    ) -> dict:
        """List tags for a Route 53 resource.

        Args:
            resource_type: Resource type (``hostedzone`` or
                ``healthcheck``).
            resource_id: The resource ID.

        Returns:
            Dict with ``tags`` key containing a dict of tag
            key-value pairs.
        """
        resp = await self._r53_request(
            "GET",
            f"tags/{_xml_escape(resource_type)}/{resource_id}",
        )
        root = ET.fromstring(resp.text)

        tags: dict[str, str] = {}
        for item in iter_elements(root, "Tag", _R53_NS):
            key = find_text(item, "Key", _R53_NS)
            value = find_text(item, "Value", _R53_NS)
            if key is not None:
                tags[key] = value or ""

        return {"tags": tags}

    @action("Change tags for a resource")
    async def change_tags_for_resource(
        self,
        resource_type: str,
        resource_id: str,
        add_tags: Optional[dict] = None,
        remove_tag_keys: Optional[list[str]] = None,
    ) -> dict:
        """Add or remove tags for a Route 53 resource.

        Args:
            resource_type: Resource type (``hostedzone`` or
                ``healthcheck``).
            resource_id: The resource ID.
            add_tags: Dict of tag key-value pairs to add.
            remove_tag_keys: List of tag keys to remove.

        Returns:
            Empty dict on success.
        """
        add_xml = ""
        if add_tags:
            tag_items = ""
            for k, v in add_tags.items():
                tag_items += (
                    f"<Tag>"
                    f"<Key>{_xml_escape(k)}</Key>"
                    f"<Value>{_xml_escape(str(v))}</Value>"
                    f"</Tag>"
                )
            add_xml = f"<AddTags>{tag_items}</AddTags>"

        remove_xml = ""
        if remove_tag_keys:
            key_items = ""
            for k in remove_tag_keys:
                key_items += f"<Key>{_xml_escape(k)}</Key>"
            remove_xml = f"<RemoveTagKeys>{key_items}</RemoveTagKeys>"

        body_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<ChangeTagsForResourceRequest xmlns="{_R53_NS}">'
            f"{add_xml}{remove_xml}"
            f"</ChangeTagsForResourceRequest>"
        ).encode()

        await self._r53_request(
            "POST",
            f"tags/{_xml_escape(resource_type)}/{resource_id}",
            body=body_xml,
            extra_headers={"Content-Type": "application/xml"},
        )
        return {}

    # ------------------------------------------------------------------
    # Actions -- Zone Count
    # ------------------------------------------------------------------

    @action("Get hosted zone count")
    async def get_hosted_zone_count(self) -> int:
        """Get the total number of hosted zones in the account.

        Returns:
            The number of hosted zones.
        """
        resp = await self._r53_request("GET", "hostedzonecount")
        root = ET.fromstring(resp.text)

        count_text = find_text(root, "HostedZoneCount", _R53_NS)
        return int(count_text) if count_text else 0


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


def _raise_r53_error(resp: httpx.Response) -> None:
    """Parse a Route 53 error response and raise AWSError.

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
