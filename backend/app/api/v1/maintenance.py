"""Administrative maintenance: wipe captured data and every non-admin account.

Used to hand a deployment over with a clean slate. Guarded three ways: admin
role required, an exact confirmation phrase in the body, and `dry_run`
defaulting to true so a mistaken call only reports what it would delete.

    POST /api/v1/maintenance/reset   {"confirm": "DELETE ALL DATA", "dry_run": true}
    POST /api/v1/maintenance/reset   {"confirm": "DELETE ALL DATA", "dry_run": false}

For a capture-only wipe (keep every account and all browser-time data), use
/purge-interactions instead — it clears captured interactions and their
classification findings, nothing else:

    POST /api/v1/maintenance/purge-interactions
    {"confirm": "DELETE ALL INTERACTIONS", "dry_run": true}

And for browser-time segments (where focused browser time went), leaving
interactions and accounts alone:

    POST /api/v1/maintenance/purge-browser-time
    {"confirm": "DELETE ALL BROWSER TIME", "dry_run": true}
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlmodel import Session

from app.core.deps import get_db, require_admin
from app.models.user import User

router = APIRouter(prefix="/maintenance", tags=["maintenance"])

CONFIRM_PHRASE = "DELETE ALL DATA"
PURGE_CONFIRM_PHRASE = "DELETE ALL INTERACTIONS"
BROWSER_TIME_CONFIRM_PHRASE = "DELETE ALL BROWSER TIME"
# Child rows first — findings reference an interaction. Users are never touched.
INTERACTION_TABLES = ["classification_finding", "captured_interaction"]

# Child rows first — the schema's foreign keys are not ON DELETE CASCADE.
TABLES = [
    "classification_finding",
    "captured_interaction",
    "time_segment",
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


class PurgeInteractionsIn(BaseModel):
    confirm: str
    dry_run: bool = True


def _interaction_rows(session: Session) -> dict[str, int]:
    return {
        table: int(session.execute(text(f'select count(*) from "{table}"')).scalar() or 0)
        for table in INTERACTION_TABLES
    }


@router.post("/purge-interactions")
def purge_interactions(
    payload: PurgeInteractionsIn,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_db),
) -> dict:
    """Delete captured interactions + findings only; accounts and time stay."""
    if payload.confirm != PURGE_CONFIRM_PHRASE:
        raise HTTPException(
            status_code=400,
            detail=f'confirm must be exactly "{PURGE_CONFIRM_PHRASE}"',
        )

    counts = _interaction_rows(session)
    if payload.dry_run:
        return {"dry_run": True, "rows": counts, "users_kept": True}

    for table in INTERACTION_TABLES:
        session.execute(text(f'delete from "{table}"'))
    session.commit()

    return {
        "dry_run": False,
        "deleted_rows": counts,
        "rows_after": _interaction_rows(session),
        "users_kept": True,
        "time_segments_kept": int(
            session.execute(text('select count(*) from "time_segment"')).scalar() or 0
        ),
    }


class PurgeBrowserTimeIn(BaseModel):
    confirm: str
    dry_run: bool = True


@router.post("/purge-browser-time")
def purge_browser_time(
    payload: PurgeBrowserTimeIn,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_db),
) -> dict:
    """Delete browser-time segments only; accounts and interactions stay."""
    if payload.confirm != BROWSER_TIME_CONFIRM_PHRASE:
        raise HTTPException(
            status_code=400,
            detail=f'confirm must be exactly "{BROWSER_TIME_CONFIRM_PHRASE}"',
        )

    before = int(session.execute(text('select count(*) from "time_segment"')).scalar() or 0)
    if payload.dry_run:
        return {"dry_run": True, "rows": {"time_segment": before}, "users_kept": True}

    session.execute(text('delete from "time_segment"'))
    session.commit()

    after = int(session.execute(text('select count(*) from "time_segment"')).scalar() or 0)
    interactions = int(
        session.execute(text('select count(*) from "captured_interaction"')).scalar() or 0
    )
    return {
        "dry_run": False,
        "deleted_rows": {"time_segment": before},
        "rows_after": {"time_segment": after},
        "users_kept": True,
        "interactions_kept": interactions,
    }
