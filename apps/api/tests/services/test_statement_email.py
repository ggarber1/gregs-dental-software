"""SES raw-email attachment sending. boto3 is mocked."""

from __future__ import annotations

import email
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from app.services.email import send_email_with_attachment


def _settings(from_address: str = "billing@sunrise.test", config_set: str = ""):
    return SimpleNamespace(
        ses_from_address=from_address,
        ses_configuration_set=config_set,
        aws_region="us-east-1",
        aws_endpoint_url=None,
    )


async def _send(**overrides):
    kwargs = dict(
        to="jane@example.com",
        subject="Statement from Sunrise Dental",
        html_body="<p>Your statement is attached.</p>",
        text_body="Your statement is attached.",
        attachment_bytes=b"%PDF-1.7 fake",
        attachment_filename="statement-2026-09-18.pdf",
    )
    kwargs.update(overrides)
    return await send_email_with_attachment(**kwargs)


async def test_builds_mime_with_pdf_attachment():
    client = MagicMock()
    client.send_raw_email.return_value = {"MessageId": "msg-123"}
    with (
        patch("app.services.email.get_settings", return_value=_settings(config_set="cs-1")),
        patch("app.services.email.boto3.client", return_value=client),
    ):
        message_id = await _send()

    assert message_id == "msg-123"
    kwargs = client.send_raw_email.call_args.kwargs
    assert kwargs["Source"] == "billing@sunrise.test"
    assert kwargs["Destinations"] == ["jane@example.com"]
    assert kwargs["ConfigurationSetName"] == "cs-1"
    parsed = email.message_from_bytes(kwargs["RawMessage"]["Data"])
    assert parsed["Subject"] == "Statement from Sunrise Dental"
    assert parsed["From"] == "billing@sunrise.test"
    assert parsed["To"] == "jane@example.com"
    attachments = [p for p in parsed.walk() if p.get_filename() == "statement-2026-09-18.pdf"]
    assert len(attachments) == 1
    assert attachments[0].get_content_type() == "application/pdf"
    assert attachments[0].get_payload(decode=True) == b"%PDF-1.7 fake"
    assert attachments[0].get_content_disposition() == "attachment"
    assert attachments[0]["Content-Transfer-Encoding"] == "base64"
    bodies = {p.get_content_type() for p in parsed.walk() if not p.is_multipart()}
    assert {"text/plain", "text/html"} <= bodies


async def test_from_name_sets_display_name():
    client = MagicMock()
    client.send_raw_email.return_value = {"MessageId": "msg-456"}
    with (
        patch("app.services.email.get_settings", return_value=_settings()),
        patch("app.services.email.boto3.client", return_value=client),
    ):
        await _send(from_name="Sunrise Dental")

    kwargs = client.send_raw_email.call_args.kwargs
    assert kwargs["Source"] == "Sunrise Dental <billing@sunrise.test>"
    parsed = email.message_from_bytes(kwargs["RawMessage"]["Data"])
    assert parsed["From"] == "Sunrise Dental <billing@sunrise.test>"


async def test_skips_when_ses_unconfigured():
    with (
        patch("app.services.email.get_settings", return_value=_settings(from_address="")),
        patch("app.services.email.boto3.client") as boto,
    ):
        result = await _send()
    assert result is None
    boto.assert_not_called()


async def test_raises_runtime_error_on_ses_failure():
    client = MagicMock()
    client.send_raw_email.side_effect = ClientError(
        {"Error": {"Code": "MessageRejected", "Message": "nope"}}, "SendRawEmail"
    )
    with (
        patch("app.services.email.get_settings", return_value=_settings()),
        patch("app.services.email.boto3.client", return_value=client),
        pytest.raises(RuntimeError, match="SES send_raw_email failed"),
    ):
        await _send()
