"""Ingest: validated capture events → CapturedInteraction rows → classification.

Two storage modes (settings.storage_mode):
- "full" (default): every prompt/response is stored verbatim at ingest time and
  classified; the retention sweep ages content out after retention_days_full.
- "minimal": raw text is NEVER written at ingest time; the worker retains it
  only for flagged interactions — everything else stays hash + masked preview.

In both modes every prompt IS classified, so every interaction ends up with a
risky/safe verdict either way.
"""

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, func, select

from app.core.config import settings
from app.core.enums import ClassificationStatus, ShadowRisk
from app.core.time import utcnow
from app.domain.capture.minimize import build_preview, is_full_storage, sha256_text, truncate
from app.domain.capture.shadow import (
    assess_shadow_risk,
    is_known_platform,
    is_valid_domain,
    normalize_domain,
)
from app.models.interaction import CapturedInteraction
from app.schemas.capture import CaptureEventIn, RejectedEvent, ShadowVisitEvent

logger = logging.getLogger("aidlp.capture.ingest")


@dataclass
class IngestResult:
    created: list[UUID] = field(default_factory=list)
    rejected: list[RejectedEvent] = field(default_factory=list)


@dataclass
class ShadowIngestResult:
    first_seen: list[str] = field(default_factory=list)
    capture_enabled_for: list[str] = field(default_factory=list)
    risk: ShadowRisk | None = None


def _known_event_ids(session: Session, user_id: UUID, event_ids: list[str]) -> set[str]:
    if not event_ids:
        return set()
    rows = session.exec(
        select(CapturedInteraction.client_event_id).where(
            CapturedInteraction.user_id == user_id,
            CapturedInteraction.client_event_id.in_(event_ids),
        )
    ).all()
    return set(rows)


def _rows_for_domain(session: Session, user_id: UUID, domain: str) -> int:
    return session.exec(
        select(func.count())
        .select_from(CapturedInteraction)
        .where(CapturedInteraction.user_id == user_id, CapturedInteraction.domain == domain)
    ).one()


def _dispatch_classification(interaction_id: UUID, prompt: str | None, response: str | None) -> None:
    if not prompt:
        return
    from app.workers import tasks  # local import: worker imports this module too

    args = (str(interaction_id), prompt, response)
    if settings.classify_sync:
        # Tests / no-Redis dev: run the exact same code path inline.
        tasks.classify_interaction(*args)
    else:
        tasks.classify_interaction.delay(*args)


def ingest_events(
    session: Session,
    user,
    device_id: str | None,
    events: list[CaptureEventIn],
) -> IngestResult:
    result = IngestResult()
    seen = _known_event_ids(session, user.id, [e.client_event_id for e in events])
    dispatch_queue: list[tuple[UUID, str | None, str | None]] = []

    for ev in events:
        if ev.client_event_id in seen:
            continue  # extension retry → idempotent success

        domain = normalize_domain(ev.domain)
        if not is_valid_domain(domain):
            result.rejected.append(
                RejectedEvent(client_event_id=ev.client_event_id, reason="invalid domain")
            )
            continue

        known = is_known_platform(domain)  # server list is authoritative
        first_seen = False
        shadow_risk = None
        if not known:
            first_seen = _rows_for_domain(session, user.id, domain) == 0
            shadow_risk = assess_shadow_risk(domain)

        prompt = truncate(ev.prompt_text, settings.max_prompt_chars)
        # Prompts-only monitoring (settings.capture_responses=False): response
        # text is dropped at the door — never stored, never classified.
        response = (
            truncate(ev.response_text, settings.max_response_chars)
            if settings.capture_responses
            else None
        )

        # Full-capture mode stores every prompt verbatim at ingest time; the
        # worker still classifies it and the retention sweep ages it out on
        # schedule. Minimal mode keeps the old contract: hash + preview only.
        store_full = is_full_storage()

        row = CapturedInteraction(
            id=uuid4(),
            user_id=user.id,
            device_id=device_id or user.device_id,
            client_event_id=ev.client_event_id,
            ai_tool=ev.ai_tool,
            domain=domain,
            page_path=ev.page_path,
            is_known_platform=known,
            is_first_seen=first_seen,
            shadow_risk=shadow_risk,
            prompt_text=prompt if store_full else None,  # minimal: raw lands via worker, if flagged
            response_text=response if store_full else None,
            prompt_hash=sha256_text(prompt),
            redacted_preview=build_preview(prompt) or build_preview(response),
            classification_status=(
                ClassificationStatus.pending if prompt else ClassificationStatus.skipped
            ),
            was_blocked=ev.was_blocked,
            occurred_at=ev.occurred_at,
            received_at=utcnow(),
        )
        if store_full:
            # Response-only rows are content too — store + retention deadline.
            row.content_stored = bool(prompt or response)
            row.purge_after = (
                utcnow() + timedelta(days=settings.retention_days_full)
                if (prompt or response)
                else None
            )
        session.add(row)
        session.flush()  # assigns PK before commit; catches constraint errors early
        seen.add(ev.client_event_id)
        result.created.append(row.id)
        dispatch_queue.append((row.id, prompt, response))

    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        logger.warning("Capture batch hit a uniqueness race; treating as duplicates")
        result.created.clear()
        return result

    # Dispatch strictly after commit so the worker can see the row.
    for interaction_id, prompt, response in dispatch_queue:
        try:
            _dispatch_classification(interaction_id, prompt, response)
        except Exception:
            # Never fail capture because the broker is down; the stale-pending
            # sweep will surface it and sync reprocessing remains possible.
            logger.exception("Failed to enqueue classification for %s", interaction_id)

    return result


def ingest_shadow_visits(
    session: Session,
    user,
    device_id: str | None,
    events: list[ShadowVisitEvent],
) -> ShadowIngestResult:
    """First-time access to an unrecognized, AI-looking domain → flagged row.

    Only first access per (user, domain) is recorded — the visit itself carries
    no prompt content, and repeat visits would add nothing new to the report.
    """
    result = ShadowIngestResult()
    seen = _known_event_ids(session, user.id, [e.client_event_id for e in events])

    for ev in events:
        domain = normalize_domain(ev.domain)
        if not is_valid_domain(domain) or is_known_platform(domain):
            continue  # invalid or not actually shadow AI

        # The extension will want the generic adapter on every unknown host the
        # probe flagged, regardless of whether this is the first visit.
        if domain not in result.capture_enabled_for:
            result.capture_enabled_for.append(domain)

        if ev.client_event_id in seen:
            continue
        if _rows_for_domain(session, user.id, domain) != 0:
            continue  # repeat access — already flagged before

        risk = assess_shadow_risk(domain, ev.markers, ev.page_title)
        row = CapturedInteraction(
            id=uuid4(),
            user_id=user.id,
            device_id=device_id or user.device_id,
            client_event_id=ev.client_event_id,
            domain=domain,
            page_path=None,
            is_known_platform=False,
            is_first_seen=True,
            shadow_risk=risk,
            prompt_hash=None,
            redacted_preview=(ev.page_title or None),
            classification_status=ClassificationStatus.skipped,
            occurred_at=ev.occurred_at,
            received_at=utcnow(),
        )
        session.add(row)
        seen.add(ev.client_event_id)
        result.first_seen.append(domain)
        if result.risk is None or _risk_rank(risk) > _risk_rank(result.risk):
            result.risk = risk

    session.commit()
    return result


def _risk_rank(risk: ShadowRisk) -> int:
    return {
        ShadowRisk.low: 0,
        ShadowRisk.unknown: 1,
        ShadowRisk.medium: 2,
        ShadowRisk.high: 3,
    }[risk]
