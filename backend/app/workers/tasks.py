"""Celery tasks: classification + policy evaluation, alert fan-out, retention.

`classify_interaction` receives the raw prompt as an argument (not from the
DB) — the row itself never contains raw text before the flagging decision.
"""

import logging
from datetime import timedelta
from uuid import UUID

from sqlalchemy import update as sa_update
from sqlmodel import Session

from app.core.config import settings
from app.core.enums import ClassificationStatus, PolicyAction
from app.core.time import utcnow
from app.db.session import engine
from app.domain.alerts.dispatcher import maybe_create_alert
from app.domain.alerts.realtime import alert_payload, publish_alert
from app.domain.classification.pipeline import classify_prompt
from app.domain.policy.engine import evaluate_policy
from app.models.alert import Alert
from app.models.interaction import CapturedInteraction, ClassificationFinding
from app.models.user import User
from app.workers.celery_app import celery_app

logger = logging.getLogger("aidlp.worker")

MAX_FINDINGS = 50
STALE_PENDING_MINUTES = 15


def _mark_failed(interaction_id: str) -> None:
    try:
        with Session(engine) as session:
            row = session.get(CapturedInteraction, UUID(interaction_id))
            if row is not None and row.classification_status == ClassificationStatus.pending:
                row.classification_status = ClassificationStatus.failed
                session.commit()
    except Exception:
        logger.exception("Could not mark %s as failed", interaction_id)


@celery_app.task(name="capture.classify_interaction")
def classify_interaction(
    interaction_id: str,
    prompt_text: str | None,
    response_text: str | None,
) -> None:
    """Full pipeline: classify → retain-if-flagged → policy → alert."""
    try:
        _classify_and_evaluate(interaction_id, prompt_text, response_text)
    except Exception:
        logger.exception("classification failed for %s", interaction_id)
        _mark_failed(interaction_id)


def _classify_and_evaluate(
    interaction_id: str,
    prompt_text: str | None,
    response_text: str | None,
) -> None:
    with Session(engine) as session:
        row = session.get(CapturedInteraction, UUID(interaction_id))
        if row is None:
            logger.warning("interaction %s no longer exists", interaction_id)
            return
        user = session.get(User, row.user_id)

        result = classify_prompt(prompt_text or "")

        row.classification_status = ClassificationStatus.complete
        row.risk_category = result.category
        row.risk_score = result.score
        row.classifier_version = result.version
        row.is_flagged = result.flagged

        for det in result.detections[:MAX_FINDINGS]:
            session.add(
                ClassificationFinding(
                    interaction_id=row.id,
                    engine=det.engine,
                    label=det.label[:64],
                    score=det.score,
                    start=det.start,
                    end=det.end,
                )
            )

        # --- content retention decision point ---
        # Full mode already stored the text at ingest; here we (re)compute the
        # retention window (flagged rows keep longer). Minimal mode retains raw
        # text only for flagged interactions — everything else is hash+preview.
        if settings.storage_mode == "full":
            if row.prompt_text or row.response_text:
                days = (
                    settings.retention_days_flagged
                    if row.is_flagged
                    else settings.retention_days_full
                )
                row.content_stored = True
                row.purge_after = utcnow() + timedelta(days=days)
        elif row.is_flagged and settings.store_raw_when_flagged:
            row.prompt_text = prompt_text
            row.response_text = response_text
            row.content_stored = True
            row.purge_after = utcnow() + timedelta(days=settings.retention_days_flagged)
        else:
            row.prompt_text = None
            row.response_text = None
            row.content_stored = False

        evaluation = evaluate_policy(
            session,
            category=result.category,
            score=result.score,
            user=user,
            ai_tool=row.ai_tool,
            domain=row.domain,
        )
        row.applied_action = evaluation.action
        row.policy_rule_id = evaluation.rule.id if evaluation.rule else None
        # row.was_blocked stays as reported by the extension (what actually happened).

        alert = maybe_create_alert(session, row, evaluation, user)
        session.commit()

        if alert is not None:
            _queue_alert(str(alert.id))


def _queue_alert(alert_id: str) -> None:
    """Queue via Redis — or run inline when CLASSIFY_SYNC=true (tests/dev),
    so no broker is required for the deterministic test-suite."""
    if settings.classify_sync:
        send_alert(alert_id)
    else:
        send_alert.delay(alert_id)


@celery_app.task(name="alert.send_alert")
def send_alert(alert_id: str) -> None:
    with Session(engine) as session:
        alert = session.get(Alert, UUID(alert_id))
        if alert is None:
            return
        publish_alert(alert_payload(alert))
        alert.notified_at = utcnow()
        session.commit()
        logger.info("alert %s notified (%s)", alert.id, alert.severity.value)


@celery_app.task(name="retention.purge_expired_content")
def purge_expired_content() -> int:
    """Null out raw text whose retention window expired; metadata survives."""
    with Session(engine) as session:
        result = session.execute(
            sa_update(CapturedInteraction)
            .where(
                CapturedInteraction.content_stored == True,  # noqa: E712
                CapturedInteraction.purge_after.is_not(None),
                CapturedInteraction.purge_after < utcnow(),
            )
            .values(prompt_text=None, response_text=None, content_stored=False)
        )
        session.commit()
        count = result.rowcount or 0
        if count:
            logger.info("retention sweep purged raw content from %s rows", count)
        return count


@celery_app.task(name="capture.mark_stale_pending")
def mark_stale_pending() -> int:
    """Rows still 'pending' long after arrival lost their queue message."""
    cutoff = utcnow() - timedelta(minutes=STALE_PENDING_MINUTES)
    with Session(engine) as session:
        result = session.execute(
            sa_update(CapturedInteraction)
            .where(
                CapturedInteraction.classification_status == ClassificationStatus.pending,  # type: ignore[comparison-overlap]
                CapturedInteraction.received_at < cutoff,
            )
            .values(classification_status=ClassificationStatus.failed)
        )
        session.commit()
        return result.rowcount or 0
