import json
import logging
from functools import cache
from typing import Any

import boto3
from botocore.config import Config

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_BOTO_CONFIG = Config(connect_timeout=5, read_timeout=25, retries={"max_attempts": 2})


@cache
def _get_sqs_client():
    settings = get_settings()
    kwargs: dict[str, Any] = {
        "service_name": "sqs",
        "region_name": settings.aws_region,
        "config": _BOTO_CONFIG,
    }
    if settings.aws_endpoint_url:
        kwargs["endpoint_url"] = settings.aws_endpoint_url
    return boto3.client(**kwargs)


@cache
def _get_queue_url(queue_name: str) -> str:
    client = _get_sqs_client()
    response = client.get_queue_url(QueueName=queue_name)
    url: str = response["QueueUrl"]
    return url


def enqueue_message_sync(queue_name: str, body: dict[str, Any]) -> str:
    """Enqueue a JSON message. Returns the SQS MessageId."""
    client = _get_sqs_client()
    url = _get_queue_url(queue_name)
    response = client.send_message(QueueUrl=url, MessageBody=json.dumps(body))
    msg_id: str = response["MessageId"]
    logger.info("Enqueued SQS message %s to %s", msg_id, queue_name)
    return msg_id


def poll_messages_sync(
    queue_name: str,
    *,
    max_messages: int = 10,
    wait_seconds: int = 20,
) -> list[dict[str, Any]]:
    """Long-poll SQS. Returns up to max_messages messages (may be empty)."""
    client = _get_sqs_client()
    url = _get_queue_url(queue_name)
    response = client.receive_message(
        QueueUrl=url,
        MaxNumberOfMessages=max_messages,
        WaitTimeSeconds=wait_seconds,
        VisibilityTimeout=60,
    )
    messages: list[dict[str, Any]] = response.get("Messages", [])
    return messages


def delete_message_sync(queue_name: str, receipt_handle: str) -> None:
    """Delete a processed SQS message."""
    client = _get_sqs_client()
    url = _get_queue_url(queue_name)
    client.delete_message(QueueUrl=url, ReceiptHandle=receipt_handle)
    logger.debug("Deleted SQS message from %s", queue_name)
