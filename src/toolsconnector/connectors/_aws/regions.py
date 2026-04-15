"""AWS service endpoint resolution and region helpers.

Maps service names to their correct endpoint URL format, handling
global services (IAM, Route 53, CloudFront, STS) and service-specific
URL patterns (e.g. S3's ``s3.{region}.amazonaws.com``).
"""

from __future__ import annotations


# Services that use a single global endpoint (``us-east-1``).
GLOBAL_SERVICES: frozenset[str] = frozenset({
    "iam",
    "route53",
    "cloudfront",
    "sts",
})

# Services whose endpoint pattern differs from the default
# ``{service}.{region}.amazonaws.com``.
_ENDPOINT_OVERRIDES: dict[str, str] = {
    "s3": "https://s3.{region}.amazonaws.com",
    "cloudfront": "https://cloudfront.amazonaws.com",
    "route53": "https://route53.amazonaws.com",
    "iam": "https://iam.amazonaws.com",
    "sts": "https://sts.amazonaws.com",
}


def get_endpoint(service: str, region: str) -> str:
    """Return the HTTPS endpoint URL for an AWS service.

    Special cases:

    * **S3** -- ``https://s3.{region}.amazonaws.com``
    * **CloudFront, Route 53, IAM, STS** -- global endpoints without a
      region component.
    * All other services -- ``https://{service}.{region}.amazonaws.com``

    Args:
        service: AWS service name (lowercase), e.g. ``"ecs"``,
            ``"s3"``, ``"cloudfront"``.
        region: AWS region code, e.g. ``"us-east-1"``.

    Returns:
        Full HTTPS endpoint URL string.
    """
    override = _ENDPOINT_OVERRIDES.get(service)
    if override is not None:
        return override.format(region=region)

    if service in GLOBAL_SERVICES:
        return f"https://{service}.amazonaws.com"

    return f"https://{service}.{region}.amazonaws.com"
