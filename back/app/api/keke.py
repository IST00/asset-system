"""Keke (呼噜与可可) H5 endpoints — public, no JWT required.

Two POST routes per CLAUDE.md §11 (GET/POST only):
- POST /api/keke/track            single analytics event (visit / save_*)
- POST /api/keke/story/generate   create a bedtime story via DeepSeek
"""

from __future__ import annotations

from flask import Blueprint, request

from app.common import Result
from app.schemas import GenerateStoryRequestSchema, TrackingEventRequestSchema
from app.services import story_service, tracking_service

bp = Blueprint("keke", __name__, url_prefix="/api/keke")

_track_schema = TrackingEventRequestSchema()
_generate_schema = GenerateStoryRequestSchema()


@bp.post("/track")
def track() -> dict:
    payload = _track_schema.load(request.get_json(silent=True) or {})
    tracking_service.record(
        event_name=payload["event"],
        device_id=payload["device_id"],
        source=payload.get("from_", "unknown"),
        ua=payload.get("ua"),
        keyword=payload.get("keyword"),
        duration_ms=payload.get("duration_ms"),
    )
    return Result.success().to_dict()


@bp.post("/story/generate")
def generate_story() -> dict:
    payload = _generate_schema.load(request.get_json(silent=True) or {})

    # Implicit generate_start mirrors the original SCF behaviour: the
    # request itself counts as the start event, no separate /track call.
    tracking_service.record(
        event_name="generate_start",
        device_id=payload["device_id"],
        source=payload.get("from_", "unknown"),
        ua=payload.get("ua"),
        keyword=payload["keyword"],
    )

    result = story_service.generate(keyword=payload["keyword"])
    return Result.success(result).to_dict()
