"""Google Sheets connector -- manage spreadsheets and cell data via the Sheets API v4.

Uses httpx for direct HTTP calls against the Google Sheets REST API.
Expects an OAuth 2.0 access token passed as ``credentials``.
"""

from __future__ import annotations

from typing import Any, Optional

import httpx

from toolsconnector.connectors._helpers import raise_typed_for_status
from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import ConnectorCategory, ProtocolType, RateLimitSpec

from .types import (
    AppendResult,
    BatchUpdateResult,
    ClearResult,
    Sheet,
    SheetValues,
    Spreadsheet,
    UpdateResult,
)


def _parse_sheet_properties(props: dict[str, Any]) -> Sheet:
    """Parse a sheet properties dict from the Sheets API.

    Args:
        props: Raw sheetProperties dict.

    Returns:
        Parsed Sheet model.
    """
    grid = props.get("gridProperties", {})
    return Sheet(
        id=props.get("sheetId", 0),
        title=props.get("title", ""),
        index=props.get("index", 0),
        row_count=grid.get("rowCount", 0),
        column_count=grid.get("columnCount", 0),
    )


def _parse_spreadsheet(data: dict[str, Any]) -> Spreadsheet:
    """Parse a Sheets API spreadsheet resource into a Spreadsheet model.

    Args:
        data: Raw JSON dict from the Sheets API.

    Returns:
        Populated Spreadsheet instance.
    """
    props = data.get("properties", {})
    sheets_data = data.get("sheets", [])
    sheets = [_parse_sheet_properties(s.get("properties", {})) for s in sheets_data]
    return Spreadsheet(
        id=data.get("spreadsheetId", ""),
        title=props.get("title", ""),
        url=data.get("spreadsheetUrl"),
        sheets=sheets,
    )


def _parse_update_result(data: dict[str, Any]) -> UpdateResult:
    """Parse an update response from the Sheets values API.

    Args:
        data: Raw JSON dict from an update/append response.

    Returns:
        Parsed UpdateResult model.
    """
    return UpdateResult(
        updated_range=data.get("updatedRange", ""),
        updated_rows=data.get("updatedRows", 0),
        updated_columns=data.get("updatedColumns", 0),
        updated_cells=data.get("updatedCells", 0),
    )


class GoogleSheets(BaseConnector):
    """Connect to Google Sheets to manage spreadsheets and cell data.

    Supports OAuth 2.0 authentication. Pass an access token as
    ``credentials`` when instantiating. Uses the Sheets REST API v4
    via direct httpx calls.
    """

    name = "gsheets"
    display_name = "Google Sheets"
    category = ConnectorCategory.PRODUCTIVITY
    protocol = ProtocolType.REST
    base_url = "https://sheets.googleapis.com/v4"
    description = "Connect to Google Sheets to manage spreadsheets and cell data."
    _rate_limit_config = RateLimitSpec(rate=300, period=60, burst=60)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_headers(self) -> dict[str, str]:
        """Build authorization headers for Sheets API requests.

        Returns:
            Dict with Authorization bearer header.
        """
        return {"Authorization": f"Bearer {self._credentials}"}

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """Execute an authenticated HTTP request against the Sheets API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE).
            path: API path relative to base_url.
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
                f"{self._base_url}{path}",
                headers=self._get_headers(),
                **kwargs,
            )
            raise_typed_for_status(response, connector=self.name)
            if response.status_code == 204 or not response.content:
                return {}
            return response.json()

    # ------------------------------------------------------------------
    # Actions — Spreadsheet-level
    # ------------------------------------------------------------------

    @action("Get spreadsheet metadata and sheets", requires_scope="read")
    async def get_spreadsheet(self, spreadsheet_id: str) -> Spreadsheet:
        """Retrieve a spreadsheet's metadata including all sheet tabs.

        Args:
            spreadsheet_id: The ID of the spreadsheet to retrieve.

        Returns:
            The Spreadsheet object with metadata and sheet list.
        """
        data = await self._request(
            "GET",
            f"/spreadsheets/{spreadsheet_id}",
        )
        return _parse_spreadsheet(data)

    @action("Create a new spreadsheet", requires_scope="write", dangerous=True)
    async def create_spreadsheet(
        self,
        title: str,
        sheet_names: Optional[list[str]] = None,
    ) -> Spreadsheet:
        """Create a new Google Sheets spreadsheet.

        Args:
            title: Title for the new spreadsheet.
            sheet_names: Optional list of sheet tab names to create.
                If omitted, Google creates a single default sheet.

        Returns:
            The created Spreadsheet object.
        """
        body: dict[str, Any] = {
            "properties": {"title": title},
        }
        if sheet_names:
            body["sheets"] = [{"properties": {"title": name}} for name in sheet_names]

        data = await self._request("POST", "/spreadsheets", json=body)
        return _parse_spreadsheet(data)

    @action("Get sheet metadata for all tabs", requires_scope="read")
    async def get_sheet_metadata(self, spreadsheet_id: str) -> list[Sheet]:
        """Retrieve metadata for all sheets in a spreadsheet.

        Args:
            spreadsheet_id: The ID of the spreadsheet.

        Returns:
            List of Sheet objects with properties for each tab.
        """
        data = await self._request(
            "GET",
            f"/spreadsheets/{spreadsheet_id}",
            params={"fields": "sheets.properties"},
        )
        return [_parse_sheet_properties(s.get("properties", {})) for s in data.get("sheets", [])]

    # ------------------------------------------------------------------
    # Actions — Values (read)
    # ------------------------------------------------------------------

    @action("Get values from a range", requires_scope="read")
    async def get_values(
        self,
        spreadsheet_id: str,
        range: str,
    ) -> SheetValues:
        """Read cell values from a specified range.

        Args:
            spreadsheet_id: The ID of the spreadsheet.
            range: A1 notation range (e.g., ``'Sheet1!A1:D10'``).

        Returns:
            SheetValues containing the cell data.
        """
        data = await self._request(
            "GET",
            f"/spreadsheets/{spreadsheet_id}/values/{range}",
        )
        return SheetValues(
            range=data.get("range", ""),
            major_dimension=data.get("majorDimension", "ROWS"),
            values=data.get("values", []),
        )

    @action("Batch get values from multiple ranges", requires_scope="read")
    async def batch_get_values(
        self,
        spreadsheet_id: str,
        ranges: list[str],
    ) -> list[SheetValues]:
        """Read cell values from multiple ranges in a single request.

        Args:
            spreadsheet_id: The ID of the spreadsheet.
            ranges: List of A1 notation ranges to read.

        Returns:
            List of SheetValues, one per requested range.
        """
        data = await self._request(
            "GET",
            f"/spreadsheets/{spreadsheet_id}/values:batchGet",
            params={"ranges": ranges},
        )
        results: list[SheetValues] = []
        for vr in data.get("valueRanges", []):
            results.append(
                SheetValues(
                    range=vr.get("range", ""),
                    major_dimension=vr.get("majorDimension", "ROWS"),
                    values=vr.get("values", []),
                )
            )
        return results

    # ------------------------------------------------------------------
    # Actions — Values (write)
    # ------------------------------------------------------------------

    @action("Update values in a range", requires_scope="write", dangerous=True)
    async def update_values(
        self,
        spreadsheet_id: str,
        range: str,
        values: list[list[Any]],
        input_option: str = "USER_ENTERED",
    ) -> UpdateResult:
        """Update cell values in a specified range.

        Args:
            spreadsheet_id: The ID of the spreadsheet.
            range: A1 notation range to write to (e.g., ``'Sheet1!A1:D10'``).
            values: 2D list of cell values to write.
            input_option: How to interpret the input data. Either
                ``'RAW'`` (no parsing) or ``'USER_ENTERED'`` (parsed as
                if typed into the UI).

        Returns:
            UpdateResult with details about the update operation.
        """
        body: dict[str, Any] = {
            "range": range,
            "majorDimension": "ROWS",
            "values": values,
        }
        data = await self._request(
            "PUT",
            f"/spreadsheets/{spreadsheet_id}/values/{range}",
            json=body,
            params={"valueInputOption": input_option},
        )
        return _parse_update_result(data)

    @action("Append values after a range", requires_scope="write", dangerous=True)
    async def append_values(
        self,
        spreadsheet_id: str,
        range: str,
        values: list[list[Any]],
        input_option: str = "USER_ENTERED",
    ) -> AppendResult:
        """Append rows of data after the last row in a range.

        Args:
            spreadsheet_id: The ID of the spreadsheet.
            range: A1 notation range that defines the table to append to
                (e.g., ``'Sheet1!A1:D1'``).
            values: 2D list of cell values to append.
            input_option: How to interpret the input data (``'RAW'`` or
                ``'USER_ENTERED'``).

        Returns:
            AppendResult containing the update details.
        """
        body: dict[str, Any] = {
            "range": range,
            "majorDimension": "ROWS",
            "values": values,
        }
        data = await self._request(
            "POST",
            f"/spreadsheets/{spreadsheet_id}/values/{range}:append",
            json=body,
            params={"valueInputOption": input_option},
        )
        updates_data = data.get("updates", {})
        return AppendResult(
            updates=_parse_update_result(updates_data) if updates_data else None,
        )

    @action("Clear values from a range", requires_scope="write", dangerous=True)
    async def clear_values(
        self,
        spreadsheet_id: str,
        range: str,
    ) -> ClearResult:
        """Clear all values from a specified range (keeps formatting).

        Args:
            spreadsheet_id: The ID of the spreadsheet.
            range: A1 notation range to clear (e.g., ``'Sheet1!A1:D10'``).

        Returns:
            ClearResult with the cleared range.
        """
        data = await self._request(
            "POST",
            f"/spreadsheets/{spreadsheet_id}/values/{range}:clear",
        )
        return ClearResult(
            cleared_range=data.get("clearedRange", ""),
        )

    @action("Batch update values across multiple ranges", requires_scope="write", dangerous=True)
    async def batch_update_values(
        self,
        spreadsheet_id: str,
        data: list[dict[str, Any]],
        input_option: str = "USER_ENTERED",
    ) -> BatchUpdateResult:
        """Update values across multiple ranges in a single request.

        Args:
            spreadsheet_id: The ID of the spreadsheet.
            data: List of dicts, each with ``range`` (str) and ``values``
                (2D list). Example::

                    [
                        {"range": "Sheet1!A1:B2", "values": [[1, 2], [3, 4]]},
                        {"range": "Sheet1!D1:E2", "values": [["a", "b"]]},
                    ]
            input_option: How to interpret the input data (``'RAW'`` or
                ``'USER_ENTERED'``).

        Returns:
            BatchUpdateResult with per-range update details.
        """
        body: dict[str, Any] = {
            "valueInputOption": input_option,
            "data": [
                {
                    "range": d["range"],
                    "majorDimension": "ROWS",
                    "values": d["values"],
                }
                for d in data
            ],
        }
        resp = await self._request(
            "POST",
            f"/spreadsheets/{spreadsheet_id}/values:batchUpdate",
            json=body,
        )
        responses = [_parse_update_result(r) for r in resp.get("responses", [])]
        return BatchUpdateResult(responses=responses)

    # ------------------------------------------------------------------
    # Actions — Sheet management
    # ------------------------------------------------------------------

    @action("Add a new sheet tab", requires_scope="write", dangerous=True)
    async def add_sheet(
        self,
        spreadsheet_id: str,
        title: str,
        row_count: Optional[int] = None,
        column_count: Optional[int] = None,
    ) -> Sheet:
        """Add a new sheet (tab) to an existing spreadsheet.

        Args:
            spreadsheet_id: The ID of the spreadsheet.
            title: Name for the new sheet tab.
            row_count: Optional initial row count.
            column_count: Optional initial column count.

        Returns:
            The created Sheet object.
        """
        props: dict[str, Any] = {"title": title}
        grid: dict[str, int] = {}
        if row_count is not None:
            grid["rowCount"] = row_count
        if column_count is not None:
            grid["columnCount"] = column_count
        if grid:
            props["gridProperties"] = grid

        body: dict[str, Any] = {
            "requests": [
                {"addSheet": {"properties": props}},
            ],
        }
        data = await self._request(
            "POST",
            f"/spreadsheets/{spreadsheet_id}:batchUpdate",
            json=body,
        )
        reply = data.get("replies", [{}])[0]
        added = reply.get("addSheet", {}).get("properties", {})
        return _parse_sheet_properties(added)

    @action("Delete a sheet tab", requires_scope="write", dangerous=True)
    async def delete_sheet(
        self,
        spreadsheet_id: str,
        sheet_id: int,
    ) -> None:
        """Delete a sheet (tab) from a spreadsheet by its numeric ID.

        Args:
            spreadsheet_id: The ID of the spreadsheet.
            sheet_id: The numeric sheet ID to delete (not the tab name).

        Warning:
            This permanently deletes the sheet and all its data.
        """
        body: dict[str, Any] = {
            "requests": [
                {"deleteSheet": {"sheetId": sheet_id}},
            ],
        }
        await self._request(
            "POST",
            f"/spreadsheets/{spreadsheet_id}:batchUpdate",
            json=body,
        )

    @action("Copy a sheet to another spreadsheet", requires_scope="write")
    async def copy_sheet(
        self,
        spreadsheet_id: str,
        sheet_id: int,
        destination_spreadsheet_id: str,
    ) -> Sheet:
        """Copy a sheet to another (or the same) spreadsheet.

        Args:
            spreadsheet_id: The source spreadsheet ID.
            sheet_id: The numeric sheet ID to copy.
            destination_spreadsheet_id: The target spreadsheet ID.

        Returns:
            The Sheet object for the newly created copy.
        """
        body: dict[str, Any] = {
            "destinationSpreadsheetId": destination_spreadsheet_id,
        }
        data = await self._request(
            "POST",
            f"/spreadsheets/{spreadsheet_id}/sheets/{sheet_id}:copyTo",
            json=body,
        )
        return Sheet(
            id=data.get("sheetId", 0),
            title=data.get("title", ""),
            index=data.get("index", 0),
            row_count=data.get("gridProperties", {}).get("rowCount", 0),
            column_count=data.get("gridProperties", {}).get("columnCount", 0),
        )

    # ------------------------------------------------------------------
    # Actions — Structural operations (batchUpdate)
    # ------------------------------------------------------------------

    @action(
        "Apply structural changes to a spreadsheet",
        dangerous=True,
    )
    async def batch_update_spreadsheet(
        self,
        spreadsheet_id: str,
        requests: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Apply formatting, merge, chart, and structural operations.

        This is the primary method for modifying spreadsheet structure
        beyond cell values. Supports operations like merge cells,
        format cells, add charts, conditional formatting, sort ranges,
        auto-resize columns, add named ranges, and more.

        Each request dict should follow the Google Sheets batchUpdate
        request format. Common requests:

        - ``{"mergeCells": {"range": {...}, "mergeType": "..."}}``
        - ``{"repeatCell": {"range": {...}, "cell": {...}, "fields": "..."}}``
        - ``{"addChart": {"chart": {...}}}``
        - ``{"sortRange": {"range": {...}, "sortSpecs": [...]}}``
        - ``{"autoResizeDimensions": {"dimensions": {...}}}``
        - ``{"addNamedRange": {"namedRange": {...}}}``
        - ``{"updateBorders": {"range": {...}, ...}}``
        - ``{"addConditionalFormatRule": {"rule": {...}, "index": 0}}``

        See Google Sheets API batchUpdate reference for all request
        types.

        Args:
            spreadsheet_id: The spreadsheet ID.
            requests: List of request dicts. Each dict should contain
                exactly one request type as its key.

        Returns:
            Dict with ``spreadsheet_id`` and ``replies`` list.
        """
        data = await self._request(
            "POST",
            f"/spreadsheets/{spreadsheet_id}:batchUpdate",
            json={"requests": requests},
        )
        return {
            "spreadsheet_id": data.get("spreadsheetId", spreadsheet_id),
            "replies": data.get("replies", []),
        }

    @action("Rename a sheet tab within a spreadsheet", dangerous=True)
    async def rename_sheet(
        self,
        spreadsheet_id: str,
        sheet_id: int,
        new_title: str,
    ) -> dict[str, Any]:
        """Rename a sheet tab in a spreadsheet.

        Convenience wrapper around batchUpdate with
        updateSheetProperties request.

        Args:
            spreadsheet_id: The spreadsheet ID.
            sheet_id: The numeric sheet ID (not the sheet name).
            new_title: The new name for the sheet tab.

        Returns:
            Dict with spreadsheet_id and replies.
        """
        return await self.abatch_update_spreadsheet(
            spreadsheet_id,
            [
                {
                    "updateSheetProperties": {
                        "properties": {
                            "sheetId": sheet_id,
                            "title": new_title,
                        },
                        "fields": "title",
                    }
                }
            ],
        )

    @action("Merge cells in a range", dangerous=True)
    async def merge_cells(
        self,
        spreadsheet_id: str,
        sheet_id: int,
        start_row: int,
        end_row: int,
        start_column: int,
        end_column: int,
        merge_type: str = "MERGE_ALL",
    ) -> dict[str, Any]:
        """Merge a range of cells in a sheet.

        Args:
            spreadsheet_id: The spreadsheet ID.
            sheet_id: The numeric sheet ID.
            start_row: Start row (0-indexed).
            end_row: End row (exclusive).
            start_column: Start column (0-indexed).
            end_column: End column (exclusive).
            merge_type: "MERGE_ALL", "MERGE_COLUMNS", or "MERGE_ROWS".

        Returns:
            Dict with spreadsheet_id and replies.
        """
        return await self.abatch_update_spreadsheet(
            spreadsheet_id,
            [
                {
                    "mergeCells": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": start_row,
                            "endRowIndex": end_row,
                            "startColumnIndex": start_column,
                            "endColumnIndex": end_column,
                        },
                        "mergeType": merge_type,
                    }
                }
            ],
        )

    @action("Auto-resize columns to fit content")
    async def auto_resize_columns(
        self,
        spreadsheet_id: str,
        sheet_id: int,
        start_column: int = 0,
        end_column: int = 26,
    ) -> dict[str, Any]:
        """Auto-resize columns to fit their content.

        Args:
            spreadsheet_id: The spreadsheet ID.
            sheet_id: The numeric sheet ID.
            start_column: Start column index (0-indexed, default 0 = A).
            end_column: End column index (exclusive, default 26 = Z).

        Returns:
            Dict with spreadsheet_id and replies.
        """
        return await self.abatch_update_spreadsheet(
            spreadsheet_id,
            [
                {
                    "autoResizeDimensions": {
                        "dimensions": {
                            "sheetId": sheet_id,
                            "dimension": "COLUMNS",
                            "startIndex": start_column,
                            "endIndex": end_column,
                        }
                    }
                }
            ],
        )
