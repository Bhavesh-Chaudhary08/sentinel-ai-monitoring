"""WebSocket endpoint streaming alert events to connected dashboards.

Two delivery modes, chosen at connection time:
  * Redis pub/sub (compose/VM deployments): Celery notifies → relay subscribes.
  * DB-polling fallback (single-process free hosting, no Redis): the relay
    polls for newly created alerts — identical frames, ~5s latency.

The DB remains the source of truth; a dropped socket just means the UI refetches.
"""

import asyncio
import json
import logging
from datetime import datetime

import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlmodel import Session, select

from app.core.config import settings
from app.core.enums import UserRole
from app.core.security import decode_token, token_user_id
from app.core.time import utcnow
from app.db.session import engine
from app.domain.alerts.realtime import ALERTS_CHANNEL, alert_payload
from app.models.alert import Alert
from app.models.user import User

logger = logging.getLogger("aidlp.ws")
router = APIRouter(tags=["realtime"])

POLL_SECONDS = 5.0
REDIS_CONNECT_TIMEOUT = 2.0


async def _require_admin_ws(token: str) -> User:
    payload = decode_token(token)  # raises HTTPException(401) on bad tokens
    with Session(engine) as session:
        user = session.get(User, token_user_id(payload))
    if user is None or not user.is_active or user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Admin role required for live alerts")
    return user


def _poll_new_alerts(since: datetime) -> list[dict]:
    """No-broker fallback: alerts created after `since`, in wire format."""
    with Session(engine) as session:
        rows = session.exec(
            select(Alert).where(Alert.created_at > since).order_by(Alert.created_at)
        ).all()
    return [alert_payload(row) for row in rows]


@router.websocket("/ws/alerts")
async def ws_alerts(websocket: WebSocket, token: str = Query(...)) -> None:
    """Admin-only live alert feed (?token=<JWT>)."""
    try:
        await _require_admin_ws(token)
    except HTTPException:
        await websocket.close(code=4401, reason="unauthorized")
        return

    await websocket.accept()
    # Cursor must predate the Redis connect attempt below: taking it after the
    # (up to 2s) timeout would silently drop any alert created in between —
    # exactly what happens on a fresh capture racing a new connection.
    cursor = utcnow()

    # Prefer Redis pub/sub; fall back to polling the DB when no broker is
    # reachable (single-process deployments: CLASSIFY_SYNC=true, no Redis).
    client = None
    pubsub = None
    try:
        client = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=REDIS_CONNECT_TIMEOUT,
            socket_timeout=6.0,
        )
        await client.ping()
        pubsub = client.pubsub()
        await pubsub.subscribe(ALERTS_CHANNEL)
        logger.info("alert websocket connected (redis pub/sub)")
    except Exception as exc:
        logger.warning(
            "redis unavailable (%s: %s) — alert websocket falls back to DB polling",
            type(exc).__name__,
            exc,
        )
        if client is not None:
            try:
                await client.aclose()
            except Exception:  # pragma: no cover - teardown best effort
                pass
            client = None

    try:
        if pubsub is not None:
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=5.0)
                if message and message.get("type") == "message":
                    # Validate JSON before pushing so a bad frame can't break clients.
                    try:
                        json.loads(message["data"])
                    except (TypeError, ValueError):
                        continue
                    await websocket.send_text(message["data"])
                else:
                    # Idle loop: sending keeps the socket liveness check honest —
                    # raises if the client has gone away.
                    await websocket.send_json({"type": "ping"})
                    await asyncio.sleep(0.5)
        else:
            while True:
                payloads = await asyncio.to_thread(_poll_new_alerts, cursor)
                for payload in payloads:
                    await websocket.send_text(json.dumps(payload, default=str))
                if payloads:
                    cursor = datetime.fromisoformat(payloads[-1]["created_at"])
                await websocket.send_json({"type": "ping"})
                await asyncio.sleep(POLL_SECONDS)
    except (WebSocketDisconnect, ConnectionError, RuntimeError):
        logger.info("alert websocket disconnected")
    finally:
        if pubsub is not None:
            try:
                await pubsub.unsubscribe(ALERTS_CHANNEL)
                await pubsub.aclose()
            except Exception:  # pragma: no cover - teardown best effort
                pass
        if client is not None:
            try:
                await client.aclose()
            except Exception:  # pragma: no cover - teardown best effort
                pass
