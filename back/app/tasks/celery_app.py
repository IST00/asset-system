"""Celery application and beat schedule."""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from config import load_config

_config = load_config()

celery_app = Celery(
    "asset-system",
    broker=_config.CELERY_BROKER_URL,
    backend=_config.CELERY_RESULT_BACKEND,
    include=["app.tasks.feishu_contact_sync"],
)
celery_app.conf.update(
    task_track_started=True,
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "feishu-directory-sync": {
            "task": "tasks.feishu_sync_directory",
            "schedule": crontab(minute="*/15"),
            "options": {"expires": 900},
        }
    },
)
