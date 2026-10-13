"""Auth + RBAC tests."""

from tests.conftest import auth_header, capture_event


def test_login_and_me(client, admin):
    resp = client.post(
        "/api/v1/auth/token",
        data={"username": admin.email, "password": "Admin@12345"},
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    assert resp.json()["user"]["role"] == "admin"

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == admin.email


def test_login_rejects_bad_password(client, admin):
    resp = client.post(
        "/api/v1/auth/token",
        data={"username": admin.email, "password": "wrong-password"},
    )
    assert resp.status_code == 401


def test_register_creates_employee_and_logs_in(client, engine):
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "New.Hire@Corp.Example", "full_name": "New Hire",
              "password": "Hire@12345", "department": "Engineering"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["user"]["role"] == "employee"
    assert body["user"]["email"] == "new.hire@corp.example"  # normalized

    token = body["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["consent_accepted"] is False

    # Fresh signup has no consent yet → capture stays blocked until they accept.
    capture = client.post(
        "/api/v1/capture/interactions",
        json={"device_id": "reg-device-0001", "events": [capture_event()]},
        headers=headers,
    )
    assert capture.status_code == 403

    from sqlmodel import Session, select

    from app.models.audit import AuditLog

    with Session(engine) as session:
        actions = [a.action for a in session.exec(select(AuditLog)).all()]
        assert "user.register" in actions


def test_register_duplicate_email_is_409(client, employee):
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": employee.email.upper(), "full_name": "Dup",
              "password": "Whatever@123"},
    )
    assert resp.status_code == 409


def test_register_rejects_short_password(client):
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "weak@test.example", "full_name": "Weak", "password": "short"},
    )
    assert resp.status_code == 422


def test_register_cannot_choose_admin_role(client):
    # "role" is not part of RegisterIn — even if sent, the account is employee.
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "sneaky@test.example", "full_name": "Sneaky",
              "password": "Sneaky@12345", "role": "admin"},
    )
    assert resp.status_code == 201
    assert resp.json()["user"]["role"] == "employee"


def test_missing_token_is_401(client):
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/interactions").status_code == 401


def test_garbage_token_is_401(client):
    from uuid import uuid4

    from jose import jwt

    forged = jwt.encode(
        {"sub": str(uuid4()), "role": "employee", "iss": "aidlp"},
        "attacker-key",
        algorithm="HS256",
    )
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not.a.jwt"}).status_code == 401
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code
        == 401
    )


def test_employee_blocked_from_admin_endpoints(client, employee):
    for path in ("/api/v1/alerts", "/api/v1/policy/rules", "/api/v1/users",
                 "/api/v1/audit", "/api/v1/analytics/shadow-ai"):
        resp = client.get(path, headers=auth_header(employee))
        assert resp.status_code == 403, f"{path} should be admin-only"


def test_admin_can_list_users_and_rules(client, admin):
    assert client.get("/api/v1/users", headers=auth_header(admin)).status_code == 200
    assert client.get("/api/v1/policy/rules", headers=auth_header(admin)).status_code == 200


def test_consent_flow_enables_capture(client, no_consent_user):
    # Before consent: capture rejected.
    before = client.post(
        "/api/v1/capture/interactions",
        json={"device_id": "consent-device-1", "events": [capture_event()]},
        headers=auth_header(no_consent_user),
    )
    assert before.status_code == 403

    # Accept consent + bind device.
    accepted = client.post(
        "/api/v1/auth/consent",
        json={"device_id": "consent-device-1", "extension_version": "0.1.0", "accepted": True},
        headers=auth_header(no_consent_user),
    )
    assert accepted.status_code == 200
    assert accepted.json()["consent_accepted"] is True
    assert accepted.json()["is_enrolled"] is True

    # After consent: capture accepted.
    after = client.post(
        "/api/v1/capture/interactions",
        json={"device_id": "consent-device-1", "events": [capture_event(prompt="hello")]},
        headers=auth_header(no_consent_user),
    )
    assert after.status_code == 200


def test_rule_crud_and_audit_trail(client, admin, engine):
    from sqlmodel import Session, select

    from app.models.audit import AuditLog
    from tests.conftest import default_rules  # noqa: F401  (kept for symmetry)

    created = client.post(
        "/api/v1/policy/rules",
        json={"name": "unit-test-rule", "category": "financial",
              "action": "warn", "min_confidence": 0.7},
        headers=auth_header(admin),
    )
    assert created.status_code == 201
    rule_id = created.json()["id"]

    patched = client.patch(
        f"/api/v1/policy/rules/{rule_id}",
        json={"action": "block"},
        headers=auth_header(admin),
    )
    assert patched.status_code == 200
    assert patched.json()["action"] == "block"

    deleted = client.delete(f"/api/v1/policy/rules/{rule_id}", headers=auth_header(admin))
    assert deleted.status_code == 200
    listed = client.get("/api/v1/policy/rules?active=true", headers=auth_header(admin)).json()
    assert all(r["id"] != rule_id for r in listed["items"])

    with Session(engine) as session:
        actions = [a.action for a in session.exec(select(AuditLog)).all()]
        assert "rule.create" in actions
        assert "rule.update" in actions
        assert "rule.deactivate" in actions
