import logging
import time
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = logging.getLogger("policy_api.requests")

#: Applied to every response. This is a JSON API, not an HTML-rendering one, so the CSP is
#: deliberately minimal (nothing here ever serves a page a browser would execute script/styles
#: from); the other headers matter regardless of content type.
#: HSTS/`Strict-Transport-Security` is intentionally not set here: TLS termination is a deployment
#: decision not yet made (`docs/operations/deployment.md`), and a wrong host header behind a
#: misconfigured proxy could pin HSTS for real users — that belongs at the edge/proxy layer once a
#: provider is chosen, not hardcoded into the app.
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
}

#: FastAPI's default Swagger UI at /docs loads its JS/CSS from a CDN (cdn.jsdelivr.net) — a
#: strict `default-src 'none'` CSP would silently render it blank. Every other header (frame
#: denial, no-sniff, referrer, permissions) still applies there; only the CSP is relaxed, and only
#: for the docs surface itself.
_DOCS_PATHS = ("/docs", "/openapi.json", "/redoc")
_DOCS_CSP = (
    "default-src 'none'; script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; img-src 'self' data: "
    "https://fastapi.tiangolo.com; connect-src 'self'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        headers = dict(_SECURITY_HEADERS)
        if request.url.path in _DOCS_PATHS:
            headers["Content-Security-Policy"] = _DOCS_CSP
        for name, value in headers.items():
            response.headers.setdefault(name, value)
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id", str(uuid4()))[:128]
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["x-request-id"] = request_id
            return response
        finally:
            logger.info(
                "request_complete",
                extra={
                    "fields": {
                        "request_id": request_id,
                        "endpoint": request.url.path,
                        "method": request.method,
                        "status": status,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                    }
                },
            )
