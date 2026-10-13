"""Append-only audit helper.

`detail` must contain only non-sensitive metadata (rule names, filter
criteria, row counts) — never raw prompt text. Callers flush; the surrounding
request/task transaction commits.
"""

from uuid import UUID

from sqlmodel import Session

from app.models.audit import AuditLog


def record_audit(
    session: Session,
    actor_id: UUID | None,
    action: str,
    *,
    target_type: str | None = None,
    target_id: str | UUID | None = None,
    detail: dict | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        detail=detail,
    )
    session.add(entry)
    session.flush()
    return entry
