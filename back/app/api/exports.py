"""Authenticated asset export and label download endpoints."""

from __future__ import annotations

from flask import Blueprint, request, send_file
from flask_jwt_extended import jwt_required

from app.common import Result
from app.schemas.export import ExportCreateSchema, ExportPageQuerySchema
from app.security import current_user_id
from app.services import export_service

bp = Blueprint("exports", __name__, url_prefix="/api/v1")
_create_schema = ExportCreateSchema()
_page_schema = ExportPageQuerySchema()


@bp.post("/exports")
@jwt_required()
def create_export() -> dict:
    payload = _create_schema.load(request.get_json(silent=True) or {})
    return Result.success(export_service.create(payload, current_user_id())).to_dict()


@bp.get("/exports")
@jwt_required()
def list_exports() -> dict:
    query = _page_schema.load(request.args.to_dict())
    return Result.success(
        export_service.page(
            actor_id=current_user_id(),
            page_index=query["page"],
            size=query["size"],
        ).to_dict()
    ).to_dict()


@bp.get("/exports/<int:export_id>/download")
@jwt_required()
def download_export(export_id: int):
    target = export_service.download_target(export_id, current_user_id())
    return send_file(
        target.path,
        mimetype=target.mime_type,
        as_attachment=True,
        download_name=target.original_name,
        conditional=True,
    )


__all__ = ["bp"]
