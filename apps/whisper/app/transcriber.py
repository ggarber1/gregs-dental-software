from __future__ import annotations

import io
import logging
import os

logger = logging.getLogger(__name__)

_model_instance = None


def _model():
    global _model_instance
    if _model_instance is None:
        from faster_whisper import WhisperModel

        model_size = os.getenv("WHISPER_MODEL", "large-v3-turbo")
        device = os.getenv("WHISPER_DEVICE", "cpu")
        compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
        logger.info("Loading Whisper model %s on %s (%s)", model_size, device, compute_type)
        _model_instance = WhisperModel(model_size, device=device, compute_type=compute_type)
        logger.info("Whisper model loaded")
    return _model_instance


def transcribe(audio_bytes: bytes) -> str:
    """Transcribe audio bytes to text. Audio is never written to disk."""
    model = _model()
    buf = io.BytesIO(audio_bytes)
    segments, _ = model.transcribe(buf, language="en", beam_size=5)
    return " ".join(seg.text.strip() for seg in segments).strip()
