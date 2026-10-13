"""Policy engine unit tests: matching, specificity, role overrides, defaults."""

from app.core.enums import PolicyAction, RiskCategory, UserRole
from app.domain.policy.engine import evaluate_policy
from app.models.policy import PolicyRule
from tests.conftest import default_rules


def test_default_action_is_log_only_when_no_rule_matches(session, employee):
    result = evaluate_policy(
        session, category=RiskCategory.confidential, score=0.99, user=employee
    )
    assert result.matched is False
    assert result.action == PolicyAction.log_only
    assert result.rule is None


def test_block_rule_matches_on_category_and_confidence(session, employee):
    default_rules(session, employee)
    result = evaluate_policy(
        session, category=RiskCategory.credentials, score=0.97, user=employee
    )
    assert result.matched is True
    assert result.action == PolicyAction.block
    assert result.rule.name == "test-block-credentials"
    assert result.message == "Blocked: secret detected"


def test_below_min_confidence_does_not_match(session, employee):
    default_rules(session, employee)
    result = evaluate_policy(
        session, category=RiskCategory.credentials, score=0.40, user=employee
    )
    assert result.matched is False
    assert result.action == PolicyAction.log_only


def test_role_override_beats_global_rule(session, admin, employee):
    """The seeded admin override (log-only for secrets) must win for admins…"""
    default_rules(session, admin)

    as_admin = evaluate_policy(
        session, category=RiskCategory.credentials, score=0.97, user=admin
    )
    assert as_admin.action == PolicyAction.log_only
    assert as_admin.rule.role_scope == UserRole.admin

    # …while employees keep getting the global block.
    as_employee = evaluate_policy(
        session, category=RiskCategory.credentials, score=0.97, user=employee
    )
    assert as_employee.action == PolicyAction.block


def test_priority_decides_between_same_scope_rules(session, employee):
    low = PolicyRule(
        name="low-priority-block", category=RiskCategory.pii,
        action=PolicyAction.block, priority=10, min_confidence=0.5,
    )
    high = PolicyRule(
        name="high-priority-block", category=RiskCategory.pii,
        action=PolicyAction.block, priority=500, min_confidence=0.5,
    )
    session.add(low)
    session.add(high)
    session.commit()

    result = evaluate_policy(session, category=RiskCategory.pii, score=0.8, user=employee)
    assert result.rule.name == "high-priority-block"


def test_department_scope_excludes_other_departments(session, employee):
    rule = PolicyRule(
        name="finance-only-warn", category=RiskCategory.financial,
        action=PolicyAction.warn, department_scope="Finance",
        priority=100, min_confidence=0.5,
    )
    session.add(rule)
    session.commit()

    assert evaluate_policy(
        session, category=RiskCategory.financial, score=0.9, user=employee
    ).matched is False


def test_inactive_rules_are_ignored(session, employee):
    default_rules(session, employee)
    for rule in session.query(PolicyRule).all():
        rule.is_active = False
    session.commit()

    result = evaluate_policy(session, category=RiskCategory.credentials, score=0.99, user=employee)
    assert result.matched is False
    assert result.action == PolicyAction.log_only
