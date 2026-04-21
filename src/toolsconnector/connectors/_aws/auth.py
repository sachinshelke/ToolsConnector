"""AWS credential parsing and representation.

Provides a unified ``AWSCredentials`` dataclass and a flexible
``parse_credentials`` function that accepts environment variables, JSON
dicts, INI profile references, and colon-separated strings.

This module is internal infrastructure shared by all AWS connectors.
"""

from __future__ import annotations

import configparser
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


# Keys we accept as aliases for ``access_key_id`` in dict credentials.
_AK_KEYS = ("access_key_id", "access_key", "aws_access_key_id")
# Keys we accept as aliases for ``secret_access_key`` in dict credentials.
_SK_KEYS = ("secret_access_key", "secret_key", "aws_secret_access_key")
# Keys we accept as aliases for ``region`` in dict credentials.
_RG_KEYS = ("region", "aws_region", "aws_default_region")
# Keys we accept as aliases for ``session_token`` in dict credentials.
_ST_KEYS = ("session_token", "aws_session_token")


def _pick(d: dict[str, Any], candidates: tuple[str, ...]) -> Optional[str]:
    """Return the first matching value from *d* for the given key candidates."""
    for k in candidates:
        if k in d:
            return str(d[k])
    return None


@dataclass(frozen=True)
class AWSCredentials:
    """Immutable container for AWS authentication details.

    Attributes:
        access_key_id: AWS access key ID.
        secret_access_key: AWS secret access key.
        region: AWS region code (e.g. ``us-east-1``).
        session_token: Optional STS session token for temporary credentials.
    """

    access_key_id: str
    secret_access_key: str
    region: str
    session_token: Optional[str] = None


def _parse_dict(d: dict[str, Any]) -> AWSCredentials:
    """Build ``AWSCredentials`` from a dictionary, tolerating key aliases."""
    ak = _pick(d, _AK_KEYS)
    sk = _pick(d, _SK_KEYS)
    rg = _pick(d, _RG_KEYS) or "us-east-1"
    st = _pick(d, _ST_KEYS)

    if not ak or not sk:
        raise ValueError(
            "Credential dict must contain 'access_key_id' (or "
            "'access_key'/'aws_access_key_id') and 'secret_access_key' "
            "(or 'secret_key'/'aws_secret_access_key')."
        )
    return AWSCredentials(
        access_key_id=ak,
        secret_access_key=sk,
        region=rg,
        session_token=st,
    )


def _parse_env() -> AWSCredentials:
    """Read AWS credentials from environment variables."""
    ak = os.environ.get("AWS_ACCESS_KEY_ID", "")
    sk = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
    rg = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    st = os.environ.get("AWS_SESSION_TOKEN")

    if not ak or not sk:
        raise ValueError(
            "AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment "
            "variables must be set when using env-based credentials."
        )
    return AWSCredentials(
        access_key_id=ak,
        secret_access_key=sk,
        region=rg,
        session_token=st or None,
    )


def _parse_profile(profile_name: str) -> AWSCredentials:
    """Read credentials from the ``~/.aws/credentials`` INI file."""
    creds_path = Path.home() / ".aws" / "credentials"
    if not creds_path.exists():
        raise ValueError(
            f"Cannot read profile '{profile_name}': "
            f"{creds_path} does not exist."
        )

    config = configparser.ConfigParser()
    config.read(creds_path)

    if profile_name not in config:
        raise ValueError(
            f"Profile '{profile_name}' not found in {creds_path}. "
            f"Available profiles: {', '.join(config.sections())}"
        )

    section = config[profile_name]
    ak = section.get("aws_access_key_id", "")
    sk = section.get("aws_secret_access_key", "")
    rg = section.get("region", "")

    # Region may live in ~/.aws/config instead.
    if not rg:
        cfg_path = Path.home() / ".aws" / "config"
        if cfg_path.exists():
            cfg = configparser.ConfigParser()
            cfg.read(cfg_path)
            # In config file, non-default profiles are [profile name].
            cfg_section = (
                "default" if profile_name == "default"
                else f"profile {profile_name}"
            )
            if cfg_section in cfg:
                rg = cfg[cfg_section].get("region", "")

    rg = rg or "us-east-1"
    st = section.get("aws_session_token")

    if not ak or not sk:
        raise ValueError(
            f"Profile '{profile_name}' in {creds_path} is missing "
            f"aws_access_key_id or aws_secret_access_key."
        )
    return AWSCredentials(
        access_key_id=ak,
        secret_access_key=sk,
        region=rg,
        session_token=st or None,
    )


def parse_credentials(
    creds: Any,
) -> AWSCredentials:
    """Parse AWS credentials from multiple input formats.

    Accepted formats:

    1. ``None`` or ``"env"`` -- read from environment variables
       (``AWS_ACCESS_KEY_ID``, ``AWS_SECRET_ACCESS_KEY``,
       ``AWS_DEFAULT_REGION``, ``AWS_SESSION_TOKEN``).
    2. ``dict`` with ``access_key_id`` (or alias) -- direct dict mapping.
    3. JSON string starting with ``{`` -- parsed then treated as a dict.
    4. ``"profile:<name>"`` -- reads the named section from
       ``~/.aws/credentials``.
    5. ``"key:secret:region"`` (string with exactly two colons) -- inline
       colon-separated format used by the SQS connector.

    Args:
        creds: Credential input in any of the formats above.

    Returns:
        Parsed ``AWSCredentials`` instance.

    Raises:
        ValueError: If the input format is not recognised or required
            fields are missing.
    """
    # 1. None / "env"
    if creds is None or (isinstance(creds, str) and creds.strip().lower() == "env"):
        return _parse_env()

    # 2. dict
    if isinstance(creds, dict):
        return _parse_dict(creds)

    # Already an AWSCredentials instance -- pass through.
    if isinstance(creds, AWSCredentials):
        return creds

    # Must be a string from here on.
    if not isinstance(creds, str):
        raise ValueError(
            f"Unsupported credential type: {type(creds).__name__}. "
            f"Expected None, 'env', dict, JSON string, 'profile:<name>', "
            f"or 'key:secret:region'."
        )

    text = creds.strip()

    # 3. JSON string
    if text.startswith("{"):
        try:
            return _parse_dict(json.loads(text))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Credential string looks like JSON but failed to parse: {exc}"
            ) from exc

    # 4. Profile reference
    if text.lower().startswith("profile:"):
        profile_name = text[len("profile:"):].strip()
        return _parse_profile(profile_name)

    # 5. Colon-separated "key:secret:region"
    parts = text.split(":")
    if len(parts) == 3:
        return AWSCredentials(
            access_key_id=parts[0],
            secret_access_key=parts[1],
            region=parts[2],
        )

    raise ValueError(
        "Unrecognised credential format. Accepted formats:\n"
        "  1. None or 'env' -- read from environment variables\n"
        "  2. dict with 'access_key_id' and 'secret_access_key'\n"
        "  3. JSON string: '{\"access_key_id\": ..., ...}'\n"
        "  4. 'profile:<name>' -- read from ~/.aws/credentials\n"
        "  5. 'key:secret:region' -- colon-separated string"
    )
