"""Administrative maintenance: wipe captured data and every non-admin account.

Used to hand a deployment over with a clean slate. Guarded three ways: admin
role required, an exact confirmation phrase in the body, and `dry_run`
defaulting to true so a mistaken call only reports what it would delete.

The audit entry is written after the wipe (it would otherwise be deleted with
the rest), so the action itself stays traceable.

    POST /api/v1/maintenance/reset   {"confirm": "DELETE ALL DATA", "dry_run": true}
    POST /api/v1/maintenance/reset   {"confirm": "DELETE ALL DATA", "dry_run": false}
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlmodel import Session

from app.core.deps import get_db, require_admin
from app.domain.audit.service import record_audit
from app.models.user import User

router = APIRouter(prefix="/maintenance", tags=["maintenance"])

CONFIRM_PHRASE = "DELETE ALL DATA"

# Child rows first — the schema's foreign keys are not ON DELETE CASCADE.
TABLES = [
    "classification_finding",
    "alert",
    "captured_interaction",
    "time_segment",
    "audit_log",
]


class ResetIn(BaseModel):
    confirm: str
    dry_run: bool = True


def _rows(session: Session) -> dict[str, int]:
    return {
        table: int(session.execute(text(f'select count(*) from "{table}"')).scalar() or 0)
        for table in TABLES
    }


@router.post("/reset")
def reset_data(
    payload: ResetIn,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_db),
) -> dict:
    if payload.confirm != CONFIRM_PHRASE:
        raise HTTPException(
            status_code=400,
            detail=f'confirm must be exactly "{CONFIRM_PHRASE}"',
        )

    doomed_users = [
        row[0]
        for row in session.execute(
            text("select email from \"user\" where role <> 'admin' order by email")
        ).all()
    ]
    counts = _rows(session)

    if payload.dry_run:
        return {
            "dry_run": True,
            "target": "this deployment's database",
            "rows": counts,
            "users_to_delete": doomed_users,
        }

    for table in TABLES:
        session.execute(text(f'delete from "{table}"'))
    session.execute(text("delete from \"user\" where role <> 'admin'"))

    record_audit(
        session,
        admin.id,
        "data.reset",
        target_type="system",
        detail={"rows": counts, "users_deleted": len(doomed_users)},
    )
    session.commit()

    remaining = [
        row[0]
        for row in session.execute(text("select email from \"user\" order by email")).all()
    ]
    return {
        "dry_run": False,
        "deleted_rows": counts,
        "deleted_users": doomed_users,
        "users_remaining": remaining,
        "rows_after": _rows(session),
    }
