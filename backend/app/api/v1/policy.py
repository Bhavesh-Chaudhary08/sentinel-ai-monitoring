"""Policy endpoints: synchronous pre-flight check + admin rule CRUD."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlmodel import Session, select

from app.core.deps import get_current_user, get_db, require_admin
from app.core.time import utcnow
from app.domain.classification.pipeline import classify_prompt
from app.domain.policy.engine import evaluate_policy
from app.models.policy import PolicyRule
from app.models.user import User
from app.schemas.capture import PolicyCheckIn, PolicyCheckOut
from app.schemas.common import Msg, Page
from app.schemas.policy import RuleCreate, RuleOut, RuleUpdate

router = APIRouter(prefix="/policy", tags=["policy"])


@router.post("/check", response_model=PolicyCheckOut)
def policy_check(
    payload: PolicyCheckIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> PolicyCheckOut:
    """Synchronous DLP pre-flight — called by the extension BEFORE sending.

    Uses the quick tier (regex + lexical similarity): no spaCy/torch on the
    request path, so it stays fast enough for an inline send-blocking hook.
    The full Presidio/embedding classification still runs async afterwards.
    """
    result = classify_prompt(payload.prompt_text, quick=True)
    evaluation = evaluate_policy(
        session,
        category=result.category,
        score=result.score,
        user=user,
        ai_tool=payload.ai_tool,
        domain=payload.domain,
    )
    return PolicyCheckOut(
        action=evaluation.action,
        message=evaluation.message,
        category=result.category,
        confidence=result.score,
        flagged=result.flagged,
        rule_id=evaluation.rule.id if evaluation.rule else None,
        rule_name=evaluation.rule.name if evaluation.rule else None,
    )


@router.get("/rules", response_model=Page[RuleOut])
def list_rules(
    active: bool | None = None,
    page: int = 1,
    page_size: int = 50,
    _: User = Depends(require_admin),
    session: Session = Depends(get_db),
) -> Page[RuleOut]:
    criteria = [PolicyRule.is_active == active] if active is not None else []
    total = session.exec(
        select(func.count()).select_from(PolicyRule).where(*criteria)
    ).one()
    rows = session.exec(
        select(PolicyRule)
        .where(*criteria)
        .order_by(PolicyRule.priority.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page[RuleOut](
        items=[RuleOut.model_validate(r) for r in rows],
        total=int(total),
        page=page,
        page_size=page_size,
    )


@router.post("/rules", response_model=RuleOut, status_code=status.HTTP_201_CREATED)
def create_rule(
    payload: RuleCreate,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_db),
) -> RuleOut:
    exists = session.exec(select(PolicyRule).where(PolicyRule.name == payload.name)).first()
    if exists is not None:
        raise HTTPException(status_code=409, detail="A rule with this name already exists")
    rule = PolicyRule(**payload.model_dump(), created_by=admin.id)
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return RuleOut.model_validate(rule)


@router.patch("/rules/{rule_id}", response_model=RuleOut)
def update_rule(
    rule_id: UUID,
    payload: RuleUpdate,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_db),
) -> RuleOut:
    rule = session.get(PolicyRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(rule, field, value)
    rule.updated_at = utcnow()
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return RuleOut.model_validate(rule)


@router.delete("/rules/{rule_id}", response_model=Msg)
def deactivate_rule(
    rule_id: UUID,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_db),
) -> Msg:
    """Rules are deactivated, never hard-deleted: historical interactions
    keep their FK references."""
    rule = session.get(PolicyRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    rule.is_active = False
    rule.updated_at = utcnow()
    session.add(rule)
    session.commit()
    return Msg(detail=f"Rule '{rule.name}' deactivated")
