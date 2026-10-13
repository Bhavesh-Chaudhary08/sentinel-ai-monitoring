"""Interaction read schemas."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.core.enums import (
    AiTool,
    ClassificationStatus,
    PolicyAction,
    RiskCategory,
    ShadowRisk,
)


class ClassificationFindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    engine: str
    label: str
    score: float
    start: Optional[int] = None
    end: Optional[int] = None


class InteractionOut(BaseModel):
    id: UUID
    user_id: UUID
    user_email: Optional[str] = None  # joined in for admin views
    device_id: Optional[str] = None
    ai_tool: AiTool
    domain: str
    page_path: Optional[str] = None
    is_known_platform: bool
    is_first_seen: bool
    shadow_risk: Optional[ShadowRisk] = None
    prompt_text: Optional[str] = None  # present only when content_stored
    response_text: Optional[str] = None
    prompt_hash: Optional[str] = None
    redacted_preview: Optional[str] = None
    classification_status: ClassificationStatus
    risk_category: RiskCategory
    risk_score: float
    classifier_version: Optional[str] = None
    is_flagged: bool
    policy_rule_id: Optional[UUID] = None
    applied_action: Optional[PolicyAction] = None
    was_blocked: bool
    content_stored: bool
    purge_after: Optional[datetime] = None
    occurred_at: datetime
    received_at: datetime


class InteractionDetailOut(InteractionOut):
    findings: list[ClassificationFindingOut] = []
