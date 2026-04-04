"""AWS SQS connector -- send, receive, and manage messages in SQS queues.

Uses the SQS JSON API with ``X-Amz-Target`` headers. Credentials should be
``"access_key:secret_key:region"`` format.

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

from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import (
    ConnectorCategory,
    ProtocolType,
    RateLimitSpec,
)
from toolsconnector.types import PaginatedList, PageState
from toolsconnector.errors import APIError, NotFoundError, ValidationError

from toolsconnector.connectors.s3._signing import get_signing_key, hmac_sha256

from .types import (
    SQSBatchResult,
    SQSBatchResultEntry,
    SQSMessage,
    SQSQueue,
    SQSQueueAttributes,
    SQSSendResult,
)

logger = logging.getLogger("toolsconnector.sqs")


def _sqs_sign_v4(
    method: str,
    url: str,
    headers: dict[str, str],
    body: str,
    access_key: str,
    secret_key: str,
    region: str,
) -> dict[str, str]:
    """Build AWS SigV4 Authorization header for SQS JSON API.

    Args:
        method: HTTP method.
        url: Full request URL.
        headers: Request headers (must include host, x-amz-date).
        body: Request body string.
        access_key: AWS access key ID.
        secret_key: AWS secret access key.
        region: AWS region.

    Returns:
        Updated headers dict with Authorization header.
    """
    import urllib.parse
    import hmac

    parsed = urllib.parse.urlparse(url)
    canonical_uri = urllib.parse.quote(parsed.path or "/", safe="/")
    canonical_querystring = ""

    payload_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    headers["x-amz-content-sha256"] = payload_hash

    amz_date = headers["x-amz-date"]
    date_stamp = amz_date[:8]

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

    credential_scope = f"{date_stamp}/{region}/sqs/aws4_request"
    canonical_hash = hashlib.sha256(
        canonical_request.encode("utf-8"),
    ).hexdigest()
    string_to_sign = (
        f"AWS4-HMAC-SHA256\n"
        f"{amz_date}\n"
        f"{credential_scope}\n"
        f"{canonical_hash}"
    )

    signing_key = get_signing_key(secret_key, date_stamp, region, "sqs")
    signature = hmac.new(
        signing_key,
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    headers["Authorization"] = (
        f"AWS4-HMAC-SHA256 "
        f"Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers_str}, "
        f"Signature={signature}"
    )
    return headers


class SQS(BaseConnector):
    """Connect to AWS SQS to send, receive, and manage queue messages.

    Credentials format: ``"access_key_id:secret_access_key:region"``
    Uses the SQS JSON API (``X-Amz-Target: AmazonSQS.{Action}``).

    .. note::

        SigV4 signing is simplified. For production, use ``boto3``.
    """

    name = "sqs"
    display_name = "AWS SQS"
    category = ConnectorCategory.MESSAGE_QUEUE
    protocol = ProtocolType.REST
    base_url = "https://sqs.us-east-1.amazonaws.com"
    description = (
        "Connect to AWS Simple Queue Service (SQS) to send, receive, "
        "and manage messages in distributed queues."
    )
    _rate_limit_config = RateLimitSpec(rate=100, period=1, burst=300)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Parse credentials and initialise the HTTP client."""
        creds = str(self._credentials)
        parts = creds.split(":")
        if len(parts) < 3:
            raise ValueError(
                "SQS credentials must be 'access_key:secret_key:region'"
            )
        self._access_key = parts[0]
        self._secret_key = parts[1]
        self._region = parts[2]
        self._base_url = f"https://sqs.{self._region}.amazonaws.com"

        self._client = httpx.AsyncClient(timeout=self._timeout)

    async def _teardown(self) -> None:
        """Close the HTTP client."""
        if hasattr(self, "_client"):
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _sqs_request(
        self,
        target_action: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a signed SQS JSON API request.

        Args:
            target_action: SQS action name (e.g. ``SendMessage``).
            payload: JSON request body dict.

        Returns:
            Parsed JSON response body.

        Raises:
            NotFoundError: If the queue is not found.
            APIError: For any SQS API error.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        body = json.dumps(payload)

        headers: dict[str, str] = {
            "Content-Type": "application/x-amz-json-1.0",
            "X-Amz-Target": f"AmazonSQS.{target_action}",
            "X-Amz-Date": amz_date,
            "Host": f"sqs.{self._region}.amazonaws.com",
        }

        signed = _sqs_sign_v4(
            "POST",
            self._base_url + "/",
            headers,
            body,
            self._access_key,
            self._secret_key,
            self._region,
        )

        response = await self._client.post(
            self._base_url + "/",
            content=body,
            headers=signed,
        )

        if response.status_code >= 400:
            try:
                err_body = response.json()
            except Exception:
                err_body = {"message": response.text}

            err_type = err_body.get("__type", "")
            err_msg = err_body.get("message", err_body.get("Message", ""))
            full_msg = f"SQS {target_action} error: {err_type} - {err_msg}"

            if "NonExistentQueue" in err_type or "NotFound" in err_type:
                raise NotFoundError(
                    full_msg,
                    connector="sqs",
                    action=target_action,
                    details=err_body,
                )
            raise APIError(
                full_msg,
                connector="sqs",
                action=target_action,
                upstream_status=response.status_code,
                details=err_body,
            )

        return response.json()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    @action("Send a message to an SQS queue")
    async def send_message(
        self,
        queue_url: str,
        message_body: str,
        delay_seconds: Optional[int] = None,
    ) -> SQSSendResult:
        """Send a message to an SQS queue.

        Args:
            queue_url: The URL of the target SQS queue.
            message_body: The message body string.
            delay_seconds: Delay in seconds before the message becomes visible.

        Returns:
            SQSSendResult with message_id and MD5 digest.
        """
        payload: dict[str, Any] = {
            "QueueUrl": queue_url,
            "MessageBody": message_body,
        }
        if delay_seconds is not None:
            payload["DelaySeconds"] = delay_seconds

        body = await self._sqs_request("SendMessage", payload)
        return SQSSendResult(
            message_id=body.get("MessageId", ""),
            md5_of_message_body=body.get("MD5OfMessageBody", ""),
            sequence_number=body.get("SequenceNumber"),
        )

    @action("Receive messages from an SQS queue")
    async def receive_messages(
        self,
        queue_url: str,
        max_messages: int = 1,
        wait_time: Optional[int] = None,
    ) -> list[SQSMessage]:
        """Receive messages from an SQS queue.

        Args:
            queue_url: The URL of the SQS queue to poll.
            max_messages: Maximum number of messages to receive (1-10).
            wait_time: Long-poll wait time in seconds (0-20).

        Returns:
            List of received SQSMessage objects.
        """
        payload: dict[str, Any] = {
            "QueueUrl": queue_url,
            "MaxNumberOfMessages": min(max_messages, 10),
            "AttributeNames": ["All"],
        }
        if wait_time is not None:
            payload["WaitTimeSeconds"] = wait_time

        body = await self._sqs_request("ReceiveMessage", payload)
        messages = body.get("Messages", [])
        return [
            SQSMessage(
                message_id=m.get("MessageId", ""),
                receipt_handle=m.get("ReceiptHandle", ""),
                body=m.get("Body", ""),
                md5_of_body=m.get("MD5OfBody", ""),
                attributes=m.get("Attributes", {}),
                message_attributes=m.get("MessageAttributes", {}),
            )
            for m in messages
        ]

    @action("Delete a message from an SQS queue", dangerous=True)
    async def delete_message(
        self,
        queue_url: str,
        receipt_handle: str,
    ) -> None:
        """Delete a message from an SQS queue using its receipt handle.

        Args:
            queue_url: The URL of the SQS queue.
            receipt_handle: The receipt handle of the message to delete.
        """
        await self._sqs_request("DeleteMessage", {
            "QueueUrl": queue_url,
            "ReceiptHandle": receipt_handle,
        })

    @action("List SQS queues in the account")
    async def list_queues(
        self,
        prefix: Optional[str] = None,
    ) -> PaginatedList[SQSQueue]:
        """List SQS queues, optionally filtered by name prefix.

        Args:
            prefix: Filter queues to those whose name starts with this prefix.

        Returns:
            Paginated list of SQSQueue objects.
        """
        payload: dict[str, Any] = {}
        if prefix:
            payload["QueueNamePrefix"] = prefix

        body = await self._sqs_request("ListQueues", payload)
        urls = body.get("QueueUrls", [])
        queues = [SQSQueue(queue_url=u) for u in urls]
        return PaginatedList(
            items=queues,
            page_state=PageState(has_more=False),
        )

    @action("Get attributes of an SQS queue")
    async def get_queue_attributes(
        self,
        queue_url: str,
    ) -> SQSQueueAttributes:
        """Get attributes of an SQS queue.

        Args:
            queue_url: The URL of the SQS queue.

        Returns:
            SQSQueueAttributes with queue metadata.
        """
        body = await self._sqs_request("GetQueueAttributes", {
            "QueueUrl": queue_url,
            "AttributeNames": ["All"],
        })
        attrs = body.get("Attributes", {})
        return SQSQueueAttributes(
            queue_arn=attrs.get("QueueArn", ""),
            approximate_number_of_messages=int(
                attrs.get("ApproximateNumberOfMessages", "0")
            ),
            approximate_number_of_messages_not_visible=int(
                attrs.get("ApproximateNumberOfMessagesNotVisible", "0")
            ),
            approximate_number_of_messages_delayed=int(
                attrs.get("ApproximateNumberOfMessagesDelayed", "0")
            ),
            created_timestamp=attrs.get("CreatedTimestamp", ""),
            last_modified_timestamp=attrs.get("LastModifiedTimestamp", ""),
            visibility_timeout=attrs.get("VisibilityTimeout", ""),
            maximum_message_size=attrs.get("MaximumMessageSize", ""),
            message_retention_period=attrs.get("MessageRetentionPeriod", ""),
            delay_seconds=attrs.get("DelaySeconds", ""),
            receive_message_wait_time_seconds=attrs.get(
                "ReceiveMessageWaitTimeSeconds", ""
            ),
            raw_attributes=attrs,
        )

    @action("Create a new SQS queue")
    async def create_queue(
        self,
        queue_name: str,
        attributes: Optional[dict[str, str]] = None,
    ) -> SQSQueue:
        """Create a new SQS queue.

        Args:
            queue_name: Name for the new queue.
            attributes: Optional queue attributes (e.g. VisibilityTimeout).

        Returns:
            SQSQueue with the new queue URL.
        """
        payload: dict[str, Any] = {"QueueName": queue_name}
        if attributes:
            payload["Attributes"] = attributes

        body = await self._sqs_request("CreateQueue", payload)
        return SQSQueue(queue_url=body.get("QueueUrl", ""))

    @action("Purge all messages from an SQS queue", dangerous=True)
    async def purge_queue(self, queue_url: str) -> None:
        """Purge all messages from an SQS queue.

        Args:
            queue_url: The URL of the queue to purge.
        """
        await self._sqs_request("PurgeQueue", {"QueueUrl": queue_url})

    @action("Send a batch of messages to an SQS queue")
    async def send_message_batch(
        self,
        queue_url: str,
        entries: list[dict[str, Any]],
    ) -> SQSBatchResult:
        """Send a batch of up to 10 messages to an SQS queue.

        Args:
            queue_url: The URL of the target SQS queue.
            entries: List of message entries, each containing ``Id`` and
                ``MessageBody``, and optionally ``DelaySeconds``.

        Returns:
            SQSBatchResult with successful and failed entries.
        """
        body = await self._sqs_request("SendMessageBatch", {
            "QueueUrl": queue_url,
            "Entries": entries,
        })
        successful = [
            SQSBatchResultEntry(
                id=e.get("Id", ""),
                message_id=e.get("MessageId", ""),
                md5_of_message_body=e.get("MD5OfMessageBody", ""),
            )
            for e in body.get("Successful", [])
        ]
        return SQSBatchResult(
            successful=successful,
            failed=body.get("Failed", []),
        )
