"""Tracking service — write Keke H5 analytics events to DB + app log.

Two outputs, one call:
  1. Row in `events` (queried later for funnels)
  2. Structured `EVENT=... DID=... FROM=... UA=... KEYWORD=... DUR=...`
     line in app.logger (matches the original SCF/CLS log shape so the
     pre-existing CLS queries from `文档/02-埋点事件清单.md` still work)

Side effect on `visit`: a row is upserted into `devices` so we can count
unique users without scanning the per-event table. The frontend's
localStorage flag is the primary de-dupe — DB lookup here is the
fallback for cleared caches.

Failures are logged and swallowed — analytics must never break the user-
facing request path. The caller still gets `None` so the blueprint can
continue.
"""

from __future__ import annotations

from flask import current_app

from app.extensions import db
from app.models import Device, Event
from app.repositories import device_repository, event_repository


def _truncate(value: str | None, max_len: int, default: str = "") -> str:
    if value is None:
        return default
    stripped = str(value).strip()[:max_len]
    return stripped or default


def _register_device_if_new(*, device_id: str, source: str, ua: str | None) -> None:
    """Insert a `devices` row the first time we see this device_id.

    Lookup-then-insert is good enough here: the frontend already filters
    repeat visits via localStorage, so we expect at most one race per
    cleared browser cache. A duplicate row in that edge case is
    cheaper than the operational overhead of a UNIQUE constraint.
    """
    try:
        if device_repository.find_by_device_id(device_id) is not None:
            return
        device_repository.add(Device(device_id=device_id, source=source, ua=ua))
        db.session.commit()
    except Exception:
        try:
            db.session.rollback()
        except Exception:  # noqa: BLE001
            pass
        current_app.logger.exception("device register failed did=%s", device_id)


def record(
    *,
    event_name: str,
    device_id: str,
    source: str = "unknown",
    ua: str | None = None,
    keyword: str | None = None,
    duration_ms: int | None = None,
) -> None:
    """Persist one analytics row and mirror it to the app logger.

    Swallows every exception. Returns nothing — callers should not branch
    on tracking success/failure.
    """
    did = _truncate(device_id, 64, "no_did")
    src = _truncate(source, 32, "unknown")
    ua_tag = _truncate(ua, 16, "") or None
    kw = _truncate(keyword, 40, "") or None

    try:
        row = Event(
            event_name=event_name,
            device_id=did,
            source=src,
            ua=ua_tag,
            keyword=kw,
            duration_ms=duration_ms,
        )
        event_repository.add(row)
        db.session.commit()
    except Exception:
        try:
            db.session.rollback()
        except Exception:  # noqa: BLE001
            pass
        current_app.logger.exception("tracking persist failed event=%s did=%s", event_name, did)

    if event_name == "visit" and did != "no_did":
        _register_device_if_new(device_id=did, source=src, ua=ua_tag)

    try:
        current_app.logger.info(
            "EVENT=%s DID=%s FROM=%s UA=%s KEYWORD=%s DUR=%s",
            event_name,
            did,
            src,
            ua_tag or "",
            kw or "",
            duration_ms if duration_ms is not None else "",
        )
    except Exception:  # noqa: BLE001
        pass
