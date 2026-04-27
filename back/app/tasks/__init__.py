"""Celery tasks.

Celery is optional — the worker is only started when the user runs
`celery -A app.tasks.celery_app worker`. The business code can enqueue
via `app.tasks.celery_app.send_task("...")` if needed.
"""

from __future__ import annotations

from celery import Celery

from config import load_config

_config = load_config()

celery_app = Celery(
    "scaffold-python",
    broker=_config.CELERY_BROKER_URL,
    backend=_config.CELERY_RESULT_BACKEND,
)
celery_app.conf.update(task_track_started=True, timezone="UTC", enable_utc=True)


@celery_app.task(name="tasks.sample_add")
def sample_add(a: int, b: int) -> int:
    """Example task so the worker has something to execute."""
    return a + b
