"""Capture endpoints — the extension's write path.

Gates enforced in order: valid JWT → active user → consent recorded →
enrolled device matches the payload's device_id. Only then does ingest run.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.core.deps import get_db, require_consent
from app.domain.activity.ingest import ingest_time_segments
from app.domain.capture.ingest import ingest_events, ingest_shadow_visits
from app.models.user import User
from app.schemas.activity import TimeSegmentsIn, TimeSegmentsOut
from app.schemas.capture import CaptureIn, CaptureOut, ShadowVisitIn, ShadowVisitOut

router = APIRouter(prefix="/capture", tags=["capture"])


def _assert_device(user: User, device_id: str | None) -> None:
    if device_id != user.device_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Device not enrolled for this account — re-confirm consent in the extension",
        )


@router.post("/interactions", response_model=CaptureOut)
def capture_interactions(
    payload: CaptureIn,
    user: User = Depends(require_consent),
    session: Session = Depends(get_db),
) -> CaptureOut:
    _assert_device(user, payload.device_id)
    outcome = ingest_events(session, user, payload.device_id, payload.events)
    return CaptureOut(
        accepted=len(outcome.created),
        rejected=outcome.rejected,
        interaction_ids=outcome.created,
    )


@router.post("/shadow-visits", response_model=ShadowVisitOut)
def capture_shadow_visits(
    payload: ShadowVisitIn,
    user: User = Depends(require_consent),
    session: Session = Depends(get_db),
) -> ShadowVisitOut:
    """First-seen access to an unrecognized, AI-looking domain.

    The response tells the extension which unknown domains may now register the
    generic capture adapter — a deliberate allowlist-driven design so we don't
    inject content scripts across the whole web.
    """
    _assert_device(user, payload.device_id)
    outcome = ingest_shadow_visits(session, user, payload.device_id, payload.events)
    return ShadowVisitOut(
        first_seen=outcome.first_seen,
        capture_enabled_for=outcome.capture_enabled_for,
        risk=outcome.risk,
    )


@router.post("/time-sessions", response_model=TimeSegmentsOut)
def capture_time_sessions(
    payload: TimeSegmentsIn,
    user: User = Depends(require_consent),
    session: Session = Depends(get_db),
) -> TimeSegmentsOut:
    """Closed browser-time segments from the extension's sessionizer.

    Durations and domain+path only — no keystrokes, no query strings. Same
    consent + device gates as every other capture path.
    """
    _assert_device(user, payload.device_id)
    outcome = ingest_time_segments(session, user, payload.device_id, payload.events)
    return TimeSegmentsOut(accepted=len(outcome.created), rejected=outcome.rejected)
