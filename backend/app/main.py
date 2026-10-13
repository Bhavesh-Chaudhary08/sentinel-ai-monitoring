"""FastAPI application factory."""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging

logger = logging.getLogger("aidlp.api")

# How often the in-process retention sweep runs (single-process deployments).
RETENTION_SWEEP_SECONDS = 6 * 3600


async def _retention_sweep_loop() -> None:
    """In-process replacement for Celery beat when no worker exists.

    Calls the very same task functions, so retention behavior is identical
    to the worker/beat (compose/VM) deployment.
    """
    from app.workers.tasks import mark_stale_pending, purge_expired_content  # noqa: PLC0415

    while True:
        await asyncio.sleep(RETENTION_SWEEP_SECONDS)
        try:
            purged = await asyncio.to_thread(purge_expired_content)
            stale = await asyncio.to_thread(mark_stale_pending)
            if purged or stale:
                logger.info("inline retention sweep: purged=%s stale-marked=%s", purged, stale)
        except Exception:  # the sweep must never kill the loop
            logger.exception("inline retention sweep failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger.info(
        "starting %s v%s (env=%s, presidio=%s, semantic=%s)",
        settings.project_name,
        settings.app_version,
        settings.environment,
        settings.presidio_enabled,
        settings.semantic_enabled,
    )
    run_sweeps = (
        settings.inline_scheduler
        if settings.inline_scheduler is not None
        else settings.classify_sync
    )
    scheduler: asyncio.Task[None] | None = None
    if run_sweeps:
        scheduler = asyncio.create_task(_retention_sweep_loop())
        logger.info("inline retention scheduler enabled (no Celery beat)")
    yield
    if scheduler is not None:
        scheduler.cancel()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.project_name,
        version=settings.app_version,
        description=(
            "Consented, transparent AI-usage monitoring & content-aware DLP for "
            "org-enrolled devices. Capture only runs for enrolled accounts with "
            "recorded consent; employees can always see their own data."
        ),
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/health", tags=["meta"])
    def health() -> JSONResponse:
        return JSONResponse({"status": "ok", "version": settings.app_version})

    if settings.frontend_dir:
        _mount_dashboard(app, Path(settings.frontend_dir))

    return app


def _mount_dashboard(app: FastAPI, root: Path) -> None:
    """Serve the built SPA from this process (single-origin deployments).

    Registered after every API route so /api/* and /health always win;
    unknown paths fall back to index.html for client-side routing, and
    traversal outside the static root is rejected.
    """
    root = root.resolve()
    if not (root / "index.html").is_file():
        logger.warning("FRONTEND_DIR=%s has no index.html — dashboard not served", root)
        return

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        candidate = (root / full_path).resolve() if full_path else root / "index.html"
        try:
            candidate.relative_to(root)
        except ValueError:
            raise HTTPException(status_code=404) from None
        if not candidate.is_file():
            candidate = root / "index.html"  # SPA client-side routing
        return FileResponse(candidate)


app = create_app()
