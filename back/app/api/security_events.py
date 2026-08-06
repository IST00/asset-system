"""Security event audit endpoints."""

from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from app.common import Result
from app.schemas.security import SecurityEventPageQuerySchema
from app.security import current_user_id
from app.services import security_service

bp = Blueprint("security_events", __name__, url_prefix="/api/v1/security-events")

_page_schema = SecurityEventPageQuerySchema()


@bp.get("")
@jwt_required()
def page() -> dict:
    query = _page_schema.load(request.args.to_dict())
    return Result.success(
        security_service.list_events(
            actor_id=current_user_id(),
            page=query["page"],
            size=query["size"],
            event_type=query.get("event_type"),
            keyword=query.get("keyword"),
        )
    ).to_dict()


__all__ = ["bp"]
