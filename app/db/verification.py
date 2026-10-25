"""Read-only schema verification before adopting an existing MySQL database."""

import re

from sqlalchemy import UniqueConstraint, inspect, select, text
from sqlalchemy.dialects import mysql
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from app import models  # noqa: F401 -- populate the complete registry
from app.db.base import Base


class SchemaMismatchError(RuntimeError):
    def __init__(self, differences: list[str]) -> None:
        self.differences = differences
        super().__init__("Database schema differs from ORM metadata.")


def normalize_default(value: str | None) -> str | None:
    if value is None or value.upper() == "NULL":
        return None
    value = re.sub(r"current_timestamp\(\)", "CURRENT_TIMESTAMP", value,
                   flags=re.IGNORECASE)
    if "current_timestamp" in value.lower():
        return " ".join(value.upper().split())
    if re.fullmatch(r"'?-?\d+(?:\.\d+)?'?", value):
        return value.strip("'")
    return value


def type_signature(column_type: object) -> object:
    if isinstance(column_type, mysql.ENUM):
        return ("ENUM", tuple(column_type.enums))
    compiled = str(column_type.compile(dialect=mysql.dialect())).upper()
    compiled = compiled.replace("NUMERIC(", "DECIMAL(")
    if compiled in {"BOOL", "BOOLEAN", "TINYINT(1)"}:
        return "BOOLEAN"
    # Display widths are deprecated in MySQL 8 and do not change integer storage.
    return re.sub(r"\b(BIGINT|INTEGER|INT)\(\d+\)", r"\1", compiled)


def _action(value: str | None) -> str:
    return "RESTRICT" if value in (None, "NO ACTION", "RESTRICT") else value


def schema_differences(connection: Connection, *, baseline: bool = False) -> list[str]:
    if connection.dialect.name != "mysql":
        raise ValueError("Live schema verification requires MySQL.")
    inspector = inspect(connection)
    differences: list[str] = []
    expected_tables = set(Base.metadata.tables)
    if baseline:
        expected_tables -= {"patient_credentials", "auth_sessions", "auth_rate_limits"}
    actual_tables = set(inspector.get_table_names()) - {"alembic_version"}
    for name in sorted(expected_tables - actual_tables):
        differences.append(f"{name}: missing table")
    for name in sorted(actual_tables - expected_tables):
        differences.append(f"{name}: unexpected table")
    for name in sorted(expected_tables & actual_tables):
        table = Base.metadata.tables[name]
        actual_columns = {col["name"]: col for col in inspector.get_columns(name)}
        if set(actual_columns) != set(table.columns.keys()):
            differences.append(f"{name}: column names differ")
        for column in table.columns:
            actual = actual_columns.get(column.name)
            if actual is None:
                continue
            prefix = f"{name}.{column.name}"
            if type_signature(column.type) != type_signature(actual["type"]):
                differences.append(f"{prefix}: type differs")
            if column.nullable != actual["nullable"]:
                differences.append(f"{prefix}: nullability differs")
            default = (
                str(column.server_default.arg)
                if column.server_default is not None else None
            )
            if normalize_default(default) != normalize_default(actual.get("default")):
                differences.append(f"{prefix}: server default/ON UPDATE differs")
            expected_auto = column is table.autoincrement_column
            if expected_auto != bool(actual.get("autoincrement", False)):
                differences.append(f"{prefix}: auto increment differs")
            if actual.get("computed") or actual.get("identity"):
                differences.append(f"{prefix}: unexpected generated column")
        pk = inspector.get_pk_constraint(name)["constrained_columns"]
        if pk != [column.name for column in table.primary_key.columns]:
            differences.append(f"{name}: primary key differs")
        expected_unique = {
            tuple(column.name for column in constraint.columns): constraint.name
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        }
        actual_unique = {
            tuple(item["column_names"]): item["name"]
            for item in inspector.get_unique_constraints(name)
        }
        if set(expected_unique) != set(actual_unique) or any(
            key in actual_unique and value is not None and value != actual_unique[key]
            for key, value in expected_unique.items()
        ):
            differences.append(f"{name}: unique constraints differ")
        expected_fks = {
            (tuple(col.name for col in fk.columns),
             tuple(element.column.name for element in fk.elements),
             fk.referred_table.name, _action(fk.ondelete), _action(fk.onupdate))
            for fk in table.foreign_key_constraints
        }
        actual_fk_items = inspector.get_foreign_keys(name)
        actual_fks = {
            (tuple(item["constrained_columns"]), tuple(item["referred_columns"]),
             item["referred_table"], _action(item.get("options", {}).get("ondelete")),
             _action(item.get("options", {}).get("onupdate")))
            for item in actual_fk_items
        }
        if expected_fks != actual_fks or any(
            item.get("referred_schema") not in (None, connection.engine.url.database)
            for item in actual_fk_items
        ):
            differences.append(f"{name}: foreign keys/actions differ")
        # MySQL creates supporting FK indexes automatically. Do not model those
        # as additional application indexes, but reject unrelated indexes.
        for index in inspector.get_indexes(name):
            columns = tuple(index["column_names"])
            supports_fk = any(
                columns == tuple(fk["constrained_columns"])[:len(columns)]
                for fk in actual_fk_items
            )
            if not index["unique"] and not supports_fk:
                differences.append(f"{name}: unmodeled index {index['name']}")
        if inspector.get_check_constraints(name):
            differences.append(f"{name}: unmodeled check constraints")
        options = inspector.get_table_options(name)
        for key in ("mysql_engine", "mysql_collate"):
            if options.get(key) != table.dialect_options["mysql"].get(key[6:]):
                differences.append(f"{name}: {key} differs")
    return differences


def verify_connection(connection: Connection) -> None:
    if connection.scalar(text("SELECT 1")) != 1:
        raise RuntimeError("Database connection verification failed.")


def verify_schema(connection: Connection, *, baseline: bool = False) -> None:
    verify_connection(connection)
    differences = schema_differences(connection, baseline=baseline)
    if differences:
        raise SchemaMismatchError(differences)
    # Execute ORM SELECTs with LIMIT 0: validate access without reading records.
    with Session(bind=connection) as session:
        for mapper in sorted(
            Base.registry.mappers, key=lambda item: item.local_table.name
        ):
            if baseline and mapper.local_table.name in {"patient_credentials", "auth_sessions", "auth_rate_limits"}:
                continue
            session.execute(select(mapper.class_).limit(0)).all()
