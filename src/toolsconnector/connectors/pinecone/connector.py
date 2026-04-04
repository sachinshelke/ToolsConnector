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
    PineconeFetchResult,
    PineconeIndex,
    PineconeMatch,
    PineconeQueryResult,
    PineconeStats,
    PineconeUpsertResult,
    PineconeVector,
    PineconeVectorList,
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
            httpx.HTTPStatusError: If the API returns a non-2xx status.
        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.request(
                method,
                f"{self._index_host}{path}",
                headers=self._get_headers(),
                **kwargs,
            )
            response.raise_for_status()
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
            httpx.HTTPStatusError: If the API returns a non-2xx status.
        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.request(
                method,
                f"{_CONTROL_PLANE_URL}{path}",
                headers=self._get_headers(),
                **kwargs,
            )
            response.raise_for_status()
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

        vectors = [
            PineconeVectorListItem(id=v.get("id", ""))
            for v in data.get("vectors", [])
        ]

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
