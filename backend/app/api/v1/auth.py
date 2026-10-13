"""Auth endpoints: OAuth2 password token, current user, consent recording."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select

from app.core.deps import get_current_user, get_db
from app.core.enums import UserRole
from app.core.security import hash_password
from app.domain.audit.service import record_audit
from app.domain.auth.service import authenticate, issue_token, normalize_email, record_consent
from app.models.user import User
from app.schemas.auth import ConsentIn, RegisterIn, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token", response_model=TokenOut)
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_db),
) -> TokenOut:
    """Used by the dashboard login page *and* the extension popup."""
    user = authenticate(session, form.username, form.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenOut(access_token=issue_token(user), user=UserOut.model_validate(user))


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterIn,
    session: Session = Depends(get_db),
) -> TokenOut:
    """Public self-signup for **employee** accounts; logs the new user straight in.

    Role is forced to `employee` (the schema has no role field) so this can
    never be used to mint admin access. Monitoring still doesn't start until
    the user accepts consent via the extension/popup — a fresh registration
    is rejected at the capture gate like any unconsented account.
    """
    email = normalize_email(payload.email)
    if session.exec(select(User).where(User.email == email)).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    user = User(
        email=email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=UserRole.employee,
        department=payload.department,
        job_title=payload.job_title,
    )
    session.add(user)
    session.flush()
    record_audit(session, user.id, "user.register", target_type="user",
                 target_id=user.id, detail={"email": email, "role": "employee"})
    session.commit()
    session.refresh(user)
    return TokenOut(access_token=issue_token(user), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user=Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)


@router.post("/consent", response_model=UserOut)
def accept_consent(
    payload: ConsentIn,
    user=Depends(get_current_user),
    session: Session = Depends(get_db),
) -> UserOut:
    """Employee accepts the monitoring notice; optionally binds their device.

    This is the transparency gate: without it, every capture request is
    rejected with 403 regardless of token validity.
    """
    if not payload.accepted:
        raise HTTPException(status_code=400, detail="Consent must be accepted to enable capture")
    user = record_consent(session, user, payload)
    session.commit()
    session.refresh(user)
    return UserOut.model_validate(user)
