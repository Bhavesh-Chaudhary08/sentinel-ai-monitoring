"""Browser time-tracking schemas (extension → backend ingest, dashboard reads)."""

from datetime import date, datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.core.enums import TimeSegmentKind
from app.schemas.analytics import KeyCount
from app.schemas.capture import RejectedEvent


class TimeSegmentIn(BaseModel):
    """One closed segment: a focused tab URL, or an away/unfocused span.

    Durations are counts of seconds, never content — see models/activity.py
    for kind semantics.
    """

    client_event_id: str = Field(min_length=8, max_length=64)
    kind: TimeSegmentKind = TimeSegmentKind.tab
    domain: str | None = Field(default=None, max_length=255)
    page_path: str | None = Field(default=None, max_length=512)
    active_seconds: int = Field(default=0, ge=0)
    idle_seconds: int = Field(default=0, ge=0)
    audible_seconds: int = Field(default=0, ge=0)
    started_at: datetime
    ended_at: datetime

    @field_validator("started_at", "ended_at")
    @classmethod
    def _naive_utc(cls, value: datetime) -> datetime:
        """Client clocks send Z-suffixed ISO strings (Date.toISOString()); the
        project stores naive UTC everywhere (app/core/time.py), so normalize
        at the boundary — aware datetimes crash naive comparisons at ingest.
        """
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value


class TimeSegmentsIn(BaseModel):
    device_id: str | None = Field(default=None, max_length=64)
    events: list[TimeSegmentIn] = Field(min_length=1, max_length=200)


class TimeSegmentsOut(BaseModel):
    accepted: int
    rejected: list[RejectedEvent] = []


# ------------------------------ dashboard reads -----------------------------


class DaySummary(BaseModel):
    date: date
    browser_active_seconds: int = 0  # kind=tab, OS input recent
    browser_idle_seconds: int = 0    # kind=tab, no input (still on the page)
    other_seconds: int = 0           # kind=away, OS input recent (another app)
    away_seconds: int = 0            # kind=away, no input at all
    audible_seconds: int = 0         # media playing in the focused tab


class ActivityDailyOut(BaseModel):
    window_days: int
    user_id: UUID
    user_email: str
    user_name: str
    days: list[DaySummary]


class TeamDayRow(BaseModel):
    user_id: UUID
    user_email: str
    user_name: str
    date: date
    browser_active_seconds: int = 0
    browser_idle_seconds: int = 0
    other_seconds: int = 0
    away_seconds: int = 0
    audible_seconds: int = 0


class TopDomainRow(BaseModel):
    domain: str
    seconds: int  # active + idle while focused on this domain


class SegmentOut(BaseModel):
    id: UUID
    kind: TimeSegmentKind
    domain: str | None
    page_path: str | None
    active_seconds: int
    idle_seconds: int
    audible_seconds: int
    started_at: datetime
    ended_at: datetime


# ------------------------- trends (period comparison) -----------------------

class PeriodTotals(BaseModel):
    """One comparison window, summed across the scope (team or one user)."""

    browser_active_seconds: int = 0
    browser_idle_seconds: int = 0
    other_seconds: int = 0
    away_seconds: int = 0
    audible_seconds: int = 0
    segments: int = 0


class TrendDeltas(BaseModel):
    """Percent change of current vs previous window, per bucket.

    None means "no baseline" (previous window was 0) — a percentage against
    zero would be infinite, so the UI shows "new" instead of a fake 0% or ∞.
    """

    browser_active_seconds: float | None = None
    browser_idle_seconds: float | None = None
    other_seconds: float | None = None
    away_seconds: float | None = None


class FocusMetrics(BaseModel):
    """Depth-of-work metrics derived from the *sequence* of focused segments.

    Framing (product rule): these describe browser behaviour only — a focus
    block is a run of focused time on one domain, not a judgement about the
    person. Definitions live in domain/activity/queries.py (focus_blocks()).
    """

    focus_blocks: int = 0            # contiguous runs on a single domain
    context_switches: int = 0        # domain changes with no break in between
    switches_per_day: float = 0.0
    longest_focus_seconds: int = 0   # longest single-domain run
    avg_focus_block_seconds: int = 0


class UserTrendRow(BaseModel):
    user_id: UUID
    user_email: str
    user_name: str
    current: PeriodTotals
    previous: PeriodTotals
    # percent change of browser_active_seconds (None = no previous baseline)
    delta_pct: float | None = None


class TrendsOut(BaseModel):
    """Current window vs the immediately preceding one, same length."""

    window_days: int
    scope: Literal["team", "user"]
    user_id: UUID | None = None
    current: PeriodTotals
    previous: PeriodTotals
    deltas: TrendDeltas
    focus: FocusMetrics
    daily: list[DaySummary]  # current window only, ascending
    users: list[UserTrendRow]  # team scope: everyone; user scope: just them


# ---------------------------- focus score (Phase 3) -------------------------

class FocusComponents(BaseModel):
    """The three weighted parts of a day's focus score, each 0–100.

    Always shipped alongside the composite so the number is never a black
    box: share = focused tab vs all keyboard-tracked time; continuity =
    average focus block vs the 25-minute target; calm = context switches vs
    the 12/day baseline.
    """

    share_pct: int
    continuity_pct: int
    calm_pct: int


class FocusDayRow(BaseModel):
    """One day's honest focus number for one person.

    Framing (product rule): this describes browser focus only, not work
    quality. focus_score is None when the day has no focused-tab time —
    nothing to score, shown as "—", never a fake 0. Away time appears in the
    payload but counts against no component: breaks neither help nor hurt.
    """

    date: date
    focus_score: int | None = None  # 0–100, None = no focused-tab time
    components: FocusComponents | None = None
    focus_seconds: int = 0          # active time inside focus blocks
    browser_active_seconds: int = 0
    browser_idle_seconds: int = 0
    other_seconds: int = 0
    away_seconds: int = 0
    focus_blocks: int = 0
    context_switches: int = 0
    longest_focus_seconds: int = 0


class FocusOut(BaseModel):
    """Per-day focus scores for ONE person (employee: themselves; admin: the
    user they selected). Deliberately no team aggregate or ranking — the
    score is gamified for the employee, not turned into a leaderboard."""

    window_days: int
    user_id: UUID
    user_email: str
    user_name: str
    average_score: int | None = None  # mean over days WITH focused-tab time
    days: list[FocusDayRow]  # ascending by date


# --------------------------- weekly digest (Phase 4) ------------------------

class DigestFocus(BaseModel):
    """The week's focus picture for ONE person — the daily score rolled up.

    average_score follows the FocusOut rule: the mean over days WITH
    focused-tab time (untracked days excluded, never averaged in as zeros),
    so an unscored week reports None and the UI shows "—".
    """

    average_score: int | None = None
    days_scored: int = 0
    best_day: date | None = None
    best_day_score: int | None = None
    focus_seconds: int = 0
    focus_blocks: int = 0
    context_switches: int = 0
    longest_focus_seconds: int = 0


class DigestAiUsage(BaseModel):
    """The same person's week of captured AI interactions — counts and tool
    mix only. The digest never carries prompt text or previews: it is a
    summary, not a second copy of the evidence."""

    interactions: int = 0
    flagged: int = 0
    blocked: int = 0
    alerts: int = 0
    by_tool: list[KeyCount] = []


class DigestOut(BaseModel):
    """One person's week on a page (ISO week, Monday-start, UTC days).

    Per-person by design, like FocusOut: a team-wide digest would turn the
    focus score into the leaderboard the product spec deliberately avoids.
    Employees get their own week; an admin may pass user_id for one person.
    """

    week: str            # ISO week label, e.g. "2026-W43"
    week_start: date     # Monday (UTC)
    week_end: date       # Sunday (UTC)
    user_id: UUID
    user_email: str
    user_name: str
    totals: PeriodTotals
    tracked_days: int = 0  # days with any segment at all
    focus: DigestFocus
    top_domains: list[TopDomainRow] = []
    ai_usage: DigestAiUsage
    days: list[FocusDayRow] = []  # the week's scored days, ascending
