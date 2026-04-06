import asyncio
import logging
import uuid
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.db import get_session_factory
from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)

# Paths that never contain PHI and don't need to be audited.
_SKIP_AUDIT_PATHS: set[str] = {"/health", "/docs", "/redoc", "/openapi.json"}


def _extract_resource(path: str) -> tuple[str | None, str | None]:
    """
    Derive resource_type and resource_id from the URL path.

    e.g. /api/v1/patients/abc-123  →  ("patients", "abc-123")
         /api/v1/patients          →  ("patients", None)
    """
    parts = [p for p in path.strip("/").split("/") if p]
    # Skip "api/v1" prefix
    if len(parts) >= 3 and parts[0] == "api" and parts[1] == "v1":
        parts = parts[2:]

    if not parts:
        return None, None

    resource_type = parts[0]
    resource_id = parts[1] if len(parts) >= 2 else None
    return resource_type, resource_id


async def _write_audit_log(entry: dict[str, Any]) -> None:
    try:
        async with get_session_factory()() as session:
            session.add(AuditLog(**entry))
            await session.commit()
    except Exception:
        logger.exception("Failed to write audit log entry: %s", entry)


class AuditLogMiddleware(BaseHTTPMiddleware):
    """
    Records every PHI-touching request to the insert-only audit_logs table.

    Runs after CognitoAuthMiddleware so request.state.user is populated.
    The write is fire-and-forget via asyncio.create_task — it never blocks
    the response, but failures are logged as errors.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in _SKIP_AUDIT_PATHS:
            return await call_next(request)

        response = await call_next(request)

        user = getattr(request.state, "user", None)
        resource_type, resource_id = _extract_resource(request.url.path)

        entry: dict[str, Any] = {
            "id": uuid.uuid4(),
            "practice_id": getattr(user, "practice_id", None),
            "user_id": getattr(user, "sub", None),
            "action": request.method,
            "path": request.url.path,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "ip_address": _get_client_ip(request),
            "user_agent": request.headers.get("User-Agent"),
            "status_code": response.status_code,
        }

        asyncio.create_task(_write_audit_log(entry))

        return response


def _get_client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None
