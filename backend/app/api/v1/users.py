"""Admin user management: list, create, activate/deactivate."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlmodel import Session, select

from app.core.deps import get_db, require_admin
from app.core.enums import UserRole
from app.core.security import hash_password
from app.core.time import utcnow
from app.domain.auth.service import normalize_email
from app.models.user import User
from app.schemas.auth import UserCreate, UserOut
from app.schemas.common import Page

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=Page[UserOut])
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    role: UserRole | None = None,
    _: User = Depends(require_admin),
    session: Session = Depends(get_db),
) -> Page[UserOut]:
    criteria = [User.role == role] if role is not None else []
    total = session.exec(select(func.count()).select_from(User).where(*criteria)).one()
    rows = session.exec(
        select(User)
        .where(*criteria)
        .order_by(User.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page[UserOut](
        items=[UserOut.model_validate(u) for u in rows],
        total=int(total),
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_db),
) -> UserOut:
    email = normalize_email(payload.email)
    if session.exec(select(User).where(User.email == email)).first() is not None:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(
        email=email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        department=payload.department,
        job_title=payload.job_title,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    # NOTE: the plaintext password is never returned — admin shares it out of band.
    return UserOut.model_validate(user)


@router.post("/{user_id}/status", response_model=UserOut)
def set_user_status(
    user_id: UUID,
    is_active: bool,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_db),
) -> UserOut:
    target = session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == admin.id:
        raise HTTPException(status_code=409, detail="Cannot deactivate your own account")
    target.is_active = is_active
    target.updated_at = utcnow()
    session.add(target)
    session.commit()
    session.refresh(target)
    return UserOut.model_validate(target)
