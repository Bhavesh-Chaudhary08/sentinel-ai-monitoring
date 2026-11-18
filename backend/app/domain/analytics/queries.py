"""Aggregations for the admin dashboard (SQL for usage, Python for shadow AI)."""

from datetime import timedelta
from uuid import UUID

from sqlalchemy import Integer, case, func
from sqlmodel import Session, select

from app.core.time import utcnow
from app.domain.capture.shadow import normalize_domain
from app.models.interaction import CapturedInteraction
from app.models.user import User
from app.schemas.analytics import (
    DayBucket,
    KeyCount,
    ShadowDomainOut,
    UsageOut,
    UsageTotals,
)


def _flagged_expr():
    return case((CapturedInteraction.is_flagged == True, 1), else_=0)  # noqa: E712


def _blocked_expr():
    return case((CapturedInteraction.was_blocked == True, 1), else_=0)  # noqa: E712


def usage_summary(session: Session, days: int = 30, user_id: UUID | None = None) -> UsageOut:
    since = utcnow() - timedelta(days=days)
    scope = [CapturedInteraction.occurred_at >= since]
    if user_id is not None:
        scope.append(CapturedInteraction.user_id == user_id)

    # --- totals ---
    totals_row = session.exec(
        select(
            func.count(),
            func.coalesce(func.sum(_flagged_expr()), 0),
            func.coalesce(func.sum(_blocked_expr()), 0),
            func.count(func.distinct(CapturedInteraction.user_id)),
        ).where(*scope)
    ).one()

    shadow_q = [CapturedInteraction.occurred_at >= since,
                CapturedInteraction.is_known_platform == False]  # noqa: E712
    if user_id is not None:
        shadow_q.append(CapturedInteraction.user_id == user_id)
    shadow_count = session.exec(
        select(func.count(func.distinct(CapturedInteraction.domain))).where(*shadow_q)
    ).one()

    # --- by day ---
    day_rows = session.exec(
        select(
            func.date(CapturedInteraction.occurred_at).label("d"),
            func.count(),
            func.coalesce(func.sum(_flagged_expr()), 0),
            func.coalesce(func.sum(_blocked_expr()), 0),
        )
        .where(*scope)
        .group_by("d")
        .order_by("d")
    ).all()
    by_day = [
        DayBucket(date=str(row[0]), total=row[1], flagged=int(row[2]), blocked=int(row[3]))
        for row in day_rows
    ]

    # --- by tool / category ---
    tool_rows = session.exec(
        select(CapturedInteraction.ai_tool, func.count())
        .where(*scope)
        .group_by(CapturedInteraction.ai_tool)
        .order_by(func.count().desc())
    ).all()
    by_tool = [KeyCount(key=key.value, label=key.value, count=count) for key, count in tool_rows]

    cat_rows = session.exec(
        select(CapturedInteraction.risk_category, func.count())
        .where(*scope)
        .group_by(CapturedInteraction.risk_category)
        .order_by(func.count().desc())
    ).all()
    by_category = [KeyCount(key=key.value, label=key.value, count=count) for key, count in cat_rows]

    # --- top users (joined with email for display) ---
    # The JOIN must be explicit: selecting User.email without it would
    # cross-join every interaction with every user, duplicating rows.
    top_rows = session.exec(
        select(CapturedInteraction.user_id, User.email, func.count())
        .join(User, CapturedInteraction.user_id == User.id)
        .where(*scope)
        .group_by(CapturedInteraction.user_id, User.email)
        .order_by(func.count().desc())
        .limit(5)
    ).all()
    top_users = [
        KeyCount(key=str(uid), label=email, count=count) for uid, email, count in top_rows
    ]

    return UsageOut(
        days=days,
        totals=UsageTotals(
            interactions=int(totals_row[0]),
            flagged=int(totals_row[1]),
            blocked=int(totals_row[2]),
            shadow_domains=int(shadow_count),
            active_users=int(totals_row[3]),
        ),
        by_day=by_day,
        by_tool=by_tool,
        by_category=by_category,
        top_users=top_users,
    )


_RISK_ORDER = {"low": 0, "unknown": 1, "medium": 2, "high": 3, None: -1}


def shadow_ai_domains(session: Session, limit: int = 100) -> list[ShadowDomainOut]:
    """Unrecognized AI domains, aggregated per domain (first/last seen, risk)."""
    rows = session.exec(
        select(CapturedInteraction)
        .where(CapturedInteraction.is_known_platform == False)  # noqa: E712
        .order_by(CapturedInteraction.occurred_at.desc())
        .limit(2000)
    ).all()

    agg: dict[str, dict] = {}
    for row in rows:
        domain = normalize_domain(row.domain)
        entry = agg.setdefault(
            domain,
            {
                "first_seen": row.occurred_at,
                "last_seen": row.occurred_at,
                "interactions": 0,
                "users": set(),
                "risk": None,
                "known": row.is_known_platform,
            },
        )
        entry["first_seen"] = min(entry["first_seen"], row.occurred_at)
        entry["last_seen"] = max(entry["last_seen"], row.occurred_at)
        entry["interactions"] += 1
        entry["users"].add(row.user_id)
        risk_value = row.shadow_risk.value if row.shadow_risk else None
        current = entry["risk"].value if entry["risk"] else None
        if _RISK_ORDER.get(risk_value, -1) > _RISK_ORDER.get(current, -1):
            entry["risk"] = row.shadow_risk

    out = [
        ShadowDomainOut(
            domain=domain,
            first_seen=data["first_seen"],
            last_seen=data["last_seen"],
            interactions=data["interactions"],
            users=len(data["users"]),
            risk=data["risk"],
            is_known_platform=data["known"],
        )
        for domain, data in agg.items()
    ]
    out.sort(key=lambda item: item.first_seen, reverse=True)
    return out[:limit]
