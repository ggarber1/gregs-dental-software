from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.routers.patients import _require_practice_scope, _require_write_role
from app.services import bedrock_extraction, whisper_client
from app.services.bedrock_extraction import BedrockExtractionError
from app.services.whisper_client import WhisperTimeoutError, WhisperUnavailableError

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/patients/{patient_id}",
    tags=["ambient-notes"],
)

_MAX_AUDIO_BYTES = 25 * 1024 * 1024  # 25 MB
_ALLOWED_CONTENT_TYPES = {
    "audio/webm",
    "audio/ogg",
    "audio/mpeg",
    "audio/mp4",
    "audio/wav",
    "audio/x-wav",
    "audio/m4a",
    "audio/x-m4a",
    "application/octet-stream",  # some browsers omit the specific type
}


class AmbientNoteDraftResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    draft: str
    detected_template: str | None = Field(None, alias="detectedTemplate")


@router.post("/ambient-note-draft")
async def create_ambient_note_draft(
    patient_id: uuid.UUID,
    request: Request,
    audio: UploadFile,
    template_hint: str | None = None,
) -> JSONResponse:
    _require_practice_scope(request)
    _require_write_role(request)

    content_type = (audio.content_type or "").split(";")[0].strip().lower()
    if content_type and content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported audio format")

    audio_bytes = await audio.read()
    if len(audio_bytes) > _MAX_AUDIO_BYTES:
        raise HTTPException(status_code=400, detail="Audio exceeds 25 MB limit")

    filename = audio.filename or "audio.webm"

    try:
        transcript = await whisper_client.transcribe(audio_bytes, filename=filename)
    except WhisperUnavailableError as exc:
        logger.warning("Whisper service unavailable: %s", exc)
        raise HTTPException(status_code=502, detail="Transcription service unavailable") from exc
    except WhisperTimeoutError as exc:
        logger.warning("Whisper service timed out: %s", exc)
        raise HTTPException(status_code=504, detail="Transcription service timed out") from exc

    logger.info(
        "Transcribed ambient dictation: patient_id=%s transcript_length=%d",
        patient_id,
        len(transcript),
    )

    try:
        result = await bedrock_extraction.draft_note(transcript, template_hint)
    except BedrockExtractionError as exc:
        logger.error("Bedrock extraction failed: %s", exc)
        raise HTTPException(status_code=502, detail="Note extraction service unavailable") from exc

    return JSONResponse(
        content=AmbientNoteDraftResponse(
            draft=result["draft"],
            detectedTemplate=result.get("detected_template"),
        ).model_dump(by_alias=True)
    )
