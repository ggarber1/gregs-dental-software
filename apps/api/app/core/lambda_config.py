"""Load deployed settings from SSM at Lambda cold start.

ECS injects SSM SecureStrings into the API container as env vars (modules/ecs
`secrets`); Lambda can't, so the workers read the same parameters here and expose
them under the same env names before Settings is built. Must run before the first
get_settings() call (Settings is cached).
"""

from __future__ import annotations

import logging
import os
from typing import Any

import boto3
from botocore.config import Config

logger = logging.getLogger(__name__)

_BOTO_CONFIG = Config(connect_timeout=5, read_timeout=10, retries={"max_attempts": 2})

# SSM name (relative to SSM_PARAMETER_PATH) -> env var. Keep in sync with the API
# task's `secrets` in infra/terraform/modules/ecs/main.tf.
SSM_TO_ENV: dict[str, str] = {
    "db/url": "DATABASE_URL",
    "redis/url": "REDIS_URL",
    "app/secret_key": "SECRET_KEY",
    "app/encryption_key": "APP_ENCRYPTION_KEY",
    "app/web_url": "APP_URL",
    "cognito/user_pool_id": "COGNITO_USER_POOL_ID",
    "cognito/app_client_id": "COGNITO_CLIENT_ID",
    "twilio/account_sid": "TWILIO_ACCOUNT_SID",
    "twilio/auth_token": "TWILIO_AUTH_TOKEN",
    "twilio/phone_number": "TWILIO_FROM_NUMBER",
}


def _ssm_client() -> Any:
    return boto3.client(
        "ssm", region_name=os.environ.get("AWS_REGION", "us-east-1"), config=_BOTO_CONFIG
    )


def load_settings_from_ssm(path: str | None = None, *, client: Any | None = None) -> int:
    """Export mapped SSM parameters under `path` as env vars; returns how many were set.

    Values already present in the environment win (explicit Lambda config, tests).
    """
    path = (path or os.environ["SSM_PARAMETER_PATH"]).rstrip("/")
    client = client or _ssm_client()
    loaded = 0
    pages = client.get_paginator("get_parameters_by_path").paginate(
        Path=path, Recursive=True, WithDecryption=True
    )
    for page in pages:
        for param in page["Parameters"]:
            env_name = SSM_TO_ENV.get(param["Name"].removeprefix(f"{path}/"))
            if env_name and env_name not in os.environ:
                os.environ[env_name] = param["Value"]
                loaded += 1
    logger.info("Loaded %d settings from SSM path %s", loaded, path)
    return loaded
