"""Password hashing and JWT issue/verify.

One token type serves both the React dashboard (Authorization header) and the
browser extension (stored in chrome.storage) — RBAC lives in the `role` claim.
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.enums import UserRole
from app.core.time import utcnow

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except ValueError:  # malformed hash stored — never 500 on login
        return False


def create_access_token(
    user_id: UUID,
    role: UserRole,
    expires_minutes: int | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    now = utcnow()
    expire = now + timedelta(minutes=expires_minutes or settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role.value,
        "iat": now,
        "exp": expire,
        "iss": "aidlp",
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT; raises HTTPException(401) on any failure."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    if payload.get("iss") not in (None, "aidlp") or not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token claims",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


def token_user_id(payload: dict[str, Any]) -> UUID:
    return UUID(payload["sub"])


def token_role(payload: dict[str, Any]) -> UserRole:
    try:
        return UserRole(payload.get("role"))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown role claim") from exc


def token_iat_datetime(payload: dict[str, Any]) -> datetime:
    """Token issue time as naive-UTC datetime — lets us reject tokens minted
    before consent was (re)given or a role changed."""
    return datetime.fromtimestamp(float(payload.get("iat", 0)), tz=timezone.utc).replace(tzinfo=None)
