"""Unit tests for the types/ module."""

from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel

from toolsconnector.errors import PaginationNotWiredError
from toolsconnector.spec.auth import AuthType
from toolsconnector.types import CredentialSet, FileRef, PageState, PaginatedList
from toolsconnector.types.file import InMemoryStorageBackend


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

    @pytest.mark.asyncio
    async def test_collect_stall_guard_terminates_on_empty_pages(self):
        """A page advertising has_more=True but returning NO items must not loop forever.

        Regression guard for the shared pagination hang found by chaos testing
        (codevira D000009). ``asyncio.wait_for`` makes a regression fail fast
        instead of hanging the whole suite.
        """

        async def fetch_empty() -> PaginatedList[Item]:
            nxt = PaginatedList[Item](items=[], page_state=PageState(has_more=True))
            nxt._fetch_next = fetch_empty  # always "more", always empty
            return nxt

        pl = PaginatedList[Item](
            items=[Item(id="1", name="A")], page_state=PageState(has_more=True)
        )
        pl._fetch_next = fetch_empty
        collected = await asyncio.wait_for(pl.collect(), timeout=5.0)
        assert [i.id for i in collected] == ["1"]  # initial page only; empty page is terminal

    @pytest.mark.asyncio
    async def test_collect_max_pages_ceiling(self):
        """max_pages bounds total fetches even when every page is non-empty + has_more=True."""

        async def fetch_one() -> PaginatedList[Item]:
            nxt = PaginatedList[Item](
                items=[Item(id="x", name="x")], page_state=PageState(has_more=True)
            )
            nxt._fetch_next = fetch_one
            return nxt

        pl = PaginatedList[Item](
            items=[Item(id="0", name="0")], page_state=PageState(has_more=True)
        )
        pl._fetch_next = fetch_one
        collected = await asyncio.wait_for(pl.collect(max_items=10**9, max_pages=5), timeout=5.0)
        assert len(collected) == 6  # 1 initial + 5 fetched pages * 1 item

    @pytest.mark.asyncio
    async def test_anext_page_raises_when_has_more_but_unwired(self):
        """has_more=True with no _fetch_next is a connector bug — it must be loud.

        Returning None here (the old behavior) is indistinguishable from
        "no more results", so the caller silently acts on a truncated set.
        """
        pl = PaginatedList[Item](
            items=[Item(id="1", name="A")],
            page_state=PageState(has_more=True, cursor="CURSOR_2"),
        )

        with pytest.raises(PaginationNotWiredError) as exc:
            await pl.anext_page()

        assert exc.value.code == "CONNECTOR_PAGINATION_NOT_WIRED"
        # The stranded cursor must reach the caller so manual paging stays possible.
        assert exc.value.details["page_state"]["cursor"] == "CURSOR_2"

    @pytest.mark.asyncio
    async def test_collect_raises_when_has_more_but_unwired(self):
        """collect() must not quietly return page one for an unwired page."""
        pl = PaginatedList[Item](
            items=[Item(id="1", name="A")],
            page_state=PageState(has_more=True, cursor="CURSOR_2"),
        )

        with pytest.raises(PaginationNotWiredError):
            await pl.collect()

    @pytest.mark.asyncio
    async def test_anext_page_returns_none_at_end_of_results(self):
        """has_more=False still returns None even with no fetcher — not an error."""
        pl = PaginatedList[Item](items=[Item(id="1", name="A")])

        assert await pl.anext_page() is None
        assert len(await pl.collect()) == 1

    def test_collect_sync_stall_guard(self):
        """The sync wrapper inherits the stall guard (no hang)."""

        async def fetch_empty() -> PaginatedList[Item]:
            nxt = PaginatedList[Item](items=[], page_state=PageState(has_more=True))
            nxt._fetch_next = fetch_empty
            return nxt

        pl = PaginatedList[Item](
            items=[Item(id="1", name="A")], page_state=PageState(has_more=True)
        )
        pl._fetch_next = fetch_empty
        assert len(pl.collect_sync()) == 1


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
