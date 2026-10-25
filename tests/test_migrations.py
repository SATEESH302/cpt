from pathlib import Path
from unittest.mock import Mock

import pytest
from alembic import command
from alembic.config import Config
from alembic.util.exc import CommandError
from sqlalchemy import create_engine, inspect
from sqlalchemy.dialects import mysql

from app.db.verification import (
    SchemaMismatchError, normalize_default, schema_differences, type_signature,
)

ROOT = Path(__file__).resolve().parents[1]


def test_baseline_refuses_drift_before_creating_version_table(monkeypatch) -> None:
    import app.db.verification as verification

    def mismatch(connection, **kwargs) -> None:
        raise SchemaMismatchError(["patients: column names differ"])

    monkeypatch.setattr(verification, "verify_schema", mismatch)
    engine = create_engine("sqlite://")
    try:
        with engine.connect() as connection:
            config = Config(str(ROOT / "alembic.ini"))
            config.attributes["connection"] = connection
            with pytest.raises(CommandError, match="Schema mismatch"):
                command.stamp(config, "0001_existing_schema")
            assert inspect(connection).get_table_names() == []
    finally:
        engine.dispose()


def test_verified_baseline_only_records_revision_in_unit_database(monkeypatch) -> None:
    import app.db.verification as verification

    verified = Mock()
    monkeypatch.setattr(verification, "verify_schema", verified)
    engine = create_engine("sqlite://")
    try:
        with engine.connect() as connection:
            config = Config(str(ROOT / "alembic.ini"))
            config.attributes["connection"] = connection
            command.stamp(config, "0001_existing_schema")
            assert inspect(connection).get_table_names() == ["alembic_version"]
            verified.assert_called_once_with(connection, baseline=True)
    finally:
        engine.dispose()


def test_offline_stamp_is_refused() -> None:
    with pytest.raises(CommandError, match="Offline migrations"):
        command.stamp(
            Config(str(ROOT / "alembic.ini")), "0001_existing_schema", sql=True
        )


@pytest.mark.parametrize("left,right", [
    ("CURRENT_TIMESTAMP", "current_timestamp()"),
    ("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
     "current_timestamp() ON UPDATE current_timestamp()"),
    ("1", "'1'"), (None, "NULL"),
])
def test_mysql_default_normalization(left, right) -> None:
    assert normalize_default(left) == normalize_default(right)


def test_enum_order_and_default_values_are_significant() -> None:
    assert type_signature(mysql.ENUM("PENDING", "ACTIVE")) != type_signature(
        mysql.ENUM("ACTIVE", "PENDING")
    )
    assert normalize_default("'PENDING'") != normalize_default("'ACTIVE'")


def test_missing_tables_are_not_silently_adopted(monkeypatch) -> None:
    connection = Mock()
    connection.dialect.name = "mysql"
    inspector = Mock()
    inspector.get_table_names.return_value = ["unrelated_table"]
    monkeypatch.setattr("app.db.verification.inspect", lambda _: inspector)
    differences = schema_differences(connection)
    assert len(differences) == 14
    assert "patients: missing table" in differences
    assert "unrelated_table: unexpected table" in differences
