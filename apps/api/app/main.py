import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.requests import Request

from app.core.config import get_settings
from app.core.db import dispose_engine, get_session_factory
from app.core.redis import close_redis, get_redis
from app.middleware.audit import AuditLogMiddleware
from app.middleware.auth import CognitoAuthMiddleware
from app.middleware.idempotency import IdempotencyMiddleware
from app.middleware.security import SecurityHeadersMiddleware
from app.routers import insurance, intake, patients

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup: initialise connections so they're ready before the first request.
    get_session_factory()
    get_redis()
    logger.info("DB and Redis connections initialised")
    yield
    # Shutdown: drain connections cleanly.
    await dispose_engine()
    await close_redis()
    logger.info("DB and Redis connections closed")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Dental PMS API",
        version="0.1.0",
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
        lifespan=lifespan,
    )

    # ── Middleware (outermost first) ───────────────────────────────────────────
    # 1. Security headers — wraps everything, headers on all responses incl. errors
    app.add_middleware(SecurityHeadersMiddleware)
    # 2. Auth — rejects unauthenticated requests before any business logic runs
    app.add_middleware(CognitoAuthMiddleware)
    # 3. Audit log — runs after auth so request.state.user is populated
    app.add_middleware(AuditLogMiddleware)
    # 4. Idempotency — innermost mutation guard; reads/writes Redis cache
    app.add_middleware(IdempotencyMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Exception handlers ────────────────────────────────────────────────────
    # Normalise all error responses to {"error": {"code": ..., "message": ...}}
    # so routes and middleware share the same shape.

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail
        # Route guards raise HTTPException with detail={"error": {...}}
        if isinstance(detail, dict) and "error" in detail:
            return JSONResponse(status_code=exc.status_code, content=detail)
        # Fall back for plain string details (e.g. FastAPI 404 for unknown routes)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": str(exc.status_code), "message": str(detail)}},
        )

    # ── Routes ────────────────────────────────────────────────────────────────
    @app.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        db_status = "ok"
        redis_status = "ok"

        try:
            async with get_session_factory()() as session:
                await session.execute(text("SELECT 1"))
        except Exception:
            logger.exception("Health check: DB unreachable")
            db_status = "error"

        try:
            await get_redis().ping()  # type: ignore[misc]
        except Exception:
            logger.exception("Health check: Redis unreachable")
            redis_status = "error"

        return {"status": "ok", "db": db_status, "redis": redis_status}

    # Additional routers registered here per module (2.x onward)
    app.include_router(patients.router)
    app.include_router(insurance.router)
    app.include_router(intake.public_router)
    app.include_router(intake.staff_router)

    return app


app = create_app()
