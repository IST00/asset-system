"""Tests for observability: traceId header round-trip + text log format aligned with Java."""

from __future__ import annotations

import io
import logging
import re

from app.observability import MdcFilter, _TEXT_FMT, _DATE_FMT  # type: ignore[attr-defined]


def test_trace_id_echoed_when_provided(client):
    resp = client.get("/api/hello", headers={"X-Request-ID": "fixed-trace-123"})
    assert resp.status_code == 200
    assert resp.headers.get("X-Request-ID") == "fixed-trace-123"


def test_trace_id_generated_when_absent(client):
    resp = client.get("/api/hello")
    assert resp.status_code == 200
    rid = resp.headers.get("X-Request-ID")
    assert rid is not None and len(rid) >= 16  # uuid4 hex


# Pattern to confirm "YYYY-MM-DD HH:MM:SS.mmm [thread] [traceId] LEVEL logger - msg"
_LOG_LINE_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3} "
    r"\[[^\]]+\] \[[^\]]+\] "
    r"[A-Z]{4,5}\s+\S.*? - .+$"
)


def test_log_format_matches_java_pattern(app, client):
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.addFilter(MdcFilter())
    handler.setFormatter(logging.Formatter(_TEXT_FMT, _DATE_FMT))
    logger = logging.getLogger("app.access")
    logger.addHandler(handler)
    try:
        client.get("/api/hello", headers={"X-Request-ID": "trace-abc"})
    finally:
        logger.removeHandler(handler)

    lines = [
        line_text for line_text in buf.getvalue().splitlines() if line_text.strip()
    ]
    assert lines, "expected access log output"
    line = lines[-1]
    assert _LOG_LINE_RE.match(line), f"log line does not match Java pattern: {line!r}"
    assert "[trace-abc]" in line
    assert "GET /api/hello" in line


def test_health_endpoints_use_check_registry():
    # Reset registry so create_health_app re-evaluates the gate.
    from app.health import _REGISTRY  # type: ignore[attr-defined]

    _REGISTRY.clear()

    from app.health import _run_checks, create_health_app, register_check

    create_health_app()

    called: list[str] = []

    def _fake():
        from app.health import CheckResult

        called.append("fake")
        return CheckResult("fake", ok=True, detail={"source": "unit-test"})

    register_check("fake", _fake)
    ok, checks = _run_checks()
    assert "fake" in checks
    assert called == ["fake"]
    assert checks["fake"]["ok"] is True
    assert checks["fake"]["source"] == "unit-test"
    # Built-in checks are wrapped by _timed() and must report latency_ms.
    assert "latency_ms" in checks["db"]
    assert isinstance(ok, bool)


def test_health_registry_only_contains_database_by_default():
    from app.health import _REGISTRY  # type: ignore[attr-defined]

    _REGISTRY.clear()

    from app.health import create_health_app

    create_health_app()
    assert set(_REGISTRY) == {"db"}


def test_health_registry_ignores_redis_environment(monkeypatch):
    monkeypatch.setenv("REDIS_HOST", "localhost")
    monkeypatch.setenv("REDIS_PORT", "6379")
    from app.health import _REGISTRY  # type: ignore[attr-defined]

    _REGISTRY.clear()

    from app.health import create_health_app

    create_health_app()
    assert set(_REGISTRY) == {"db"}
