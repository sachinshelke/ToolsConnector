"""End-to-end tests for the Google Drive connector using respx.

Pinned to Drive API v3 at ``www.googleapis.com/drive/v3``. Auth is
OAuth 2.0 bearer (`Authorization: Bearer ya29.…`).

Structure (5 rounds):
  Round 1 — happy path for all 22 actions
  Round 2 — defensive parsing + URL-path guards
  Round 3 — error matrix (401/403/404/429/500)
  Round 4 — transport errors + 204 No Content
  Round 5 — MCP + OpenAI schema + dangerous flag + sync wrappers
"""

from __future__ import annotations

import asyncio
import base64

import httpx
import pytest
import pytest_asyncio
import respx

from toolsconnector.connectors.gdrive import GoogleDrive
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
async def gd() -> GoogleDrive:
    yield GoogleDrive(credentials="ya29.fake_test_token")


_FILE = {
    "id": "file-abc-123",
    "name": "test.txt",
    "mimeType": "text/plain",
    "size": "42",
    "createdTime": "2026-05-28T12:00:00Z",
    "modifiedTime": "2026-05-28T12:00:00Z",
    "parents": ["folder-root"],
    "webViewLink": "https://drive.google.com/file/d/file-abc-123/view",
    "webContentLink": "https://drive.google.com/uc?id=file-abc-123",
    "iconLink": "https://drive.google.com/icon.png",
    "trashed": False,
    "starred": False,
}
_PERM = {
    "id": "perm-1",
    "type": "user",
    "role": "reader",
    "emailAddress": "alice@example.com",
    "displayName": "Alice",
}
_COMMENT = {
    "id": "comment-1",
    "content": "Looks good",
    "author": {"displayName": "Bob", "me": False},
    "createdTime": "2026-05-28T12:00:00Z",
    "modifiedTime": "2026-05-28T12:00:00Z",
    "resolved": False,
    "deleted": False,
}
_REV = {
    "id": "rev-1",
    "mimeType": "text/plain",
    "modifiedTime": "2026-05-28T12:00:00Z",
    "size": "42",
    "originalFilename": "test.txt",
    "keepForever": False,
}


# ===========================================================================
# Round 1 — happy path × 22 actions
# ===========================================================================


@pytest.mark.asyncio
async def test_list_files_with_filters(gd: GoogleDrive) -> None:
    """list_files: GET /files with pageSize + orderBy + folder_id.

    Signature is (page_size, order_by, page_token, folder_id) — there
    is no `query` parameter on `list_files`. `search_files` is the
    action that accepts a Drive query DSL.
    """
    with respx.mock(base_url="https://www.googleapis.com/drive/v3") as mock:
        route = mock.get("/files").mock(
            return_value=httpx.Response(200, json={"files": [_FILE], "nextPageToken": "tok-2"})
        )
        page = await gd.alist_files(
            page_size=50,
            order_by="name",
            folder_id="folder-x",
        )
        assert len(page.items) == 1
        assert page.page_state.cursor == "tok-2"
        params = dict(route.calls.last.request.url.params)
        assert params["pageSize"] == "50"
        assert params["orderBy"] == "name"
        # folder_id is encoded into the query as 'X in parents'
        assert "folder-x" in params["q"]


@pytest.mark.asyncio
async def test_get_file(gd: GoogleDrive) -> None:
    """get_file: GET /files/{id}?fields=… → DriveFile."""
    with respx.mock(base_url="https://www.googleapis.com/drive/v3") as mock:
        route = mock.get("/files/file-abc-123").mock(return_value=httpx.Response(200, json=_FILE))
        f = await gd.aget_file(file_id="file-abc-123")
        assert f.id == "file-abc-123"
        assert f.name == "test.txt"
        params = dict(route.calls.last.request.url.params)
        assert "fields" in params  # full-field projection


@pytest.mark.asyncio
async def test_upload_file_uses_multipart(gd: GoogleDrive) -> None:
    """upload_file: POST /upload/drive/v3/files?uploadType=multipart with multipart body."""
    content = base64.b64encode(b"Hello content").decode()
    with respx.mock() as mock:
        route = mock.post("https://www.googleapis.com/upload/drive/v3/files").mock(
            return_value=httpx.Response(200, json={**_FILE, "id": "uploaded"})
        )
        result = await gd.aupload_file(
            name="upload.txt",
            content_base64=content,
            mime_type="text/plain",
            parent_folder_id="folder-x",
        )
        assert result.id == "uploaded"
        # Multipart Content-Type with boundary
        ct = route.calls.last.request.headers["content-type"]
        assert ct.startswith("multipart/related")


@pytest.mark.asyncio
async def test_upload_file_does_not_declare_content_transfer_encoding(
    gd: GoogleDrive,
) -> None:
    """Regression test for the production bug fixed in 0.3.11.

    Before the fix, the multipart body declared
    ``Content-Transfer-Encoding: base64`` while actually sending the
    raw decoded bytes. Google's upload endpoint took the header at
    face value, tried to decode the raw bytes as base64 again, and
    rejected with HTTP 400 — every prior upload failed.

    The fix: do NOT include that header. Raw bytes match the
    ``Content-Type: <mime>`` declaration. This test pins absence so
    a refactor reintroducing the header would fail loudly.
    """
    content = base64.b64encode(b"x").decode()
    with respx.mock() as mock:
        route = mock.post("https://www.googleapis.com/upload/drive/v3/files").mock(
            return_value=httpx.Response(200, json=_FILE)
        )
        await gd.aupload_file(
            name="r.txt",
            content_base64=content,
            mime_type="text/plain",
        )
        body = route.calls.last.request.read()
        # The header MUST NOT appear in the multipart body parts
        assert b"Content-Transfer-Encoding" not in body, (
            "Regression: upload_file is again declaring "
            "Content-Transfer-Encoding: base64 but sending raw bytes — "
            "Google will reject with HTTP 400."
        )


@pytest.mark.asyncio
async def test_upload_file_transport_error_wraps_typed(gd: GoogleDrive) -> None:
    """Regression test for the production gap closed in 0.3.11.

    Before the fix, upload_file had a hardcoded httpx.AsyncClient call
    that bypassed the transport-error wrapping in ``_request`` /
    ``_request_raw``. A ConnectError during upload bubbled out as raw
    httpx — breaking ``except ToolsConnectorError`` callers.

    The fix: wrap the inner call in the same try/except. This test
    pins that a httpx.ConnectError during upload now raises typed
    ConnectionError.
    """
    content = base64.b64encode(b"x").decode()
    with respx.mock() as mock:
        mock.post("https://www.googleapis.com/upload/drive/v3/files").mock(
            side_effect=httpx.ConnectError("DNS failure")
        )
        with pytest.raises(TCConnectionError) as exc_info:
            await gd.aupload_file(
                name="r.txt",
                content_base64=content,
                mime_type="text/plain",
            )
        assert exc_info.value.connector == "gdrive"


@pytest.mark.asyncio
async def test_upload_file_convert_to_google_docs_sets_native_mime_type(
    gd: GoogleDrive,
) -> None:
    """upload_file(convert_to_google_docs=True): metadata.mimeType is the Google native type.

    Drive uses ``metadata.mimeType`` as the "store as" target. When the
    target is a Google native type
    (``application/vnd.google-apps.document``), Drive interprets the body
    bytes per their ``Content-Type`` and converts them server-side.
    """
    content = base64.b64encode(b"sample docx bytes").decode()
    docx_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    with respx.mock() as mock:
        route = mock.post("https://www.googleapis.com/upload/drive/v3/files").mock(
            return_value=httpx.Response(
                200,
                json={
                    **_FILE,
                    "id": "converted-doc",
                    "mimeType": "application/vnd.google-apps.document",
                },
            )
        )
        result = await gd.aupload_file(
            name="report.docx",
            content_base64=content,
            mime_type=docx_mime,
            convert_to_google_docs=True,
        )
        assert result.id == "converted-doc"
        assert result.mime_type == "application/vnd.google-apps.document"
        body = route.calls.last.request.read()
        # The metadata JSON part must claim the Google native type
        assert b'"mimeType": "application/vnd.google-apps.document"' in body
        # AND the source bytes part must keep its original Content-Type
        assert docx_mime.encode() in body


@pytest.mark.asyncio
async def test_upload_file_convert_to_google_docs_unsupported_mime_raises(
    gd: GoogleDrive,
) -> None:
    """upload_file: convert_to_google_docs with an unmapped mime_type raises ValueError.

    The conversion map is conservative — only formats Drive officially
    supports. Asking to convert a PDF or arbitrary binary should fail
    fast at the client rather than silently uploading raw bytes.
    """
    content = base64.b64encode(b"pretend pdf").decode()
    with pytest.raises(ValueError) as exc_info:
        await gd.aupload_file(
            name="report.pdf",
            content_base64=content,
            mime_type="application/pdf",
            convert_to_google_docs=True,
        )
    assert "no documented Drive conversion" in str(exc_info.value)
    assert "application/pdf" in str(exc_info.value)


@pytest.mark.asyncio
async def test_upload_file_convert_to_google_docs_default_false_preserves_mime(
    gd: GoogleDrive,
) -> None:
    """upload_file: default convert_to_google_docs=False preserves source mime_type as storage type."""
    content = base64.b64encode(b"plain text").decode()
    with respx.mock() as mock:
        route = mock.post("https://www.googleapis.com/upload/drive/v3/files").mock(
            return_value=httpx.Response(200, json={**_FILE, "id": "raw-upload"})
        )
        await gd.aupload_file(
            name="r.txt",
            content_base64=content,
            mime_type="text/plain",
        )
        body = route.calls.last.request.read()
        # No conversion: metadata.mimeType stays as source
        assert b'"mimeType": "text/plain"' in body
        # And no Google-native marker appears
        assert b"application/vnd.google-apps." not in body


@pytest.mark.asyncio
async def test_share_file_anyone_type_omits_email_address(gd: GoogleDrive) -> None:
    """Regression test for the production bug fixed in 0.3.11.

    Before the fix, share_file unconditionally included ``emailAddress``
    in the permission body — but Drive rejects that field when type
    is ``"anyone"`` (public link) or ``"domain"``. The fix: include
    emailAddress only when type is user/group; map email to ``domain``
    when type is domain.

    This test pins that type="anyone" sends a body WITHOUT emailAddress.
    """
    with respx.mock(base_url="https://www.googleapis.com/drive/v3") as mock:
        route = mock.post("/files/file-abc-123/permissions").mock(
            return_value=httpx.Response(
                200, json={"id": "anyoneWithLink", "type": "anyone", "role": "reader"}
            )
        )
        await gd.ashare_file(
            file_id="file-abc-123",
            email="",  # type=anyone doesn't need an email
            role="reader",
            type="anyone",
            send_notification=False,
        )
        body = route.calls.last.request.read()
        # The KEY regression check: emailAddress must NOT be in the body
        assert b'"emailAddress"' not in body, (
            "Regression: share_file is again including emailAddress in "
            "the body for type=anyone — Drive will reject with HTTP 400."
        )
        # Type + role still present
        assert b'"type":"anyone"' in body
        assert b'"role":"reader"' in body


@pytest.mark.asyncio
async def test_share_file_domain_type_maps_email_to_domain_field(
    gd: GoogleDrive,
) -> None:
    """Companion to test_share_file_anyone_type_omits_email_address.

    For type=domain, the connector maps the ``email`` arg to the
    ``domain`` field rather than ``emailAddress``. The receiver is a
    domain name like ``example.com``, not an email.
    """
    with respx.mock(base_url="https://www.googleapis.com/drive/v3") as mock:
        route = mock.post("/files/file-abc-123/permissions").mock(
            return_value=httpx.Response(
                200, json={"id": "x", "type": "domain", "role": "reader", "domain": "example.com"}
            )
        )
        await gd.ashare_file(
            file_id="file-abc-123",
            email="example.com",  # for type=domain this is the domain
            role="reader",
            type="domain",
            send_notification=False,
        )
        body = route.calls.last.request.read()
        # domain field set, emailAddress NOT set
        assert b'"domain":"example.com"' in body
        assert b'"emailAddress"' not in body


@pytest.mark.asyncio
async def test_download_file_returns_base64(gd: GoogleDrive) -> None:
    """download_file: GET /files/{id} metadata + GET /files/{id}?alt=media → FileDownloadResult.

    The connector makes two requests: first metadata (id/name/mimeType/size)
    via the standard _request, then the content via _request_raw against
    the alt=media URL. The mock uses side_effect to route by call order
    rather than by URL match — the metadata GET and the alt=media GET
    share the same base URL.
    """
    file_bytes = b"download content"
    metadata = {
        "id": "file-abc-123",
        "name": "test.txt",
        "mimeType": "text/plain",
        "size": str(len(file_bytes)),
    }
    with respx.mock() as mock:
        # Order matters: the connector calls metadata first, then alt=media.
        mock.get(
            "https://www.googleapis.com/drive/v3/files/file-abc-123",
            params={"fields": "id,name,mimeType,size"},
        ).mock(return_value=httpx.Response(200, json=metadata))
        mock.get(
            "https://www.googleapis.com/drive/v3/files/file-abc-123",
            params={"alt": "media"},
        ).mock(return_value=httpx.Response(200, content=file_bytes))

        result = await gd.adownload_file(file_id="file-abc-123")
        assert result.id == "file-abc-123"
        decoded = base64.b64decode(result.content_base64)
        assert decoded == file_bytes


@pytest.mark.asyncio
async def test_create_folder(gd: GoogleDrive) -> None:
    """create_folder: POST /files with mimeType=…folder → FolderId."""
    with respx.mock(base_url="https://www.googleapis.com/drive/v3") as mock:
        route = mock.post("/files").mock(
            return_value=httpx.Response(200, json={"id": "folder-new", "name": "MyFolder"})
        )
        folder = await gd.acreate_folder(name="MyFolder", parent_folder_id="folder-root")
        assert folder.id == "folder-new"
        body = route.calls.last.request.read()
        assert b'"mimeType":"application/vnd.google-apps.folder"' in body
        assert b'"parents":["folder-root"]' in body


@pytest.mark.asyncio
async def test_delete_file(gd: GoogleDrive) -> None:
    """delete_file: DELETE /files/{id} → None."""
    with respx.mock(base_url="https://www.googleapis.com/drive/v3") as mock:
        mock.delete("/files/file-abc-123").mock(return_value=httpx.Response(204))
        result = await gd.adelete_file(file_id="file-abc-123")
        assert result is None


@pytest.mark.asyncio
async def test_search_files(gd: GoogleDrive) -> None:
    """search_files: GET /files with q + pageSize → PaginatedList."""
    with respx.mock(base_url="https://www.googleapis.com/drive/v3") as mock:
        mock.get("/files").mock(return_value=httpx.Response(200, json={"files": [_FILE]}))
        page = await gd.asearch_files(query="fullText contains 'test'")
        assert len(page.items) == 1


@pytest.mark.asyncio
async def test_share_file_sends_correct_body(gd: GoogleDrive) -> None:
    """share_file: POST /files/{id}/permissions with role + emailAddress + sendNotificationEmail."""
    with respx.mock(base_url="https://www.googleapis.com/drive/v3") as mock:
        route = mock.post("/files/file-abc-123/permissions").mock(
            return_value=httpx.Response(200, json=_PERM)
        )
        perm = await gd.ashare_file(
            file_id="file-abc-123",
            email="alice@example.com",
            role="writer",
            send_notification=False,
            message="Sharing for review",
        )
        assert perm.role == "reader"  # mock response says reader
        body = route.calls.last.request.read()
        assert b'"emailAddress":"alice@example.com"' in body
        assert b'"role":"writer"' in body
        params = dict(route.calls.last.request.url.params)
        assert params["sendNotificationEmail"] == "false"
        assert params["emailMessage"] == "Sharing for review"


@pytest.mark.asyncio
async def test_move_file(gd: GoogleDrive) -> None:
    """move_file: GET parents → PATCH addParents/removeParents."""
    with respx.mock(base_url="https://www.googleapis.com/drive/v3") as mock:
        mock.get("/files/file-abc-123").mock(
            return_value=httpx.Response(200, json={"parents": ["folder-old"]})
        )
        route = mock.patch("/files/file-abc-123").mock(return_value=httpx.Response(200, json=_FILE))
        await gd.amove_file(file_id="file-abc-123", new_parent_id="folder-new")
        params = dict(route.calls.last.request.url.params)
        assert params["addParents"] == "folder-new"
        assert params["removeParents"] == "folder-old"


@pytest.mark.asyncio
async def test_copy_file(gd: GoogleDrive) -> None:
    """copy_file: POST /files/{id}/copy → new DriveFile."""
    with respx.mock(base_url="https://www.googleapis.com/drive/v3") as mock:
        route = mock.post("/files/file-abc-123/copy").mock(
            return_value=httpx.Response(200, json={**_FILE, "id": "copy-1"})
        )
        copy = await gd.acopy_file(file_id="file-abc-123", name="Copy of test")
        assert copy.id == "copy-1"
        body = route.calls.last.request.read()
        assert b'"name":"Copy of test"' in body


@pytest.mark.asyncio
async def test_list_permissions(gd: GoogleDrive) -> None:
    """list_permissions: GET /files/{id}/permissions → list[FilePermission]."""
    with respx.mock(base_url="https://www.googleapis.com/drive/v3") as mock:
        mock.get("/files/file-abc-123/permissions").mock(
            return_value=httpx.Response(200, json={"permissions": [_PERM]})
        )
        perms = await gd.alist_permissions(file_id="file-abc-123")
        assert len(perms) == 1
        assert perms[0].role == "reader"


@pytest.mark.asyncio
async def test_get_storage_quota(gd: GoogleDrive) -> None:
    """get_storage_quota: GET /about?fields=storageQuota → StorageQuota.

    Model exposes `limit`, `usage`, `usage_in_drive`, `usage_in_drive_trash`
    as strings (Drive API returns them as decimal strings, not ints,
    because they can exceed 2^31 for unlimited Workspace plans).
    """
    with respx.mock(base_url="https://www.googleapis.com/drive/v3") as mock:
        mock.get("/about").mock(
            return_value=httpx.Response(
                200,
                json={
                    "storageQuota": {
                        "limit": "16106127360",
                        "usage": "1073741824",
                        "usageInDrive": "1000000000",
                        "usageInDriveTrash": "73741824",
                    }
                },
            )
        )
        quota = await gd.aget_storage_quota()
        assert quota.limit == "16106127360"
        assert quota.usage == "1073741824"


@pytest.mark.asyncio
async def test_update_file_metadata(gd: GoogleDrive) -> None:
    """update_file: PATCH /files/{id} with metadata overrides → DriveFile."""
    with respx.mock(base_url="https://www.googleapis.com/drive/v3") as mock:
        route = mock.patch("/files/file-abc-123").mock(
            return_value=httpx.Response(200, json={**_FILE, "name": "renamed.txt"})
        )
        f = await gd.aupdate_file(
            file_id="file-abc-123",
            name="renamed.txt",
            description="new description",
            starred=True,
        )
        assert f.name == "renamed.txt"
        body = route.calls.last.request.read()
        assert b'"name":"renamed.txt"' in body
        assert b'"starred":true' in body


@pytest.mark.asyncio
async def test_export_file_returns_base64_string(gd: GoogleDrive) -> None:
    """export_file: GET /files/{id}/export?mimeType=… → base64-encoded str.

    The connector returns the base64 string directly (not wrapped in
    a FileDownloadResult) because export is read-only — no metadata
    enrichment over the raw bytes.
    """
    with respx.mock() as mock:
        mock.get("https://www.googleapis.com/drive/v3/files/doc-1/export").mock(
            return_value=httpx.Response(200, content=b"PDF content")
        )
        result = await gd.aexport_file(file_id="doc-1", mime_type="application/pdf")
        # Returns the base64-encoded string directly
        assert isinstance(result, str)
        assert base64.b64decode(result) == b"PDF content"


@pytest.mark.asyncio
async def test_empty_trash(gd: GoogleDrive) -> None:
    """empty_trash: DELETE /files/trash → None."""
    with respx.mock(base_url="https://www.googleapis.com/drive/v3") as mock:
        mock.delete("/files/trash").mock(return_value=httpx.Response(204))
        result = await gd.aempty_trash()
        assert result is None


@pytest.mark.asyncio
async def test_list_comments(gd: GoogleDrive) -> None:
    """list_comments: GET /files/{id}/comments → PaginatedList[DriveComment]."""
    with respx.mock(base_url="https://www.googleapis.com/drive/v3") as mock:
        mock.get("/files/file-abc-123/comments").mock(
            return_value=httpx.Response(200, json={"comments": [_COMMENT]})
        )
        page = await gd.alist_comments(file_id="file-abc-123")
        assert len(page.items) == 1
        assert page.items[0].content == "Looks good"


@pytest.mark.asyncio
async def test_create_comment(gd: GoogleDrive) -> None:
    """create_comment: POST /files/{id}/comments with content."""
    with respx.mock(base_url="https://www.googleapis.com/drive/v3") as mock:
        route = mock.post("/files/file-abc-123/comments").mock(
            return_value=httpx.Response(200, json=_COMMENT)
        )
        c = await gd.acreate_comment(file_id="file-abc-123", content="New comment 你好")
        assert c.id == "comment-1"
        body = route.calls.last.request.read()
        # Unicode round-trip
        assert "你好".encode() in body


@pytest.mark.asyncio
async def test_delete_comment(gd: GoogleDrive) -> None:
    """delete_comment: DELETE /files/{id}/comments/{commentId} → None."""
    with respx.mock(base_url="https://www.googleapis.com/drive/v3") as mock:
        mock.delete("/files/file-abc-123/comments/comment-1").mock(return_value=httpx.Response(204))
        result = await gd.adelete_comment(file_id="file-abc-123", comment_id="comment-1")
        assert result is None


@pytest.mark.asyncio
async def test_list_revisions(gd: GoogleDrive) -> None:
    """list_revisions: GET /files/{id}/revisions → PaginatedList[DriveRevision]."""
    with respx.mock(base_url="https://www.googleapis.com/drive/v3") as mock:
        mock.get("/files/file-abc-123/revisions").mock(
            return_value=httpx.Response(200, json={"revisions": [_REV]})
        )
        page = await gd.alist_revisions(file_id="file-abc-123")
        assert len(page.items) == 1
        assert page.items[0].id == "rev-1"


@pytest.mark.asyncio
async def test_get_revision(gd: GoogleDrive) -> None:
    """get_revision: GET /files/{id}/revisions/{revId} → DriveRevision."""
    with respx.mock(base_url="https://www.googleapis.com/drive/v3") as mock:
        mock.get("/files/file-abc-123/revisions/rev-1").mock(
            return_value=httpx.Response(200, json=_REV)
        )
        rev = await gd.aget_revision(file_id="file-abc-123", revision_id="rev-1")
        assert rev.id == "rev-1"


@pytest.mark.asyncio
async def test_get_permission(gd: GoogleDrive) -> None:
    """get_permission: GET /files/{id}/permissions/{permId} → FilePermission."""
    with respx.mock(base_url="https://www.googleapis.com/drive/v3") as mock:
        mock.get("/files/file-abc-123/permissions/perm-1").mock(
            return_value=httpx.Response(200, json=_PERM)
        )
        perm = await gd.aget_permission(file_id="file-abc-123", permission_id="perm-1")
        assert perm.id == "perm-1"


@pytest.mark.asyncio
async def test_delete_permission(gd: GoogleDrive) -> None:
    """delete_permission: DELETE /files/{id}/permissions/{permId} → None."""
    with respx.mock(base_url="https://www.googleapis.com/drive/v3") as mock:
        mock.delete("/files/file-abc-123/permissions/perm-1").mock(return_value=httpx.Response(204))
        result = await gd.adelete_permission(file_id="file-abc-123", permission_id="perm-1")
        assert result is None


# ===========================================================================
# Round 2 — defensive parsing + URL-path guards
# ===========================================================================


@pytest.mark.asyncio
async def test_file_id_with_slash_percent_encoded(gd: GoogleDrive) -> None:
    """Adversarial file_id MUST NOT escape /files/ prefix."""
    with respx.mock(base_url="https://www.googleapis.com/drive/v3") as mock:
        route = mock.get(host="www.googleapis.com").mock(
            return_value=httpx.Response(404, json={"error": {"code": 404, "message": "Not found"}})
        )
        with pytest.raises(NotFoundError):
            await gd.aget_file(file_id="../admin")
        url = str(route.calls.last.request.url)
        assert "/files/" in url
        assert "..%2Fadmin" in url or "..%2fadmin" in url


@pytest.mark.asyncio
async def test_drive_file_model_tolerates_unknown_fields(gd: GoogleDrive) -> None:
    """Real Drive API responses have many fields we don't model.
    extra='ignore' silently drops them."""
    fat = {
        **_FILE,
        "kind": "drive#file",
        "etag": "etag-1",
        "version": "1",
        "spaces": ["drive"],
        "permissions": [],
        "owners": [],
        "lastModifyingUser": {},
        "shared": False,
        "ownedByMe": True,
        "capabilities": {"canEdit": True, "canShare": True},
    }
    with respx.mock(base_url="https://www.googleapis.com/drive/v3") as mock:
        mock.get("/files/file-abc-123").mock(return_value=httpx.Response(200, json=fat))
        f = await gd.aget_file(file_id="file-abc-123")
        assert f.id == "file-abc-123"


# ===========================================================================
# Round 3 — error matrix
# ===========================================================================


@pytest.mark.asyncio
async def test_401_invalid_credentials(gd: GoogleDrive) -> None:
    with respx.mock(base_url="https://www.googleapis.com/drive/v3") as mock:
        mock.get("/files/d").mock(
            return_value=httpx.Response(
                401, json={"error": {"code": 401, "message": "Invalid Credentials"}}
            )
        )
        with pytest.raises(InvalidCredentialsError) as exc_info:
            await gd.aget_file(file_id="d")
        assert exc_info.value.connector == "gdrive"


@pytest.mark.asyncio
async def test_403_permission_denied(gd: GoogleDrive) -> None:
    with respx.mock(base_url="https://www.googleapis.com/drive/v3") as mock:
        mock.get("/files/d").mock(
            return_value=httpx.Response(
                403, json={"error": {"code": 403, "message": "Insufficient Permission"}}
            )
        )
        with pytest.raises(PermissionDeniedError):
            await gd.aget_file(file_id="d")


@pytest.mark.asyncio
async def test_404_not_found(gd: GoogleDrive) -> None:
    with respx.mock(base_url="https://www.googleapis.com/drive/v3") as mock:
        mock.get("/files/missing").mock(
            return_value=httpx.Response(404, json={"error": {"code": 404, "message": "Not Found"}})
        )
        with pytest.raises(NotFoundError):
            await gd.aget_file(file_id="missing")


@pytest.mark.asyncio
async def test_429_rate_limit(gd: GoogleDrive) -> None:
    with respx.mock(base_url="https://www.googleapis.com/drive/v3") as mock:
        mock.get("/files/d").mock(
            return_value=httpx.Response(
                429,
                json={"error": {"code": 429, "message": "Quota exceeded"}},
                headers={"Retry-After": "30"},
            )
        )
        with pytest.raises(RateLimitError):
            await gd.aget_file(file_id="d")


@pytest.mark.asyncio
async def test_500_server_error(gd: GoogleDrive) -> None:
    with respx.mock(base_url="https://www.googleapis.com/drive/v3") as mock:
        mock.get("/files/d").mock(return_value=httpx.Response(500, json={"error": {"code": 500}}))
        with pytest.raises(ServerError):
            await gd.aget_file(file_id="d")


# ===========================================================================
# Round 4 — transport errors
# ===========================================================================


@pytest.mark.asyncio
async def test_connect_error_typed(gd: GoogleDrive) -> None:
    with respx.mock(base_url="https://www.googleapis.com/drive/v3") as mock:
        mock.get("/files/d").mock(side_effect=httpx.ConnectError("DNS"))
        with pytest.raises(TCConnectionError):
            await gd.aget_file(file_id="d")


@pytest.mark.asyncio
async def test_timeout_typed(gd: GoogleDrive) -> None:
    with respx.mock(base_url="https://www.googleapis.com/drive/v3") as mock:
        mock.get("/files/d").mock(side_effect=httpx.ReadTimeout("slow"))
        with pytest.raises(TCTimeoutError):
            await gd.aget_file(file_id="d")


@pytest.mark.asyncio
async def test_transport_error_typed(gd: GoogleDrive) -> None:
    with respx.mock(base_url="https://www.googleapis.com/drive/v3") as mock:
        mock.get("/files/d").mock(side_effect=httpx.RemoteProtocolError("dropped"))
        with pytest.raises(TCTransportError):
            await gd.aget_file(file_id="d")


# ===========================================================================
# Round 5 — MCP + schema + dangerous + sync wrappers + concurrency
# ===========================================================================


def test_dangerous_actions_flagged() -> None:
    """Writes/mutations are dangerous; reads are not."""
    spec = GoogleDrive.get_spec()
    expected_dangerous = {
        "delete_file",
        "share_file",
        "delete_comment",
        "delete_permission",
        "empty_trash",
        "create_comment",
    }
    for a in expected_dangerous:
        assert spec.actions[a].dangerous is True, f"{a} must be dangerous"
    # upload_file is mutating but not flagged dangerous (write but not destructive)
    # update_file likewise — these are LOW-risk writes
    assert spec.actions["get_file"].dangerous is False
    assert spec.actions["list_files"].dangerous is False
    assert spec.actions["download_file"].dangerous is False


def test_openai_schema_sweep() -> None:
    from toolsconnector.serve import ToolKit

    kit = ToolKit(["gdrive"], credentials={"gdrive": "ya29.fake"})
    tools = kit.to_openai_tools()
    assert len(tools) == 22
    for tool in tools:
        assert tool["function"]["name"].startswith("gdrive_")


def test_mcp_exposure_all_22_actions() -> None:
    from toolsconnector.serve import ToolKit

    kit = ToolKit(["gdrive"], credentials={"gdrive": "ya29.fake"})
    names = {t["name"] for t in kit.list_tools()}
    assert len(names) == 22


def test_sync_wrappers_exist() -> None:
    inst = GoogleDrive(credentials="ya29.fake")
    for action_name in (
        "list_files",
        "get_file",
        "upload_file",
        "download_file",
        "create_folder",
        "delete_file",
        "share_file",
    ):
        assert hasattr(inst, action_name)
        assert hasattr(inst, f"a{action_name}")


def test_verification_status_live() -> None:
    assert GoogleDrive.verification_status == "live"
    assert GoogleDrive.get_spec().verification_status == "live"


@pytest.mark.asyncio
async def test_concurrent_get_files(gd: GoogleDrive) -> None:
    with respx.mock(base_url="https://www.googleapis.com/drive/v3") as mock:
        mock.get("/files/a").mock(return_value=httpx.Response(200, json={**_FILE, "id": "a"}))
        mock.get("/files/b").mock(return_value=httpx.Response(200, json={**_FILE, "id": "b"}))
        results = await asyncio.gather(
            gd.aget_file(file_id="a"),
            gd.aget_file(file_id="b"),
        )
        assert results[0].id == "a"
        assert results[1].id == "b"


@pytest.mark.asyncio
async def test_concurrent_get_files_high_fanout_10(gd: GoogleDrive) -> None:
    """10-way concurrent fanout — exercises shared httpx-client + header
    construction under load, and confirms no per-call state leaks
    between coroutines.

    A 2-way test (above) catches the obvious "global mutable buffer"
    bug class; bumping to 10 exercises the asyncio scheduler enough to
    surface ordering-dependent shared-state bugs (e.g., a header dict
    being mutated after enqueue but before dispatch).
    """
    ids = [f"file-{i}" for i in range(10)]
    with respx.mock(base_url="https://www.googleapis.com/drive/v3") as mock:
        for fid in ids:
            mock.get(f"/files/{fid}").mock(
                return_value=httpx.Response(200, json={**_FILE, "id": fid})
            )
        results = await asyncio.gather(*(gd.aget_file(file_id=fid) for fid in ids))
        # Each request must return its OWN id — verifies no cross-coroutine
        # response mixup.
        for expected_id, file in zip(ids, results):
            assert file.id == expected_id


@pytest.mark.asyncio
async def test_concurrent_mixed_actions_5_way(gd: GoogleDrive) -> None:
    """5 distinct actions in flight concurrently — get_file, list_files,
    get_storage_quota, list_comments, list_revisions. Verifies action
    routing inside the connector class doesn't share scratch state
    between dispatched coroutines.
    """
    with respx.mock(base_url="https://www.googleapis.com/drive/v3") as mock:
        mock.get("/files/x").mock(return_value=httpx.Response(200, json={**_FILE, "id": "x"}))
        mock.get("/files", params={"pageSize": "10"}).mock(
            return_value=httpx.Response(200, json={"files": [_FILE], "nextPageToken": None})
        )
        mock.get("/about", params={"fields": "storageQuota"}).mock(
            return_value=httpx.Response(
                200, json={"storageQuota": {"limit": "100", "usage": "10", "usageInDrive": "10"}}
            )
        )
        mock.get("/files/x/comments").mock(
            return_value=httpx.Response(200, json={"comments": [_COMMENT]})
        )
        mock.get("/files/x/revisions").mock(
            return_value=httpx.Response(200, json={"revisions": [_REV]})
        )
        results = await asyncio.gather(
            gd.aget_file(file_id="x"),
            gd.alist_files(page_size=10),
            gd.aget_storage_quota(),
            gd.alist_comments(file_id="x"),
            gd.alist_revisions(file_id="x"),
        )
        # Each result must have the right shape for its action — no swaps
        assert results[0].id == "x"  # DriveFile
        assert len(results[1].items) == 1  # PaginatedList
        assert results[2].limit == "100"  # StorageQuota (string per Drive API)
        assert len(results[3].items) == 1  # PaginatedList[Comment]
        assert len(results[4].items) == 1  # PaginatedList[Revision]
