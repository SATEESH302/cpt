"""Adopt an existing schema only after verification; never run create_all."""

from alembic import context
from alembic.util.exc import CommandError

from app import models  # noqa: F401
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import build_engine
from app.db.verification import SchemaMismatchError, verify_schema

config = context.config
target_metadata = Base.metadata
BASELINE_REVISION = "0001_existing_schema"


def run(connection) -> None:
    context.configure(
        connection=connection, target_metadata=target_metadata,
        compare_type=True, compare_server_default=True,
    )
    migration_context = context.get_context()
    current = migration_context.get_current_revision()
    command_name = getattr(
        getattr(config, "cmd_opts", None), "cmd", (None,)
    )[0]
    is_stamp = getattr(command_name, "__name__", "") == "stamp"
    # Programmatic callers must not stamp an arbitrary revision without checking.
    if current is None or is_stamp or config.attributes.get("verify_baseline"):
        try:
            verify_schema(connection, baseline=current in (None, BASELINE_REVISION))
        except SchemaMismatchError as exc:
            raise CommandError(
                "Schema mismatch: " + "; ".join(exc.differences)
            ) from None
    if current not in (None, BASELINE_REVISION, "0002_patient_auth") and config.attributes.get("connection"):
        raise CommandError("Refusing to overwrite an existing migration history.")
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    raise CommandError("Offline migrations cannot verify an existing schema.")
else:
    external_connection = config.attributes.get("connection")
    if external_connection is not None:
        run(external_connection)
    else:
        engine = build_engine(get_settings())
        try:
            with engine.connect() as connection:
                run(connection)
                connection.commit()
        finally:
            engine.dispose()
