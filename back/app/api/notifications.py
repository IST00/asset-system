"""Persistent in-product notification endpoints."""

from __future__ import annotations

from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from app.common import Result
from app.schemas.notifications import NotificationPageQuerySchema
from app.security import current_user_id
from app.services import notification_service

bp = Blueprint("notifications", __name__, url_prefix="/api/v1/notifications")
_query_schema = NotificationPageQuerySchema()


@bp.get("")
@jwt_required()
def page() -> dict:
    query = _query_schema.load(request.args.to_dict())
    return Result.success(
        notification_service.page(
            current_user_id(), query["page"], query["size"], query["unread_only"]
        ).to_dict()
    ).to_dict()


@bp.get("/unread-count")
@jwt_required()
def unread_count() -> dict:
    return Result.success(
        notification_service.unread_count(current_user_id())
    ).to_dict()


@bp.post("/<int:notification_id>/read")
@jwt_required()
def mark_read(notification_id: int) -> dict:
    return Result.success(
        notification_service.mark_read(notification_id, current_user_id())
    ).to_dict()


@bp.post("/read-all")
@jwt_required()
def mark_all_read() -> dict:
    return Result.success(
        notification_service.mark_all_read(current_user_id())
    ).to_dict()
