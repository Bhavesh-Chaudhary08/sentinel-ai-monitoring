"""CSV / PDF export of the interaction report (audited)."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func
from sqlmodel import Session, select

from app.core.deps import get_db, get_current_user
from app.core.enums import UserRole
from app.domain.audit.service import record_audit
from app.domain.analytics.exporters import to_csv, to_pdf
from app.api.v1.interactions import InteractionFilters, apply_filters, email_map, interaction_query, to_out
from app.models.interaction import CapturedInteraction
from app.models.user import User

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
