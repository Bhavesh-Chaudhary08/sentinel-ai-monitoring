"""Time helpers.

All timestamps in this project are naive UTC (Postgres `timestamp` columns):
writing `datetime.now(timezone.utc)` into a timezone-less column makes psycopg
drop the offset anyway, and naive-UTC keeps Python-side comparisons safe.
"""

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Current UTC time as a naive datetime."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
