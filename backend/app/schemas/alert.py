"""Alert schemas."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from app.core.enums import AlertSeverity, AlertStatus


class AlertOut(BaseModel):
    id: UUID
    interaction_id: UUID
    rule_id: Optional[UUID] = None
    user_id: UUID
    user_email: Optional[str] = None
    severity: AlertSeverity
    status: AlertStatus
    title: str
    summary: str
    context: Optional[dict] = None
    notified_at: Optional[datetime] = None
    acknowledged_by: Optional[UUID] = None
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime


class AlertStatusPatch(BaseModel):
    status: AlertStatus
