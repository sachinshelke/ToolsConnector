"""AWS Signature Version 4 signing -- service-agnostic.

Generalised from the S3-specific implementation to work with any AWS
service. The ``sign_v4`` function accepts a ``service`` parameter instead
of hardcoding ``"s3"`` in the credential scope.

Implements the canonical-request -> string-to-sign -> signing-key ->
signature flow per the AWS documentation.
"""

from __future__ import annotations

import hashlib
import hmac
import urllib.parse
from typing import Optional


def hmac_sha256(key: bytes, msg: str) -> bytes:
    """Compute HMAC-SHA256.

    Args:
        key: HMAC key bytes.
        msg: Message string to sign.

    Returns:
        HMAC-SHA256 digest bytes.
    """
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def get_signing_key(
    secret_access_key: str,
    date_stamp: str,
    region: str,
    service: str,
) -> bytes:
    """Derive the SigV4 signing key.

    Args:
        secret_access_key: AWS secret access key.
        date_stamp: Date in ``YYYYMMDD`` format.
        region: AWS region string.
        service: AWS service name (e.g. ``s3``, ``sqs``, ``ecs``).

    Returns:
        Derived signing key bytes.
    """
    k_date = hmac_sha256(
        f"AWS4{secret_access_key}".encode("utf-8"), date_stamp,
    )
    k_region = hmac_sha256(k_date, region)
    k_service = hmac_sha256(k_region, service)
    return hmac_sha256(k_service, "aws4_request")


def sign_v4(
    method: str,
    url: str,
    headers: dict[str, str],
    payload_hash: str,
    access_key_id: str,
    secret_access_key: str,
    region: str,
    service: str,
    session_token: Optional[str] = None,
) -> dict[str, str]:
    """Build AWS SigV4 Authorization header for any AWS service.

    When *session_token* is provided (temporary credentials from STS),
    the ``x-amz-security-token`` header is added before the canonical
    request is built so the token is included in the signature.

    Args:
        method: HTTP method (``GET``, ``PUT``, ``POST``, etc.).
        url: Full request URL.
        headers: Request headers (must include ``Host`` and
            ``x-amz-date``).
        payload_hash: SHA256 hex digest of the request body.
        access_key_id: AWS access key ID.
        secret_access_key: AWS secret access key.
        region: AWS region string.
        service: AWS service name (e.g. ``s3``, ``sqs``, ``ecs``).
        session_token: Optional STS session token for temporary
            credentials.

    Returns:
        Updated *headers* dict with the ``Authorization`` header (and
        ``x-amz-security-token`` if applicable) added.
    """
    # Inject security token header *before* building the canonical
    # request so that it participates in signing.
    if session_token is not None:
        headers["x-amz-security-token"] = session_token

    parsed = urllib.parse.urlparse(url)
    canonical_uri = urllib.parse.quote(parsed.path or "/", safe="/")

    # Parse and sort query string parameters.
    query_parts = urllib.parse.parse_qsl(
        parsed.query, keep_blank_values=True,
    )
    sorted_qs = sorted(query_parts, key=lambda x: (x[0], x[1]))
    canonical_querystring = urllib.parse.urlencode(
        sorted_qs, quote_via=urllib.parse.quote,
    )

    amz_date = headers["x-amz-date"]
    date_stamp = amz_date[:8]

    # Build canonical headers (sorted, lowercased keys).
    signed_header_keys = sorted(
        k.lower() for k in headers if k.lower() != "authorization"
    )
    canonical_headers = ""
    for k in signed_header_keys:
        for orig_k, v in headers.items():
            if orig_k.lower() == k:
                canonical_headers += f"{k}:{v.strip()}\n"
                break

    signed_headers_str = ";".join(signed_header_keys)

    canonical_request = (
        f"{method}\n"
        f"{canonical_uri}\n"
        f"{canonical_querystring}\n"
        f"{canonical_headers}\n"
        f"{signed_headers_str}\n"
        f"{payload_hash}"
    )

    # String to sign -- uses the *service* parameter in the scope.
    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    canonical_hash = hashlib.sha256(
        canonical_request.encode("utf-8"),
    ).hexdigest()
    string_to_sign = (
        f"AWS4-HMAC-SHA256\n"
        f"{amz_date}\n"
        f"{credential_scope}\n"
        f"{canonical_hash}"
    )

    # Signing key and final signature.
    signing_key = get_signing_key(
        secret_access_key, date_stamp, region, service,
    )
    signature = hmac.new(
        signing_key,
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    headers["Authorization"] = (
        f"AWS4-HMAC-SHA256 "
        f"Credential={access_key_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers_str}, "
        f"Signature={signature}"
    )
    return headers
