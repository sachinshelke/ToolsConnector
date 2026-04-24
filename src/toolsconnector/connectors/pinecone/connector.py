"""Pinecone connector -- vector upsert, query, delete, and index management.

Uses httpx for direct HTTP calls against the Pinecone REST API.
Credentials format: ``api_key:index_host`` (colon-separated).
The index_host is the full host for a specific index (e.g., ``my-index-abc123.svc.us-east1-gcp.pinecone.io``).
The control plane (for list_indexes) uses ``https://api.pinecone.io``.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from toolsconnector.connectors._helpers import raise_typed_for_status
from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import (
    ConnectorCategory,
    ProtocolType,
    RateLimitSpec,
)
from toolsconnector.types import PageState, PaginatedList

from .types import (
    DeleteResult,
    NamespaceStats,
    PineconeCollection,
    PineconeFetchResult,
    PineconeIndex,
    PineconeMatch,
    PineconeQueryResult,
    PineconeStats,
    PineconeUpsertResult,
    PineconeVector,
    PineconeVectorListItem,
)

logger = logging.getLogger("toolsconnector.pinecone")

_CONTROL_PLANE_URL = "https://api.pinecone.io"


class Pinecone(BaseConnector):
    """Connect to Pinecone for vector database operations.

    Supports API key authentication. Pass credentials as a
    colon-separated string ``api_key:index_host`` when instantiating.
    The index host is the full hostname for a specific Pinecone index.

    Example:
        >>> pc = Pinecone(credentials="pk-abc123:my-index-xyz.svc.us-east1-gcp.pinecone.io")
    """

    name = "pinecone"
    display_name = "Pinecone"
    category = ConnectorCategory.AI_ML
    protocol = ProtocolType.REST
    base_url = "https://api.pinecone.io"
    description = (
        "Connect to Pinecone for vector database operations including "
        "upsert, query, fetch, delete, and index management."
    )
    _rate_limit_config = RateLimitSpec(rate=100, period=60, burst=30)

    # ------------------------------------------------------------------
    # Credential parsing
    # ------------------------------------------------------------------

    def _parse_credentials(self) -> tuple[str, str]:
        """Parse api_key and index_host from the credentials string.

        Returns:
            Tuple of (api_key, index_host).
        """
        creds = str(self._credentials)
        if ":" in creds:
            parts = creds.split(":", 1)
            return parts[0], parts[1]
        return creds, ""

    @property
    def _api_key(self) -> str:
        """Return the Pinecone API key."""
        return self._parse_credentials()[0]

    @property
    def _index_host(self) -> str:
        """Return the Pinecone index host URL."""
        host = self._parse_credentials()[1]
        if host and not host.startswith("https://"):
            return f"https://{host}"
        return host

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_headers(self) -> dict[str, str]:
        """Build authentication headers for Pinecone API requests.

        Returns:
            Dict with Api-Key header and content type.
        """
        return {
            "Api-Key": self._api_key,
            "Content-Type": "application/json",
        }

    async def _data_request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute an authenticated request against the index data plane.

        Args:
            method: HTTP method (GET, POST, DELETE, etc.).
            path: API path (e.g., '/vectors/upsert').
            **kwargs: Additional keyword arguments passed to httpx.

        Returns:
            Parsed JSON response as a dict.

        Raises:
            toolsconnector.errors.APIError (subclass): On any non-2xx response.
                Maps to a typed exception by status: 401 -> InvalidCredentialsError
                or TokenExpiredError; 403 -> PermissionDeniedError; 404 -> NotFoundError;
                409 -> ConflictError; 400/422 -> ValidationError; 429 -> RateLimitError;
                5xx -> ServerError; other 4xx -> APIError. See
                toolsconnector.connectors._helpers.raise_typed_for_status for the full mapping.

        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.request(
                method,
                f"{self._index_host}{path}",
                headers=self._get_headers(),
                **kwargs,
            )
            raise_typed_for_status(response, connector=self.name)
            if response.status_code == 204 or not response.content:
                return {}
            return response.json()

    async def _control_request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute an authenticated request against the control plane.

        Args:
            method: HTTP method (GET, POST, etc.).
            path: API path (e.g., '/indexes').
            **kwargs: Additional keyword arguments passed to httpx.

        Returns:
            Parsed JSON response as a dict.

        Raises:
            toolsconnector.errors.APIError (subclass): On any non-2xx response.
                Maps to a typed exception by status: 401 -> InvalidCredentialsError
                or TokenExpiredError; 403 -> PermissionDeniedError; 404 -> NotFoundError;
                409 -> ConflictError; 400/422 -> ValidationError; 429 -> RateLimitError;
                5xx -> ServerError; other 4xx -> APIError. See
                toolsconnector.connectors._helpers.raise_typed_for_status for the full mapping.

        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.request(
                method,
                f"{_CONTROL_PLANE_URL}{path}",
                headers=self._get_headers(),
                **kwargs,
            )
            raise_typed_for_status(response, connector=self.name)
            if response.status_code == 204 or not response.content:
                return {}
            return response.json()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    @action("Upsert vectors into the index")
    async def upsert(
        self,
        vectors: list[dict[str, Any]],
        namespace: Optional[str] = None,
    ) -> PineconeUpsertResult:
        """Upsert vectors into the Pinecone index.

        Args:
            vectors: List of vector dicts, each with 'id', 'values', and optional 'metadata'.
            namespace: Target namespace for the vectors.

        Returns:
            PineconeUpsertResult with the count of upserted vectors.
        """
        payload: dict[str, Any] = {"vectors": vectors}
        if namespace is not None:
            payload["namespace"] = namespace

        data = await self._data_request("POST", "/vectors/upsert", json=payload)

        return PineconeUpsertResult(
            upserted_count=data.get("upsertedCount", 0),
        )

    @action("Query vectors by similarity")
    async def query(
        self,
        vector: list[float],
        top_k: Optional[int] = None,
        namespace: Optional[str] = None,
        filter: Optional[dict[str, Any]] = None,
        include_metadata: Optional[bool] = None,
    ) -> PineconeQueryResult:
        """Query the index for vectors similar to the given vector.

        Args:
            vector: The query vector.
            top_k: Number of top results to return (default: 10).
            namespace: Namespace to query within.
            filter: Metadata filter expression.
            include_metadata: Whether to include metadata in results.

        Returns:
            PineconeQueryResult with matching vectors and scores.
        """
        payload: dict[str, Any] = {
            "vector": vector,
            "topK": top_k or 10,
        }
        if namespace is not None:
            payload["namespace"] = namespace
        if filter is not None:
            payload["filter"] = filter
        if include_metadata is not None:
            payload["includeMetadata"] = include_metadata

        data = await self._data_request("POST", "/query", json=payload)

        matches = [
            PineconeMatch(
                id=m.get("id", ""),
                score=m.get("score", 0.0),
                values=m.get("values", []),
                metadata=m.get("metadata"),
                sparse_values=m.get("sparseValues"),
            )
            for m in data.get("matches", [])
        ]

        return PineconeQueryResult(
            namespace=data.get("namespace", ""),
            matches=matches,
            usage=data.get("usage"),
        )

    @action("Delete vectors from the index", dangerous=True)
    async def delete(
        self,
        ids: Optional[list[str]] = None,
        namespace: Optional[str] = None,
        delete_all: Optional[bool] = None,
    ) -> DeleteResult:
        """Delete vectors from the index by ID or delete all vectors.

        Args:
            ids: List of vector IDs to delete.
            namespace: Namespace to delete from.
            delete_all: If True, deletes all vectors in the namespace.

        Returns:
            DeleteResult confirming the deletion.

        Warning:
            Setting delete_all=True will permanently remove all vectors
            in the specified namespace.
        """
        payload: dict[str, Any] = {}
        if ids is not None:
            payload["ids"] = ids
        if namespace is not None:
            payload["namespace"] = namespace
        if delete_all is not None:
            payload["deleteAll"] = delete_all

        await self._data_request("POST", "/vectors/delete", json=payload)
        return DeleteResult(deleted=True)

    @action("Get index statistics", idempotent=True)
    async def describe_index_stats(self) -> PineconeStats:
        """Get statistics about the Pinecone index.

        Returns:
            PineconeStats with dimension, fullness, and per-namespace counts.
        """
        data = await self._data_request("POST", "/describe_index_stats", json={})

        namespaces = {
            ns_name: NamespaceStats(
                vector_count=ns_data.get("vectorCount", 0),
            )
            for ns_name, ns_data in data.get("namespaces", {}).items()
        }

        return PineconeStats(
            dimension=data.get("dimension", 0),
            index_fullness=data.get("indexFullness", 0.0),
            total_vector_count=data.get("totalVectorCount", 0),
            namespaces=namespaces,
        )

    @action("Fetch vectors by ID", idempotent=True)
    async def fetch(
        self,
        ids: list[str],
        namespace: Optional[str] = None,
    ) -> PineconeFetchResult:
        """Fetch vectors by their IDs.

        Args:
            ids: List of vector IDs to fetch.
            namespace: Namespace to fetch from.

        Returns:
            PineconeFetchResult with the requested vectors.
        """
        params: dict[str, Any] = {"ids": ids}
        if namespace is not None:
            params["namespace"] = namespace

        data = await self._data_request("GET", "/vectors/fetch", params=params)

        vectors = {
            vec_id: PineconeVector(
                id=vec_id,
                values=vec_data.get("values", []),
                metadata=vec_data.get("metadata"),
                sparse_values=vec_data.get("sparseValues"),
            )
            for vec_id, vec_data in data.get("vectors", {}).items()
        }

        return PineconeFetchResult(
            namespace=data.get("namespace", ""),
            vectors=vectors,
            usage=data.get("usage"),
        )

    @action("Update a vector's values or metadata")
    async def update(
        self,
        id: str,
        values: Optional[list[float]] = None,
        metadata: Optional[dict[str, Any]] = None,
        namespace: Optional[str] = None,
    ) -> DeleteResult:
        """Update a vector's values or metadata.

        Args:
            id: The ID of the vector to update.
            values: New vector values to set.
            metadata: New metadata to set or merge.
            namespace: Namespace of the vector.

        Returns:
            DeleteResult confirming the update (Pinecone returns empty on success).
        """
        payload: dict[str, Any] = {"id": id}
        if values is not None:
            payload["values"] = values
        if metadata is not None:
            payload["setMetadata"] = metadata
        if namespace is not None:
            payload["namespace"] = namespace

        await self._data_request("POST", "/vectors/update", json=payload)
        return DeleteResult(deleted=True)

    @action("List vector IDs in the index", idempotent=True)
    async def list_vectors(
        self,
        prefix: Optional[str] = None,
        namespace: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> PaginatedList[PineconeVectorListItem]:
        """List vector IDs in the index, optionally filtered by prefix.

        Args:
            prefix: ID prefix to filter vectors by.
            namespace: Namespace to list vectors from.
            limit: Maximum number of IDs to return.

        Returns:
            Paginated list of PineconeVectorListItem objects.
        """
        params: dict[str, Any] = {}
        if prefix is not None:
            params["prefix"] = prefix
        if namespace is not None:
            params["namespace"] = namespace
        if limit is not None:
            params["limit"] = limit

        data = await self._data_request("GET", "/vectors/list", params=params)

        vectors = [PineconeVectorListItem(id=v.get("id", "")) for v in data.get("vectors", [])]

        pagination = data.get("pagination")
        next_token = pagination.get("next") if pagination else None

        return PaginatedList(
            items=vectors,
            page_state=PageState(
                cursor=next_token,
                has_more=next_token is not None,
            ),
        )

    @action("List all indexes in the account", idempotent=True)
    async def list_indexes(self) -> list[PineconeIndex]:
        """List all Pinecone indexes in the account.

        Uses the control plane API at https://api.pinecone.io.

        Returns:
            List of PineconeIndex objects with index metadata.
        """
        data = await self._control_request("GET", "/indexes")

        return [
            PineconeIndex(
                name=idx.get("name", ""),
                dimension=idx.get("dimension", 0),
                metric=idx.get("metric", "cosine"),
                host=idx.get("host", ""),
                status=idx.get("status"),
                spec=idx.get("spec"),
            )
            for idx in data.get("indexes", [])
        ]

    # ------------------------------------------------------------------
    # Actions -- Index management (extended)
    # ------------------------------------------------------------------

    @action("Describe a Pinecone index", idempotent=True)
    async def describe_index(self, index_name: str) -> PineconeIndex:
        """Get detailed information about a specific Pinecone index.

        Uses the control plane API at https://api.pinecone.io.

        Args:
            index_name: Name of the index to describe.

        Returns:
            PineconeIndex with full index metadata, status, and spec.
        """
        data = await self._control_request("GET", f"/indexes/{index_name}")

        return PineconeIndex(
            name=data.get("name", ""),
            dimension=data.get("dimension", 0),
            metric=data.get("metric", "cosine"),
            host=data.get("host", ""),
            status=data.get("status"),
            spec=data.get("spec"),
        )

    @action("Create a new Pinecone index", dangerous=True)
    async def create_index(
        self,
        name: str,
        dimension: int,
        metric: Optional[str] = None,
    ) -> PineconeIndex:
        """Create a new Pinecone index.

        Creates a serverless index on AWS us-east-1 by default.

        Args:
            name: Name of the index.
            dimension: Vector dimension.
            metric: Distance metric (``cosine``, ``euclidean``, ``dotproduct``).

        Returns:
            The created PineconeIndex.
        """
        payload: dict[str, Any] = {
            "name": name,
            "dimension": dimension,
            "metric": metric or "cosine",
            "spec": {"serverless": {"cloud": "aws", "region": "us-east-1"}},
        }
        data = await self._control_request("POST", "/indexes", json=payload)
        return PineconeIndex(
            name=data.get("name", ""),
            dimension=data.get("dimension", dimension),
            metric=data.get("metric", metric or "cosine"),
            host=data.get("host", ""),
            status=data.get("status"),
            spec=data.get("spec"),
        )

    @action("Delete a Pinecone index", dangerous=True)
    async def delete_index(self, name: str) -> bool:
        """Delete a Pinecone index permanently.

        Args:
            name: Name of the index to delete.

        Returns:
            True if the index was deleted.
        """
        await self._control_request("DELETE", f"/indexes/{name}")
        return True

    @action("Configure an existing Pinecone index")
    async def configure_index(
        self,
        name: str,
        replicas: Optional[int] = None,
        pod_type: Optional[str] = None,
    ) -> PineconeIndex:
        """Update the configuration of a Pinecone index.

        Args:
            name: Name of the index to configure.
            replicas: Number of replicas.
            pod_type: Pod type (e.g. ``"p1.x1"``).

        Returns:
            The updated PineconeIndex.
        """
        spec: dict[str, Any] = {}
        if replicas is not None:
            spec["replicas"] = replicas
        if pod_type is not None:
            spec["pod_type"] = pod_type
        payload: dict[str, Any] = {"spec": {"pod": spec}}
        data = await self._control_request(
            "PATCH",
            f"/indexes/{name}",
            json=payload,
        )
        return PineconeIndex(
            name=data.get("name", ""),
            dimension=data.get("dimension", 0),
            metric=data.get("metric", "cosine"),
            host=data.get("host", ""),
            status=data.get("status"),
            spec=data.get("spec"),
        )

    # ------------------------------------------------------------------
    # Actions -- Collections
    # ------------------------------------------------------------------

    @action("List all collections", idempotent=True)
    async def list_collections(self) -> list[PineconeCollection]:
        """List all collections in the current project.

        Collections are static snapshots of an index. Note that
        serverless indexes do not support collections.

        Uses the control plane API at https://api.pinecone.io.

        Returns:
            List of PineconeCollection objects with collection metadata.
        """
        data = await self._control_request("GET", "/collections")

        return [
            PineconeCollection(
                name=c.get("name", ""),
                size=c.get("size"),
                status=c.get("status"),
                dimension=c.get("dimension"),
                vector_count=c.get("vector_count"),
                environment=c.get("environment"),
            )
            for c in data.get("collections", [])
        ]

    @action("Create a collection from an index", dangerous=True)
    async def create_collection(
        self,
        name: str,
        source_index: str,
    ) -> PineconeCollection:
        """Create a collection from an existing index.

        A collection is a static snapshot of an index that can be used
        to create new indexes. Serverless indexes do not support
        collections.

        Args:
            name: Name for the new collection.
            source_index: Name of the source index to snapshot.

        Returns:
            The created PineconeCollection.
        """
        payload: dict[str, Any] = {
            "name": name,
            "source": source_index,
        }
        data = await self._control_request("POST", "/collections", json=payload)
        return PineconeCollection(
            name=data.get("name", ""),
            size=data.get("size"),
            status=data.get("status"),
            dimension=data.get("dimension"),
            vector_count=data.get("vector_count"),
            environment=data.get("environment"),
        )

    @action("Delete a collection", dangerous=True)
    async def delete_collection(self, name: str) -> bool:
        """Permanently delete a collection.

        Args:
            name: Name of the collection to delete.

        Returns:
            True if the collection was deleted.
        """
        await self._control_request("DELETE", f"/collections/{name}")
        return True
