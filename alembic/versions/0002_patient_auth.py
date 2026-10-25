"""Add patient credentials, opaque sessions, and shared rate-limit counters.

Existing patient records and all original tables are preserved.
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_patient_auth"
down_revision = "0001_existing_schema"
branch_labels = None
depends_on = None

OPTIONS = dict(mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_0900_ai_ci")


def upgrade():
    op.create_table(
        "patient_credentials",
        sa.Column("patient_id", sa.BigInteger(), sa.ForeignKey("patients.patient_id", ondelete="CASCADE"), primary_key=True, autoincrement=False),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("phone", sa.String(15), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("terms_accepted_at", sa.DateTime(), nullable=False), **OPTIONS,
    )
    op.create_table(
        "auth_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("patient_id", sa.BigInteger(), sa.ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False), **OPTIONS,
    )
    op.create_table(
        "auth_rate_limits",
        sa.Column("key_hash", sa.String(64), primary_key=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("resets_at", sa.DateTime(), nullable=False), **OPTIONS,
    )


def downgrade():
    # Refuse accidental account/session data loss; rollback needs an explicit plan.
    raise RuntimeError("Authentication downgrade requires an explicit backup and data-retention plan.")
