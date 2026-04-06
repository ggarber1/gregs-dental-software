from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

_HSTS_MAX_AGE = 63_072_000  # 2 years


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Adds HIPAA-aligned security headers to every response.

    Applied outermost so headers are present even on error responses
    from downstream middleware.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["Strict-Transport-Security"] = (
            f"max-age={_HSTS_MAX_AGE}; includeSubDomains"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "object-src 'none'; "
            "frame-ancestors 'none';"
        )
        return response
