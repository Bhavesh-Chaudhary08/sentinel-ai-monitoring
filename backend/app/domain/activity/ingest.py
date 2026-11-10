"""Ingest: extension time segments → TimeSegment rows.

Same idempotent shape as capture.ingest (dedupe on (user_id, client_event_id)),
with server-side sanity clamps so a buggy or hostile client can't write
nonsense durations or future-dated history.
"""

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from uuid import UUID, uuid4

from sqlmodel import Session, select

from app.core.config import settings
from app.core.time import utcnow
from app.domain.capture.shadow import is_valid_domain, normalize_domain
from app.models.activity import TimeSegment
from app.schemas.activity import TimeSegmentIn
from app.schemas.capture import RejectedEvent

logger = logging.getLogger("aidlp.activity.ingest")

# A single segment can't span more than this (laptop lid closed overnight with
# the SW suspended would otherwise upload an absurd "session").
MAX_SEGMENT_SECONDS = 12 * 3600
# Allowance for extension-clock skew; anything further in the future is bogus.
MAX_FUTURE_SKEW = timedelta(minutes=10)


@dataclass
class ActivityIngestResult:
    created: list[UUID] = field(default_factory=list)
    rejected: list[RejectedEvent] = field(default_factory=list)


def _known_event_ids(session: Session, user_id: UUID, event_ids: list[str]) -> set[str]:
    if not event_ids:
        return set()
    rows = session.exec(
        select(TimeSegment.client_event_id).where(
            TimeSegment.user_id == user_id,
            TimeSegment.client_event_id.in_(event_ids),
        )
    ).all()
    return set(rows)


def ingest_time_segments(
    session: Session,
    user,
    device_id: str | None,
    events: list[TimeSegmentIn],
) -> ActivityIngestResult:
    result = ActivityIngestResult()
    seen = _known_event_ids(session, user.id, [e.client_event_id for e in events])
    now = utcnow()
    purge_after = now + timedelta(days=settings.retention_days_time)

    for ev in events:
        if ev.client_event_id in seen:
            continue  # extension retry → idempotent success

        if ev.ended_at < ev.started_at:
            result.rejected.append(
                RejectedEvent(client_event_id=ev.client_event_id, reason="ended before it started")
            )
            continue
        if ev.started_at > now + MAX_FUTURE_SKEW or ev.ended_at > now + MAX_FUTURE_SKEW:
            result.rejected.append(
                RejectedEvent(client_event_id=ev.client_event_id, reason="timestamp in the future")
            )
            continue

        duration = min((ev.ended_at - ev.started_at).total_seconds(), MAX_SEGMENT_SECONDS)
        # Clamp the counters into the wall clock: active first, idle fills the
        # remainder — a client can over-report but never past the duration.
        active = min(ev.active_seconds, int(duration))
        idle = min(ev.idle_seconds, max(0, int(duration) - active))
        audible = min(ev.audible_seconds, int(duration))
        if active + idle == 0:
            result.rejected.append(
                RejectedEvent(client_event_id=ev.client_event_id, reason="no recorded time")
            )
            continue

        domain = None
        page_path = None
        if ev.domain:
            domain = normalize_domain(ev.domain)
            if not is_valid_domain(domain):
                result.rejected.append(
                    RejectedEvent(client_event_id=ev.client_event_id, reason="invalid domain")
                )
                continue
            # Query/fragment are stripped client-side; strip again server-side
            # so a modified extension can't smuggle search queries in.
            page_path = (ev.page_path or "").split("?")[0].split("#")[0][:512] or None

        row = TimeSegment(
            user_id=user.id,
            device_id=device_id,
            client_event_id=ev.client_event_id,
            kind=ev.kind,
            domain=domain,
            page_path=page_path,
            active_seconds=active,
            idle_seconds=idle,
            audible_seconds=audible,
            started_at=ev.started_at,
            ended_at=ev.started_at + timedelta(seconds=duration),
            purge_after=purge_after,
        )
        session.add(row)
        result.created.append(row.id)
        seen.add(ev.client_event_id)

    session.commit()
    return result
