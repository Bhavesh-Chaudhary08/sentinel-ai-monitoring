"""Router aggregation for /api/v1."""

from fastapi import APIRouter

from app.api.v1 import (
    activity,
    alerts,
    analytics,
    audit,
    auth,
    capture,
    export,
    interactions,
    meta,
    policy,
    users,
    ws,
)

api_router = APIRouter()
api_router.include_router(meta.router)
api_router.include_router(auth.router)
api_router.include_router(capture.router)
api_router.include_router(activity.router)
api_router.include_router(policy.router)
api_router.include_router(interactions.router)
api_router.include_router(alerts.router)
api_router.include_router(analytics.router)
api_router.include_router(export.router)
api_router.include_router(users.router)
api_router.include_router(audit.router)
api_router.include_router(ws.router)
