"""Analytics + shadow-AI discovery schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.core.enums import ShadowRisk


class DayBucket(BaseModel):
    date: str  # YYYY-MM-DD
    total: int = 0
    flagged: int = 0
    blocked: int = 0


class KeyCount(BaseModel):
    key: str
    label: Optional[str] = None
    count: int


class UsageTotals(BaseModel):
    interactions: int = 0
    flagged: int = 0
    blocked: int = 0
    alerts: int = 0
    shadow_domains: int = 0
    active_users: int = 0


class UsageOut(BaseModel):
    days: int
    totals: UsageTotals
    by_day: list[DayBucket] = []
    by_tool: list[KeyCount] = []
    by_category: list[KeyCount] = []
    top_users: list[KeyCount] = []


class ShadowDomainOut(BaseModel):
    domain: str
    first_seen: datetime
    last_seen: datetime
    interactions: int
    users: int
    risk: Optional[ShadowRisk] = None
    is_known_platform: bool
