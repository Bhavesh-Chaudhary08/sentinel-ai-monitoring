"""Admin alert endpoints (list, filter, status transitions)."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlmodel import Session, select

from app.core.deps import get_db, require_admin
from app.core.enums import AlertSeverity, AlertStatus
from app.core.time import utcnow
from app.domain.audit.service import record_audit
from app.models.alert import Alert
from app.models.user import User
from app.schemas.alert import AlertOut, AlertStatusPatch
from app.schemas.common import Page

router = APIRouter(prefix="/alerts", tags=["alerts"])


@dataclass
class AlertFilters:
    page: int = 1
    page_size: int = 25
    status: AlertStatus | None = None
    severity: AlertSeverity | None = None
    from_: datetime | None = None


def alert_query(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    status: AlertStatus | None = Query(None),
    severity: AlertSeverity | None = Query(None),
    from_: datetime | None = Query(None, alias="from"),
) -> AlertFilters:
    return AlertFilters(page=page, page_size=page_size, status=status,
                        severity=severity, from_=from_)


def _to_out(alert: Alert, email: str | None) -> AlertOut:
    data = alert.model_dump()
    data["user_email"] = email
    return AlertOut.model_validate(data)


@router.get("", response_model=Page[AlertOut])
def list_alerts(
    filters: AlertFilters = Depends(alert_query),
    _: User = Depends(require_admin),
    session: Session = Depends(get_db),
) -> Page[AlertOut]:
    criteria = []
    if filters.status is not None:
        criteria.append(Alert.status == filters.status)
    if filters.severity is not None:
        criteria.append(Alert.severity == filters.severity)
    if filters.from_ is not None:
        criteria.append(Alert.created_at >= filters.from_)

    total = session.exec(select(func.count()).select_from(Alert).where(*criteria)).one()
    rows = session.exec(
        select(Alert)
        .where(*criteria)
        .order_by(Alert.created_at.desc())
        .offset((filters.page - 1) * filters.page_size)
        .limit(filters.page_size)
    ).all()

    user_ids = {row.user_id for row in rows}
    emails: dict[UUID, str] = {}
    if user_ids:
        pairs = session.exec(select(User.id, User.email).where(User.id.in_(user_ids))).all()
        emails = dict(pairs)

    return Page[AlertOut](
        items=[_to_out(r, emails.get(r.user_id)) for r in rows],
        total=int(total),
        page=filters.page,
        page_size=filters.page_size,
    )


@router.post("/{alert_id}/status", response_model=AlertOut)
def set_alert_status(
    alert_id: UUID,
    payload: AlertStatusPatch,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_db),
) -> AlertOut:
    alert = session.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")

    previous = alert.status
    alert.status = payload.status
    now = utcnow()
    if payload.status == AlertStatus.acknowledged:
        alert.acknowledged_by = admin.id
        alert.acknowledged_at = now
    elif payload.status in (AlertStatus.resolved, AlertStatus.false_positive):
        alert.resolved_at = now

    session.add(alert)
    record_audit(
        session, admin.id, "alert.status",
        target_type="alert", target_id=alert.id,
        detail={"from": previous.value, "to": alert.status.value},
    )
    session.commit()
    session.refresh(alert)

    owner = session.get(User, alert.user_id)
    return _to_out(alert, owner.email if owner else None)
