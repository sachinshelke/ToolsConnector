"""AWS error types and IAM permission hints.

Provides ``AWSError`` -- the shared exception class for all AWS
connector errors -- and helper functions for parsing error responses
and generating actionable IAM permission suggestions.
"""

from __future__ import annotations

import json
from typing import Optional

from .xml_helpers import parse_xml_error

# ---------------------------------------------------------------------------
# IAM permission hints
# ---------------------------------------------------------------------------

# Maps ``(service, action_prefix)`` to the IAM permission string a
# caller most likely needs. The *action_prefix* is matched as a
# case-insensitive prefix of the API action name.
_IAM_HINTS: dict[tuple[str, str], str] = {
    # ECS
    ("ecs", "listtasks"): "ecs:ListTasks",
    ("ecs", "describetasks"): "ecs:DescribeTasks",
    ("ecs", "listservices"): "ecs:ListServices",
    ("ecs", "describeservices"): "ecs:DescribeServices",
    ("ecs", "listclusters"): "ecs:ListClusters",
    ("ecs", "describeclusters"): "ecs:DescribeClusters",
    ("ecs", "runtask"): "ecs:RunTask",
    ("ecs", "stoptask"): "ecs:StopTask",
    ("ecs", "updateservice"): "ecs:UpdateService",
    ("ecs", "registerTask"): "ecs:RegisterTaskDefinition",
    # ECR
    ("ecr", "describerepositories"): "ecr:DescribeRepositories",
    ("ecr", "listimages"): "ecr:ListImages",
    ("ecr", "describeimages"): "ecr:DescribeImages",
    ("ecr", "getauthorizationtoken"): "ecr:GetAuthorizationToken",
    ("ecr", "batchdeleteimage"): "ecr:BatchDeleteImage",
    ("ecr", "createrepository"): "ecr:CreateRepository",
    ("ecr", "deleterepository"): "ecr:DeleteRepository",
    # CloudFront
    ("cloudfront", "listdistributions"): "cloudfront:ListDistributions",
    ("cloudfront", "getdistribution"): "cloudfront:GetDistribution",
    ("cloudfront", "createinvalidation"): "cloudfront:CreateInvalidation",
    ("cloudfront", "listinvalidations"): "cloudfront:ListInvalidations",
    # EC2
    ("ec2", "describeinstances"): "ec2:DescribeInstances",
    ("ec2", "startinstances"): "ec2:StartInstances",
    ("ec2", "stopinstances"): "ec2:StopInstances",
    ("ec2", "terminateinstances"): "ec2:TerminateInstances",
    ("ec2", "describesecuritygroups"): "ec2:DescribeSecurityGroups",
    ("ec2", "describevpcs"): "ec2:DescribeVpcs",
    ("ec2", "describesubnets"): "ec2:DescribeSubnets",
    # ALB / ELBv2
    ("elasticloadbalancing", "describeloadbalancers"): "elasticloadbalancing:DescribeLoadBalancers",
    ("elasticloadbalancing", "describetargetgroups"): "elasticloadbalancing:DescribeTargetGroups",
    ("elasticloadbalancing", "describetargethealth"): "elasticloadbalancing:DescribeTargetHealth",
    ("elasticloadbalancing", "describelisteners"): "elasticloadbalancing:DescribeListeners",
    ("elasticloadbalancing", "describerules"): "elasticloadbalancing:DescribeRules",
    # Route 53
    ("route53", "listhostedzones"): "route53:ListHostedZones",
    ("route53", "listresourcerecordsets"): "route53:ListResourceRecordSets",
    ("route53", "changeresourcerecordsets"): "route53:ChangeResourceRecordSets",
    ("route53", "gethostedzonecount"): "route53:GetHostedZoneCount",
    # ACM
    ("acm", "listcertificates"): "acm:ListCertificates",
    ("acm", "describecertificate"): "acm:DescribeCertificate",
    ("acm", "requestcertificate"): "acm:RequestCertificate",
    ("acm", "deletecertificate"): "acm:DeleteCertificate",
    # S3 (common)
    ("s3", "listbuckets"): "s3:ListAllMyBuckets",
    ("s3", "listobjects"): "s3:ListBucket",
    ("s3", "getobject"): "s3:GetObject",
    ("s3", "putobject"): "s3:PutObject",
    ("s3", "deleteobject"): "s3:DeleteObject",
    # SQS
    ("sqs", "sendmessage"): "sqs:SendMessage",
    ("sqs", "receivemessage"): "sqs:ReceiveMessage",
    ("sqs", "deletemessage"): "sqs:DeleteMessage",
    ("sqs", "listqueues"): "sqs:ListQueues",
    ("sqs", "createqueue"): "sqs:CreateQueue",
    ("sqs", "deletequeue"): "sqs:DeleteQueue",
}


def format_access_denied_hint(service: str, action: str) -> Optional[str]:
    """Map a service + action to the IAM permission likely needed.

    Performs a case-insensitive prefix match against the known action
    map. Returns ``None`` if no specific hint is available.

    Args:
        service: AWS service name (lowercase), e.g. ``"ecs"``.
        action: API action name, e.g. ``"ListTasks"``.

    Returns:
        A human-readable hint string like
        ``"Ensure your IAM policy includes: ecs:ListTasks"``,
        or ``None`` if no mapping exists.
    """
    action_lower = action.lower()
    for (svc, prefix), iam_perm in _IAM_HINTS.items():
        if svc == service and action_lower.startswith(prefix):
            return f"Ensure your IAM policy includes: {iam_perm}"

    # Fallback: construct a best-guess permission.
    if action:
        return f"Ensure your IAM policy includes: {service}:{action}"
    return None


# ---------------------------------------------------------------------------
# Error class
# ---------------------------------------------------------------------------


class AWSError(Exception):
    """Exception raised for AWS API errors.

    Carries structured error details including the HTTP status code,
    AWS error code, message, and an optional IAM hint when the error
    is an access-denied type.

    Attributes:
        status_code: HTTP status code from the response.
        error_code: AWS error code string (e.g. ``AccessDeniedException``).
        message: Human-readable error message from AWS.
        iam_hint: Suggested IAM permission when the error is access-related.
    """

    def __init__(
        self,
        status_code: int,
        error_code: str,
        message: str,
        iam_hint: Optional[str] = None,
    ) -> None:
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.iam_hint = iam_hint
        parts = [f"[{status_code}] {error_code}: {message}"]
        if iam_hint:
            parts.append(f"Hint: {iam_hint}")
        super().__init__(" | ".join(parts))


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def parse_aws_error(
    response_text: str,
    content_type: str,
) -> dict[str, Optional[str]]:
    """Parse an AWS error response body (JSON or XML).

    Args:
        response_text: Raw response body string.
        content_type: ``Content-Type`` header value from the response.

    Returns:
        Dict with ``code`` and ``message`` keys (values may be
        ``None`` if extraction fails).
    """
    ct = content_type.lower() if content_type else ""

    # JSON errors (used by SQS, ECS, ECR, Secrets Manager, etc.)
    if "json" in ct or response_text.strip().startswith("{"):
        try:
            body = json.loads(response_text)
        except json.JSONDecodeError:
            return {"code": None, "message": response_text}

        code = body.get("__type") or body.get("Error", {}).get("Code") or body.get("code")
        message = body.get("message") or body.get("Message") or body.get("Error", {}).get("Message")
        return {"code": code, "message": message}

    # XML errors (used by S3, EC2, IAM, ALB, Route 53, etc.)
    if "xml" in ct or response_text.strip().startswith("<"):
        return parse_xml_error(response_text)

    # Unknown format -- return raw text as message.
    return {"code": None, "message": response_text}
