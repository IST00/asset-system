"""Observability: traceId injection + file/console logging aligned with Java.

Log format contract
-------------------
Matches the Java side's `logback-quick-include.xml` pattern:

    %d{yyyy-MM-dd HH:mm:ss.SSS} [%thread] [%X{traceId:-}] %-5level %logger{36} - %msg%n

- Timestamp with millis, local time (matches logback default).
- Thread name (Python: threading.current_thread().name, typically "MainThread"
  for the Flask dev server, "Thread-N" in gunicorn workers).
- traceId comes from the inbound `X-Request-ID` header or a freshly minted
  uuid4 hex. Absent context renders as `-` (same sentinel as Java's
  `traceId:-` default).
- Logger name is the Python module logger, truncated to 36 chars from the
  left to keep alignment with %logger{36}.

File output
-----------
Rolling file appender mirrors Java:
  - Current file:  ${LOG_PATH}/${LOG_FILE_BASENAME}.log   (default logs/back.log)
  - Archive:       ${LOG_PATH}/${LOG_FILE_BASENAME}.%Y-%m-%d.%i.log.gz
  - Rotation: size (LOG_MAX_FILE_SIZE, default 50MB) + daily, keep 30 files.

Env knobs (aligned with Java -D properties):
  LOG_FILE            absolute path to current log file  (Java: -DLOG_FILE)
  LOG_PATH            directory if LOG_FILE unset        (Java: -DLOG_PATH)
  LOG_FILE_BASENAME   defaults to 'back'                 (Java: QUICK_LOG_ARCHIVE_BASENAME)
  LOG_MAX_FILE_SIZE   default 50MB                       (Java: QUICK_LOG_MAX_FILE_SIZE)
  LOG_MAX_HISTORY     default 30 archives                (Java: QUICK_LOG_MAX_HISTORY)
  LOG_LEVEL           default INFO                       (Java: QUICK_LOG_ROOT_LEVEL)
  LOG_CONSOLE         'true' (default) to keep stdout appender
  LOG_FILE_ENABLED    'true' (default) to enable file appender; set 'false'
                      for local dev if you prefer console-only.
"""

from __future__ import annotations

import gzip
import logging
import os
import re
import shutil
import sys
import threading
import time
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from flask import Flask, Response, g, request

REQUEST_ID_HEADER = "X-Request-ID"
_UNSET = "-"

# -- MDC equivalent --------------------------------------------------------
# flask.g covers in-request scope. For logging outside request scope
# (startup, Celery, CLI) we fall back to a thread-local so logs still have
# a traceId slot.
_thread_local = threading.local()


def _current_trace_id() -> str:
    try:
        return getattr(g, "trace_id", None) or _UNSET
    except RuntimeError:
        return getattr(_thread_local, "trace_id", _UNSET)


class MdcFilter(logging.Filter):
    """Attach traceId (and convenience fields) to every LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.traceId = _current_trace_id()
        record.thread_name = threading.current_thread().name
        # Shorten logger name to the last 36 chars for alignment parity.
        name = record.name
        record.logger36 = name if len(name) <= 36 else name[-36:]
        return True


# Matches Java pattern exactly. %(msecs)03d gives zero-padded millis.
_TEXT_FMT = (
    "%(asctime)s.%(msecs)03d [%(thread_name)s] [%(traceId)s] "
    "%(levelname)-5s %(logger36)-36s - %(message)s"
)
_DATE_FMT = "%Y-%m-%d %H:%M:%S"


# -- Rotating file handler with gzip-on-rollover --------------------------
def _parse_size(raw: str) -> int:
    """Parse sizes like '50MB', '1GB', '500KB' — matches logback tokens."""
    m = re.fullmatch(r"\s*(\d+)\s*([KMG]?B)?\s*", raw.upper())
    if not m:
        raise ValueError(f"invalid size: {raw!r}")
    n = int(m.group(1))
    unit = m.group(2) or "B"
    return n * {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}[unit]


class GzipRotatingFileHandler(RotatingFileHandler):
    """RotatingFileHandler that gzips rolled-over files.

    Naming matches Java: ``<base>.YYYY-MM-DD.<i>.log.gz`` in the same dir.
    We do day+size combined rotation by encoding the date into the rollover
    filename (checked on every rollover).
    """

    def __init__(
        self, filename: str, max_bytes: int, backup_count: int, basename: str
    ) -> None:
        super().__init__(
            filename=filename,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
            delay=False,
        )
        self.basename = basename

    def rotation_filename(self, default_name: str) -> str:
        # default_name is '<file>.1', '<file>.2' ...
        idx = default_name.rsplit(".", 1)[-1]
        day = time.strftime("%Y-%m-%d")
        parent = Path(self.baseFilename).parent
        return str(parent / f"{self.basename}.{day}.{idx}.log.gz")

    def rotate(self, source: str, dest: str) -> None:
        # source = self.baseFilename, dest = result of rotation_filename(...)
        if not os.path.exists(source):
            return
        with open(source, "rb") as fi, gzip.open(dest, "wb") as fo:
            shutil.copyfileobj(fi, fo)
        os.remove(source)


def _resolve_log_file() -> tuple[Path, str]:
    """Return (current_file_path, basename) matching Java resolver rules."""
    basename = os.getenv("LOG_FILE_BASENAME", "back")
    log_file_env = os.getenv("LOG_FILE")
    if log_file_env:
        path = Path(log_file_env).expanduser().resolve()
        return path, path.stem
    log_path_env = os.getenv("LOG_PATH", "logs")
    path = Path(log_path_env).expanduser().resolve() / f"{basename}.log"
    return path, basename


def _build_handlers(app: Flask) -> list[logging.Handler]:
    handlers: list[logging.Handler] = []

    want_console = os.getenv("LOG_CONSOLE", "true").lower() in {"1", "true", "yes"}
    if want_console:
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(logging.Formatter(_TEXT_FMT, _DATE_FMT))
        ch.addFilter(MdcFilter())
        handlers.append(ch)

    want_file = os.getenv(
        "LOG_FILE_ENABLED",
        "false" if app.testing else "true",
    ).lower() in {"1", "true", "yes"}
    if want_file:
        file_path, basename = _resolve_log_file()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        max_bytes = _parse_size(os.getenv("LOG_MAX_FILE_SIZE", "50MB"))
        backup = int(os.getenv("LOG_MAX_HISTORY", "30"))
        fh = GzipRotatingFileHandler(
            filename=str(file_path),
            max_bytes=max_bytes,
            backup_count=backup,
            basename=basename,
        )
        fh.setFormatter(logging.Formatter(_TEXT_FMT, _DATE_FMT))
        fh.addFilter(MdcFilter())
        handlers.append(fh)

    return handlers


def _configure_root_logger(app: Flask) -> None:
    level = os.getenv("LOG_LEVEL", "INFO" if not app.debug else "DEBUG").upper()
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    for h in _build_handlers(app):
        root.addHandler(h)
    root.setLevel(getattr(logging, level, logging.INFO))


def init_observability(app: Flask) -> None:
    """Wire traceId injection + text-format logging (Java-aligned) into Flask.

    Call before register_error_handlers so exception logs carry traceId.
    """
    _configure_root_logger(app)
    access_log = logging.getLogger("app.access")

    @app.before_request
    def _assign_trace_id() -> None:
        incoming = request.headers.get(REQUEST_ID_HEADER)
        g.trace_id = incoming if incoming else uuid.uuid4().hex
        _thread_local.trace_id = g.trace_id
        g._request_started = time.monotonic()

    @app.after_request
    def _emit_access_log(resp: Response) -> Response:
        resp.headers[REQUEST_ID_HEADER] = getattr(g, "trace_id", _UNSET)
        started = getattr(g, "_request_started", None)
        duration_ms = (time.monotonic() - started) * 1000.0 if started else -1.0
        if not request.path.startswith("/health"):
            access_log.info(
                "%s %s -> %d (%.2fms) from %s",
                request.method,
                request.path,
                resp.status_code,
                duration_ms,
                request.remote_addr or _UNSET,
            )
        return resp

    @app.teardown_request
    def _clear_thread_local(_exc: BaseException | None) -> None:
        _thread_local.trace_id = _UNSET


def current_request_id() -> str | None:
    """Return the active request id for response envelopes."""
    value = _current_trace_id()
    return None if value == _UNSET else value


def set_trace_id(trace_id: str) -> None:
    """Set traceId outside a request context (Celery tasks, CLI jobs)."""
    _thread_local.trace_id = trace_id or _UNSET


__all__: list[str] = [
    "current_request_id",
    "init_observability",
    "set_trace_id",
    "REQUEST_ID_HEADER",
    "MdcFilter",
    "GzipRotatingFileHandler",
]


# -- back-compat shim ------------------------------------------------------
# Older tests imported JsonFormatter / RequestContextFilter from this module.
# Keep those names resolvable but wired to the Java-aligned text path.
RequestContextFilter = MdcFilter


def JsonFormatter(*_a: Any, **_kw: Any) -> logging.Formatter:  # noqa: N802 — legacy API
    """Deprecated: Java side uses text format. Returns the text formatter."""
    return logging.Formatter(_TEXT_FMT, _DATE_FMT)
