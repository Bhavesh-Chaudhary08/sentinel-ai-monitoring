"""Admin usage-analytics aggregation tests."""

from tests.conftest import auth_header, capture_event

BENIGN_PROMPT = "Summarize this article about glaciers in three bullet points"


def _post_interaction(client, user, count: int) -> None:
    for i in range(count):
        resp = client.post(
            "/api/v1/capture/interactions",
            json={
                "device_id": user.device_id,
                "events": [capture_event(prompt=BENIGN_PROMPT, event_id=f"{user.email}-{i}")],
            },
            headers=auth_header(user),
        )
        assert resp.status_code == 200
        assert resp.json()["accepted"] == 1


def test_top_users_joins_each_interaction_with_its_own_user(client, admin, employee):
    """Regression: selecting User.email without a JOIN cross-joined every
    interaction with every user — duplicate keys and misattributed counts
    in the admin dashboard's Top users table (React duplicate-key warning)."""
    _post_interaction(client, employee, 2)
    _post_interaction(client, admin, 1)

    resp = client.get("/api/v1/analytics/usage?days=7", headers=auth_header(admin))
    assert resp.status_code == 200
    usage = resp.json()

    keys = [row["key"] for row in usage["top_users"]]
    assert len(keys) == len(set(keys)), "top_users keys must be unique"
    by_email = {row["label"]: row["count"] for row in usage["top_users"]}
    assert by_email == {employee.email: 2, admin.email: 1}
    # The key must be the user the label names — not the first user in the table.
    for row in usage["top_users"]:
        expected = employee.id if row["label"] == employee.email else admin.id
        assert row["key"] == str(expected)

    assert usage["totals"]["active_users"] == 2
    assert usage["totals"]["interactions"] == 3
