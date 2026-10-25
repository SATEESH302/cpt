"""MySQL DDL contract checks need no live server or patient records."""

import re
from pathlib import Path

from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

from app import models
from app.db.base import Base


def test_all_sql_script_tables_have_mappings() -> None:
    script = (Path(__file__).resolve().parents[1] / "sql_scripts").read_text()
    names = set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", script))
    assert set(Base.metadata.tables) == names | {"patient_credentials", "auth_sessions", "auth_rate_limits"}
    assert len(Base.registry.mappers) == 13
    for table in [Base.metadata.tables[name] for name in names]:
        ddl = str(CreateTable(table).compile(dialect=mysql.dialect()))
        assert "AUTO_INCREMENT" in ddl


def test_timestamp_and_boolean_defaults_match_mysql() -> None:
    patient = Base.metadata.tables["patients"]
    assert patient.c.created_at.nullable is True
    assert "ON UPDATE CURRENT_TIMESTAMP" in str(patient.c.updated_at.server_default.arg)
    is_active = Base.metadata.tables["diagnostic_tests"].c.is_active
    assert str(is_active.server_default.arg) == "1"
    assert Base.metadata.tables["diagnostic_tests"].c.is_active.nullable is True


def test_foreign_keys_uniqueness_and_enum_values() -> None:
    assert sum(len(table.foreign_keys) for table in Base.metadata.tables.values()) == 15
    assert models.Booking.__table__.c.lab_id.nullable
    assert not models.Booking.__table__.c.patient_id.nullable
    assert models.Booking.__table__.c.collection_type.type.enums == ["HOME", "LAB"]
    unique_names = {
        constraint.name for table in Base.metadata.tables.values()
        for constraint in table.constraints if isinstance(constraint, UniqueConstraint)
    }
    assert {"uq_lab_test", "uq_booking_test"} <= unique_names
