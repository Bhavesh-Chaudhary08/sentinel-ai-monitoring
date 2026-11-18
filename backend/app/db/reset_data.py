"""Wipe captured data and every non-admin account.

For a clean slate before a demo or a hand-over: deletes all activity rows
(time segments, captured interactions, findings, alerts, audit entries) and
every user except the admin, so a fresh account can be registered afterwards.

Policy rules are configuration, not user data, so they are kept unless
--drop-policies is passed.

Destructive — requires --yes. Use --dry-run to see what would go.

    cd backend
    python -m app.db.reset_data --dry-run          # preview
    python -m app.db.reset_data --yes              # do it

Against another environment, point DATABASE_URL at it first (never commit it):

    DATABASE_URL="postgresql+psycopg2://...@...neon.tech/neondb?sslmode=require" \
      python -m app.db.reset_data --yes
"""

from __future__ import annotations

import sys

from sqlalchemy import text
from sqlmodel import Session

from app.db.session import engine

# Child rows first: FK order matters when the constraint is not ON DELETE CASCADE.
TABLES = [
    "classification_finding",
    "alert",
    "captured_interaction",
    "time_segment",
    "audit_log",
]


def _count(session: Session, sql: str) -> int:
    return int(session.execute(text(sql)).scalar() or 0)


def main(argv: list[str]) -> int:
    dry_run = "--dry-run" in argv
    confirmed = "--yes" in argv or "-y" in argv
    drop_policies = "--drop-policies" in argv

    if not dry_run and not confirmed:
        print("refusing to delete anything without --yes (or use --dry-run)")
        return 2

    url = engine.url
    print(f"target : {url.host}:{url.port}/{url.database} (driver {url.drivername})")
    print(f"mode   : {'DRY RUN' if dry_run else 'DELETE'}")

    with Session(engine) as session:
        admins = session.execute(
            text("select email from \"user\" where role = 'admin' order by email")
        ).all()
        others = session.execute(
            text("select email from \"user\" where role <> 'admin' order by email")
        ).all()
        print(f"admins kept      : {[row[0] for row in admins] or '(none!)'}")
        print(f"users to delete  : {[row[0] for row in others]}")

        for table in TABLES:
            print(f"  {table:26} {_count(session, f'select count(*) from \"{table}\"'):>7} rows")
        if drop_policies:
            print(f"  {'policy_rule':26} {_count(session, 'select count(*) from policy_rule'):>7} rows")

        if not admins:
            print("aborting: no admin account exists, a wipe would lock everyone out")
            return 3

        non_admin_users = _count(session, "select count(*) from \"user\" where role <> 'admin'")

        if dry_run:
            print(f"would delete {sum(_count(session, f'select count(*) from \"{t}\"') for t in TABLES)} "
                  f"activity rows and {non_admin_users} non-admin user(s)")
            return 0

        for table in TABLES:
            session.execute(text(f'delete from "{table}"'))
        session.execute(text("delete from \"user\" where role <> 'admin'"))
        if drop_policies:
            session.execute(text("delete from policy_rule"))
        session.commit()

        print("after  :")
        for table in TABLES:
            print(f"  {table:26} {_count(session, f'select count(*) from \"{table}\"'):>7} rows")
        remaining = session.execute(text("select email, role from \"user\" order by role, email")).all()
        print(f"users  : {[(r[0], r[1]) for r in remaining]}")
        print("done — register the new account at /register (or let an admin create it)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
