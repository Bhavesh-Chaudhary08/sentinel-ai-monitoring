"""Auth + account schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import UserRole

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str
    role: UserRole
    department: str | None = None
    job_title: str | None = None
    is_enrolled: bool
    consent_accepted: bool
    consent_version: str | None = None
    consent_at: datetime | None = None
    device_id: str | None = None
    extension_version: str | None = None
    is_active: bool
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserCreate(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=255)
    full_name: str = Field(min_length=1, max_length=120)
    # bcrypt truncates at 72 bytes — validate rather than silently ignore.
    password: str = Field(min_length=8, max_length=72)
    role: UserRole = UserRole.employee
    department: str | None = Field(default=None, max_length=120)
    job_title: str | None = Field(default=None, max_length=120)


class RegisterIn(BaseModel):
    """Self-service signup payload.

    `role` is intentionally absent: public registration can only ever create
    employee accounts — admins are created by admins via POST /users.
    """

    email: str = Field(pattern=EMAIL_PATTERN, max_length=255)
    full_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=72)
    department: str | None = Field(default=None, max_length=120)
    job_title: str | None = Field(default=None, max_length=120)


class ConsentIn(BaseModel):
    """Recorded when the employee accepts the monitoring notice in the popup/dashboard."""

    device_id: str | None = Field(default=None, min_length=8, max_length=64)
    extension_version: str | None = Field(default=None, max_length=32)
    accepted: bool = True
