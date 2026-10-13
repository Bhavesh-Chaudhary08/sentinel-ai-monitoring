"""Captured AI interaction + per-finding classification details.

Storage contract depends on settings.storage_mode:
- "full" (default): prompt/response text is stored verbatim for EVERY
  interaction, flagged or not; content_stored=True and purge_after is set at
  ingest (flagged rows later get the longer flagged retention window).
- "minimal": prompt_hash and redacted_preview are ALWAYS present for prompt
  events; prompt_text/response_text exist ONLY when is_flagged (then
  content_stored=True and purge_after schedules their removal), otherwise
  they are never persisted.

In BOTH modes every prompt is classified — every row ends up with a
risky/safe verdict, category, score and per-detection findings.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Index, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.core.enums import (
    AiTool,
    ClassificationStatus,
    PolicyAction,
    RiskCategory,
    ShadowRisk,
)
from app.core.time import utcnow


class CapturedInteraction(SQLModel, table=True):
    __tablename__ = "captured_interaction"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    device_id: Optional[str] = Field(default=None, max_length=64)
    # Idempotency key from the extension so retries never double-count.
    client_event_id: str = Field(max_length=64)

    # --- what was captured ---
    ai_tool: AiTool = Field(default=AiTool.other, index=True)
    domain: str = Field(index=True, max_length=255)
    page_path: Optional[str] = Field(default=None, max_length=512)
    is_known_platform: bool = Field(default=True, index=True)
    # Shadow-AI discovery: first time this user hits an unrecognized AI domain.
    is_first_seen: bool = Field(default=False)
    shadow_risk: Optional[ShadowRisk] = Field(default=None)

    # full mode: always stored · minimal mode: flagged-only (see module docstring)
    prompt_text: Optional[str] = Field(default=None)
    response_text: Optional[str] = Field(default=None)
    prompt_hash: Optional[str] = Field(default=None, index=True, max_length=64)  # sha256, always
    redacted_preview: Optional[str] = Field(default=None, max_length=1000)  # PII-scrubbed

    # --- classification ---
    classification_status: ClassificationStatus = Field(
        default=ClassificationStatus.pending, index=True
    )
    risk_category: RiskCategory = Field(default=RiskCategory.none, index=True)
    risk_score: float = Field(default=0.0)
    classifier_version: Optional[str] = Field(default=None, max_length=64)
    is_flagged: bool = Field(default=False, index=True)

    # --- policy outcome ---
    policy_rule_id: Optional[UUID] = Field(default=None, foreign_key="policy_rule.id")
    applied_action: Optional[PolicyAction] = Field(default=None)  # server decision
    was_blocked: bool = Field(default=False)  # client actually suppressed the send

    # --- retention ---
    content_stored: bool = Field(default=False)
    purge_after: Optional[datetime] = Field(default=None, index=True)

    # occurred_at comes from the extension clock; received_at from the server.
    occurred_at: datetime = Field(index=True)
    received_at: datetime = Field(default_factory=utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "client_event_id", name="uq_interaction_user_event"),
        Index("ix_interaction_user_occurred", "user_id", "occurred_at"),
        Index("ix_interaction_category_occurred", "risk_category", "occurred_at"),
        Index("ix_interaction_domain_known", "domain", "is_known_platform"),
    )


class ClassificationFinding(SQLModel, table=True):
    """Why an interaction was flagged: one row per detection.

    `label` is a Presidio entity (EMAIL_ADDRESS, CREDIT_CARD, ...) for PII, or a
    semantic category (source_code, financial, ...) for similarity hits.
    """

    __tablename__ = "classification_finding"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    interaction_id: UUID = Field(foreign_key="captured_interaction.id", index=True)
    engine: str = Field(max_length=16)  # regex | presidio | semantic | lexical
    label: str = Field(max_length=64)
    score: float = Field(default=0.0)
    start: Optional[int] = Field(default=None)
    end: Optional[int] = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow)

    __table_args__ = (Index("ix_finding_interaction_score", "interaction_id", "score"),)
