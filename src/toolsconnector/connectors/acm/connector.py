"""AWS ACM connector -- request, manage, and deploy SSL/TLS certificates.

Uses the ACM JSON Target API with ``X-Amz-Target`` headers. Credentials
should be ``"access_key:secret_key:region"`` format or any format accepted
by ``parse_credentials``.

.. note::

    The SigV4 signing implementation is simplified. For production
    workloads, ``boto3`` is strongly recommended.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
from typing import Any, Optional

import httpx

from toolsconnector.connectors._aws.auth import parse_credentials
from toolsconnector.connectors._aws.signing import sign_v4
from toolsconnector.errors import APIError, NotFoundError
from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import (
    ConnectorCategory,
    ProtocolType,
    RateLimitSpec,
)

from .types import (
    ACMCertificateDetail,
    ACMCertificateSummary,
    ACMTag,
)

logger = logging.getLogger("toolsconnector.acm")

_TARGET_PREFIX = "CertificateManager"


class ACM(BaseConnector):
    """Connect to AWS ACM to request, manage, and deploy SSL/TLS certificates.

    Credentials format: ``"access_key_id:secret_access_key:region"``
    Uses the ACM JSON API (``X-Amz-Target: CertificateManager.{Action}``).

    .. note::

        SigV4 signing is simplified. For production, use ``boto3``.
    """

    name = "acm"
    display_name = "AWS ACM"
    category = ConnectorCategory.SECURITY
    protocol = ProtocolType.REST
    base_url = "https://acm.us-east-1.amazonaws.com"
    description = "Request, manage, and deploy SSL/TLS certificates."
    _rate_limit_config = RateLimitSpec(rate=20, period=1, burst=40)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Parse credentials and initialise the HTTP client."""
        creds = parse_credentials(self._credentials)
        self._access_key = creds.access_key_id
        self._secret_key = creds.secret_access_key
        self._region = creds.region
        self._session_token = creds.session_token
        self._host = f"acm.{self._region}.amazonaws.com"
        self._base_url = f"https://{self._host}"

        self._client = httpx.AsyncClient(timeout=self._timeout)

    async def _teardown(self) -> None:
        """Close the HTTP client."""
        if hasattr(self, "_client"):
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _acm_request(
        self,
        target_action: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a signed ACM JSON API request.

        Args:
            target_action: ACM action name (e.g. ``RequestCertificate``).
            payload: JSON request body dict.

        Returns:
            Parsed JSON response body.

        Raises:
            NotFoundError: If the certificate is not found.
            APIError: For any ACM API error.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        body = json.dumps(payload)
        payload_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()

        headers: dict[str, str] = {
            "Content-Type": "application/x-amz-json-1.1",
            "X-Amz-Target": f"{_TARGET_PREFIX}.{target_action}",
            "x-amz-date": amz_date,
            "Host": self._host,
        }

        sign_v4(
            "POST",
            self._base_url + "/",
            headers,
            payload_hash,
            self._access_key,
            self._secret_key,
            self._region,
            service="acm",
            session_token=self._session_token,
        )

        response = await self._client.post(
            self._base_url + "/",
            content=body,
            headers=headers,
        )

        if response.status_code >= 400:
            try:
                err_body = response.json()
            except Exception:
                err_body = {"message": response.text}

            err_type = err_body.get("__type", "")
            err_msg = err_body.get("message", err_body.get("Message", ""))
            full_msg = f"ACM {target_action} error: {err_type} - {err_msg}"

            if "ResourceNotFoundException" in err_type or "NotFound" in err_type:
                raise NotFoundError(
                    full_msg,
                    connector="acm",
                    action=target_action,
                    details=err_body,
                )
            raise APIError(
                full_msg,
                connector="acm",
                action=target_action,
                upstream_status=response.status_code,
                details=err_body,
            )

        # Some actions return empty bodies (e.g. DeleteCertificate).
        if not response.text or not response.text.strip():
            return {}
        return response.json()

    # ------------------------------------------------------------------
    # Actions -- Certificate management
    # ------------------------------------------------------------------

    @action("Request a new SSL/TLS certificate")
    async def request_certificate(
        self,
        domain_name: str,
        subject_alternative_names: list[str] | None = None,
        validation_method: str = "DNS",
    ) -> str:
        """Request a new ACM SSL/TLS certificate.

        Args:
            domain_name: The primary domain name for the certificate
                (e.g. ``example.com``).
            subject_alternative_names: Additional domain names to
                include in the certificate (e.g.
                ``["www.example.com", "api.example.com"]``).
            validation_method: Validation method (``DNS`` or ``EMAIL``).

        Returns:
            The certificate ARN string.
        """
        payload: dict[str, Any] = {
            "DomainName": domain_name,
            "ValidationMethod": validation_method,
        }
        if subject_alternative_names:
            payload["SubjectAlternativeNames"] = subject_alternative_names

        body = await self._acm_request("RequestCertificate", payload)
        return body.get("CertificateArn", "")

    @action("Describe a certificate")
    async def describe_certificate(
        self, certificate_arn: str,
    ) -> ACMCertificateDetail:
        """Retrieve detailed information about an ACM certificate.

        Args:
            certificate_arn: The ARN of the certificate.

        Returns:
            ACMCertificateDetail with full certificate information.
        """
        payload: dict[str, Any] = {
            "CertificateArn": certificate_arn,
        }

        body = await self._acm_request("DescribeCertificate", payload)
        cert = body.get("Certificate", {})
        return ACMCertificateDetail(
            certificate_arn=cert.get("CertificateArn", ""),
            domain_name=cert.get("DomainName", ""),
            status=cert.get("Status", ""),
            type=cert.get("Type", ""),
            issuer=cert.get("Issuer", ""),
            created_at=(
                str(cert.get("CreatedAt", ""))
                if cert.get("CreatedAt") else None
            ),
            not_before=(
                str(cert.get("NotBefore", ""))
                if cert.get("NotBefore") else None
            ),
            not_after=(
                str(cert.get("NotAfter", ""))
                if cert.get("NotAfter") else None
            ),
            subject_alternative_names=cert.get("SubjectAlternativeNames", []),
            domain_validation_options=cert.get("DomainValidationOptions", []),
            in_use_by=cert.get("InUseBy", []),
            renewal_eligibility=cert.get("RenewalEligibility", ""),
            key_algorithm=cert.get("KeyAlgorithm", ""),
            failure_reason=cert.get("FailureReason", ""),
        )

    @action("List certificates")
    async def list_certificates(
        self,
        statuses: list[str] | None = None,
    ) -> list[ACMCertificateSummary]:
        """List ACM certificates, optionally filtered by status.

        Args:
            statuses: Optional list of statuses to filter by (e.g.
                ``["ISSUED", "PENDING_VALIDATION"]``).

        Returns:
            List of ACMCertificateSummary objects.
        """
        payload: dict[str, Any] = {}
        if statuses:
            payload["CertificateStatuses"] = statuses

        body = await self._acm_request("ListCertificates", payload)
        summaries = body.get("CertificateSummaryList", [])
        return [
            ACMCertificateSummary(
                certificate_arn=s.get("CertificateArn", ""),
                domain_name=s.get("DomainName", ""),
                status=s.get("Status", ""),
                type=s.get("Type", ""),
            )
            for s in summaries
        ]

    @action("Delete a certificate", dangerous=True)
    async def delete_certificate(
        self, certificate_arn: str,
    ) -> dict:
        """Delete an ACM certificate.

        The certificate must not be associated with any AWS resources.

        Args:
            certificate_arn: The ARN of the certificate to delete.

        Returns:
            Dict with ``deleted`` status.
        """
        payload: dict[str, Any] = {
            "CertificateArn": certificate_arn,
        }

        await self._acm_request("DeleteCertificate", payload)
        return {"deleted": True, "certificate_arn": certificate_arn}

    @action("Get the certificate PEM and chain")
    async def get_certificate(
        self, certificate_arn: str,
    ) -> dict:
        """Get the PEM-encoded certificate and certificate chain.

        Only available for ACM-issued certificates that have been
        validated and issued.

        Args:
            certificate_arn: The ARN of the certificate.

        Returns:
            Dict with ``certificate`` (PEM string) and
            ``certificate_chain`` (PEM string).
        """
        payload: dict[str, Any] = {
            "CertificateArn": certificate_arn,
        }

        body = await self._acm_request("GetCertificate", payload)
        return {
            "certificate": body.get("Certificate", ""),
            "certificate_chain": body.get("CertificateChain", ""),
        }

    @action("Export a certificate and private key")
    async def export_certificate(
        self,
        certificate_arn: str,
        passphrase: str,
    ) -> dict:
        """Export a private certificate and its private key.

        Only works with certificates issued by a Private CA.

        Args:
            certificate_arn: The ARN of the certificate to export.
            passphrase: Passphrase to encrypt the private key.

        Returns:
            Dict with ``certificate``, ``certificate_chain``, and
            ``private_key`` (PEM strings).
        """
        import base64

        payload: dict[str, Any] = {
            "CertificateArn": certificate_arn,
            "Passphrase": base64.b64encode(
                passphrase.encode("utf-8"),
            ).decode("ascii"),
        }

        body = await self._acm_request("ExportCertificate", payload)
        return {
            "certificate": body.get("Certificate", ""),
            "certificate_chain": body.get("CertificateChain", ""),
            "private_key": body.get("PrivateKey", ""),
        }

    # ------------------------------------------------------------------
    # Actions -- Tagging
    # ------------------------------------------------------------------

    @action("Add tags to a certificate")
    async def add_tags_to_certificate(
        self,
        certificate_arn: str,
        tags: list[dict],
    ) -> dict:
        """Add tags to an ACM certificate.

        Args:
            certificate_arn: The ARN of the certificate to tag.
            tags: List of tag dicts, each with ``Key`` and ``Value``.

        Returns:
            Empty dict on success.
        """
        payload: dict[str, Any] = {
            "CertificateArn": certificate_arn,
            "Tags": tags,
        }

        await self._acm_request("AddTagsToCertificate", payload)
        return {}

    @action("Remove tags from a certificate")
    async def remove_tags_from_certificate(
        self,
        certificate_arn: str,
        tags: list[dict],
    ) -> dict:
        """Remove tags from an ACM certificate.

        Args:
            certificate_arn: The ARN of the certificate to untag.
            tags: List of tag dicts identifying tags to remove. Each
                dict should contain at least ``Key``.

        Returns:
            Empty dict on success.
        """
        payload: dict[str, Any] = {
            "CertificateArn": certificate_arn,
            "Tags": tags,
        }

        await self._acm_request("RemoveTagsFromCertificate", payload)
        return {}

    @action("List tags for a certificate")
    async def list_tags_for_certificate(
        self,
        certificate_arn: str,
    ) -> list[ACMTag]:
        """List tags for an ACM certificate.

        Args:
            certificate_arn: The ARN of the certificate.

        Returns:
            List of ACMTag objects.
        """
        payload: dict[str, Any] = {
            "CertificateArn": certificate_arn,
        }

        body = await self._acm_request("ListTagsForCertificate", payload)
        tag_list = body.get("Tags", [])
        return [
            ACMTag(
                key=t.get("Key", ""),
                value=t.get("Value", ""),
            )
            for t in tag_list
        ]

    # ------------------------------------------------------------------
    # Actions -- Validation
    # ------------------------------------------------------------------

    @action("Resend validation email for a certificate")
    async def resend_validation_email(
        self,
        certificate_arn: str,
        domain: str,
        validation_domain: str,
    ) -> dict:
        """Resend the email used for domain validation.

        Only applicable when ``ValidationMethod`` is ``EMAIL``.

        Args:
            certificate_arn: The ARN of the certificate.
            domain: The domain name that needs validation.
            validation_domain: The domain to which validation email
                is sent (e.g. the base domain for subdomains).

        Returns:
            Empty dict on success.
        """
        payload: dict[str, Any] = {
            "CertificateArn": certificate_arn,
            "Domain": domain,
            "ValidationDomain": validation_domain,
        }

        await self._acm_request("ResendValidationEmail", payload)
        return {}
