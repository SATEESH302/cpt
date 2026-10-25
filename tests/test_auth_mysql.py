"""Opt-in auth integration in a new temporary MySQL schema; no real data writes."""

import os
import re
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core.config import Settings
from app.db.base import Base
from app.db.session import build_engine
from app.db.verification import verify_schema

pytestmark = [pytest.mark.mysql, pytest.mark.skipif(os.getenv("RUN_AUTH_MYSQL_TESTS") != "1", reason="Opt-in isolated MySQL auth test.")]


def test_auth_mysql_migration_and_full_lifecycle():
    from app.main import create_app
    settings = Settings(_env_file=os.environ["AUTH_MYSQL_ENV_FILE"], debug=False)
    admin = build_engine(settings)
    schema = "cpt_auth_test_" + uuid4().hex
    assert re.fullmatch(r"cpt_auth_test_[a-f0-9]{32}", schema)
    engine = None
    created = False
    try:
        with admin.connect() as connection:
            connection.execute(text(f"CREATE DATABASE `{schema}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"))
        created = True
        engine = create_engine(admin.url.set(database=schema), hide_parameters=True)
        auth_tables = {"patient_credentials", "auth_sessions", "auth_rate_limits"}
        Base.metadata.create_all(engine, tables=[table for table in Base.metadata.sorted_tables if table.name not in auth_tables])
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        with engine.connect() as connection:
            config.attributes["connection"] = connection
            command.stamp(config, "0001_existing_schema")
            command.upgrade(config, "head")
            connection.commit()
            verify_schema(connection)
        application = create_app(settings.model_copy(update={"db_name": schema, "app_env": "development"}))
        headers = {"Origin": "http://localhost:5173"}
        with TestClient(application) as client:
            def post(path, payload):
                csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
                return client.post("/api/v1/auth/" + path, json=payload, headers={**headers, "X-CSRF-Token": csrf})
            response = post("register", {"full_name": "Isolated MySQL Test", "phone": "9876543210", "email": "mysql-auth@example.com", "password": "isolated mysql test password", "terms_accepted": True})
            assert response.status_code == 201, response.status_code
            response = post("login", {"identifier": "mysql-auth@example.com", "password": "isolated mysql test password"})
            assert response.status_code == 200, response.status_code
            profile = client.get("/api/v1/auth/me")
            assert profile.status_code == 200
            assert profile.json()["user"]["full_name"] == "Isolated MySQL Test"
            token = client.cookies.get("dtp_session")
            response = client.post("/api/v1/auth/logout", json={}, headers={**headers, "X-CSRF-Token": profile.json()["csrf_token"]})
            assert response.status_code == 200
            client.cookies.set("dtp_session", token)
            assert client.get("/api/v1/auth/me").status_code == 401
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            assert re.fullmatch(r"cpt_auth_test_[a-f0-9]{32}", schema)
            with admin.connect() as connection:
                connection.execute(text(f"DROP DATABASE `{schema}`"))
        admin.dispose()
