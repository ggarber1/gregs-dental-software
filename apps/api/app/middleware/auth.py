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
from app.models.patient_portal_account import PatientPortalAccount
from app.models.user import PracticeUser, User

logger = logging.getLogger(__name__)

# Routes that do not require authentication.
_PUBLIC_PATHS: set[str] = {"/health"}
_PUBLIC_PREFIXES: tuple[str, ...] = (
    "/api/intake/form/",
    "/api/v1/webhooks/",
    "/api/portal/invite/",
)

# Patient portal routes validated against the dedicated patient Cognito pool.
_PATIENT_AUTH_EXACT_PATHS: set[str] = {"/api/v1/portal/me"}

_JWKS_TTL = 3600.0  # re-fetch JWKS once per hour
_jwks_cache: dict[str, dict[str, Any]] = {}
_jwks_fetched_at: dict[str, float] = {}


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


class AuthenticatedPatient:
    """Populated on request.state.patient for patient portal routes."""

    __slots__ = ("sub", "email", "account_id", "patient_id", "practice_id")

    def __init__(
        self,
        sub: str,
        email: str,
        account_id: uuid.UUID,
        patient_id: uuid.UUID,
        practice_id: uuid.UUID,
    ) -> None:
        self.sub = sub
        self.email = email
        self.account_id = account_id
        self.patient_id = patient_id
        self.practice_id = practice_id


def _jwks_url(pool_id: str, region: str) -> str:
    return (
        f"https://cognito-idp.{region}.amazonaws.com"
        f"/{pool_id}/.well-known/jwks.json"
    )


async def _get_public_key(kid: str, pool_id: str, region: str) -> Any:
    cache_key = f"{region}:{pool_id}"
    now = time.monotonic()
    cache = _jwks_cache.get(cache_key, {})
    fetched_at = _jwks_fetched_at.get(cache_key, 0.0)

    if not cache or (now - fetched_at) > _JWKS_TTL:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(_jwks_url(pool_id, region))
            resp.raise_for_status()
            keys = resp.json().get("keys", [])
        cache = {k["kid"]: jwk.construct(k) for k in keys}
        _jwks_cache[cache_key] = cache
        _jwks_fetched_at[cache_key] = now

    return cache.get(kid)


def _is_public(path: str) -> bool:
    if path in _PUBLIC_PATHS:
        return True
    if any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES):
        # Invite completion requires patient auth even though prefix is public.
        return not path.endswith("/complete")
    return False


def _requires_patient_auth(path: str) -> bool:
    if path in _PATIENT_AUTH_EXACT_PATHS:
        return True
    return path.startswith("/api/portal/invite/") and path.endswith("/complete")


async def _resolve_practice_membership(
    cognito_sub: str,
    practice_id: uuid.UUID,
) -> tuple[uuid.UUID, str] | None:
    """
    Look up the user's internal ID and role for the given practice.

    Returns (user_id, role) if the membership is active, None otherwise.
    """
    async with get_session_factory()() as session:
        user_row = await session.scalar(select(User.id).where(User.cognito_sub == cognito_sub))
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


async def _resolve_active_patient_account(cognito_sub: str) -> PatientPortalAccount | None:
    async with get_session_factory()() as session:
        account = await session.scalar(
            select(PatientPortalAccount).where(
                PatientPortalAccount.cognito_sub == cognito_sub,
                PatientPortalAccount.status == "active",
            )
        )
        return account


async def _resolve_patient_from_invite_token(
    token: str,
    cognito_sub: str,
    email: str,
) -> AuthenticatedPatient | None:
    """Allow invite completion before the account is marked active."""
    async with get_session_factory()() as session:
        account = await session.scalar(
            select(PatientPortalAccount).where(PatientPortalAccount.invite_token == token)
        )
        if account is None or account.status != "invited":
            return None
        if account.email.lower() != email.lower():
            return None
        return AuthenticatedPatient(
            sub=cognito_sub,
            email=email,
            account_id=account.id,
            patient_id=account.patient_id,
            practice_id=account.practice_id,
        )


class CognitoAuthMiddleware(BaseHTTPMiddleware):
    """
    Verifies Cognito JWT on every non-public request.

    Staff routes use the staff Cognito pool + optional X-Practice-ID membership.
    Patient portal routes use the dedicated patient Cognito pool.
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

        token = auth_header[len("Bearer ") :]
        settings = get_settings()

        if _requires_patient_auth(request.url.path):
            return await self._handle_patient_auth(request, call_next, token, settings)

        return await self._handle_staff_auth(request, call_next, token, settings)

    async def _handle_patient_auth(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
        token: str,
        settings: Any,
    ) -> Response:
        if not settings.has_patient_auth:
            return JSONResponse(
                {
                    "error": {
                        "code": "PATIENT_AUTH_UNAVAILABLE",
                        "message": "Patient portal authentication is not configured",
                    }
                },
                status_code=503,
            )

        try:
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get("kid", "")
            public_key = await _get_public_key(
                kid,
                settings.cognito_patient_pool_id,
                settings.cognito_patient_region,
            )
            if public_key is None:
                raise JWTError("Unknown key ID")

            claims = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                audience=settings.cognito_patient_client_id,
            )
        except JWTError as exc:
            logger.warning("Patient JWT verification failed: %s", exc)
            return JSONResponse(
                {"error": {"code": "INVALID_TOKEN", "message": "Token is invalid or expired"}},
                status_code=401,
            )
        except httpx.HTTPError as exc:
            logger.error("Patient JWKS fetch failed: %s", exc)
            return JSONResponse(
                {"error": {"code": "AUTH_UNAVAILABLE", "message": "Authentication service error"}},
                status_code=503,
            )

        email = claims.get("email", "")
        sub = claims["sub"]
        path = request.url.path

        if path.endswith("/complete"):
            token_suffix = path.removeprefix("/api/portal/invite/").removesuffix("/complete")
            patient = await _resolve_patient_from_invite_token(token_suffix, sub, email)
        else:
            account = await _resolve_active_patient_account(sub)
            if account is None:
                return JSONResponse(
                    {
                        "error": {
                            "code": "PORTAL_ACCESS_DENIED",
                            "message": "No active patient portal account found",
                        }
                    },
                    status_code=403,
                )
            patient = AuthenticatedPatient(
                sub=sub,
                email=email,
                account_id=account.id,
                patient_id=account.patient_id,
                practice_id=account.practice_id,
            )

        if patient is None:
            return JSONResponse(
                {
                    "error": {
                        "code": "PORTAL_ACCESS_DENIED",
                        "message": "Portal access denied for this invite",
                    }
                },
                status_code=403,
            )

        request.state.patient = patient
        return await call_next(request)

    async def _handle_staff_auth(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
        token: str,
        settings: Any,
    ) -> Response:
        try:
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get("kid", "")
            public_key = await _get_public_key(
                kid,
                settings.cognito_user_pool_id,
                settings.cognito_region,
            )
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
                    {
                        "error": {
                            "code": "INVALID_PRACTICE_ID",
                            "message": "X-Practice-ID must be a valid UUID",
                        }
                    },
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
                    {
                        "error": {
                            "code": "PRACTICE_ACCESS_DENIED",
                            "message": "Practice access denied",
                        }
                    },
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
