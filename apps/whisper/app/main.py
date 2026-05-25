from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, UploadFile
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_MAX_BYTES = 25 * 1024 * 1024  # 25 MB


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    from app.transcriber import _model
    _model()  # pre-load on startup
    yield


app = FastAPI(title="Whisper transcription service", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "model": os.getenv("WHISPER_MODEL", "large-v3-turbo")}


@app.post("/transcribe")
async def transcribe_audio(audio: UploadFile) -> JSONResponse:
    data = await audio.read()
    if len(data) > _MAX_BYTES:
        return JSONResponse(status_code=400, content={"error": "Audio exceeds 25 MB limit"})
    from app.transcriber import transcribe
    transcript = transcribe(data)
    return JSONResponse(content={"transcript": transcript})
