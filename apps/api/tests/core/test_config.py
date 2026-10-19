"""Deployed environments must fail fast on missing or dev-default config."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import Settings

_DEPLOYED_OK: dict[str, Any] = {
    "database_url": "postgresql://u:p@db/dental",
    "s3_bucket_phi_documents": "dental-phi-documents-staging",
    "s3_bucket_era_files": "dental-era-files-staging",
    "s3_bucket_exports": "dental-exports-staging",
    "cognito_user_pool_id": "us-east-1_abc",
    "cognito_client_id": "client123",
    "app_encryption_key": "a-real-key",
}


def _settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, **{**_DEPLOYED_OK, **overrides})  # type: ignore[call-arg]


@pytest.mark.parametrize("env", ["staging", "production"])
def test_deployed_env_with_complete_config_loads(env: str) -> None:
    assert _settings(api_env=env).api_env == env


@pytest.mark.parametrize("env", ["staging", "production"])
@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("s3_bucket_phi_documents", "dental-phi-documents-local"),
        ("s3_bucket_era_files", "dental-era-files-local"),
        ("s3_bucket_exports", "dental-exports-local"),
        ("cognito_user_pool_id", ""),
        ("cognito_client_id", ""),
        ("app_encryption_key", ""),
    ],
)
def test_deployed_env_rejects_dev_or_missing_config(env: str, field: str, bad_value: str) -> None:
    with pytest.raises(ValidationError, match=field):
        _settings(api_env=env, **{field: bad_value})


def test_development_keeps_local_defaults() -> None:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None, api_env="development", database_url="postgresql://u:p@db/dental"
    )
    assert settings.s3_bucket_phi_documents == "dental-phi-documents-local"
    assert settings.cognito_user_pool_id == ""
