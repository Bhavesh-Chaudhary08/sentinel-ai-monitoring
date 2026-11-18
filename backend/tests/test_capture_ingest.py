"""Capture + classification pipeline tests (regex/lexical tiers, sync mode)."""

from datetime import datetime, timedelta

from sqlmodel import select

from app.core.config import settings

from app.core.enums import ClassificationStatus, PolicyAction, RiskCategory, ShadowRisk
from app.models.interaction import CapturedInteraction, ClassificationFinding
from tests.conftest import auth_header, capture_event, default_rules

SECRET_PROMPT = "Deploy with this key: AKIA1234567890ABCDEF and the db password hunter2secret"
PII_PROMPT = "Email jane.doe@corp.example about her SSN 123-45-6789 renewal"
BENIGN_PROMPT = "Summarize this article about glaciers in three bullet points"


def test_capture_requires_consent(client, no_consent_user):
    resp = client.post(
        "/api/v1/capture/interactions",
        json={"device_id": "whatever-123", "events": [capture_event(prompt=BENIGN_PROMPT)]},
        headers=auth_header(no_consent_user),
    )
    assert resp.status_code == 403
    assert "consent" in resp.json()["detail"].lower()


def test_capture_rejects_wrong_device(client, employee):
    resp = client.post(
        "/api/v1/capture/interactions",
        json={"device_id": "not-my-device", "events": [capture_event(prompt=BENIGN_PROMPT)]},
        headers=auth_header(employee),
    )
    assert resp.status_code == 403
    assert "device" in resp.json()["detail"].lower()


def test_benign_prompt_verdict_depends_on_storage_mode(client, employee, engine):
    """Every prompt gets classified either way; only raw storage differs by mode."""
    from sqlmodel import Session

    event = capture_event(prompt=BENIGN_PROMPT, response="Here is a summary: …")
    resp = client.post(
        "/api/v1/capture/interactions",
        json={"device_id": employee.device_id, "events": [event]},
        headers=auth_header(employee),
    )
    assert resp.status_code == 200
    assert resp.json()["accepted"] == 1

    with Session(engine) as session:
        row = session.exec(select(CapturedInteraction)).one()
        assert row.prompt_hash and len(row.prompt_hash) == 64
        assert row.redacted_preview
        assert row.classification_status == ClassificationStatus.complete
        assert row.is_flagged is False
        assert row.risk_category == RiskCategory.none

        if settings.storage_mode == "full":
            # full-capture mode: benign prompts are stored too, with a retention deadline
            assert row.prompt_text == BENIGN_PROMPT
            assert row.content_stored is True
            assert row.purge_after is not None
        else:
            # minimization: hash + preview kept, raw content never persisted
            assert row.prompt_text is None
            assert row.response_text is None
            assert row.content_stored is False


def test_minimal_mode_still_drops_benign_text(client, employee, engine):
    """Explicit minimal-mode run of the old invariant."""
    from sqlmodel import Session

    old = settings.storage_mode
    settings.storage_mode = "minimal"
    try:
        event = capture_event(prompt=BENIGN_PROMPT)
        resp = client.post(
            "/api/v1/capture/interactions",
            json={"device_id": employee.device_id, "events": [event]},
            headers=auth_header(employee),
        )
        assert resp.status_code == 200
        with Session(engine) as session:
            row = session.exec(select(CapturedInteraction)).one()
            assert row.prompt_text is None
            assert row.response_text is None
            assert row.content_stored is False
            assert row.prompt_hash
            assert row.classification_status == ClassificationStatus.complete
    finally:
        settings.storage_mode = old


def test_flagged_prompt_retains_raw_text(client, employee, engine):
    from sqlmodel import Session

    with Session(engine) as session:
        default_rules(session, employee)

    event = capture_event(prompt=SECRET_PROMPT)
    resp = client.post(
        "/api/v1/capture/interactions",
        json={"device_id": employee.device_id, "events": [event]},
        headers=auth_header(employee),
    )
    assert resp.status_code == 200

    with Session(engine) as session:
        row = session.exec(select(CapturedInteraction)).one()
        assert row.is_flagged is True
        assert row.risk_category == RiskCategory.credentials
        assert row.content_stored is True
        assert row.purge_after is not None
        assert row.prompt_text == SECRET_PROMPT  # retained because flagged
        assert row.applied_action == PolicyAction.block
        assert row.classifier_version  # records which engines ran

        findings = session.exec(
            select(ClassificationFinding).where(ClassificationFinding.interaction_id == row.id)
        ).all()
        assert findings, "flagged rows keep per-detection findings"
        assert any(f.engine in ("regex", "presidio") for f in findings)


def test_duplicate_event_ids_are_idempotent(client, employee, engine):
    from sqlmodel import Session

    event = capture_event(prompt=BENIGN_PROMPT, event_id="fixed-event-0001")
    payload = {"device_id": employee.device_id, "events": [event]}

    first = client.post("/api/v1/capture/interactions", json=payload, headers=auth_header(employee))
    second = client.post("/api/v1/capture/interactions", json=payload, headers=auth_header(employee))

    assert first.status_code == second.status_code == 200
    assert second.json()["accepted"] == 0  # duplicate silently dropped

    with Session(engine) as session:
        assert len(session.exec(select(CapturedInteraction)).all()) == 1


def test_shadow_visit_flags_first_time_unknown_domain(client, employee, engine):
    from sqlmodel import Session

    event = {
        "client_event_id": "shadow-visit-0001",
        "occurred_at": datetime.utcnow().isoformat(),
        "domain": "chatgpt-free-login.xyz",
        "page_title": "ChatGPT login",
        "markers": {"composer": True, "send_label": True},
    }
    resp = client.post(
        "/api/v1/capture/shadow-visits",
        json={"device_id": employee.device_id, "events": [event]},
        headers=auth_header(employee),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "chatgpt-free-login.xyz" in body["first_seen"]
    assert body["risk"] == ShadowRisk.high.value  # brand term + suspicious TLD

    # Second visit: no new row (first-time access only), but capture stays enabled.
    again = dict(event, client_event_id="shadow-visit-0002")
    resp2 = client.post(
        "/api/v1/capture/shadow-visits",
        json={"device_id": employee.device_id, "events": [again]},
        headers=auth_header(employee),
    )
    assert resp2.json()["first_seen"] == []
    assert "chatgpt-free-login.xyz" in resp2.json()["capture_enabled_for"]

    with Session(engine) as session:
        rows = session.exec(select(CapturedInteraction)).all()
        assert len(rows) == 1
        assert rows[0].is_known_platform is False
        assert rows[0].is_first_seen is True


def test_known_platform_is_not_shadow(client, employee, engine):
    event = {
        "client_event_id": "shadow-known-0001",
        "occurred_at": datetime.utcnow().isoformat(),
        "domain": "chatgpt.com",
        "markers": {"composer": True},
    }
    resp = client.post(
        "/api/v1/capture/shadow-visits",
        json={"device_id": employee.device_id, "events": [event]},
        headers=auth_header(employee),
    )
    assert resp.json()["first_seen"] == []  # chatgpt.com is a known platform


def test_quick_policy_check_blocks_secrets_inline(client, employee, engine):
    from sqlmodel import Session

    with Session(engine) as session:
        default_rules(session, employee)

    resp = client.post(
        "/api/v1/policy/check",
        json={"prompt_text": "here is the api key: AKIA1234567890ABCDEF",
              "ai_tool": "chatgpt", "domain": "chatgpt.com"},
        headers=auth_header(employee),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == PolicyAction.block.value
    assert body["flagged"] is True
    assert body["category"] == RiskCategory.credentials.value
    assert body["rule_name"]


def test_employee_cannot_see_others_interactions(client, admin, employee):
    # Employee creates one of their own rows…
    client.post(
        "/api/v1/capture/interactions",
        json={"device_id": employee.device_id, "events": [capture_event(prompt=BENIGN_PROMPT)]},
        headers=auth_header(employee),
    )
    # …admin creates one of theirs.
    client.post(
        "/api/v1/capture/interactions",
        json={"device_id": admin.device_id, "events": [capture_event(prompt=BENIGN_PROMPT)]},
        headers=auth_header(admin),
    )

    listing = client.get("/api/v1/interactions", headers=auth_header(employee)).json()
    assert listing["total"] == 1
    assert {item["user_id"] for item in listing["items"]} == {str(employee.id)}

    admin_listing = client.get("/api/v1/interactions", headers=auth_header(admin)).json()
    assert admin_listing["total"] == 2
