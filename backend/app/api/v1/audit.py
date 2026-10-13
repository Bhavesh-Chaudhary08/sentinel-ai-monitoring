"""Admin-only audit log listing."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlmodel import Session, select

from app.core.deps import get_db, require_admin
from app.models.audit import AuditLog
from app.models.user import User
from app.schemas.audit import AuditOut
from app.schemas.common import Page

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=Page[AuditOut])
def list_audit(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    action: str | None = Query(None, max_length=64),
    actor_id: UUID | None = None,
    from_: datetime | None = Query(None, alias="from"),
    _: User = Depends(require_admin),
    session: Session = Depends(get_db),
) -> Page[AuditOut]:
    criteria = []
    if action:
        criteria.append(AuditLog.action == action)
    if actor_id:
        criteria.append(AuditLog.actor_id == actor_id)
    if from_:
        criteria.append(AuditLog.created_at >= from_)

    total = session.exec(select(func.count()).select_from(AuditLog).where(*criteria)).one()
    rows = session.exec(
        select(AuditLog)
        .where(*criteria)
        .order_by(AuditLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    actor_ids = {row.actor_id for row in rows}
    emails: dict[UUID, str] = {}
    if actor_ids:
        pairs = session.exec(select(User.id, User.email).where(User.id.in_(actor_ids))).all()
        emails = dict(pairs)

    items = []
    for row in rows:
        data = row.model_dump()
        data["actor_email"] = emails.get(row.actor_id)
        items.append(AuditOut.model_validate(data))

    return Page[AuditOut](items=items, total=int(total), page=page, page_size=page_size)
