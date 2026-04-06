import logging
import time
import uuid
from typing import Any

import httpx
from jose import JWTError, jwk, jwt
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Routes that do not require authentication.
_PUBLIC_PATHS: set[str] = {"/health"}
_PUBLIC_PREFIXES: tuple[str, ...] = ("/intake/",)

# JWKS cache: { kid -> public key object }
_jwks_cache: dict[str, Any] = {}
_jwks_fetched_at: float = 0.0
_JWKS_TTL = 3600.0  # re-fetch JWKS once per hour


class AuthenticatedUser:
    __slots__ = ("sub", "email", "practice_id", "groups")

    def __init__(
        self,
        sub: str,
        email: str,
        practice_id: uuid.UUID | None,
        groups: list[str],
    ) -> None:
        self.sub = sub
        self.email = email
        self.practice_id = practice_id
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


class CognitoAuthMiddleware(BaseHTTPMiddleware):
    """
    Verifies Cognito JWT on every non-public request.

    On success: attaches AuthenticatedUser to request.state.user.
    On failure: returns 401 immediately — never passes the request downstream.
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

        raw_practice_id = claims.get("custom:practice_id")
        practice_id: uuid.UUID | None = None
        if raw_practice_id:
            try:
                practice_id = uuid.UUID(raw_practice_id)
            except ValueError:
                logger.warning("Malformed practice_id claim: %s", raw_practice_id)

        request.state.user = AuthenticatedUser(
            sub=claims["sub"],
            email=claims.get("email", ""),
            practice_id=practice_id,
            groups=claims.get("cognito:groups", []),
        )

        return await call_next(request)
