"""Spreadsheet import preview, confirmation, and report endpoints."""

from __future__ import annotations

from io import BytesIO

from flask import Blueprint, request, send_file
from flask_jwt_extended import jwt_required

from app.common import BusinessException, Result, ResultCode
from app.schemas.import_job import (
    ImportConfirmRequestSchema,
    ImportPageQuerySchema,
    ImportPreviewRequestSchema,
)
from app.security import current_user_id
from app.services import import_service

bp = Blueprint("imports", __name__, url_prefix="/api/v1/imports")

_preview_schema = ImportPreviewRequestSchema()
_confirm_schema = ImportConfirmRequestSchema()
_page_schema = ImportPageQuerySchema()


@bp.get("")
@jwt_required()
def list_jobs() -> dict:
    query = _page_schema.load(request.args)
    return import_service.page(query, current_user_id()).to_dict()


@bp.post("/preview")
@jwt_required()
def preview() -> dict:
    payload = _preview_schema.load(request.form)
    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        raise BusinessException("请选择导入文件", result_code=ResultCode.BAD_REQUEST)
    return Result.success(
        import_service.preview(
            payload["import_type"],
            uploaded.filename,
            uploaded.read(),
            current_user_id(),
        )
    ).to_dict()


@bp.get("/<int:job_id>")
@jwt_required()
def detail(job_id: int) -> dict:
    return Result.success(import_service.get(job_id, current_user_id())).to_dict()


@bp.post("/<int:job_id>/confirm")
@jwt_required()
def confirm(job_id: int) -> dict:
    payload = _confirm_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        import_service.confirm(job_id, payload["version"], current_user_id())
    ).to_dict()


@bp.get("/templates/<string:import_type>")
@jwt_required()
def template(import_type: str):
    content, filename = import_service.template(import_type.upper(), current_user_id())
    return send_file(
        BytesIO(content),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
    )


@bp.get("/master-data/<string:import_type>/export")
@jwt_required()
def export_master_data(import_type: str):
    content, filename = import_service.export_master_data(
        import_type.upper(), current_user_id()
    )
    return send_file(
        BytesIO(content),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
    )


@bp.get("/<int:job_id>/error-report")
@jwt_required()
def error_report(job_id: int):
    content, filename = import_service.error_report(job_id, current_user_id())
    return send_file(
        BytesIO(content),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
    )


__all__ = ["bp"]
