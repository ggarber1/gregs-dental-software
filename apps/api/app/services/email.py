import logging

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
