"""Google Drive connector -- manage files and folders via the Drive REST API v3.

Uses httpx for direct HTTP calls against the Google Drive REST API.
Expects an OAuth 2.0 access token passed as ``credentials``.
"""

from __future__ import annotations

import base64
from typing import Any, Optional

import httpx

from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import ConnectorCategory, ProtocolType, RateLimitSpec
from toolsconnector.types import PageState, PaginatedList

from .types import (
    DriveComment,
    DriveFile,
    DriveRevision,
    DriveUser,
    FileDownloadResult,
    FilePermission,
    FileUploadResult,
    FolderId,
    StorageQuota,
)

# Default fields to request from the Drive API for file metadata
_FILE_FIELDS = (
    "id,name,mimeType,description,starred,trashed,size,"
    "createdTime,modifiedTime,parents,webViewLink,webContentLink,"
    "iconLink,owners(displayName,emailAddress,photoLink),shared"
)


def _parse_file(data: dict[str, Any]) -> DriveFile:
    """Parse a Drive API file resource into a DriveFile model.

    Args:
        data: Raw JSON dict from the Drive API.

    Returns:
        Populated DriveFile instance.
    """
    owners_raw = data.get("owners", [])
    owners = [
        DriveUser(
            display_name=o.get("displayName", ""),
            email_address=o.get("emailAddress"),
            photo_link=o.get("photoLink"),
        )
        for o in owners_raw
    ]

    size_raw = data.get("size")
    size_val = int(size_raw) if size_raw is not None else None

    return DriveFile(
        id=data.get("id", ""),
        name=data.get("name", ""),
        mime_type=data.get("mimeType", ""),
        description=data.get("description"),
        starred=data.get("starred", False),
        trashed=data.get("trashed", False),
        size=size_val,
        created_time=data.get("createdTime"),
        modified_time=data.get("modifiedTime"),
        parents=data.get("parents", []),
        web_view_link=data.get("webViewLink"),
        web_content_link=data.get("webContentLink"),
        icon_link=data.get("iconLink"),
        owners=owners,
        shared=data.get("shared", False),
    )


class GoogleDrive(BaseConnector):
    """Connect to Google Drive to manage files and folders.

    Supports OAuth 2.0 authentication. Pass an access token as
    ``credentials`` when instantiating. Uses the Drive REST API v3
    via direct httpx calls.
    """

    name = "gdrive"
    display_name = "Google Drive"
    category = ConnectorCategory.STORAGE
    protocol = ProtocolType.REST
    base_url = "https://www.googleapis.com/drive/v3"
    description = "Connect to Google Drive to manage files and folders."
    _rate_limit_config = RateLimitSpec(rate=600, period=60, burst=100)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_headers(self) -> dict[str, str]:
        """Build authorization headers for Drive API requests.

        Returns:
            Dict with Authorization bearer header.
        """
        return {"Authorization": f"Bearer {self._credentials}"}

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """Execute an authenticated HTTP request against the Drive API.

        Args:
            method: HTTP method (GET, POST, PATCH, DELETE, etc.).
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
            response.raise_for_status()
            if response.status_code == 204 or not response.content:
                return {}
            return response.json()

    async def _request_raw(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Execute an authenticated HTTP request returning the raw response.

        Used for file downloads and uploads that require binary handling.

        Args:
            method: HTTP method.
            url: Full URL (not relative path).
            **kwargs: Additional keyword arguments passed to httpx.

        Returns:
            Raw httpx Response object.

        Raises:
            httpx.HTTPStatusError: If the API returns a non-2xx status.
        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.request(
                method,
                url,
                headers=self._get_headers(),
                **kwargs,
            )
            response.raise_for_status()
            return response

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    @action("List files in Google Drive", requires_scope="read")
    async def list_files(
        self,
        page_size: int = 20,
        order_by: str = "modifiedTime desc",
        page_token: Optional[str] = None,
        folder_id: Optional[str] = None,
    ) -> PaginatedList[DriveFile]:
        """List files in the user's Google Drive.

        Args:
            page_size: Maximum number of files to return per page (max 1000).
            order_by: Sort order (e.g., 'modifiedTime desc', 'name').
            page_token: Token for fetching the next page of results.
            folder_id: If provided, list only files in this folder.

        Returns:
            Paginated list of DriveFile objects.
        """
        params: dict[str, Any] = {
            "pageSize": min(page_size, 1000),
            "orderBy": order_by,
            "fields": f"nextPageToken,incompleteSearch,files({_FILE_FIELDS})",
        }
        if page_token:
            params["pageToken"] = page_token
        if folder_id:
            params["q"] = f"'{folder_id}' in parents and trashed = false"

        data = await self._request("GET", "/files", params=params)

        files = [_parse_file(f) for f in data.get("files", [])]
        next_token = data.get("nextPageToken")

        return PaginatedList(
            items=files,
            page_state=PageState(
                cursor=next_token,
                has_more=next_token is not None,
            ),
        )

    @action("Get file metadata by ID", requires_scope="read")
    async def get_file(self, file_id: str) -> DriveFile:
        """Retrieve metadata for a single file.

        Args:
            file_id: The ID of the file to retrieve.

        Returns:
            DriveFile with full metadata.
        """
        data = await self._request(
            "GET",
            f"/files/{file_id}",
            params={"fields": _FILE_FIELDS},
        )
        return _parse_file(data)

    @action("Upload a file to Google Drive", requires_scope="write")
    async def upload_file(
        self,
        name: str,
        content_base64: str,
        mime_type: str = "application/octet-stream",
        parent_folder_id: Optional[str] = None,
        description: Optional[str] = None,
    ) -> FileUploadResult:
        """Upload a file to Google Drive using multipart upload.

        The file content must be provided as a base64-encoded string.

        Args:
            name: The filename for the uploaded file.
            content_base64: Base64-encoded file content.
            mime_type: MIME type of the file.
            parent_folder_id: Optional parent folder ID.
            description: Optional file description.

        Returns:
            FileUploadResult with the created file's metadata.
        """
        import json as json_mod

        metadata: dict[str, Any] = {"name": name, "mimeType": mime_type}
        if parent_folder_id:
            metadata["parents"] = [parent_folder_id]
        if description:
            metadata["description"] = description

        file_bytes = base64.b64decode(content_base64)

        # Use multipart upload endpoint
        upload_url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart"

        # Build multipart body manually for proper boundary handling
        boundary = "toolsconnector_boundary"
        body_parts = [
            f"--{boundary}\r\n"
            f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
            f"{json_mod.dumps(metadata)}\r\n"
            f"--{boundary}\r\n"
            f"Content-Type: {mime_type}\r\n"
            f"Content-Transfer-Encoding: base64\r\n\r\n".encode(),
            file_bytes,
            f"\r\n--{boundary}--".encode(),
        ]

        content = body_parts[0] if isinstance(body_parts[0], bytes) else body_parts[0].encode("utf-8")
        content += body_parts[1] + body_parts[2]

        headers = self._get_headers()
        headers["Content-Type"] = f"multipart/related; boundary={boundary}"

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(upload_url, headers=headers, content=content)
            response.raise_for_status()
            data = response.json()

        return FileUploadResult(
            id=data.get("id", ""),
            name=data.get("name", ""),
            mime_type=data.get("mimeType", ""),
            size=int(data["size"]) if data.get("size") else None,
            web_view_link=data.get("webViewLink"),
        )

    @action("Download a file from Google Drive", requires_scope="read")
    async def download_file(self, file_id: str) -> FileDownloadResult:
        """Download a file's content from Google Drive.

        Returns the file content as a base64-encoded string in the
        response model. For Google Workspace files (Docs, Sheets, etc.),
        use the export MIME type parameter.

        Args:
            file_id: The ID of the file to download.

        Returns:
            FileDownloadResult with metadata and base64-encoded content.
        """
        # First, get file metadata
        meta = await self._request(
            "GET",
            f"/files/{file_id}",
            params={"fields": "id,name,mimeType,size"},
        )

        # Download the file content
        download_url = f"{self._base_url}/files/{file_id}?alt=media"
        response = await self._request_raw("GET", download_url)
        content_b64 = base64.b64encode(response.content).decode("ascii")

        size_raw = meta.get("size")
        size_val = int(size_raw) if size_raw is not None else len(response.content)

        return FileDownloadResult(
            id=meta.get("id", ""),
            name=meta.get("name", ""),
            mime_type=meta.get("mimeType", ""),
            size=size_val,
            content_base64=content_b64,
        )

    @action("Create a folder in Google Drive", requires_scope="write")
    async def create_folder(
        self,
        name: str,
        parent_folder_id: Optional[str] = None,
        description: Optional[str] = None,
    ) -> FolderId:
        """Create a new folder in Google Drive.

        Args:
            name: Name of the folder to create.
            parent_folder_id: Optional parent folder ID.
            description: Optional folder description.

        Returns:
            FolderId with the created folder's ID and metadata.
        """
        metadata: dict[str, Any] = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        if parent_folder_id:
            metadata["parents"] = [parent_folder_id]
        if description:
            metadata["description"] = description

        data = await self._request(
            "POST",
            "/files",
            json=metadata,
            params={"fields": "id,name,webViewLink"},
        )

        return FolderId(
            id=data.get("id", ""),
            name=data.get("name", ""),
            web_view_link=data.get("webViewLink"),
        )

    @action("Delete a file from Google Drive", requires_scope="write", dangerous=True)
    async def delete_file(self, file_id: str) -> None:
        """Permanently delete a file or folder from Google Drive.

        Args:
            file_id: The ID of the file or folder to delete.

        Warning:
            This action permanently deletes the file. It cannot be undone.
        """
        await self._request("DELETE", f"/files/{file_id}")

    @action("Search files in Google Drive", requires_scope="read")
    async def search_files(
        self,
        query: str,
        page_size: int = 20,
        page_token: Optional[str] = None,
    ) -> PaginatedList[DriveFile]:
        """Search for files using Drive query syntax.

        Supports the full Drive query language. Common examples:
        - ``name contains 'report'``
        - ``mimeType = 'application/pdf'``
        - ``modifiedTime > '2024-01-01T00:00:00'``
        - ``fullText contains 'budget'``
        - ``'folder_id' in parents``

        Args:
            query: Drive search query string.
            page_size: Maximum number of results per page.
            page_token: Pagination token for next page.

        Returns:
            Paginated list of matching DriveFile objects.
        """
        params: dict[str, Any] = {
            "q": query,
            "pageSize": min(page_size, 1000),
            "fields": f"nextPageToken,files({_FILE_FIELDS})",
        }
        if page_token:
            params["pageToken"] = page_token

        data = await self._request("GET", "/files", params=params)

        files = [_parse_file(f) for f in data.get("files", [])]
        next_token = data.get("nextPageToken")

        return PaginatedList(
            items=files,
            page_state=PageState(
                cursor=next_token,
                has_more=next_token is not None,
            ),
        )

    @action("Share a file with a user or group", requires_scope="write", dangerous=True)
    async def share_file(
        self,
        file_id: str,
        email: str,
        role: str = "reader",
        type: str = "user",
        send_notification: bool = True,
        message: Optional[str] = None,
    ) -> FilePermission:
        """Share a file by creating a permission entry.

        Args:
            file_id: The ID of the file to share.
            email: Email address of the user or group to share with.
            role: Permission role: 'reader', 'commenter', 'writer', or 'organizer'.
            type: Permission type: 'user', 'group', 'domain', or 'anyone'.
            send_notification: Whether to send an email notification.
            message: Optional message to include in the notification email.

        Returns:
            FilePermission with the created permission details.
        """
        permission_body: dict[str, Any] = {
            "type": type,
            "role": role,
            "emailAddress": email,
        }

        params: dict[str, Any] = {
            "sendNotificationEmail": str(send_notification).lower(),
            "fields": "id,type,role,emailAddress,displayName,domain",
        }
        if message:
            params["emailMessage"] = message

        data = await self._request(
            "POST",
            f"/files/{file_id}/permissions",
            json=permission_body,
            params=params,
        )

        return FilePermission(
            id=data.get("id", ""),
            type=data.get("type", type),
            role=data.get("role", role),
            email_address=data.get("emailAddress"),
            display_name=data.get("displayName"),
            domain=data.get("domain"),
        )

    # ------------------------------------------------------------------
    # Actions — File operations (extended)
    # ------------------------------------------------------------------

    @action("Move a file to a different folder")
    async def move_file(
        self, file_id: str, new_parent_id: str,
    ) -> DriveFile:
        """Move a file to a different folder.

        Args:
            file_id: The ID of the file to move.
            new_parent_id: The ID of the destination folder.

        Returns:
            The updated DriveFile in its new location.
        """
        # Get current parents to remove
        current = await self._request(
            "GET", f"/files/{file_id}",
            params={"fields": "parents"},
        )
        previous_parents = ",".join(current.get("parents", []))

        data = await self._request(
            "PATCH", f"/files/{file_id}",
            params={
                "addParents": new_parent_id,
                "removeParents": previous_parents,
                "fields": "id,name,mimeType,parents,modifiedTime,webViewLink",
            },
        )
        return _parse_file(data)

    @action("Copy a file")
    async def copy_file(
        self,
        file_id: str,
        name: Optional[str] = None,
    ) -> DriveFile:
        """Create a copy of a file.

        Args:
            file_id: The ID of the file to copy.
            name: Optional name for the copy. Defaults to original name.

        Returns:
            The newly created DriveFile copy.
        """
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        data = await self._request(
            "POST", f"/files/{file_id}/copy",
            json=body or None,
            params={"fields": _FILE_FIELDS},
        )
        return _parse_file(data)

    @action("List permissions on a file")
    async def list_permissions(
        self, file_id: str,
    ) -> list[FilePermission]:
        """List all permissions on a file.

        Args:
            file_id: The ID of the file.

        Returns:
            List of FilePermission objects.
        """
        data = await self._request(
            "GET", f"/files/{file_id}/permissions",
            params={"fields": "permissions(id,type,role,emailAddress,displayName,domain)"},
        )
        return [
            FilePermission(
                id=p.get("id", ""),
                type=p.get("type", ""),
                role=p.get("role", ""),
                email_address=p.get("emailAddress"),
                display_name=p.get("displayName"),
                domain=p.get("domain"),
            )
            for p in data.get("permissions", [])
        ]

    @action("Get storage quota information")
    async def get_storage_quota(self) -> StorageQuota:
        """Get the authenticated user's storage quota.

        Returns:
            StorageQuota with usage and limit information.
        """
        data = await self._request(
            "GET", "/about",
            params={"fields": "storageQuota"},
        )
        quota = data.get("storageQuota", {})
        return StorageQuota(
            limit=quota.get("limit"),
            usage=quota.get("usage"),
            usage_in_drive=quota.get("usageInDrive"),
            usage_in_drive_trash=quota.get("usageInDriveTrash"),
        )

    # ------------------------------------------------------------------
    # Actions — File metadata updates
    # ------------------------------------------------------------------

    @action("Update file metadata", requires_scope="write")
    async def update_file(
        self,
        file_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        starred: Optional[bool] = None,
    ) -> DriveFile:
        """Update metadata for a file.

        Only provided fields will be updated. Uses PATCH semantics.

        Args:
            file_id: The ID of the file to update.
            name: New filename.
            description: New file description.
            starred: Whether to star / unstar the file.

        Returns:
            The updated DriveFile.
        """
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        if starred is not None:
            body["starred"] = starred

        data = await self._request(
            "PATCH",
            f"/files/{file_id}",
            json=body,
            params={"fields": _FILE_FIELDS},
        )
        return _parse_file(data)

    @action("Export a Google Workspace file", requires_scope="read")
    async def export_file(
        self,
        file_id: str,
        mime_type: str,
    ) -> str:
        """Export a Google Workspace file to the requested MIME type.

        Use this to convert Google Docs, Sheets, Slides, etc. into
        downloadable formats such as PDF, DOCX, CSV, PPTX, etc.

        Args:
            file_id: The ID of the Google Workspace file to export.
            mime_type: Target MIME type (e.g., 'application/pdf',
                'text/csv', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document').

        Returns:
            Base64-encoded string of the exported file content.
        """
        export_url = f"{self._base_url}/files/{file_id}/export"
        response = await self._request_raw(
            "GET",
            export_url,
            params={"mimeType": mime_type},
        )
        return base64.b64encode(response.content).decode("ascii")

    @action("Empty the trash", requires_scope="write", dangerous=True)
    async def empty_trash(self) -> None:
        """Permanently delete all files in the user's trash.

        Warning:
            This action permanently deletes every file currently in the
            trash. It cannot be undone.
        """
        await self._request("DELETE", "/files/trash")

    # ------------------------------------------------------------------
    # Actions — Comments
    # ------------------------------------------------------------------

    @action("List comments on a file", requires_scope="read")
    async def list_comments(
        self,
        file_id: str,
        page_size: int = 20,
        page_token: Optional[str] = None,
    ) -> PaginatedList[DriveComment]:
        """List comments on a file.

        Args:
            file_id: The ID of the file.
            page_size: Maximum number of comments per page (max 100).
            page_token: Token for fetching the next page of results.

        Returns:
            Paginated list of DriveComment objects.
        """
        params: dict[str, Any] = {
            "pageSize": min(page_size, 100),
            "fields": (
                "nextPageToken,"
                "comments(id,content,htmlContent,author(displayName,emailAddress,photoLink),"
                "createdTime,modifiedTime,resolved)"
            ),
        }
        if page_token:
            params["pageToken"] = page_token

        data = await self._request(
            "GET",
            f"/files/{file_id}/comments",
            params=params,
        )

        comments: list[DriveComment] = []
        for c in data.get("comments", []):
            author = c.get("author", {})
            comments.append(
                DriveComment(
                    id=c.get("id", ""),
                    content=c.get("content", ""),
                    author_display_name=author.get("displayName"),
                    author_email=author.get("emailAddress"),
                    author_photo_link=author.get("photoLink"),
                    created_time=c.get("createdTime"),
                    modified_time=c.get("modifiedTime"),
                    resolved=c.get("resolved", False),
                    html_content=c.get("htmlContent"),
                )
            )

        next_token = data.get("nextPageToken")
        return PaginatedList(
            items=comments,
            page_state=PageState(
                cursor=next_token,
                has_more=next_token is not None,
            ),
        )

    @action("Create a comment on a file", requires_scope="write", dangerous=True)
    async def create_comment(
        self,
        file_id: str,
        content: str,
    ) -> DriveComment:
        """Create a comment on a file.

        Args:
            file_id: The ID of the file to comment on.
            content: The plain-text content of the comment.

        Returns:
            The created DriveComment.
        """
        data = await self._request(
            "POST",
            f"/files/{file_id}/comments",
            json={"content": content},
            params={
                "fields": (
                    "id,content,htmlContent,"
                    "author(displayName,emailAddress,photoLink),"
                    "createdTime,modifiedTime,resolved"
                ),
            },
        )
        author = data.get("author", {})
        return DriveComment(
            id=data.get("id", ""),
            content=data.get("content", ""),
            author_display_name=author.get("displayName"),
            author_email=author.get("emailAddress"),
            author_photo_link=author.get("photoLink"),
            created_time=data.get("createdTime"),
            modified_time=data.get("modifiedTime"),
            resolved=data.get("resolved", False),
            html_content=data.get("htmlContent"),
        )

    @action("Delete a comment from a file", requires_scope="write", dangerous=True)
    async def delete_comment(
        self,
        file_id: str,
        comment_id: str,
    ) -> None:
        """Delete a comment from a file.

        Args:
            file_id: The ID of the file containing the comment.
            comment_id: The ID of the comment to delete.

        Warning:
            This action permanently deletes the comment. It cannot be undone.
        """
        await self._request("DELETE", f"/files/{file_id}/comments/{comment_id}")

    # ------------------------------------------------------------------
    # Actions — Revisions
    # ------------------------------------------------------------------

    @action("List revisions of a file", requires_scope="read")
    async def list_revisions(
        self,
        file_id: str,
        page_size: int = 20,
        page_token: Optional[str] = None,
    ) -> PaginatedList[DriveRevision]:
        """List revisions (version history) of a file.

        Args:
            file_id: The ID of the file.
            page_size: Maximum number of revisions per page (max 1000).
            page_token: Token for fetching the next page of results.

        Returns:
            Paginated list of DriveRevision objects.
        """
        params: dict[str, Any] = {
            "pageSize": min(page_size, 1000),
            "fields": (
                "nextPageToken,"
                "revisions(id,mimeType,modifiedTime,keepForever,published,"
                "size,lastModifyingUser(displayName,emailAddress),originalFilename)"
            ),
        }
        if page_token:
            params["pageToken"] = page_token

        data = await self._request(
            "GET",
            f"/files/{file_id}/revisions",
            params=params,
        )

        revisions: list[DriveRevision] = []
        for r in data.get("revisions", []):
            lmu = r.get("lastModifyingUser", {})
            size_raw = r.get("size")
            revisions.append(
                DriveRevision(
                    id=r.get("id", ""),
                    mime_type=r.get("mimeType"),
                    modified_time=r.get("modifiedTime"),
                    keep_forever=r.get("keepForever", False),
                    published=r.get("published", False),
                    size=int(size_raw) if size_raw is not None else None,
                    last_modifying_user_display_name=lmu.get("displayName"),
                    last_modifying_user_email=lmu.get("emailAddress"),
                    original_filename=r.get("originalFilename"),
                )
            )

        next_token = data.get("nextPageToken")
        return PaginatedList(
            items=revisions,
            page_state=PageState(
                cursor=next_token,
                has_more=next_token is not None,
            ),
        )

    @action("Get a specific revision of a file", requires_scope="read")
    async def get_revision(
        self,
        file_id: str,
        revision_id: str,
    ) -> DriveRevision:
        """Retrieve metadata for a specific file revision.

        Args:
            file_id: The ID of the file.
            revision_id: The ID of the revision.

        Returns:
            The requested DriveRevision.
        """
        data = await self._request(
            "GET",
            f"/files/{file_id}/revisions/{revision_id}",
            params={
                "fields": (
                    "id,mimeType,modifiedTime,keepForever,published,"
                    "size,lastModifyingUser(displayName,emailAddress),"
                    "originalFilename"
                ),
            },
        )
        lmu = data.get("lastModifyingUser", {})
        size_raw = data.get("size")
        return DriveRevision(
            id=data.get("id", ""),
            mime_type=data.get("mimeType"),
            modified_time=data.get("modifiedTime"),
            keep_forever=data.get("keepForever", False),
            published=data.get("published", False),
            size=int(size_raw) if size_raw is not None else None,
            last_modifying_user_display_name=lmu.get("displayName"),
            last_modifying_user_email=lmu.get("emailAddress"),
            original_filename=data.get("originalFilename"),
        )

    # ------------------------------------------------------------------
    # Actions — Permissions (extended)
    # ------------------------------------------------------------------

    @action("Get a specific permission on a file", requires_scope="read")
    async def get_permission(
        self,
        file_id: str,
        permission_id: str,
    ) -> FilePermission:
        """Retrieve a specific permission on a file.

        Args:
            file_id: The ID of the file.
            permission_id: The ID of the permission entry.

        Returns:
            The requested FilePermission.
        """
        data = await self._request(
            "GET",
            f"/files/{file_id}/permissions/{permission_id}",
            params={
                "fields": "id,type,role,emailAddress,displayName,domain",
            },
        )
        return FilePermission(
            id=data.get("id", ""),
            type=data.get("type", ""),
            role=data.get("role", ""),
            email_address=data.get("emailAddress"),
            display_name=data.get("displayName"),
            domain=data.get("domain"),
        )

    @action("Delete a permission from a file", requires_scope="write", dangerous=True)
    async def delete_permission(
        self,
        file_id: str,
        permission_id: str,
    ) -> None:
        """Delete a permission from a file, revoking access.

        Args:
            file_id: The ID of the file.
            permission_id: The ID of the permission to delete.

        Warning:
            This revokes the user's or group's access to the file
            immediately. It cannot be undone.
        """
        await self._request(
            "DELETE",
            f"/files/{file_id}/permissions/{permission_id}",
        )
