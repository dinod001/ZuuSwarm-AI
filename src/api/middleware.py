"""
HTTP middleware for the ZuuSwarm AI API.

Adds three pieces of cross-cutting behaviour to every request:

1. ``X-Request-Id`` — generated if the client didn't supply one; echoed
   back on the response for log correlation.
2. ``X-Latency-Ms`` — server-side wall-clock time per request.
3. Unhandled-exception handler — turns any uncaught error into a clean
   JSON 500 with the request id, instead of Starlette's default HTML.

IMPORTANT: Uses a pure-ASGI middleware instead of Starlette's
BaseHTTPMiddleware to avoid buffering StreamingResponse / SSE bodies.
BaseHTTPMiddleware reads the ENTIRE response body into memory before
forwarding it, which breaks Server-Sent Events (the browser won't see
any events until the stream closes).
"""

import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.types import ASGIApp, Receive, Scope, Send


class RequestContextMiddleware:
    """
    Pure-ASGI middleware that stamps every HTTP request/response with a
    request-id and measures wall-clock latency WITHOUT buffering the body.

    Unlike BaseHTTPMiddleware, this never consumes the response body, so
    StreamingResponse / SSE works correctly.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Extract or generate request-id
        headers = dict(scope.get("headers", []))
        req_id = (
            headers.get(b"x-request-id", b"").decode()
            or uuid.uuid4().hex[:16]
        )

        # Stash on scope so downstream code can access it via request.state
        scope.setdefault("state", {})["request_id"] = req_id

        start = time.perf_counter()

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                # Inject our headers into the initial response frame
                latency_ms = int((time.perf_counter() - start) * 1000)
                extra_headers = [
                    (b"x-request-id", req_id.encode()),
                    (b"x-latency-ms", str(latency_ms).encode()),
                ]
                existing = list(message.get("headers", []))
                message = {**message, "headers": existing + extra_headers}
            await send(message)

        await self.app(scope, receive, send_wrapper)


def install_middleware(app: FastAPI) -> None:
    """Attach middleware + the catch-all exception handler."""
    app.add_middleware(RequestContextMiddleware)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        req_id = getattr(request.state, "request_id", None)
        logger.exception("Unhandled error on {} {} [req_id={}]", request.method, request.url.path, req_id)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": req_id},
            headers={"x-request-id": req_id or ""},
        )
