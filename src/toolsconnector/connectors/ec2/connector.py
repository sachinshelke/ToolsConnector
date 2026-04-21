"""AWS EC2 connector -- launch and manage virtual server instances.

Uses the EC2 Query API with ``Action`` and ``Version`` parameters in
form-encoded POST bodies. Credentials should be a JSON string or dict
containing ``access_key_id``, ``secret_access_key``, and optionally
``region`` (defaults to ``us-east-1``).

EC2 responses are XML-formatted with the namespace
``http://ec2.amazonaws.com/doc/2016-11-15/``.

.. note::

    The SigV4 signing implementation is simplified. For production
    workloads, ``boto3`` is strongly recommended.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import logging
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any, Optional, Union

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
    EC2Address,
    EC2Image,
    EC2Instance,
    EC2InstanceType,
    EC2KeyPair,
    EC2SecurityGroup,
    EC2Subnet,
    EC2Volume,
    EC2Vpc,
)

logger = logging.getLogger("toolsconnector.ec2")

# EC2 XML namespace for API version 2016-11-15.
_NS = "http://ec2.amazonaws.com/doc/2016-11-15/"


# ------------------------------------------------------------------
# XML namespace helpers
# ------------------------------------------------------------------


def _find(elem: ET.Element, tag: str) -> str:
    """Find a direct child element's text by tag name within the EC2 namespace.

    Args:
        elem: Parent XML element.
        tag: Tag name without namespace prefix.

    Returns:
        Element text or empty string if not found.
    """
    return elem.findtext(f"{{{_NS}}}{tag}", default="")


def _findall(elem: ET.Element, tag: str) -> list[ET.Element]:
    """Find all child elements by tag name within the EC2 namespace.

    Args:
        elem: Parent XML element.
        tag: Tag name without namespace prefix.

    Returns:
        List of matching elements.
    """
    return elem.findall(f"{{{_NS}}}{tag}")


def _find_deep(elem: ET.Element, path: str) -> str:
    """Find nested element text using a dotted path within the EC2 namespace.

    For example, ``_find_deep(elem, "placement.availabilityZone")``
    resolves ``<placement><availabilityZone>...</availabilityZone></placement>``.

    Args:
        elem: Root XML element.
        path: Dot-separated path of tag names.

    Returns:
        Element text or empty string if not found.
    """
    parts = path.split(".")
    current: Optional[ET.Element] = elem
    for part in parts[:-1]:
        if current is None:
            return ""
        current = current.find(f"{{{_NS}}}{part}")
    if current is None:
        return ""
    return current.findtext(f"{{{_NS}}}{parts[-1]}", default="")


# ------------------------------------------------------------------
# EC2 parameter encoding helpers
# ------------------------------------------------------------------


def _encode_list(prefix: str, items: list[str]) -> dict[str, str]:
    """Encode a list of values into EC2 numbered parameter format.

    EC2 uses ``Prefix.N`` notation for list parameters. For example::

        _encode_list("SecurityGroupId", ["sg-123", "sg-456"])
        => {"SecurityGroupId.1": "sg-123", "SecurityGroupId.2": "sg-456"}

    Args:
        prefix: Parameter name prefix.
        items: List of string values.

    Returns:
        Dict of numbered parameter entries.
    """
    return {f"{prefix}.{i}": v for i, v in enumerate(items, 1)}


def _encode_filters(filters: dict[str, Union[str, list[str]]]) -> dict[str, str]:
    """Encode a filter dict into EC2 numbered filter parameter format.

    EC2 uses ``Filter.N.Name`` and ``Filter.N.Value.M`` notation::

        _encode_filters({"instance-state-name": "running"})
        => {"Filter.1.Name": "instance-state-name",
            "Filter.1.Value.1": "running"}

    Args:
        filters: Mapping of filter name to value or list of values.

    Returns:
        Dict of numbered filter parameter entries.
    """
    params: dict[str, str] = {}
    for idx, (name, values) in enumerate(filters.items(), 1):
        params[f"Filter.{idx}.Name"] = name
        if isinstance(values, str):
            values = [values]
        for vidx, val in enumerate(values, 1):
            params[f"Filter.{idx}.Value.{vidx}"] = val
    return params


def _parse_tags(item: ET.Element) -> dict[str, str]:
    """Extract tags from an EC2 XML element's tagSet.

    Args:
        item: XML element containing a ``tagSet`` child.

    Returns:
        Dict mapping tag keys to values.
    """
    tags: dict[str, str] = {}
    tag_set = item.find(f"{{{_NS}}}tagSet")
    if tag_set is not None:
        for tag_item in _findall(tag_set, "item"):
            key = _find(tag_item, "key")
            val = _find(tag_item, "value")
            if key:
                tags[key] = val
    return tags


class EC2(BaseConnector):
    """Connect to AWS EC2 to launch and manage virtual server instances.

    Authenticates using AWS Signature Version 4. Credentials should be
    provided as a JSON string or dict::

        {
            "access_key_id": "AKIA...",
            "secret_access_key": "...",
            "region": "us-east-1"
        }

    Uses the EC2 Query API (``Action=X&Version=2016-11-15``) with
    form-encoded POST requests.

    .. note::

        SigV4 signing is simplified. For production, use ``boto3``.
    """

    name = "ec2"
    display_name = "AWS EC2"
    category = ConnectorCategory.COMPUTE
    protocol = ProtocolType.REST
    base_url = "https://ec2.us-east-1.amazonaws.com"
    description = (
        "Launch and manage EC2 instances, security groups, key pairs, "
        "and Elastic IPs."
    )
    _rate_limit_config = RateLimitSpec(rate=100, period=1, burst=200)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Parse credentials and initialise the HTTP client."""
        from toolsconnector.connectors._aws.auth import parse_credentials

        creds = parse_credentials(self._credentials)
        self._access_key_id = creds.access_key_id
        self._secret_access_key = creds.secret_access_key
        self._region = creds.region
        self._session_token = creds.session_token
        self._host = f"ec2.{self._region}.amazonaws.com"
        self._endpoint = f"https://{self._host}"
        self._api_version = "2016-11-15"

        self._client = httpx.AsyncClient(timeout=self._timeout)

    async def _teardown(self) -> None:
        """Close the HTTP client."""
        if hasattr(self, "_client"):
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _ec2_request(
        self,
        ec2_action: str,
        params: Optional[dict[str, str]] = None,
    ) -> ET.Element:
        """Send a Query API request to EC2.

        Args:
            ec2_action: EC2 API action name (e.g. ``DescribeInstances``).
            params: Additional form parameters for the request.

        Returns:
            Parsed XML root element of the response.

        Raises:
            NotFoundError: If the resource is not found.
            APIError: For any EC2 API error.
        """
        form_params: dict[str, str] = {
            "Action": ec2_action,
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
            "ec2",
            session_token=self._session_token,
        )

        resp = await self._client.post(
            self._endpoint + "/",
            content=body,
            headers=headers,
        )

        if resp.status_code >= 400:
            error_msg = f"EC2 {ec2_action} error"
            error_code = ""
            try:
                err_root = ET.fromstring(resp.text)
                # EC2 error XML: <Response><Errors><Error><Code/><Message/></Error></Errors></Response>
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

            full_msg = f"EC2 {ec2_action}: {error_code} - {error_msg}"

            if "NotFound" in error_code or "InvalidInstanceID" in error_code:
                raise NotFoundError(
                    full_msg,
                    connector="ec2",
                    action=ec2_action,
                    details={"code": error_code, "message": error_msg},
                )
            raise APIError(
                full_msg,
                connector="ec2",
                action=ec2_action,
                upstream_status=resp.status_code,
                details={"code": error_code, "message": error_msg},
            )

        return ET.fromstring(resp.text)

    # ------------------------------------------------------------------
    # Model parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_instance(item: ET.Element) -> EC2Instance:
        """Parse an EC2 instance XML element into an EC2Instance model.

        Args:
            item: XML ``<item>`` element from ``<instancesSet>``.

        Returns:
            EC2Instance model.
        """
        # Security groups
        sgs: list[dict[str, Any]] = []
        sg_set = item.find(f"{{{_NS}}}groupSet")
        if sg_set is not None:
            for sg_item in _findall(sg_set, "item"):
                sgs.append({
                    "group_id": _find(sg_item, "groupId"),
                    "group_name": _find(sg_item, "groupName"),
                })

        # State
        state_elem = item.find(f"{{{_NS}}}instanceState")
        state = ""
        if state_elem is not None:
            state = _find(state_elem, "name")

        return EC2Instance(
            instance_id=_find(item, "instanceId"),
            instance_type=_find(item, "instanceType"),
            state=state,
            public_ip=_find(item, "ipAddress") or None,
            private_ip=_find(item, "privateIpAddress") or None,
            launch_time=_find(item, "launchTime") or None,
            availability_zone=_find_deep(item, "placement.availabilityZone"),
            subnet_id=_find(item, "subnetId"),
            vpc_id=_find(item, "vpcId"),
            security_groups=sgs,
            tags=_parse_tags(item),
            image_id=_find(item, "imageId"),
            key_name=_find(item, "keyName"),
            platform=_find(item, "platform"),
        )

    @staticmethod
    def _parse_key_pair(item: ET.Element) -> EC2KeyPair:
        """Parse a key pair XML element into an EC2KeyPair model.

        Args:
            item: XML ``<item>`` element from key pair responses.

        Returns:
            EC2KeyPair model.
        """
        return EC2KeyPair(
            key_name=_find(item, "keyName"),
            key_pair_id=_find(item, "keyPairId"),
            key_fingerprint=_find(item, "keyFingerprint"),
            key_material=_find(item, "keyMaterial") or None,
        )

    @staticmethod
    def _parse_security_group(item: ET.Element) -> EC2SecurityGroup:
        """Parse a security group XML element into an EC2SecurityGroup model.

        Args:
            item: XML ``<item>`` element from security group responses.

        Returns:
            EC2SecurityGroup model.
        """
        def _parse_ip_perms(parent_tag: str) -> list[dict[str, Any]]:
            perms: list[dict[str, Any]] = []
            perm_set = item.find(f"{{{_NS}}}{parent_tag}")
            if perm_set is not None:
                for perm_item in _findall(perm_set, "item"):
                    ip_ranges: list[str] = []
                    ranges_set = perm_item.find(f"{{{_NS}}}ipRanges")
                    if ranges_set is not None:
                        for r in _findall(ranges_set, "item"):
                            cidr = _find(r, "cidrIp")
                            if cidr:
                                ip_ranges.append(cidr)
                    perms.append({
                        "ip_protocol": _find(perm_item, "ipProtocol"),
                        "from_port": _find(perm_item, "fromPort"),
                        "to_port": _find(perm_item, "toPort"),
                        "ip_ranges": ip_ranges,
                    })
            return perms

        return EC2SecurityGroup(
            group_id=_find(item, "groupId"),
            group_name=_find(item, "groupName"),
            description=_find(item, "groupDescription"),
            vpc_id=_find(item, "vpcId"),
            ip_permissions=_parse_ip_perms("ipPermissions"),
            ip_permissions_egress=_parse_ip_perms("ipPermissionsEgress"),
            tags=_parse_tags(item),
        )

    @staticmethod
    def _parse_address(item: ET.Element) -> EC2Address:
        """Parse an Elastic IP XML element into an EC2Address model.

        Args:
            item: XML ``<item>`` element from address responses.

        Returns:
            EC2Address model.
        """
        return EC2Address(
            allocation_id=_find(item, "allocationId"),
            public_ip=_find(item, "publicIp"),
            instance_id=_find(item, "instanceId"),
            association_id=_find(item, "associationId"),
            domain=_find(item, "domain"),
            network_interface_id=_find(item, "networkInterfaceId"),
            tags=_parse_tags(item),
        )

    @staticmethod
    def _parse_image(item: ET.Element) -> EC2Image:
        """Parse an AMI image XML element into an EC2Image model.

        Args:
            item: XML ``<item>`` element from image responses.

        Returns:
            EC2Image model.
        """
        return EC2Image(
            image_id=_find(item, "imageId"),
            name=_find(item, "name"),
            description=_find(item, "description"),
            state=_find(item, "imageState"),
            architecture=_find(item, "architecture"),
            platform_details=_find(item, "platformDetails"),
            owner_id=_find(item, "imageOwnerId"),
            creation_date=_find(item, "creationDate") or None,
            public=_find(item, "isPublic") == "true",
        )

    @staticmethod
    def _parse_instance_type(item: ET.Element) -> EC2InstanceType:
        """Parse an instance type XML element into an EC2InstanceType model.

        Args:
            item: XML ``<item>`` element from instance type responses.

        Returns:
            EC2InstanceType model.
        """
        vcpu_info = item.find(f"{{{_NS}}}vCpuInfo")
        vcpu_count = 0
        if vcpu_info is not None:
            raw = _find(vcpu_info, "defaultVCpus")
            vcpu_count = int(raw) if raw else 0

        mem_info = item.find(f"{{{_NS}}}memoryInfo")
        mem_mb = 0
        if mem_info is not None:
            raw = _find(mem_info, "sizeInMiB")
            mem_mb = int(raw) if raw else 0

        return EC2InstanceType(
            instance_type=_find(item, "instanceType"),
            vcpu_count=vcpu_count,
            memory_size_mb=mem_mb,
            current_generation=_find(item, "currentGeneration") == "true",
        )

    @staticmethod
    def _parse_vpc(item: ET.Element) -> EC2Vpc:
        """Parse a VPC XML element into an EC2Vpc model.

        Args:
            item: XML ``<item>`` element from VPC responses.

        Returns:
            EC2Vpc model.
        """
        return EC2Vpc(
            vpc_id=_find(item, "vpcId"),
            cidr_block=_find(item, "cidrBlock"),
            state=_find(item, "state"),
            is_default=_find(item, "isDefault") == "true",
            tags=_parse_tags(item),
        )

    @staticmethod
    def _parse_subnet(item: ET.Element) -> EC2Subnet:
        """Parse a subnet XML element into an EC2Subnet model.

        Args:
            item: XML ``<item>`` element from subnet responses.

        Returns:
            EC2Subnet model.
        """
        avail_raw = _find(item, "availableIpAddressCount")
        return EC2Subnet(
            subnet_id=_find(item, "subnetId"),
            vpc_id=_find(item, "vpcId"),
            cidr_block=_find(item, "cidrBlock"),
            availability_zone=_find(item, "availabilityZone"),
            available_ip_count=int(avail_raw) if avail_raw else 0,
            tags=_parse_tags(item),
        )

    @staticmethod
    def _parse_volume(item: ET.Element) -> EC2Volume:
        """Parse a volume XML element into an EC2Volume model.

        Args:
            item: XML ``<item>`` element from volume responses.

        Returns:
            EC2Volume model.
        """
        size_raw = _find(item, "size")
        iops_raw = _find(item, "iops")
        return EC2Volume(
            volume_id=_find(item, "volumeId"),
            size=int(size_raw) if size_raw else 0,
            state=_find(item, "status"),
            availability_zone=_find(item, "availabilityZone"),
            volume_type=_find(item, "volumeType"),
            iops=int(iops_raw) if iops_raw else 0,
            encrypted=_find(item, "encrypted") == "true",
            tags=_parse_tags(item),
        )

    # ==================================================================
    # Actions -- Instances
    # ==================================================================

    @action("Launch new EC2 instances", dangerous=True)
    async def run_instances(
        self,
        image_id: str,
        instance_type: str = "t3.micro",
        min_count: int = 1,
        max_count: int = 1,
        key_name: str = "",
        security_group_ids: Optional[list[str]] = None,
        subnet_id: str = "",
        user_data: str = "",
    ) -> list[EC2Instance]:
        """Launch one or more EC2 instances.

        Args:
            image_id: AMI image ID to launch.
            instance_type: Instance type (e.g. t3.micro, m5.large).
            min_count: Minimum number of instances to launch.
            max_count: Maximum number of instances to launch.
            key_name: Name of the SSH key pair.
            security_group_ids: Security group IDs to attach.
            subnet_id: Subnet to launch into.
            user_data: Base64-encoded user data script.

        Returns:
            List of launched EC2Instance objects.
        """
        params: dict[str, str] = {
            "ImageId": image_id,
            "InstanceType": instance_type,
            "MinCount": str(min_count),
            "MaxCount": str(max_count),
        }
        if key_name:
            params["KeyName"] = key_name
        if security_group_ids:
            params.update(_encode_list("SecurityGroupId", security_group_ids))
        if subnet_id:
            params["SubnetId"] = subnet_id
        if user_data:
            # Encode to base64 if not already encoded
            try:
                base64.b64decode(user_data, validate=True)
                params["UserData"] = user_data
            except Exception:
                params["UserData"] = base64.b64encode(
                    user_data.encode("utf-8"),
                ).decode("ascii")

        root = await self._ec2_request("RunInstances", params)

        instances: list[EC2Instance] = []
        instances_set = root.find(f"{{{_NS}}}instancesSet")
        if instances_set is not None:
            for item in _findall(instances_set, "item"):
                instances.append(self._parse_instance(item))
        return instances

    @action("Describe EC2 instances")
    async def describe_instances(
        self,
        instance_ids: Optional[list[str]] = None,
        filters: Optional[dict[str, Union[str, list[str]]]] = None,
    ) -> list[EC2Instance]:
        """Describe EC2 instances with optional filtering.

        Args:
            instance_ids: Specific instance IDs to describe.
            filters: Filter criteria (e.g. ``{"instance-state-name": "running"}``).

        Returns:
            List of EC2Instance objects.
        """
        params: dict[str, str] = {}
        if instance_ids:
            params.update(_encode_list("InstanceId", instance_ids))
        if filters:
            params.update(_encode_filters(filters))

        root = await self._ec2_request("DescribeInstances", params)

        instances: list[EC2Instance] = []
        for reservation in root.iter(f"{{{_NS}}}reservationSet"):
            for res_item in _findall(reservation, "item"):
                inst_set = res_item.find(f"{{{_NS}}}instancesSet")
                if inst_set is not None:
                    for inst_item in _findall(inst_set, "item"):
                        instances.append(self._parse_instance(inst_item))
        return instances

    @action("Start stopped EC2 instances")
    async def start_instances(
        self,
        instance_ids: list[str],
    ) -> list[dict[str, Any]]:
        """Start one or more stopped EC2 instances.

        Args:
            instance_ids: Instance IDs to start.

        Returns:
            List of state change dicts with instance_id, previous_state,
            and current_state.
        """
        params = _encode_list("InstanceId", instance_ids)
        root = await self._ec2_request("StartInstances", params)

        results: list[dict[str, Any]] = []
        for item in root.iter(f"{{{_NS}}}item"):
            iid = _find(item, "instanceId")
            if not iid:
                continue
            prev = item.find(f"{{{_NS}}}previousState")
            curr = item.find(f"{{{_NS}}}currentState")
            results.append({
                "instance_id": iid,
                "previous_state": _find(prev, "name") if prev is not None else "",
                "current_state": _find(curr, "name") if curr is not None else "",
            })
        return results

    @action("Stop running EC2 instances")
    async def stop_instances(
        self,
        instance_ids: list[str],
        force: bool = False,
    ) -> list[dict[str, Any]]:
        """Stop one or more running EC2 instances.

        Args:
            instance_ids: Instance IDs to stop.
            force: Force the instances to stop without graceful shutdown.

        Returns:
            List of state change dicts with instance_id, previous_state,
            and current_state.
        """
        params = _encode_list("InstanceId", instance_ids)
        if force:
            params["Force"] = "true"
        root = await self._ec2_request("StopInstances", params)

        results: list[dict[str, Any]] = []
        for item in root.iter(f"{{{_NS}}}item"):
            iid = _find(item, "instanceId")
            if not iid:
                continue
            prev = item.find(f"{{{_NS}}}previousState")
            curr = item.find(f"{{{_NS}}}currentState")
            results.append({
                "instance_id": iid,
                "previous_state": _find(prev, "name") if prev is not None else "",
                "current_state": _find(curr, "name") if curr is not None else "",
            })
        return results

    @action("Terminate EC2 instances", dangerous=True)
    async def terminate_instances(
        self,
        instance_ids: list[str],
    ) -> list[dict[str, Any]]:
        """Terminate one or more EC2 instances.

        Terminated instances cannot be restarted. All associated EBS
        volumes with ``DeleteOnTermination`` enabled will be deleted.

        Args:
            instance_ids: Instance IDs to terminate.

        Returns:
            List of state change dicts with instance_id, previous_state,
            and current_state.
        """
        params = _encode_list("InstanceId", instance_ids)
        root = await self._ec2_request("TerminateInstances", params)

        results: list[dict[str, Any]] = []
        for item in root.iter(f"{{{_NS}}}item"):
            iid = _find(item, "instanceId")
            if not iid:
                continue
            prev = item.find(f"{{{_NS}}}previousState")
            curr = item.find(f"{{{_NS}}}currentState")
            results.append({
                "instance_id": iid,
                "previous_state": _find(prev, "name") if prev is not None else "",
                "current_state": _find(curr, "name") if curr is not None else "",
            })
        return results

    @action("Reboot EC2 instances")
    async def reboot_instances(
        self,
        instance_ids: list[str],
    ) -> dict[str, Any]:
        """Reboot one or more EC2 instances.

        Args:
            instance_ids: Instance IDs to reboot.

        Returns:
            Dict confirming the reboot request was accepted.
        """
        params = _encode_list("InstanceId", instance_ids)
        await self._ec2_request("RebootInstances", params)
        return {"status": "ok", "instance_ids": instance_ids}

    # ==================================================================
    # Actions -- Key Pairs
    # ==================================================================

    @action("Create a key pair")
    async def create_key_pair(self, key_name: str) -> EC2KeyPair:
        """Create a new EC2 key pair for SSH access.

        The private key material is only available in this response and
        cannot be retrieved again.

        Args:
            key_name: Name for the key pair.

        Returns:
            EC2KeyPair with the private key material.
        """
        root = await self._ec2_request("CreateKeyPair", {"KeyName": key_name})
        return EC2KeyPair(
            key_name=_find(root, "keyName"),
            key_pair_id=_find(root, "keyPairId"),
            key_fingerprint=_find(root, "keyFingerprint"),
            key_material=_find(root, "keyMaterial") or None,
        )

    @action("Describe key pairs")
    async def describe_key_pairs(self) -> list[EC2KeyPair]:
        """List all EC2 key pairs in the account.

        Returns:
            List of EC2KeyPair objects (without private key material).
        """
        root = await self._ec2_request("DescribeKeyPairs")

        key_pairs: list[EC2KeyPair] = []
        kp_set = root.find(f"{{{_NS}}}keySet")
        if kp_set is not None:
            for item in _findall(kp_set, "item"):
                key_pairs.append(self._parse_key_pair(item))
        return key_pairs

    @action("Delete a key pair", dangerous=True)
    async def delete_key_pair(self, key_name: str) -> dict[str, Any]:
        """Delete an EC2 key pair.

        Args:
            key_name: Name of the key pair to delete.

        Returns:
            Dict confirming deletion.
        """
        await self._ec2_request("DeleteKeyPair", {"KeyName": key_name})
        return {"status": "ok", "key_name": key_name}

    # ==================================================================
    # Actions -- Elastic IPs
    # ==================================================================

    @action("Allocate an Elastic IP address")
    async def allocate_address(self, domain: str = "vpc") -> EC2Address:
        """Allocate a new Elastic IP address.

        Args:
            domain: Scope for the address -- ``vpc`` (default) or ``standard``.

        Returns:
            EC2Address for the newly allocated IP.
        """
        root = await self._ec2_request(
            "AllocateAddress", {"Domain": domain},
        )
        return EC2Address(
            allocation_id=_find(root, "allocationId"),
            public_ip=_find(root, "publicIp"),
            domain=_find(root, "domain"),
        )

    @action("Associate an Elastic IP with an instance")
    async def associate_address(
        self,
        allocation_id: str,
        instance_id: str,
    ) -> dict[str, Any]:
        """Associate an Elastic IP address with an EC2 instance.

        Args:
            allocation_id: Allocation ID of the Elastic IP.
            instance_id: Instance ID to associate with.

        Returns:
            Dict with the association ID.
        """
        root = await self._ec2_request("AssociateAddress", {
            "AllocationId": allocation_id,
            "InstanceId": instance_id,
        })
        return {
            "association_id": _find(root, "associationId"),
            "status": "ok",
        }

    @action("Release an Elastic IP address", dangerous=True)
    async def release_address(self, allocation_id: str) -> dict[str, Any]:
        """Release an Elastic IP address back to the pool.

        Args:
            allocation_id: Allocation ID of the address to release.

        Returns:
            Dict confirming release.
        """
        await self._ec2_request(
            "ReleaseAddress", {"AllocationId": allocation_id},
        )
        return {"status": "ok", "allocation_id": allocation_id}

    @action("Describe Elastic IP addresses")
    async def describe_addresses(
        self,
        allocation_ids: Optional[list[str]] = None,
    ) -> list[EC2Address]:
        """Describe Elastic IP addresses.

        Args:
            allocation_ids: Specific allocation IDs to describe.

        Returns:
            List of EC2Address objects.
        """
        params: dict[str, str] = {}
        if allocation_ids:
            params.update(_encode_list("AllocationId", allocation_ids))

        root = await self._ec2_request("DescribeAddresses", params)

        addresses: list[EC2Address] = []
        addr_set = root.find(f"{{{_NS}}}addressesSet")
        if addr_set is not None:
            for item in _findall(addr_set, "item"):
                addresses.append(self._parse_address(item))
        return addresses

    # ==================================================================
    # Actions -- Security Groups
    # ==================================================================

    @action("Create a security group")
    async def create_security_group(
        self,
        group_name: str,
        description: str,
        vpc_id: str = "",
    ) -> EC2SecurityGroup:
        """Create a new VPC security group.

        Args:
            group_name: Name for the security group.
            description: Description of the security group.
            vpc_id: VPC in which to create the group.

        Returns:
            EC2SecurityGroup for the newly created group.
        """
        params: dict[str, str] = {
            "GroupName": group_name,
            "GroupDescription": description,
        }
        if vpc_id:
            params["VpcId"] = vpc_id

        root = await self._ec2_request("CreateSecurityGroup", params)
        group_id = _find(root, "groupId")

        return EC2SecurityGroup(
            group_id=group_id,
            group_name=group_name,
            description=description,
            vpc_id=vpc_id,
        )

    @action("Describe security groups")
    async def describe_security_groups(
        self,
        group_ids: Optional[list[str]] = None,
    ) -> list[EC2SecurityGroup]:
        """Describe security groups.

        Args:
            group_ids: Specific security group IDs to describe.

        Returns:
            List of EC2SecurityGroup objects.
        """
        params: dict[str, str] = {}
        if group_ids:
            params.update(_encode_list("GroupId", group_ids))

        root = await self._ec2_request("DescribeSecurityGroups", params)

        groups: list[EC2SecurityGroup] = []
        sg_set = root.find(f"{{{_NS}}}securityGroupInfo")
        if sg_set is not None:
            for item in _findall(sg_set, "item"):
                groups.append(self._parse_security_group(item))
        return groups

    @action("Add an inbound rule to a security group")
    async def authorize_security_group_ingress(
        self,
        group_id: str,
        ip_protocol: str,
        from_port: int,
        to_port: int,
        cidr_ip: str = "0.0.0.0/0",
    ) -> dict[str, Any]:
        """Add an inbound (ingress) rule to a security group.

        Args:
            group_id: Security group ID.
            ip_protocol: IP protocol (tcp, udp, icmp, or -1 for all).
            from_port: Start of port range.
            to_port: End of port range.
            cidr_ip: CIDR IP range to allow.

        Returns:
            Dict confirming the rule was added.
        """
        params: dict[str, str] = {
            "GroupId": group_id,
            "IpPermissions.1.IpProtocol": ip_protocol,
            "IpPermissions.1.FromPort": str(from_port),
            "IpPermissions.1.ToPort": str(to_port),
            "IpPermissions.1.IpRanges.1.CidrIp": cidr_ip,
        }
        await self._ec2_request("AuthorizeSecurityGroupIngress", params)
        return {"status": "ok", "group_id": group_id, "direction": "ingress"}

    @action("Add an outbound rule to a security group")
    async def authorize_security_group_egress(
        self,
        group_id: str,
        ip_protocol: str,
        from_port: int,
        to_port: int,
        cidr_ip: str = "0.0.0.0/0",
    ) -> dict[str, Any]:
        """Add an outbound (egress) rule to a security group.

        Args:
            group_id: Security group ID.
            ip_protocol: IP protocol (tcp, udp, icmp, or -1 for all).
            from_port: Start of port range.
            to_port: End of port range.
            cidr_ip: CIDR IP range to allow.

        Returns:
            Dict confirming the rule was added.
        """
        params: dict[str, str] = {
            "GroupId": group_id,
            "IpPermissions.1.IpProtocol": ip_protocol,
            "IpPermissions.1.FromPort": str(from_port),
            "IpPermissions.1.ToPort": str(to_port),
            "IpPermissions.1.IpRanges.1.CidrIp": cidr_ip,
        }
        await self._ec2_request("AuthorizeSecurityGroupEgress", params)
        return {"status": "ok", "group_id": group_id, "direction": "egress"}

    @action("Remove an inbound rule from a security group")
    async def revoke_security_group_ingress(
        self,
        group_id: str,
        ip_protocol: str,
        from_port: int,
        to_port: int,
        cidr_ip: str = "0.0.0.0/0",
    ) -> dict[str, Any]:
        """Remove an inbound (ingress) rule from a security group.

        Args:
            group_id: Security group ID.
            ip_protocol: IP protocol of the rule to remove.
            from_port: Start of port range.
            to_port: End of port range.
            cidr_ip: CIDR IP range of the rule.

        Returns:
            Dict confirming the rule was removed.
        """
        params: dict[str, str] = {
            "GroupId": group_id,
            "IpPermissions.1.IpProtocol": ip_protocol,
            "IpPermissions.1.FromPort": str(from_port),
            "IpPermissions.1.ToPort": str(to_port),
            "IpPermissions.1.IpRanges.1.CidrIp": cidr_ip,
        }
        await self._ec2_request("RevokeSecurityGroupIngress", params)
        return {"status": "ok", "group_id": group_id, "direction": "ingress"}

    @action("Remove an outbound rule from a security group")
    async def revoke_security_group_egress(
        self,
        group_id: str,
        ip_protocol: str,
        from_port: int,
        to_port: int,
        cidr_ip: str = "0.0.0.0/0",
    ) -> dict[str, Any]:
        """Remove an outbound (egress) rule from a security group.

        Args:
            group_id: Security group ID.
            ip_protocol: IP protocol of the rule to remove.
            from_port: Start of port range.
            to_port: End of port range.
            cidr_ip: CIDR IP range of the rule.

        Returns:
            Dict confirming the rule was removed.
        """
        params: dict[str, str] = {
            "GroupId": group_id,
            "IpPermissions.1.IpProtocol": ip_protocol,
            "IpPermissions.1.FromPort": str(from_port),
            "IpPermissions.1.ToPort": str(to_port),
            "IpPermissions.1.IpRanges.1.CidrIp": cidr_ip,
        }
        await self._ec2_request("RevokeSecurityGroupEgress", params)
        return {"status": "ok", "group_id": group_id, "direction": "egress"}

    @action("Delete a security group", dangerous=True)
    async def delete_security_group(
        self,
        group_id: str,
    ) -> dict[str, Any]:
        """Delete a security group.

        The group must not be referenced by any instances or other
        security groups.

        Args:
            group_id: Security group ID to delete.

        Returns:
            Dict confirming deletion.
        """
        await self._ec2_request(
            "DeleteSecurityGroup", {"GroupId": group_id},
        )
        return {"status": "ok", "group_id": group_id}

    # ==================================================================
    # Actions -- Images & Instance Types
    # ==================================================================

    @action("Describe AMI images")
    async def describe_images(
        self,
        image_ids: Optional[list[str]] = None,
        owners: Optional[list[str]] = None,
        filters: Optional[dict[str, Union[str, list[str]]]] = None,
    ) -> list[EC2Image]:
        """Describe Amazon Machine Images (AMIs).

        Args:
            image_ids: Specific image IDs to describe.
            owners: Filter by owner (e.g. ``["self"]``, ``["amazon"]``).
            filters: Additional filter criteria.

        Returns:
            List of EC2Image objects.
        """
        params: dict[str, str] = {}
        if image_ids:
            params.update(_encode_list("ImageId", image_ids))
        if owners:
            params.update(_encode_list("Owner", owners))
        if filters:
            params.update(_encode_filters(filters))

        root = await self._ec2_request("DescribeImages", params)

        images: list[EC2Image] = []
        img_set = root.find(f"{{{_NS}}}imagesSet")
        if img_set is not None:
            for item in _findall(img_set, "item"):
                images.append(self._parse_image(item))
        return images

    @action("Describe available instance types")
    async def describe_instance_types(
        self,
        instance_types: Optional[list[str]] = None,
    ) -> list[EC2InstanceType]:
        """Describe available EC2 instance types and their specifications.

        Args:
            instance_types: Specific instance types to describe
                (e.g. ``["t3.micro", "m5.large"]``).

        Returns:
            List of EC2InstanceType objects.
        """
        params: dict[str, str] = {}
        if instance_types:
            params.update(_encode_list("InstanceType", instance_types))

        root = await self._ec2_request("DescribeInstanceTypes", params)

        types: list[EC2InstanceType] = []
        type_set = root.find(f"{{{_NS}}}instanceTypeSet")
        if type_set is not None:
            for item in _findall(type_set, "item"):
                types.append(self._parse_instance_type(item))
        return types

    @action("Describe availability zones")
    async def describe_availability_zones(self) -> list[dict[str, Any]]:
        """Describe availability zones in the current region.

        Returns:
            List of dicts with zone_name, zone_id, state, and region_name.
        """
        root = await self._ec2_request("DescribeAvailabilityZones")

        zones: list[dict[str, Any]] = []
        zone_set = root.find(f"{{{_NS}}}availabilityZoneInfo")
        if zone_set is not None:
            for item in _findall(zone_set, "item"):
                zones.append({
                    "zone_name": _find(item, "zoneName"),
                    "zone_id": _find(item, "zoneId"),
                    "state": _find(item, "zoneState"),
                    "region_name": _find(item, "regionName"),
                })
        return zones

    # ==================================================================
    # Actions -- Tags
    # ==================================================================

    @action("Create or update tags on EC2 resources")
    async def create_tags(
        self,
        resource_ids: list[str],
        tags: dict[str, str],
    ) -> dict[str, Any]:
        """Create or update tags on one or more EC2 resources.

        Args:
            resource_ids: Resource IDs to tag (instances, volumes, etc.).
            tags: Dict of tag key-value pairs.

        Returns:
            Dict confirming the tags were created.
        """
        params: dict[str, str] = {}
        params.update(_encode_list("ResourceId", resource_ids))
        for idx, (key, val) in enumerate(tags.items(), 1):
            params[f"Tag.{idx}.Key"] = key
            params[f"Tag.{idx}.Value"] = val

        await self._ec2_request("CreateTags", params)
        return {"status": "ok", "resource_ids": resource_ids}

    @action("Describe tags")
    async def describe_tags(
        self,
        filters: Optional[dict[str, Union[str, list[str]]]] = None,
    ) -> list[dict[str, Any]]:
        """Describe tags on EC2 resources with optional filtering.

        Args:
            filters: Filter criteria (e.g. ``{"resource-type": "instance"}``).

        Returns:
            List of tag dicts with resource_id, resource_type, key, and value.
        """
        params: dict[str, str] = {}
        if filters:
            params.update(_encode_filters(filters))

        root = await self._ec2_request("DescribeTags", params)

        tag_list: list[dict[str, Any]] = []
        tag_set = root.find(f"{{{_NS}}}tagSet")
        if tag_set is not None:
            for item in _findall(tag_set, "item"):
                tag_list.append({
                    "resource_id": _find(item, "resourceId"),
                    "resource_type": _find(item, "resourceType"),
                    "key": _find(item, "key"),
                    "value": _find(item, "value"),
                })
        return tag_list

    # ==================================================================
    # Actions -- VPC / Subnets (read-only)
    # ==================================================================

    @action("Describe VPCs")
    async def describe_vpcs(
        self,
        vpc_ids: Optional[list[str]] = None,
    ) -> list[EC2Vpc]:
        """Describe Virtual Private Clouds.

        Args:
            vpc_ids: Specific VPC IDs to describe.

        Returns:
            List of EC2Vpc objects.
        """
        params: dict[str, str] = {}
        if vpc_ids:
            params.update(_encode_list("VpcId", vpc_ids))

        root = await self._ec2_request("DescribeVpcs", params)

        vpcs: list[EC2Vpc] = []
        vpc_set = root.find(f"{{{_NS}}}vpcSet")
        if vpc_set is not None:
            for item in _findall(vpc_set, "item"):
                vpcs.append(self._parse_vpc(item))
        return vpcs

    @action("Describe subnets")
    async def describe_subnets(
        self,
        subnet_ids: Optional[list[str]] = None,
        filters: Optional[dict[str, Union[str, list[str]]]] = None,
    ) -> list[EC2Subnet]:
        """Describe VPC subnets.

        Args:
            subnet_ids: Specific subnet IDs to describe.
            filters: Additional filter criteria.

        Returns:
            List of EC2Subnet objects.
        """
        params: dict[str, str] = {}
        if subnet_ids:
            params.update(_encode_list("SubnetId", subnet_ids))
        if filters:
            params.update(_encode_filters(filters))

        root = await self._ec2_request("DescribeSubnets", params)

        subnets: list[EC2Subnet] = []
        subnet_set = root.find(f"{{{_NS}}}subnetSet")
        if subnet_set is not None:
            for item in _findall(subnet_set, "item"):
                subnets.append(self._parse_subnet(item))
        return subnets

    # ==================================================================
    # Actions -- Volumes
    # ==================================================================

    @action("Describe EBS volumes")
    async def describe_volumes(
        self,
        volume_ids: Optional[list[str]] = None,
    ) -> list[EC2Volume]:
        """Describe EBS volumes.

        Args:
            volume_ids: Specific volume IDs to describe.

        Returns:
            List of EC2Volume objects.
        """
        params: dict[str, str] = {}
        if volume_ids:
            params.update(_encode_list("VolumeId", volume_ids))

        root = await self._ec2_request("DescribeVolumes", params)

        volumes: list[EC2Volume] = []
        vol_set = root.find(f"{{{_NS}}}volumeSet")
        if vol_set is not None:
            for item in _findall(vol_set, "item"):
                volumes.append(self._parse_volume(item))
        return volumes

    @action("Create an EBS volume")
    async def create_volume(
        self,
        availability_zone: str,
        size: int = 20,
        volume_type: str = "gp3",
        encrypted: bool = True,
    ) -> EC2Volume:
        """Create a new EBS volume.

        Args:
            availability_zone: AZ for the volume (e.g. us-east-1a).
            size: Volume size in GiB.
            volume_type: Volume type (gp3, gp2, io1, io2, st1, sc1, standard).
            encrypted: Whether to encrypt the volume.

        Returns:
            EC2Volume for the newly created volume.
        """
        params: dict[str, str] = {
            "AvailabilityZone": availability_zone,
            "Size": str(size),
            "VolumeType": volume_type,
            "Encrypted": "true" if encrypted else "false",
        }
        root = await self._ec2_request("CreateVolume", params)

        iops_raw = _find(root, "iops")
        size_raw = _find(root, "size")
        return EC2Volume(
            volume_id=_find(root, "volumeId"),
            size=int(size_raw) if size_raw else size,
            state=_find(root, "status"),
            availability_zone=_find(root, "availabilityZone"),
            volume_type=_find(root, "volumeType"),
            iops=int(iops_raw) if iops_raw else 0,
            encrypted=_find(root, "encrypted") == "true",
        )

    # ==================================================================
    # Actions -- Console
    # ==================================================================

    @action("Get instance console output")
    async def get_console_output(
        self,
        instance_id: str,
    ) -> dict[str, Any]:
        """Get the console output for an EC2 instance.

        Useful for debugging boot issues. Output is base64-decoded
        automatically.

        Args:
            instance_id: Instance ID to get console output for.

        Returns:
            Dict with instance_id, timestamp, and decoded output text.
        """
        root = await self._ec2_request(
            "GetConsoleOutput", {"InstanceId": instance_id},
        )

        output_b64 = _find(root, "output")
        output_text = ""
        if output_b64:
            try:
                output_text = base64.b64decode(output_b64).decode(
                    "utf-8", errors="replace",
                )
            except Exception:
                output_text = output_b64

        return {
            "instance_id": _find(root, "instanceId"),
            "timestamp": _find(root, "timestamp"),
            "output": output_text,
        }
