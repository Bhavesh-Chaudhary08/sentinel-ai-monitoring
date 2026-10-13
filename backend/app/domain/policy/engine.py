"""Policy engine: resolve which rule governs a (category, score, subject) triple.

Resolution order:
  1. rule must be active and match every non-None matcher
     (category / ai_tool / domain / role_scope / department_scope / min_confidence)
  2. specificity: role- or department-scoped rules beat global ones
  3. priority (higher wins)
  4. min_confidence (higher wins — the stricter requirement)
No match → default action is log_only (everything is always logged anyway).
"""

from dataclasses import dataclass

from sqlmodel import Session, select

from app.core.enums import PolicyAction, RiskCategory
from app.models.policy import PolicyRule


@dataclass
class Evaluation:
    action: PolicyAction
    rule: PolicyRule | None
    matched: bool
    message: str | None = None


def _matches(
    rule: PolicyRule,
    *,
    category: RiskCategory,
    score: float,
    user,
    ai_tool,
    domain: str | None,
) -> bool:
    if rule.category is not None and rule.category != category:
        return False
    if rule.ai_tool is not None and ai_tool is not None and rule.ai_tool != ai_tool:
        return False
    if rule.domain:
        if not domain or not (domain == rule.domain or domain.endswith("." + rule.domain)):
            return False
    if score < rule.min_confidence:
        return False
    if rule.role_scope is not None and rule.role_scope != user.role:
        return False
    if rule.department_scope is not None and rule.department_scope != (user.department or ""):
        return False
    return True


def _specificity(rule: PolicyRule) -> tuple[int, int, float]:
    scope = (1 if rule.role_scope is not None else 0) + (1 if rule.department_scope else 0)
    return (scope, rule.priority, rule.min_confidence)


def evaluate_policy(
    session: Session,
    *,
    category: RiskCategory,
    score: float,
    user,
    ai_tool=None,
    domain: str | None = None,
) -> Evaluation:
    rules = session.exec(select(PolicyRule).where(PolicyRule.is_active == True)).all()  # noqa: E712
    candidates = [r for r in rules if _matches(r, category=category, score=score, user=user,
                                               ai_tool=ai_tool, domain=domain)]
    if not candidates:
        return Evaluation(action=PolicyAction.log_only, rule=None, matched=False)

    best = max(candidates, key=_specificity)
    message = (
        best.block_message if best.action == PolicyAction.block
        else best.warn_message if best.action == PolicyAction.warn
        else None
    )
    return Evaluation(action=best.action, rule=best, matched=True, message=message)
