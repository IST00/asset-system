"""Asset maintenance, relation, public-object and lifecycle endpoints."""

from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from app.common import Result
from app.schemas.asset_management import (
    BatchUpdateAssetRequestSchema,
    CreatePublicUsageObjectSchema,
    RelationRequestSchema,
    RepairCompleteSchema,
    RepairStartSchema,
    ScrapAssetsSchema,
    TransferAssetsSchema,
    UpdateAssetRequestSchema,
    UpdatePublicUsageObjectSchema,
)
from app.security import current_user_id
from app.services import asset_management_service

bp = Blueprint("asset_management", __name__, url_prefix="/api/v1")
_update_schema = UpdateAssetRequestSchema()
_batch_update_schema = BatchUpdateAssetRequestSchema()
_relation_schema = RelationRequestSchema()
_create_public_schema = CreatePublicUsageObjectSchema()
_update_public_schema = UpdatePublicUsageObjectSchema()
_transfer_schema = TransferAssetsSchema()
_repair_start_schema = RepairStartSchema()
_repair_complete_schema = RepairCompleteSchema()
_scrap_schema = ScrapAssetsSchema()


@bp.post("/assets/<int:asset_id>/update")
@jwt_required()
def update_asset(asset_id: int) -> dict:
    payload = _update_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        asset_management_service.update_one(asset_id, payload, current_user_id())
    ).to_dict()


@bp.post("/assets/batch-update")
@jwt_required()
def batch_update_assets() -> dict:
    payload = _batch_update_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        asset_management_service.update_batch(payload, current_user_id())
    ).to_dict()


@bp.get("/assets/<int:asset_id>/relations")
@jwt_required()
def asset_relations(asset_id: int) -> dict:
    return Result.success(
        asset_management_service.relation_tree(asset_id, current_user_id())
    ).to_dict()


@bp.post("/assets/<int:asset_id>/relations/attach")
@jwt_required()
def attach_assets(asset_id: int) -> dict:
    payload = _relation_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        asset_management_service.attach(asset_id, payload, current_user_id())
    ).to_dict()


@bp.post("/assets/<int:asset_id>/relations/detach")
@jwt_required()
def detach_assets(asset_id: int) -> dict:
    payload = _relation_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        asset_management_service.detach(asset_id, payload, current_user_id())
    ).to_dict()


@bp.get("/public-usage-objects")
@jwt_required()
def public_objects() -> dict:
    include_disabled = request.args.get("include_disabled", "false").lower() == "true"
    return Result.success(
        asset_management_service.list_public_objects(
            current_user_id(), include_disabled
        )
    ).to_dict()


@bp.post("/public-usage-objects")
@jwt_required()
def create_public_object() -> dict:
    payload = _create_public_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        asset_management_service.create_public_object(payload, current_user_id())
    ).to_dict()


@bp.post("/public-usage-objects/<int:object_id>/update")
@jwt_required()
def update_public_object(object_id: int) -> dict:
    payload = _update_public_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        asset_management_service.update_public_object(
            object_id, payload, current_user_id()
        )
    ).to_dict()


@bp.post("/asset-actions/transfer")
@jwt_required()
def transfer_assets() -> dict:
    payload = _transfer_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        asset_management_service.transfer(payload, current_user_id())
    ).to_dict()


@bp.post("/asset-actions/repair/start")
@jwt_required()
def start_repair() -> dict:
    payload = _repair_start_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        asset_management_service.repair_start(payload, current_user_id())
    ).to_dict()


@bp.post("/asset-actions/repair/complete")
@jwt_required()
def complete_repair() -> dict:
    payload = _repair_complete_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        asset_management_service.repair_complete(payload, current_user_id())
    ).to_dict()


@bp.post("/asset-actions/scrap")
@jwt_required()
def scrap_assets() -> dict:
    payload = _scrap_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        asset_management_service.scrap(payload, current_user_id())
    ).to_dict()


__all__ = ["bp"]
