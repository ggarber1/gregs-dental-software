import logging
from functools import cache
from typing import Any

import boto3
from botocore.config import Config

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_BOTO_CONFIG = Config(connect_timeout=5, read_timeout=60, retries={"max_attempts": 2})


@cache
def _get_s3_client() -> Any:
    settings = get_settings()
    kwargs: dict[str, Any] = {
        "service_name": "s3",
        "region_name": settings.aws_region,
        "config": _BOTO_CONFIG,
    }
    if settings.aws_endpoint_url:
        kwargs["endpoint_url"] = settings.aws_endpoint_url
    return boto3.client(**kwargs)


def put_object(bucket: str, key: str, body: bytes, content_type: str) -> None:
    """Upload bytes to S3 with SSE-S3 encryption."""
    _get_s3_client().put_object(
        Bucket=bucket,
        Key=key,
        Body=body,
        ContentType=content_type,
        ServerSideEncryption="AES256",
    )
    logger.info("S3 put_object: bucket=%s key=%s size=%d", bucket, key, len(body))


def get_object_bytes(bucket: str, key: str) -> bytes:
    """Download an S3 object and return its bytes."""
    response = _get_s3_client().get_object(Bucket=bucket, Key=key)
    data: bytes = response["Body"].read()
    return data


def delete_object(bucket: str, key: str) -> None:
    """Delete an S3 object."""
    _get_s3_client().delete_object(Bucket=bucket, Key=key)
    logger.info("S3 delete_object: bucket=%s key=%s", bucket, key)
