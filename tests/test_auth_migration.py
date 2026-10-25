"""Apply the additive revision on a private database, preserving legacy rows."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_auth_upgrade_preserves_existing_patients_and_refuses_destructive_downgrade(monkeypatch):
    monkeypatch.setattr("app.db.verification.verify_schema", lambda *args, **kwargs: None)
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        connection.execute(text("CREATE TABLE patients (patient_id INTEGER PRIMARY KEY, full_name VARCHAR(150))"))
        connection.execute(text("INSERT INTO patients VALUES (1, 'Existing Patient')"))
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        config.attributes["connection"] = connection
        command.stamp(config, "0001_existing_schema")
        command.upgrade(config, "head")
        assert set(inspect(connection).get_table_names()) == {"patients", "patient_credentials", "auth_sessions", "auth_rate_limits", "alembic_version"}
        assert connection.scalar(text("SELECT full_name FROM patients WHERE patient_id=1")) == "Existing Patient"
        # Prevent env.py's verification from attempting MySQL introspection on SQLite.
        with pytest.raises(RuntimeError, match="backup"):
            command.downgrade(config, "0001_existing_schema")
    engine.dispose()
