"""Celery tasks.

The worker/beat entry point is ``app.tasks.celery_app``. The explicit task import registers task names when this package is loaded
by the worker; web code should not import task functions.
"""

from __future__ import annotations

from app.tasks.celery_app import celery_app
from app.tasks.feishu_contact_sync import feishu_sync_directory

del feishu_sync_directory

__all__ = ["celery_app"]
