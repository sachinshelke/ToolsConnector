"""Firebase Firestore connector -- documents, queries, and batch writes.

Uses the Firestore REST API v1 with Google OAuth Bearer token
authentication.  Firestore values use a special type-descriptor
encoding (e.g. ``{"stringValue": "hello"}``) which is handled
transparently by the encode/decode helpers.
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
    FirestoreBatchWriteResult,
    FirestoreCollection,
    FirestoreDocument,
)

logger = logging.getLogger("toolsconnector.firestore")


# ---------------------------------------------------------------------------
# Value encoding / decoding helpers
# ---------------------------------------------------------------------------


def _encode_value(value: Any) -> dict[str, Any]:
    """Encode a Python value into Firestore's type-descriptor format.

    Args:
        value: Python-native value to encode.

    Returns:
        Dict with the appropriate Firestore type key.
    """
    if value is None:
        return {"nullValue": None}
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int):
        return {"integerValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, str):
        return {"stringValue": value}
    if isinstance(value, list):
        return {
            "arrayValue": {
                "values": [_encode_value(v) for v in value],
            },
        }
    if isinstance(value, dict):
        return {
            "mapValue": {
                "fields": {k: _encode_value(v) for k, v in value.items()},
            },
        }
    return {"stringValue": str(value)}


def _decode_value(fv: dict[str, Any]) -> Any:
    """Decode a Firestore type-descriptor into a Python-native value.

    Args:
        fv: Firestore value dict (e.g. ``{"stringValue": "hello"}``).

    Returns:
        Decoded Python value.
    """
    if "nullValue" in fv:
        return None
    if "booleanValue" in fv:
        return fv["booleanValue"]
    if "integerValue" in fv:
        return int(fv["integerValue"])
    if "doubleValue" in fv:
        return fv["doubleValue"]
    if "stringValue" in fv:
        return fv["stringValue"]
    if "timestampValue" in fv:
        return fv["timestampValue"]
    if "geoPointValue" in fv:
        return fv["geoPointValue"]
    if "referenceValue" in fv:
        return fv["referenceValue"]
    if "bytesValue" in fv:
        return fv["bytesValue"]
    if "arrayValue" in fv:
        values = fv["arrayValue"].get("values", [])
        return [_decode_value(v) for v in values]
    if "mapValue" in fv:
        fields = fv["mapValue"].get("fields", {})
        return {k: _decode_value(v) for k, v in fields.items()}
    return None


def _decode_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Decode a Firestore fields dict into plain Python values.

    Args:
        fields: Raw Firestore ``fields`` dict from a document.

    Returns:
        Dict of field names to decoded Python values.
    """
    return {k: _decode_value(v) for k, v in fields.items()}


def _encode_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Encode a plain Python dict into Firestore fields format.

    Args:
        fields: Dict of field names to Python values.

    Returns:
        Dict in Firestore type-descriptor format.
    """
    return {k: _encode_value(v) for k, v in fields.items()}


def _parse_document(doc: dict[str, Any]) -> FirestoreDocument:
    """Parse a raw Firestore document JSON into a FirestoreDocument.

    Args:
        doc: Raw document dict from the API response.

    Returns:
        FirestoreDocument with decoded fields.
    """
    name = doc.get("name", "")
    doc_id = name.rsplit("/", 1)[-1] if name else None

    return FirestoreDocument(
        name=name,
        document_id=doc_id,
        fields=_decode_fields(doc.get("fields", {})),
        create_time=doc.get("createTime"),
        update_time=doc.get("updateTime"),
    )


def _doc_path(project: str, collection: str, document_id: str) -> str:
    """Build the Firestore document resource path.

    Args:
        project: GCP project ID.
        collection: Collection name.
        document_id: Document ID.

    Returns:
        Full resource path string.
    """
    return f"/projects/{project}/databases/(default)/documents/{collection}/{document_id}"


def _collection_path(project: str, collection: str) -> str:
    """Build the Firestore collection resource path.

    Args:
        project: GCP project ID.
        collection: Collection name.

    Returns:
        Full resource path string.
    """
    return f"/projects/{project}/databases/(default)/documents/{collection}"


class Firestore(BaseConnector):
    """Connect to Firebase Firestore to manage documents and collections.

    Credentials should be a Google OAuth Bearer token string.
    """

    name = "firestore"
    display_name = "Firebase Firestore"
    category = ConnectorCategory.DATABASE
    protocol = ProtocolType.REST
    base_url = "https://firestore.googleapis.com/v1"
    description = (
        "Connect to Firebase Firestore to read, write, query, "
        "and batch-write documents in collections."
    )
    _rate_limit_config = RateLimitSpec(rate=300, period=1, burst=50)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Initialise the httpx client with Bearer auth."""
        token = self._credentials or ""

        headers: dict[str, str] = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        self._client = httpx.AsyncClient(
            base_url=self._base_url or self.__class__.base_url,
            headers=headers,
            timeout=self._timeout,
        )

    async def _teardown(self) -> None:
        """Close the httpx client."""
        if hasattr(self, "_client"):
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[Any] = None,
    ) -> httpx.Response:
        """Send an authenticated request to the Firestore REST API.

        Args:
            method: HTTP method.
            path: API path relative to base_url.
            params: Query parameters.
            json_body: JSON request body.

        Returns:
            httpx.Response object.

        Raises:
            toolsconnector.errors.APIError (subclass): On any non-2xx response.
                Maps to a typed exception by status: 401 -> InvalidCredentialsError
                or TokenExpiredError; 403 -> PermissionDeniedError; 404 -> NotFoundError;
                409 -> ConflictError; 400/422 -> ValidationError; 429 -> RateLimitError;
                5xx -> ServerError; other 4xx -> APIError. See
                toolsconnector.connectors._helpers.raise_typed_for_status for the full mapping.
        """
        kwargs: dict[str, Any] = {"method": method, "url": path}
        if params:
            kwargs["params"] = params
        if json_body is not None:
            kwargs["json"] = json_body

        resp = await self._client.request(**kwargs)
        raise_typed_for_status(resp, connector=self.name)
        return resp

    # ------------------------------------------------------------------
    # Actions -- Read
    # ------------------------------------------------------------------

    @action("Get a Firestore document by ID")
    async def get_document(
        self,
        project: str,
        collection: str,
        document_id: str,
    ) -> FirestoreDocument:
        """Retrieve a single document from a collection.

        Args:
            project: GCP project ID.
            collection: Collection name.
            document_id: Document ID.

        Returns:
            FirestoreDocument with decoded fields.
        """
        path = _doc_path(project, collection, document_id)
        resp = await self._request("GET", path)
        return _parse_document(resp.json())

    @action("List documents in a Firestore collection")
    async def list_documents(
        self,
        project: str,
        collection: str,
        limit: int = 100,
        page_token: Optional[str] = None,
    ) -> PaginatedList[FirestoreDocument]:
        """List documents in a collection with pagination.

        Args:
            project: GCP project ID.
            collection: Collection name.
            limit: Maximum documents per page.
            page_token: Token from a previous response for next page.

        Returns:
            Paginated list of FirestoreDocument objects.
        """
        path = _collection_path(project, collection)
        params: dict[str, Any] = {"pageSize": limit}
        if page_token:
            params["pageToken"] = page_token

        resp = await self._request("GET", path, params=params)
        data = resp.json()

        docs = data.get("documents", [])
        items = [_parse_document(d) for d in docs]

        next_token = data.get("nextPageToken")
        has_more = next_token is not None
        page_state = PageState(has_more=has_more, cursor=next_token)

        result = PaginatedList(items=items, page_state=page_state)
        result._fetch_next = (
            (
                lambda t=next_token: self.alist_documents(
                    project=project,
                    collection=collection,
                    limit=limit,
                    page_token=t,
                )
            )
            if has_more
            else None
        )
        return result

    @action("List collections in a Firestore project")
    async def list_collections(
        self,
        project: str,
    ) -> list[FirestoreCollection]:
        """List root-level collection IDs in a project.

        Args:
            project: GCP project ID.

        Returns:
            List of FirestoreCollection objects.
        """
        path = f"/projects/{project}/databases/(default)/documents:listCollectionIds"
        resp = await self._request("POST", path, json_body={})
        data = resp.json()

        return [FirestoreCollection(collection_id=cid) for cid in data.get("collectionIds", [])]

    # ------------------------------------------------------------------
    # Actions -- Write
    # ------------------------------------------------------------------

    @action("Create a document in a Firestore collection")
    async def create_document(
        self,
        project: str,
        collection: str,
        fields: dict[str, Any],
        document_id: Optional[str] = None,
    ) -> FirestoreDocument:
        """Create a new document in a collection.

        Args:
            project: GCP project ID.
            collection: Collection name.
            fields: Dict of field names to Python-native values.
            document_id: Optional document ID; auto-generated if omitted.

        Returns:
            FirestoreDocument with the created document data.
        """
        path = _collection_path(project, collection)
        params: dict[str, Any] = {}
        if document_id:
            params["documentId"] = document_id

        body = {"fields": _encode_fields(fields)}
        resp = await self._request(
            "POST",
            path,
            params=params,
            json_body=body,
        )
        return _parse_document(resp.json())

    @action("Update a Firestore document")
    async def update_document(
        self,
        project: str,
        collection: str,
        document_id: str,
        fields: dict[str, Any],
    ) -> FirestoreDocument:
        """Update an existing document (full replace of specified fields).

        Only the fields provided are updated; other fields are left
        unchanged via ``updateMask``.

        Args:
            project: GCP project ID.
            collection: Collection name.
            document_id: Document ID to update.
            fields: Dict of field names to new values.

        Returns:
            FirestoreDocument with the updated document.
        """
        path = _doc_path(project, collection, document_id)
        encoded = _encode_fields(fields)

        # httpx handles repeated query params via list values, so passing
        # the field-paths list directly produces ?updateMask.fieldPaths=a
        # &updateMask.fieldPaths=b... per the Firestore patch-mask spec.
        params: dict[str, Any] = {}
        field_paths = list(fields.keys())
        if field_paths:
            params["updateMask.fieldPaths"] = field_paths

        body = {"fields": encoded}
        resp = await self._request(
            "PATCH",
            path,
            params=params,
            json_body=body,
        )
        return _parse_document(resp.json())

    @action("Delete a Firestore document", dangerous=True)
    async def delete_document(
        self,
        project: str,
        collection: str,
        document_id: str,
    ) -> None:
        """Delete a document from a collection.

        Args:
            project: GCP project ID.
            collection: Collection name.
            document_id: Document ID to delete.
        """
        path = _doc_path(project, collection, document_id)
        await self._request("DELETE", path)

    # ------------------------------------------------------------------
    # Actions -- Query
    # ------------------------------------------------------------------

    @action("Run a structured query on a Firestore collection")
    async def query(
        self,
        project: str,
        collection: str,
        where: Optional[list[dict[str, Any]]] = None,
        order_by: Optional[list[dict[str, str]]] = None,
        limit: Optional[int] = None,
    ) -> list[FirestoreDocument]:
        """Run a structured query on a collection.

        Each ``where`` entry should be a dict with ``field``, ``op``
        (e.g. ``EQUAL``, ``LESS_THAN``), and ``value`` keys.

        Args:
            project: GCP project ID.
            collection: Collection name.
            where: List of field filter dicts.
            order_by: List of ``{"field": "name", "direction": "ASCENDING"}`` dicts.
            limit: Maximum number of documents to return.

        Returns:
            List of matching FirestoreDocument objects.
        """
        structured_query: dict[str, Any] = {
            "from": [{"collectionId": collection}],
        }

        if where:
            filters = []
            for w in where:
                filters.append(
                    {
                        "fieldFilter": {
                            "field": {"fieldPath": w["field"]},
                            "op": w.get("op", "EQUAL"),
                            "value": _encode_value(w.get("value")),
                        },
                    }
                )
            if len(filters) == 1:
                structured_query["where"] = filters[0]
            else:
                structured_query["where"] = {
                    "compositeFilter": {
                        "op": "AND",
                        "filters": filters,
                    },
                }

        if order_by:
            structured_query["orderBy"] = [
                {
                    "field": {"fieldPath": o["field"]},
                    "direction": o.get("direction", "ASCENDING"),
                }
                for o in order_by
            ]

        if limit is not None:
            structured_query["limit"] = limit

        path = f"/projects/{project}/databases/(default)/documents:runQuery"
        body = {"structuredQuery": structured_query}
        resp = await self._request("POST", path, json_body=body)
        data = resp.json()

        results: list[FirestoreDocument] = []
        for entry in data:
            doc = entry.get("document")
            if doc:
                results.append(_parse_document(doc))

        return results

    # ------------------------------------------------------------------
    # Actions -- Batch
    # ------------------------------------------------------------------

    @action("Execute a batch write in Firestore")
    async def batch_write(
        self,
        project: str,
        writes: list[dict[str, Any]],
    ) -> FirestoreBatchWriteResult:
        """Execute multiple writes atomically.

        Each write should be a dict with an ``update`` key containing
        ``name`` (full document path) and ``fields`` (Python-native
        values that will be encoded).

        Args:
            project: GCP project ID.
            writes: List of write operation dicts.

        Returns:
            FirestoreBatchWriteResult with status and write results.
        """
        encoded_writes = []
        for w in writes:
            ew: dict[str, Any] = {}
            if "update" in w:
                update = w["update"]
                ew["update"] = {
                    "name": update["name"],
                    "fields": _encode_fields(update.get("fields", {})),
                }
            if "delete" in w:
                ew["delete"] = w["delete"]
            encoded_writes.append(ew)

        path = f"/projects/{project}/databases/(default)/documents:batchWrite"
        body = {"writes": encoded_writes}
        resp = await self._request("POST", path, json_body=body)
        data = resp.json()

        return FirestoreBatchWriteResult(
            status=data.get("status", []),
            write_results=data.get("writeResults", []),
        )

    # ------------------------------------------------------------------
    # Actions -- Advanced operations
    # ------------------------------------------------------------------

    @action("Run a transaction with multiple operations")
    async def run_transaction(
        self,
        project: str,
        operations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Run a transaction that commits multiple writes atomically.

        Args:
            project: Google Cloud project ID.
            operations: List of write operation dicts. Each should have
                either ``"update"`` or ``"delete"`` keys.

        Returns:
            Dict with commit results including commit_time.
        """
        # Begin transaction
        begin_path = f"/projects/{project}/databases/(default)/documents:beginTransaction"
        begin_resp = await self._request("POST", begin_path, json_body={})
        begin_data = begin_resp.json()
        transaction_id = begin_data.get("transaction", "")

        # Build writes
        encoded_writes: list[dict[str, Any]] = []
        for op in operations:
            ew: dict[str, Any] = {}
            if "update" in op:
                update = op["update"]
                ew["update"] = {
                    "name": update["name"],
                    "fields": _encode_fields(update.get("fields", {})),
                }
            if "delete" in op:
                ew["delete"] = op["delete"]
            encoded_writes.append(ew)

        # Commit
        commit_path = f"/projects/{project}/databases/(default)/documents:commit"
        commit_body: dict[str, Any] = {
            "writes": encoded_writes,
            "transaction": transaction_id,
        }
        commit_resp = await self._request("POST", commit_path, json_body=commit_body)
        return commit_resp.json()

    @action("List indexes for a collection")
    async def list_indexes(
        self,
        project: str,
        collection: str,
    ) -> list[dict[str, Any]]:
        """List composite indexes for a Firestore collection.

        Args:
            project: Google Cloud project ID.
            collection: The collection group ID.

        Returns:
            List of index configuration dicts.
        """
        path = f"/projects/{project}/databases/(default)/collectionGroups/{collection}/indexes"
        resp = await self._request("GET", path)
        data = resp.json()
        return data.get("indexes", [])

    @action("Export documents from a collection")
    async def export_documents(
        self,
        project: str,
        collection: str,
    ) -> list[dict[str, Any]]:
        """Export all documents from a Firestore collection.

        Args:
            project: Google Cloud project ID.
            collection: The collection path.

        Returns:
            List of raw document dicts from the collection.
        """
        path = f"/projects/{project}/databases/(default)/documents/{collection}"
        resp = await self._request("GET", path)
        data = resp.json()
        documents = data.get("documents", [])
        return [
            {
                "name": doc.get("name", ""),
                "fields": doc.get("fields", {}),
                "createTime": doc.get("createTime"),
                "updateTime": doc.get("updateTime"),
            }
            for doc in documents
        ]

    # ------------------------------------------------------------------
    # Actions -- Partial updates, counting, and field access
    # ------------------------------------------------------------------

    @action("Update specific fields in a Firestore document")
    async def update_fields(
        self,
        project: str,
        collection: str,
        document_id: str,
        fields: dict[str, Any],
        update_mask: Optional[list[str]] = None,
    ) -> FirestoreDocument:
        """Update only the specified fields of a document.

        If ``update_mask`` is provided, only those field paths are
        written.  Otherwise the mask is derived from the ``fields``
        dict keys.

        Args:
            project: GCP project ID.
            collection: Collection name.
            document_id: Document ID to update.
            fields: Dict of field names to new Python-native values.
            update_mask: Explicit list of field paths to update.
                Defaults to the keys of ``fields``.

        Returns:
            FirestoreDocument with the updated document.
        """
        path = _doc_path(project, collection, document_id)
        encoded = _encode_fields(fields)

        mask_paths = update_mask if update_mask else list(fields.keys())
        params: dict[str, Any] = {"updateMask.fieldPaths": mask_paths}

        body = {"fields": encoded}
        resp = await self._request(
            "PATCH",
            path,
            params=params,
            json_body=body,
        )
        return _parse_document(resp.json())

    @action("Count documents in a Firestore collection")
    async def count_documents(
        self,
        project: str,
        collection: str,
        filter: Optional[list[dict[str, Any]]] = None,
    ) -> int:
        """Count documents in a collection using an aggregation query.

        Uses ``runAggregationQuery`` with a ``COUNT`` aggregation for
        an efficient server-side count.

        Args:
            project: GCP project ID.
            collection: Collection name.
            filter: Optional list of field filter dicts (same format as
                the ``query`` action's ``where`` parameter).

        Returns:
            Number of matching documents.
        """
        structured_query: dict[str, Any] = {
            "from": [{"collectionId": collection}],
        }

        if filter:
            filters = []
            for w in filter:
                filters.append(
                    {
                        "fieldFilter": {
                            "field": {"fieldPath": w["field"]},
                            "op": w.get("op", "EQUAL"),
                            "value": _encode_value(w.get("value")),
                        },
                    }
                )
            if len(filters) == 1:
                structured_query["where"] = filters[0]
            else:
                structured_query["where"] = {
                    "compositeFilter": {
                        "op": "AND",
                        "filters": filters,
                    },
                }

        path = f"/projects/{project}/databases/(default)/documents:runAggregationQuery"
        body: dict[str, Any] = {
            "structuredAggregationQuery": {
                "structuredQuery": structured_query,
                "aggregations": [
                    {
                        "alias": "count",
                        "count": {},
                    },
                ],
            },
        }

        resp = await self._request("POST", path, json_body=body)
        data = resp.json()

        # Response is a list of result entries
        results = data if isinstance(data, list) else [data]
        for entry in results:
            agg_result = entry.get("result", {}).get("aggregateFields", {})
            count_val = agg_result.get("count", {})
            if "integerValue" in count_val:
                return int(count_val["integerValue"])
        return 0

    @action("Create a collection group index in Firestore", dangerous=True)
    async def create_collection_group_index(
        self,
        project: str,
        collection_group: str,
        fields: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Create a composite index for a collection group.

        Each field dict should have ``fieldPath`` and ``order``
        (``ASCENDING`` or ``DESCENDING``) or ``arrayConfig``
        (``CONTAINS``) keys.

        Args:
            project: GCP project ID.
            collection_group: The collection group ID.
            fields: List of index field configurations.

        Returns:
            Dict with the created index metadata from the API.
        """
        index_fields = []
        for f in fields:
            entry: dict[str, str] = {"fieldPath": f["fieldPath"]}
            if "order" in f:
                entry["order"] = f["order"]
            elif "arrayConfig" in f:
                entry["arrayConfig"] = f["arrayConfig"]
            else:
                entry["order"] = "ASCENDING"
            index_fields.append(entry)

        path = (
            f"/projects/{project}/databases/(default)/collectionGroups/{collection_group}/indexes"
        )
        body: dict[str, Any] = {
            "queryScope": "COLLECTION_GROUP",
            "fields": index_fields,
        }

        resp = await self._request("POST", path, json_body=body)
        return resp.json()

    @action("Get a single field value from a Firestore document")
    async def get_document_field(
        self,
        project: str,
        collection: str,
        document_id: str,
        field_path: str,
    ) -> Any:
        """Retrieve a single field value from a document.

        Fetches the full document using a field mask to limit the
        response to the requested field, then returns the decoded value.

        Args:
            project: GCP project ID.
            collection: Collection name.
            document_id: Document ID.
            field_path: Dot-separated field path (e.g. ``"address.city"``).

        Returns:
            The decoded Python-native value of the field, or None if
            the field does not exist.
        """
        path = _doc_path(project, collection, document_id)
        params: dict[str, Any] = {"mask.fieldPaths": [field_path]}

        resp = await self._request("GET", path, params=params)
        doc = resp.json()

        raw_fields = doc.get("fields", {})
        # Navigate dotted path
        parts = field_path.split(".")
        current: Any = raw_fields
        for part in parts:
            if isinstance(current, dict):
                if part in current:
                    current = current[part]
                else:
                    return None
            else:
                return None

        # current should be a Firestore value descriptor
        if isinstance(current, dict):
            return _decode_value(current)
        return current

    # ------------------------------------------------------------------
    # Actions — Batch read
    # ------------------------------------------------------------------

    @action("Batch get multiple documents")
    async def batch_get(
        self,
        project: str,
        collection: str,
        document_ids: list[str],
        database: str = "(default)",
    ) -> list[FirestoreDocument]:
        """Retrieve multiple documents in a single request.

        More efficient than individual get_document calls.

        Args:
            project: Google Cloud project ID.
            collection: Collection name.
            document_ids: List of document IDs to retrieve.
            database: Database ID (default: '(default)').

        Returns:
            List of FirestoreDocument objects.
        """
        parent = f"projects/{project}/databases/{database}/documents"
        doc_names = [f"{parent}/{collection}/{doc_id}" for doc_id in document_ids]
        data = await self._request(
            "POST",
            f"projects/{project}/databases/{database}/documents:batchGet",
            json={"documents": doc_names},
        )
        results = []
        for item in data if isinstance(data, list) else [data]:
            found = item.get("found")
            if found:
                fields = found.get("fields", {})
                name = found.get("name", "")
                doc_id = name.rsplit("/", 1)[-1] if "/" in name else name
                decoded = {k: _decode_value(v) for k, v in fields.items()}
                results.append(
                    FirestoreDocument(
                        name=name,
                        document_id=doc_id,
                        fields=decoded,
                        create_time=found.get("createTime"),
                        update_time=found.get("updateTime"),
                    )
                )
        return results

    # ------------------------------------------------------------------
    # Actions — Index management
    # ------------------------------------------------------------------

    @action("Delete a composite index", dangerous=True)
    async def delete_index(
        self,
        project: str,
        database: str,
        index_id: str,
    ) -> None:
        """Delete a composite index.

        Args:
            project: Google Cloud project ID.
            database: Database ID (usually '(default)').
            index_id: The index ID to delete.
        """
        await self._request(
            "DELETE",
            f"projects/{project}/databases/{database}/collectionGroups/-/indexes/{index_id}",
        )
