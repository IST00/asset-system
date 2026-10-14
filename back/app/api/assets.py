"""Formal asset and audit read endpoints."""

from __future__ import annotations

from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from app.common import Result
from app.schemas import (
    BatchCompleteAssetDataRequestSchema,
    CompleteAssetDataRequestSchema,
)
from app.schemas.asset import AssetPageQuerySchema
from app.schemas.asset_scan import (
    AssetScanIntentLookupSchema,
    AssetScanLookupSchema,
    AssetUsageCandidateLookupSchema,
)
from app.security import current_user_id
from app.services import (
    asset_data_completion_service,
    asset_scan_service,
    asset_service,
)

bp = Blueprint("assets", __name__, url_prefix="/api/v1")

_page_schema = AssetPageQuerySchema()
_complete_data_schema = CompleteAssetDataRequestSchema()
_batch_complete_data_schema = BatchCompleteAssetDataRequestSchema()
_scan_lookup_schema = AssetScanLookupSchema()
_usage_candidate_schema = AssetUsageCandidateLookupSchema()
_scan_intent_schema = AssetScanIntentLookupSchema()


@bp.get("/assets")
@jwt_required()
def page() -> dict:
    query = _page_schema.load(request.args.to_dict())
    result = asset_service.page(
        actor_id=current_user_id(),
        page_index=query["page"],
        size=query["size"],
        keyword=query.get("keyword"),
        asset_code=query.get("asset_code"),
        asset_codes=query.get("asset_codes"),
        asset_name=query.get("asset_name"),
        serial_number=query.get("serial_number"),
        company_name=query.get("company_name"),
        category_name=query.get("category_name"),
        status=query.get("status"),
        department_name=query.get("department_name"),
        location_name=query.get("location_name"),
        user_name=query.get("user_name"),
        manager_name=query.get("manager_name"),
        supplier_name=query.get("supplier_name"),
        source_name=query.get("source_name"),
        purchase_date_from=query.get("purchase_date_from"),
        purchase_date_to=query.get("purchase_date_to"),
        data_completeness=query.get("data_completeness"),
    )
    return Result.success(result.to_dict()).to_dict()


@bp.get("/assets/dashboard")
@jwt_required()
def dashboard() -> dict:
    return Result.success(asset_service.dashboard(current_user_id())).to_dict()


@bp.get("/assets/scan-lookup")
@jwt_required()
def scan_lookup() -> dict:
    query = _scan_lookup_schema.load(request.args.to_dict())
    return Result.success(
        asset_scan_service.lookup(
            current_user_id(),
            asset_code=query.get("asset_code"),
            rfid_tag=query.get("rfid_tag"),
        )
    ).to_dict()


@bp.get("/assets/usage-candidate")
@jwt_required()
def usage_candidate() -> dict:
    query = _usage_candidate_schema.load(request.args.to_dict())
    return Result.success(
        asset_scan_service.usage_candidate(
            current_user_id(),
            asset_code=query.get("asset_code"),
            rfid_tag=query.get("rfid_tag"),
        )
    ).to_dict()


@bp.get("/assets/scan-intent")
@jwt_required()
def scan_intent() -> dict:
    query = _scan_intent_schema.load(request.args.to_dict())
    return Result.success(
        asset_scan_service.scan_intent(
            current_user_id(),
            asset_code=query.get("asset_code"),
            rfid_tag=query.get("rfid_tag"),
        )
    ).to_dict()


@bp.get("/assets/<int:asset_id>")
@jwt_required()
def detail(asset_id: int) -> dict:
    return Result.success(asset_service.get(asset_id, current_user_id())).to_dict()


@bp.post("/assets/<int:asset_id>/complete-data")
@jwt_required()
def complete_data(asset_id: int) -> dict:
    payload = _complete_data_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        asset_data_completion_service.complete_data(
            asset_id,
            payload,
            current_user_id(),
        )
    ).to_dict()


@bp.post("/assets/complete-data")
@jwt_required()
def complete_data_batch() -> dict:
    payload = _batch_complete_data_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        asset_data_completion_service.complete_data_batch(
            payload,
            current_user_id(),
        )
    ).to_dict()


@bp.get("/assets/<int:asset_id>/lifecycle")
@jwt_required()
def lifecycle(asset_id: int) -> dict:
    return Result.success(
        asset_service.lifecycle(asset_id, current_user_id())
    ).to_dict()


@bp.get("/assets/<int:asset_id>/related-records")
@jwt_required()
def related_records(asset_id: int) -> dict:
    return Result.success(
        asset_service.related_records(asset_id, current_user_id())
    ).to_dict()


@bp.get("/audit-logs")
@jwt_required()
def audit_logs() -> dict:
    return Result.success(asset_service.audit_logs(current_user_id())).to_dict()


__all__ = ["bp"]
