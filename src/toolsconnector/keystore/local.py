"""Local file-based keystore with Fernet encryption.

Stores credentials in an encrypted JSON file on the local filesystem.
Uses Python's ``cryptography`` library (Fernet symmetric encryption)
with a key derived from a user-provided password via PBKDF2.

Usage::

    from toolsconnector.keystore import LocalFileKeyStore

    # Creates/opens ~/.toolsconnector/keys.enc
    ks = LocalFileKeyStore(password="my-secret-password")
    await ks.set("gmail:default:access_token", "ya29.a0A...")
    token = await ks.get("gmail:default:access_token")
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Optional


# Default location for the encrypted key file
_DEFAULT_PATH = Path.home() / ".toolsconnector" / "keys.enc"


class LocalFileKeyStore:
    """Encrypted local file credential store.

    Credentials are stored as a JSON dict, encrypted with Fernet
    symmetric encryption. The encryption key is derived from a
    user-provided password using PBKDF2-HMAC-SHA256.

    Thread-safe for single-process use. For multi-process, use
    a database-backed keystore instead.

    Args:
        path: Path to the encrypted key file.
            Defaults to ``~/.toolsconnector/keys.enc``.
        password: Password for encryption/decryption.
            If None, uses ``TC_KEYSTORE_PASSWORD`` env var.
            If neither is set, falls back to a machine-specific
            default (less secure, suitable for development only).
    """

    def __init__(
        self,
        path: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        self._path = Path(path) if path else _DEFAULT_PATH
        self._password = (
            password
            or os.environ.get("TC_KEYSTORE_PASSWORD")
            or self._machine_default_password()
        )
        self._data: dict[str, str] = {}
        self._key = self._derive_key(self._password)
        self._load()

    def _derive_key(self, password: str) -> bytes:
        """Derive a 32-byte encryption key from password via PBKDF2.

        Args:
            password: The password to derive from.

        Returns:
            URL-safe base64-encoded 32-byte key for Fernet.
        """
        salt = b"toolsconnector-keystore-v1"
        dk = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations=100_000,
            dklen=32,
        )
        return base64.urlsafe_b64encode(dk)

    def _machine_default_password(self) -> str:
        """Generate a machine-specific default password.

        Uses hostname + username as a weak but deterministic key.
        Only for development — production should set TC_KEYSTORE_PASSWORD.
        """
        import getpass
        import platform
        return f"tc-dev-{platform.node()}-{getpass.getuser()}"

    def _encrypt(self, plaintext: str) -> bytes:
        """Encrypt a string using Fernet.

        Args:
            plaintext: The string to encrypt.

        Returns:
            Encrypted bytes.
        """
        try:
            from cryptography.fernet import Fernet
        except ImportError:
            # Fallback: base64 encode (NOT secure, just obfuscation)
            return base64.b64encode(plaintext.encode("utf-8"))

        f = Fernet(self._key)
        return f.encrypt(plaintext.encode("utf-8"))

    def _decrypt(self, ciphertext: bytes) -> str:
        """Decrypt bytes using Fernet.

        Args:
            ciphertext: The encrypted bytes.

        Returns:
            Decrypted string.
        """
        try:
            from cryptography.fernet import Fernet
        except ImportError:
            # Fallback: base64 decode
            return base64.b64decode(ciphertext).decode("utf-8")

        f = Fernet(self._key)
        return f.decrypt(ciphertext).decode("utf-8")

    def _load(self) -> None:
        """Load and decrypt the key file."""
        if not self._path.exists():
            self._data = {}
            return

        try:
            raw = self._path.read_bytes()
            decrypted = self._decrypt(raw)
            self._data = json.loads(decrypted)
        except Exception:
            # Corrupted or wrong password — start fresh
            self._data = {}

    def _save(self) -> None:
        """Encrypt and save the key file."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        plaintext = json.dumps(self._data, indent=2)
        encrypted = self._encrypt(plaintext)
        self._path.write_bytes(encrypted)

    async def get(self, key: str) -> Optional[str]:
        """Get a credential by key.

        Args:
            key: The credential key (e.g., 'gmail:default:access_token').

        Returns:
            The credential value, or None if not found.
        """
        return self._data.get(key)

    async def set(
        self, key: str, value: str, ttl: Optional[int] = None
    ) -> None:
        """Store a credential.

        Args:
            key: The credential key.
            value: The credential value.
            ttl: Ignored for file-based store (no expiry support).
        """
        self._data[key] = value
        self._save()

    async def delete(self, key: str) -> None:
        """Delete a credential.

        Args:
            key: The credential key to delete.
        """
        self._data.pop(key, None)
        self._save()

    async def exists(self, key: str) -> bool:
        """Check if a credential exists.

        Args:
            key: The credential key to check.

        Returns:
            True if the key exists.
        """
        return key in self._data

    def list_keys(self) -> list[str]:
        """List all stored credential keys.

        Returns:
            Sorted list of key names.
        """
        return sorted(self._data.keys())
