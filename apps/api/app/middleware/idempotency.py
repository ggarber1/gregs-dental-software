import json
import logging

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.redis import get_redis

logger = logging.getLogger(__name__)

_MUTATION_METHODS: frozenset[str] = frozenset({"POST", "PATCH", "PUT", "DELETE"})
_TTL_SECONDS = 86_400  # 24 hours


def _cache_key(practice_id: str | None, idempotency_key: str) -> str:
    scope = practice_id or "anonymous"
    return f"idempotency:{scope}:{idempotency_key}"


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """
    Enforces Idempotency-Key header on all mutation requests.

    Behaviour:
    - Missing header on POST/PATCH/PUT/DELETE → 422
    - Key seen before and response is cached → return cached response immediately
    - Key not seen → allow request through, cache response for 24 h

    The cache key is scoped to practice_id to prevent cross-tenant collisions.
    Redis errors are logged but never block the request — the middleware degrades
    gracefully rather than taking down the API.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method not in _MUTATION_METHODS:
            return await call_next(request)

        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return JSONResponse(
                {
                    "error": {
                        "code": "MISSING_IDEMPOTENCY_KEY",
                        "message": "Idempotency-Key header is required for mutating requests",
                    }
                },
                status_code=422,
            )

        user = getattr(request.state, "user", None)
        practice_id = str(user.practice_id) if user and user.practice_id else None
        key = _cache_key(practice_id, idempotency_key)

        try:
            redis = get_redis()
            cached = await redis.get(key)
            if cached is not None:
                payload = json.loads(cached)
                return Response(
                    content=payload["body"],
                    status_code=payload["status_code"],
                    media_type="application/json",
                    headers={"X-Idempotent-Replayed": "true"},
                )
        except Exception:
            logger.exception("Redis read failed for idempotency key %s", idempotency_key)

        response = await call_next(request)

        # Only cache successful (2xx) and client-error (4xx) responses.
        # Never cache 5xx — those represent transient failures that should be retried.
        if response.status_code < 500:
            try:
                body = b""
                async for chunk in response.body_iterator:  # type: ignore[attr-defined]
                    body += chunk if isinstance(chunk, bytes) else chunk.encode()

                payload = json.dumps({"status_code": response.status_code, "body": body.decode()})
                await redis.setex(key, _TTL_SECONDS, payload)

                return Response(
                    content=body,
                    status_code=response.status_code,
                    media_type=response.media_type,
                    headers=dict(response.headers),
                )
            except Exception:
                logger.exception("Redis write failed for idempotency key %s", idempotency_key)

        return response
