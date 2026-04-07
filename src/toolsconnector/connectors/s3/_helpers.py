"""Internal helpers for the S3 connector.

Provides XML parsing utilities and pre-signed URL generation logic.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Optional

from .types import S3PresignedUrl

_S3_NS = "http://s3.amazonaws.com/doc/2006-03-01/"


def find_text(elem: ET.Element, tag: str) -> Optional[str]:
    """Find a child element by tag (namespace-aware) and return its text.

    Args:
        elem: Parent XML element.
        tag: Child element tag name (without namespace).

    Returns:
        Text content of the child element, or None if not found.
    """
    child = elem.find(f"{{{_S3_NS}}}{tag}")
    if child is None:
        child = elem.find(tag)
    return child.text if child is not None else None


def extract_user_metadata(headers: dict[str, str]) -> dict[str, str]:
    """Extract x-amz-meta-* headers into a dict.

    Args:
        headers: HTTP response headers (or header-like mapping).

    Returns:
        Dict of user metadata key-value pairs.
    """
    prefix = "x-amz-meta-"
    return {
        k[len(prefix):]: v
        for k, v in headers.items()
        if k.lower().startswith(prefix)
    }


def build_presigned_url(
    *,
    bucket: str,
    key: str,
    host: str,
    region: str,
    access_key_id: str,
    secret_access_key: str,
    expiration: int = 3600,
    method: str = "GET",
) -> S3PresignedUrl:
    """Build a pre-signed URL using AWS Signature Version 4.

    Args:
        bucket: S3 bucket name.
        key: Object key.
        host: Bucket virtual-hosted-style host.
        region: AWS region.
        access_key_id: AWS access key ID.
        secret_access_key: AWS secret access key.
        expiration: URL validity in seconds (max 604800).
        method: HTTP method the URL authorises (GET or PUT).

    Returns:
        S3PresignedUrl with the signed URL string.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    credential_scope = f"{date_stamp}/{region}/s3/aws4_request"
    credential = f"{access_key_id}/{credential_scope}"
    enc_key = urllib.parse.quote(key, safe="/")

    query_params = {
        "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
        "X-Amz-Credential": credential,
        "X-Amz-Date": amz_date,
        "X-Amz-Expires": str(min(expiration, 604800)),
        "X-Amz-SignedHeaders": "host",
    }
    canonical_qs = urllib.parse.urlencode(
        sorted(query_params.items()),
        quote_via=urllib.parse.quote,
    )

    canonical_request = (
        f"{method}\n/{enc_key}\n{canonical_qs}\n"
        f"host:{host}\n\nhost\nUNSIGNED-PAYLOAD"
    )
    cr_hash = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    string_to_sign = (
        f"AWS4-HMAC-SHA256\n{amz_date}\n{credential_scope}\n{cr_hash}"
    )

    def _sign(k: bytes, msg: str) -> bytes:
        return hmac.new(k, msg.encode("utf-8"), hashlib.sha256).digest()

    date_key = _sign(f"AWS4{secret_access_key}".encode("utf-8"), date_stamp)
    region_key = _sign(date_key, region)
    service_key = _sign(region_key, "s3")
    signing_key = _sign(service_key, "aws4_request")

    signature = hmac.new(
        signing_key,
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    signed_url = (
        f"https://{host}/{enc_key}?{canonical_qs}"
        f"&X-Amz-Signature={signature}"
    )

    return S3PresignedUrl(
        bucket=bucket,
        key=key,
        url=signed_url,
        expiration=expiration,
        method=method,
    )


def build_tagging_xml(tags: dict[str, str], namespace: str) -> bytes:
    """Build the XML body for a PutObjectTagging request.

    Args:
        tags: Dictionary of tag key-value pairs.
        namespace: S3 XML namespace URI.

    Returns:
        UTF-8 encoded XML bytes.
    """
    tag_elements = "".join(
        f"<Tag><Key>{k}</Key><Value>{v}</Value></Tag>"
        for k, v in tags.items()
    )
    return (
        f'<Tagging xmlns="{namespace}">'
        f"<TagSet>{tag_elements}</TagSet>"
        f"</Tagging>"
    ).encode("utf-8")


def compute_content_md5(body: bytes) -> str:
    """Compute the Base64-encoded MD5 digest for a request body.

    Args:
        body: Raw request body bytes.

    Returns:
        Base64-encoded MD5 string.
    """
    return base64.b64encode(
        hashlib.md5(body).digest(),  # noqa: S324
    ).decode("ascii")
