from __future__ import annotations

import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class WhisperUnavailableError(Exception):
    pass


class WhisperTimeoutError(Exception):
    pass


async def transcribe(audio_bytes: bytes, filename: str = "audio.webm") -> str:
    """Send audio bytes to the Whisper service and return the transcript.

    Audio bytes are sent as a multipart upload and never written to disk.
    """
    settings = get_settings()
    endpoint = settings.whisper_endpoint_url
    if not endpoint:
        raise WhisperUnavailableError("WHISPER_ENDPOINT_URL is not configured")

    timeout = httpx.Timeout(connect=5.0, read=90.0, write=15.0, pool=5.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{endpoint}/transcribe",
                files={"audio": (filename, audio_bytes)},
            )
            response.raise_for_status()
            return str(response.json()["transcript"])
    except httpx.ConnectError as exc:
        raise WhisperUnavailableError(f"Whisper service unreachable: {exc}") from exc
    except httpx.TimeoutException as exc:
        raise WhisperTimeoutError(f"Whisper service timed out: {exc}") from exc
    except Exception as exc:
        raise WhisperUnavailableError(f"Whisper service error: {exc}") from exc
