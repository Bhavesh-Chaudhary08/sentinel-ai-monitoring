"""Celery application: broker/backend on Redis + beat schedule.

Privacy note: Redis runs with AOF and RDB persistence disabled in
docker-compose, so prompt text that transits the queue is never written to
disk on the broker — it either gets consumed or dies with the container.
"""

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "aidlp",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # At-least-once delivery: if a worker dies mid-classification the task is
    # redelivered instead of silently losing the DLP decision.
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    broker_transport_options={"visibility_timeout": 300},
    beat_schedule={
        # Remove raw prompt/response text from flagged rows once retention expires.
        "retention.purge_expired_content": {
            "task": "retention.purge_expired_content",
            "schedule": 3600.0,  # hourly
        },
        # Surface classification rows orphaned by a broker/worker outage.
        "capture.mark_stale_pending": {
            "task": "capture.mark_stale_pending",
            "schedule": 600.0,  # every 10 min
        },
    },
)
