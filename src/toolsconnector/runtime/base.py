"""BaseConnector — abstract base class for all connectors.

Connector authors subclass this and:
1. Set class-level metadata (name, category, protocol, auth_providers).
2. Implement ``@action`` methods.
3. Optionally override lifecycle hooks (``_setup``, ``_teardown``).
"""

from __future__ import annotations

import logging
from abc import ABC
from typing import (
    Any,
    ClassVar,
    Optional,
)

from pydantic import BaseModel

from toolsconnector.runtime._sync import run_sync
from toolsconnector.runtime.action import ActionMeta, get_actions
from toolsconnector.spec.action import ActionSpec
from toolsconnector.spec.connector import (
    ConnectorCategory,
    ConnectorSpec,
    ProtocolType,
    RateLimitSpec,
)

logger = logging.getLogger("toolsconnector")


class HealthStatus(BaseModel):
    """Result of a connector health check."""

    healthy: bool
    message: str = ""
    latency_ms: Optional[float] = None


class BaseConnector(ABC):
    """Abstract base for all connectors.

    Class-level attributes (set by connector authors)::

        class Gmail(BaseConnector):
            name = "gmail"
            display_name = "Gmail"
            category = ConnectorCategory.COMMUNICATION
            protocol = ProtocolType.REST
            base_url = "https://gmail.googleapis.com"

    Attributes:
        name: Machine-readable connector name.
        display_name: Human-readable display name.
        category: Tool category enum value.
        protocol: Primary communication protocol.
        base_url: Base URL for API requests.
    """

    # --- Class-level declarations (set by subclasses) ---
    name: ClassVar[str] = ""
    display_name: ClassVar[str] = ""
    category: ClassVar[ConnectorCategory] = ConnectorCategory.CUSTOM
    description: ClassVar[str] = ""
    protocol: ClassVar[ProtocolType] = ProtocolType.REST
    base_url: ClassVar[Optional[str]] = None

    # Overridden by subclasses to declare auth, rate limits
    _auth_providers_config: ClassVar[list[Any]] = []
    _rate_limit_config: ClassVar[Optional[RateLimitSpec]] = None

    def __init__(
        self,
        *,
        credentials: Any = None,
        keystore: Any = None,
        middleware: Optional[list[Any]] = None,
        storage: Any = None,
        tenant_id: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        """Initialise a connector instance.

        Args:
            credentials: Credentials for authenticating with the tool API.
                Can be a CredentialSet, dict, or string path.
            keystore: KeyStore instance for credential persistence.
            middleware: Additional middleware to add to the pipeline.
            storage: StorageBackend for file handling.
            tenant_id: Tenant identifier for multi-tenant deployments.
            base_url: Override the class-level base URL (useful for
                testing or on-premise deployments).
            timeout: Default request timeout in seconds.
            max_retries: Maximum retry attempts for transient failures.
        """
        self._credentials = credentials
        self._keystore = keystore
        self._user_middleware = middleware or []
        self._storage = storage
        self._tenant_id = tenant_id
        self._base_url = base_url or self.__class__.base_url
        self._timeout = timeout
        self._max_retries = max_retries
        self._is_setup = False

        # Install sync wrappers for all @action methods
        self._install_sync_wrappers()

    def _install_sync_wrappers(self) -> None:
        """Create sync entry points for all @action methods.

        For each ``async def list_emails(...)``, creates a sync
        ``list_emails(...)`` that wraps the async version.
        """
        for attr_name in dir(self.__class__):
            method = getattr(self.__class__, attr_name, None)
            if method is None:
                continue
            if not hasattr(method, "__action_meta__"):
                continue
            if hasattr(method, "__is_sync_wrapper__"):
                continue

            # The async method has a __sync_wrapper__ attached by @action
            sync_wrapper = getattr(method, "__sync_wrapper__", None)
            if sync_wrapper is not None:
                # Bind the sync wrapper to this instance
                bound = sync_wrapper.__get__(self, self.__class__)
                # Store as instance attribute (overrides class method lookup)
                # The async version is still accessible as alist_*
                setattr(self, attr_name, bound)
                # Also make the async version accessible as a{name}
                async_bound = method.__get__(self, self.__class__)
                setattr(self, f"a{attr_name}", async_bound)

    # --- Lifecycle ---

    async def _setup(self) -> None:
        """Called once after init. Override to initialise SDK clients.

        This is where connector authors should create their API client,
        validate credentials, etc.
        """

    async def _teardown(self) -> None:
        """Called on context manager exit. Override to clean up resources."""

    async def _health_check(self) -> HealthStatus:
        """Verify connectivity to the tool API.

        Override to implement a lightweight health probe (e.g., call a
        ``/me`` endpoint).

        Returns:
            HealthStatus indicating whether the connector is healthy.
        """
        return HealthStatus(healthy=True, message="No health check implemented")

    async def __aenter__(self) -> "BaseConnector":
        """Async context manager entry."""
        await self._setup()
        self._is_setup = True
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Any,
    ) -> None:
        """Async context manager exit."""
        await self._teardown()
        self._is_setup = False

    def __enter__(self) -> "BaseConnector":
        """Sync context manager entry."""
        run_sync(self._setup())
        self._is_setup = True
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Any,
    ) -> None:
        """Sync context manager exit."""
        run_sync(self._teardown())
        self._is_setup = False

    # --- Schema introspection (no instantiation needed) ---

    @classmethod
    def get_actions(cls) -> dict[str, ActionMeta]:
        """Extract all action metadata from this connector.

        Returns:
            Dict mapping action name to ActionMeta.
        """
        return get_actions(cls)

    @classmethod
    def get_spec(cls) -> ConnectorSpec:
        """Extract the full connector specification.

        Used by the serve layer, codegen, documentation, and
        conformance tests.  Does not require instantiation.

        Returns:
            A ConnectorSpec describing this connector's full interface.
        """
        actions_meta = cls.get_actions()

        # Convert ActionMeta → ActionSpec
        action_specs: dict[str, ActionSpec] = {}
        for name, meta in actions_meta.items():
            action_specs[name] = ActionSpec(
                name=meta.name,
                description=meta.description,
                parameters=meta.parameters,
                input_schema=meta.input_schema,
                output_schema=meta.output_schema,
                return_type=meta.return_type_name,
                requires_scope=meta.requires_scope,
                dangerous=meta.dangerous,
                idempotent=meta.idempotent,
                pagination=meta.pagination,
                tags=meta.tags,
                rate_limit_weight=meta.rate_limit_weight,
            )

        return ConnectorSpec(
            name=cls.name,
            display_name=cls.display_name or cls.name.title(),
            category=cls.category,
            description=cls.description or cls.__doc__ or "",
            protocol=cls.protocol,
            base_url=cls.base_url,
            actions=action_specs,
            rate_limits=cls._rate_limit_config or RateLimitSpec(),
        )

    def __repr__(self) -> str:
        tenant = f", tenant={self._tenant_id}" if self._tenant_id else ""
        return f"<{self.__class__.__name__}(name={self.name!r}{tenant})>"
