import logging
import time
import uuid
from typing import Any

import httpx
from jose import JWTError, jwk, jwt
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings
from app.core.db import get_session_factory
from app.models.user import PracticeUser, User

logger = logging.getLogger(__name__)

# Routes that do not require authentication.
_PUBLIC_PATHS: set[str] = {"/health"}
_PUBLIC_PREFIXES: tuple[str, ...] = ("/intake/",)

# JWKS cache: { kid -> public key object }
_jwks_cache: dict[str, Any] = {}
_jwks_fetched_at: float = 0.0
_JWKS_TTL = 3600.0  # re-fetch JWKS once per hour


class AuthenticatedUser:
    """
    Populated on request.state.user after successful JWT verification.

    practice_id and role are only set when X-Practice-ID header is present
    and the user has an active practice_users row for that practice.
    Routes that require practice scope must check practice_id is not None.
    """

    __slots__ = ("sub", "email", "user_id", "practice_id", "role", "groups")

    def __init__(
        self,
        sub: str,
        email: str,
        user_id: uuid.UUID | None,
        practice_id: uuid.UUID | None,
        role: str | None,
        groups: list[str],
    ) -> None:
        self.sub = sub
        self.email = email
        self.user_id = user_id
        self.practice_id = practice_id
        self.role = role
        self.groups = groups


def _jwks_url() -> str:
    settings = get_settings()
    return (
        f"https://cognito-idp.{settings.cognito_region}.amazonaws.com"
        f"/{settings.cognito_user_pool_id}/.well-known/jwks.json"
    )


async def _get_public_key(kid: str) -> Any:
    global _jwks_cache, _jwks_fetched_at

    now = time.monotonic()
    if not _jwks_cache or (now - _jwks_fetched_at) > _JWKS_TTL:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(_jwks_url())
            resp.raise_for_status()
            keys = resp.json().get("keys", [])
        _jwks_cache = {k["kid"]: jwk.construct(k) for k in keys}
        _jwks_fetched_at = now

    return _jwks_cache.get(kid)


def _is_public(path: str) -> bool:
    if path in _PUBLIC_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES)


async def _resolve_practice_membership(
    cognito_sub: str,
    practice_id: uuid.UUID,
) -> tuple[uuid.UUID, str] | None:
    """
    Look up the user's internal ID and role for the given practice.

    Returns (user_id, role) if the membership is active, None otherwise.
    """
    async with get_session_factory()() as session:
        user_row = await session.scalar(
            select(User.id).where(User.cognito_sub == cognito_sub)
        )
        if user_row is None:
            return None

        membership = await session.scalar(
            select(PracticeUser).where(
                PracticeUser.user_id == user_row,
                PracticeUser.practice_id == practice_id,
                PracticeUser.is_active.is_(True),
            )
        )
        if membership is None:
            return None

        return user_row, membership.role


class CognitoAuthMiddleware(BaseHTTPMiddleware):
    """
    Verifies Cognito JWT on every non-public request.

    If X-Practice-ID header is present, also validates the user has an active
    practice_users row for that practice and populates practice_id + role.

    On success: attaches AuthenticatedUser to request.state.user.
    On failure: returns 401/403 immediately — never passes the request downstream.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if _is_public(request.url.path):
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                {"error": {"code": "MISSING_TOKEN", "message": "Authorization header required"}},
                status_code=401,
            )

        token = auth_header[len("Bearer "):]
        settings = get_settings()

        try:
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get("kid", "")
            public_key = await _get_public_key(kid)
            if public_key is None:
                raise JWTError("Unknown key ID")

            claims = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                audience=settings.cognito_client_id,
            )
        except JWTError as exc:
            logger.warning("JWT verification failed: %s", exc)
            return JSONResponse(
                {"error": {"code": "INVALID_TOKEN", "message": "Token is invalid or expired"}},
                status_code=401,
            )
        except httpx.HTTPError as exc:
            logger.error("JWKS fetch failed: %s", exc)
            return JSONResponse(
                {"error": {"code": "AUTH_UNAVAILABLE", "message": "Authentication service error"}},
                status_code=503,
            )

        user_id: uuid.UUID | None = None
        practice_id: uuid.UUID | None = None
        role: str | None = None

        raw_practice_id = request.headers.get("X-Practice-ID")
        if raw_practice_id:
            try:
                practice_id = uuid.UUID(raw_practice_id)
            except ValueError:
                return JSONResponse(
                    {"error": {"code": "INVALID_PRACTICE_ID", "message": "X-Practice-ID must be a valid UUID"}},
                    status_code=400,
                )

            result = await _resolve_practice_membership(claims["sub"], practice_id)
            if result is None:
                logger.warning(
                    "Practice access denied: sub=%s practice_id=%s",
                    claims["sub"],
                    practice_id,
                )
                return JSONResponse(
                    {"error": {"code": "PRACTICE_ACCESS_DENIED", "message": "Practice access denied"}},
                    status_code=403,
                )

            user_id, role = result

        request.state.user = AuthenticatedUser(
            sub=claims["sub"],
            email=claims.get("email", ""),
            user_id=user_id,
            practice_id=practice_id,
            role=role,
            groups=claims.get("cognito:groups", []),
        )

        return await call_next(request)
