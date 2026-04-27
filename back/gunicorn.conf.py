"""Gunicorn configuration + post_fork hook that boots the health app thread."""

from __future__ import annotations

import logging
import os
import threading

bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8080")
workers = int(os.getenv("GUNICORN_WORKERS", "2"))
threads = int(os.getenv("GUNICORN_THREADS", "4"))
timeout = int(os.getenv("GUNICORN_TIMEOUT", "60"))
worker_class = os.getenv("GUNICORN_WORKER_CLASS", "sync")
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")

_log = logging.getLogger("gunicorn.scaffold")


def post_fork(server, worker):  # type: ignore[no-untyped-def]
    """Boot the health-check Flask app once per worker, on a private port.

    Only the first worker starts the listener; others no-op to keep the
    bind exclusive.
    """
    if worker.age != 1:
        return
    try:
        from app.health import run_health_server

        t = threading.Thread(
            target=run_health_server,
            name="health-server",
            daemon=True,
        )
        t.start()
        _log.info("health server thread started (worker=%s)", worker.pid)
    except Exception as exc:  # pragma: no cover
        _log.warning("failed to start health server: %s", exc)
