"""Adopt the ten existing tables from sql_scripts without executing DDL.

This revision is intentionally empty. env.py verifies the live schema before
initial adoption. It does not bootstrap an empty database or drop existing data.
"""

revision = "0001_existing_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
