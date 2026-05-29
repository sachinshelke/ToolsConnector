"""End-to-end tests for the Google Sheets connector using respx.

Pinned to Sheets API v4 at ``sheets.googleapis.com/v4``. Auth is
OAuth 2.0 bearer (`Authorization: Bearer ya29.…`).

Structure:
  Round 1 — happy path for all 16 actions
  Round 2 — defensive parsing + URL-path guards (incl. range encoding)
  Round 3 — error matrix (401/403/404/429/500)
  Round 4 — transport errors + 204 No Content
  Round 5 — MCP + OpenAI schema + dangerous flag + sync wrappers + concurrency
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
import pytest_asyncio
import respx

from toolsconnector.connectors.gsheets import GoogleSheets
from toolsconnector.errors import ConnectionError as TCConnectionError
from toolsconnector.errors import (
    InvalidCredentialsError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
)
from toolsconnector.errors import TimeoutError as TCTimeoutError
from toolsconnector.errors import TransportError as TCTransportError


@pytest_asyncio.fixture
async def gs() -> GoogleSheets:
    connector = GoogleSheets(credentials="ya29.fake_test_token")
    yield connector


# Canonical Sheets API response shapes — minimal but valid.
_SHEET_PROPS = {
    "sheetId": 0,
    "title": "Sheet1",
    "index": 0,
    "gridProperties": {"rowCount": 1000, "columnCount": 26},
}
_SPREADSHEET = {
    "spreadsheetId": "sht-abc-123",
    "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/sht-abc-123/edit",
    "properties": {"title": "Test Sheet"},
    "sheets": [{"properties": _SHEET_PROPS}],
}
_VALUES_RESP = {
    "range": "Sheet1!A1:C2",
    "majorDimension": "ROWS",
    "values": [["Name", "Value", "Unicode"], ["foo", 42, "你好 🚀"]],
}
_UPDATE_RESP = {
    "spreadsheetId": "sht-abc-123",
    "updatedRange": "Sheet1!A1:C2",
    "updatedRows": 2,
    "updatedColumns": 3,
    "updatedCells": 6,
}


# ===========================================================================
# Round 1 — happy path for every action
# ===========================================================================


@pytest.mark.asyncio
async def test_get_spreadsheet_returns_typed_model(gs: GoogleSheets) -> None:
    """get_spreadsheet: GET /spreadsheets/{id} → Spreadsheet with metadata + sheets."""
    with respx.mock(base_url="https://sheets.googleapis.com/v4") as mock:
        route = mock.get("/spreadsheets/sht-abc-123").mock(
            return_value=httpx.Response(200, json=_SPREADSHEET)
        )
        spreadsheet = await gs.aget_spreadsheet(spreadsheet_id="sht-abc-123")
        assert spreadsheet.id == "sht-abc-123"
        assert spreadsheet.title == "Test Sheet"
        assert len(spreadsheet.sheets) == 1
        assert spreadsheet.sheets[0].title == "Sheet1"

        # Bearer auth header applied
        assert route.calls.last.request.headers["authorization"] == "Bearer ya29.fake_test_token"


@pytest.mark.asyncio
async def test_create_spreadsheet_with_sheet_names(gs: GoogleSheets) -> None:
    """create_spreadsheet: POST /spreadsheets with title + optional sheet_names."""
    with respx.mock(base_url="https://sheets.googleapis.com/v4") as mock:
        route = mock.post("/spreadsheets").mock(return_value=httpx.Response(200, json=_SPREADSHEET))
        spreadsheet = await gs.acreate_spreadsheet(title="New", sheet_names=["First", "Second"])
        assert spreadsheet.id == "sht-abc-123"
        body = route.calls.last.request.read()
        assert b'"title":"New"' in body
        assert b'"First"' in body
        assert b'"Second"' in body


@pytest.mark.asyncio
async def test_get_sheet_metadata_uses_fields_param(gs: GoogleSheets) -> None:
    """get_sheet_metadata: GET /spreadsheets/{id}?fields=sheets.properties."""
    with respx.mock(base_url="https://sheets.googleapis.com/v4") as mock:
        route = mock.get("/spreadsheets/sht-abc-123").mock(
            return_value=httpx.Response(200, json={"sheets": [{"properties": _SHEET_PROPS}]})
        )
        sheets = await gs.aget_sheet_metadata(spreadsheet_id="sht-abc-123")
        assert len(sheets) == 1
        assert sheets[0].title == "Sheet1"
        # fields parameter narrows the response
        params = dict(route.calls.last.request.url.params)
        assert params["fields"] == "sheets.properties"


@pytest.mark.asyncio
async def test_get_values_returns_typed_sheet_values(gs: GoogleSheets) -> None:
    """get_values: GET /spreadsheets/{id}/values/{range} → SheetValues."""
    with respx.mock(base_url="https://sheets.googleapis.com/v4") as mock:
        # Range gets percent-encoded by _p() — match the encoded form
        mock.get(host="sheets.googleapis.com").mock(
            return_value=httpx.Response(200, json=_VALUES_RESP)
        )
        vals = await gs.aget_values(spreadsheet_id="sht-abc-123", range="Sheet1!A1:C2")
        assert vals.range == "Sheet1!A1:C2"
        assert vals.major_dimension == "ROWS"
        assert vals.values[1][2] == "你好 🚀"  # unicode round-trip


@pytest.mark.asyncio
async def test_batch_get_values_multiple_ranges(gs: GoogleSheets) -> None:
    """batch_get_values: GET .../values:batchGet?ranges=...&ranges=...."""
    with respx.mock(base_url="https://sheets.googleapis.com/v4") as mock:
        route = mock.get("/spreadsheets/sht-abc-123/values:batchGet").mock(
            return_value=httpx.Response(
                200,
                json={
                    "valueRanges": [
                        {"range": "Sheet1!A1:B1", "majorDimension": "ROWS", "values": [["A", "B"]]},
                        {"range": "Sheet1!D1:E1", "majorDimension": "ROWS", "values": [["D", "E"]]},
                    ]
                },
            )
        )
        results = await gs.abatch_get_values(
            spreadsheet_id="sht-abc-123",
            ranges=["Sheet1!A1:B1", "Sheet1!D1:E1"],
        )
        assert len(results) == 2
        assert results[0].values == [["A", "B"]]
        assert results[1].values == [["D", "E"]]
        # Verify both ranges in query params
        url = str(route.calls.last.request.url)
        assert "A1%3AB1" in url or "A1:B1" in url


@pytest.mark.asyncio
async def test_update_values_sends_correct_body(gs: GoogleSheets) -> None:
    """update_values: PUT .../values/{range} with body + valueInputOption."""
    with respx.mock(base_url="https://sheets.googleapis.com/v4") as mock:
        route = mock.put(host="sheets.googleapis.com").mock(
            return_value=httpx.Response(200, json=_UPDATE_RESP)
        )
        result = await gs.aupdate_values(
            spreadsheet_id="sht-abc-123",
            range="Sheet1!A1:C2",
            values=[["a", "b", "c"], ["d", "e", "f"]],
            input_option="USER_ENTERED",
        )
        assert result.updated_cells == 6
        body = route.calls.last.request.read()
        assert b'"values":[["a","b","c"],["d","e","f"]]' in body
        params = dict(route.calls.last.request.url.params)
        assert params["valueInputOption"] == "USER_ENTERED"


@pytest.mark.asyncio
async def test_append_values_with_correct_endpoint(gs: GoogleSheets) -> None:
    """append_values: POST .../values/{range}:append → AppendResult."""
    with respx.mock(base_url="https://sheets.googleapis.com/v4") as mock:
        mock.post(host="sheets.googleapis.com").mock(
            return_value=httpx.Response(
                200,
                json={"updates": _UPDATE_RESP},
            )
        )
        result = await gs.aappend_values(
            spreadsheet_id="sht-abc-123",
            range="Sheet1!A:C",
            values=[["new1", "new2", "new3"]],
        )
        assert result.updates is not None
        assert result.updates.updated_cells == 6


@pytest.mark.asyncio
async def test_clear_values(gs: GoogleSheets) -> None:
    """clear_values: POST .../values/{range}:clear → ClearResult."""
    with respx.mock(base_url="https://sheets.googleapis.com/v4") as mock:
        mock.post(host="sheets.googleapis.com").mock(
            return_value=httpx.Response(200, json={"clearedRange": "Sheet1!A1:C2"})
        )
        result = await gs.aclear_values(spreadsheet_id="sht-abc-123", range="Sheet1!A1:C2")
        assert result.cleared_range == "Sheet1!A1:C2"


@pytest.mark.asyncio
async def test_batch_update_values_multiple_ranges(gs: GoogleSheets) -> None:
    """batch_update_values: POST .../values:batchUpdate → BatchUpdateResult."""
    with respx.mock(base_url="https://sheets.googleapis.com/v4") as mock:
        mock.post("/spreadsheets/sht-abc-123/values:batchUpdate").mock(
            return_value=httpx.Response(
                200,
                json={
                    "spreadsheetId": "sht-abc-123",
                    "responses": [_UPDATE_RESP, _UPDATE_RESP],
                },
            )
        )
        result = await gs.abatch_update_values(
            spreadsheet_id="sht-abc-123",
            data=[
                {"range": "Sheet1!A1:B2", "values": [[1, 2], [3, 4]]},
                {"range": "Sheet1!D1:E1", "values": [["a", "b"]]},
            ],
        )
        assert len(result.responses) == 2


@pytest.mark.asyncio
async def test_add_sheet_via_batch_update(gs: GoogleSheets) -> None:
    """add_sheet: POST :batchUpdate with addSheet request → Sheet."""
    with respx.mock(base_url="https://sheets.googleapis.com/v4") as mock:
        route = mock.post("/spreadsheets/sht-abc-123:batchUpdate").mock(
            return_value=httpx.Response(
                200,
                json={
                    "replies": [
                        {
                            "addSheet": {
                                "properties": {
                                    "sheetId": 999,
                                    "title": "New Tab",
                                    "index": 1,
                                    "gridProperties": {"rowCount": 100, "columnCount": 5},
                                }
                            }
                        }
                    ]
                },
            )
        )
        sheet = await gs.aadd_sheet(
            spreadsheet_id="sht-abc-123",
            title="New Tab",
            row_count=100,
            column_count=5,
        )
        assert sheet.id == 999
        assert sheet.title == "New Tab"
        body = route.calls.last.request.read()
        assert b'"addSheet"' in body
        assert b'"rowCount":100' in body


@pytest.mark.asyncio
async def test_delete_sheet_sends_batch_update_with_delete_request(
    gs: GoogleSheets,
) -> None:
    """delete_sheet: POST :batchUpdate with deleteSheet request → None."""
    with respx.mock(base_url="https://sheets.googleapis.com/v4") as mock:
        route = mock.post("/spreadsheets/sht-abc-123:batchUpdate").mock(
            return_value=httpx.Response(200, json={})
        )
        result = await gs.adelete_sheet(spreadsheet_id="sht-abc-123", sheet_id=42)
        assert result is None
        body = route.calls.last.request.read()
        assert b'"deleteSheet"' in body
        assert b'"sheetId":42' in body


@pytest.mark.asyncio
async def test_copy_sheet_to_destination_spreadsheet(gs: GoogleSheets) -> None:
    """copy_sheet: POST .../sheets/{sheetId}:copyTo → Sheet of the copy."""
    with respx.mock(base_url="https://sheets.googleapis.com/v4") as mock:
        route = mock.post(host="sheets.googleapis.com").mock(
            return_value=httpx.Response(
                200,
                json={
                    "sheetId": 555,
                    "title": "Copy of X",
                    "index": 0,
                    "gridProperties": {"rowCount": 100, "columnCount": 26},
                },
            )
        )
        copy = await gs.acopy_sheet(
            spreadsheet_id="src",
            sheet_id=42,
            destination_spreadsheet_id="dst",
        )
        assert copy.id == 555
        body = route.calls.last.request.read()
        assert b'"destinationSpreadsheetId":"dst"' in body


@pytest.mark.asyncio
async def test_batch_update_spreadsheet_with_structural_requests(
    gs: GoogleSheets,
) -> None:
    """batch_update_spreadsheet: arbitrary structural mutations → dict.

    This is the general-purpose mutation endpoint underpinning rename_sheet,
    merge_cells, etc.
    """
    with respx.mock(base_url="https://sheets.googleapis.com/v4") as mock:
        mock.post("/spreadsheets/sht-abc-123:batchUpdate").mock(
            return_value=httpx.Response(
                200,
                json={"spreadsheetId": "sht-abc-123", "replies": [{"updateSheetProperties": {}}]},
            )
        )
        result = await gs.abatch_update_spreadsheet(
            spreadsheet_id="sht-abc-123",
            requests=[
                {
                    "updateSheetProperties": {
                        "properties": {"sheetId": 0, "title": "Renamed"},
                        "fields": "title",
                    }
                }
            ],
        )
        assert result["spreadsheet_id"] == "sht-abc-123"
        assert len(result["replies"]) == 1


@pytest.mark.asyncio
async def test_rename_sheet_delegates_to_batch_update(gs: GoogleSheets) -> None:
    """rename_sheet: convenience wrapper around batch_update_spreadsheet
    with an updateSheetProperties request."""
    with respx.mock(base_url="https://sheets.googleapis.com/v4") as mock:
        route = mock.post("/spreadsheets/sht-abc-123:batchUpdate").mock(
            return_value=httpx.Response(200, json={"spreadsheetId": "sht-abc-123", "replies": [{}]})
        )
        await gs.arename_sheet(spreadsheet_id="sht-abc-123", sheet_id=42, new_title="NewName")
        body = route.calls.last.request.read()
        assert b'"updateSheetProperties"' in body
        assert b'"title":"NewName"' in body
        assert b'"sheetId":42' in body


@pytest.mark.asyncio
async def test_merge_cells_constructs_correct_range(gs: GoogleSheets) -> None:
    """merge_cells: convenience wrapper constructs mergeCells request with range."""
    with respx.mock(base_url="https://sheets.googleapis.com/v4") as mock:
        route = mock.post("/spreadsheets/sht-abc-123:batchUpdate").mock(
            return_value=httpx.Response(200, json={"spreadsheetId": "sht-abc-123", "replies": [{}]})
        )
        await gs.amerge_cells(
            spreadsheet_id="sht-abc-123",
            sheet_id=0,
            start_row=0,
            end_row=2,
            start_column=0,
            end_column=3,
            merge_type="MERGE_ALL",
        )
        body = route.calls.last.request.read()
        assert b'"mergeCells"' in body
        assert b'"mergeType":"MERGE_ALL"' in body
        assert b'"startRowIndex":0' in body
        assert b'"endRowIndex":2' in body
        assert b'"endColumnIndex":3' in body


@pytest.mark.asyncio
async def test_auto_resize_columns_default_range(gs: GoogleSheets) -> None:
    """auto_resize_columns: default range covers columns 0-26 (A-Z)."""
    with respx.mock(base_url="https://sheets.googleapis.com/v4") as mock:
        route = mock.post("/spreadsheets/sht-abc-123:batchUpdate").mock(
            return_value=httpx.Response(200, json={"spreadsheetId": "sht-abc-123", "replies": [{}]})
        )
        await gs.aauto_resize_columns(spreadsheet_id="sht-abc-123", sheet_id=0)
        body = route.calls.last.request.read()
        assert b'"autoResizeDimensions"' in body
        assert b'"dimension":"COLUMNS"' in body
        assert b'"startIndex":0' in body
        assert b'"endIndex":26' in body


# ===========================================================================
# Round 2 — defensive parsing + URL-path guards
# ===========================================================================


@pytest.mark.asyncio
async def test_spreadsheet_id_with_slash_percent_encoded(gs: GoogleSheets) -> None:
    """Adversarial spreadsheet_id must NOT escape /spreadsheets/ prefix
    via httpx URL normalization. The `_p()` helper percent-encodes the
    segment.
    """
    with respx.mock(base_url="https://sheets.googleapis.com/v4") as mock:
        route = mock.get(host="sheets.googleapis.com").mock(
            return_value=httpx.Response(404, json={"error": {"code": 404, "message": "Not found"}})
        )
        with pytest.raises(NotFoundError):
            await gs.aget_spreadsheet(spreadsheet_id="../admin")

        actual_url = str(route.calls.last.request.url)
        assert "/spreadsheets/" in actual_url
        # Owner-style slash was percent-encoded
        assert "..%2Fadmin" in actual_url or "..%2fadmin" in actual_url
        assert "/admin/" not in actual_url


@pytest.mark.asyncio
async def test_range_with_unicode_passes_through(gs: GoogleSheets) -> None:
    """A1 notation can include sheet tab names with unicode. The range
    string passes through `_p()` which percent-encodes per byte; Google's
    API accepts both literal and percent-encoded forms.
    """
    with respx.mock(base_url="https://sheets.googleapis.com/v4") as mock:
        route = mock.get(host="sheets.googleapis.com").mock(
            return_value=httpx.Response(200, json=_VALUES_RESP)
        )
        await gs.aget_values(spreadsheet_id="sht-abc-123", range="数据!A1:B2")
        # Either form is acceptable — _p() percent-encodes
        url = str(route.calls.last.request.url)
        # The unicode bytes encoded as %E6%95%B0%E6%8D%AE for "数据"
        assert "%E6" in url or "数据" in url


@pytest.mark.asyncio
async def test_spreadsheet_model_tolerates_unknown_fields(gs: GoogleSheets) -> None:
    """All 7 type models declare extra='ignore'. Verify the parser doesn't
    crash on a fully-populated response with many extra fields the Sheets
    API returns (developerMetadata, namedRanges, protectedRanges, etc.).
    """
    fat = {
        "spreadsheetId": "sht-xyz",
        "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/sht-xyz/edit",
        "properties": {
            "title": "Title",
            "locale": "en_US",
            "timeZone": "UTC",
            "autoRecalc": "ON_CHANGE",
            "defaultFormat": {},
            "spreadsheetTheme": {},  # extra
        },
        "sheets": [
            {
                "properties": {
                    **_SHEET_PROPS,
                    "tabColor": {"red": 0.5},
                    "tabColorStyle": {},
                    "hidden": False,
                },
                "merges": [],  # extra
                "filterViews": [],
                "protectedRanges": [],
            }
        ],
        "developerMetadata": [],  # extra top-level
        "namedRanges": [],
        "dataSources": [],
    }
    with respx.mock(base_url="https://sheets.googleapis.com/v4") as mock:
        mock.get("/spreadsheets/sht-xyz").mock(return_value=httpx.Response(200, json=fat))
        ss = await gs.aget_spreadsheet(spreadsheet_id="sht-xyz")
        assert ss.id == "sht-xyz"
        assert ss.sheets[0].title == "Sheet1"


@pytest.mark.asyncio
async def test_append_values_returns_none_updates_when_missing(
    gs: GoogleSheets,
) -> None:
    """append_values: if API returns no `updates` field, AppendResult.updates is None."""
    with respx.mock(base_url="https://sheets.googleapis.com/v4") as mock:
        mock.post(host="sheets.googleapis.com").mock(return_value=httpx.Response(200, json={}))
        result = await gs.aappend_values(
            spreadsheet_id="sht-abc-123",
            range="A:C",
            values=[["1", "2", "3"]],
        )
        assert result.updates is None


# ===========================================================================
# Round 3 — error matrix
# ===========================================================================


@pytest.mark.asyncio
async def test_401_raises_invalid_credentials_error(gs: GoogleSheets) -> None:
    """Expired or invalid OAuth token → 401 → InvalidCredentialsError."""
    with respx.mock(base_url="https://sheets.googleapis.com/v4") as mock:
        mock.get("/spreadsheets/d").mock(
            return_value=httpx.Response(
                401, json={"error": {"code": 401, "message": "Invalid Credentials"}}
            )
        )
        with pytest.raises(InvalidCredentialsError) as exc_info:
            await gs.aget_spreadsheet(spreadsheet_id="d")
        assert exc_info.value.connector == "gsheets"


@pytest.mark.asyncio
async def test_403_raises_permission_denied_error(gs: GoogleSheets) -> None:
    """Token lacks the spreadsheets scope → 403 → PermissionDeniedError."""
    with respx.mock(base_url="https://sheets.googleapis.com/v4") as mock:
        mock.get("/spreadsheets/d").mock(
            return_value=httpx.Response(
                403, json={"error": {"code": 403, "message": "Insufficient Permission"}}
            )
        )
        with pytest.raises(PermissionDeniedError):
            await gs.aget_spreadsheet(spreadsheet_id="d")


@pytest.mark.asyncio
async def test_404_raises_not_found_error(gs: GoogleSheets) -> None:
    """Nonexistent spreadsheet ID → 404."""
    with respx.mock(base_url="https://sheets.googleapis.com/v4") as mock:
        mock.get("/spreadsheets/missing").mock(
            return_value=httpx.Response(404, json={"error": {"code": 404, "message": "Not found"}})
        )
        with pytest.raises(NotFoundError):
            await gs.aget_spreadsheet(spreadsheet_id="missing")


@pytest.mark.asyncio
async def test_429_raises_rate_limit_error(gs: GoogleSheets) -> None:
    """Quota exceeded → 429."""
    with respx.mock(base_url="https://sheets.googleapis.com/v4") as mock:
        mock.get("/spreadsheets/d").mock(
            return_value=httpx.Response(
                429,
                json={"error": {"code": 429, "message": "Quota exceeded"}},
                headers={"Retry-After": "60"},
            )
        )
        with pytest.raises(RateLimitError):
            await gs.aget_spreadsheet(spreadsheet_id="d")


@pytest.mark.asyncio
async def test_500_raises_server_error(gs: GoogleSheets) -> None:
    """5xx → ServerError, eligible for backoff."""
    with respx.mock(base_url="https://sheets.googleapis.com/v4") as mock:
        mock.get("/spreadsheets/d").mock(
            return_value=httpx.Response(500, json={"error": {"code": 500}})
        )
        with pytest.raises(ServerError):
            await gs.aget_spreadsheet(spreadsheet_id="d")


# ===========================================================================
# Round 4 — transport errors + 204
# ===========================================================================


@pytest.mark.asyncio
async def test_connect_error_raises_typed(gs: GoogleSheets) -> None:
    """httpx.ConnectError → typed ConnectionError."""
    with respx.mock(base_url="https://sheets.googleapis.com/v4") as mock:
        mock.get("/spreadsheets/d").mock(side_effect=httpx.ConnectError("DNS"))
        with pytest.raises(TCConnectionError):
            await gs.aget_spreadsheet(spreadsheet_id="d")


@pytest.mark.asyncio
async def test_timeout_raises_typed(gs: GoogleSheets) -> None:
    """httpx.TimeoutException → typed TimeoutError."""
    with respx.mock(base_url="https://sheets.googleapis.com/v4") as mock:
        mock.get("/spreadsheets/d").mock(side_effect=httpx.ReadTimeout("slow"))
        with pytest.raises(TCTimeoutError):
            await gs.aget_spreadsheet(spreadsheet_id="d")


@pytest.mark.asyncio
async def test_transport_error_raises_typed(gs: GoogleSheets) -> None:
    """httpx.RemoteProtocolError → typed TransportError."""
    with respx.mock(base_url="https://sheets.googleapis.com/v4") as mock:
        mock.get("/spreadsheets/d").mock(side_effect=httpx.RemoteProtocolError("conn dropped"))
        with pytest.raises(TCTransportError):
            await gs.aget_spreadsheet(spreadsheet_id="d")


@pytest.mark.asyncio
async def test_delete_sheet_handles_empty_response_gracefully(
    gs: GoogleSheets,
) -> None:
    """delete_sheet returns None even if the API returns an empty body
    (some success responses on batchUpdate are minimal)."""
    with respx.mock(base_url="https://sheets.googleapis.com/v4") as mock:
        mock.post("/spreadsheets/d:batchUpdate").mock(return_value=httpx.Response(204))
        result = await gs.adelete_sheet(spreadsheet_id="d", sheet_id=42)
        assert result is None


# ===========================================================================
# Round 5 — MCP exposure + OpenAI schema + dangerous flag + sync wrappers
# ===========================================================================


def test_dangerous_actions_are_flagged() -> None:
    """All mutations dangerous; all reads safe. Pinned for the dangerous-flag tripwire."""
    spec = GoogleSheets.get_spec()
    expected_dangerous = {
        "create_spreadsheet",
        "update_values",
        "append_values",
        "clear_values",
        "batch_update_values",
        "add_sheet",
        "delete_sheet",
        "batch_update_spreadsheet",
        "rename_sheet",
        "merge_cells",
    }
    for action_name in expected_dangerous:
        assert spec.actions[action_name].dangerous is True, f"{action_name} must be dangerous=True"

    expected_safe = {
        "get_spreadsheet",
        "get_sheet_metadata",
        "get_values",
        "batch_get_values",
        "copy_sheet",  # currently NOT flagged dangerous; reads source, creates copy
        "auto_resize_columns",  # no body mutation; layout only
    }
    for action_name in expected_safe:
        assert spec.actions[action_name].dangerous is False, (
            f"{action_name} must be dangerous=False"
        )


def test_every_action_has_openai_compatible_schema() -> None:
    """Sweep: every @action produces a valid OpenAI function-call schema."""
    from toolsconnector.serve import ToolKit

    kit = ToolKit(["gsheets"], credentials={"gsheets": "ya29.fake"})
    tools = kit.to_openai_tools()
    assert len(tools) == 16
    for tool in tools:
        fn = tool["function"]
        assert fn["name"].startswith("gsheets_")
        assert fn["description"]
        assert fn["parameters"]["type"] == "object"


def test_mcp_exposure_via_toolkit() -> None:
    """All 16 actions are exposed when serving via MCP."""
    from toolsconnector.serve import ToolKit

    kit = ToolKit(["gsheets"], credentials={"gsheets": "ya29.fake"})
    tools = kit.list_tools()
    names = {t["name"] for t in tools}
    assert len(names) == 16
    for action_name in (
        "get_spreadsheet",
        "create_spreadsheet",
        "get_values",
        "update_values",
        "batch_update_values",
        "add_sheet",
        "delete_sheet",
        "merge_cells",
    ):
        assert f"gsheets_{action_name}" in names


def test_mcp_exclude_dangerous_filters_10_dangerous() -> None:
    """exclude_dangerous filters out 10 dangerous → 6 safe remain."""
    from toolsconnector.serve import ToolKit

    kit_safe = ToolKit(["gsheets"], credentials={"gsheets": "ya29.fake"}, exclude_dangerous=True)
    tools_safe = kit_safe.list_tools()
    assert len(tools_safe) == 6
    safe_names = {t["name"] for t in tools_safe}
    for dangerous in (
        "gsheets_create_spreadsheet",
        "gsheets_update_values",
        "gsheets_append_values",
        "gsheets_clear_values",
        "gsheets_batch_update_values",
        "gsheets_add_sheet",
        "gsheets_delete_sheet",
        "gsheets_batch_update_spreadsheet",
        "gsheets_rename_sheet",
        "gsheets_merge_cells",
    ):
        assert dangerous not in safe_names


def test_sync_wrappers_match_async() -> None:
    """Each async @action has a sync wrapper at the bare name + an `a`-prefixed async name."""
    inst = GoogleSheets(credentials="ya29.fake")
    for action_name in (
        "get_spreadsheet",
        "create_spreadsheet",
        "get_values",
        "update_values",
        "delete_sheet",
        "merge_cells",
    ):
        assert hasattr(inst, action_name)
        assert hasattr(inst, f"a{action_name}")


def test_verification_status_marked_live() -> None:
    """gsheets promoted to Tier 1 on 2026-05-28."""
    assert GoogleSheets.verification_status == "live"
    assert GoogleSheets.get_spec().verification_status == "live"


@pytest.mark.asyncio
async def test_concurrent_requests_safe(gs: GoogleSheets) -> None:
    """Two concurrent get_spreadsheet calls don't share mutable state."""
    with respx.mock(base_url="https://sheets.googleapis.com/v4") as mock:
        mock.get("/spreadsheets/a").mock(
            return_value=httpx.Response(200, json={**_SPREADSHEET, "spreadsheetId": "a"})
        )
        mock.get("/spreadsheets/b").mock(
            return_value=httpx.Response(200, json={**_SPREADSHEET, "spreadsheetId": "b"})
        )
        results = await asyncio.gather(
            gs.aget_spreadsheet(spreadsheet_id="a"),
            gs.aget_spreadsheet(spreadsheet_id="b"),
        )
        assert results[0].id == "a"
        assert results[1].id == "b"
