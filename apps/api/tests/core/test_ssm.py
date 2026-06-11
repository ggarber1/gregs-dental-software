from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.core.ssm import get_ssm_parameter


def test_get_ssm_parameter_returns_decrypted_value():
    fake_client = MagicMock()
    fake_client.get_parameter.return_value = {"Parameter": {"Value": "secret-key"}}
    with patch("app.core.ssm._get_ssm_client", return_value=fake_client):
        value = get_ssm_parameter("/dental/practice/abc/stedi-key")
    assert value == "secret-key"
    fake_client.get_parameter.assert_called_once_with(
        Name="/dental/practice/abc/stedi-key", WithDecryption=True
    )


def test_get_ssm_parameter_missing_returns_none():
    fake_client = MagicMock()
    # The broad except in get_ssm_parameter catches any exception from get_parameter.
    fake_client.get_parameter.side_effect = KeyError("nope")
    with patch("app.core.ssm._get_ssm_client", return_value=fake_client):
        assert get_ssm_parameter("/missing") is None
