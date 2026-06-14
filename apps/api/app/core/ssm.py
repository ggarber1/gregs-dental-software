from __future__ import annotations

import logging
from typing import Any

import boto3
from botocore.config import Config

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_BOTO_CONFIG = Config(connect_timeout=5, read_timeout=10, retries={"max_attempts": 2})


# Not cached (unlike sqs.py): SSM is called infrequently; a fresh client avoids
# stale-credential issues with IAM role rotation on long-lived containers.
def _get_ssm_client() -> Any:
    settings = get_settings()
    kwargs: dict[str, Any] = {
        "service_name": "ssm",
        "region_name": settings.aws_region,
        "config": _BOTO_CONFIG,
    }
    if settings.aws_endpoint_url:
        kwargs["endpoint_url"] = settings.aws_endpoint_url
    return boto3.client(**kwargs)


def get_ssm_parameter(path: str) -> str | None:
    """Fetch a (SecureString) parameter from SSM. Returns None if absent."""
    client = _get_ssm_client()
    try:
        resp = client.get_parameter(Name=path, WithDecryption=True)
        return str(resp["Parameter"]["Value"])
    except Exception as exc:  # noqa: BLE001 — missing/permission errors → treat as unavailable
        logger.warning("SSM parameter unavailable at %s: %s", path, exc)
        return None
