"""User model: accounts, RBAC role, and the consent/enrollment record."""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Index
from sqlmodel import Field, SQLModel

from app.core.enums import UserRole
from app.core.time import utcnow


class User(SQLModel, table=True):
    __tablename__ = "user"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(index=True, unique=True, max_length=255)
    full_name: str = Field(max_length=120)
    hashed_password: Optional[str] = Field(default=None, max_length=255)

    # --- RBAC (mirrored into the JWT `role` claim) ---
    role: UserRole = Field(default=UserRole.employee, index=True)
    department: Optional[str] = Field(default=None, index=True, max_length=120)
    job_title: Optional[str] = Field(default=None, max_length=120)

    # --- consent & device enrollment: the gate for ALL capture activity ---
    device_id: Optional[str] = Field(default=None, index=True, max_length=64)
    extension_version: Optional[str] = Field(default=None, max_length=32)
    is_enrolled: bool = Field(default=False)
    consent_accepted: bool = Field(default=False)
    consent_version: Optional[str] = Field(default=None, max_length=32)  # which policy text
    consent_at: Optional[datetime] = Field(default=None)

    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    __table_args__ = (Index("ix_user_role_active", "role", "is_active"),)
