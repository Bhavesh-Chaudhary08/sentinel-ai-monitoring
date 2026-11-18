"""Aggregation queries for the browser-time dashboards.

Four buckets per day, all derived from TimeSegment rows:
- browser_active: focused tab + OS input recent
- browser_idle:   focused tab + no input (page open, user away at desk)
- other:          browser unfocused + OS input recent (another app)
- away:           no input at all

Grouping is by UTC date. Org-timezone day-boundaries are a Phase-2 concern.
"""

from datetime import date, datetime, timedelta
from uuid import UUID

from sqlalchemy import case, func
from sqlmodel import Session, select

from app.core.enums import TimeSegmentKind
from app.core.time import utcnow
from app.models.activity import TimeSegment
from app.models.interaction import CapturedInteraction
from app.models.user import User
from app.schemas.activity import (
    DaySummary,
    DigestAiUsage,
    DigestFocus,
    DigestOut,
    FocusComponents,
    FocusDayRow,
    FocusMetrics,
    FocusOut,
    PeriodTotals,
    SegmentOut,
    TeamDayRow,
    TopDomainRow,
    TrendDeltas,
    TrendsOut,
    UserTrendRow,
)
from app.schemas.analytics import KeyCount

MAX_DAYS = 90


def window_start(days: int) -> datetime:
    return utcnow() - timedelta(days=max(1, min(days, MAX_DAYS)))


def _bucketed(group_cols, where, extras=()):
    """Select the five per-group sums shared by every rollup here.

    `extras` appends further aggregates (e.g. a row count) after the sums —
    callers that don't need them see exactly the old column layout.
    """

    def total(kind: TimeSegmentKind, column: str):
        return func.coalesce(
            func.sum(
                case((TimeSegment.kind == kind, getattr(TimeSegment, column)), else_=0)
            ),
            0,
        )

    return select(
        *group_cols,
        total(TimeSegmentKind.tab, "active_seconds"),
        total(TimeSegmentKind.tab, "idle_seconds"),
        total(TimeSegmentKind.away, "active_seconds"),
        total(TimeSegmentKind.away, "idle_seconds"),
        func.coalesce(func.sum(TimeSegment.audible_seconds), 0),
        *extras,
    ).where(*where)


def daily_for_user(session: Session, user_id: UUID, days: int) -> list[DaySummary]:
    day = func.date(TimeSegment.started_at)
    rows = session.exec(
        _bucketed(
            (day,),
            (TimeSegment.user_id == user_id, TimeSegment.started_at >= window_start(days)),
        )
        .group_by(day)
        .order_by(day)
    ).all()
    return [
        DaySummary(
            date=row[0],
            browser_active_seconds=int(row[1]),
            browser_idle_seconds=int(row[2]),
            other_seconds=int(row[3]),
            away_seconds=int(row[4]),
            audible_seconds=int(row[5]),
        )
        for row in rows
    ]


def team_daily(session: Session, days: int) -> list[TeamDayRow]:
    """Per-user per-day rollup across the org (admin Activity page)."""
    day = func.date(TimeSegment.started_at)
    rows = session.exec(
        _bucketed(
            (TimeSegment.user_id, User.email, User.full_name, day),
            (TimeSegment.started_at >= window_start(days),),
        )
        .select_from(TimeSegment)
        .join(User, User.id == TimeSegment.user_id)
        .where(User.is_active == True)  # noqa: E712 — SQLModel boolean compare
        .group_by(TimeSegment.user_id, User.email, User.full_name, day)
        .order_by(User.email, day)
    ).all()
    return [
        TeamDayRow(
            user_id=row[0],
            user_email=row[1],
            user_name=row[2],
            date=row[3],
            browser_active_seconds=int(row[4]),
            browser_idle_seconds=int(row[5]),
            other_seconds=int(row[6]),
            away_seconds=int(row[7]),
            audible_seconds=int(row[8]),
        )
        for row in rows
    ]


def top_domains(session: Session, user_id: UUID, days: int, limit: int = 8) -> list[TopDomainRow]:
    return _top_domains_between(session, user_id, window_start(days), None, limit)


def _top_domains_between(
    session: Session,
    user_id: UUID,
    since: datetime,
    until: datetime | None,
    limit: int = 8,
) -> list[TopDomainRow]:
    conditions = [
        TimeSegment.user_id == user_id,
        TimeSegment.kind == TimeSegmentKind.tab,
        TimeSegment.domain.is_not(None),
        TimeSegment.started_at >= since,
    ]
    if until is not None:
        conditions.append(TimeSegment.started_at < until)
    rows = session.exec(
        select(TimeSegment.domain, func.sum(TimeSegment.active_seconds + TimeSegment.idle_seconds))
        .where(*conditions)
        .group_by(TimeSegment.domain)
        .order_by(func.sum(TimeSegment.active_seconds + TimeSegment.idle_seconds).desc())
        .limit(max(1, min(limit, 50)))
    ).all()
    return [TopDomainRow(domain=row[0], seconds=int(row[1] or 0)) for row in rows]


def recent_segments(
    session: Session, user_id: UUID, days: int, limit: int = 200
) -> list[SegmentOut]:
    rows = session.exec(
        select(TimeSegment)
        .where(TimeSegment.user_id == user_id, TimeSegment.started_at >= window_start(days))
        .order_by(TimeSegment.started_at.desc())
        .limit(max(1, min(limit, 500)))
    ).all()
    return [
        SegmentOut(
            id=row.id,
            kind=row.kind,
            domain=row.domain,
            page_path=row.page_path,
            active_seconds=row.active_seconds,
            idle_seconds=row.idle_seconds,
            audible_seconds=row.audible_seconds,
            started_at=row.started_at,
            ended_at=row.ended_at,
        )
        for row in rows
    ]


# ------------------------------ trends (Phase 2) ----------------------------
# Current window vs the immediately preceding window of equal length, plus
# depth-of-work metrics derived from the segment SEQUENCE. Comparisons are
# duration facts, never verdicts (module docstring).

# A gap longer than this ends a focus block: the sessionizer closes segments
# on tab/focus changes, so a bigger hole means unrecorded time (a break, a
# suspended worker), not continued focus on the same domain.
MAX_BLOCK_GAP = timedelta(minutes=2)


def _add(t: PeriodTotals, seg: TimeSegment) -> None:
    """Fold one raw segment into a PeriodTotals (same bucket rules as SQL)."""
    if seg.kind == TimeSegmentKind.tab:
        t.browser_active_seconds += seg.active_seconds
        t.browser_idle_seconds += seg.idle_seconds
    else:
        t.other_seconds += seg.active_seconds
        t.away_seconds += seg.idle_seconds
    t.audible_seconds += seg.audible_seconds
    t.segments += 1


def _pct(current: int, previous: int) -> float | None:
    """Percent change; None when there is no baseline (a percentage against
    zero would be infinite — the UI shows "new" instead of a fake number)."""
    if previous <= 0:
        return None
    return round((current - previous) / previous * 100, 1)


def _focus_for_user(segments: list[TimeSegment]) -> dict[str, int]:
    """One user's segments (any order) → raw focus numbers.

    Rules:
    - only kind=tab segments with a domain count as focus; away spans and
      internal pages are break separators — they split blocks;
    - consecutive segments on the SAME domain with gaps <= MAX_BLOCK_GAP are
      one focus block (length = sum of the segments' own spans, so overlap
      can never inflate it);
    - a context switch is a domain change between two blocks adjacent in
      time (gap <= MAX_BLOCK_GAP). Moving on after a long break is a new
      start, not a switch.
    """
    entries: list[tuple[str, datetime, datetime, int] | None] = []

    for seg in sorted(segments, key=lambda s: s.started_at):
        if seg.kind != TimeSegmentKind.tab or not seg.domain:
            entries.append(None)
            continue
        span = max(0, int((seg.ended_at - seg.started_at).total_seconds()))
        last = entries[-1] if entries else None
        if (
            last is not None
            and last[0] == seg.domain
            and (seg.started_at - last[2]) <= MAX_BLOCK_GAP
        ):
            entries[-1] = (last[0], last[1], seg.ended_at, last[3] + span)
        else:
            entries.append((seg.domain, seg.started_at, seg.ended_at, span))

    real = [e for e in entries if e is not None]
    switches = sum(
        1
        for prev, cur in zip(entries, entries[1:])
        if prev is not None
        and cur is not None
        and prev[0] != cur[0]
        and (cur[1] - prev[2]) <= MAX_BLOCK_GAP
    )
    block_seconds = sum(e[3] for e in real)
    return {
        "focus_blocks": len(real),
        "context_switches": switches,
        "block_seconds": block_seconds,
        "longest": max((e[3] for e in real), default=0),
    }


def _focus_metrics(per_user: dict[UUID, list[TimeSegment]], days: int) -> FocusMetrics:
    """Aggregate per-user focus numbers across a scope (team = sums + max)."""
    blocks = switches = block_seconds = longest = 0
    for segs in per_user.values():
        m = _focus_for_user(segs)
        blocks += m["focus_blocks"]
        switches += m["context_switches"]
        block_seconds += m["block_seconds"]
        longest = max(longest, m["longest"])
    return FocusMetrics(
        focus_blocks=blocks,
        context_switches=switches,
        switches_per_day=round(switches / days, 1) if days else 0.0,
        longest_focus_seconds=longest,
        avg_focus_block_seconds=round(block_seconds / blocks) if blocks else 0,
    )


def trends(session: Session, user_id: UUID | None, days: int) -> TrendsOut:
    """Current vs previous window of equal length.

    user_id=None scopes to the whole org (admin team view); a UUID pins the
    scope to one user (the router already forces employees to themselves).
    Windows are exact datetime boundaries, so a segment never leaks across.
    """
    days = max(1, min(days, MAX_DAYS))
    now = utcnow()
    current_start = now - timedelta(days=days)
    previous_start = current_start - timedelta(days=days)

    user_filter = () if user_id is None else (TimeSegment.user_id == user_id,)
    active_filter = (User.is_active == True,)  # noqa: E712 — SQLModel boolean compare

    # 1) Raw segments of the CURRENT window: exact boundary, per-user grouping
    #    for focus metrics, and the daily series — one pass, one query.
    raw = session.exec(
        select(TimeSegment, User.email, User.full_name)
        .select_from(TimeSegment)
        .join(User, User.id == TimeSegment.user_id)
        .where(TimeSegment.started_at >= current_start, *user_filter, *active_filter)
        .order_by(TimeSegment.started_at)
    ).all()

    daily_map: dict[date, PeriodTotals] = {}
    per_user_current: dict[UUID, dict] = {}
    segments_by_user: dict[UUID, list[TimeSegment]] = {}
    for seg, email, name in raw:
        _add(daily_map.setdefault(seg.started_at.date(), PeriodTotals()), seg)
        info = per_user_current.setdefault(
            seg.user_id, {"email": email, "name": name, "totals": PeriodTotals()}
        )
        _add(info["totals"], seg)
        segments_by_user.setdefault(seg.user_id, []).append(seg)

    current = PeriodTotals()
    for totals in daily_map.values():
        current.browser_active_seconds += totals.browser_active_seconds
        current.browser_idle_seconds += totals.browser_idle_seconds
        current.other_seconds += totals.other_seconds
        current.away_seconds += totals.away_seconds
        current.audible_seconds += totals.audible_seconds
        current.segments += totals.segments

    # 2) Previous window as per-user sums — cheap grouped SQL; the sequence
    #    (focus metrics) is only reported for the current window.
    prev_rows = session.exec(
        _bucketed(
            (TimeSegment.user_id, User.email, User.full_name),
            (
                TimeSegment.started_at >= previous_start,
                TimeSegment.started_at < current_start,
                *user_filter,
            ),
            (func.count(),),  # → segments per user in the previous window
        )
        .select_from(TimeSegment)
        .join(User, User.id == TimeSegment.user_id)
        .where(*active_filter)
        .group_by(TimeSegment.user_id, User.email, User.full_name)
    ).all()

    previous = PeriodTotals()
    per_user_previous: dict[UUID, dict] = {}
    for row in prev_rows:
        totals = PeriodTotals(
            browser_active_seconds=int(row[3]),
            browser_idle_seconds=int(row[4]),
            other_seconds=int(row[5]),
            away_seconds=int(row[6]),
            audible_seconds=int(row[7]),
            segments=int(row[8]),
        )
        previous.browser_active_seconds += totals.browser_active_seconds
        previous.browser_idle_seconds += totals.browser_idle_seconds
        previous.other_seconds += totals.other_seconds
        previous.away_seconds += totals.away_seconds
        previous.audible_seconds += totals.audible_seconds
        previous.segments += totals.segments
        per_user_previous[row[0]] = {"email": row[1], "name": row[2], "totals": totals}

    # 3) Per-user comparison rows: union of both windows, sorted by email.
    merged: dict[UUID, dict] = {}
    for uid, info in per_user_previous.items():
        merged[uid] = {
            "email": info["email"],
            "name": info["name"],
            "current": PeriodTotals(),
            "previous": info["totals"],
        }
    for uid, info in per_user_current.items():
        entry = merged.setdefault(
            uid,
            {"email": info["email"], "name": info["name"],
             "current": PeriodTotals(), "previous": PeriodTotals()},
        )
        entry["current"] = info["totals"]
        entry["email"], entry["name"] = info["email"], info["name"]

    users = [
        UserTrendRow(
            user_id=uid,
            user_email=entry["email"],
            user_name=entry["name"],
            current=entry["current"],
            previous=entry["previous"],
            delta_pct=_pct(entry["current"].browser_active_seconds,
                           entry["previous"].browser_active_seconds),
        )
        for uid, entry in merged.items()
    ]
    users.sort(key=lambda u: u.user_email.lower())

    return TrendsOut(
        window_days=days,
        scope="team" if user_id is None else "user",
        user_id=user_id,
        current=current,
        previous=previous,
        deltas=TrendDeltas(
            browser_active_seconds=_pct(current.browser_active_seconds,
                                        previous.browser_active_seconds),
            browser_idle_seconds=_pct(current.browser_idle_seconds,
                                      previous.browser_idle_seconds),
            other_seconds=_pct(current.other_seconds, previous.other_seconds),
            away_seconds=_pct(current.away_seconds, previous.away_seconds),
        ),
        focus=_focus_metrics(segments_by_user, days),
        daily=[
            DaySummary(
                date=day,
                browser_active_seconds=t.browser_active_seconds,
                browser_idle_seconds=t.browser_idle_seconds,
                other_seconds=t.other_seconds,
                away_seconds=t.away_seconds,
                audible_seconds=t.audible_seconds,
            )
            for day, t in sorted(daily_map.items())
        ],
        users=users,
    )


# --------------------------- focus score (Phase 3) --------------------------
# One honest composite number per day: HOW FOCUSED browser time was, never
# how good the work was. Framing rules (product spec):
# - away time (no input at all — breaks, meetings, lunch) is excluded from
#   every component: it neither helps nor hurts;
# - the composite is always accompanied by its three weighted parts, so it is
#   never a black box, and a day with no focused-tab time scores None (the UI
#   shows "—"), never a fake 0;
# - scores are per person, with no team aggregate or ranking endpoint — they
#   are gamified for the employee, not usable against them.

FOCUS_SHARE_WEIGHT = 45       # pts: focused tab vs all keyboard-tracked time
FOCUS_CONTINUITY_WEIGHT = 30  # pts: average focus block vs the 25-min target
FOCUS_CALM_WEIGHT = 25        # pts: context switches vs the 12/day baseline
FOCUS_BLOCK_TARGET_SECONDS = 25 * 60
SWITCH_BASELINE_PER_DAY = 12


def _score_day(day: date, totals: PeriodTotals, focus: dict[str, int]) -> FocusDayRow:
    """Compose one day's score from its buckets + sequence metrics.

    - browser_idle counts against the share (a page left open is not focus);
    - keyboard-tracked time is tab active + tab idle + other-app active;
    - no focused-tab time at all → score None, components None.
    """
    tab_seconds = totals.browser_active_seconds + totals.browser_idle_seconds
    if tab_seconds <= 0:
        return FocusDayRow(
            date=day,
            browser_active_seconds=totals.browser_active_seconds,
            browser_idle_seconds=totals.browser_idle_seconds,
            other_seconds=totals.other_seconds,
            away_seconds=totals.away_seconds,
            focus_blocks=focus["focus_blocks"],
            context_switches=focus["context_switches"],
            longest_focus_seconds=focus["longest"],
        )

    keyboard_seconds = tab_seconds + totals.other_seconds
    share = totals.browser_active_seconds / max(keyboard_seconds, 1)
    avg_block = (
        focus["block_seconds"] / focus["focus_blocks"] if focus["focus_blocks"] else 0
    )
    continuity = min(avg_block / FOCUS_BLOCK_TARGET_SECONDS, 1.0)
    calm = 1.0 - min(focus["context_switches"] / SWITCH_BASELINE_PER_DAY, 1.0)

    return FocusDayRow(
        date=day,
        focus_score=round(
            share * FOCUS_SHARE_WEIGHT
            + continuity * FOCUS_CONTINUITY_WEIGHT
            + calm * FOCUS_CALM_WEIGHT
        ),
        components=FocusComponents(
            share_pct=round(share * 100),
            continuity_pct=round(continuity * 100),
            calm_pct=round(calm * 100),
        ),
        focus_seconds=focus["block_seconds"],
        browser_active_seconds=totals.browser_active_seconds,
        browser_idle_seconds=totals.browser_idle_seconds,
        other_seconds=totals.other_seconds,
        away_seconds=totals.away_seconds,
        focus_blocks=focus["focus_blocks"],
        context_switches=focus["context_switches"],
        longest_focus_seconds=focus["longest"],
    )


def focus_scores(session: Session, user_id: UUID, days: int) -> FocusOut:
    """Per-day focus scores for ONE person over the current window.

    Day grouping follows the module docstring (UTC dates); the score of a day
    uses only that day's own segments, so the sequence rules (_focus_for_user)
    never see across-midnight runs as one block.
    """
    days = max(1, min(days, MAX_DAYS))
    rows = session.exec(
        select(TimeSegment)
        .where(TimeSegment.user_id == user_id, TimeSegment.started_at >= window_start(days))
        .order_by(TimeSegment.started_at)
    ).all()

    by_day: dict[date, list[TimeSegment]] = {}
    for seg in rows:
        by_day.setdefault(seg.started_at.date(), []).append(seg)

    day_rows: list[FocusDayRow] = []
    for day, segs in sorted(by_day.items()):
        totals = PeriodTotals()
        for seg in segs:
            _add(totals, seg)
        day_rows.append(_score_day(day, totals, _focus_for_user(segs)))

    scored = [r.focus_score for r in day_rows if r.focus_score is not None]
    user = session.get(User, user_id)
    return FocusOut(
        window_days=days,
        user_id=user_id,
        user_email=user.email if user else "",
        user_name=user.full_name if user else "",
        # Mean over days WITH focused-tab time — untracked days are excluded,
        # never averaged in as zeros.
        average_score=round(sum(scored) / len(scored)) if scored else None,
        days=day_rows,
    )


# --------------------------- weekly digest (Phase 4) ------------------------
# One person's week on a page: browser-time totals, the focus rollup and the
# week's AI-usage counts in a single response. Same framing rules as the rest
# of the module — per-person only (a team digest would be the ranking the
# focus score deliberately avoids), durations are facts, never verdicts, and
# the AI part is counts + tool mix, never prompt text. Weeks are ISO weeks
# (Monday-start) and day grouping stays UTC, matching everything above.


def week_label(monday: date) -> str:
    """The Monday's ISO week label, e.g. '2026-W43'."""
    iso = monday.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def current_week_monday() -> date:
    today = utcnow().date()
    return today - timedelta(days=today.isoweekday() - 1)


def parse_week(label: str) -> date:
    """'2026-W43' → that ISO week's Monday.

    Raises ValueError for impossible labels (non-numeric, W00, or W53 of a
    52-week year) — the router converts it to a 422.
    """
    year_str, week_str = label.upper().split("-W")
    return date.fromisocalendar(int(year_str), int(week_str), 1)


def weekly_digest(session: Session, user_id: UUID, monday: date) -> DigestOut:
    """Everything one person's week needs, in one query set.

    The focus rollup reuses the Phase-3 day scorer (_score_day) on each day
    of the week, so the digest and the daily score can never disagree; the
    average follows the FocusOut rule (mean over scored days only).
    """
    start = datetime(monday.year, monday.month, monday.day)
    end = start + timedelta(days=7)

    segs = session.exec(
        select(TimeSegment)
        .where(
            TimeSegment.user_id == user_id,
            TimeSegment.started_at >= start,
            TimeSegment.started_at < end,
        )
        .order_by(TimeSegment.started_at)
    ).all()

    totals = PeriodTotals()
    by_day: dict[date, list[TimeSegment]] = {}
    for seg in segs:
        _add(totals, seg)
        by_day.setdefault(seg.started_at.date(), []).append(seg)

    day_rows: list[FocusDayRow] = []
    for day, day_segs in sorted(by_day.items()):
        day_totals = PeriodTotals()
        for seg in day_segs:
            _add(day_totals, seg)
        day_rows.append(_score_day(day, day_totals, _focus_for_user(day_segs)))

    scored = [(r.date, r.focus_score) for r in day_rows if r.focus_score is not None]
    best = max(scored, key=lambda pair: pair[1]) if scored else None

    # --- AI usage for the same week: counts + tool mix, never text ---
    ai_scope = (
        CapturedInteraction.user_id == user_id,
        CapturedInteraction.occurred_at >= start,
        CapturedInteraction.occurred_at < end,
    )
    counts = session.exec(
        select(
            func.count(),
            func.coalesce(
                func.sum(case((CapturedInteraction.is_flagged == True, 1), else_=0)), 0  # noqa: E712
            ),
            func.coalesce(
                func.sum(case((CapturedInteraction.was_blocked == True, 1), else_=0)), 0  # noqa: E712
            ),
        ).where(*ai_scope)
    ).one()
    tool_rows = session.exec(
        select(CapturedInteraction.ai_tool, func.count())
        .where(*ai_scope)
        .group_by(CapturedInteraction.ai_tool)
        .order_by(func.count().desc())
        .limit(5)
    ).all()

    user = session.get(User, user_id)
    return DigestOut(
        week=week_label(monday),
        week_start=monday,
        week_end=monday + timedelta(days=6),
        user_id=user_id,
        user_email=user.email if user else "",
        user_name=user.full_name if user else "",
        totals=totals,
        tracked_days=len(by_day),
        focus=DigestFocus(
            # Mean over days WITH focused-tab time (same rule as FocusOut).
            average_score=round(sum(s for _, s in scored) / len(scored)) if scored else None,
            days_scored=len(scored),
            best_day=best[0] if best else None,
            best_day_score=best[1] if best else None,
            focus_seconds=sum(r.focus_seconds for r in day_rows),
            focus_blocks=sum(r.focus_blocks for r in day_rows),
            context_switches=sum(r.context_switches for r in day_rows),
            longest_focus_seconds=max((r.longest_focus_seconds for r in day_rows), default=0),
        ),
        top_domains=_top_domains_between(session, user_id, start, end, limit=5),
        ai_usage=DigestAiUsage(
            interactions=int(counts[0]),
            flagged=int(counts[1]),
            blocked=int(counts[2]),
            by_tool=[KeyCount(key=k.value, label=k.value, count=c) for k, c in tool_rows],
        ),
        days=day_rows,
    )
