"""Audit log read schema."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class AuditOut(BaseModel):
    id: UUID
    actor_id: UUID
    actor_email: Optional[str] = None
    action: str
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    detail: Optional[dict] = None
    created_at: datetime
