"""Analytics endpoints: usage aggregates + shadow-AI discovery report."""

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.core.deps import get_current_user, get_db, require_admin
from app.core.enums import UserRole
from app.domain.analytics.queries import shadow_ai_domains, usage_summary
from app.models.user import User
from app.schemas.analytics import ShadowDomainOut, UsageOut

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/usage", response_model=UsageOut)
def usage(
    days: int = Query(30, ge=1, le=365),
    user_id: str | None = Query(None, description="admin only; ignored for employees"),
    current: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> UsageOut:
    """Admins see the org; employees automatically see only themselves
    (the transparency self-view reuses this endpoint)."""
    scope = None
    if current.role == UserRole.admin and user_id:
        from uuid import UUID

        scope = UUID(user_id)
    elif current.role != UserRole.admin:
        scope = current.id
    return usage_summary(session, days=days, user_id=scope)


@router.get("/shadow-ai", response_model=list[ShadowDomainOut])
def shadow_ai(_: User = Depends(require_admin), session: Session = Depends(get_db)):
    return shadow_ai_domains(session)
