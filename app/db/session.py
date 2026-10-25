"""Lazy engine creation and request-scoped, explicitly committed sessions."""

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import URL, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.core.exceptions import ApplicationError


class DatabaseConfigurationError(ValueError):
    pass


def database_url(settings: Settings) -> URL:
    if settings.db_user is None or settings.db_password is None:
        raise DatabaseConfigurationError("Set DB_USER and DB_PASSWORD in .env.")
    # URL.create handles @, %, / and other characters without manual escaping.
    return URL.create(
        "mysql+pymysql", username=settings.db_user,
        password=settings.db_password.get_secret_value(),
        host=settings.db_host, port=settings.db_port, database=settings.db_name,
        query={"charset": "utf8mb4"},
    )


def build_engine(settings: Settings) -> Engine:
    options = {
        "pool_pre_ping": True,
        "pool_recycle": settings.db_pool_recycle,
        "echo": False,
        "hide_parameters": True,
        "connect_args": {
            "connect_timeout": settings.db_connect_timeout,
            "read_timeout": settings.db_connect_timeout,
            "write_timeout": settings.db_connect_timeout,
        },
    }
    if settings.db_use_null_pool:
        options["poolclass"] = NullPool
    else:
        options.update(
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout,
        )
    return create_engine(database_url(settings), **options)


class Database:
    def __init__(self, settings: Settings) -> None:
        self.engine = build_engine(settings)
        self.session_factory = sessionmaker(
            bind=self.engine, class_=Session,
            autoflush=False, expire_on_commit=False,
        )

    def dispose(self) -> None:
        self.engine.dispose()


def get_db(request: Request) -> Iterator[Session]:
    database: Database | None = request.app.state.database
    if database is None:
        raise ApplicationError(
            "DATABASE_UNAVAILABLE", "Database service is unavailable.", 503
        )
    session = database.session_factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        # Closing rolls back any uncommitted work; commits belong to services.
        session.close()
