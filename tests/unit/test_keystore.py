"""Unit tests for the keystore/ module."""

from __future__ import annotations

import asyncio
import base64
import json
import sys

import pytest

from toolsconnector.keystore import EnvironmentKeyStore, InMemoryKeyStore, LocalFileKeyStore


def _hide_cryptography(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make ``cryptography`` unimportable, as on a plain ``pip install toolsconnector``."""
    monkeypatch.setitem(sys.modules, "cryptography", None)
    monkeypatch.setitem(sys.modules, "cryptography.fernet", None)


def _legacy_key_file(data: dict[str, str]) -> bytes:
    """The bytes the removed base64 fallback wrote instead of a Fernet token."""
    return base64.b64encode(json.dumps(data, indent=2).encode("utf-8"))


def _is_fernet_token(raw: bytes) -> bool:
    """Fernet tokens are urlsafe base64 whose first decoded byte is the 0x80 version."""
    return base64.urlsafe_b64decode(raw)[0] == 0x80


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


class TestLocalFileKeyStore:
    def test_round_trip_writes_fernet_ciphertext(self, tmp_path):
        path = tmp_path / "keys.enc"
        asyncio.run(LocalFileKeyStore(path=str(path), password="pw").set("k", "ya29.secret"))

        assert _is_fernet_token(path.read_bytes())
        reopened = LocalFileKeyStore(path=str(path), password="pw")
        assert asyncio.run(reopened.get("k")) == "ya29.secret"

    def test_missing_cryptography_raises_instead_of_writing_base64(self, tmp_path, monkeypatch):
        _hide_cryptography(monkeypatch)
        path = tmp_path / "keys.enc"

        # Construction or, at the latest, the first write must fail -- never a
        # silent base64 write.
        with pytest.raises(ImportError, match=r'pip install "toolsconnector\[local-keystore\]"'):
            ks = LocalFileKeyStore(path=str(path), password="pw")
            asyncio.run(ks.set("gmail:default:access_token", "ya29.secret"))
        assert not path.exists()

    def test_legacy_base64_file_raises_actionable_error(self, tmp_path):
        path = tmp_path / "keys.enc"
        legacy = _legacy_key_file({"gmail:default:access_token": "ya29.secret"})
        path.write_bytes(legacy)

        with pytest.raises(ValueError, match="legacy base64 format") as excinfo:
            LocalFileKeyStore(path=str(path), password="pw")
        message = str(excinfo.value)
        assert str(path) in message
        assert "NOT encrypted" in message
        assert "rotate" in message
        assert "migrate_legacy=True" in message
        assert path.read_bytes() == legacy  # refused, not overwritten

    def test_migrate_legacy_reencrypts_in_place(self, tmp_path):
        path = tmp_path / "keys.enc"
        path.write_bytes(_legacy_key_file({"gmail:default:access_token": "ya29.secret"}))

        LocalFileKeyStore(path=str(path), password="pw", migrate_legacy=True)

        assert _is_fernet_token(path.read_bytes())
        reopened = LocalFileKeyStore(path=str(path), password="pw")
        assert asyncio.run(reopened.get("gmail:default:access_token")) == "ya29.secret"
