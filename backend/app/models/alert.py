"""Alerts raised for high-confidence policy violations."""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column, Index
from sqlmodel import Field, SQLModel

from app.core.enums import AlertSeverity, AlertStatus
from app.core.time import utcnow


class Alert(SQLModel, table=True):
    __tablename__ = "alert"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    interaction_id: UUID = Field(foreign_key="captured_interaction.id", index=True)
    rule_id: Optional[UUID] = Field(default=None, foreign_key="policy_rule.id")
    user_id: UUID = Field(foreign_key="user.id", index=True)  # who triggered it

    severity: AlertSeverity = Field(default=AlertSeverity.medium, index=True)
    status: AlertStatus = Field(default=AlertStatus.triggered, index=True)
    title: str = Field(max_length=200)
    # Summary is built from the redacted preview — raw prompt text never goes here.
    summary: str = Field(max_length=1000)
    # JSON column (SQLModel has no native dict mapping) — category, score, tool, domain.
    context: Optional[dict] = Field(
        default=None, sa_column=Column("context", JSON, nullable=True)
    )

    notified_at: Optional[datetime] = Field(default=None)
    acknowledged_by: Optional[UUID] = Field(default=None, foreign_key="user.id")
    acknowledged_at: Optional[datetime] = Field(default=None)
    resolved_at: Optional[datetime] = Field(default=None)

    created_at: datetime = Field(default_factory=utcnow, index=True)

    __table_args__ = (
        Index("ix_alert_status_severity_created", "status", "severity", "created_at"),
    )
