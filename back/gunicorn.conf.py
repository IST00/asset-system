"""Gunicorn configuration + post_fork hook that boots the health app thread.

The .env file (.env.dev / .env.prod, picked by FLASK_ENV) is loaded at
import time so the GUNICORN_* tunables below can be sourced from it too.
"""

from __future__ import annotations

import logging
import os
import threading

# Load .env.dev / .env.prod BEFORE reading GUNICORN_* tunables, so values
# in the file (e.g. GUNICORN_WORKERS=4 in .env.prod) take effect.
from config import bootstrap_env

bootstrap_env()

bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8080")
workers = int(os.getenv("GUNICORN_WORKERS", "2"))
threads = int(os.getenv("GUNICORN_THREADS", "4"))
timeout = int(os.getenv("GUNICORN_TIMEOUT", "60"))
worker_class = os.getenv("GUNICORN_WORKER_CLASS", "sync")
# accesslog / errorlog 默认走 stdout/stderr（"-"），可通过 env 指向具体文件；
# scripts/back-start.sh 会按 --log-file 自动注入。
accesslog = os.getenv("GUNICORN_ACCESS_LOG", "-")
errorlog = os.getenv("GUNICORN_ERROR_LOG", "-")
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
# Use URL path (U), never the full request line (r) or query string (q).
# Request headers and bodies are intentionally excluded as well.
access_log_format = "%(h)s %(m)s %(U)s %(s)s %(L)s"

_log = logging.getLogger("gunicorn.scaffold")


def post_fork(server, worker):  # type: ignore[no-untyped-def]
    """Boot the health-check Flask app once per worker, on a private port.

    Only the first worker starts the listener; others no-op to keep the
    bind exclusive.
    """
    if worker.age != 1:
        return
    try:
        from app.health import bind_business_app, run_health_server
        from wsgi import app as business_app

        # Let the health server borrow the business app context for DB checks.
        bind_business_app(business_app)

        t = threading.Thread(
            target=run_health_server,
            name="health-server",
            daemon=True,
        )
        t.start()
        _log.info("health server thread started (worker=%s)", worker.pid)
    except Exception as exc:  # pragma: no cover
        _log.warning("failed to start health server: %s", exc)
