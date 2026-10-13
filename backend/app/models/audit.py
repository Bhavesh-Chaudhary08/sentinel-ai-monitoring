"""Audit log: every privileged/administrative action, append-only."""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.core.time import utcnow


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_log"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    actor_id: UUID = Field(foreign_key="user.id", index=True)
    action: str = Field(index=True, max_length=64)  # e.g. rule.create, export.csv
    target_type: Optional[str] = Field(default=None, max_length=64)
    target_id: Optional[str] = Field(default=None, max_length=64)
    # JSON column (SQLModel has no native dict mapping) — redacted metadata only.
    detail: Optional[dict] = Field(
        default=None, sa_column=Column("detail", JSON, nullable=True)
    )
    created_at: datetime = Field(default_factory=utcnow, index=True)
