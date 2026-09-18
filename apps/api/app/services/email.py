import logging
from email.message import EmailMessage

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import get_settings

logger = logging.getLogger(__name__)


async def send_email(to: str, subject: str, html_body: str, text_body: str) -> str | None:
    """Send an email via AWS SES.

    Returns the SES MessageId on success, or None in dev (no-send) mode.
    Raises on SES errors so the caller can mark the reminder failed.
    """
    settings = get_settings()

    if not settings.ses_from_address:
        logger.info(
            "Email send skipped (SES not configured). To=%s Subject=%s",
            to,
            subject,
        )
        return None

    client = boto3.client(
        "ses",
        region_name=settings.aws_region,
        endpoint_url=settings.aws_endpoint_url or None,
    )

    kwargs: dict[str, object] = {
        "Source": settings.ses_from_address,
        "Destination": {"ToAddresses": [to]},
        "Message": {
            "Subject": {"Data": subject, "Charset": "UTF-8"},
            "Body": {
                "Text": {"Data": text_body, "Charset": "UTF-8"},
                "Html": {"Data": html_body, "Charset": "UTF-8"},
            },
        },
    }
    if settings.ses_configuration_set:
        kwargs["ConfigurationSetName"] = settings.ses_configuration_set

    try:
        response = client.send_email(**kwargs)
    except (BotoCoreError, ClientError) as exc:
        raise RuntimeError(f"SES send_email failed: {exc}") from exc

    message_id: str = response["MessageId"]
    logger.info("Email sent to %s (SES MessageId=%s)", to, message_id)
    return message_id


async def send_email_with_attachment(
    *,
    to: str,
    subject: str,
    html_body: str,
    text_body: str,
    attachment_bytes: bytes,
    attachment_filename: str,
    attachment_maintype: str = "application",
    attachment_subtype: str = "pdf",
) -> str | None:
    """Send a MIME email with one attachment via SES SendRawEmail.

    Same contract as `send_email`: returns the SES MessageId, or None in dev
    (no-send) mode; raises RuntimeError on SES errors.
    """
    settings = get_settings()

    if not settings.ses_from_address:
        logger.info(
            "Email send skipped (SES not configured). To=%s Subject=%s Attachment=%s",
            to,
            subject,
            attachment_filename,
        )
        return None

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.ses_from_address
    msg["To"] = to
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    msg.add_attachment(
        attachment_bytes,
        maintype=attachment_maintype,
        subtype=attachment_subtype,
        filename=attachment_filename,
    )

    client = boto3.client(
        "ses",
        region_name=settings.aws_region,
        endpoint_url=settings.aws_endpoint_url or None,
    )
    kwargs: dict[str, object] = {
        "Source": settings.ses_from_address,
        "Destinations": [to],
        "RawMessage": {"Data": msg.as_bytes()},
    }
    if settings.ses_configuration_set:
        kwargs["ConfigurationSetName"] = settings.ses_configuration_set

    try:
        response = client.send_raw_email(**kwargs)
    except (BotoCoreError, ClientError) as exc:
        raise RuntimeError(f"SES send_raw_email failed: {exc}") from exc

    message_id: str = response["MessageId"]
    logger.info("Email with attachment sent to %s (SES MessageId=%s)", to, message_id)
    return message_id
