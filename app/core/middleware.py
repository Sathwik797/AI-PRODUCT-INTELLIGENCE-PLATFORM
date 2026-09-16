"""Production Hardening Middleware and Global Exception Handlers.

Phase 10:
- Request ID generation and propagation (X-Request-ID)
- Unified, safe global error handling with zero leakage of SQL, paths, stack traces, or credentials
"""

from datetime import datetime, timezone
import logging
from typing import Any
import uuid

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.schemas.error import APIErrorDetail, APIErrorResponse

logger = logging.getLogger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware attaching a unique X-Request-ID to every request and response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
        request.state.request_id = req_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response


def _get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")


def _get_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handles explicit HTTPExceptions and converts to the standard APIErrorResponse envelope."""
    req_id = _get_request_id(request)
    code_map = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "CONFLICT",
        422: "UNPROCESSABLE_ENTITY",
        429: "RATE_LIMIT_EXCEEDED",
        500: "INTERNAL_SERVER_ERROR",
        503: "SERVICE_UNAVAILABLE"
    }
    error_code = code_map.get(exc.status_code, f"HTTP_{exc.status_code}")

    error_resp = APIErrorResponse(
        error=APIErrorDetail(
            code=error_code,
            message=str(exc.detail),
            request_id=req_id,
            timestamp=_get_timestamp()
        )
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=error_resp.model_dump(),
        headers={"X-Request-ID": req_id}
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handles Pydantic/FastAPI request validation errors safely."""
    req_id = _get_request_id(request)
    safe_details: list[dict[str, Any]] = []

    for err in exc.errors():
        safe_details.append({
            "loc": [str(x) for x in err.get("loc", [])],
            "msg": err.get("msg", "Invalid value"),
            "type": err.get("type", "validation_error")
        })

    error_resp = APIErrorResponse(
        error=APIErrorDetail(
            code="VALIDATION_ERROR",
            message="Request body or parameter validation failed.",
            request_id=req_id,
            timestamp=_get_timestamp(),
            details=safe_details
        )
    )
    return JSONResponse(
        status_code=422,
        content=error_resp.model_dump(),
        headers={"X-Request-ID": req_id}
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler for unexpected server exceptions.
    
    Strictly prevents leaking stack traces, SQL strings, file paths, or provider keys.
    Logs full diagnostic traceback server-side tagged with request_id.
    """
    req_id = _get_request_id(request)
    logger.error(
        f"Unhandled exception processing request [{req_id}] {request.method} {request.url.path}: {exc}",
        exc_info=True
    )

    error_resp = APIErrorResponse(
        error=APIErrorDetail(
            code="INTERNAL_SERVER_ERROR",
            message="An internal server error occurred. Please reference the request_id for support.",
            request_id=req_id,
            timestamp=_get_timestamp()
        )
    )
    return JSONResponse(
        status_code=500,
        content=error_resp.model_dump(),
        headers={"X-Request-ID": req_id}
    )
