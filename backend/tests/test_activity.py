"""Browser time segments: ingest gates + activity read endpoints.

Naive-UTC timestamps throughout, matching app.core.time.utcnow (see conftest).
"""

from datetime import date, datetime, timedelta
from uuid import uuid4

from sqlmodel import Session, select

from app.models.activity import TimeSegment
from tests.conftest import auth_header


def segment_event(
    *,
    event_id: str | None = None,
    domain: str | None = "github.com",
    page_path: str | None = "/org/repo",
    kind: str = "tab",
    active: int = 300,
    idle: int = 0,
    audible: int = 0,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
) -> dict:
    start = started_at or (datetime.utcnow() - timedelta(minutes=10))
    end = ended_at or (start + timedelta(minutes=10))
    return {
        "client_event_id": event_id or str(uuid4()),
        "kind": kind,
        "domain": domain,
        "page_path": page_path,
        "active_seconds": active,
        "idle_seconds": idle,
        "audible_seconds": audible,
        "started_at": start.isoformat(),
        "ended_at": end.isoformat(),
    }


def post_segments(client, user, events: list[dict], device_id: str | None = None):
    return client.post(
        "/api/v1/capture/time-sessions",
        json={"device_id": device_id or user.device_id, "events": events},
        headers=auth_header(user),
    )


# ------------------------------- ingest -------------------------------------


def test_ingest_requires_consent(client, no_consent_user):
    resp = post_segments(client, no_consent_user, [segment_event()])
    assert resp.status_code == 403


def test_ingest_requires_enrolled_device(client, employee):
    resp = post_segments(client, employee, [segment_event()], device_id="some-other-device")
    assert resp.status_code == 403


def test_ingest_happy_path(client, employee, session):
    resp = post_segments(
        client,
        employee,
        [segment_event(active=300, idle=120, audible=60)],
    )
    assert resp.status_code == 200
    assert resp.json() == {"accepted": 1, "rejected": []}

    row = session.exec(select(TimeSegment)).one()
    assert row.user_id == employee.id
    assert row.domain == "github.com"
    assert (row.active_seconds, row.idle_seconds, row.audible_seconds) == (300, 120, 60)
    assert row.purge_after is not None


def test_ingest_is_idempotent_on_retry(client, employee, session):
    event = segment_event()
    first = post_segments(client, employee, [event])
    second = post_segments(client, employee, [event])  # extension retries the batch
    assert first.json()["accepted"] == 1
    assert second.json()["accepted"] == 0
    assert len(session.exec(select(TimeSegment)).all()) == 1


def test_ingest_rejects_bad_rows(client, employee, session):
    events = [
        segment_event(domain="not a domain!!"),                       # invalid domain
        segment_event(                                               # ended before start
            started_at=datetime.utcnow(),
            ended_at=datetime.utcnow() - timedelta(minutes=5),
        ),
        segment_event(                                               # far-future clock
            started_at=datetime.utcnow() + timedelta(hours=3),
            ended_at=datetime.utcnow() + timedelta(hours=4),
        ),
        segment_event(active=0, idle=0),                             # nothing recorded
    ]
    resp = post_segments(client, employee, events)
    assert resp.status_code == 200
    body = resp.json()
    assert body["accepted"] == 0
    assert len(body["rejected"]) == 4
    assert len(session.exec(select(TimeSegment)).all()) == 0


def test_ingest_clamps_counters_into_duration(client, employee, session):
    # 10-minute segment claiming 10 hours of activity — server clamps.
    resp = post_segments(
        client,
        employee,
        [segment_event(active=36_000, idle=36_000, audible=36_000)],
    )
    assert resp.json()["accepted"] == 1
    row = session.exec(select(TimeSegment)).one()
    assert row.active_seconds == 600       # capped at the wall clock
    assert row.idle_seconds == 0           # active already consumed it all
    assert row.audible_seconds == 600


def test_ingest_strips_query_strings(client, employee, session):
    resp = post_segments(
        client,
        employee,
        [segment_event(page_path="/search?q=secret+query#frag")],
    )
    assert resp.json()["accepted"] == 1
    row = session.exec(select(TimeSegment)).one()
    assert row.page_path == "/search"


def test_ingest_accepts_real_client_timestamps(client, employee, session):
    """The extension sends Date.toISOString() — Z-suffixed, offset-aware.
    The project stores naive UTC, so ingest must normalize, not crash."""
    start = datetime.utcnow().replace(microsecond=0)
    end = start + timedelta(minutes=10)
    # Explicit Z suffix — what the extension's Date.toISOString() actually sends.
    event = segment_event(active=600)
    event["started_at"] = start.isoformat() + "Z"
    event["ended_at"] = end.isoformat() + "Z"
    resp = post_segments(client, employee, [event])
    assert resp.status_code == 200
    assert resp.json()["accepted"] == 1
    row = session.exec(select(TimeSegment)).one()
    assert row.started_at.tzinfo is None  # stored naive


def test_away_segments_carry_no_domain(client, employee, session):
    resp = post_segments(
        client,
        employee,
        [segment_event(kind="away", domain=None, page_path=None, active=600, idle=0)],
    )
    assert resp.json()["accepted"] == 1
    row = session.exec(select(TimeSegment)).one()
    assert row.kind.value == "away"
    assert row.domain is None


# ------------------------------- reads --------------------------------------


def _seed_segment(session, user, **kwargs) -> None:
    start = kwargs.pop("started_at", datetime.utcnow() - timedelta(minutes=30))
    session.add(
        TimeSegment(
            user_id=user.id,
            device_id=user.device_id,
            client_event_id=str(uuid4()),
            domain="chatgpt.com",
            page_path="/c/1",
            active_seconds=600,
            idle_seconds=60,
            audible_seconds=0,
            started_at=start,
            ended_at=start + timedelta(minutes=11),
            **kwargs,
        )
    )
    session.commit()


def test_daily_me_summary(client, employee, session):
    _seed_segment(session, employee)
    resp = client.get("/api/v1/activity/me?days=7", headers=auth_header(employee))
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_email"] == employee.email
    assert len(body["days"]) == 1
    day = body["days"][0]
    assert day["browser_active_seconds"] == 600
    assert day["browser_idle_seconds"] == 60
    assert day["other_seconds"] == 0
    assert day["away_seconds"] == 0


def test_employee_cannot_read_another_users_activity(client, employee, admin, session):
    _seed_segment(session, admin)
    resp = client.get(
        f"/api/v1/activity/daily?days=7&user_id={admin.id}", headers=auth_header(employee)
    )
    assert resp.status_code == 403
    resp = client.get(
        f"/api/v1/activity/top-domains?days=7&user_id={admin.id}", headers=auth_header(employee)
    )
    assert resp.status_code == 403
    resp = client.get(
        f"/api/v1/activity/segments?days=7&user_id={admin.id}", headers=auth_header(employee)
    )
    assert resp.status_code == 403


def test_user_can_read_own_daily_and_top_domains(client, employee, session):
    _seed_segment(session, employee)
    resp = client.get(
        f"/api/v1/activity/daily?days=7&user_id={employee.id}", headers=auth_header(employee)
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    resp = client.get(
        f"/api/v1/activity/top-domains?days=7&user_id={employee.id}", headers=auth_header(employee)
    )
    assert resp.status_code == 200
    assert resp.json() == [{"domain": "chatgpt.com", "seconds": 660}]


def test_admin_can_read_any_users_activity(client, employee, admin, session):
    _seed_segment(session, employee)
    resp = client.get(
        f"/api/v1/activity/daily?days=7&user_id={employee.id}", headers=auth_header(admin)
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    resp = client.get(
        f"/api/v1/activity/segments?days=7&user_id={employee.id}", headers=auth_header(admin)
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_team_daily_is_admin_only(client, employee, admin, session):
    _seed_segment(session, employee)
    resp = client.get("/api/v1/activity/team-daily?days=7", headers=auth_header(employee))
    assert resp.status_code == 403

    resp = client.get("/api/v1/activity/team-daily?days=7", headers=auth_header(admin))
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["user_email"] == employee.email
    assert rows[0]["browser_active_seconds"] == 600


def test_segments_timeline(client, employee, session):
    _seed_segment(session, employee)
    resp = client.get("/api/v1/activity/segments?days=1", headers=auth_header(employee))
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["domain"] == "chatgpt.com"
    assert rows[0]["kind"] == "tab"


# ------------------------------- trends (Phase 2) ---------------------------

def _seed_raw(session, user, *, domain, kind, start, seconds, active, idle=0, path="/x"):
    """Direct row insert for sequence/window tests (bypasses ingest clamps,
    so callers keep active+idle within the wall-clock span)."""
    session.add(
        TimeSegment(
            user_id=user.id,
            device_id=user.device_id,
            client_event_id=str(uuid4()),
            kind=kind,
            domain=domain,
            page_path=path,
            active_seconds=active,
            idle_seconds=idle,
            audible_seconds=0,
            started_at=start,
            ended_at=start + timedelta(seconds=seconds),
        )
    )
    session.commit()


def test_trends_compares_current_vs_previous_window(client, employee, session):
    now = datetime.utcnow()
    _seed_raw(session, employee, domain="github.com", kind="tab",
              start=now - timedelta(days=2, hours=1), seconds=600, active=600)
    _seed_raw(session, employee, domain="github.com", kind="tab",
              start=now - timedelta(days=10, hours=1), seconds=1200, active=1200)

    resp = client.get("/api/v1/activity/trends?days=7", headers=auth_header(employee))
    assert resp.status_code == 200
    body = resp.json()
    assert body["scope"] == "user"
    assert body["window_days"] == 7
    assert body["current"]["browser_active_seconds"] == 600
    assert body["current"]["segments"] == 1
    assert body["previous"]["browser_active_seconds"] == 1200
    assert body["previous"]["segments"] == 1
    assert body["deltas"]["browser_active_seconds"] == -50.0
    assert body["deltas"]["other_seconds"] is None  # no baseline in either window
    assert len(body["daily"]) == 1
    assert body["daily"][0]["browser_active_seconds"] == 600
    # self-scope still returns the comparison row for the employee
    assert len(body["users"]) == 1
    assert body["users"][0]["user_email"] == employee.email
    assert body["users"][0]["delta_pct"] == -50.0


def test_trends_missing_baseline_is_null_not_infinite(client, employee):
    resp = client.get("/api/v1/activity/trends?days=7", headers=auth_header(employee))
    assert resp.status_code == 200
    body = resp.json()
    assert body["current"]["browser_active_seconds"] == 0
    assert body["previous"]["browser_active_seconds"] == 0
    assert body["deltas"]["browser_active_seconds"] is None  # not 0, not ∞
    assert body["users"] == [] or body["users"][0]["delta_pct"] is None
    assert body["focus"]["context_switches"] == 0


def test_trends_focus_metrics_from_segment_sequence(client, employee, session):
    """Blocks/switches math: A-A extend → one block; A→B adjacent → switch;
    an away span breaks adjacency, so B→C after it is NOT a switch."""
    t0 = datetime.utcnow() - timedelta(hours=3)
    _seed_raw(session, employee, domain="a.example", kind="tab",
              start=t0, seconds=600, active=600)                       # block A (600s)
    _seed_raw(session, employee, domain="a.example", kind="tab",
              start=t0 + timedelta(minutes=11), seconds=300, active=300)  # still A (+300s)
    _seed_raw(session, employee, domain="b.example", kind="tab",
              start=t0 + timedelta(minutes=17), seconds=120, active=120)   # switch → B
    _seed_raw(session, employee, domain=None, kind="away",
              start=t0 + timedelta(minutes=20), seconds=600, active=600)   # break
    _seed_raw(session, employee, domain="c.example", kind="tab",
              start=t0 + timedelta(minutes=31), seconds=300, active=300)   # new start

    resp = client.get("/api/v1/activity/trends?days=1", headers=auth_header(employee))
    assert resp.status_code == 200
    focus = resp.json()["focus"]
    assert focus["focus_blocks"] == 3                 # A, B, C
    assert focus["context_switches"] == 1             # only A→B was adjacent
    assert focus["longest_focus_seconds"] == 900      # A = 600 + 300
    assert focus["avg_focus_block_seconds"] == round((900 + 120 + 300) / 3)
    assert focus["switches_per_day"] == 1.0


def test_trends_admin_team_scope_and_scoping(client, employee, admin, session):
    now = datetime.utcnow()
    _seed_raw(session, employee, domain="github.com", kind="tab",
              start=now - timedelta(days=10, hours=1), seconds=1200, active=1200)
    _seed_raw(session, employee, domain="github.com", kind="tab",
              start=now - timedelta(days=2, hours=1), seconds=600, active=600)

    team = client.get("/api/v1/activity/trends?days=7", headers=auth_header(admin)).json()
    assert team["scope"] == "team"
    assert team["user_id"] is None
    assert team["current"]["browser_active_seconds"] == 600
    assert team["previous"]["browser_active_seconds"] == 1200
    # Rows are the union of both windows: anyone with tracked time in either
    # period appears (so "had time before, none now" shows as -100%). Users
    # with no segments anywhere have nothing to compare and don't appear —
    # same rule as the team table above it.
    assert {u["user_email"] for u in team["users"]} == {employee.email}
    emp_row = next(u for u in team["users"] if u["user_email"] == employee.email)
    assert emp_row["delta_pct"] == -50.0
    assert admin.email not in {u["user_email"] for u in team["users"]}

    one = client.get(
        f"/api/v1/activity/trends?days=7&user_id={employee.id}",
        headers=auth_header(admin),
    ).json()
    assert one["scope"] == "user"
    assert one["user_id"] == str(employee.id)
    assert len(one["users"]) == 1


def test_trends_employee_cannot_query_another_user(client, employee, admin):
    resp = client.get(
        f"/api/v1/activity/trends?days=7&user_id={admin.id}", headers=auth_header(employee)
    )
    assert resp.status_code == 403

    # …and their unscoped call only ever sees their own numbers.
    resp = client.get("/api/v1/activity/trends?days=7", headers=auth_header(employee))
    assert resp.status_code == 200
    assert resp.json()["scope"] == "user"
    assert resp.json()["user_id"] == str(employee.id)


# ---------------------------- focus score (Phase 3) -------------------------

def _fixed_noon(days_ago: int = 1) -> datetime:
    """A stable timestamp well inside any test window: yesterday at 10:00 UTC.

    Anchoring to the clock's hour would make segments straddle midnight on
    late-night runs and split the seeded data across two day rows.
    """
    return (datetime.utcnow() - timedelta(days=days_ago)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )


def test_focus_score_formula_and_away_exclusion(client, employee, session):
    """Exact composite for a crafted day:
    - block A: 600s focused on a.example
    - block B (10s later, different domain): 300s active + 600s idle → switch
    - 1200s away (no input) — reported, but must NOT affect the score

    share = 900 / (900 + 600) = 0.60        → 27.0 pts
    continuity = avg block 750s / 1500s      → 15.0 pts
    calm = 1 − 1/12                           → 22.9 pts
    score = round(64.9) = 65
    """
    t0 = _fixed_noon()
    _seed_raw(session, employee, domain="a.example", kind="tab",
              start=t0, seconds=600, active=600)
    _seed_raw(session, employee, domain="b.example", kind="tab",
              start=t0 + timedelta(seconds=610), seconds=900, active=300, idle=600)
    _seed_raw(session, employee, domain=None, kind="away",
              start=t0 + timedelta(seconds=1520), seconds=1200, active=0, idle=1200)

    resp = client.get("/api/v1/activity/focus?days=2", headers=auth_header(employee))
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == str(employee.id)
    assert body["user_email"] == employee.email
    assert body["window_days"] == 2
    assert len(body["days"]) == 1
    row = body["days"][0]
    assert row["focus_score"] == 65
    assert row["components"] == {"share_pct": 60, "continuity_pct": 50, "calm_pct": 92}
    assert row["focus_seconds"] == 1500        # block lengths are spans, incl. in-block idle
    assert row["focus_blocks"] == 2
    assert row["context_switches"] == 1
    assert row["longest_focus_seconds"] == 900
    assert row["browser_active_seconds"] == 900
    assert row["browser_idle_seconds"] == 600
    assert row["away_seconds"] == 1200         # present in the payload…
    assert body["average_score"] == 65
    # …and excluded: had away counted in the share's denominator the score
    # would be round(0.4286*45 + 15 + 22.92) = 57, not 65.


def test_focus_score_none_when_no_focused_tab_time(client, employee, session):
    """A day with only away/other-app time has nothing to score: None ("—"
    in the UI), never a fake 0 that would read as a bad focus day."""
    _seed_raw(session, employee, domain=None, kind="away",
              start=_fixed_noon(), seconds=3600, active=600, idle=3000)

    resp = client.get("/api/v1/activity/focus?days=2", headers=auth_header(employee))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["days"]) == 1
    row = body["days"][0]
    assert row["focus_score"] is None
    assert row["components"] is None
    assert row["away_seconds"] == 3000
    assert row["other_seconds"] == 600
    assert body["average_score"] is None


def test_focus_average_excludes_untracked_days(client, employee, session):
    """average_score is the mean over days WITH focused-tab time; a nearby
    away-only day must dilute it to nothing (days are excluded, not zeroed)."""
    t0 = _fixed_noon()
    _seed_raw(session, employee, domain="a.example", kind="tab",
              start=t0, seconds=1500, active=1500)          # perfect day → 100
    _seed_raw(session, employee, domain=None, kind="away",
              start=t0 + timedelta(days=1), seconds=600, active=0, idle=600)

    resp = client.get("/api/v1/activity/focus?days=3", headers=auth_header(employee))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["days"]) == 2
    perfect, no_data = body["days"]
    assert perfect["focus_score"] == 100       # share 1.0, 25-min block, no switches
    assert no_data["focus_score"] is None
    assert body["average_score"] == 100        # not 50 — the away day is not a zero


def test_focus_scoping_matches_the_rest_of_activity(client, employee, admin, session):
    _seed_raw(session, employee, domain="github.com", kind="tab",
              start=_fixed_noon(), seconds=600, active=600)

    # employee: pinned to self, 403 on anyone else
    resp = client.get(
        f"/api/v1/activity/focus?days=2&user_id={admin.id}", headers=auth_header(employee)
    )
    assert resp.status_code == 403
    resp = client.get("/api/v1/activity/focus?days=2", headers=auth_header(employee))
    assert resp.json()["user_id"] == str(employee.id)

    # admin: may view one person; unknown user → 404; unscoped → themselves
    resp = client.get(
        f"/api/v1/activity/focus?days=2&user_id={employee.id}", headers=auth_header(admin)
    )
    assert resp.status_code == 200
    assert resp.json()["user_email"] == employee.email
    assert len(resp.json()["days"]) == 1
    resp = client.get(
        "/api/v1/activity/focus?days=2&user_id=00000000-0000-0000-0000-000000000000",
        headers=auth_header(admin),
    )
    assert resp.status_code == 404
    resp = client.get("/api/v1/activity/focus?days=2", headers=auth_header(admin))
    assert resp.json()["user_id"] == str(admin.id)


# ---------------------------- weekly digest (Phase 4) -----------------------

def _this_week_monday() -> date:
    """Monday of the CURRENT ISO week (UTC) — matches the endpoint default.

    Digest tests use the current week (not a past one) because the AI-usage
    counts include alerts, whose created_at is the server clock at ingest.
    """
    today = date.today()
    return today - timedelta(days=today.isoweekday() - 1)


def _week_label(monday: date) -> str:
    iso = monday.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def test_digest_week_rollup_and_scoping(client, employee, admin, session):
    """One person's week on a page: totals, focus rollup and AI counts, with
    the same scoping as every other activity endpoint."""
    from tests.conftest import capture_event, default_rules

    monday = _this_week_monday()
    t1 = datetime(monday.year, monday.month, monday.day, 10)  # Mon 10:00 UTC
    # Monday: one perfect 25-minute focused block → share 1.0, continuity 1.0,
    # calm 1.0 → score 100. The away span must not dent it.
    _seed_raw(session, employee, domain="a.example", kind="tab",
              start=t1, seconds=1500, active=1500)
    _seed_raw(session, employee, domain=None, kind="away",
              start=t1 + timedelta(hours=2), seconds=600, active=0, idle=600)
    # Tuesday: a 5-minute block → 45 + 0.2×30 + 25 = 76.
    _seed_raw(session, employee, domain="a.example", kind="tab",
              start=t1 + timedelta(days=1), seconds=300, active=300)

    default_rules(session, admin)
    for prompt in ("Summarize this article about glaciers",
                   "Deploy with this key: AKIA1234567890ABCDEF"):
        resp = client.post(
            "/api/v1/capture/interactions",
            json={
                "device_id": employee.device_id,
                "events": [capture_event(prompt=prompt, occurred_at=t1 + timedelta(hours=3))],
            },
            headers=auth_header(employee),
        )
        assert resp.status_code == 200, resp.text

    week = _week_label(monday)
    resp = client.get(f"/api/v1/activity/digest?week={week}", headers=auth_header(employee))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["week"] == week
    assert body["week_start"] == monday.isoformat()
    assert body["week_end"] == (monday + timedelta(days=6)).isoformat()
    assert body["user_id"] == str(employee.id)
    assert body["totals"]["browser_active_seconds"] == 1800
    assert body["totals"]["away_seconds"] == 600
    assert body["tracked_days"] == 2
    assert body["focus"]["average_score"] == round((100 + 76) / 2)  # 88
    assert body["focus"]["days_scored"] == 2
    assert body["focus"]["best_day"] == monday.isoformat()
    assert body["focus"]["best_day_score"] == 100
    assert body["focus"]["focus_seconds"] == 1800
    assert body["top_domains"] == [{"domain": "a.example", "seconds": 1800}]
    assert body["ai_usage"]["interactions"] == 2
    assert body["ai_usage"]["flagged"] == 1
    assert body["ai_usage"]["alerts"] == 1        # block action ⇒ one alert
    assert body["ai_usage"]["blocked"] == 0       # client reported the send went
    assert body["ai_usage"]["by_tool"][0]["key"] == "chatgpt"
    assert [d["date"] for d in body["days"]] == [
        monday.isoformat(), (monday + timedelta(days=1)).isoformat()
    ]

    # Scoping: employees are pinned to themselves,403 on anyone else.
    resp = client.get(
        f"/api/v1/activity/digest?week={week}&user_id={admin.id}",
        headers=auth_header(employee),
    )
    assert resp.status_code == 403

    # Admin: unscoped → their own (empty) week; scoped → the employee's week.
    resp = client.get(f"/api/v1/activity/digest?week={week}", headers=auth_header(admin))
    assert resp.status_code == 200
    mine = resp.json()
    assert mine["user_id"] == str(admin.id)
    assert mine["totals"]["segments"] == 0
    assert mine["focus"]["average_score"] is None   # no focused-tab time → "—"
    assert mine["days"] == []

    resp = client.get(
        f"/api/v1/activity/digest?week={week}&user_id={employee.id}",
        headers=auth_header(admin),
    )
    assert resp.status_code == 200
    assert resp.json()["user_email"] == employee.email
    assert resp.json()["focus"]["average_score"] == 88


def test_digest_empty_week_and_invalid_labels(client, employee):
    """No data is an honest empty week (score None → "—" in the UI), and an
    impossible week label is a 422, never a 500."""
    resp = client.get("/api/v1/activity/digest", headers=auth_header(employee))
    assert resp.status_code == 200
    body = resp.json()
    today = date.today().isoformat()
    assert body["week"] == _week_label(_this_week_monday())
    assert body["week_start"] <= today <= body["week_end"]  # JSON dates are strings
    assert body["totals"]["segments"] == 0
    assert body["tracked_days"] == 0
    assert body["focus"]["average_score"] is None
    assert body["focus"]["days_scored"] == 0
    assert body["days"] == []
    assert body["ai_usage"]["interactions"] == 0

    # 2025 has 52 ISO weeks (Jan 1 2025 is a Wednesday), so W53 doesn't exist;
    # W00 and a non-week label are never valid.
    for bad in ("2025-W53", "2026-W00", "2026-13", "garbage"):
        resp = client.get(
            f"/api/v1/activity/digest?week={bad}", headers=auth_header(employee)
        )
        assert resp.status_code == 422, bad


def test_digest_export_csv_is_scoped_and_audited(client, employee, admin, session):
    """The digest exports as CSV with the same scoping as the JSON endpoint,
    and — like every other export — lands in the audit log."""
    from app.models.audit import AuditLog

    monday = _this_week_monday()
    t1 = datetime(monday.year, monday.month, monday.day, 10)
    _seed_raw(session, employee, domain="a.example", kind="tab",
              start=t1, seconds=1500, active=1500)
    week = _week_label(monday)

    resp = client.get(f"/api/v1/export/digest?week={week}", headers=auth_header(employee))
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    local = employee.email.split("@")[0]
    assert f'digest-{week}-{local}.csv' in resp.headers["content-disposition"]
    assert "meta,week," + week in resp.text
    assert "time,browser_active_seconds,1500" in resp.text
    assert "focus,average_score,100" in resp.text   # the perfect Monday

    entry = session.exec(
        select(AuditLog).order_by(AuditLog.created_at.desc())
    ).first()
    assert entry is not None
    assert entry.action == "export.csv"
    assert entry.target_type == "digest"
    assert entry.actor_id == employee.id

    # Employees can't export someone else's week (same rule as the JSON one).
    resp = client.get(
        f"/api/v1/export/digest?week={week}&user_id={admin.id}",
        headers=auth_header(employee),
    )
    assert resp.status_code == 403
