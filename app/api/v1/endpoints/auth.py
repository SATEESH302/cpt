"""Patient authentication; session cookies never appear in JSON or logs."""

import secrets
from datetime import timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.exceptions import ApplicationError
from app.db.session import get_db
from app.schemas.auth import (
    AuthPatient, CsrfResponse, LoginRequest, MessageResponse,
    RegistrationRequest, SessionResponse,
)
from app.services.auth import AuthService, session_csrf

router = APIRouter(prefix="/auth", tags=["Patient Authentication"])
DB = Annotated[Session, Depends(get_db)]


def no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


def set_cookie(response: Response, request: Request, name: str, value: str, age: int) -> None:
    response.set_cookie(
        name, value, max_age=age, path="/", httponly=True,
        secure=request.app.state.settings.auth_secure_cookies, samesite="lax",
    )


def require_origin(request: Request) -> None:
    settings = request.app.state.settings
    origin = request.headers.get("origin")
    if origin not in settings.cors_origins or (
        settings.auth_secure_cookies and (
            request.url.scheme != "https" or not origin.startswith("https://")
        )
    ):
        raise ApplicationError("CSRF_REJECTED", "The request origin is not permitted.", 403)
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        raise ApplicationError("CSRF_REJECTED", "Send an application/json request.", 403)


def require_pre_auth_csrf(request: Request) -> None:
    require_origin(request)
    cookie = request.cookies.get(request.app.state.settings.auth_csrf_cookie_name, "")
    header = request.headers.get("x-csrf-token", "")
    if len(cookie) != 43 or not secrets.compare_digest(cookie.encode(), header.encode()):
        raise ApplicationError("CSRF_REJECTED", "Please refresh the form and try again.", 403)


def session_payload(patient, token, expires) -> SessionResponse:
    return SessionResponse(
        user=AuthPatient.model_validate(patient), csrf_token=session_csrf(token),
        expires_at=expires.replace(tzinfo=timezone.utc).isoformat(),
    )


@router.get("/csrf", response_model=CsrfResponse)
def csrf(request: Request, response: Response) -> CsrfResponse:
    # Pre-login double-submit nonce, protected by exact Origin checks on writes.
    token = secrets.token_urlsafe(32)
    set_cookie(response, request, request.app.state.settings.auth_csrf_cookie_name, token, 900)
    no_store(response)
    return CsrfResponse(csrf_token=token)


@router.post("/register", response_model=MessageResponse, status_code=201,
             dependencies=[Depends(require_pre_auth_csrf)])
def register(payload: RegistrationRequest, request: Request, response: Response, db: DB):
    settings = request.app.state.settings
    service = AuthService(db, settings)
    service.throttle("register-ip:" + request.client.host, settings.auth_login_attempts)
    service.register(payload)
    no_store(response)
    return MessageResponse(message="Registration successful. Please log in.")


@router.post("/login", response_model=SessionResponse,
             dependencies=[Depends(require_pre_auth_csrf)])
def login(payload: LoginRequest, request: Request, response: Response, db: DB):
    settings = request.app.state.settings
    service = AuthService(db, settings)
    service.throttle("login-ip:" + request.client.host, settings.auth_ip_attempts)
    patient, token, expires = service.login(
        payload.identifier, payload.password, request.cookies.get(settings.auth_cookie_name)
    )
    set_cookie(response, request, settings.auth_cookie_name, token, settings.auth_session_seconds)
    response.delete_cookie(settings.auth_csrf_cookie_name, path="/", secure=settings.auth_secure_cookies, httponly=True, samesite="lax")
    no_store(response)
    return session_payload(patient, token, expires)


@router.get("/me", response_model=SessionResponse)
def current_patient(request: Request, response: Response, db: DB):
    settings = request.app.state.settings
    token = request.cookies.get(settings.auth_cookie_name)
    patient, session = AuthService(db, settings).current(token)
    no_store(response)
    return session_payload(patient, token, session.expires_at)


@router.post("/logout", response_model=MessageResponse,
             dependencies=[Depends(require_origin)])
def logout(request: Request, response: Response, db: DB):
    settings = request.app.state.settings
    token = request.cookies.get(settings.auth_cookie_name)
    service = AuthService(db, settings)
    service.current(token)
    header = request.headers.get("x-csrf-token", "")
    if not secrets.compare_digest(session_csrf(token).encode(), header.encode()):
        raise ApplicationError("CSRF_REJECTED", "Please refresh the page and try again.", 403)
    service.logout(token)
    for name in (settings.auth_cookie_name, settings.auth_csrf_cookie_name):
        response.delete_cookie(name, path="/", secure=settings.auth_secure_cookies, httponly=True, samesite="lax")
    no_store(response)
    return MessageResponse(message="You have been logged out.")
