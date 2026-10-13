"""Engine + session factory.

Postgres in Docker/production, SQLite (`sqlite:///:memory:` with StaticPool) in
the test-suite — the models only use portable column types to allow this.
"""

from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings


def _build_engine():
    url = settings.database_url
    kwargs: dict = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        # One shared in-memory DB across connections so tests see the same data.
        from sqlalchemy.pool import StaticPool

        kwargs = {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool}
    return create_engine(url, **kwargs)


engine = _build_engine()


def init_db() -> None:
    """Create tables directly — used by tests and as a dev safety net.

    Production schema changes always go through Alembic (`alembic upgrade head`).
    """
    import app.models  # noqa: F401  — ensures every model is registered

    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
