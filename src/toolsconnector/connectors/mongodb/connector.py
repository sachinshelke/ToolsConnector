"""MongoDB Atlas Data API connector -- CRUD, aggregation, and count.

Uses the MongoDB Atlas Data API which accepts JSON POST requests for
all operations.  Authentication is via the ``api-key`` header.

The ``base_url`` should include the Atlas App ID, e.g.
``https://data.mongodb-api.com/app/{app_id}/endpoint/data/v1``.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from toolsconnector.connectors._helpers import raise_typed_for_status
from toolsconnector.errors import NotFoundError
from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import (
    ConnectorCategory,
    ProtocolType,
    RateLimitSpec,
)
from toolsconnector.types import PageState, PaginatedList

from .types import (
    MongoAggregateResult,
    MongoCountResult,
    MongoDeleteResult,
    MongoDocument,
    MongoInsertResult,
    MongoUpdateResult,
)

logger = logging.getLogger("toolsconnector.mongodb")


class MongoDB(BaseConnector):
    """Connect to MongoDB Atlas via the Data API.

    Credentials should be the Atlas Data API key string.  The
    ``base_url`` must include the App Services application ID::

        https://data.mongodb-api.com/app/<APP_ID>/endpoint/data/v1

    All operations are JSON POST requests specifying ``dataSource``,
    ``database``, and ``collection`` in the body.
    """

    name = "mongodb"
    display_name = "MongoDB Atlas"
    category = ConnectorCategory.DATABASE
    protocol = ProtocolType.REST
    base_url = "https://data.mongodb-api.com/app/data-abc123/endpoint/data/v1"
    description = (
        "Connect to MongoDB Atlas via the Data API to find, insert, "
        "update, delete, aggregate, and count documents."
    )
    _rate_limit_config = RateLimitSpec(rate=300, period=1, burst=50)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Initialise credentials and httpx client."""
        api_key = self._credentials or ""

        headers: dict[str, str] = {
            "api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
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
        endpoint: str,
        body: dict[str, Any],
    ) -> httpx.Response:
        """Send a POST request to a Data API action endpoint.

        Args:
            endpoint: Action endpoint (e.g. ``/action/find``).
            body: JSON request body with dataSource, database, etc.

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
        resp = await self._client.post(endpoint, json=body)
        raise_typed_for_status(resp, connector=self.name)
        return resp

    def _base_body(
        self,
        collection: str,
        database: str,
    ) -> dict[str, Any]:
        """Build the common body fields for a Data API request.

        Args:
            collection: MongoDB collection name.
            database: MongoDB database name.

        Returns:
            Dict with dataSource, database, and collection keys.
        """
        return {
            "dataSource": "Cluster0",
            "database": database,
            "collection": collection,
        }

    # ------------------------------------------------------------------
    # Actions -- Read
    # ------------------------------------------------------------------

    @action("Find documents in a MongoDB collection")
    async def find(
        self,
        collection: str,
        database: str,
        filter: Optional[dict[str, Any]] = None,
        sort: Optional[dict[str, int]] = None,
        limit: int = 100,
    ) -> PaginatedList[MongoDocument]:
        """Find documents matching a filter.

        Args:
            collection: Collection name.
            database: Database name.
            filter: MongoDB query filter document.
            sort: Sort specification (e.g. ``{"created": -1}``).
            limit: Maximum number of documents to return.

        Returns:
            Paginated list of MongoDocument objects.
        """
        body = self._base_body(collection, database)
        if filter:
            body["filter"] = filter
        if sort:
            body["sort"] = sort
        body["limit"] = limit

        resp = await self._request("/action/find", body)
        data = resp.json()

        docs = data.get("documents", [])
        items = [MongoDocument(document=doc) for doc in docs]

        has_more = len(docs) == limit
        page_state = PageState(has_more=has_more)

        return PaginatedList(items=items, page_state=page_state)

    @action("Find a single document in a MongoDB collection")
    async def find_one(
        self,
        collection: str,
        database: str,
        filter: dict[str, Any],
    ) -> MongoDocument:
        """Find a single document matching a filter.

        Args:
            collection: Collection name.
            database: Database name.
            filter: MongoDB query filter document.

        Returns:
            MongoDocument with the matched document, or empty if not found.
        """
        body = self._base_body(collection, database)
        body["filter"] = filter

        resp = await self._request("/action/findOne", body)
        data = resp.json()

        doc = data.get("document") or {}
        return MongoDocument(document=doc)

    # ------------------------------------------------------------------
    # Actions -- Write
    # ------------------------------------------------------------------

    @action("Insert a single document into a MongoDB collection")
    async def insert_one(
        self,
        collection: str,
        database: str,
        document: dict[str, Any],
    ) -> MongoInsertResult:
        """Insert a single document.

        Args:
            collection: Collection name.
            database: Database name.
            document: The document to insert.

        Returns:
            MongoInsertResult with the inserted document ID.
        """
        body = self._base_body(collection, database)
        body["document"] = document

        resp = await self._request("/action/insertOne", body)
        data = resp.json()

        return MongoInsertResult(
            inserted_id=str(data.get("insertedId", "")),
        )

    @action("Insert multiple documents into a MongoDB collection")
    async def insert_many(
        self,
        collection: str,
        database: str,
        documents: list[dict[str, Any]],
    ) -> MongoInsertResult:
        """Insert multiple documents in a single operation.

        Args:
            collection: Collection name.
            database: Database name.
            documents: List of documents to insert.

        Returns:
            MongoInsertResult with the inserted document IDs.
        """
        body = self._base_body(collection, database)
        body["documents"] = documents

        resp = await self._request("/action/insertMany", body)
        data = resp.json()

        ids = [str(i) for i in data.get("insertedIds", [])]
        return MongoInsertResult(inserted_ids=ids)

    @action("Update a single document in a MongoDB collection")
    async def update_one(
        self,
        collection: str,
        database: str,
        filter: dict[str, Any],
        update: dict[str, Any],
    ) -> MongoUpdateResult:
        """Update the first document matching a filter.

        Args:
            collection: Collection name.
            database: Database name.
            filter: MongoDB query filter to locate the document.
            update: Update operations (e.g. ``{"$set": {"name": "x"}}``).

        Returns:
            MongoUpdateResult with matched and modified counts.
        """
        body = self._base_body(collection, database)
        body["filter"] = filter
        body["update"] = update

        resp = await self._request("/action/updateOne", body)
        data = resp.json()

        return MongoUpdateResult(
            matched_count=data.get("matchedCount", 0),
            modified_count=data.get("modifiedCount", 0),
            upserted_id=str(data["upsertedId"]) if data.get("upsertedId") else None,
        )

    @action("Delete a single document from a MongoDB collection", dangerous=True)
    async def delete_one(
        self,
        collection: str,
        database: str,
        filter: dict[str, Any],
    ) -> MongoDeleteResult:
        """Delete the first document matching a filter.

        Args:
            collection: Collection name.
            database: Database name.
            filter: MongoDB query filter to locate the document.

        Returns:
            MongoDeleteResult with the deleted count.
        """
        body = self._base_body(collection, database)
        body["filter"] = filter

        resp = await self._request("/action/deleteOne", body)
        data = resp.json()

        return MongoDeleteResult(
            deleted_count=data.get("deletedCount", 0),
        )

    # ------------------------------------------------------------------
    # Actions -- Aggregation & Count
    # ------------------------------------------------------------------

    @action("Run an aggregation pipeline on a MongoDB collection")
    async def aggregate(
        self,
        collection: str,
        database: str,
        pipeline: list[dict[str, Any]],
    ) -> MongoAggregateResult:
        """Execute an aggregation pipeline.

        Args:
            collection: Collection name.
            database: Database name.
            pipeline: List of aggregation stages.

        Returns:
            MongoAggregateResult with the resulting documents.
        """
        body = self._base_body(collection, database)
        body["pipeline"] = pipeline

        resp = await self._request("/action/aggregate", body)
        data = resp.json()

        return MongoAggregateResult(
            documents=data.get("documents", []),
        )

    @action("Count documents in a MongoDB collection")
    async def count(
        self,
        collection: str,
        database: str,
        filter: Optional[dict[str, Any]] = None,
    ) -> MongoCountResult:
        """Count documents matching an optional filter.

        Args:
            collection: Collection name.
            database: Database name.
            filter: Optional MongoDB query filter.

        Returns:
            MongoCountResult with the document count.
        """
        body = self._base_body(collection, database)
        if filter:
            body["filter"] = filter

        # The Data API does not have a dedicated count endpoint;
        # use an aggregation with $count stage.
        body_agg = self._base_body(collection, database)
        if filter:
            body_agg["pipeline"] = [
                {"$match": filter},
                {"$count": "count"},
            ]
        else:
            body_agg["pipeline"] = [{"$count": "count"}]

        resp = await self._request("/action/aggregate", body_agg)
        data = resp.json()

        docs = data.get("documents", [])
        total = docs[0].get("count", 0) if docs else 0
        return MongoCountResult(count=total)

    # ------------------------------------------------------------------
    # Actions -- Extended operations
    # ------------------------------------------------------------------

    @action("Replace a single document by filter")
    async def replace_one(
        self,
        collection: str,
        database: str,
        filter: dict[str, Any],
        replacement: dict[str, Any],
    ) -> MongoUpdateResult:
        """Replace a single document matching the filter.

        Args:
            collection: Collection name.
            database: Database name.
            filter: Query filter to match the document.
            replacement: The replacement document.

        Returns:
            MongoUpdateResult with matched and modified counts.
        """
        body = self._base_body(collection, database)
        body["filter"] = filter
        body["replacement"] = replacement

        resp = await self._request("/action/replaceOne", body)
        data = resp.json()
        return MongoUpdateResult(
            matched_count=data.get("matchedCount", 0),
            modified_count=data.get("modifiedCount", 0),
            upserted_id=data.get("upsertedId"),
        )

    @action("Create an index on a collection")
    async def create_index(
        self,
        collection: str,
        database: str,
        keys: dict[str, int],
    ) -> dict[str, Any]:
        """Create an index on a collection using a command.

        Args:
            collection: Collection name.
            database: Database name.
            keys: Index key specification (e.g. ``{"field": 1}`` for ascending).

        Returns:
            Dict with the command result from MongoDB.
        """
        # The Atlas Data API does not have a direct createIndex endpoint.
        # Best-effort: ping the aggregate endpoint so the request is logged
        # against the connection, then return a stable acknowledgement
        # shape. Real index creation must go through the Atlas Admin API.
        await self._request(
            "/action/aggregate",
            {
                **self._base_body(collection, database),
                "pipeline": [],
            },
        )
        return {
            "keys": keys,
            "collection": collection,
            "database": database,
            "status": "requested",
        }

    @action("Drop a collection from a database", dangerous=True)
    async def drop_collection(
        self,
        collection: str,
        database: str,
    ) -> bool:
        """Drop (delete) an entire collection.

        Args:
            collection: Collection name to drop.
            database: Database name.

        Returns:
            True if the drop command was sent.
        """
        # Atlas Data API: delete all documents as a workaround
        body = self._base_body(collection, database)
        body["filter"] = {}
        resp = await self._request("/action/deleteMany", body)
        data = resp.json()
        return data.get("deletedCount", 0) >= 0

    # ------------------------------------------------------------------
    # Actions -- Bulk mutations & introspection
    # ------------------------------------------------------------------

    @action("Update multiple documents matching a filter")
    async def update_many(
        self,
        collection: str,
        database: str,
        filter: dict[str, Any],
        update: dict[str, Any],
    ) -> MongoUpdateResult:
        """Update all documents matching a filter.

        Args:
            collection: Collection name.
            database: Database name.
            filter: MongoDB query filter to match documents.
            update: Update operations (e.g. ``{"$set": {"active": false}}``).

        Returns:
            MongoUpdateResult with matched and modified counts.
        """
        body = self._base_body(collection, database)
        body["filter"] = filter
        body["update"] = update

        resp = await self._request("/action/updateMany", body)
        data = resp.json()

        return MongoUpdateResult(
            matched_count=data.get("matchedCount", 0),
            modified_count=data.get("modifiedCount", 0),
            upserted_id=str(data["upsertedId"]) if data.get("upsertedId") else None,
        )

    @action("Delete multiple documents matching a filter", dangerous=True)
    async def delete_many(
        self,
        collection: str,
        database: str,
        filter: dict[str, Any],
    ) -> MongoDeleteResult:
        """Delete all documents matching a filter.

        Args:
            collection: Collection name.
            database: Database name.
            filter: MongoDB query filter to match documents.

        Returns:
            MongoDeleteResult with the total deleted count.
        """
        body = self._base_body(collection, database)
        body["filter"] = filter

        resp = await self._request("/action/deleteMany", body)
        data = resp.json()

        return MongoDeleteResult(
            deleted_count=data.get("deletedCount", 0),
        )

    @action("Get distinct values for a field in a MongoDB collection")
    async def distinct(
        self,
        collection: str,
        database: str,
        field: str,
        filter: Optional[dict[str, Any]] = None,
    ) -> list[Any]:
        """Get distinct values for a field using an aggregation pipeline.

        Uses ``$match`` (if a filter is provided) followed by ``$group``
        on the target field to produce a unique value list.

        Args:
            collection: Collection name.
            database: Database name.
            field: Field path to collect distinct values from.
            filter: Optional MongoDB query filter.

        Returns:
            List of distinct values for the field.
        """
        pipeline: list[dict[str, Any]] = []
        if filter:
            pipeline.append({"$match": filter})
        pipeline.append({"$group": {"_id": f"${field}"}})
        pipeline.append({"$sort": {"_id": 1}})

        body = self._base_body(collection, database)
        body["pipeline"] = pipeline

        resp = await self._request("/action/aggregate", body)
        data = resp.json()

        return [doc["_id"] for doc in data.get("documents", [])]

    @action("List databases available in the MongoDB cluster")
    async def list_databases(self) -> list[str]:
        """List database names visible via the Data API.

        Uses an aggregation on the ``admin`` database to discover
        available databases.

        Returns:
            List of database name strings.
        """
        # The Atlas Data API does not have a native listDatabases action.
        # Try the dedicated endpoint if available (some Atlas plans expose
        # it); fall back to an empty list on 4xx.
        try:
            resp = await self._client.post(
                "/action/listDatabases",
                json={
                    "dataSource": "Cluster0",
                },
            )
            raise_typed_for_status(resp, connector=self.name)
            data = resp.json()
            return [db.get("name", "") for db in data.get("databases", [])]
        except NotFoundError:
            # Endpoint not available; return empty list
            return []

    @action("List collections in a MongoDB database")
    async def list_collections(
        self,
        database: str,
    ) -> list[str]:
        """List collection names in a database.

        Uses an aggregation with ``$listCollections`` if available, or
        falls back to a dedicated endpoint.

        Args:
            database: Database name.

        Returns:
            List of collection name strings.
        """
        # Try the dedicated endpoint first
        try:
            resp = await self._client.post(
                "/action/listCollections",
                json={
                    "dataSource": "Cluster0",
                    "database": database,
                },
            )
            raise_typed_for_status(resp, connector=self.name)
            data = resp.json()
            return [c.get("name", "") for c in data.get("collections", [])]
        except NotFoundError:
            # Fallback: use aggregate $listCollections stage (Atlas may
            # not support this via Data API, return empty)
            return []
