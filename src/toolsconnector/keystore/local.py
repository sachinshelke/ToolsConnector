"""Local file-based keystore with Fernet encryption.

Stores credentials in an encrypted JSON file on the local filesystem.
Uses Python's ``cryptography`` library (Fernet symmetric encryption)
with a key derived from a user-provided password via PBKDF2.

``cryptography`` is an optional dependency::

    pip install "toolsconnector[local-keystore]"

Without it, :class:`LocalFileKeyStore` raises :class:`ImportError`; it
never falls back to storing credentials unencrypted.

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
from typing import Optional

# Default location for the encrypted key file
_DEFAULT_PATH = Path.home() / ".toolsconnector" / "keys.enc"


class LegacyKeyFileError(ValueError):
    """The key file is in the legacy base64 format, which is not encrypted.

    Older releases wrote this format when ``cryptography`` was not
    installed. Open the store once with ``migrate_legacy=True`` to
    re-encrypt the file in place.
    """


class UnreadableKeyFileError(ValueError):
    """The key file exists but cannot be read with this password.

    The password is wrong, or the file is empty or corrupted. The store
    refuses to open rather than start empty, because its next write
    would replace every credential in the file. The file is left as is.
    """


def _decode_legacy(raw: bytes) -> Optional[dict[str, str]]:
    """Return the credentials in a legacy base64 key file, or None.

    A Fernet token never matches: it base64-decodes to bytes starting
    with 0x80, which is not valid UTF-8.

    Args:
        raw: The key file's bytes.

    Returns:
        The decoded credentials, or None if *raw* is not the legacy format.
    """
    try:
        data = json.loads(base64.b64decode(raw.strip(), validate=True).decode("utf-8"))
    except ValueError:  # binascii.Error, UnicodeDecodeError and JSONDecodeError
        return None
    return data if isinstance(data, dict) else None


class LocalFileKeyStore:
    """Encrypted local file credential store.

    Credentials are stored as a JSON dict, encrypted with Fernet
    symmetric encryption. The encryption key is derived from a
    user-provided password using PBKDF2-HMAC-SHA256.

    Requires ``cryptography``: ``pip install "toolsconnector[local-keystore]"``.

    Thread-safe for single-process use. For multi-process, use
    a database-backed keystore instead.

    Args:
        path: Path to the encrypted key file.
            Defaults to ``~/.toolsconnector/keys.enc``.
        password: Password for encryption/decryption.
            If None, uses ``TC_KEYSTORE_PASSWORD`` env var.
            If neither is set, falls back to a machine-specific
            default (less secure, suitable for development only).
        migrate_legacy: Re-encrypt, in place, a key file that older
            releases left in the unencrypted legacy base64 format.
            Without it, such a file raises :class:`LegacyKeyFileError`.

    Raises:
        ImportError: ``cryptography`` is not installed.
        LegacyKeyFileError: The key file is in the legacy base64 format
            and ``migrate_legacy`` is False.
        UnreadableKeyFileError: The key file exists but cannot be read
            with this password (wrong password, empty, or corrupted).
    """

    def __init__(
        self,
        path: Optional[str] = None,
        password: Optional[str] = None,
        *,
        migrate_legacy: bool = False,
    ) -> None:
        try:
            from cryptography.fernet import Fernet
        except ImportError as exc:
            raise ImportError(
                "LocalFileKeyStore requires the 'cryptography' package to encrypt "
                'credentials. Install with: pip install "toolsconnector[local-keystore]"'
            ) from exc

        self._path = Path(path) if path else _DEFAULT_PATH
        supplied = password or os.environ.get("TC_KEYSTORE_PASSWORD")
        # Kept for the wrong-password error: an unset TC_KEYSTORE_PASSWORD
        # silently switches to the machine default.
        self._password_is_default = not supplied
        self._password = supplied or self._machine_default_password()
        self._data: dict[str, str] = {}
        self._key = self._derive_key(self._password)
        self._fernet = Fernet(self._key)
        self._load(migrate_legacy)

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
        # Annotated local, not cast(): cryptography is typed when installed
        # (a cast is then redundant) but Any to mypy when it isn't; the
        # annotation type-checks cleanly both ways.
        token: bytes = self._fernet.encrypt(plaintext.encode("utf-8"))
        return token

    def _decrypt(self, ciphertext: bytes) -> str:
        """Decrypt bytes using Fernet.

        Args:
            ciphertext: The encrypted bytes.

        Returns:
            Decrypted string.
        """
        plaintext: str = self._fernet.decrypt(ciphertext).decode("utf-8")
        return plaintext

    def _load(self, migrate_legacy: bool = False) -> None:
        """Load and decrypt the key file.

        A file that exists but can't be read raises instead of opening as
        an empty store, which the next write would save over the file.

        Args:
            migrate_legacy: Re-encrypt a legacy base64 key file in place
                instead of raising.

        Raises:
            LegacyKeyFileError: The file is in the legacy base64 format
                and *migrate_legacy* is False.
            UnreadableKeyFileError: The file is empty, can't be decrypted
                with this password, or doesn't hold a JSON object.
        """
        if not self._path.exists():
            self._data = {}
            return

        raw = self._path.read_bytes()
        if not raw.strip():
            # _save() never leaves a file empty unless a write was cut short;
            # say so rather than quietly open it as a new store.
            raise UnreadableKeyFileError(
                f"{self._path} is empty, so it holds no credentials. The file was left "
                "untouched; delete it to start a new store."
            )
        legacy = _decode_legacy(raw)
        if legacy is not None:
            if not migrate_legacy:
                raise LegacyKeyFileError(
                    f"{self._path} is in the legacy base64 format, which is NOT encrypted: "
                    "older toolsconnector releases wrote it that way when 'cryptography' "
                    "was not installed. Treat the credentials in it as exposed and rotate "
                    "them. To re-encrypt the file in place, pass migrate_legacy=True to "
                    "your usual LocalFileKeyStore(...) call once."
                )
            self._data = legacy
            self._save()
            return

        from cryptography.fernet import InvalidToken

        try:
            data = json.loads(self._decrypt(raw))
        except InvalidToken as exc:  # Fernet can't tell a wrong key from damaged bytes
            hint = (
                "Neither password= nor TC_KEYSTORE_PASSWORD was set, so the machine-default "
                "password was tried; supply the password the file was created with. "
                if self._password_is_default
                else ""
            )
            raise UnreadableKeyFileError(
                f"{self._path} could not be decrypted: the password is wrong or the file is "
                f"corrupted. {hint}The file was left untouched; to start a new store instead, "
                "move it aside."
            ) from exc
        except ValueError:  # UnicodeDecodeError or JSONDecodeError
            data = None
        if not isinstance(data, dict):
            raise UnreadableKeyFileError(
                f"{self._path} decrypted, but it does not hold a JSON object of credentials, "
                "so it is corrupted. The file was left untouched; to start a new store "
                "instead, move it aside."
            )
        self._data = data

    def _save(self) -> None:
        """Encrypt and save the key file.

        A new key file is created 0600 and a missing parent directory 0700.
        An existing file or directory keeps its permissions.
        """
        self._path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        plaintext = json.dumps(self._data, indent=2)
        encrypted = self._encrypt(plaintext)
        # Mode set at creation, so the file is never readable by others, even briefly.
        with open(self._path, "wb", opener=lambda p, flags: os.open(p, flags, 0o600)) as f:
            f.write(encrypted)

    async def get(self, key: str) -> Optional[str]:
        """Get a credential by key.

        Args:
            key: The credential key (e.g., 'gmail:default:access_token').

        Returns:
            The credential value, or None if not found.
        """
        return self._data.get(key)

    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> None:
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
