"""Demo seed data — idempotent, safe to re-run.

Run:  python -m app.db.seed
  or: docker compose --profile tools run --rm seed
"""

import os

from sqlmodel import Session, select

from app.core.config import settings
from app.core.enums import PolicyAction, RiskCategory, UserRole
from app.core.security import hash_password
from app.core.time import utcnow
from app.db.session import engine, init_db
from app.models.policy import PolicyRule
from app.models.user import User


USERS = [
    # email, name, password, role, department, job_title, device, consented
    ("admin@corp.example", "Asha Admin", "Admin@12345", UserRole.admin,
     "Security", "SOC Analyst", "dev-admin-01", True),
    ("alice@corp.example", "Alice Engineer", "Employee@123", UserRole.employee,
     "Engineering", "Backend Engineer", "dev-alice-01", True),
    ("bob@corp.example", "Bob Analyst", "Employee@123", UserRole.employee,
     "Finance", "Financial Analyst", "dev-bob-01", True),
    ("carol@corp.example", "Carol Writer", "Employee@123", UserRole.employee,
     "Marketing", "Content Strategist", "dev-carol-01", True),
    # Deliberately NOT consented — demonstrates the capture gate returning 403.
    ("temp@corp.example", "Tara Contractor", "Employee@123", UserRole.employee,
     "Contractors", "Contractor", None, False),
]

RULES = [
    dict(name="Block secrets in prompts",
         description="Credentials, API keys and private keys must never leave the device.",
         category=RiskCategory.credentials, action=PolicyAction.block, priority=200,
         min_confidence=0.70,
         block_message="Blocked by DLP: your prompt contains credentials or secrets. "
                       "Rotate them if they were exposed, then retry without the secret."),
    dict(name="Block confidential material",
         description="Embargoed/proprietary business content.",
         category=RiskCategory.confidential, action=PolicyAction.block, priority=180,
         min_confidence=0.75,
         block_message="Blocked by DLP: this looks like confidential internal material. "
                       "Redact it or request approval from your data owner."),
    dict(name="Warn on personal data (PII)",
         description="PII prompts are allowed but warned and retained for review.",
         category=RiskCategory.pii, action=PolicyAction.warn, priority=150,
         min_confidence=0.60,
         warn_message="Heads-up: this prompt appears to contain personal data. "
                      "Remove names/IDs/emails if the AI task doesn't need them."),
    dict(name="Warn on financial data",
         description="Invoices, forecasts, account numbers.",
         category=RiskCategory.financial, action=PolicyAction.warn, priority=140,
         min_confidence=0.70,
         warn_message="Heads-up: financial data detected. Use the sanctioned analytics "
                      "tools for figures covered by the finance data policy."),
    dict(name="Log source code prompts",
         description="Default: code prompts are logged (hash + category), not blocked.",
         category=RiskCategory.source_code, action=PolicyAction.log_only, priority=100,
         min_confidence=0.60),
    dict(name="Security team may paste secrets for incident triage",
         description="Role override: admins get log-only instead of block for credentials.",
         category=RiskCategory.credentials, action=PolicyAction.log_only, priority=900,
         role_scope=UserRole.admin, min_confidence=0.70),
]


def upsert_users(session: Session) -> list[str]:
    # Bootstrap only: demo accounts are seeded into an EMPTY user table. Once
    # any account exists (including a lone admin after a data reset) the demo
    # cast is never recreated, so a hand-over stays clean across redeploys.
    if session.exec(select(User).limit(1)).first() is not None:
        return []

    created: list[str] = []
    for email, name, password, role, department, job_title, device, consented in USERS:
        user = session.exec(select(User).where(User.email == email)).first()
        if user is None:
            user = User(
                email=email,
                full_name=name,
                hashed_password=hash_password(password),
                role=role,
                department=department,
                job_title=job_title,
                device_id=device,
                is_enrolled=consented,
                consent_accepted=consented,
                consent_version=settings.consent_version if consented else None,
                consent_at=utcnow() if consented else None,
            )
            session.add(user)
            created.append(email)
    session.commit()
    return created


def upsert_rules(session: Session) -> list[str]:
    created: list[str] = []
    for spec in RULES:
        existing = session.exec(select(PolicyRule).where(PolicyRule.name == spec["name"])).first()
        if existing is None:
            session.add(PolicyRule(**spec))
            created.append(spec["name"])
    session.commit()
    return created


def demo_seeding_disabled() -> bool:
    """SEED_DEMO_USERS=false keeps a wiped database clean.

    The hosted image runs this seeder on every boot, so without the switch a
    reset (admin-only, no demo accounts) would be silently undone on the next
    deploy.
    """
    return os.environ.get("SEED_DEMO_USERS", "true").strip().lower() in {
        "0", "false", "no", "off",
    }


def main() -> None:
    init_db()  # no-op if Alembic already created the schema
    if demo_seeding_disabled():
        print("SEED_DEMO_USERS=false — demo accounts left untouched")
        return
    with Session(engine) as session:
        new_users = upsert_users(session)
        new_rules = upsert_rules(session)

    print("Seed complete.")
    if new_users:
        print(f"  users created: {', '.join(new_users)}")
    if new_rules:
        print(f"  rules created: {len(new_rules)}")
    if not new_users and not new_rules:
        print("  nothing to do — data already present")
    print("\nDemo credentials (change these!):")
    print("  admin : admin@corp.example / Admin@12345")
    print("  employee : alice@corp.example / Employee@123  (also bob@, carol@)")
    print("  no-consent demo : temp@corp.example / Employee@123")


if __name__ == "__main__":
    main()
