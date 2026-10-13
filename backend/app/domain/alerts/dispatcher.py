"""Alert creation: policy outcome + confidence → admin-facing alert row."""

import logging

from app.core.config import settings
from app.core.enums import AlertSeverity, PolicyAction
from app.domain.policy.engine import Evaluation
from app.models.alert import Alert
from app.models.interaction import CapturedInteraction

logger = logging.getLogger("aidlp.alerts")


def severity_for(action: PolicyAction, score: float) -> AlertSeverity:
    if action == PolicyAction.block:
        return AlertSeverity.critical if score >= settings.critical_score else AlertSeverity.high
    return AlertSeverity.medium


def maybe_create_alert(session, interaction: CapturedInteraction, evaluation: Evaluation, user) -> Alert | None:
    """Warn/block outcomes raise an alert; log-only never does.

    `warn` additionally requires alert_min_score confidence so low-confidence
    warnings don't page the SOC with noise.
    """
    if evaluation.action == PolicyAction.log_only:
        return None
    if evaluation.action == PolicyAction.warn and interaction.risk_score < settings.alert_min_score:
        return None

    title = (
        f"{evaluation.action.value.upper()} · {interaction.risk_category.value} · {interaction.ai_tool.value}"
    )
    alert = Alert(
        interaction_id=interaction.id,
        rule_id=evaluation.rule.id if evaluation.rule else None,
        user_id=interaction.user_id,
        severity=severity_for(evaluation.action, interaction.risk_score),
        title=title,
        # Summaries are built from the *redacted* preview — raw prompt text
        # never enters the alerting path (see data minimization contract).
        summary=(interaction.redacted_preview or "Prompt flagged by DLP policy.")[:1000],
        context={
            "category": interaction.risk_category.value,
            "score": round(interaction.risk_score, 4),
            "ai_tool": interaction.ai_tool.value,
            "domain": interaction.domain,
            "action": evaluation.action.value,
            "rule": evaluation.rule.name if evaluation.rule else None,
            "user_email": user.email if user else None,
        },
    )
    session.add(alert)
    return alert
