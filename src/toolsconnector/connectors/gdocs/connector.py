"""Google Docs connector -- manage documents via the Docs API v1.

Uses httpx for direct HTTP calls against the Google Docs REST API.
Expects an OAuth 2.0 access token passed as ``credentials``.
"""

from __future__ import annotations

from typing import Any, Optional

import httpx

from toolsconnector.connectors._helpers import raise_typed_for_status
from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import ConnectorCategory, ProtocolType, RateLimitSpec

from .types import BatchUpdateResponse, Document


def _extract_plain_text(body: dict[str, Any]) -> str:
    """Extract plain text from a Google Docs body content structure.

    Walks the structural elements in the document body and concatenates
    all text runs into a single plain-text string.

    Args:
        body: The ``body`` dict from a Docs API document resource.

    Returns:
        Concatenated plain text from all paragraphs.
    """
    parts: list[str] = []
    for element in body.get("content", []):
        paragraph = element.get("paragraph")
        if paragraph is None:
            # Handle tables and other structural elements
            table = element.get("table")
            if table:
                for row in table.get("tableRows", []):
                    for cell in row.get("tableCells", []):
                        for cell_element in cell.get("content", []):
                            cell_para = cell_element.get("paragraph")
                            if cell_para:
                                for text_elem in cell_para.get("elements", []):
                                    text_run = text_elem.get("textRun")
                                    if text_run:
                                        parts.append(text_run.get("content", ""))
            continue
        for text_elem in paragraph.get("elements", []):
            text_run = text_elem.get("textRun")
            if text_run:
                parts.append(text_run.get("content", ""))
    return "".join(parts)


def _parse_document(data: dict[str, Any], include_body: bool = False) -> Document:
    """Parse a Docs API document resource into a Document model.

    Args:
        data: Raw JSON dict from the Docs API.
        include_body: Whether to extract and include the body text.

    Returns:
        Populated Document instance.
    """
    body_text: Optional[str] = None
    if include_body:
        body = data.get("body", {})
        body_text = _extract_plain_text(body)

    return Document(
        id=data.get("documentId", ""),
        title=data.get("title", ""),
        body_text=body_text,
        revision_id=data.get("revisionId"),
    )


class GoogleDocs(BaseConnector):
    """Connect to Google Docs to manage documents.

    Supports OAuth 2.0 authentication. Pass an access token as
    ``credentials`` when instantiating. Uses the Docs REST API v1
    via direct httpx calls.
    """

    name = "gdocs"
    display_name = "Google Docs"
    category = ConnectorCategory.PRODUCTIVITY
    protocol = ProtocolType.REST
    base_url = "https://docs.googleapis.com/v1"
    description = "Connect to Google Docs to create and manage documents."
    _rate_limit_config = RateLimitSpec(rate=300, period=60, burst=60)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_headers(self) -> dict[str, str]:
        """Build authorization headers for Docs API requests.

        Returns:
            Dict with Authorization bearer header.
        """
        return {"Authorization": f"Bearer {self._credentials}"}

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """Execute an authenticated HTTP request against the Docs API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE).
            path: API path relative to base_url.
            **kwargs: Additional keyword arguments passed to httpx.

        Returns:
            Parsed JSON response as a dict.

        Raises:
            httpx.HTTPStatusError: If the API returns a non-2xx status.
        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.request(
                method,
                f"{self._base_url}{path}",
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

    @action("Get a document by ID", requires_scope="read")
    async def get_document(self, document_id: str) -> Document:
        """Retrieve a Google Docs document with metadata.

        Returns document metadata without the full body text. Use
        ``get_document_text`` to also retrieve the plain-text content.

        Args:
            document_id: The ID of the document to retrieve.

        Returns:
            Document object with metadata (title, revision ID).
        """
        data = await self._request("GET", f"/documents/{document_id}")
        return _parse_document(data, include_body=False)

    @action("Create a new document", requires_scope="write", dangerous=True)
    async def create_document(self, title: str) -> Document:
        """Create a new empty Google Docs document.

        Args:
            title: Title for the new document.

        Returns:
            The created Document object.
        """
        body: dict[str, Any] = {"title": title}
        data = await self._request("POST", "/documents", json=body)
        return _parse_document(data, include_body=False)

    @action("Batch update a document", requires_scope="write", dangerous=True)
    async def batch_update(
        self,
        document_id: str,
        requests: list[dict[str, Any]],
    ) -> BatchUpdateResponse:
        """Apply a list of update requests to a document.

        This is the general-purpose mutation endpoint for Google Docs.
        Each request dict should follow the Docs API ``Request`` format
        (e.g., ``insertText``, ``deleteContentRange``, ``createParagraphBullets``).

        Args:
            document_id: The ID of the document to update.
            requests: List of Docs API request objects. See
                `Google Docs API reference <https://developers.google.com/docs/api/reference/rest/v1/documents/batchUpdate>`_
                for the full request specification.

        Returns:
            BatchUpdateResponse with the document ID and reply list.
        """
        body: dict[str, Any] = {"requests": requests}
        data = await self._request(
            "POST",
            f"/documents/{document_id}:batchUpdate",
            json=body,
        )
        return BatchUpdateResponse(
            document_id=data.get("documentId", document_id),
            replies=data.get("replies", []),
        )

    @action("Insert text into a document", requires_scope="write", dangerous=True)
    async def insert_text(
        self,
        document_id: str,
        text: str,
        index: Optional[int] = None,
    ) -> BatchUpdateResponse:
        """Insert text at a specific position in a document.

        This is a convenience wrapper around ``batch_update`` that
        constructs an ``insertText`` request.

        Args:
            document_id: The ID of the document.
            text: The text content to insert.
            index: The zero-based character index to insert at. If
                omitted, defaults to index 1 (start of document body,
                after the implicit newline).

        Returns:
            BatchUpdateResponse from the underlying batch update.
        """
        insert_index = index if index is not None else 1
        requests: list[dict[str, Any]] = [
            {
                "insertText": {
                    "location": {"index": insert_index},
                    "text": text,
                },
            },
        ]
        return await self.batch_update(document_id, requests)

    @action("Extract plain text from a document", requires_scope="read")
    async def get_document_text(self, document_id: str) -> str:
        """Retrieve the full plain-text content of a document.

        Fetches the document and walks its body structure to extract
        all text runs into a single concatenated string.

        Args:
            document_id: The ID of the document.

        Returns:
            The plain-text content of the document.
        """
        data = await self._request("GET", f"/documents/{document_id}")
        doc = _parse_document(data, include_body=True)
        return doc.body_text or ""
