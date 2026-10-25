"""Opt-in read-only integration tests; never insert, migrate or stamp."""

import os

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.base import Base
from app.db.session import Database
from app.db.verification import verify_schema

pytestmark = [
    pytest.mark.mysql,
    pytest.mark.skipif(
        os.getenv("RUN_MYSQL_TESTS") != "1",
        reason="Set RUN_MYSQL_TESTS=1 to enable read-only local MySQL tests.",
    ),
]


@pytest.fixture
def local_database():
    database = Database(Settings(debug=False))
    yield database
    database.dispose()


def test_live_mysql_schema(local_database) -> None:
    with local_database.engine.connect() as connection:
        verify_schema(connection)


def test_live_orm_access_without_reading_records(local_database) -> None:
    with Session(local_database.engine) as session:
        for mapper in Base.registry.mappers:
            assert session.execute(select(mapper.class_).limit(0)).all() == []


def test_fastapi_connects_to_mysql_on_startup() -> None:
    from fastapi.testclient import TestClient
    from app.main import create_app

    settings = Settings(debug=False, db_verify_on_startup=True)
    with TestClient(create_app(settings)) as client:
        assert client.app.state.database is not None
        assert client.get("/api/v1/health").status_code == 200
