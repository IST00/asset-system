"""Configured asset label generation for printable QR / barcode stickers."""

from __future__ import annotations

from flask import Blueprint, request, send_file
from flask_jwt_extended import jwt_required

from app.schemas.export import AssetLabelQuerySchema, AssetLabelUrlQuerySchema
from app.security import current_user_id
from app.services import export_service

bp = Blueprint("asset_labels", __name__, url_prefix="/api/v1")
_label_ids_schema = AssetLabelQuerySchema()
_label_url_schema = AssetLabelUrlQuerySchema()


@bp.get("/asset-labels")
@jwt_required()
def preview_labels():
    query = _label_ids_schema.load(request.args.to_dict())
    url_query = _label_url_schema.load(request.args.to_dict())
    target = export_service.preview_labels(
        query["asset_ids"],
        current_user_id(),
        qr_base_url=url_query.get("base_url"),
    )
    return send_file(
        target.path,
        mimetype=target.mime_type,
        as_attachment=False,
        download_name=target.original_name,
        conditional=True,
    )


__all__ = ["bp"]
