"""AWS ECS connector -- deploy and manage containerized applications.

Uses the ECS JSON Target API with ``X-Amz-Target`` headers. Credentials
should be ``"access_key:secret_key:region"`` format.

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
    ECSCluster,
    ECSService,
    ECSTask,
    ECSTaskDefinition,
)

logger = logging.getLogger("toolsconnector.ecs")

# X-Amz-Target prefix for the ECS JSON API.
_TARGET_PREFIX = "AmazonEC2ContainerServiceV20141113"


class ECS(BaseConnector):
    """Connect to AWS ECS to deploy and manage containerized applications.

    Credentials format: ``"access_key_id:secret_access_key:region"``
    Uses the ECS JSON API (``X-Amz-Target: AmazonEC2ContainerServiceV20141113.{Action}``).

    .. note::

        SigV4 signing is simplified. For production, use ``boto3``.
    """

    name = "ecs"
    display_name = "AWS ECS"
    category = ConnectorCategory.COMPUTE
    protocol = ProtocolType.REST
    base_url = "https://ecs.us-east-1.amazonaws.com"
    description = "Deploy and manage containerized applications with ECS and Fargate."
    _rate_limit_config = RateLimitSpec(rate=20, period=1, burst=40)

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
        self._base_url = f"https://ecs.{self._region}.amazonaws.com"

        self._client = httpx.AsyncClient(timeout=self._timeout)

    async def _teardown(self) -> None:
        """Close the HTTP client."""
        if hasattr(self, "_client"):
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _ecs_request(
        self,
        target_action: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a signed ECS JSON API request.

        Args:
            target_action: ECS action name (e.g. ``CreateCluster``).
            payload: JSON request body dict.

        Returns:
            Parsed JSON response body.

        Raises:
            NotFoundError: If the resource is not found.
            APIError: For any ECS API error.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        body = json.dumps(payload)

        payload_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()

        headers: dict[str, str] = {
            "Content-Type": "application/x-amz-json-1.1",
            "X-Amz-Target": f"{_TARGET_PREFIX}.{target_action}",
            "x-amz-date": amz_date,
            "Host": f"ecs.{self._region}.amazonaws.com",
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
            "ecs",
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
            full_msg = f"ECS {target_action} error: {err_type} - {err_msg}"

            if "NotFound" in err_type or "ClusterNotFoundException" in err_type:
                raise NotFoundError(
                    full_msg,
                    connector="ecs",
                    action=target_action,
                    details=err_body,
                )
            raise APIError(
                full_msg,
                connector="ecs",
                action=target_action,
                upstream_status=response.status_code,
                details=err_body,
            )

        return response.json()

    # ------------------------------------------------------------------
    # Helpers -- model parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_cluster(data: dict[str, Any]) -> ECSCluster:
        """Parse a raw ECS cluster dict into an ECSCluster model."""
        return ECSCluster(
            cluster_arn=data.get("clusterArn", ""),
            cluster_name=data.get("clusterName", ""),
            status=data.get("status", ""),
            registered_container_instances_count=data.get("registeredContainerInstancesCount", 0),
            running_tasks_count=data.get("runningTasksCount", 0),
            pending_tasks_count=data.get("pendingTasksCount", 0),
            active_services_count=data.get("activeServicesCount", 0),
            settings=data.get("settings", []),
        )

    @staticmethod
    def _parse_service(data: dict[str, Any]) -> ECSService:
        """Parse a raw ECS service dict into an ECSService model."""
        return ECSService(
            service_arn=data.get("serviceArn", ""),
            service_name=data.get("serviceName", ""),
            cluster_arn=data.get("clusterArn", ""),
            status=data.get("status", ""),
            desired_count=data.get("desiredCount", 0),
            running_count=data.get("runningCount", 0),
            pending_count=data.get("pendingCount", 0),
            launch_type=data.get("launchType", ""),
            task_definition=data.get("taskDefinition", ""),
            load_balancers=data.get("loadBalancers", []),
            deployment_configuration=data.get("deploymentConfiguration", {}),
            deployments=data.get("deployments", []),
            created_at=data.get("createdAt"),
            events=data.get("events", []),
        )

    @staticmethod
    def _parse_task_definition(data: dict[str, Any]) -> ECSTaskDefinition:
        """Parse a raw ECS task definition dict into an ECSTaskDefinition model."""
        return ECSTaskDefinition(
            task_definition_arn=data.get("taskDefinitionArn", ""),
            family=data.get("family", ""),
            revision=data.get("revision", 0),
            status=data.get("status", ""),
            container_definitions=data.get("containerDefinitions", []),
            cpu=data.get("cpu", ""),
            memory=data.get("memory", ""),
            network_mode=data.get("networkMode", ""),
            requires_compatibilities=data.get("requiresCompatibilities", []),
            execution_role_arn=data.get("executionRoleArn", ""),
            task_role_arn=data.get("taskRoleArn", ""),
            volumes=data.get("volumes", []),
        )

    @staticmethod
    def _parse_task(data: dict[str, Any]) -> ECSTask:
        """Parse a raw ECS task dict into an ECSTask model."""
        return ECSTask(
            task_arn=data.get("taskArn", ""),
            task_definition_arn=data.get("taskDefinitionArn", ""),
            cluster_arn=data.get("clusterArn", ""),
            container_instance_arn=data.get("containerInstanceArn", ""),
            last_status=data.get("lastStatus", ""),
            desired_status=data.get("desiredStatus", ""),
            cpu=data.get("cpu", ""),
            memory=data.get("memory", ""),
            containers=data.get("containers", []),
            started_at=data.get("startedAt"),
            stopped_at=data.get("stoppedAt"),
            stopped_reason=data.get("stoppedReason", ""),
            launch_type=data.get("launchType", ""),
            connectivity=data.get("connectivity", ""),
        )

    # ==================================================================
    # Actions -- Clusters
    # ==================================================================

    @action("Create an ECS cluster")
    async def create_cluster(
        self,
        cluster_name: str,
        capacity_providers: Optional[list[str]] = None,
        settings: Optional[list[dict]] = None,
    ) -> ECSCluster:
        """Create a new ECS cluster.

        Args:
            cluster_name: The name of the cluster to create.
            capacity_providers: List of capacity provider names to associate.
            settings: Cluster settings (e.g. containerInsights).

        Returns:
            The created ECSCluster.
        """
        payload: dict[str, Any] = {"clusterName": cluster_name}
        if capacity_providers is not None:
            payload["capacityProviders"] = capacity_providers
        if settings is not None:
            payload["settings"] = settings

        body = await self._ecs_request("CreateCluster", payload)
        return self._parse_cluster(body.get("cluster", {}))

    @action("Delete an ECS cluster", dangerous=True)
    async def delete_cluster(self, cluster: str) -> ECSCluster:
        """Delete an ECS cluster.

        The cluster must have no registered container instances and no
        running tasks.

        Args:
            cluster: The cluster name or ARN to delete.

        Returns:
            The deleted ECSCluster.
        """
        body = await self._ecs_request("DeleteCluster", {"cluster": cluster})
        return self._parse_cluster(body.get("cluster", {}))

    @action("List ECS clusters")
    async def list_clusters(self) -> list[str]:
        """List all ECS cluster ARNs in the account.

        Returns:
            List of cluster ARN strings.
        """
        body = await self._ecs_request("ListClusters", {})
        return body.get("clusterArns", [])

    @action("Describe ECS clusters")
    async def describe_clusters(self, clusters: list[str]) -> list[ECSCluster]:
        """Describe one or more ECS clusters.

        Args:
            clusters: List of cluster names or ARNs to describe.

        Returns:
            List of ECSCluster objects.
        """
        body = await self._ecs_request(
            "DescribeClusters",
            {
                "clusters": clusters,
            },
        )
        return [self._parse_cluster(c) for c in body.get("clusters", [])]

    # ==================================================================
    # Actions -- Services
    # ==================================================================

    @action("Create an ECS service")
    async def create_service(
        self,
        cluster: str,
        service_name: str,
        task_definition: str,
        desired_count: int = 1,
        launch_type: str = "FARGATE",
        network_configuration: Optional[dict] = None,
        load_balancers: Optional[list[dict]] = None,
    ) -> ECSService:
        """Create a new ECS service in a cluster.

        Args:
            cluster: The cluster name or ARN.
            service_name: The name of the service.
            task_definition: The task definition family:revision or ARN.
            desired_count: Number of task instances to run.
            launch_type: Launch type (FARGATE or EC2).
            network_configuration: Network configuration for awsvpc mode.
            load_balancers: List of load balancer configurations.

        Returns:
            The created ECSService.
        """
        payload: dict[str, Any] = {
            "cluster": cluster,
            "serviceName": service_name,
            "taskDefinition": task_definition,
            "desiredCount": desired_count,
            "launchType": launch_type,
        }
        if network_configuration is not None:
            payload["networkConfiguration"] = network_configuration
        if load_balancers is not None:
            payload["loadBalancers"] = load_balancers

        body = await self._ecs_request("CreateService", payload)
        return self._parse_service(body.get("service", {}))

    @action("Update an ECS service")
    async def update_service(
        self,
        cluster: str,
        service: str,
        task_definition: Optional[str] = None,
        desired_count: Optional[int] = None,
        force_new_deployment: bool = False,
    ) -> ECSService:
        """Update an existing ECS service.

        Args:
            cluster: The cluster name or ARN.
            service: The service name or ARN.
            task_definition: New task definition family:revision or ARN.
            desired_count: New desired count of running tasks.
            force_new_deployment: Force a new deployment of the service.

        Returns:
            The updated ECSService.
        """
        payload: dict[str, Any] = {
            "cluster": cluster,
            "service": service,
        }
        if task_definition is not None:
            payload["taskDefinition"] = task_definition
        if desired_count is not None:
            payload["desiredCount"] = desired_count
        if force_new_deployment:
            payload["forceNewDeployment"] = True

        body = await self._ecs_request("UpdateService", payload)
        return self._parse_service(body.get("service", {}))

    @action("Delete an ECS service", dangerous=True)
    async def delete_service(
        self,
        cluster: str,
        service: str,
        force: bool = False,
    ) -> ECSService:
        """Delete an ECS service.

        Args:
            cluster: The cluster name or ARN.
            service: The service name or ARN.
            force: Force deletion even if the service has running tasks.

        Returns:
            The deleted ECSService.
        """
        payload: dict[str, Any] = {
            "cluster": cluster,
            "service": service,
        }
        if force:
            payload["force"] = True

        body = await self._ecs_request("DeleteService", payload)
        return self._parse_service(body.get("service", {}))

    @action("Describe ECS services")
    async def describe_services(
        self,
        cluster: str,
        services: list[str],
    ) -> list[ECSService]:
        """Describe one or more ECS services.

        Args:
            cluster: The cluster name or ARN.
            services: List of service names or ARNs to describe.

        Returns:
            List of ECSService objects.
        """
        body = await self._ecs_request(
            "DescribeServices",
            {
                "cluster": cluster,
                "services": services,
            },
        )
        return [self._parse_service(s) for s in body.get("services", [])]

    @action("List ECS services in a cluster")
    async def list_services(
        self,
        cluster: str,
        launch_type: Optional[str] = None,
    ) -> list[str]:
        """List service ARNs in a cluster.

        Args:
            cluster: The cluster name or ARN.
            launch_type: Filter by launch type (FARGATE or EC2).

        Returns:
            List of service ARN strings.
        """
        payload: dict[str, Any] = {"cluster": cluster}
        if launch_type is not None:
            payload["launchType"] = launch_type

        body = await self._ecs_request("ListServices", payload)
        return body.get("serviceArns", [])

    # ==================================================================
    # Actions -- Task definitions
    # ==================================================================

    @action("Register a new task definition")
    async def register_task_definition(
        self,
        family: str,
        container_definitions: list[dict],
        cpu: str = "256",
        memory: str = "512",
        network_mode: str = "awsvpc",
        requires_compatibilities: Optional[list[str]] = None,
        execution_role_arn: str = "",
        task_role_arn: str = "",
    ) -> ECSTaskDefinition:
        """Register a new ECS task definition.

        Args:
            family: The family name for the task definition.
            container_definitions: List of container definition dicts.
            cpu: CPU units for the task (e.g. 256, 512, 1024).
            memory: Memory in MiB for the task (e.g. 512, 1024).
            network_mode: Docker networking mode (awsvpc, bridge, host, none).
            requires_compatibilities: Launch type compatibilities (FARGATE, EC2).
            execution_role_arn: ARN of the task execution IAM role.
            task_role_arn: ARN of the task IAM role for container permissions.

        Returns:
            The registered ECSTaskDefinition.
        """
        payload: dict[str, Any] = {
            "family": family,
            "containerDefinitions": container_definitions,
            "cpu": cpu,
            "memory": memory,
            "networkMode": network_mode,
        }
        if requires_compatibilities is not None:
            payload["requiresCompatibilities"] = requires_compatibilities
        if execution_role_arn:
            payload["executionRoleArn"] = execution_role_arn
        if task_role_arn:
            payload["taskRoleArn"] = task_role_arn

        body = await self._ecs_request("RegisterTaskDefinition", payload)
        return self._parse_task_definition(body.get("taskDefinition", {}))

    @action("Describe a task definition")
    async def describe_task_definition(
        self,
        task_definition: str,
    ) -> ECSTaskDefinition:
        """Describe an ECS task definition.

        Args:
            task_definition: The task definition family:revision or ARN.

        Returns:
            The ECSTaskDefinition.
        """
        body = await self._ecs_request(
            "DescribeTaskDefinition",
            {
                "taskDefinition": task_definition,
            },
        )
        return self._parse_task_definition(body.get("taskDefinition", {}))

    @action("List task definition families")
    async def list_task_definition_families(
        self,
        family_prefix: str = "",
        status: str = "ACTIVE",
    ) -> list[str]:
        """List ECS task definition family names.

        Args:
            family_prefix: Filter families by name prefix.
            status: Filter by status (ACTIVE, INACTIVE, ALL).

        Returns:
            List of family name strings.
        """
        payload: dict[str, Any] = {"status": status}
        if family_prefix:
            payload["familyPrefix"] = family_prefix

        body = await self._ecs_request("ListTaskDefinitionFamilies", payload)
        return body.get("families", [])

    @action("List task definition revisions")
    async def list_task_definitions(
        self,
        family_prefix: str = "",
        status: str = "ACTIVE",
        sort: str = "DESC",
    ) -> list[str]:
        """List ECS task definition ARNs.

        Args:
            family_prefix: Filter by family name prefix.
            status: Filter by status (ACTIVE, INACTIVE).
            sort: Sort order for results (ASC or DESC).

        Returns:
            List of task definition ARN strings.
        """
        payload: dict[str, Any] = {
            "status": status,
            "sort": sort,
        }
        if family_prefix:
            payload["familyPrefix"] = family_prefix

        body = await self._ecs_request("ListTaskDefinitions", payload)
        return body.get("taskDefinitionArns", [])

    @action("Deregister a task definition")
    async def deregister_task_definition(
        self,
        task_definition: str,
    ) -> ECSTaskDefinition:
        """Deregister an ECS task definition revision.

        Args:
            task_definition: The task definition family:revision or ARN.

        Returns:
            The deregistered ECSTaskDefinition.
        """
        body = await self._ecs_request(
            "DeregisterTaskDefinition",
            {
                "taskDefinition": task_definition,
            },
        )
        return self._parse_task_definition(body.get("taskDefinition", {}))

    # ==================================================================
    # Actions -- Tasks
    # ==================================================================

    @action("Run a standalone task")
    async def run_task(
        self,
        cluster: str,
        task_definition: str,
        count: int = 1,
        launch_type: str = "FARGATE",
        network_configuration: Optional[dict] = None,
    ) -> list[ECSTask]:
        """Run one or more standalone tasks.

        Args:
            cluster: The cluster name or ARN.
            task_definition: The task definition family:revision or ARN.
            count: Number of task instances to run (1-10).
            launch_type: Launch type (FARGATE or EC2).
            network_configuration: Network configuration for awsvpc mode.

        Returns:
            List of started ECSTask objects.
        """
        payload: dict[str, Any] = {
            "cluster": cluster,
            "taskDefinition": task_definition,
            "count": count,
            "launchType": launch_type,
        }
        if network_configuration is not None:
            payload["networkConfiguration"] = network_configuration

        body = await self._ecs_request("RunTask", payload)
        return [self._parse_task(t) for t in body.get("tasks", [])]

    @action("Stop a running task", dangerous=True)
    async def stop_task(
        self,
        cluster: str,
        task: str,
        reason: str = "",
    ) -> ECSTask:
        """Stop a running ECS task.

        Args:
            cluster: The cluster name or ARN.
            task: The task ID or ARN.
            reason: Reason for stopping the task.

        Returns:
            The stopped ECSTask.
        """
        payload: dict[str, Any] = {
            "cluster": cluster,
            "task": task,
        }
        if reason:
            payload["reason"] = reason

        body = await self._ecs_request("StopTask", payload)
        return self._parse_task(body.get("task", {}))

    @action("List tasks in a cluster")
    async def list_tasks(
        self,
        cluster: str,
        service_name: Optional[str] = None,
        desired_status: str = "RUNNING",
    ) -> list[str]:
        """List task ARNs in a cluster.

        Args:
            cluster: The cluster name or ARN.
            service_name: Filter tasks by service name.
            desired_status: Filter by desired status (RUNNING or STOPPED).

        Returns:
            List of task ARN strings.
        """
        payload: dict[str, Any] = {
            "cluster": cluster,
            "desiredStatus": desired_status,
        }
        if service_name is not None:
            payload["serviceName"] = service_name

        body = await self._ecs_request("ListTasks", payload)
        return body.get("taskArns", [])

    @action("Describe tasks")
    async def describe_tasks(
        self,
        cluster: str,
        tasks: list[str],
    ) -> list[ECSTask]:
        """Describe one or more ECS tasks.

        Args:
            cluster: The cluster name or ARN.
            tasks: List of task IDs or ARNs to describe.

        Returns:
            List of ECSTask objects.
        """
        body = await self._ecs_request(
            "DescribeTasks",
            {
                "cluster": cluster,
                "tasks": tasks,
            },
        )
        return [self._parse_task(t) for t in body.get("tasks", [])]

    # ==================================================================
    # Actions -- Capacity & settings
    # ==================================================================

    @action("Update cluster settings")
    async def update_cluster_settings(
        self,
        cluster: str,
        settings: list[dict],
    ) -> ECSCluster:
        """Update settings for an ECS cluster.

        Args:
            cluster: The cluster name or ARN.
            settings: List of cluster setting dicts (name/value pairs).

        Returns:
            The updated ECSCluster.
        """
        body = await self._ecs_request(
            "UpdateClusterSettings",
            {
                "cluster": cluster,
                "settings": settings,
            },
        )
        return self._parse_cluster(body.get("cluster", {}))

    @action("Put cluster capacity providers")
    async def put_cluster_capacity_providers(
        self,
        cluster: str,
        capacity_providers: list[str],
        default_capacity_provider_strategy: list[dict],
    ) -> ECSCluster:
        """Associate capacity providers with a cluster.

        Args:
            cluster: The cluster name or ARN.
            capacity_providers: List of capacity provider names.
            default_capacity_provider_strategy: Default strategy dicts.

        Returns:
            The updated ECSCluster.
        """
        body = await self._ecs_request(
            "PutClusterCapacityProviders",
            {
                "cluster": cluster,
                "capacityProviders": capacity_providers,
                "defaultCapacityProviderStrategy": default_capacity_provider_strategy,
            },
        )
        return self._parse_cluster(body.get("cluster", {}))

    # ==================================================================
    # Actions -- Tagging
    # ==================================================================

    @action("Add tags to an ECS resource")
    async def tag_resource(
        self,
        resource_arn: str,
        tags: list[dict],
    ) -> dict:
        """Add tags to an ECS resource.

        Args:
            resource_arn: The ARN of the resource to tag.
            tags: List of tag dicts with 'key' and 'value'.

        Returns:
            Empty dict on success.
        """
        await self._ecs_request(
            "TagResource",
            {
                "resourceArn": resource_arn,
                "tags": tags,
            },
        )
        return {}

    @action("List tags for an ECS resource")
    async def list_tags_for_resource(
        self,
        resource_arn: str,
    ) -> list[dict]:
        """List tags for an ECS resource.

        Args:
            resource_arn: The ARN of the resource.

        Returns:
            List of tag dicts with 'key' and 'value'.
        """
        body = await self._ecs_request(
            "ListTagsForResource",
            {
                "resourceArn": resource_arn,
            },
        )
        return body.get("tags", [])

    # ==================================================================
    # Actions -- Account settings
    # ==================================================================

    @action("List account-level ECS settings")
    async def list_account_settings(
        self,
        effective_settings: bool = True,
    ) -> list[dict]:
        """List ECS account settings.

        Args:
            effective_settings: Whether to include effective settings.

        Returns:
            List of account setting dicts.
        """
        payload: dict[str, Any] = {}
        if effective_settings:
            payload["effectiveSettings"] = True

        body = await self._ecs_request("ListAccountSettings", payload)
        return body.get("settings", [])

    # ==================================================================
    # Actions -- Container instances
    # ==================================================================

    @action("List container instances in a cluster")
    async def list_container_instances(
        self,
        cluster: str,
        status: str = "ACTIVE",
    ) -> list[str]:
        """List container instance ARNs in a cluster.

        Args:
            cluster: The cluster name or ARN.
            status: Filter by status (ACTIVE, DRAINING).

        Returns:
            List of container instance ARN strings.
        """
        payload: dict[str, Any] = {
            "cluster": cluster,
            "status": status,
        }

        body = await self._ecs_request("ListContainerInstances", payload)
        return body.get("containerInstanceArns", [])

    @action("Describe container instances")
    async def describe_container_instances(
        self,
        cluster: str,
        container_instances: list[str],
    ) -> list[dict]:
        """Describe one or more container instances.

        Args:
            cluster: The cluster name or ARN.
            container_instances: List of container instance IDs or ARNs.

        Returns:
            List of container instance detail dicts.
        """
        body = await self._ecs_request(
            "DescribeContainerInstances",
            {
                "cluster": cluster,
                "containerInstances": container_instances,
            },
        )
        return body.get("containerInstances", [])
