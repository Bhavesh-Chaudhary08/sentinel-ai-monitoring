"""Demo browser-time segments + AI-usage rows for the employee accounts.

A fresh dashboard looks empty until the extension has tracked a full week,
so this seeds realistic Mon-Fri workday data — focus blocks with short
breaks, an away spell, media time, plus a handful of safe/flagged/blocked
prompts — for the accounts people actually log in with.

It only FILLS GAPS: a day that already has real segments, or a week that
already has real interactions, is left untouched, so real capture is never
duplicated or overwritten. Every demo row is marked `device_id="demo"` with
a `client_event_id` prefixed `demo-` (the ingest dedupe keys stay unique),
which also makes the rows easy to filter or purge later.

Idempotent — re-running skips events that already exist.

Run from backend/:  python -m app.db.seed_activity
"""

from datetime import date, datetime, time, timedelta
from hashlib import sha256

from sqlmodel import Session, select

from app.core.config import settings
from app.core.enums import (
    AiTool,
    ClassificationStatus,
    PolicyAction,
    RiskCategory,
    TimeSegmentKind,
)
from app.core.time import utcnow
from app.db.session import engine
from app.models.activity import TimeSegment
from app.models.interaction import CapturedInteraction, ClassificationFinding
from app.models.user import User

DEMO_DEVICE = "demo"

# Employee accounts to seed. temp@ is deliberately left out — it exists to
# demonstrate the consent gate (capture returns 403 for it).
EMPLOYEE_EMAILS = [
    "alice@corp.example",
    "bob@corp.example",
    "carol@corp.example",
    "bhavesh.chaudhary1608@gmail.com",
]

# One workday in naive UTC (IST = UTC+5:30, so 04:00 UTC ≈ 09:30 local).
# (start, minutes, kind, domain, active, idle, audible) — active+idle fills
# the span; 1-minute gaps are tab switches (count as context switches),
# longer gaps are breaks (new focus block).
DAY_TEMPLATE: list[tuple[str, int, str, str | None, int, int, int]] = [
    ("04:00", 90, "tab", "github.com", 72, 18, 0),
    ("05:31", 47, "tab", "chatgpt.com", 40, 7, 0),
    ("06:19", 45, "tab", "stackoverflow.com", 36, 9, 0),
    ("07:05", 30, "away", None, 25, 5, 0),
    ("07:45", 75, "tab", "github.com", 61, 14, 0),
    ("09:01", 45, "tab", "gmail.com", 33, 12, 0),
    ("10:00", 32, "tab", "youtube.com", 26, 6, 24),
    ("10:41", 45, "tab", "notion.so", 32, 13, 0),
]

PAGE_PATHS = {
    "github.com": "/fastapi/fastapi",
    "chatgpt.com": "/c/demo-thread",
    "stackoverflow.com": "/q/42178965",
    "gmail.com": "/mail/u/0",
    "youtube.com": "/watch",
    "notion.so": "/demo-page",
}

# AI prompts per week: (weekday-offset, "HH:MM", tool, kind)
# kind: safe | pii | creds  (pii → flagged+warn, creds → flagged+blocked)
AI_WEEK_TEMPLATE: list[tuple[int, str, AiTool, str]] = [
    (0, "05:10", AiTool.chatgpt, "safe"),
    (1, "07:20", AiTool.gemini, "pii"),
    (2, "06:30", AiTool.claude, "safe"),
    (3, "08:40", AiTool.chatgpt, "creds"),
    (4, "05:50", AiTool.gemini, "safe"),
]
# Current week only exists up to "now", so it uses a short list.
AI_CURRENT_WEEK: list[tuple[int, str, AiTool, str]] = [
    (0, "05:00", AiTool.chatgpt, "safe"),
    (0, "06:40", AiTool.gemini, "pii"),
    (0, "08:20", AiTool.chatgpt, "creds"),
]

AI_TEXTS = {
    "safe_chatgpt": "Summarize this meeting note into action items",
    "safe_claude": "Explain the difference between SQL and NoSQL in two lines",
    "safe_gemini": "Write a Python one-liner to list unique values in a list",
    "pii": "Email john.doe@corp.example about invoice INV-2041 and call +91 9876543210",
    "creds": "Use this key: AKIA1234567890ABCDEF to access the bucket",
}
AI_DOMAINS = {
    AiTool.chatgpt: "chatgpt.com",
    AiTool.gemini: "gemini.google.com",
    AiTool.claude: "claude.ai",
}


def _iso_day(d: date) -> str:
    return d.isoformat()


def _existing_ids(session: Session, user_id) -> set[str]:
    rows = session.exec(
        select(CapturedInteraction.client_event_id).where(CapturedInteraction.user_id == user_id)
    ).all()
    seg_rows = session.exec(
        select(TimeSegment.client_event_id).where(TimeSegment.user_id == user_id)
    ).all()
    return set(rows) | set(seg_rows)


def _week_monday(d: date) -> date:
    return d - timedelta(days=d.isoweekday() - 1)


def seed_segments(session: Session, user: User, days: list[date], now: datetime) -> int:
    """One demo day per date that has no real segments yet."""
    known = _existing_ids(session, user.id)
    created = 0
    for day in days:
        has_real = session.exec(
            select(TimeSegment.id)
            .where(
                TimeSegment.user_id == user.id,
                TimeSegment.started_at >= datetime(day.year, day.month, day.day),
                TimeSegment.started_at < datetime(day.year, day.month, day.day)
                + timedelta(days=1),
            )
            .limit(1)
        ).first()
        if has_real:
            continue  # real capture already covers this day — don't mix

        for hhmm, minutes, kind, domain, active, idle, audible in DAY_TEMPLATE:
            started = datetime.combine(day, time.fromisoformat(hhmm))
            ended = started + timedelta(minutes=minutes)
            if ended > now:
                continue  # never seed the future (today's day is partial)
            event_id = f"demo-seg-{_iso_day(day)}-{hhmm}-{user.email.split('@')[0][:12]}"
            if event_id in known:
                continue
            session.add(
                TimeSegment(
                    user_id=user.id,
                    device_id=DEMO_DEVICE,
                    client_event_id=event_id,
                    kind=TimeSegmentKind(kind),
                    domain=domain,
                    page_path=PAGE_PATHS.get(domain) if domain else None,
                    active_seconds=active * 60,
                    idle_seconds=idle * 60,
                    audible_seconds=audible * 60,
                    started_at=started,
                    ended_at=ended,
                    purge_after=now + timedelta(days=settings.retention_days_time),
                )
            )
            known.add(event_id)
            created += 1
    return created


def _prompt_for(kind: str, tool: AiTool) -> tuple[str, str, RiskCategory, float, bool, PolicyAction | None]:
    """(prompt, redacted_preview, category, score, flagged, applied_action)."""
    if kind == "pii":
        text = AI_TEXTS["pii"]
        return (
            text,
            "Email j***@corp.example about invoice INV-2041 and call +91 98765***10",
            RiskCategory.pii,
            0.92,
            True,
            PolicyAction.warn,
        )
    if kind == "creds":
        text = AI_TEXTS["creds"]
        return (
            text,
            "Use this key: AKIA**************** to access the bucket",
            RiskCategory.credentials,
            0.98,
            True,
            PolicyAction.block,
        )
    text = {
        AiTool.chatgpt: AI_TEXTS["safe_chatgpt"],
        AiTool.claude: AI_TEXTS["safe_claude"],
        AiTool.gemini: AI_TEXTS["safe_gemini"],
    }[tool]
    return text, text, RiskCategory.none, 0.02, False, None


def seed_ai(session: Session, user: User, monday: date, template, now: datetime) -> int:
    """Demo interactions for one ISO week that has no real interactions."""
    start = datetime(monday.year, monday.month, monday.day)
    has_real = session.exec(
        select(CapturedInteraction.id)
        .where(
            CapturedInteraction.user_id == user.id,
            CapturedInteraction.occurred_at >= start,
            CapturedInteraction.occurred_at < start + timedelta(days=7),
        )
        .limit(1)
    ).first()
    if has_real:
        return 0

    known = _existing_ids(session, user.id)
    created = 0
    for offset, hhmm, tool, kind in template:
        day = monday + timedelta(days=offset)
        occurred = datetime.combine(day, time.fromisoformat(hhmm))
        if occurred > now:
            continue
        event_id = f"demo-ai-{_iso_day(day)}-{hhmm}-{user.email.split('@')[0][:12]}"
        if event_id in known:
            continue

        prompt, preview, category, score, flagged, action = _prompt_for(kind, tool)
        flagged_or_blocked = flagged or action == PolicyAction.block
        interaction = CapturedInteraction(
            user_id=user.id,
            device_id=DEMO_DEVICE,
            client_event_id=event_id,
            ai_tool=tool,
            domain=AI_DOMAINS[tool],
            page_path="/",
            prompt_text=prompt,
            prompt_hash=sha256(prompt.encode()).hexdigest(),
            redacted_preview=preview,
            classification_status=ClassificationStatus.complete,
            risk_category=category,
            risk_score=score,
            classifier_version="demo-seed",
            is_flagged=flagged,
            applied_action=action,
            was_blocked=action == PolicyAction.block,
            content_stored=True,
            purge_after=now
            + timedelta(
                days=settings.retention_days_flagged
                if flagged_or_blocked
                else settings.retention_days_default
            ),
            occurred_at=occurred,
        )
        session.add(interaction)
        # Persist the parent first: findings FK to this row, and the
        # unit-of-work must never emit their inserts before it exists.
        session.flush()
        known.add(event_id)
        created += 1

        detections = (
            (("EMAIL_ADDRESS", 0.92), ("PHONE_NUMBER", 0.85))
            if kind == "pii"
            else (("AWS_ACCESS_KEY", 0.98),)
        )
        for label, s in detections:
            session.add(
                ClassificationFinding(
                    interaction_id=interaction.id,
                    engine="regex",
                    label=label,
                    score=s,
                )
            )
    return created


def main() -> None:
    now = utcnow()
    today = now.date()
    this_monday = _week_monday(today)
    # Candidate workdays: last week's Mon-Fri, the week before's Mon-Fri,
    # and today (the current week is only one day old).
    days: list[date] = []
    for monday in (this_monday - timedelta(days=14), this_monday - timedelta(days=7)):
        days += [monday + timedelta(days=i) for i in range(5)]
    days.append(today)

    seg_total = ai_total = 0
    with Session(engine) as session:
        for email in EMPLOYEE_EMAILS:
            user = session.exec(select(User).where(User.email == email)).first()
            if not user:
                print(f"skip (not found): {email}")
                continue
            segs = seed_segments(session, user, days, now)
            # AI: full template for complete weeks, short list for the
            # current (partial) week.
            ai = 0
            for monday in (this_monday - timedelta(days=14), this_monday - timedelta(days=7)):
                ai += seed_ai(session, user, monday, AI_WEEK_TEMPLATE, now)
            ai += seed_ai(session, user, this_monday, AI_CURRENT_WEEK, now)
            seg_total += segs
            ai_total += ai
            print(f"{email}: +{segs} segments, +{ai} AI interactions")
        session.commit()

    print(f"done: {seg_total} segments, {ai_total} AI interactions "
          f"(device_id={DEMO_DEVICE!r}, idempotent)")


if __name__ == "__main__":
    main()
