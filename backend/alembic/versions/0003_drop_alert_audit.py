"""Drop the alert and audit_log tables.

Both features (the alerting pipeline and the audit log) were removed from the
product, so their tables and native enum types go with them. A fresh database
never creates them (see 0001_initial); this revision cleans up databases that
were migrated before the removal, and is a no-op where they are already gone.

Revision ID: 0003_drop_alert_audit
Revises: 0002_time_segment
Create Date: 2026-11-18

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_drop_alert_audit"
down_revision: Union[str, None] = "0002_time_segment"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IF EXISTS: a database migrated from scratch never had these tables.
    op.execute("DROP TABLE IF EXISTS alert")
    op.execute("DROP TABLE IF EXISTS audit_log")
    # Native enum types are Postgres-only, and they are not dropped with
    # their table (SQLite has neither, so the test suite skips them).
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS alertseverity")
        op.execute("DROP TYPE IF EXISTS alertstatus")


def downgrade() -> None:
    """Not reversible: the tables belong to features that no longer exist.

    Recreating the schema alone would not restore the code that wrote to it,
    so this fails loudly rather than pretending to restore a half-working state.
    """
    raise NotImplementedError(
        "alert and audit_log were removed from the product; restore from a backup"
    )
