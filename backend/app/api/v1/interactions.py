"""Interaction search (admin) / self-view (employee) + shared filter builder."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, col, func, select

from app.core.deps import get_current_user, get_db
from app.core.enums import AiTool, RiskCategory, UserRole
from app.models.interaction import CapturedInteraction, ClassificationFinding
from app.models.user import User
from app.schemas.common import Page
from app.schemas.interaction import ClassificationFindingOut, InteractionDetailOut, InteractionOut

router = APIRouter(prefix="/interactions", tags=["interactions"])


@dataclass
class InteractionFilters:
    page: int = 1
    page_size: int = 25
    category: RiskCategory | None = None
    tool: AiTool | None = None
    flagged: bool | None = None
    known: bool | None = None
    shadow_only: bool | None = None
    domain: str | None = None
    q: str | None = None
    from_: datetime | None = None
    to: datetime | None = None
    user_id: UUID | None = None


def interaction_query(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    category: RiskCategory | None = Query(None),
    tool: AiTool | None = Query(None),
    flagged: bool | None = Query(None),
    known: bool | None = Query(None),
    shadow_only: bool | None = Query(None),
    domain: str | None = Query(None, max_length=255),
    q: str | None = Query(None, max_length=100, description="substring match on domain"),
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = Query(None),
    user_id: UUID | None = Query(None),
) -> InteractionFilters:
    return InteractionFilters(
        page=page, page_size=page_size, category=category, tool=tool, flagged=flagged,
        known=known, shadow_only=shadow_only, domain=domain, q=q, from_=from_, to=to,
        user_id=user_id,
    )


def apply_filters(filters: InteractionFilters, user: User) -> list[Any]:
    """RBAC first: employees can only ever see their own rows."""
    criteria: list[Any] = []
    if user.role != UserRole.admin:
        criteria.append(CapturedInteraction.user_id == user.id)
    elif filters.user_id is not None:
        criteria.append(CapturedInteraction.user_id == filters.user_id)

    if filters.category is not None:
        criteria.append(CapturedInteraction.risk_category == filters.category)
    if filters.tool is not None:
        criteria.append(CapturedInteraction.ai_tool == filters.tool)
    if filters.flagged is not None:
        criteria.append(CapturedInteraction.is_flagged == filters.flagged)
    if filters.known is not None:
        criteria.append(CapturedInteraction.is_known_platform == filters.known)
    if filters.shadow_only:
        criteria.append(CapturedInteraction.is_known_platform == False)  # noqa: E712
    if filters.domain:
        criteria.append(col(CapturedInteraction.domain).like(f"%{filters.domain.lower()}%"))
    if filters.q:
        criteria.append(col(CapturedInteraction.domain).like(f"%{filters.q.lower()}%"))
    if filters.from_ is not None:
        criteria.append(CapturedInteraction.occurred_at >= filters.from_)
    if filters.to is not None:
        criteria.append(CapturedInteraction.occurred_at <= filters.to)
    return criteria


def email_map(session: Session, rows: list[CapturedInteraction]) -> dict[UUID, str]:
    user_ids = {row.user_id for row in rows}
    if not user_ids:
        return {}
    pairs = session.exec(select(User.id, User.email).where(User.id.in_(user_ids))).all()
    return {uid: email for uid, email in pairs}


def to_out(row: CapturedInteraction, email: str | None = None) -> InteractionOut:
    data: dict[str, Any] = row.model_dump()
    data["user_email"] = email
    return InteractionOut.model_validate(data)


@router.get("", response_model=Page[InteractionOut])
def list_interactions(
    filters: InteractionFilters = Depends(interaction_query),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> Page[InteractionOut]:
    criteria = apply_filters(filters, user)
    total = session.exec(
        select(func.count()).select_from(CapturedInteraction).where(*criteria)
    ).one()
    rows = session.exec(
        select(CapturedInteraction)
        .where(*criteria)
        .order_by(CapturedInteraction.occurred_at.desc())
        .offset((filters.page - 1) * filters.page_size)
        .limit(filters.page_size)
    ).all()
    emails = email_map(session, rows)
    return Page[InteractionOut](
        items=[to_out(r, emails.get(r.user_id)) for r in rows],
        total=int(total),
        page=filters.page,
        page_size=filters.page_size,
    )


@router.get("/{interaction_id}", response_model=InteractionDetailOut)
def get_interaction(
    interaction_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> InteractionDetailOut:
    row = session.get(CapturedInteraction, interaction_id)
    # 404 (not 403) for foreign rows so IDs can't be probed for existence.
    if row is None or (row.user_id != user.id and user.role != UserRole.admin):
        raise HTTPException(status_code=404, detail="Interaction not found")
    findings = session.exec(
        select(ClassificationFinding)
        .where(ClassificationFinding.interaction_id == row.id)
        .order_by(ClassificationFinding.score.desc())
    ).all()
    data: dict[str, Any] = row.model_dump()
    data["user_email"] = user.email if row.user_id == user.id else None
    if user.role == UserRole.admin and row.user_id != user.id:
        owner = session.get(User, row.user_id)
        data["user_email"] = owner.email if owner else None
    data["findings"] = [ClassificationFindingOut.model_validate(f).model_dump() for f in findings]
    return InteractionDetailOut.model_validate(data)
