"""Browser-time read endpoints (dashboard).

Access rules mirror the rest of the API: employees may only ever read their
own activity; admins may read anyone's. Nothing here returns content — only
durations and domain+path names.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.core.deps import get_current_user, get_db, require_admin
from app.core.enums import UserRole
from app.domain.activity import queries
from app.models.user import User
from app.schemas.activity import (
    ActivityDailyOut,
    DaySummary,
    DigestOut,
    FocusOut,
    SegmentOut,
    TeamDayRow,
    TopDomainRow,
    TrendsOut,
)

# ISO week label: 2026-W01 … 2026-W53 (a 52-week year's W53 is caught by
# parse_week and turned into a 422 — see activity_digest).

router = APIRouter(prefix="/activity", tags=["activity"])


def _target_user(session: Session, user: User, user_id: UUID | None) -> User:
    """Employees are pinned to themselves; admins may select any user."""
    if user.role == UserRole.admin:
        if user_id is None:
            return user
        target = session.get(User, user_id)
        if target is None or not target.is_active:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return target
    if user_id is not None and user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Employees may only view their own activity",
        )
    return user


@router.get("/daily", response_model=list[DaySummary])
def activity_daily(
    days: int = Query(default=7, ge=1, le=queries.MAX_DAYS),
    user_id: UUID | None = Query(default=None),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[DaySummary]:
    target = _target_user(session, user, user_id)
    return queries.daily_for_user(session, target.id, days)


@router.get("/me", response_model=ActivityDailyOut)
def activity_me(
    days: int = Query(default=7, ge=1, le=queries.MAX_DAYS),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> ActivityDailyOut:
    """Everything the employee self-view needs in one call."""
    return ActivityDailyOut(
        window_days=days,
        user_id=user.id,
        user_email=user.email,
        user_name=user.full_name,
        days=queries.daily_for_user(session, user.id, days),
    )


@router.get("/team-daily", response_model=list[TeamDayRow], dependencies=[Depends(require_admin)])
def activity_team_daily(
    days: int = Query(default=7, ge=1, le=queries.MAX_DAYS),
    session: Session = Depends(get_db),
) -> list[TeamDayRow]:
    return queries.team_daily(session, days)


@router.get("/top-domains", response_model=list[TopDomainRow])
def activity_top_domains(
    days: int = Query(default=7, ge=1, le=queries.MAX_DAYS),
    user_id: UUID | None = Query(default=None),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[TopDomainRow]:
    target = _target_user(session, user, user_id)
    return queries.top_domains(session, target.id, days)


@router.get("/segments", response_model=list[SegmentOut])
def activity_segments(
    days: int = Query(default=1, ge=1, le=queries.MAX_DAYS),
    user_id: UUID | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[SegmentOut]:
    target = _target_user(session, user, user_id)
    return queries.recent_segments(session, target.id, days, limit)


@router.get("/focus", response_model=FocusOut)
def activity_focus(
    days: int = Query(default=7, ge=1, le=queries.MAX_DAYS),
    user_id: UUID | None = Query(default=None),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> FocusOut:
    """One honest composite focus number per day for a single person.

    Same scoping as everywhere else: employees are pinned to themselves; an
    admin may pass user_id to view one person's days. There is deliberately
    no team aggregate or ranking here — the score is gamified for the
    employee, not usable against them (see FocusOut).
    """
    target = _target_user(session, user, user_id)
    return queries.focus_scores(session, target.id, days)


@router.get("/digest", response_model=DigestOut)
def activity_digest(
    week: str | None = Query(default=None, pattern=r"^\d{4}-W\d{2}$"),
    user_id: UUID | None = Query(default=None),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> DigestOut:
    """One person's week on a page (Phase 4): totals + focus rollup + AI counts.

    Same scoping as every other endpoint here — employees are pinned to
    themselves; an admin may pass user_id to read one person's week. No
    week (or an unparsable one → 422) means the current ISO week. Per-person
    only by design: a team digest would turn the focus score into a ranking.
    """
    target = _target_user(session, user, user_id)
    if week is None:
        monday = queries.current_week_monday()
    else:
        try:
            monday = queries.parse_week(week)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{week} is not a valid ISO week (expected e.g. 2026-W43)",
            )
    return queries.weekly_digest(session, target.id, monday)


@router.get("/trends", response_model=TrendsOut)
def activity_trends(
    days: int = Query(default=7, ge=1, le=queries.MAX_DAYS),
    user_id: UUID | None = Query(default=None),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> TrendsOut:
    """Current window vs the previous window of equal length (Phase 2).

    Admins with no user_id get the team scope; admin + user_id drills into one
    person; employees are always pinned to themselves (same rules as every
    other endpoint here — see _target_user).
    """
    target = _target_user(session, user, user_id)
    scope_user = None if (user.role == UserRole.admin and user_id is None) else target.id
    return queries.trends(session, scope_user, days)
