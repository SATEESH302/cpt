"""Session tests use only a separate in-memory SQLite database."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import Depends, Request
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import Column, Integer, MetaData, Table, create_engine, select
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.db.session import (
    DatabaseConfigurationError, build_engine, database_url, get_db,
)


def test_database_url_handles_password_characters() -> None:
    settings = Settings(
        _env_file=None, db_user="test-user",
        db_password=SecretStr("unit-test@password/%?#"),
    )
    url = database_url(settings)
    assert url.password == "unit-test@password/%?#"
    assert url.drivername == "mysql+pymysql"
    assert url.database == "diagnostic_platform"
    assert "unit-test@password" not in str(url)
    assert "unit-test@password" not in repr(settings)


def test_database_credentials_required_only_when_used() -> None:
    with pytest.raises(DatabaseConfigurationError):
        build_engine(Settings(_env_file=None))


@pytest.mark.parametrize("overrides", [
    {"db_port": 0}, {"db_port": 65536}, {"db_pool_size": 0},
    {"db_max_overflow": -1}, {"db_connect_timeout": 0},
    {"db_pool_timeout": 0}, {"db_pool_recycle": 0},
])
def test_invalid_database_config(overrides: dict) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **overrides)


def test_engine_is_lazy_and_supports_null_pool() -> None:
    engine = build_engine(Settings(
        _env_file=None, db_user="unused", db_password=SecretStr("unused"),
        db_use_null_pool=True,
    ))
    try:
        assert isinstance(engine.pool, NullPool)
        assert engine.echo is False
        assert engine.hide_parameters is True
        assert engine.pool._pre_ping is True
    finally:
        engine.dispose()


@pytest.fixture
def session_probe():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    table = Table("unit_test_probe", metadata, Column("id", Integer, primary_key=True))
    metadata.create_all(engine)
    sessions = []

    class TrackedSession(Session):
        was_closed = False
        rollback_called = False

        def close(self) -> None:
            self.was_closed = True
            super().close()

        def rollback(self) -> None:
            self.rollback_called = True
            super().rollback()

    factory = sessionmaker(bind=engine, class_=TrackedSession)

    def tracked_factory():
        session = factory()
        sessions.append(session)
        return session

    request = Request({
        "type": "http", "app": SimpleNamespace(
            state=SimpleNamespace(database=SimpleNamespace(
                session_factory=tracked_factory
            ))
        ),
    })
    yield request, table, engine, sessions
    engine.dispose()


def test_session_success_closes_without_implicit_commit(session_probe) -> None:
    request, table, engine, sessions = session_probe
    dependency = get_db(request)
    session = next(dependency)
    session.execute(table.insert().values(id=1))
    with pytest.raises(StopIteration):
        next(dependency)
    assert sessions[0].was_closed
    with engine.connect() as connection:
        assert connection.execute(select(table)).all() == []


def test_session_exception_rolls_back_and_closes(session_probe) -> None:
    request, table, engine, sessions = session_probe
    dependency = get_db(request)
    session = next(dependency)
    session.execute(table.insert().values(id=1))
    with pytest.raises(ValueError, match="test error"):
        dependency.throw(ValueError("test error"))
    assert sessions[0].rollback_called
    assert sessions[0].was_closed
    with engine.connect() as connection:
        assert connection.execute(select(table)).all() == []


def test_explicit_commit_persists_only_unit_test_data(session_probe) -> None:
    request, table, engine, _ = session_probe
    dependency = get_db(request)
    session = next(dependency)
    session.execute(table.insert().values(id=1))
    session.commit()
    dependency.close()
    with engine.connect() as connection:
        assert connection.execute(select(table)).all() == [(1,)]


@pytest.mark.parametrize("exception,status,code", [
    (IntegrityError("sensitive SQL", {}, Exception("private")),
     409, "DATABASE_CONFLICT"),
    (OperationalError("sensitive SQL", {}, Exception("private")),
     503, "DATABASE_UNAVAILABLE"),
    (SQLAlchemyError("private"), 500, "DATABASE_ERROR"),
])
def test_database_error_response(application, exception, status, code) -> None:
    @application.get("/_test/database-error")
    def database_error():
        raise exception

    with TestClient(application) as client:
        response = client.get("/_test/database-error")
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert response.json()["request_id"] == response.headers["x-request-id"]
    assert "private" not in response.text
    assert "sensitive SQL" not in response.text


def test_get_db_unconfigured_is_503(application) -> None:
    @application.get("/_test/session")
    def needs_db(session: Session = Depends(get_db)) -> dict:
        return {}

    with TestClient(application) as client:
        response = client.get("/_test/session")
        assert response.status_code == 503
        assert client.get("/api/v1/health").status_code == 200


def test_database_lifecycle_disposes_engine(monkeypatch) -> None:
    import app.main as main

    database = Mock()
    monkeypatch.setattr(main, "Database", Mock(return_value=database))
    application = main.create_app(Settings(
        _env_file=None, db_user="unused", db_password=SecretStr("unused"),
        db_verify_on_startup=False,
    ))
    with TestClient(application):
        assert application.state.database is database
        database.engine.connect.assert_not_called()
    database.dispose.assert_called_once()
    assert application.state.database is None


def test_startup_failure_disposes_and_sanitizes(monkeypatch) -> None:
    import app.main as main

    database = Mock()
    database.engine.connect.side_effect = OperationalError(
        "private SQL", {}, Exception("private password")
    )
    monkeypatch.setattr(main, "Database", Mock(return_value=database))
    application = main.create_app(Settings(
        _env_file=None, db_user="unused", db_password=SecretStr("unused"),
        db_verify_on_startup=True,
    ))
    with pytest.raises(RuntimeError, match="Database initialization failed") as exc:
        with TestClient(application):
            pass
    assert "private" not in str(exc.value)
    database.dispose.assert_called_once()
