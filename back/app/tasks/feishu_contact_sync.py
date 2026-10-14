"""Scheduled Feishu directory synchronization tasks."""

from __future__ import annotations

import logging

from flask import current_app, has_app_context

from app import create_app
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.feishu_sync_directory")
def feishu_sync_directory() -> dict[str, int | str]:
    """Synchronize Feishu contacts in the worker's Flask application context."""
    if has_app_context():
        app = current_app
    else:
        app = create_app()
    with app.app_context():
        return _run_sync()


def _run_sync() -> dict[str, int | str]:
    from app.services import feishu_service

    settings = current_app.config
    if not (
        settings.get("FEISHU_INTEGRATION_ENABLED")
        and settings.get("FEISHU_APP_ID")
        and settings.get("FEISHU_APP_SECRET")
        and settings.get("FEISHU_DIRECTORY_SYNC_ENABLED")
    ):
        return {"skipped": "disabled"}
    try:
        result = feishu_service.sync_all()
    except Exception:
        logger.exception("scheduled Feishu directory synchronization failed")
        raise
    logger.info(
        "scheduled Feishu directory synchronization finished: %s",
        result,
    )
    return dict(result)
