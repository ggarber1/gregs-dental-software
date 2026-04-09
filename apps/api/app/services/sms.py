import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)


async def send_sms(to: str, body: str) -> None:
    """Send an SMS via Twilio.

    In development (or when Twilio credentials are not configured), logs the
    message body instead of sending. This lets the full intake flow be exercised
    locally without a Twilio account.

    Raises on Twilio API errors so the caller can surface them to the user.
    """
    settings = get_settings()

    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        logger.info(
            "SMS send skipped (Twilio not configured). To=%s Body=%s",
            to,
            body,
        )
        return

    # Import lazily so missing twilio dep doesn't crash the entire app on startup
    # (e.g. in environments where only eligibility features are needed).
    try:
        from twilio.rest import Client
    except ImportError as exc:
        raise RuntimeError(
            "twilio package is not installed. Run: uv add twilio"
        ) from exc

    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    client.messages.create(
        to=to,
        from_=settings.twilio_from_number,
        body=body,
    )
    logger.info("SMS sent to %s", to)
