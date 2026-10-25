"""JSON logs and pure ASGI request correlation, without request payloads."""

import json
import logging
import sys
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI
from starlette.routing import Match, Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("diagnostic")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for key in (
            "request_id", "method", "path", "status", "duration_ms",
            "exception_type", "environment",
        ):
            if hasattr(record, key):
                data[key] = getattr(record, key)
        return json.dumps(data)


def configure_logging(level: str) -> None:
    logger.setLevel(level)
    if not any(getattr(handler, "diagnostic_handler", False)
               for handler in logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.diagnostic_handler = True
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    logger.propagate = False
    # Uvicorn access logs include query strings; use our sanitized request logs.
    logging.getLogger("uvicorn.access").disabled = True


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp, application: FastAPI) -> None:
        self.app = app
        # Public OpenAPI paths include router prefixes across FastAPI versions.
        # These routes are used only for safe template matching, never dispatch.
        self.routes = [
            Route(path, endpoint=application, methods=list(operations))
            for path, operations in application.openapi()["paths"].items()
        ]
        self.routes.extend(
            route for route in application.routes if isinstance(route, Route)
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        # Log templates, not path parameter values or unknown user-supplied paths.
        path = "[unmatched]"
        for route in self.routes:
            match, _ = route.matches(scope)
            if match != Match.NONE:
                path = getattr(route, "path", "[matched]")
                break
        fields = {"request_id": request_id, "method": scope["method"], "path": path}
        logger.info("request_started", extra=fields)
        start = perf_counter()
        status = 500

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = [
                    (key, value) for key, value in message.get("headers", [])
                    if key.lower() != b"x-request-id"
                ]
                headers.append((b"x-request-id", request_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            logger.info(
                "request_completed",
                extra={**fields, "status": status,
                       "duration_ms": round((perf_counter() - start) * 1000, 3)},
            )
