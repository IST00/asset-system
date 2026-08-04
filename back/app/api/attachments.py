"""Authenticated asset attachment endpoints."""

from __future__ import annotations

from flask import Blueprint, request, send_file
from flask_jwt_extended import jwt_required

from app.common import BusinessException, Result, ResultCode
from app.schemas.attachment import (
    AttachmentCoverSchema,
    AttachmentUploadSchema,
    AttachmentVoidSchema,
)
from app.security import current_user_id
from app.services import attachment_service

bp = Blueprint("attachments", __name__, url_prefix="/api/v1")
_upload_schema = AttachmentUploadSchema()
_void_schema = AttachmentVoidSchema()
_cover_schema = AttachmentCoverSchema()


@bp.get("/assets/<int:asset_id>/attachments")
@jwt_required()
def list_attachments(asset_id: int) -> dict:
    return Result.success(
        attachment_service.list_for_asset(asset_id, current_user_id())
    ).to_dict()


@bp.post("/assets/<int:asset_id>/attachments")
@jwt_required()
def upload_attachment(asset_id: int) -> dict:
    payload = _upload_schema.load(request.form.to_dict())
    uploaded = request.files.get("file")
    if uploaded is None:
        raise BusinessException("请选择附件文件", result_code=ResultCode.BAD_REQUEST)
    return Result.success(
        attachment_service.upload(
            asset_id=asset_id,
            actor_id=current_user_id(),
            business_type=payload["business_type"],
            original_name=uploaded.filename or "file",
            mime_type=uploaded.mimetype or "application/octet-stream",
            content=uploaded.read(),
        )
    ).to_dict()


@bp.post("/attachments/<int:attachment_id>/void")
@jwt_required()
def void_attachment(attachment_id: int) -> dict:
    payload = _void_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        attachment_service.void(
            attachment_id,
            current_user_id(),
            version=payload["version"],
            reason=payload["reason"],
        )
    ).to_dict()


@bp.post("/attachments/<int:attachment_id>/cover")
@jwt_required()
def set_attachment_cover(attachment_id: int) -> dict:
    payload = _cover_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        attachment_service.set_cover(
            attachment_id, current_user_id(), version=payload["version"]
        )
    ).to_dict()


@bp.get("/attachments/<int:attachment_id>/download")
@jwt_required()
def download_attachment(attachment_id: int):
    target = attachment_service.download_target(attachment_id, current_user_id())
    return send_file(
        target.path,
        mimetype=target.mime_type,
        as_attachment=True,
        download_name=target.original_name,
        conditional=True,
    )


__all__ = ["bp"]
