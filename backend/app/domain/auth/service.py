"""Authentication + consent services."""

from sqlmodel import Session, select

from app.core.config import settings
from app.core.security import create_access_token, verify_password
from app.core.time import utcnow
from app.models.user import User
from app.schemas.auth import ConsentIn


def normalize_email(email: str) -> str:
    return email.strip().lower()


def authenticate(session: Session, email: str, password: str) -> User | None:
    user = session.exec(select(User).where(User.email == normalize_email(email))).first()
    if user is None or not user.is_active or not user.hashed_password:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def issue_token(user: User) -> str:
    return create_access_token(user.id, user.role)


def record_consent(session: Session, user: User, payload: ConsentIn) -> User:
    """Employee accepts the monitoring notice (and optionally binds a device).

    Consent is versioned so the record can prove *which* notice text was
    accepted; re-accepting after a policy change updates the version.
    """
    user.consent_accepted = bool(payload.accepted)
    user.consent_version = settings.consent_version
    user.consent_at = utcnow()
    user.updated_at = utcnow()
    if payload.device_id:
        user.device_id = payload.device_id
        user.is_enrolled = True
    if payload.extension_version:
        user.extension_version = payload.extension_version
    session.add(user)
    session.flush()
    return user
