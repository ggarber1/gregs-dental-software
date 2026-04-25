import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)


async def send_sms(to: str, body: str) -> str | None:
    """Send an SMS via Twilio.

    Returns the Twilio message SID on success, or None in dev (no-send) mode.
    Raises on Twilio API errors so the caller can mark the reminder failed.
    """
    settings = get_settings()

    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        logger.info(
            "SMS send skipped (Twilio not configured). To=%s Body=%s",
            to,
            body,
        )
        return None

    # Import lazily so missing twilio dep doesn't crash the entire app on startup.
    try:
        from twilio.rest import Client
    except ImportError as exc:
        raise RuntimeError("twilio package is not installed. Run: uv add twilio") from exc

    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    message = client.messages.create(
        to=to,
        from_=settings.twilio_from_number,
        body=body,
    )
    sid: str = message.sid
    logger.info("SMS sent to %s (SID=%s)", to, sid)
    return sid
