"""Standalone health-check Flask app.

Runs on a private port (default 8081, bind 127.0.0.1) in a daemon thread
started by gunicorn's `post_fork` hook. Provides:

- GET /health          — aggregate (all registered checks)
- GET /health/liveness — always 200 if the process is alive
- GET /health/readiness — all checks

Check registry
--------------
Checks are functions returning (name, ok, detail_dict). Register new ones
via `register_check(fn)` before `run_health_server()` is called. The default
set ships db + redis; disable via env `HEALTH_CHECKS=db,redis` narrowing.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from typing import Any

from flask import Flask, jsonify

log = logging.getLogger(__name__)

CheckFn = Callable[[], "CheckResult"]


class CheckResult:
    __slots__ = ("name", "ok", "detail")

    def __init__(self, name: str, ok: bool, detail: dict[str, Any] | None = None) -> None:
        self.name = name
        self.ok = ok
        self.detail = detail or {}

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, **self.detail}


_REGISTRY: dict[str, CheckFn] = {}


def register_check(name: str, fn: CheckFn) -> None:
    _REGISTRY[name] = fn


def _timed(name: str, work: Callable[[], dict[str, Any]]) -> CheckResult:
    start = time.monotonic()
    try:
        detail = work()
        ok = bool(detail.pop("ok", True))
        return CheckResult(
            name,
            ok,
            {"latency_ms": round((time.monotonic() - start) * 1000, 2), **detail},
        )
    except Exception as exc:  # noqa: BLE001 — health checks must never crash the probe
        log.warning("health: %s check failed: %s", name, exc)
        return CheckResult(
            name,
            False,
            {
                "latency_ms": round((time.monotonic() - start) * 1000, 2),
                "error": exc.__class__.__name__,
            },
        )


def _check_db() -> CheckResult:
    def _work() -> dict[str, Any]:
        from app.extensions import db

        db.session.execute(db.text("SELECT 1"))
        return {"ok": True}

    return _timed("db", _work)


def _check_redis() -> CheckResult:
    def _work() -> dict[str, Any]:
        import redis as _redis

        host = os.getenv("REDIS_HOST", "localhost")
        port = int(os.getenv("REDIS_PORT", "6379"))
        r = _redis.Redis(host=host, port=port, socket_connect_timeout=2)
        r.ping()
        return {"ok": True, "host": host, "port": port}

    return _timed("redis", _work)


def _enabled_checks() -> dict[str, CheckFn]:
    raw = os.getenv("HEALTH_CHECKS")
    if not raw:
        return dict(_REGISTRY)
    wanted = {s.strip() for s in raw.split(",") if s.strip()}
    return {k: v for k, v in _REGISTRY.items() if k in wanted}


def _run_checks() -> tuple[bool, dict[str, Any]]:
    results = {name: fn() for name, fn in _enabled_checks().items()}
    ok = all(r.ok for r in results.values())
    return ok, {name: r.to_dict() for name, r in results.items()}


def create_health_app() -> Flask:
    # Default registry — callers can replace entries by calling register_check() after import.
    _REGISTRY.setdefault("db", _check_db)
    _REGISTRY.setdefault("redis", _check_redis)

    health_app = Flask("health")

    @health_app.get("/health")
    def aggregate():
        ok, checks = _run_checks()
        return jsonify({"status": "UP" if ok else "DOWN", "checks": checks}), 200 if ok else 503

    @health_app.get("/health/liveness")
    def liveness():
        return jsonify({"status": "UP"}), 200

    @health_app.get("/health/readiness")
    def readiness():
        ok, checks = _run_checks()
        return jsonify({"status": "UP" if ok else "DOWN", "checks": checks}), 200 if ok else 503

    return health_app


def run_health_server() -> None:  # pragma: no cover
    port = int(os.getenv("HEALTH_PORT", "8081"))
    bind = os.getenv("HEALTH_BIND", "127.0.0.1")
    app = create_health_app()
    log.info("health server listening on %s:%s", bind, port)
    app.run(host=bind, port=port, use_reloader=False)


__all__ = [
    "create_health_app",
    "run_health_server",
    "register_check",
    "CheckResult",
]
