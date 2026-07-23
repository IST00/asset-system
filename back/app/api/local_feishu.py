"""HTTP boundary for development-only FEISHU workflow simulation."""

from __future__ import annotations

from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from app.common import Result
from app.schemas.asset_usage_return import MockFeishuActionSchema
from app.security import current_user_id
from app.services import local_feishu_service

bp = Blueprint(
    "local_feishu_usage_return",
    __name__,
    url_prefix="/api/v1",
)

_action_schema = MockFeishuActionSchema()


@bp.post("/asset-usage-requests/<int:operation_request_id>/mock-feishu-action")
@jwt_required()
def act_on_usage(operation_request_id: int) -> dict:
    payload = _action_schema.load(request.get_json(silent=True) or {})
    data = local_feishu_service.act(
        operation_request_id,
        payload,
        current_user_id(),
    )
    return Result.success(data).to_dict()


@bp.post("/asset-return-requests/<int:operation_request_id>/mock-feishu-action")
@jwt_required()
def act_on_return(operation_request_id: int) -> dict:
    payload = _action_schema.load(request.get_json(silent=True) or {})
    data = local_feishu_service.act(
        operation_request_id,
        payload,
        current_user_id(),
    )
    return Result.success(data).to_dict()
