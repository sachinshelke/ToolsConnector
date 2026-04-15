"""Shared AWS infrastructure for all AWS connectors.

This package is **internal** -- it is not a connector itself but provides
the building blocks (credentials, SigV4 signing, HTTP client, endpoint
resolution, error handling, XML parsing) shared across S3, SQS, ECS,
ECR, CloudFront, EC2, and every other AWS connector.

Typical usage from a connector module::

    from toolsconnector.connectors._aws import (
        AWSCredentials,
        parse_credentials,
        AWSBaseClient,
    )
"""

from __future__ import annotations

from .auth import AWSCredentials, parse_credentials
from .client import AWSBaseClient
from .errors import AWSError, format_access_denied_hint
from .regions import GLOBAL_SERVICES, get_endpoint
from .signing import get_signing_key, hmac_sha256, sign_v4
from .xml_helpers import find_text, iter_elements, parse_xml_error

__all__ = [
    # auth
    "AWSCredentials",
    "parse_credentials",
    # signing
    "sign_v4",
    "get_signing_key",
    "hmac_sha256",
    # client
    "AWSBaseClient",
    # regions
    "get_endpoint",
    "GLOBAL_SERVICES",
    # errors
    "AWSError",
    "format_access_denied_hint",
    # xml
    "find_text",
    "iter_elements",
    "parse_xml_error",
]
