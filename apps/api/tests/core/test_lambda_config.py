"""Unit tests for loading Lambda settings from SSM."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from app.core.lambda_config import SSM_TO_ENV, load_settings_from_ssm

_PATH = "/dental/staging"


def _client(*pages: list[dict[str, str]]) -> MagicMock:
    client = MagicMock()
    client.get_paginator.return_value.paginate.return_value = [
        {"Parameters": params} for params in pages
    ]
    return client


def _param(name: str, value: str) -> dict[str, str]:
    return {"Name": f"{_PATH}/{name}", "Value": value}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for env_name in SSM_TO_ENV.values():
        monkeypatch.delenv(env_name, raising=False)


def test_maps_parameters_to_env_across_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(
        [_param("db/url", "postgresql://db"), _param("app/encryption_key", "k")],
        [_param("twilio/phone_number", "+16175550100")],
    )

    loaded = load_settings_from_ssm(_PATH, client=client)

    import os

    assert loaded == 3
    assert os.environ["DATABASE_URL"] == "postgresql://db"
    assert os.environ["APP_ENCRYPTION_KEY"] == "k"
    assert os.environ["TWILIO_FROM_NUMBER"] == "+16175550100"
    client.get_paginator.assert_called_once_with("get_parameters_by_path")
    kwargs: dict[str, Any] = client.get_paginator.return_value.paginate.call_args.kwargs
    assert kwargs == {"Path": _PATH, "Recursive": True, "WithDecryption": True}


def test_ignores_unmapped_parameters(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client([_param("clearinghouse/api_key", "secret"), _param("e2e/practice_id", "x")])

    assert load_settings_from_ssm(_PATH, client=client) == 0


def test_existing_env_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://explicit")
    client = _client([_param("db/url", "postgresql://from-ssm")])

    assert load_settings_from_ssm(_PATH, client=client) == 0

    import os

    assert os.environ["DATABASE_URL"] == "postgresql://explicit"


def test_path_defaults_to_ssm_parameter_path_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SSM_PARAMETER_PATH", f"{_PATH}/")
    client = _client([_param("redis/url", "redis://cache:6379")])

    assert load_settings_from_ssm(client=client) == 1
    assert client.get_paginator.return_value.paginate.call_args.kwargs["Path"] == _PATH
