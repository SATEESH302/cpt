"""Centralized, sanitized HTTP errors and reusable application exceptions."""

import logging
from http import HTTPStatus
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.schemas.errors import ErrorDetail, ErrorResponse

logger = logging.getLogger("diagnostic.errors")


class ApplicationError(Exception):
    """Messages must be explicitly safe to display to clients."""

    def __init__(
        self, code: str, message: str, status_code: int = 400
    ) -> None:
        if not 400 <= status_code <= 599:
            raise ValueError("Application error status must be between 400 and 599")
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None) or str(uuid4())
    request.state.request_id = request_id
    body = ErrorResponse(
        error=ErrorDetail(code=code, message=message), request_id=request_id
    )
    if request.url.path.startswith(request.app.state.settings.api_v1_prefix + "/auth/"):
        headers = {**(headers or {}), "Cache-Control": "no-store", "Pragma": "no-cache"}
    return JSONResponse(
        status_code=status_code, content=body.model_dump(), headers=headers
    )


async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    try:
        code = HTTPStatus(exc.status_code).name
    except ValueError:
        code = "HTTP_ERROR"
    message = exc.detail if isinstance(exc.detail, str) else "Request failed."
    if exc.status_code >= 500:
        message = "An unexpected error occurred."
    return error_response(request, exc.status_code, code, message, exc.headers)


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # Do not echo validation inputs: these can contain credentials or health data.
    return error_response(
        request, 422, "VALIDATION_ERROR", "Request validation failed."
    )


async def application_error_handler(
    request: Request, exc: ApplicationError
) -> JSONResponse:
    return error_response(request, exc.status_code, exc.code, exc.message)


async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Exception messages and traceback locals can contain patient data.
    logger.error(
        "unexpected_error",
        extra={
            "request_id": getattr(request.state, "request_id", "unknown"),
            "exception_type": type(exc).__name__,
        },
    )
    return error_response(
        request, 500, "INTERNAL_SERVER_ERROR", "An unexpected error occurred."
    )


async def database_error_handler(
    request: Request, exc: SQLAlchemyError
) -> JSONResponse:
    logger.error(
        "database_operation_failed",
        extra={"request_id": getattr(request.state, "request_id", "unknown"),
               "exception_type": type(exc).__name__},
    )
    if isinstance(exc, IntegrityError):
        return error_response(
            request, 409, "DATABASE_CONFLICT",
            "The operation conflicts with existing data."
        )
    if isinstance(exc, OperationalError) or getattr(
        exc, "connection_invalidated", False
    ):
        return error_response(
            request, 503, "DATABASE_UNAVAILABLE", "Database service is unavailable."
        )
    return error_response(
        request, 500, "DATABASE_ERROR", "The database operation could not be completed."
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, http_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(ApplicationError, application_error_handler)
    app.add_exception_handler(SQLAlchemyError, database_error_handler)
    app.add_exception_handler(Exception, unexpected_error_handler)


class ErrorBoundaryMiddleware:
    """Catch errors inside CORS, including when framework debug mode is enabled."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def track_send(message: dict) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, track_send)
        except Exception as exc:
            response = await unexpected_error_handler(Request(scope), exc)
            if started:
                # A streaming response cannot be replaced after headers are sent.
                raise
            await response(scope, receive, send)
