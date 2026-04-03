"""File reference types and storage backend abstractions."""

from __future__ import annotations

import io
from pathlib import Path
from typing import AsyncIterator, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class FileRef(BaseModel):
    """Universal file reference.

    Represents a pointer to a file stored in any backend (local filesystem,
    S3, GCS, etc.).  ``FileRef`` is intentionally immutable so it can be
    safely passed across threads and serialised into JSON responses.

    Attributes:
        uri: URI identifying the file location (e.g.
            ``"s3://bucket/file.pdf"``, ``"file:///tmp/doc.pdf"``).
        filename: Human-readable filename including extension.
        mime_type: IANA media type (e.g. ``"application/pdf"``).
        size_bytes: File size in bytes, if known.
        metadata: Arbitrary key-value metadata attached to the file.
    """

    model_config = ConfigDict(frozen=True)

    uri: str
    filename: str
    mime_type: str
    size_bytes: int | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Storage backend protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class StorageBackend(Protocol):
    """Protocol that storage backends must implement.

    Connectors that deal with file uploads/downloads accept any object
    satisfying this protocol, allowing callers to plug in local-disk,
    S3, GCS, or in-memory backends interchangeably.
    """

    async def read(self, uri: str) -> AsyncIterator[bytes]:
        """Read the contents of a file as an async byte stream.

        Args:
            uri: URI of the file to read.

        Yields:
            Chunks of bytes from the file.
        """
        ...  # pragma: no cover

    async def write(
        self,
        uri: str,
        stream: AsyncIterator[bytes],
        mime_type: str,
    ) -> FileRef:
        """Write an async byte stream to a file.

        Args:
            uri: Target URI for the file.
            stream: Async iterator of byte chunks to write.
            mime_type: IANA media type of the content being written.

        Returns:
            A :class:`FileRef` pointing to the newly written file.
        """
        ...  # pragma: no cover

    async def exists(self, uri: str) -> bool:
        """Check whether a file exists at the given URI.

        Args:
            uri: URI to check.

        Returns:
            ``True`` if the file exists, ``False`` otherwise.
        """
        ...  # pragma: no cover

    async def delete(self, uri: str) -> None:
        """Delete the file at the given URI.

        Args:
            uri: URI of the file to delete.

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        ...  # pragma: no cover


# ---------------------------------------------------------------------------
# Concrete backends
# ---------------------------------------------------------------------------


class InMemoryStorageBackend:
    """In-memory storage backend for testing.

    Stores file contents in a plain ``dict`` keyed by URI.  Useful in
    unit tests and development environments where real I/O is undesirable.
    """

    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}
        self._mime_types: dict[str, str] = {}

    async def read(self, uri: str) -> AsyncIterator[bytes]:
        """Read stored bytes for *uri*.

        Args:
            uri: URI of the file to read.

        Yields:
            The complete file content as a single chunk.

        Raises:
            FileNotFoundError: If *uri* has not been written to this backend.
        """
        if uri not in self._store:
            raise FileNotFoundError(f"No file stored at {uri}")
        yield self._store[uri]

    async def write(
        self,
        uri: str,
        stream: AsyncIterator[bytes],
        mime_type: str,
    ) -> FileRef:
        """Write *stream* into memory under *uri*.

        Args:
            uri: Target URI.
            stream: Async iterator of byte chunks to store.
            mime_type: IANA media type of the content.

        Returns:
            A :class:`FileRef` describing the stored file.
        """
        buffer = io.BytesIO()
        async for chunk in stream:
            buffer.write(chunk)

        data = buffer.getvalue()
        self._store[uri] = data
        self._mime_types[uri] = mime_type

        filename = uri.rsplit("/", maxsplit=1)[-1] if "/" in uri else uri
        return FileRef(
            uri=uri,
            filename=filename,
            mime_type=mime_type,
            size_bytes=len(data),
        )

    async def exists(self, uri: str) -> bool:
        """Check if *uri* exists in memory.

        Args:
            uri: URI to check.

        Returns:
            ``True`` if the URI has been written to this backend.
        """
        return uri in self._store

    async def delete(self, uri: str) -> None:
        """Remove *uri* from memory.

        Args:
            uri: URI to delete.

        Raises:
            FileNotFoundError: If *uri* does not exist in this backend.
        """
        if uri not in self._store:
            raise FileNotFoundError(f"No file stored at {uri}")
        del self._store[uri]
        self._mime_types.pop(uri, None)


class LocalStorageBackend:
    """Local filesystem storage backend.

    Reads and writes files on the local disk.  URIs are expected to use
    the ``file://`` scheme (e.g. ``file:///tmp/uploads/report.pdf``).  The
    scheme prefix is stripped when resolving paths.

    Args:
        base_path: Optional base directory.  When provided, relative paths
            derived from URIs are resolved against this directory.
    """

    def __init__(self, base_path: str | Path | None = None) -> None:
        self._base_path: Path | None = Path(base_path) if base_path else None

    def _resolve(self, uri: str) -> Path:
        """Resolve a URI to a local filesystem path.

        Args:
            uri: The file URI to resolve.

        Returns:
            An absolute :class:`Path` on the local filesystem.
        """
        # Strip the file:// scheme if present.
        path_str = uri
        if path_str.startswith("file://"):
            path_str = path_str[len("file://") :]

        path = Path(path_str)
        if self._base_path and not path.is_absolute():
            path = self._base_path / path
        return path

    async def read(self, uri: str) -> AsyncIterator[bytes]:
        """Read a local file as an async byte stream.

        Args:
            uri: ``file://`` URI or local path of the file to read.

        Yields:
            Byte chunks of size 64 KiB.

        Raises:
            FileNotFoundError: If the resolved path does not exist.
        """
        path = self._resolve(uri)
        if not path.exists():
            raise FileNotFoundError(f"No file at {path}")

        with open(path, mode="rb") as fh:
            while True:
                chunk = fh.read(65_536)
                if not chunk:
                    break
                yield chunk

    async def write(
        self,
        uri: str,
        stream: AsyncIterator[bytes],
        mime_type: str,
    ) -> FileRef:
        """Write an async byte stream to a local file.

        Creates parent directories as needed.

        Args:
            uri: ``file://`` URI or local path for the destination.
            stream: Async iterator of byte chunks to write.
            mime_type: IANA media type of the content.

        Returns:
            A :class:`FileRef` describing the written file.
        """
        path = self._resolve(uri)
        path.parent.mkdir(parents=True, exist_ok=True)

        total_bytes = 0
        with open(path, mode="wb") as fh:
            async for chunk in stream:
                fh.write(chunk)
                total_bytes += len(chunk)

        return FileRef(
            uri=uri,
            filename=path.name,
            mime_type=mime_type,
            size_bytes=total_bytes,
        )

    async def exists(self, uri: str) -> bool:
        """Check whether a local file exists.

        Args:
            uri: ``file://`` URI or local path to check.

        Returns:
            ``True`` if the file exists on disk.
        """
        return self._resolve(uri).exists()

    async def delete(self, uri: str) -> None:
        """Delete a local file.

        Args:
            uri: ``file://`` URI or local path to delete.

        Raises:
            FileNotFoundError: If the resolved path does not exist.
        """
        path = self._resolve(uri)
        if not path.exists():
            raise FileNotFoundError(f"No file at {path}")
        path.unlink()
