"""Browser time segments: where focused browser time went, and when it didn't.

Captured client-side by the extension's sessionizer. Durations arrive as
active/idle second counts — never keystrokes, never URLs with query strings
(the extension strips query + fragment before upload).

kind semantics (TimeSegmentKind):
- "tab":  browser window focused on this domain/path.
          active_seconds = OS input recently (user at the keyboard),
          idle_seconds   = no input for the idle threshold while still focused.
- "away": browser unfocused OR machine idle/locked.
          active_seconds = input recent while another app had focus
                           ("other activity" — e.g. Excel, Slack desktop),
          idle_seconds   = no input at all (true away-from-keyboard time).

active_seconds + idle_seconds never exceed the segment's wall-clock duration;
audible_seconds (media playing in the tab) overlaps active time by design.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Index, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.core.enums import TimeSegmentKind
from app.core.time import utcnow


class TimeSegment(SQLModel, table=True):
    __tablename__ = "time_segment"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    device_id: Optional[str] = Field(default=None, max_length=64)
    # Idempotency key from the extension so retries never double-count.
    client_event_id: str = Field(max_length=64)

    kind: TimeSegmentKind = Field(default=TimeSegmentKind.tab, index=True)
    # kind=tab only; page_path is origin+path — query/fragment are stripped
    # client-side so search queries and tokens never reach the backend.
    domain: Optional[str] = Field(default=None, index=True, max_length=255)
    page_path: Optional[str] = Field(default=None, max_length=512)

    active_seconds: int = Field(default=0)
    idle_seconds: int = Field(default=0)
    audible_seconds: int = Field(default=0)

    started_at: datetime = Field(index=True)
    ended_at: datetime
    received_at: datetime = Field(default_factory=utcnow)
    # Hard-delete after the retention window (swept by workers.tasks).
    purge_after: Optional[datetime] = Field(default=None, index=True)

    __table_args__ = (
        UniqueConstraint("user_id", "client_event_id", name="uq_time_segment_user_event"),
        Index("ix_time_segment_user_started", "user_id", "started_at"),
    )
