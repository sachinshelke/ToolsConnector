"""AWS RDS connector -- create and manage relational databases.

Uses the RDS Query API with ``Action`` and ``Version`` parameters in
form-encoded POST bodies. Credentials should be a JSON string or dict
containing ``access_key_id``, ``secret_access_key``, and optionally
``region`` (defaults to ``us-east-1``).

RDS responses are XML-formatted with the namespace
``http://rds.amazonaws.com/doc/2014-10-31/``.

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
    RDSCluster,
    RDSEvent,
    RDSInstance,
    RDSSnapshot,
    RDSSubnetGroup,
)

logger = logging.getLogger("toolsconnector.rds")

# RDS XML namespace for API version 2014-10-31.
_NS = "http://rds.amazonaws.com/doc/2014-10-31/"

# API version for the RDS Query API.
_API_VERSION = "2014-10-31"


# ------------------------------------------------------------------
# XML namespace helpers
# ------------------------------------------------------------------


def _find(elem: ET.Element, tag: str) -> str:
    """Find a direct child element's text by tag name within the RDS namespace.

    Args:
        elem: Parent XML element.
        tag: Tag name without namespace prefix.

    Returns:
        Element text or empty string if not found.
    """
    return elem.findtext(f"{{{_NS}}}{tag}", default="")


def _findall(elem: ET.Element, tag: str) -> list[ET.Element]:
    """Find all child elements by tag name within the RDS namespace.

    Args:
        elem: Parent XML element.
        tag: Tag name without namespace prefix.

    Returns:
        List of matching elements.
    """
    return elem.findall(f"{{{_NS}}}{tag}")


def _get_result(root: ET.Element, action_name: str) -> ET.Element:
    """Navigate to the result element inside the RDS response wrapper.

    RDS wraps results in ``<{Action}Response><{Action}Result>...``.

    Args:
        root: Root XML element (the ``<{Action}Response>`` element).
        action_name: The API action name (e.g. ``DescribeDBInstances``).

    Returns:
        The ``<{Action}Result>`` element, or the root as fallback.
    """
    result = root.find(f"{{{_NS}}}{action_name}Result")
    if result is None:
        result = root  # fallback
    return result


# ------------------------------------------------------------------
# Tag parsing helper
# ------------------------------------------------------------------


def _parse_tag_list(elem: ET.Element) -> dict[str, str]:
    """Extract tags from an RDS XML element's Tag list.

    Args:
        elem: XML element containing ``<TagList><Tag>`` children.

    Returns:
        Dict mapping tag keys to values.
    """
    tags: dict[str, str] = {}
    tag_list = elem.find(f"{{{_NS}}}TagList")
    if tag_list is not None:
        for tag_item in _findall(tag_list, "Tag"):
            key = _find(tag_item, "Key")
            val = _find(tag_item, "Value")
            if key:
                tags[key] = val
    return tags


class RDS(BaseConnector):
    """Connect to AWS RDS to create and manage relational databases.

    Authenticates using AWS Signature Version 4. Credentials should be
    provided as a JSON string or dict::

        {
            "access_key_id": "AKIA...",
            "secret_access_key": "...",
            "region": "us-east-1"
        }

    Uses the RDS Query API (``Action=X&Version=2014-10-31``) with
    form-encoded POST requests.

    .. note::

        SigV4 signing is simplified. For production, use ``boto3``.
    """

    name = "rds"
    display_name = "AWS RDS"
    category = ConnectorCategory.DATABASE
    protocol = ProtocolType.REST
    base_url = "https://rds.us-east-1.amazonaws.com"
    description = (
        "Create and manage relational databases -- PostgreSQL, MySQL, "
        "Aurora, and more."
    )
    _rate_limit_config = RateLimitSpec(rate=25, period=1, burst=50)

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
        self._host = f"rds.{self._region}.amazonaws.com"
        self._endpoint = f"https://{self._host}"

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
        """Encode a list into RDS ``.member.N`` query parameters.

        Args:
            prefix: Parameter prefix (e.g. ``SubnetIds``).
            items: List of string values.

        Returns:
            Dict of encoded parameters.
        """
        params: dict[str, str] = {}
        for i, item in enumerate(items, 1):
            params[f"{prefix}.member.{i}"] = item
        return params

    @staticmethod
    def _encode_tags(tags: dict[str, str]) -> dict[str, str]:
        """Encode a tag dict into RDS ``Tags.member.N.Key/Value`` parameters.

        Args:
            tags: Dict of tag key-value pairs.

        Returns:
            Dict of encoded tag parameters.
        """
        params: dict[str, str] = {}
        for i, (key, value) in enumerate(tags.items(), 1):
            params[f"Tags.member.{i}.Key"] = key
            params[f"Tags.member.{i}.Value"] = value
        return params

    async def _rds_request(
        self,
        rds_action: str,
        params: dict[str, str] | None = None,
    ) -> ET.Element:
        """Send a Query API request to RDS.

        Args:
            rds_action: RDS API action name (e.g. ``DescribeDBInstances``).
            params: Additional form parameters for the request.

        Returns:
            Parsed XML root element of the response.

        Raises:
            NotFoundError: If the resource is not found.
            APIError: For any RDS API error.
        """
        form_params: dict[str, str] = {
            "Action": rds_action,
            "Version": _API_VERSION,
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
            "rds",
            session_token=self._session_token,
        )

        resp = await self._client.post(
            self._endpoint + "/",
            content=body,
            headers=headers,
        )

        if resp.status_code >= 400:
            error_msg = f"RDS {rds_action} error"
            error_code = ""
            try:
                err_root = ET.fromstring(resp.text)
                # Try with namespace first.
                err_el = err_root.find(f".//{{{_NS}}}Message")
                code_el = err_root.find(f".//{{{_NS}}}Code")
                if err_el is None:
                    # Try without namespace for generic AWS error format.
                    err_el = err_root.find(".//Message")
                    code_el = err_root.find(".//Code")
                if err_el is not None and err_el.text:
                    error_msg = err_el.text
                if code_el is not None and code_el.text:
                    error_code = code_el.text
            except ET.ParseError:
                error_msg = resp.text[:500]

            full_msg = f"RDS {rds_action}: {error_code} - {error_msg}"

            if "NotFound" in error_code or "DBInstanceNotFound" in error_code:
                raise NotFoundError(
                    full_msg,
                    connector="rds",
                    action=rds_action,
                    details={"code": error_code, "message": error_msg},
                )
            raise APIError(
                full_msg,
                connector="rds",
                action=rds_action,
                upstream_status=resp.status_code,
                details={"code": error_code, "message": error_msg},
            )

        return ET.fromstring(resp.text)

    # ------------------------------------------------------------------
    # Model parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_instance(item: ET.Element) -> RDSInstance:
        """Parse an RDS DBInstance XML element into an RDSInstance model.

        Args:
            item: XML ``<DBInstance>`` element.

        Returns:
            RDSInstance model.
        """
        # VPC security groups
        vsgs: list[dict[str, Any]] = []
        vsg_list = item.find(f"{{{_NS}}}VpcSecurityGroups")
        if vsg_list is not None:
            for vsg in _findall(vsg_list, "VpcSecurityGroupMembership"):
                vsgs.append({
                    "VpcSecurityGroupId": _find(vsg, "VpcSecurityGroupId"),
                    "Status": _find(vsg, "Status"),
                })

        # Endpoint
        endpoint_el = item.find(f"{{{_NS}}}Endpoint")
        endpoint_address = ""
        endpoint_port = 0
        if endpoint_el is not None:
            endpoint_address = _find(endpoint_el, "Address")
            port_text = _find(endpoint_el, "Port")
            if port_text:
                endpoint_port = int(port_text)

        # DB subnet group name
        subnet_group_name = ""
        subnet_group_el = item.find(f"{{{_NS}}}DBSubnetGroup")
        if subnet_group_el is not None:
            subnet_group_name = _find(subnet_group_el, "DBSubnetGroupName")

        # Allocated storage
        alloc_text = _find(item, "AllocatedStorage")
        allocated_storage = int(alloc_text) if alloc_text else 0

        return RDSInstance(
            db_instance_identifier=_find(item, "DBInstanceIdentifier"),
            db_instance_class=_find(item, "DBInstanceClass"),
            engine=_find(item, "Engine"),
            engine_version=_find(item, "EngineVersion"),
            db_instance_status=_find(item, "DBInstanceStatus"),
            master_username=_find(item, "MasterUsername"),
            endpoint_address=endpoint_address,
            endpoint_port=endpoint_port,
            allocated_storage=allocated_storage,
            instance_create_time=_find(item, "InstanceCreateTime") or None,
            availability_zone=_find(item, "AvailabilityZone"),
            multi_az=_find(item, "MultiAZ").lower() == "true",
            publicly_accessible=_find(item, "PubliclyAccessible").lower() == "true",
            storage_type=_find(item, "StorageType"),
            db_instance_arn=_find(item, "DBInstanceArn"),
            vpc_security_groups=vsgs,
            db_subnet_group_name=subnet_group_name,
            tags=_parse_tag_list(item),
        )

    @staticmethod
    def _parse_snapshot(item: ET.Element) -> RDSSnapshot:
        """Parse an RDS DBSnapshot XML element into an RDSSnapshot model.

        Args:
            item: XML ``<DBSnapshot>`` element.

        Returns:
            RDSSnapshot model.
        """
        alloc_text = _find(item, "AllocatedStorage")
        allocated_storage = int(alloc_text) if alloc_text else 0

        return RDSSnapshot(
            db_snapshot_identifier=_find(item, "DBSnapshotIdentifier"),
            db_instance_identifier=_find(item, "DBInstanceIdentifier"),
            snapshot_create_time=_find(item, "SnapshotCreateTime") or None,
            engine=_find(item, "Engine"),
            allocated_storage=allocated_storage,
            status=_find(item, "Status"),
            availability_zone=_find(item, "AvailabilityZone"),
            snapshot_type=_find(item, "SnapshotType"),
            encrypted=_find(item, "Encrypted").lower() == "true",
            db_snapshot_arn=_find(item, "DBSnapshotArn"),
        )

    @staticmethod
    def _parse_cluster(item: ET.Element) -> RDSCluster:
        """Parse an RDS DBCluster XML element into an RDSCluster model.

        Args:
            item: XML ``<DBCluster>`` element.

        Returns:
            RDSCluster model.
        """
        # Cluster members
        members: list[dict[str, Any]] = []
        members_el = item.find(f"{{{_NS}}}DBClusterMembers")
        if members_el is not None:
            for m in _findall(members_el, "DBClusterMember"):
                members.append({
                    "DBInstanceIdentifier": _find(m, "DBInstanceIdentifier"),
                    "IsClusterWriter": _find(m, "IsClusterWriter").lower() == "true",
                    "DBClusterParameterGroupStatus": _find(
                        m, "DBClusterParameterGroupStatus"
                    ),
                })

        port_text = _find(item, "Port")
        port = int(port_text) if port_text else 0

        return RDSCluster(
            db_cluster_identifier=_find(item, "DBClusterIdentifier"),
            db_cluster_arn=_find(item, "DBClusterArn"),
            status=_find(item, "Status"),
            engine=_find(item, "Engine"),
            engine_version=_find(item, "EngineVersion"),
            endpoint=_find(item, "Endpoint"),
            reader_endpoint=_find(item, "ReaderEndpoint"),
            port=port,
            master_username=_find(item, "MasterUsername"),
            database_name=_find(item, "DatabaseName"),
            multi_az=_find(item, "MultiAZ").lower() == "true",
            db_cluster_members=members,
        )

    @staticmethod
    def _parse_subnet_group(item: ET.Element) -> RDSSubnetGroup:
        """Parse an RDS DBSubnetGroup XML element into an RDSSubnetGroup model.

        Args:
            item: XML ``<DBSubnetGroup>`` element.

        Returns:
            RDSSubnetGroup model.
        """
        subnets: list[dict[str, Any]] = []
        subnets_el = item.find(f"{{{_NS}}}Subnets")
        if subnets_el is not None:
            for s in _findall(subnets_el, "Subnet"):
                subnet: dict[str, Any] = {
                    "SubnetIdentifier": _find(s, "SubnetIdentifier"),
                    "SubnetStatus": _find(s, "SubnetStatus"),
                }
                az_el = s.find(f"{{{_NS}}}SubnetAvailabilityZone")
                if az_el is not None:
                    subnet["AvailabilityZone"] = _find(az_el, "Name")
                subnets.append(subnet)

        return RDSSubnetGroup(
            db_subnet_group_name=_find(item, "DBSubnetGroupName"),
            db_subnet_group_description=_find(item, "DBSubnetGroupDescription"),
            vpc_id=_find(item, "VpcId"),
            subnet_group_status=_find(item, "SubnetGroupStatus"),
            subnets=subnets,
        )

    @staticmethod
    def _parse_event(item: ET.Element) -> RDSEvent:
        """Parse an RDS Event XML element into an RDSEvent model.

        Args:
            item: XML ``<Event>`` element.

        Returns:
            RDSEvent model.
        """
        return RDSEvent(
            source_identifier=_find(item, "SourceIdentifier"),
            source_type=_find(item, "SourceType"),
            message=_find(item, "Message"),
            date=_find(item, "Date") or None,
            source_arn=_find(item, "SourceArn"),
        )

    # ==================================================================
    # Actions -- Instances
    # ==================================================================

    @action("Create a database instance", dangerous=True)
    async def create_db_instance(
        self,
        db_instance_identifier: str,
        db_instance_class: str = "db.t3.micro",
        engine: str = "postgres",
        master_username: str = "admin",
        master_user_password: str = "",
        allocated_storage: int = 20,
        storage_type: str = "gp3",
        publicly_accessible: bool = False,
        availability_zone: str = "",
        db_name: str = "",
        vpc_security_group_ids: list[str] | None = None,
        db_subnet_group_name: str = "",
    ) -> RDSInstance:
        """Create a new RDS database instance.

        Args:
            db_instance_identifier: Unique identifier for the DB instance.
            db_instance_class: Compute and memory capacity class.
            engine: Database engine (postgres, mysql, mariadb, oracle-ee, etc.).
            master_username: Master user name for the DB instance.
            master_user_password: Password for the master user.
            allocated_storage: Storage size in GiB.
            storage_type: Storage type (gp2, gp3, io1, standard).
            publicly_accessible: Whether the instance is publicly accessible.
            availability_zone: Preferred availability zone.
            db_name: Name of the initial database to create.
            vpc_security_group_ids: List of VPC security group IDs.
            db_subnet_group_name: DB subnet group name.

        Returns:
            The created RDSInstance.
        """
        params: dict[str, str] = {
            "DBInstanceIdentifier": db_instance_identifier,
            "DBInstanceClass": db_instance_class,
            "Engine": engine,
            "MasterUsername": master_username,
            "AllocatedStorage": str(allocated_storage),
            "StorageType": storage_type,
            "PubliclyAccessible": str(publicly_accessible).lower(),
        }
        if master_user_password:
            params["MasterUserPassword"] = master_user_password
        if availability_zone:
            params["AvailabilityZone"] = availability_zone
        if db_name:
            params["DBName"] = db_name
        if vpc_security_group_ids:
            params.update(
                self._encode_members(
                    "VpcSecurityGroupIds", vpc_security_group_ids
                )
            )
        if db_subnet_group_name:
            params["DBSubnetGroupName"] = db_subnet_group_name

        root = await self._rds_request("CreateDBInstance", params)
        result = _get_result(root, "CreateDBInstance")
        db_el = result.find(f"{{{_NS}}}DBInstance")
        if db_el is None:
            raise APIError(
                "CreateDBInstance returned no DBInstance",
                connector="rds",
                action="CreateDBInstance",
            )
        return self._parse_instance(db_el)

    @action("Describe database instances")
    async def describe_db_instances(
        self,
        db_instance_identifier: str = "",
    ) -> list[RDSInstance]:
        """Describe one or all RDS database instances.

        Args:
            db_instance_identifier: Optional identifier to describe a
                specific instance. If empty, describes all instances.

        Returns:
            List of RDSInstance objects.
        """
        params: dict[str, str] = {}
        if db_instance_identifier:
            params["DBInstanceIdentifier"] = db_instance_identifier

        root = await self._rds_request("DescribeDBInstances", params)
        result = _get_result(root, "DescribeDBInstances")
        instances_el = result.find(f"{{{_NS}}}DBInstances")
        if instances_el is None:
            return []
        return [
            self._parse_instance(el)
            for el in _findall(instances_el, "DBInstance")
        ]

    @action("Delete a database instance", dangerous=True)
    async def delete_db_instance(
        self,
        db_instance_identifier: str,
        skip_final_snapshot: bool = False,
        final_snapshot_identifier: str = "",
    ) -> RDSInstance:
        """Delete an RDS database instance.

        Args:
            db_instance_identifier: Identifier of the instance to delete.
            skip_final_snapshot: Whether to skip creating a final snapshot.
            final_snapshot_identifier: Identifier for the final snapshot
                (required if skip_final_snapshot is False).

        Returns:
            The deleted RDSInstance.
        """
        params: dict[str, str] = {
            "DBInstanceIdentifier": db_instance_identifier,
            "SkipFinalSnapshot": str(skip_final_snapshot).lower(),
        }
        if final_snapshot_identifier:
            params["FinalDBSnapshotIdentifier"] = final_snapshot_identifier

        root = await self._rds_request("DeleteDBInstance", params)
        result = _get_result(root, "DeleteDBInstance")
        db_el = result.find(f"{{{_NS}}}DBInstance")
        if db_el is None:
            raise APIError(
                "DeleteDBInstance returned no DBInstance",
                connector="rds",
                action="DeleteDBInstance",
            )
        return self._parse_instance(db_el)

    @action("Stop a database instance")
    async def stop_db_instance(
        self,
        db_instance_identifier: str,
    ) -> RDSInstance:
        """Stop a running RDS database instance.

        Args:
            db_instance_identifier: Identifier of the instance to stop.

        Returns:
            The stopped RDSInstance.
        """
        params: dict[str, str] = {
            "DBInstanceIdentifier": db_instance_identifier,
        }

        root = await self._rds_request("StopDBInstance", params)
        result = _get_result(root, "StopDBInstance")
        db_el = result.find(f"{{{_NS}}}DBInstance")
        if db_el is None:
            raise APIError(
                "StopDBInstance returned no DBInstance",
                connector="rds",
                action="StopDBInstance",
            )
        return self._parse_instance(db_el)

    @action("Start a stopped database instance")
    async def start_db_instance(
        self,
        db_instance_identifier: str,
    ) -> RDSInstance:
        """Start a stopped RDS database instance.

        Args:
            db_instance_identifier: Identifier of the instance to start.

        Returns:
            The started RDSInstance.
        """
        params: dict[str, str] = {
            "DBInstanceIdentifier": db_instance_identifier,
        }

        root = await self._rds_request("StartDBInstance", params)
        result = _get_result(root, "StartDBInstance")
        db_el = result.find(f"{{{_NS}}}DBInstance")
        if db_el is None:
            raise APIError(
                "StartDBInstance returned no DBInstance",
                connector="rds",
                action="StartDBInstance",
            )
        return self._parse_instance(db_el)

    @action("Reboot a database instance")
    async def reboot_db_instance(
        self,
        db_instance_identifier: str,
        force_failover: bool = False,
    ) -> RDSInstance:
        """Reboot an RDS database instance.

        Args:
            db_instance_identifier: Identifier of the instance to reboot.
            force_failover: Whether to force a failover from one AZ to
                another (Multi-AZ instances only).

        Returns:
            The rebooted RDSInstance.
        """
        params: dict[str, str] = {
            "DBInstanceIdentifier": db_instance_identifier,
        }
        if force_failover:
            params["ForceFailover"] = "true"

        root = await self._rds_request("RebootDBInstance", params)
        result = _get_result(root, "RebootDBInstance")
        db_el = result.find(f"{{{_NS}}}DBInstance")
        if db_el is None:
            raise APIError(
                "RebootDBInstance returned no DBInstance",
                connector="rds",
                action="RebootDBInstance",
            )
        return self._parse_instance(db_el)

    @action("Modify a database instance")
    async def modify_db_instance(
        self,
        db_instance_identifier: str,
        db_instance_class: str = "",
        allocated_storage: int = 0,
        apply_immediately: bool = False,
    ) -> RDSInstance:
        """Modify settings for an RDS database instance.

        Args:
            db_instance_identifier: Identifier of the instance to modify.
            db_instance_class: New compute and memory capacity class.
            allocated_storage: New storage size in GiB (0 to keep current).
            apply_immediately: Whether to apply changes immediately or
                during the next maintenance window.

        Returns:
            The modified RDSInstance.
        """
        params: dict[str, str] = {
            "DBInstanceIdentifier": db_instance_identifier,
        }
        if db_instance_class:
            params["DBInstanceClass"] = db_instance_class
        if allocated_storage > 0:
            params["AllocatedStorage"] = str(allocated_storage)
        if apply_immediately:
            params["ApplyImmediately"] = "true"

        root = await self._rds_request("ModifyDBInstance", params)
        result = _get_result(root, "ModifyDBInstance")
        db_el = result.find(f"{{{_NS}}}DBInstance")
        if db_el is None:
            raise APIError(
                "ModifyDBInstance returned no DBInstance",
                connector="rds",
                action="ModifyDBInstance",
            )
        return self._parse_instance(db_el)

    # ==================================================================
    # Actions -- Snapshots
    # ==================================================================

    @action("Create a database snapshot")
    async def create_db_snapshot(
        self,
        db_snapshot_identifier: str,
        db_instance_identifier: str,
    ) -> RDSSnapshot:
        """Create a snapshot of an RDS database instance.

        Args:
            db_snapshot_identifier: Identifier for the new snapshot.
            db_instance_identifier: Identifier of the instance to snapshot.

        Returns:
            The created RDSSnapshot.
        """
        params: dict[str, str] = {
            "DBSnapshotIdentifier": db_snapshot_identifier,
            "DBInstanceIdentifier": db_instance_identifier,
        }

        root = await self._rds_request("CreateDBSnapshot", params)
        result = _get_result(root, "CreateDBSnapshot")
        snap_el = result.find(f"{{{_NS}}}DBSnapshot")
        if snap_el is None:
            raise APIError(
                "CreateDBSnapshot returned no DBSnapshot",
                connector="rds",
                action="CreateDBSnapshot",
            )
        return self._parse_snapshot(snap_el)

    @action("Describe database snapshots")
    async def describe_db_snapshots(
        self,
        db_instance_identifier: str = "",
        db_snapshot_identifier: str = "",
    ) -> list[RDSSnapshot]:
        """Describe RDS database snapshots.

        Args:
            db_instance_identifier: Filter by DB instance identifier.
            db_snapshot_identifier: Filter by snapshot identifier.

        Returns:
            List of RDSSnapshot objects.
        """
        params: dict[str, str] = {}
        if db_instance_identifier:
            params["DBInstanceIdentifier"] = db_instance_identifier
        if db_snapshot_identifier:
            params["DBSnapshotIdentifier"] = db_snapshot_identifier

        root = await self._rds_request("DescribeDBSnapshots", params)
        result = _get_result(root, "DescribeDBSnapshots")
        snaps_el = result.find(f"{{{_NS}}}DBSnapshots")
        if snaps_el is None:
            return []
        return [
            self._parse_snapshot(el)
            for el in _findall(snaps_el, "DBSnapshot")
        ]

    @action("Delete a database snapshot", dangerous=True)
    async def delete_db_snapshot(
        self,
        db_snapshot_identifier: str,
    ) -> RDSSnapshot:
        """Delete an RDS database snapshot.

        Args:
            db_snapshot_identifier: Identifier of the snapshot to delete.

        Returns:
            The deleted RDSSnapshot.
        """
        params: dict[str, str] = {
            "DBSnapshotIdentifier": db_snapshot_identifier,
        }

        root = await self._rds_request("DeleteDBSnapshot", params)
        result = _get_result(root, "DeleteDBSnapshot")
        snap_el = result.find(f"{{{_NS}}}DBSnapshot")
        if snap_el is None:
            raise APIError(
                "DeleteDBSnapshot returned no DBSnapshot",
                connector="rds",
                action="DeleteDBSnapshot",
            )
        return self._parse_snapshot(snap_el)

    @action("Restore a database instance from a snapshot")
    async def restore_db_instance_from_snapshot(
        self,
        db_instance_identifier: str,
        db_snapshot_identifier: str,
        db_instance_class: str = "",
    ) -> RDSInstance:
        """Restore an RDS database instance from a snapshot.

        Args:
            db_instance_identifier: Identifier for the restored instance.
            db_snapshot_identifier: Identifier of the snapshot to restore from.
            db_instance_class: Compute class for the restored instance
                (uses snapshot's class if empty).

        Returns:
            The restored RDSInstance.
        """
        params: dict[str, str] = {
            "DBInstanceIdentifier": db_instance_identifier,
            "DBSnapshotIdentifier": db_snapshot_identifier,
        }
        if db_instance_class:
            params["DBInstanceClass"] = db_instance_class

        root = await self._rds_request(
            "RestoreDBInstanceFromDBSnapshot", params
        )
        result = _get_result(root, "RestoreDBInstanceFromDBSnapshot")
        db_el = result.find(f"{{{_NS}}}DBInstance")
        if db_el is None:
            raise APIError(
                "RestoreDBInstanceFromDBSnapshot returned no DBInstance",
                connector="rds",
                action="RestoreDBInstanceFromDBSnapshot",
            )
        return self._parse_instance(db_el)

    # ==================================================================
    # Actions -- Clusters (Aurora)
    # ==================================================================

    @action("Describe Aurora database clusters")
    async def describe_db_clusters(
        self,
        db_cluster_identifier: str = "",
    ) -> list[RDSCluster]:
        """Describe Aurora database clusters.

        Args:
            db_cluster_identifier: Optional identifier to describe a
                specific cluster. If empty, describes all clusters.

        Returns:
            List of RDSCluster objects.
        """
        params: dict[str, str] = {}
        if db_cluster_identifier:
            params["DBClusterIdentifier"] = db_cluster_identifier

        root = await self._rds_request("DescribeDBClusters", params)
        result = _get_result(root, "DescribeDBClusters")
        clusters_el = result.find(f"{{{_NS}}}DBClusters")
        if clusters_el is None:
            return []
        return [
            self._parse_cluster(el)
            for el in _findall(clusters_el, "DBCluster")
        ]

    @action("Create an Aurora database cluster", dangerous=True)
    async def create_db_cluster(
        self,
        db_cluster_identifier: str,
        engine: str = "aurora-postgresql",
        master_username: str = "admin",
        master_user_password: str = "",
        database_name: str = "",
    ) -> RDSCluster:
        """Create a new Aurora database cluster.

        Args:
            db_cluster_identifier: Unique identifier for the cluster.
            engine: Database engine (aurora-mysql, aurora-postgresql).
            master_username: Master user name for the cluster.
            master_user_password: Password for the master user.
            database_name: Name of the initial database to create.

        Returns:
            The created RDSCluster.
        """
        params: dict[str, str] = {
            "DBClusterIdentifier": db_cluster_identifier,
            "Engine": engine,
            "MasterUsername": master_username,
        }
        if master_user_password:
            params["MasterUserPassword"] = master_user_password
        if database_name:
            params["DatabaseName"] = database_name

        root = await self._rds_request("CreateDBCluster", params)
        result = _get_result(root, "CreateDBCluster")
        cluster_el = result.find(f"{{{_NS}}}DBCluster")
        if cluster_el is None:
            raise APIError(
                "CreateDBCluster returned no DBCluster",
                connector="rds",
                action="CreateDBCluster",
            )
        return self._parse_cluster(cluster_el)

    @action("Delete an Aurora database cluster", dangerous=True)
    async def delete_db_cluster(
        self,
        db_cluster_identifier: str,
        skip_final_snapshot: bool = False,
    ) -> RDSCluster:
        """Delete an Aurora database cluster.

        Args:
            db_cluster_identifier: Identifier of the cluster to delete.
            skip_final_snapshot: Whether to skip creating a final snapshot.

        Returns:
            The deleted RDSCluster.
        """
        params: dict[str, str] = {
            "DBClusterIdentifier": db_cluster_identifier,
            "SkipFinalSnapshot": str(skip_final_snapshot).lower(),
        }

        root = await self._rds_request("DeleteDBCluster", params)
        result = _get_result(root, "DeleteDBCluster")
        cluster_el = result.find(f"{{{_NS}}}DBCluster")
        if cluster_el is None:
            raise APIError(
                "DeleteDBCluster returned no DBCluster",
                connector="rds",
                action="DeleteDBCluster",
            )
        return self._parse_cluster(cluster_el)

    # ==================================================================
    # Actions -- Networking
    # ==================================================================

    @action("Create a DB subnet group")
    async def create_db_subnet_group(
        self,
        db_subnet_group_name: str,
        db_subnet_group_description: str,
        subnet_ids: list[str],
    ) -> RDSSubnetGroup:
        """Create a DB subnet group.

        Args:
            db_subnet_group_name: Name of the subnet group.
            db_subnet_group_description: Description for the subnet group.
            subnet_ids: List of VPC subnet IDs to include.

        Returns:
            The created RDSSubnetGroup.
        """
        params: dict[str, str] = {
            "DBSubnetGroupName": db_subnet_group_name,
            "DBSubnetGroupDescription": db_subnet_group_description,
        }
        params.update(self._encode_members("SubnetIds", subnet_ids))

        root = await self._rds_request("CreateDBSubnetGroup", params)
        result = _get_result(root, "CreateDBSubnetGroup")
        sg_el = result.find(f"{{{_NS}}}DBSubnetGroup")
        if sg_el is None:
            raise APIError(
                "CreateDBSubnetGroup returned no DBSubnetGroup",
                connector="rds",
                action="CreateDBSubnetGroup",
            )
        return self._parse_subnet_group(sg_el)

    @action("Describe DB subnet groups")
    async def describe_db_subnet_groups(
        self,
        db_subnet_group_name: str = "",
    ) -> list[RDSSubnetGroup]:
        """Describe DB subnet groups.

        Args:
            db_subnet_group_name: Optional name to describe a specific
                subnet group. If empty, describes all subnet groups.

        Returns:
            List of RDSSubnetGroup objects.
        """
        params: dict[str, str] = {}
        if db_subnet_group_name:
            params["DBSubnetGroupName"] = db_subnet_group_name

        root = await self._rds_request("DescribeDBSubnetGroups", params)
        result = _get_result(root, "DescribeDBSubnetGroups")
        groups_el = result.find(f"{{{_NS}}}DBSubnetGroups")
        if groups_el is None:
            return []
        return [
            self._parse_subnet_group(el)
            for el in _findall(groups_el, "DBSubnetGroup")
        ]

    # ==================================================================
    # Actions -- Info
    # ==================================================================

    @action("Describe available database engine versions")
    async def describe_db_engine_versions(
        self,
        engine: str = "postgres",
    ) -> list[dict]:
        """Describe available database engine versions.

        Args:
            engine: Database engine to query (postgres, mysql, etc.).

        Returns:
            List of dicts with engine version information.
        """
        params: dict[str, str] = {
            "Engine": engine,
        }

        root = await self._rds_request("DescribeDBEngineVersions", params)
        result = _get_result(root, "DescribeDBEngineVersions")
        versions_el = result.find(f"{{{_NS}}}DBEngineVersions")
        if versions_el is None:
            return []

        versions: list[dict[str, Any]] = []
        for el in _findall(versions_el, "DBEngineVersion"):
            versions.append({
                "Engine": _find(el, "Engine"),
                "EngineVersion": _find(el, "EngineVersion"),
                "DBParameterGroupFamily": _find(el, "DBParameterGroupFamily"),
                "DBEngineDescription": _find(el, "DBEngineDescription"),
                "DBEngineVersionDescription": _find(
                    el, "DBEngineVersionDescription"
                ),
            })
        return versions

    @action("Describe orderable DB instance options")
    async def describe_orderable_db_instance_options(
        self,
        engine: str = "postgres",
    ) -> list[dict]:
        """Describe orderable DB instance options for an engine.

        Args:
            engine: Database engine to query (postgres, mysql, etc.).

        Returns:
            List of dicts with orderable instance option information.
        """
        params: dict[str, str] = {
            "Engine": engine,
        }

        root = await self._rds_request(
            "DescribeOrderableDBInstanceOptions", params
        )
        result = _get_result(root, "DescribeOrderableDBInstanceOptions")
        options_el = result.find(f"{{{_NS}}}OrderableDBInstanceOptions")
        if options_el is None:
            return []

        options: list[dict[str, Any]] = []
        for el in _findall(options_el, "OrderableDBInstanceOption"):
            options.append({
                "DBInstanceClass": _find(el, "DBInstanceClass"),
                "Engine": _find(el, "Engine"),
                "EngineVersion": _find(el, "EngineVersion"),
                "StorageType": _find(el, "StorageType"),
                "MultiAZCapable": _find(el, "MultiAZCapable"),
                "AvailabilityZones": [
                    _find(az, "Name")
                    for az_list in [el.find(f"{{{_NS}}}AvailabilityZones")]
                    if az_list is not None
                    for az in _findall(az_list, "AvailabilityZone")
                ],
            })
        return options

    @action("Describe database events")
    async def describe_events(
        self,
        source_identifier: str = "",
        source_type: str = "",
        duration: int = 60,
    ) -> list[RDSEvent]:
        """Describe RDS events for the past duration.

        Args:
            source_identifier: Identifier of the source to filter events.
            source_type: Source type filter (db-instance, db-cluster,
                db-snapshot, db-security-group, db-parameter-group).
            duration: Number of minutes to look back (default 60).

        Returns:
            List of RDSEvent objects.
        """
        params: dict[str, str] = {
            "Duration": str(duration),
        }
        if source_identifier:
            params["SourceIdentifier"] = source_identifier
        if source_type:
            params["SourceType"] = source_type

        root = await self._rds_request("DescribeEvents", params)
        result = _get_result(root, "DescribeEvents")
        events_el = result.find(f"{{{_NS}}}Events")
        if events_el is None:
            return []
        return [
            self._parse_event(el)
            for el in _findall(events_el, "Event")
        ]

    # ==================================================================
    # Actions -- Replicas
    # ==================================================================

    @action("Create a read replica")
    async def create_db_instance_read_replica(
        self,
        db_instance_identifier: str,
        source_db_instance_identifier: str,
        db_instance_class: str = "",
    ) -> RDSInstance:
        """Create a read replica of an RDS database instance.

        Args:
            db_instance_identifier: Identifier for the read replica.
            source_db_instance_identifier: Identifier of the source instance.
            db_instance_class: Compute class for the replica (uses source
                instance's class if empty).

        Returns:
            The created read replica RDSInstance.
        """
        params: dict[str, str] = {
            "DBInstanceIdentifier": db_instance_identifier,
            "SourceDBInstanceIdentifier": source_db_instance_identifier,
        }
        if db_instance_class:
            params["DBInstanceClass"] = db_instance_class

        root = await self._rds_request(
            "CreateDBInstanceReadReplica", params
        )
        result = _get_result(root, "CreateDBInstanceReadReplica")
        db_el = result.find(f"{{{_NS}}}DBInstance")
        if db_el is None:
            raise APIError(
                "CreateDBInstanceReadReplica returned no DBInstance",
                connector="rds",
                action="CreateDBInstanceReadReplica",
            )
        return self._parse_instance(db_el)

    @action("Promote a read replica to standalone")
    async def promote_read_replica(
        self,
        db_instance_identifier: str,
    ) -> RDSInstance:
        """Promote a read replica to a standalone RDS instance.

        Args:
            db_instance_identifier: Identifier of the read replica to promote.

        Returns:
            The promoted RDSInstance.
        """
        params: dict[str, str] = {
            "DBInstanceIdentifier": db_instance_identifier,
        }

        root = await self._rds_request("PromoteReadReplica", params)
        result = _get_result(root, "PromoteReadReplica")
        db_el = result.find(f"{{{_NS}}}DBInstance")
        if db_el is None:
            raise APIError(
                "PromoteReadReplica returned no DBInstance",
                connector="rds",
                action="PromoteReadReplica",
            )
        return self._parse_instance(db_el)

    # ==================================================================
    # Actions -- Tags
    # ==================================================================

    @action("List tags for a database resource")
    async def list_tags_for_resource(
        self,
        resource_name: str,
    ) -> dict:
        """List tags for an RDS resource.

        Args:
            resource_name: The ARN of the RDS resource.

        Returns:
            Dict of tag key-value pairs.
        """
        params: dict[str, str] = {
            "ResourceName": resource_name,
        }

        root = await self._rds_request("ListTagsForResource", params)
        result = _get_result(root, "ListTagsForResource")
        tags: dict[str, str] = {}
        tag_list = result.find(f"{{{_NS}}}TagList")
        if tag_list is not None:
            for tag_el in _findall(tag_list, "Tag"):
                key = _find(tag_el, "Key")
                val = _find(tag_el, "Value")
                if key:
                    tags[key] = val
        return tags

    @action("Add tags to a database resource")
    async def add_tags_to_resource(
        self,
        resource_name: str,
        tags: dict,
    ) -> dict:
        """Add tags to an RDS resource.

        Args:
            resource_name: The ARN of the RDS resource.
            tags: Dict of tag key-value pairs to add.

        Returns:
            Empty dict on success.
        """
        params: dict[str, str] = {
            "ResourceName": resource_name,
        }
        params.update(self._encode_tags(tags))

        await self._rds_request("AddTagsToResource", params)
        return {}

    @action("Remove tags from a database resource")
    async def remove_tags_from_resource(
        self,
        resource_name: str,
        tag_keys: list[str],
    ) -> dict:
        """Remove tags from an RDS resource.

        Args:
            resource_name: The ARN of the RDS resource.
            tag_keys: List of tag keys to remove.

        Returns:
            Empty dict on success.
        """
        params: dict[str, str] = {
            "ResourceName": resource_name,
        }
        params.update(self._encode_members("TagKeys", tag_keys))

        await self._rds_request("RemoveTagsFromResource", params)
        return {}

    # ==================================================================
    # Actions -- Parameters
    # ==================================================================

    @action("Describe DB parameter groups")
    async def describe_db_parameter_groups(
        self,
        db_parameter_group_name: str = "",
    ) -> list[dict]:
        """Describe DB parameter groups.

        Args:
            db_parameter_group_name: Optional name to describe a specific
                parameter group. If empty, describes all parameter groups.

        Returns:
            List of dicts with parameter group information.
        """
        params: dict[str, str] = {}
        if db_parameter_group_name:
            params["DBParameterGroupName"] = db_parameter_group_name

        root = await self._rds_request("DescribeDBParameterGroups", params)
        result = _get_result(root, "DescribeDBParameterGroups")
        groups_el = result.find(f"{{{_NS}}}DBParameterGroups")
        if groups_el is None:
            return []

        groups: list[dict[str, Any]] = []
        for el in _findall(groups_el, "DBParameterGroup"):
            groups.append({
                "DBParameterGroupName": _find(el, "DBParameterGroupName"),
                "DBParameterGroupFamily": _find(el, "DBParameterGroupFamily"),
                "Description": _find(el, "Description"),
                "DBParameterGroupArn": _find(el, "DBParameterGroupArn"),
            })
        return groups
