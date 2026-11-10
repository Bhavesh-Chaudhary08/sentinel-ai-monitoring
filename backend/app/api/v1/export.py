"""CSV / PDF export of the interaction report (audited)."""

import csv
import io
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func
from sqlmodel import Session, select

from app.core.deps import get_db, get_current_user
from app.core.enums import UserRole
from app.domain.audit.service import record_audit
from app.domain.analytics.exporters import to_csv, to_pdf
from app.api.v1.activity import _target_user
from app.api.v1.interactions import InteractionFilters, apply_filters, email_map, interaction_query, to_out
from app.domain.activity import queries
from app.models.interaction import CapturedInteraction
from app.models.user import User
from app.schemas.activity import DigestOut

router = APIRouter(prefix="/export", tags=["export"])

EXPORT_MAX_ROWS = 10_000


@router.get("/interactions")
def export_interactions(
    format: str = Query("csv", pattern="^(csv|pdf)$"),
    filters: InteractionFilters = Depends(interaction_query),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> Response:
    """Employees can export their own data (transparency right); admins can
    export anything their filters select. Either way it lands in the audit log."""
    criteria = apply_filters(filters, user)
    total = session.exec(
        select(func.count()).select_from(CapturedInteraction).where(*criteria)
    ).one()
    if total > EXPORT_MAX_ROWS:
        raise HTTPException(
            status_code=422,
            detail=f"Filter matches {total} rows; narrow the date range (max {EXPORT_MAX_ROWS})",
        )
    rows = session.exec(
        select(CapturedInteraction)
        .where(*criteria)
        .order_by(CapturedInteraction.occurred_at.desc())
        .limit(EXPORT_MAX_ROWS)
    ).all()
    emails = email_map(session, rows)
    items = [to_out(r, emails.get(r.user_id)) for r in rows]

    record_audit(
        session, user.id, f"export.{format}",
        target_type="interaction",
        detail={"rows": len(items), "role": user.role.value},
    )
    session.commit()

    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    if format == "pdf":
        content = to_pdf(items, title="AI usage & DLP report")
        return Response(
            content=content,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="ai-usage-{stamp}.pdf"'},
        )
    return Response(
        content=to_csv(items),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="ai-usage-{stamp}.csv"'},
    )


def _digest_csv(digest: DigestOut) -> str:
    """The digest as a flat section/name/value CSV — stable for spreadsheets
    and small enough to read raw. Counts and durations only; never prompt
    text, matching the digest payload itself.
    """
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["section", "name", "value"])

    focus = digest.focus
    rows: list[tuple[str, str, object]] = [
        ("meta", "week", digest.week),
        ("meta", "week_start", digest.week_start.isoformat()),
        ("meta", "week_end", digest.week_end.isoformat()),
        ("meta", "user", digest.user_email),
        ("time", "browser_active_seconds", digest.totals.browser_active_seconds),
        ("time", "browser_idle_seconds", digest.totals.browser_idle_seconds),
        ("time", "other_seconds", digest.totals.other_seconds),
        ("time", "away_seconds", digest.totals.away_seconds),
        ("time", "tracked_days", digest.tracked_days),
        ("focus", "average_score", "" if focus.average_score is None else focus.average_score),
        ("focus", "days_scored", focus.days_scored),
        ("focus", "best_day", focus.best_day.isoformat() if focus.best_day else ""),
        ("focus", "best_day_score", "" if focus.best_day_score is None else focus.best_day_score),
        ("focus", "focus_seconds", focus.focus_seconds),
        ("focus", "focus_blocks", focus.focus_blocks),
        ("focus", "context_switches", focus.context_switches),
        ("focus", "longest_focus_seconds", focus.longest_focus_seconds),
        ("ai", "interactions", digest.ai_usage.interactions),
        ("ai", "flagged", digest.ai_usage.flagged),
        ("ai", "blocked", digest.ai_usage.blocked),
        ("ai", "alerts", digest.ai_usage.alerts),
    ]
    rows.extend(
        ("ai_tool", tool.key, tool.count) for tool in digest.ai_usage.by_tool
    )
    rows.extend(("top_domain", d.domain, d.seconds) for d in digest.top_domains)
    for day in digest.days:
        rows.append(("day", f"{day.date} score", "" if day.focus_score is None else day.focus_score))
        rows.append(("day", f"{day.date} browser_active_seconds", day.browser_active_seconds))
        rows.append(("day", f"{day.date} focus_seconds", day.focus_seconds))
    writer.writerows(rows)
    return buf.getvalue()


@router.get("/digest")
def export_digest(
    week: str | None = Query(default=None, pattern=r"^\d{4}-W\d{2}$"),
    user_id: UUID | None = Query(default=None),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> Response:
    """One person's weekly digest as CSV (audited like every other export).

    Employees can export their own week (transparency right); an admin may
    export one person's week — same scoping as GET /activity/digest. The file
    carries counts and durations only, never prompt text.
    """
    target = _target_user(session, user, user_id)
    if week is None:
        monday = queries.current_week_monday()
    else:
        try:
            monday = queries.parse_week(week)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"{week} is not a valid ISO week (expected e.g. 2026-W43)",
            )
    digest = queries.weekly_digest(session, target.id, monday)

    record_audit(
        session, user.id, "export.csv",
        target_type="digest",
        detail={"week": digest.week, "user": digest.user_email, "role": user.role.value},
    )
    session.commit()

    local_part = digest.user_email.split("@")[0] or "user"
    return Response(
        content=_digest_csv(digest),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition":
                f'attachment; filename="digest-{digest.week}-{local_part}.csv"'
        },
    )
