"""HTTP boundary for formal Feishu login, sync, callbacks, and notifications."""

from __future__ import annotations

import json

from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue
from flask_jwt_extended import jwt_required

from app.common import BusinessException, Result, ResultCode
from app.schemas.feishu import (
    FeishuCallbackQuerySchema,
    FeishuExchangeSchema,
)
from app.security import current_user_id
from app.services import (
    feishu_approval_service,
    feishu_service,
    permission_service,
)

bp = Blueprint("feishu", __name__, url_prefix="/api/v1/feishu")

_callback_query_schema = FeishuCallbackQuerySchema()
_exchange_schema = FeishuExchangeSchema()


@bp.get("/login-url")
def login_url() -> dict:
    return Result.success({"authorize_url": feishu_service.authorize_url()}).to_dict()


@bp.post("/login/exchange")
def exchange() -> dict:
    payload = _exchange_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        feishu_service.login_by_code(
            payload["code"],
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string,
        )
    ).to_dict()


@bp.get("/callback")
def callback() -> dict:
    query = _callback_query_schema.load(request.args.to_dict())
    if "code" not in query:
        raise BusinessException(
            "飞书登录授权码缺失", result_code=ResultCode.BAD_REQUEST
        )
    return Result.success(feishu_service.exchange_code(query["code"])).to_dict()


def _callback_credentials(query: dict[str, str]) -> tuple[str, str, str]:
    """Feishu may send callback signature fields as headers or query params."""
    signature = (
        request.headers.get("X-Lark-Signature")
        or request.headers.get("X-Lark-Signatures")
        or query.get("signature")
        or ""
    )
    timestamp = (
        request.headers.get("X-Lark-Request-Timestamp") or query.get("timestamp") or ""
    )
    nonce = request.headers.get("X-Lark-Request-Nonce") or query.get("nonce") or ""
    return signature, timestamp, nonce


@bp.post("/webhook")
def webhook() -> ResponseReturnValue:
    query = _callback_query_schema.load(request.args.to_dict())
    body = request.get_data()
    signature, timestamp, nonce = _callback_credentials(query)
    try:
        envelope = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BusinessException("飞书回调内容无效") from error
    if not isinstance(envelope, dict):
        raise BusinessException("飞书回调内容无效")

    # A signature is always calculated over the original request body. The
    # Verification Token is then checked after decryption (or directly in the
    # plaintext payload), so either official security mechanism is supported.
    if signature:
        feishu_service.verify_callback_signature(
            signature=signature,
            timestamp=timestamp,
            nonce=nonce,
            body=body,
        )
    if isinstance(envelope.get("encrypt"), str):
        body = feishu_service.decrypt_callback(body)
        try:
            envelope = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise BusinessException("飞书回调内容无效") from error
        if not isinstance(envelope, dict):
            raise BusinessException("飞书回调内容无效")

    header = envelope.get("header")
    token = envelope.get("token")
    if isinstance(header, dict):
        token = header.get("token")
    feishu_service.verify_callback_token(str(token or ""), required=not bool(signature))

    try:
        event = feishu_service.parse_callback(body)
    except feishu_service.ChallengeRequired as challenge:
        return jsonify({"challenge": challenge.args[0]})
    result = feishu_approval_service.handle_event(event.event_id, event.payload)
    return Result.success({"event_id": event.event_id, **result}).to_dict()


@bp.post("/approvals/sync")
@jwt_required()
def sync_approvals() -> dict:
    permission_service.require_permission(current_user_id(), "asset:usage:manage")
    return Result.success(feishu_service.sync_approval_operations()).to_dict()


@bp.post("/organization/sync")
@jwt_required()
def sync_organizations() -> dict:
    permission_service.require_permission(current_user_id(), "organization:manage")
    return Result.success(feishu_service.sync_organization_tree()).to_dict()


@bp.post("/users/sync")
@jwt_required()
def sync_users() -> dict:
    permission_service.require_permission(current_user_id(), "user:manage")
    return Result.success(feishu_service.sync_users()).to_dict()


@bp.post("/sync")
@jwt_required()
def sync_all() -> dict:
    actor_id = current_user_id()
    permission_service.require_permission(actor_id, "organization:manage")
    permission_service.require_permission(actor_id, "user:manage")
    return Result.success(feishu_service.sync_all()).to_dict()
