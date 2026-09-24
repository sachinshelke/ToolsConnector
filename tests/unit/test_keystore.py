"""Unit tests for the keystore/ module."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import stat
import sys

import pytest

from toolsconnector.keystore import EnvironmentKeyStore, InMemoryKeyStore, LocalFileKeyStore
from toolsconnector.keystore.local import UnreadableKeyFileError


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

    def test_wrong_password_raises_and_leaves_the_file_intact(self, tmp_path):
        path = tmp_path / "keys.enc"
        asyncio.run(LocalFileKeyStore(path=str(path), password="right").set("k", "ya29.secret"))
        before = path.read_bytes()

        # It used to open as an empty store, which the next set() saved over the file.
        with pytest.raises(UnreadableKeyFileError, match="could not be decrypted"):
            LocalFileKeyStore(path=str(path), password="wrong")

        assert path.read_bytes() == before
        reopened = LocalFileKeyStore(path=str(path), password="right")
        assert asyncio.run(reopened.get("k")) == "ya29.secret"

    def test_unset_env_password_error_names_the_variable(self, tmp_path, monkeypatch):
        path = tmp_path / "keys.enc"
        monkeypatch.setenv("TC_KEYSTORE_PASSWORD", "right")
        asyncio.run(LocalFileKeyStore(path=str(path)).set("k", "ya29.secret"))

        # Without the variable, the machine-default password is tried instead.
        monkeypatch.delenv("TC_KEYSTORE_PASSWORD")
        with pytest.raises(UnreadableKeyFileError, match="TC_KEYSTORE_PASSWORD"):
            LocalFileKeyStore(path=str(path))

    def test_truncated_file_raises(self, tmp_path):
        path = tmp_path / "keys.enc"
        asyncio.run(LocalFileKeyStore(path=str(path), password="pw").set("k", "ya29.secret"))
        truncated = path.read_bytes()[:40]  # what an interrupted write leaves behind
        path.write_bytes(truncated)

        with pytest.raises(UnreadableKeyFileError, match="wrong or the file is corrupted"):
            LocalFileKeyStore(path=str(path), password="pw")
        assert path.read_bytes() == truncated

    @pytest.mark.parametrize("content", [b"", b"\n"])
    def test_empty_file_raises(self, tmp_path, content):
        path = tmp_path / "keys.enc"
        path.write_bytes(content)

        with pytest.raises(UnreadableKeyFileError, match="is empty"):
            LocalFileKeyStore(path=str(path), password="pw")
        assert path.read_bytes() == content

    @pytest.mark.parametrize("plaintext", ["not json", '["k"]'])
    def test_decrypted_content_that_is_not_a_json_object_raises(self, tmp_path, plaintext):
        path = tmp_path / "keys.enc"
        ks = LocalFileKeyStore(path=str(path), password="pw")
        path.write_bytes(ks._encrypt(plaintext))  # right password, wrong content

        with pytest.raises(UnreadableKeyFileError, match="JSON object"):
            LocalFileKeyStore(path=str(path), password="pw")

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
    def test_new_key_file_and_directory_are_owner_only(self, tmp_path):
        path = tmp_path / "store" / "keys.enc"
        previous = os.umask(0o022)  # the usual default, under which they were 0644 and 0755
        try:
            asyncio.run(LocalFileKeyStore(path=str(path), password="pw").set("k", "ya29.secret"))
        finally:
            os.umask(previous)

        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
