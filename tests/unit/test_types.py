"""Unit tests for the types/ module."""

from __future__ import annotations

import asyncio

import pytest

from toolsconnector.types import PaginatedList, PageState, FileRef, CredentialSet
from toolsconnector.types.file import InMemoryStorageBackend
from toolsconnector.spec.auth import AuthType
from pydantic import BaseModel


class Item(BaseModel):
    id: str
    name: str


class TestPageState:
    def test_defaults(self):
        ps = PageState()
        assert ps.cursor is None
        assert ps.has_more is False

    def test_with_cursor(self):
        ps = PageState(cursor="abc123", has_more=True)
        assert ps.cursor == "abc123"
        assert ps.has_more is True


class TestPaginatedList:
    def test_empty_list(self):
        pl = PaginatedList[Item](items=[])
        assert len(pl) == 0
        assert pl.has_more is False

    def test_with_items(self):
        items = [Item(id="1", name="First"), Item(id="2", name="Second")]
        pl = PaginatedList[Item](
            items=items,
            page_state=PageState(has_more=True, cursor="next"),
        )
        assert len(pl) == 2
        assert pl.has_more is True

    def test_iteration(self):
        items = [Item(id=str(i), name=f"Item {i}") for i in range(5)]
        pl = PaginatedList[Item](items=items)
        collected = list(pl)
        assert len(collected) == 5

    def test_total_count(self):
        pl = PaginatedList[Item](items=[], total_count=100)
        assert pl.total_count == 100


class TestFileRef:
    def test_create(self):
        fr = FileRef(
            uri="s3://bucket/file.pdf",
            filename="file.pdf",
            mime_type="application/pdf",
            size_bytes=1024,
        )
        assert fr.uri == "s3://bucket/file.pdf"
        assert fr.filename == "file.pdf"
        assert fr.size_bytes == 1024

    def test_json_schema(self):
        schema = FileRef.model_json_schema()
        assert "properties" in schema
        assert "uri" in schema["properties"]


class TestInMemoryStorageBackend:
    def test_write_and_read(self):
        backend = InMemoryStorageBackend()

        async def _test():
            async def data_stream():
                yield b"hello "
                yield b"world"

            ref = await backend.write("mem://test.txt", data_stream(), "text/plain")
            assert ref.uri == "mem://test.txt"
            assert ref.size_bytes == 11

            chunks = []
            async for chunk in backend.read("mem://test.txt"):
                chunks.append(chunk)
            assert b"".join(chunks) == b"hello world"

        asyncio.run(_test())

    def test_exists_and_delete(self):
        backend = InMemoryStorageBackend()

        async def _test():
            async def data_stream():
                yield b"data"

            await backend.write("mem://f.txt", data_stream(), "text/plain")
            assert await backend.exists("mem://f.txt")
            await backend.delete("mem://f.txt")
            assert not await backend.exists("mem://f.txt")

        asyncio.run(_test())

    def test_read_nonexistent(self):
        backend = InMemoryStorageBackend()

        async def _test():
            with pytest.raises(FileNotFoundError):
                async for _ in backend.read("mem://nope.txt"):
                    pass

        asyncio.run(_test())


class TestCredentialSet:
    def test_api_key(self):
        cred = CredentialSet(auth_type=AuthType.API_KEY, api_key="test-key")
        assert cred.api_key == "test-key"

    def test_oauth2(self):
        cred = CredentialSet(
            auth_type=AuthType.OAUTH2,
            client_id="cid",
            client_secret="csecret",
            refresh_token="rt",
        )
        assert cred.client_id == "cid"
