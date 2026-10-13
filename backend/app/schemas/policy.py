"""Policy rule schemas (create / patch / read)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import AiTool, PolicyAction, RiskCategory, UserRole


class RuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    priority: int = Field(default=100, ge=0, le=1000)
    # matchers — None means "apply to everything on this axis"
    category: RiskCategory | None = None
    ai_tool: AiTool | None = None
    domain: str | None = Field(default=None, max_length=255)
    min_confidence: float = Field(default=0.70, ge=0.0, le=1.0)
    role_scope: UserRole | None = None
    department_scope: str | None = Field(default=None, max_length=120)
    # enforcement
    action: PolicyAction = PolicyAction.log_only
    warn_message: str | None = Field(default=None, max_length=500)
    block_message: str | None = Field(default=None, max_length=500)
    is_active: bool = True


class RuleUpdate(BaseModel):
    """Partial update: omitted fields stay unchanged (FastAPI PATCH semantics)."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    priority: int | None = Field(default=None, ge=0, le=1000)
    category: RiskCategory | None = None
    ai_tool: AiTool | None = None
    domain: str | None = Field(default=None, max_length=255)
    min_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    role_scope: UserRole | None = None
    department_scope: str | None = Field(default=None, max_length=120)
    action: PolicyAction | None = None
    warn_message: str | None = Field(default=None, max_length=500)
    block_message: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None


class RuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None = None
    is_active: bool
    priority: int
    category: RiskCategory | None = None
    ai_tool: AiTool | None = None
    domain: str | None = None
    min_confidence: float
    role_scope: UserRole | None = None
    department_scope: str | None = None
    action: PolicyAction
    warn_message: str | None = None
    block_message: str | None = None
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime
