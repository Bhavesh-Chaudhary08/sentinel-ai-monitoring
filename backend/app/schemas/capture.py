"""Capture (extension → backend) and policy pre-flight schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.enums import AiTool, PolicyAction, RiskCategory, ShadowRisk


class CaptureEventIn(BaseModel):
    client_event_id: str = Field(min_length=8, max_length=64)  # idempotency key
    occurred_at: datetime
    ai_tool: AiTool = AiTool.other
    domain: str = Field(min_length=1, max_length=255)
    page_path: str | None = Field(default=None, max_length=512)
    is_known_platform: bool = True
    prompt_text: str | None = Field(default=None, max_length=20_000)
    response_text: str | None = Field(default=None, max_length=40_000)
    was_blocked: bool = False


class CaptureIn(BaseModel):
    device_id: str | None = Field(default=None, max_length=64)
    events: list[CaptureEventIn] = Field(min_length=1, max_length=50)


class RejectedEvent(BaseModel):
    client_event_id: str
    reason: str


class CaptureOut(BaseModel):
    accepted: int
    rejected: list[RejectedEvent] = []
    interaction_ids: list[UUID] = []


class ShadowVisitEvent(BaseModel):
    """A navigation to a NOT-known AI domain where the probe found chat-UI markers.

    Only domain + boolean markers leave the device here — never page content.
    """

    client_event_id: str = Field(min_length=8, max_length=64)
    occurred_at: datetime
    domain: str = Field(min_length=1, max_length=255)
    page_title: str | None = Field(default=None, max_length=120)
    markers: dict[str, bool] = {}


class ShadowVisitIn(BaseModel):
    device_id: str | None = Field(default=None, max_length=64)
    events: list[ShadowVisitEvent] = Field(min_length=1, max_length=20)


class ShadowVisitOut(BaseModel):
    # Domains first seen for this user (flagged as shadow AI) and domains the
    # backend told the extension it may now capture from (generic adapter).
    first_seen: list[str] = []
    capture_enabled_for: list[str] = []
    risk: ShadowRisk | None = None


class PolicyCheckIn(BaseModel):
    """Synchronous pre-flight: runs *before* the prompt is sent to the AI tool."""

    prompt_text: str = Field(min_length=1, max_length=20_000)
    ai_tool: AiTool = AiTool.other
    domain: str = Field(min_length=1, max_length=255)
    page_path: str | None = Field(default=None, max_length=512)


class PolicyCheckOut(BaseModel):
    action: PolicyAction
    message: str | None = None
    category: RiskCategory
    confidence: float
    flagged: bool
    rule_id: UUID | None = None
    rule_name: str | None = None
