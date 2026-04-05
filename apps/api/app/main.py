from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup: initialise connections (DB pool, Redis, etc.) in later modules
    yield
    # Shutdown: close connections cleanly


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Dental PMS API",
        version="0.1.0",
        # Disable docs in production — API is internal only
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routes ────────────────────────────────────────────────────────────────
    @app.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    # Additional routers will be registered here per module (1.4 onward)

    return app


app = create_app()
