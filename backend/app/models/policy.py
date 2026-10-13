"""Policy rules: per-category enforcement with role/department overrides."""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Index
from sqlmodel import Field, SQLModel

from app.core.enums import AiTool, PolicyAction, RiskCategory, UserRole
from app.core.time import utcnow


class PolicyRule(SQLModel, table=True):
    __tablename__ = "policy_rule"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True, unique=True, max_length=120)
    description: Optional[str] = Field(default=None, max_length=500)
    is_active: bool = Field(default=True, index=True)
    # Higher priority wins when several rules match; ties broken by specificity
    # (role/department-scoped rules beat global ones) then by min_confidence.
    priority: int = Field(default=100)

    # --- matchers (None = "match everything" on that axis) ---
    category: Optional[RiskCategory] = Field(default=None, index=True)
    ai_tool: Optional[AiTool] = Field(default=None)
    domain: Optional[str] = Field(default=None, max_length=255)
    min_confidence: float = Field(default=0.70)

    # --- role-based override scoping: NULL applies to everyone ---
    role_scope: Optional[UserRole] = Field(default=None, index=True)
    department_scope: Optional[str] = Field(default=None, max_length=120)

    # --- enforcement ---
    action: PolicyAction = Field(default=PolicyAction.log_only, index=True)
    warn_message: Optional[str] = Field(default=None, max_length=500)
    block_message: Optional[str] = Field(default=None, max_length=500)

    created_by: Optional[UUID] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    __table_args__ = (Index("ix_policy_rule_active_priority", "is_active", "priority"),)
