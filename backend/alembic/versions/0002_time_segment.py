"""Browser time segments: time_segment table.

Notes:
- Enum column uses the native Postgres ENUM type (timesegmentkind), matching
  how SQLModel maps (str, Enum) fields — same convention as 0001_initial.
- Index names follow the ORM's ix_<table>_<column> default so the model and
  migration agree.

Revision ID: 0002_time_segment
Revises: 0001_initial
Create Date: 2026-10-15

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.core.enums import TimeSegmentKind

# revision identifiers, used by Alembic.
revision: str = "0002_time_segment"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "time_segment",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("device_id", sa.String(length=64), nullable=True),
        sa.Column("client_event_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.Enum(TimeSegmentKind, native_enum=True), nullable=False, index=True),
        sa.Column("domain", sa.String(length=255), nullable=True, index=True),
        sa.Column("page_path", sa.String(length=512), nullable=True),
        sa.Column("active_seconds", sa.Integer(), nullable=False),
        sa.Column("idle_seconds", sa.Integer(), nullable=False),
        sa.Column("audible_seconds", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False, index=True),
        sa.Column("ended_at", sa.DateTime(), nullable=False),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.Column("purge_after", sa.DateTime(), nullable=True, index=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "client_event_id", name="uq_time_segment_user_event"),
    )
    op.create_index(
        "ix_time_segment_user_started", "time_segment", ["user_id", "started_at"]
    )


def downgrade() -> None:
    op.drop_table("time_segment")
    # drop_table removes indexes/constraints but not the Postgres enum type.
    # IF EXISTS keeps this safe even if SQLAlchemy derived a different name.
    op.execute(f"DROP TYPE IF EXISTS {TimeSegmentKind.__name__.lower()}")
