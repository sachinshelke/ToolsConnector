"""AWS SigV4 signing — re-exports from shared ``_aws.signing`` module.

This file exists for backward compatibility. New code should import
directly from ``toolsconnector.connectors._aws.signing``.
"""

from toolsconnector.connectors._aws.signing import (
    get_signing_key,
    hmac_sha256,
    sign_v4,
)

__all__ = ["get_signing_key", "hmac_sha256", "sign_v4"]
