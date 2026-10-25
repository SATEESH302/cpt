"""ASGI application factory and Uvicorn entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from app.api.v1.router import create_api_router
from app.core.config import Settings, get_settings
from app.core.cors import ApiCORSMiddleware
from app.core.exceptions import ErrorBoundaryMiddleware, register_exception_handlers
from app.core.logging import RequestLoggingMiddleware, configure_logging, logger
from app.schemas.errors import ErrorResponse
from app.db.session import Database, DatabaseConfigurationError
from app.db.verification import verify_connection


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        database = None
        try:
            if settings.db_user is not None or settings.db_verify_on_startup:
                database = Database(settings)
                application.state.database = database
                if settings.db_verify_on_startup:
                    def check_database() -> None:
                        with database.engine.connect() as connection:
                            verify_connection(connection)
                    await run_in_threadpool(check_database)
                    logger.info("database_connection_verified")
            logger.info("application_started", extra={"environment": settings.app_env})
            yield
        except (SQLAlchemyError, DatabaseConfigurationError):
            logger.error("database_initialization_failed")
            raise RuntimeError("Database initialization failed.") from None
        finally:
            if database is not None:
                await run_in_threadpool(database.dispose)
            application.state.database = None
            logger.info("application_stopped")

    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug and settings.app_env in {"development", "test"},
        lifespan=lifespan,
        openapi_tags=[
            {"name": "Health", "description": "Public service liveness"},
            {"name": "Patients", "description": "Local development only"},
            {"name": "Laboratories", "description": "Local development only"},
            {"name": "Diagnostic Tests", "description": "Active common-price catalog"},
            {"name": "Catalog Administration", "description": "Local development only"},
            {"name": "Laboratory Pricing", "description": "Private; development only"},
        ],
        responses={
            status: {"model": ErrorResponse}
            for status in (400, 401, 403, 404, 405, 409, 422, 429, 500, 503)
        },
    )
    application.state.settings = settings
    application.state.database = None
    register_exception_handlers(application)
    application.include_router(
        create_api_router(
            include_patients=settings.app_env == "development",
            include_laboratories=settings.app_env == "development",
            include_catalog_management=settings.app_env == "development",
        ),
        prefix=settings.api_v1_prefix,
    )
    # Last added middleware runs first: correlation -> CORS -> error boundary.
    application.add_middleware(ErrorBoundaryMiddleware)
    application.add_middleware(
        ApiCORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Request-ID", "X-CSRF-Token"],
        expose_headers=["X-Request-ID"],
    )
    application.add_middleware(
        RequestLoggingMiddleware, application=application
    )
    return application


app = create_app()
