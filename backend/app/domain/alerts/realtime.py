"""Redis pub/sub publisher: Celery task → API WebSocket relay → dashboard."""

import json
import logging

import redis as redis_lib

from app.core.config import settings

logger = logging.getLogger("aidlp.alerts.realtime")

ALERTS_CHANNEL = "aidlp:alerts"


def alert_payload(alert) -> dict:
    """Wire format pushed to dashboards — shared by the Celery notify path
    and the WebSocket's DB-poll fallback (single-process deployments)."""
    return {
        "type": "alert",
        "id": str(alert.id),
        "severity": alert.severity.value,
        "status": alert.status.value,
        "title": alert.title,
        "summary": alert.summary,  # redacted preview only — never raw prompt
        "context": alert.context,
        "user_id": str(alert.user_id),
        "created_at": alert.created_at.isoformat(),
    }


def publish_alert(payload: dict) -> None:
    """Fire-and-forget: a missed WS push is harmless — the alert is in the DB."""
    try:
        client = redis_lib.Redis.from_url(settings.redis_url, decode_responses=True)
        client.publish(ALERTS_CHANNEL, json.dumps(payload, default=str))
        client.close()
    except Exception as exc:
        logger.warning("WS publish failed (%s: %s) — alert still persisted",
                       type(exc).__name__, exc)
