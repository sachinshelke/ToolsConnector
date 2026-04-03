"""Unit tests for the keystore/ module."""

from __future__ import annotations

import asyncio
import os

import pytest

from toolsconnector.keystore import InMemoryKeyStore, EnvironmentKeyStore


class TestInMemoryKeyStore:
    def test_set_and_get(self):
        async def _test():
            ks = InMemoryKeyStore()
            await ks.set("gmail:user1:token", "abc123")
            val = await ks.get("gmail:user1:token")
            assert val == "abc123"

        asyncio.run(_test())

    def test_get_nonexistent(self):
        async def _test():
            ks = InMemoryKeyStore()
            val = await ks.get("nonexistent")
            assert val is None

        asyncio.run(_test())

    def test_exists(self):
        async def _test():
            ks = InMemoryKeyStore()
            assert not await ks.exists("key")
            await ks.set("key", "val")
            assert await ks.exists("key")

        asyncio.run(_test())

    def test_delete(self):
        async def _test():
            ks = InMemoryKeyStore()
            await ks.set("key", "val")
            await ks.delete("key")
            assert not await ks.exists("key")
            assert await ks.get("key") is None

        asyncio.run(_test())

    def test_delete_nonexistent(self):
        """Deleting a nonexistent key should not raise."""
        async def _test():
            ks = InMemoryKeyStore()
            await ks.delete("nope")  # Should not raise

        asyncio.run(_test())

    def test_overwrite(self):
        async def _test():
            ks = InMemoryKeyStore()
            await ks.set("key", "v1")
            await ks.set("key", "v2")
            assert await ks.get("key") == "v2"

        asyncio.run(_test())


class TestEnvironmentKeyStore:
    def test_read_from_env(self, monkeypatch):
        monkeypatch.setenv("TC_GMAIL_DEFAULT_API_KEY", "test-key")

        async def _test():
            ks = EnvironmentKeyStore()
            val = await ks.get("gmail:default:api_key")
            assert val == "test-key"

        asyncio.run(_test())

    def test_nonexistent_env(self):
        async def _test():
            ks = EnvironmentKeyStore()
            val = await ks.get("nonexistent:default:key")
            assert val is None

        asyncio.run(_test())

    def test_exists(self, monkeypatch):
        monkeypatch.setenv("TC_SLACK_DEFAULT_BOT_TOKEN", "xoxb-test")

        async def _test():
            ks = EnvironmentKeyStore()
            assert await ks.exists("slack:default:bot_token")
            assert not await ks.exists("nope:default:key")

        asyncio.run(_test())
