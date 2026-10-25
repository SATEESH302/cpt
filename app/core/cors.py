"""Keep rejected CORS preflights within the public JSON error contract."""

from starlette.datastructures import Headers
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.types import Receive, Scope, Send

from app.core.exceptions import error_response


class ApiCORSMiddleware(CORSMiddleware):
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] == "OPTIONS":
            headers = Headers(scope=scope)
            if "origin" in headers and "access-control-request-method" in headers:
                response = self.preflight_response(headers)
                if response.status_code >= 400:
                    cors_headers = {
                        key: value for key, value in response.headers.items()
                        if key.lower() not in {"content-length", "content-type"}
                    }
                    response = error_response(
                        Request(scope), 400, "CORS_REQUEST_DENIED",
                        "CORS request is not permitted.", cors_headers,
                    )
                await response(scope, receive, send)
                return
        await super().__call__(scope, receive, send)
