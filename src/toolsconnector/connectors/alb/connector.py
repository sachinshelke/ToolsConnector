"""AWS ALB connector -- manage Application Load Balancers.

Uses the ELBv2 Query API with ``Content-Type: application/x-www-form-urlencoded``.
Credentials should be ``"access_key:secret_key:region"`` format.

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
    ALBListener,
    ALBLoadBalancer,
    ALBRule,
    ALBTargetGroup,
    ALBTargetHealth,
)

logger = logging.getLogger("toolsconnector.alb")

# API version for the ELBv2 Query API.
_API_VERSION = "2015-12-01"

# XML namespaces used in ELBv2 responses.
_NS = {
    "ns": "http://elasticloadbalancing.amazonaws.com/doc/2015-12-01/",
}


class ALB(BaseConnector):
    """Connect to AWS ALB to manage load balancers, target groups, and listeners.

    Credentials format: ``"access_key_id:secret_access_key:region"``
    Uses the ELBv2 Query API (``Action=X&Version=2015-12-01``).

    .. note::

        SigV4 signing is simplified. For production, use ``boto3``.
    """

    name = "alb"
    display_name = "AWS ALB"
    category = ConnectorCategory.NETWORKING
    protocol = ProtocolType.REST
    base_url = "https://elasticloadbalancing.us-east-1.amazonaws.com"
    description = (
        "Manage Application Load Balancers, target groups, listeners, "
        "and routing rules."
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
        self._base_url = (
            f"https://elasticloadbalancing.{self._region}.amazonaws.com"
        )

        self._client = httpx.AsyncClient(timeout=self._timeout)

    async def _teardown(self) -> None:
        """Close the HTTP client."""
        if hasattr(self, "_client"):
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _encode_members(prefix: str, items: list[str]) -> dict[str, str]:
        """Encode a list into ALB ``.member.N`` query parameters.

        Args:
            prefix: Parameter prefix (e.g. ``Subnets``).
            items: List of string values.

        Returns:
            Dict of encoded parameters.
        """
        params: dict[str, str] = {}
        for i, item in enumerate(items, 1):
            params[f"{prefix}.member.{i}"] = item
        return params

    @staticmethod
    def _encode_target_members(
        prefix: str,
        targets: list[dict[str, Any]],
    ) -> dict[str, str]:
        """Encode a list of target dicts into ``.member.N.Key`` parameters.

        Args:
            prefix: Parameter prefix (e.g. ``Targets``).
            targets: List of target dicts with ``Id`` and optional ``Port``.

        Returns:
            Dict of encoded parameters.
        """
        params: dict[str, str] = {}
        for i, target in enumerate(targets, 1):
            params[f"{prefix}.member.{i}.Id"] = str(target["Id"])
            if "Port" in target:
                params[f"{prefix}.member.{i}.Port"] = str(target["Port"])
        return params

    @staticmethod
    def _encode_key_value_members(
        prefix: str,
        items: list[dict[str, str]],
        key_field: str = "Key",
        value_field: str = "Value",
    ) -> dict[str, str]:
        """Encode a list of key-value dicts into ``.member.N`` parameters.

        Args:
            prefix: Parameter prefix (e.g. ``Attributes``).
            items: List of dicts with key and value fields.
            key_field: Name of the key field in each dict.
            value_field: Name of the value field in each dict.

        Returns:
            Dict of encoded parameters.
        """
        params: dict[str, str] = {}
        for i, item in enumerate(items, 1):
            params[f"{prefix}.member.{i}.{key_field}"] = str(
                item[key_field]
            )
            params[f"{prefix}.member.{i}.{value_field}"] = str(
                item[value_field]
            )
        return params

    def _parse_xml(self, text: str) -> ET.Element:
        """Parse XML response text and return the root element.

        Args:
            text: Raw XML response body.

        Returns:
            Root XML Element.
        """
        return ET.fromstring(text)

    def _find_all(self, root: ET.Element, path: str) -> list[ET.Element]:
        """Find all elements at the given namespace-prefixed path.

        Args:
            root: Root XML element to search within.
            path: XPath expression using ``ns:`` prefix.

        Returns:
            List of matching elements.
        """
        return root.findall(path, _NS)

    def _find_text(
        self,
        element: ET.Element,
        path: str,
        default: str = "",
    ) -> str:
        """Find text content of a child element.

        Args:
            element: Parent XML element.
            path: XPath expression using ``ns:`` prefix.
            default: Default value if element is not found.

        Returns:
            Text content or default.
        """
        child = element.find(path, _NS)
        if child is not None and child.text is not None:
            return child.text
        return default

    async def _alb_request(
        self,
        api_action: str,
        params: dict[str, str] | None = None,
    ) -> ET.Element:
        """Execute a signed ELBv2 Query API request.

        Args:
            api_action: ELBv2 action name (e.g. ``CreateLoadBalancer``).
            params: Additional query parameters.

        Returns:
            Parsed XML root element.

        Raises:
            NotFoundError: If the resource is not found.
            APIError: For any ELBv2 API error.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")

        # Build form body.
        body_params: dict[str, str] = {
            "Action": api_action,
            "Version": _API_VERSION,
        }
        if params:
            body_params.update(params)

        body = urllib.parse.urlencode(body_params)
        payload_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()

        host = f"elasticloadbalancing.{self._region}.amazonaws.com"
        headers: dict[str, str] = {
            "Content-Type": "application/x-www-form-urlencoded",
            "x-amz-date": amz_date,
            "Host": host,
            "x-amz-content-sha256": payload_hash,
        }

        sign_v4(
            "POST",
            self._base_url + "/",
            headers,
            payload_hash,
            self._access_key,
            self._secret_key,
            self._region,
            "elasticloadbalancing",
            session_token=self._session_token,
        )

        response = await self._client.post(
            self._base_url + "/",
            content=body,
            headers=headers,
        )

        if response.status_code >= 400:
            # Parse XML error response.
            err_msg = response.text
            err_code = ""
            try:
                err_root = self._parse_xml(response.text)
                err_el = err_root.find(".//{http://elasticloadbalancing.amazonaws.com/doc/2015-12-01/}Message")
                code_el = err_root.find(".//{http://elasticloadbalancing.amazonaws.com/doc/2015-12-01/}Code")
                if err_el is None:
                    # Try without namespace for generic AWS error format.
                    err_el = err_root.find(".//Message")
                    code_el = err_root.find(".//Code")
                if err_el is not None and err_el.text:
                    err_msg = err_el.text
                if code_el is not None and code_el.text:
                    err_code = code_el.text
            except ET.ParseError:
                pass

            full_msg = f"ALB {api_action} error: {err_code} - {err_msg}"

            if "NotFound" in err_code or "TargetGroupNotFound" in err_code:
                raise NotFoundError(
                    full_msg,
                    connector="alb",
                    action=api_action,
                    details={"code": err_code, "message": err_msg},
                )
            raise APIError(
                full_msg,
                connector="alb",
                action=api_action,
                upstream_status=response.status_code,
                details={"code": err_code, "message": err_msg},
            )

        return self._parse_xml(response.text)

    # ------------------------------------------------------------------
    # Helpers -- model parsing
    # ------------------------------------------------------------------

    def _parse_load_balancer(self, el: ET.Element) -> ALBLoadBalancer:
        """Parse an XML LoadBalancer element into an ALBLoadBalancer model."""
        # Parse availability zones.
        azs: list[dict[str, Any]] = []
        for az_el in self._find_all(
            el, "ns:AvailabilityZones/ns:member"
        ):
            az: dict[str, Any] = {
                "ZoneName": self._find_text(az_el, "ns:ZoneName"),
                "SubnetId": self._find_text(az_el, "ns:SubnetId"),
            }
            azs.append(az)

        # Parse security groups.
        sgs: list[str] = []
        for sg_el in self._find_all(
            el, "ns:SecurityGroups/ns:member"
        ):
            if sg_el.text:
                sgs.append(sg_el.text)

        # Parse state.
        state = self._find_text(el, "ns:State/ns:Code")

        return ALBLoadBalancer(
            load_balancer_arn=self._find_text(el, "ns:LoadBalancerArn"),
            dns_name=self._find_text(el, "ns:DNSName"),
            name=self._find_text(el, "ns:LoadBalancerName"),
            scheme=self._find_text(el, "ns:Scheme"),
            state=state,
            type=self._find_text(el, "ns:Type"),
            vpc_id=self._find_text(el, "ns:VpcId"),
            availability_zones=azs,
            security_groups=sgs,
            created_time=self._find_text(el, "ns:CreatedTime") or None,
        )

    def _parse_target_group(self, el: ET.Element) -> ALBTargetGroup:
        """Parse an XML TargetGroup element into an ALBTargetGroup model."""
        port_text = self._find_text(el, "ns:Port", "0")
        hc_interval_text = self._find_text(
            el, "ns:HealthCheckIntervalSeconds", "30"
        )
        healthy_text = self._find_text(
            el, "ns:HealthyThresholdCount", "5"
        )
        unhealthy_text = self._find_text(
            el, "ns:UnhealthyThresholdCount", "2"
        )

        return ALBTargetGroup(
            target_group_arn=self._find_text(el, "ns:TargetGroupArn"),
            target_group_name=self._find_text(el, "ns:TargetGroupName"),
            protocol=self._find_text(el, "ns:Protocol"),
            port=int(port_text),
            vpc_id=self._find_text(el, "ns:VpcId"),
            health_check_protocol=self._find_text(
                el, "ns:HealthCheckProtocol"
            ),
            health_check_path=self._find_text(el, "ns:HealthCheckPath"),
            health_check_interval_seconds=int(hc_interval_text),
            healthy_threshold_count=int(healthy_text),
            unhealthy_threshold_count=int(unhealthy_text),
            target_type=self._find_text(el, "ns:TargetType"),
        )

    def _parse_listener(self, el: ET.Element) -> ALBListener:
        """Parse an XML Listener element into an ALBListener model."""
        port_text = self._find_text(el, "ns:Port", "0")

        # Parse certificates.
        certs: list[dict[str, Any]] = []
        for cert_el in self._find_all(el, "ns:Certificates/ns:member"):
            certs.append({
                "CertificateArn": self._find_text(
                    cert_el, "ns:CertificateArn"
                ),
            })

        # Parse default actions.
        actions: list[dict[str, Any]] = []
        for act_el in self._find_all(el, "ns:DefaultActions/ns:member"):
            act: dict[str, Any] = {
                "Type": self._find_text(act_el, "ns:Type"),
            }
            tg_arn = self._find_text(act_el, "ns:TargetGroupArn")
            if tg_arn:
                act["TargetGroupArn"] = tg_arn
            actions.append(act)

        return ALBListener(
            listener_arn=self._find_text(el, "ns:ListenerArn"),
            load_balancer_arn=self._find_text(el, "ns:LoadBalancerArn"),
            port=int(port_text),
            protocol=self._find_text(el, "ns:Protocol"),
            ssl_policy=self._find_text(el, "ns:SslPolicy"),
            certificates=certs,
            default_actions=actions,
        )

    def _parse_rule(self, el: ET.Element) -> ALBRule:
        """Parse an XML Rule element into an ALBRule model."""
        # Parse conditions.
        conditions: list[dict[str, Any]] = []
        for cond_el in self._find_all(el, "ns:Conditions/ns:member"):
            cond: dict[str, Any] = {
                "Field": self._find_text(cond_el, "ns:Field"),
            }
            values: list[str] = []
            for val_el in self._find_all(cond_el, "ns:Values/ns:member"):
                if val_el.text:
                    values.append(val_el.text)
            if values:
                cond["Values"] = values
            conditions.append(cond)

        # Parse actions.
        actions: list[dict[str, Any]] = []
        for act_el in self._find_all(el, "ns:Actions/ns:member"):
            act: dict[str, Any] = {
                "Type": self._find_text(act_el, "ns:Type"),
            }
            tg_arn = self._find_text(act_el, "ns:TargetGroupArn")
            if tg_arn:
                act["TargetGroupArn"] = tg_arn
            actions.append(act)

        is_default_text = self._find_text(el, "ns:IsDefault", "false")

        return ALBRule(
            rule_arn=self._find_text(el, "ns:RuleArn"),
            priority=self._find_text(el, "ns:Priority"),
            conditions=conditions,
            actions=actions,
            is_default=is_default_text.lower() == "true",
        )

    def _parse_target_health(
        self,
        el: ET.Element,
    ) -> ALBTargetHealth:
        """Parse an XML TargetHealthDescription into an ALBTargetHealth model."""
        target_el = el.find("ns:Target", _NS)
        target_id = ""
        target_port = 0
        if target_el is not None:
            target_id = self._find_text(target_el, "ns:Id")
            port_text = self._find_text(target_el, "ns:Port", "0")
            target_port = int(port_text)

        health_el = el.find("ns:TargetHealth", _NS)
        health_status = ""
        health_desc = ""
        if health_el is not None:
            health_status = self._find_text(health_el, "ns:State")
            health_desc = self._find_text(health_el, "ns:Description")

        return ALBTargetHealth(
            target_id=target_id,
            target_port=target_port,
            health_status=health_status,
            health_description=health_desc,
        )

    # ==================================================================
    # Actions -- Load Balancers
    # ==================================================================

    @action("Create an Application Load Balancer")
    async def create_load_balancer(
        self,
        name: str,
        subnets: list[str],
        security_groups: Optional[list[str]] = None,
        scheme: str = "internet-facing",
        ip_address_type: str = "ipv4",
    ) -> ALBLoadBalancer:
        """Create a new Application Load Balancer.

        Args:
            name: The name of the load balancer.
            subnets: List of subnet IDs (minimum 2 from different AZs).
            security_groups: List of security group IDs.
            scheme: Load balancer scheme (internet-facing or internal).
            ip_address_type: IP address type (ipv4 or dualstack).

        Returns:
            The created ALBLoadBalancer.
        """
        params: dict[str, str] = {
            "Name": name,
            "Scheme": scheme,
            "IpAddressType": ip_address_type,
            "Type": "application",
        }
        params.update(self._encode_members("Subnets", subnets))
        if security_groups:
            params.update(
                self._encode_members("SecurityGroups", security_groups)
            )

        root = await self._alb_request("CreateLoadBalancer", params)
        lbs = self._find_all(
            root,
            ".//ns:LoadBalancers/ns:member",
        )
        if not lbs:
            raise APIError(
                "CreateLoadBalancer returned no load balancers",
                connector="alb",
                action="CreateLoadBalancer",
            )
        return self._parse_load_balancer(lbs[0])

    @action("Describe load balancers")
    async def describe_load_balancers(
        self,
        names: Optional[list[str]] = None,
        arns: Optional[list[str]] = None,
    ) -> list[ALBLoadBalancer]:
        """Describe one or more load balancers.

        Args:
            names: Filter by load balancer names.
            arns: Filter by load balancer ARNs.

        Returns:
            List of ALBLoadBalancer objects.
        """
        params: dict[str, str] = {}
        if names:
            params.update(self._encode_members("Names", names))
        if arns:
            params.update(
                self._encode_members("LoadBalancerArns", arns)
            )

        root = await self._alb_request("DescribeLoadBalancers", params)
        return [
            self._parse_load_balancer(el)
            for el in self._find_all(
                root, ".//ns:LoadBalancers/ns:member"
            )
        ]

    @action("Delete a load balancer", dangerous=True)
    async def delete_load_balancer(
        self,
        load_balancer_arn: str,
    ) -> dict:
        """Delete a load balancer.

        Args:
            load_balancer_arn: The ARN of the load balancer to delete.

        Returns:
            Empty dict on success.
        """
        await self._alb_request(
            "DeleteLoadBalancer",
            {"LoadBalancerArn": load_balancer_arn},
        )
        return {}

    @action("Modify load balancer attributes")
    async def modify_load_balancer_attributes(
        self,
        load_balancer_arn: str,
        attributes: dict,
    ) -> dict:
        """Modify load balancer attributes.

        Args:
            load_balancer_arn: The ARN of the load balancer.
            attributes: Dict of attribute key-value pairs to set
                (e.g. ``{"idle_timeout.timeout_seconds": "60"}``).

        Returns:
            Dict with updated attributes.
        """
        params: dict[str, str] = {
            "LoadBalancerArn": load_balancer_arn,
        }
        attr_list = [
            {"Key": k, "Value": str(v)} for k, v in attributes.items()
        ]
        params.update(
            self._encode_key_value_members("Attributes", attr_list)
        )

        root = await self._alb_request(
            "ModifyLoadBalancerAttributes", params
        )
        result_attrs: list[dict[str, str]] = []
        for el in self._find_all(root, ".//ns:Attributes/ns:member"):
            result_attrs.append({
                "Key": self._find_text(el, "ns:Key"),
                "Value": self._find_text(el, "ns:Value"),
            })
        return {"attributes": result_attrs}

    # ==================================================================
    # Actions -- Target Groups
    # ==================================================================

    @action("Create a target group")
    async def create_target_group(
        self,
        name: str,
        protocol: str = "HTTP",
        port: int = 80,
        vpc_id: str = "",
        target_type: str = "ip",
        health_check_path: str = "/",
    ) -> ALBTargetGroup:
        """Create a new target group.

        Args:
            name: The name of the target group.
            protocol: Protocol for routing traffic (HTTP, HTTPS).
            port: Port for routing traffic.
            vpc_id: VPC ID for the target group.
            target_type: Target type (instance, ip, lambda, alb).
            health_check_path: Path for health checks.

        Returns:
            The created ALBTargetGroup.
        """
        params: dict[str, str] = {
            "Name": name,
            "Protocol": protocol,
            "Port": str(port),
            "TargetType": target_type,
            "HealthCheckPath": health_check_path,
        }
        if vpc_id:
            params["VpcId"] = vpc_id

        root = await self._alb_request("CreateTargetGroup", params)
        tgs = self._find_all(
            root, ".//ns:TargetGroups/ns:member"
        )
        if not tgs:
            raise APIError(
                "CreateTargetGroup returned no target groups",
                connector="alb",
                action="CreateTargetGroup",
            )
        return self._parse_target_group(tgs[0])

    @action("Describe target groups")
    async def describe_target_groups(
        self,
        names: Optional[list[str]] = None,
        arns: Optional[list[str]] = None,
    ) -> list[ALBTargetGroup]:
        """Describe one or more target groups.

        Args:
            names: Filter by target group names.
            arns: Filter by target group ARNs.

        Returns:
            List of ALBTargetGroup objects.
        """
        params: dict[str, str] = {}
        if names:
            params.update(self._encode_members("Names", names))
        if arns:
            params.update(
                self._encode_members("TargetGroupArns", arns)
            )

        root = await self._alb_request("DescribeTargetGroups", params)
        return [
            self._parse_target_group(el)
            for el in self._find_all(
                root, ".//ns:TargetGroups/ns:member"
            )
        ]

    @action("Delete a target group", dangerous=True)
    async def delete_target_group(
        self,
        target_group_arn: str,
    ) -> dict:
        """Delete a target group.

        Args:
            target_group_arn: The ARN of the target group to delete.

        Returns:
            Empty dict on success.
        """
        await self._alb_request(
            "DeleteTargetGroup",
            {"TargetGroupArn": target_group_arn},
        )
        return {}

    @action("Register targets with a target group")
    async def register_targets(
        self,
        target_group_arn: str,
        targets: list[dict],
    ) -> dict:
        """Register targets with a target group.

        Args:
            target_group_arn: The ARN of the target group.
            targets: List of target dicts with ``Id`` and optional ``Port``
                (e.g. ``[{"Id": "i-123", "Port": 80}]``).

        Returns:
            Empty dict on success.
        """
        params: dict[str, str] = {
            "TargetGroupArn": target_group_arn,
        }
        params.update(self._encode_target_members("Targets", targets))

        await self._alb_request("RegisterTargets", params)
        return {}

    @action("Deregister targets from a target group")
    async def deregister_targets(
        self,
        target_group_arn: str,
        targets: list[dict],
    ) -> dict:
        """Deregister targets from a target group.

        Args:
            target_group_arn: The ARN of the target group.
            targets: List of target dicts with ``Id`` and optional ``Port``
                (e.g. ``[{"Id": "i-123", "Port": 80}]``).

        Returns:
            Empty dict on success.
        """
        params: dict[str, str] = {
            "TargetGroupArn": target_group_arn,
        }
        params.update(self._encode_target_members("Targets", targets))

        await self._alb_request("DeregisterTargets", params)
        return {}

    @action("Describe target health")
    async def describe_target_health(
        self,
        target_group_arn: str,
    ) -> list[ALBTargetHealth]:
        """Describe the health of targets in a target group.

        Args:
            target_group_arn: The ARN of the target group.

        Returns:
            List of ALBTargetHealth objects.
        """
        root = await self._alb_request(
            "DescribeTargetHealth",
            {"TargetGroupArn": target_group_arn},
        )
        return [
            self._parse_target_health(el)
            for el in self._find_all(
                root,
                ".//ns:TargetHealthDescriptions/ns:member",
            )
        ]

    # ==================================================================
    # Actions -- Listeners
    # ==================================================================

    @action("Create a listener on a load balancer")
    async def create_listener(
        self,
        load_balancer_arn: str,
        port: int = 80,
        protocol: str = "HTTP",
        default_action_type: str = "forward",
        target_group_arn: str = "",
        certificate_arn: str = "",
    ) -> ALBListener:
        """Create a listener on a load balancer.

        Args:
            load_balancer_arn: The ARN of the load balancer.
            port: Port for the listener.
            protocol: Protocol (HTTP, HTTPS).
            default_action_type: Default action type (forward, redirect, fixed-response).
            target_group_arn: Target group ARN for forward actions.
            certificate_arn: ACM certificate ARN for HTTPS listeners.

        Returns:
            The created ALBListener.
        """
        params: dict[str, str] = {
            "LoadBalancerArn": load_balancer_arn,
            "Port": str(port),
            "Protocol": protocol,
            "DefaultActions.member.1.Type": default_action_type,
        }
        if target_group_arn:
            params["DefaultActions.member.1.TargetGroupArn"] = (
                target_group_arn
            )
        if certificate_arn:
            params["Certificates.member.1.CertificateArn"] = (
                certificate_arn
            )

        root = await self._alb_request("CreateListener", params)
        listeners = self._find_all(
            root, ".//ns:Listeners/ns:member"
        )
        if not listeners:
            raise APIError(
                "CreateListener returned no listeners",
                connector="alb",
                action="CreateListener",
            )
        return self._parse_listener(listeners[0])

    @action("Describe listeners")
    async def describe_listeners(
        self,
        load_balancer_arn: str,
    ) -> list[ALBListener]:
        """Describe listeners for a load balancer.

        Args:
            load_balancer_arn: The ARN of the load balancer.

        Returns:
            List of ALBListener objects.
        """
        root = await self._alb_request(
            "DescribeListeners",
            {"LoadBalancerArn": load_balancer_arn},
        )
        return [
            self._parse_listener(el)
            for el in self._find_all(
                root, ".//ns:Listeners/ns:member"
            )
        ]

    @action("Delete a listener", dangerous=True)
    async def delete_listener(
        self,
        listener_arn: str,
    ) -> dict:
        """Delete a listener.

        Args:
            listener_arn: The ARN of the listener to delete.

        Returns:
            Empty dict on success.
        """
        await self._alb_request(
            "DeleteListener",
            {"ListenerArn": listener_arn},
        )
        return {}

    @action("Modify a listener")
    async def modify_listener(
        self,
        listener_arn: str,
        port: Optional[int] = None,
        protocol: Optional[str] = None,
        default_action_type: str = "forward",
        target_group_arn: str = "",
        certificate_arn: str = "",
    ) -> ALBListener:
        """Modify a listener.

        Args:
            listener_arn: The ARN of the listener to modify.
            port: New port for the listener.
            protocol: New protocol (HTTP, HTTPS).
            default_action_type: Default action type (forward, redirect, fixed-response).
            target_group_arn: Target group ARN for forward actions.
            certificate_arn: ACM certificate ARN for HTTPS.

        Returns:
            The modified ALBListener.
        """
        params: dict[str, str] = {
            "ListenerArn": listener_arn,
            "DefaultActions.member.1.Type": default_action_type,
        }
        if port is not None:
            params["Port"] = str(port)
        if protocol is not None:
            params["Protocol"] = protocol
        if target_group_arn:
            params["DefaultActions.member.1.TargetGroupArn"] = (
                target_group_arn
            )
        if certificate_arn:
            params["Certificates.member.1.CertificateArn"] = (
                certificate_arn
            )

        root = await self._alb_request("ModifyListener", params)
        listeners = self._find_all(
            root, ".//ns:Listeners/ns:member"
        )
        if not listeners:
            raise APIError(
                "ModifyListener returned no listeners",
                connector="alb",
                action="ModifyListener",
            )
        return self._parse_listener(listeners[0])

    # ==================================================================
    # Actions -- Rules
    # ==================================================================

    @action("Create a routing rule on a listener")
    async def create_rule(
        self,
        listener_arn: str,
        priority: int,
        conditions: list[dict],
        action_type: str = "forward",
        target_group_arn: str = "",
    ) -> ALBRule:
        """Create a routing rule on a listener.

        Args:
            listener_arn: The ARN of the listener.
            priority: Rule priority (1-50000, lower is evaluated first).
            conditions: List of condition dicts (e.g.
                ``[{"Field": "path-pattern", "Values": ["/api/*"]}]``).
            action_type: Action type (forward, redirect, fixed-response).
            target_group_arn: Target group ARN for forward actions.

        Returns:
            The created ALBRule.
        """
        params: dict[str, str] = {
            "ListenerArn": listener_arn,
            "Priority": str(priority),
            "Actions.member.1.Type": action_type,
        }
        if target_group_arn:
            params["Actions.member.1.TargetGroupArn"] = target_group_arn

        # Encode conditions.
        for i, cond in enumerate(conditions, 1):
            params[f"Conditions.member.{i}.Field"] = cond.get(
                "Field", ""
            )
            for j, val in enumerate(cond.get("Values", []), 1):
                params[f"Conditions.member.{i}.Values.member.{j}"] = val

        root = await self._alb_request("CreateRule", params)
        rules = self._find_all(root, ".//ns:Rules/ns:member")
        if not rules:
            raise APIError(
                "CreateRule returned no rules",
                connector="alb",
                action="CreateRule",
            )
        return self._parse_rule(rules[0])

    @action("Describe rules for a listener")
    async def describe_rules(
        self,
        listener_arn: str,
    ) -> list[ALBRule]:
        """Describe routing rules for a listener.

        Args:
            listener_arn: The ARN of the listener.

        Returns:
            List of ALBRule objects.
        """
        root = await self._alb_request(
            "DescribeRules",
            {"ListenerArn": listener_arn},
        )
        return [
            self._parse_rule(el)
            for el in self._find_all(root, ".//ns:Rules/ns:member")
        ]

    @action("Delete a routing rule", dangerous=True)
    async def delete_rule(
        self,
        rule_arn: str,
    ) -> dict:
        """Delete a routing rule.

        Args:
            rule_arn: The ARN of the rule to delete.

        Returns:
            Empty dict on success.
        """
        await self._alb_request(
            "DeleteRule",
            {"RuleArn": rule_arn},
        )
        return {}

    @action("Modify a routing rule")
    async def modify_rule(
        self,
        rule_arn: str,
        conditions: Optional[list[dict]] = None,
        action_type: str = "forward",
        target_group_arn: str = "",
    ) -> ALBRule:
        """Modify a routing rule.

        Args:
            rule_arn: The ARN of the rule to modify.
            conditions: New list of condition dicts (e.g.
                ``[{"Field": "path-pattern", "Values": ["/api/*"]}]``).
            action_type: Action type (forward, redirect, fixed-response).
            target_group_arn: Target group ARN for forward actions.

        Returns:
            The modified ALBRule.
        """
        params: dict[str, str] = {
            "RuleArn": rule_arn,
            "Actions.member.1.Type": action_type,
        }
        if target_group_arn:
            params["Actions.member.1.TargetGroupArn"] = target_group_arn

        if conditions is not None:
            for i, cond in enumerate(conditions, 1):
                params[f"Conditions.member.{i}.Field"] = cond.get(
                    "Field", ""
                )
                for j, val in enumerate(cond.get("Values", []), 1):
                    params[
                        f"Conditions.member.{i}.Values.member.{j}"
                    ] = val

        root = await self._alb_request("ModifyRule", params)
        rules = self._find_all(root, ".//ns:Rules/ns:member")
        if not rules:
            raise APIError(
                "ModifyRule returned no rules",
                connector="alb",
                action="ModifyRule",
            )
        return self._parse_rule(rules[0])
