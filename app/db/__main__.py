"""python -m app.db verify|baseline: explicit maintenance commands."""

import argparse
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.util.exc import CommandError
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.core.logging import configure_logging, logger
from app.db.session import Database, DatabaseConfigurationError
from app.db.verification import SchemaMismatchError, verify_schema

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASELINE_REVISION = "0001_existing_schema"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["verify", "baseline"])
    args = parser.parse_args()
    database = None
    try:
        settings = get_settings()
        configure_logging(settings.log_level)
        database = Database(settings)
        with database.engine.connect() as connection:
            verify_schema(connection)
            if args.operation == "baseline":
                config = Config(str(PROJECT_ROOT / "alembic.ini"))
                config.attributes["connection"] = connection
                # env.py independently repeats verification before any stamp.
                command.stamp(config, BASELINE_REVISION)
                connection.commit()
                print(f"Alembic baseline recorded: {BASELINE_REVISION}")
            else:
                print(
                    "MySQL connection verified; "
                    "all 10 ORM tables match and are accessible."
                )
        return 0
    except SchemaMismatchError as exc:
        print("Schema verification failed; no baseline was recorded:")
        for difference in exc.differences:
            print(f"- {difference}")
        return 1
    except DatabaseConfigurationError as exc:
        print(str(exc))
        return 1
    except (SQLAlchemyError, ValidationError, CommandError):
        # Driver errors can contain credentials and SQL parameters.
        logger.error("database_verification_failed")
        print(
            "Database operation failed. "
            "Check configuration, MySQL service, and permissions."
        )
        return 1
    finally:
        if database is not None:
            database.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
