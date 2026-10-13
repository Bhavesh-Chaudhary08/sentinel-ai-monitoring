"""Test fixtures: in-memory SQLite + FastAPI TestClient + auth helpers.

ML/NLP tiers are disabled in tests (they're optional by design) — the regex +
lexical tiers make classification fully deterministic here.
"""

import os
import sys
from datetime import datetime, timedelta
from uuid import uuid4

import pytest

# Make `app` importable when pytest runs from the backend/ directory.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("CLASSIFY_SYNC", "true")
os.environ.setdefault("PRESIDIO_ENABLED", "false")
os.environ.setdefault("SEMANTIC_ENABLED", "false")

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.enums import PolicyAction, RiskCategory, UserRole  # noqa: E402
from app.core.security import create_access_token, hash_password  # noqa: E402
from app.core.deps import get_db  # routes depend on get_db, not get_session
from app.db.session import engine as app_engine  # noqa: E402  (restored after tests)
from app.db.session import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import PolicyRule, User  # noqa: E402

settings.classify_sync = True
settings.presidio_enabled = False
settings.semantic_enabled = False


@pytest.fixture()
def engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def session(engine):
    with Session(engine) as s:
        yield s


@pytest.fixture()
def admin(engine) -> User:
    with Session(engine) as s:
        user = User(
            email="admin@test.example",
            full_name="Test Admin",
            hashed_password=hash_password("Admin@12345"),
            role=UserRole.admin,
            department="Security",
            is_enrolled=True,
            consent_accepted=True,
            consent_version=settings.consent_version,
            device_id="test-device-admin",
        )
        s.add(user)
        s.commit()
        s.refresh(user)
        return user


@pytest.fixture()
def employee(engine) -> User:
    with Session(engine) as s:
        user = User(
            email="emp@test.example",
            full_name="Test Employee",
            hashed_password=hash_password("Employee@123"),
            role=UserRole.employee,
            department="Engineering",
            is_enrolled=True,
            consent_accepted=True,
            consent_version=settings.consent_version,
            device_id="test-device-emp",
        )
        s.add(user)
        s.commit()
        s.refresh(user)
        return user


@pytest.fixture()
def no_consent_user(engine) -> User:
    with Session(engine) as s:
        user = User(
            email="noconsent@test.example",
            full_name="Unconsented",
            hashed_password=hash_password("Employee@123"),
            role=UserRole.employee,
            department="Engineering",
        )
        s.add(user)
        s.commit()
        s.refresh(user)
        return user


@pytest.fixture()
def client(engine):
    # The sync classify path opens sessions on the *app* engine — point it at
    # the test engine so inline classification sees the rows ingest just wrote.
    import app.workers.tasks as worker_tasks

    worker_tasks.engine = engine
    # Override BOTH callables: api routers use get_db, anything else get_session.
    app.dependency_overrides[get_db] = lambda: Session(engine)
    app.dependency_overrides[get_session] = lambda: Session(engine)
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    worker_tasks.engine = app_engine


def auth_header(user: User) -> dict[str, str]:
    token = create_access_token(user.id, user.role)
    return {"Authorization": f"Bearer {token}"}


def capture_event(
    *,
    prompt: str | None = None,
    response: str | None = None,
    domain: str = "chatgpt.com",
    tool: str = "chatgpt",
    event_id: str | None = None,
    occurred_at: datetime | None = None,
    was_blocked: bool = False,
) -> dict:
    return {
        "client_event_id": event_id or str(uuid4()),
        "occurred_at": (occurred_at or datetime.utcnow()).isoformat(),
        "ai_tool": tool,
        "domain": domain,
        "page_path": "/c/123",
        "prompt_text": prompt,
        "response_text": response,
        "was_blocked": was_blocked,
    }


def default_rules(session: Session, owner: User) -> None:
    """The subset of seeded rules the tests rely on."""
    session.add(
        PolicyRule(
            name="test-block-credentials",
            category=RiskCategory.credentials,
            action=PolicyAction.block,
            priority=200,
            min_confidence=0.70,
            block_message="Blocked: secret detected",
            created_by=owner.id,
        )
    )
    session.add(
        PolicyRule(
            name="test-warn-pii",
            category=RiskCategory.pii,
            action=PolicyAction.warn,
            priority=150,
            min_confidence=0.60,
            warn_message="Warn: PII",
            created_by=owner.id,
        )
    )
    session.add(
        PolicyRule(
            name="test-admin-credentials-override",
            category=RiskCategory.credentials,
            action=PolicyAction.log_only,
            role_scope=UserRole.admin,
            priority=900,
            min_confidence=0.70,
            created_by=owner.id,
        )
    )
    session.commit()


def future() -> datetime:
    return datetime.utcnow() + timedelta(seconds=1)
