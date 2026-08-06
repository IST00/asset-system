"""Asset master-data endpoints."""

from __future__ import annotations

from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from app.common import Result
from app.schemas.master_data import (
    CreateAssetCategoryRequestSchema,
    CreateLocationRequestSchema,
    CreateReferenceDataRequestSchema,
    DeleteMasterDataRequestSchema,
    UpdateAssetCategoryRequestSchema,
    UpdateLocationRequestSchema,
    UpdateReferenceDataRequestSchema,
)
from app.security import current_user_id
from app.services import master_data_service

bp = Blueprint("master_data", __name__, url_prefix="/api/v1")

_reference_schema = CreateReferenceDataRequestSchema()
_location_schema = CreateLocationRequestSchema()
_category_schema = CreateAssetCategoryRequestSchema()
_delete_master_data_schema = DeleteMasterDataRequestSchema()
_update_reference_schema = UpdateReferenceDataRequestSchema()
_update_location_schema = UpdateLocationRequestSchema()
_update_category_schema = UpdateAssetCategoryRequestSchema()


@bp.get("/units")
@jwt_required()
def list_units() -> dict:
    return Result.success(master_data_service.list_units(current_user_id())).to_dict()


@bp.post("/units")
@jwt_required()
def create_unit() -> dict:
    payload = _reference_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        master_data_service.create_unit(payload, current_user_id())
    ).to_dict()


@bp.post("/units/<int:unit_id>/update")
@jwt_required()
def update_unit(unit_id: int) -> dict:
    payload = _update_reference_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        master_data_service.update_unit(unit_id, payload, current_user_id())
    ).to_dict()


@bp.post("/units/<int:unit_id>/disable")
@jwt_required()
def disable_unit(unit_id: int) -> dict:
    return Result.success(
        master_data_service.set_unit_enabled(unit_id, False, current_user_id())
    ).to_dict()


@bp.post("/units/<int:unit_id>/enable")
@jwt_required()
def enable_unit(unit_id: int) -> dict:
    return Result.success(
        master_data_service.set_unit_enabled(unit_id, True, current_user_id())
    ).to_dict()


@bp.get("/asset-sources")
@jwt_required()
def list_sources() -> dict:
    return Result.success(master_data_service.list_sources(current_user_id())).to_dict()


@bp.post("/asset-sources")
@jwt_required()
def create_source() -> dict:
    payload = _reference_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        master_data_service.create_source(payload, current_user_id())
    ).to_dict()


@bp.post("/asset-sources/<int:source_id>/update")
@jwt_required()
def update_source(source_id: int) -> dict:
    payload = _update_reference_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        master_data_service.update_source(source_id, payload, current_user_id())
    ).to_dict()


@bp.post("/asset-sources/<int:source_id>/disable")
@jwt_required()
def disable_source(source_id: int) -> dict:
    return Result.success(
        master_data_service.set_source_enabled(source_id, False, current_user_id())
    ).to_dict()


@bp.post("/asset-sources/<int:source_id>/enable")
@jwt_required()
def enable_source(source_id: int) -> dict:
    return Result.success(
        master_data_service.set_source_enabled(source_id, True, current_user_id())
    ).to_dict()


@bp.get("/locations/tree")
@jwt_required()
def location_tree() -> dict:
    return Result.success(
        master_data_service.location_tree(current_user_id())
    ).to_dict()


@bp.post("/locations")
@jwt_required()
def create_location() -> dict:
    payload = _location_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        master_data_service.create_location(payload, current_user_id())
    ).to_dict()


@bp.get("/locations/<int:location_id>/delete-impact")
@jwt_required()
def location_delete_impact(location_id: int) -> dict:
    return Result.success(
        master_data_service.location_delete_impact(location_id, current_user_id())
    ).to_dict()


@bp.post("/locations/<int:location_id>/delete")
@jwt_required()
def delete_location(location_id: int) -> dict:
    payload = _delete_master_data_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        master_data_service.delete_location(location_id, payload, current_user_id())
    ).to_dict()


@bp.post("/locations/<int:location_id>/update")
@jwt_required()
def update_location(location_id: int) -> dict:
    payload = _update_location_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        master_data_service.update_location(location_id, payload, current_user_id())
    ).to_dict()


@bp.post("/locations/<int:location_id>/disable")
@jwt_required()
def disable_location(location_id: int) -> dict:
    return Result.success(
        master_data_service.set_location_enabled(location_id, False, current_user_id())
    ).to_dict()


@bp.post("/locations/<int:location_id>/enable")
@jwt_required()
def enable_location(location_id: int) -> dict:
    return Result.success(
        master_data_service.set_location_enabled(location_id, True, current_user_id())
    ).to_dict()


@bp.get("/asset-categories/tree")
@jwt_required()
def category_tree() -> dict:
    return Result.success(
        master_data_service.category_tree(current_user_id())
    ).to_dict()


@bp.post("/asset-categories")
@jwt_required()
def create_category() -> dict:
    payload = _category_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        master_data_service.create_category(payload, current_user_id())
    ).to_dict()


@bp.get("/asset-categories/<int:category_id>/delete-impact")
@jwt_required()
def category_delete_impact(category_id: int) -> dict:
    return Result.success(
        master_data_service.category_delete_impact(category_id, current_user_id())
    ).to_dict()


@bp.post("/asset-categories/<int:category_id>/delete")
@jwt_required()
def delete_category(category_id: int) -> dict:
    payload = _delete_master_data_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        master_data_service.delete_category(category_id, payload, current_user_id())
    ).to_dict()


@bp.post("/asset-categories/<int:category_id>/update")
@jwt_required()
def update_category(category_id: int) -> dict:
    payload = _update_category_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        master_data_service.update_category(category_id, payload, current_user_id())
    ).to_dict()


@bp.post("/asset-categories/<int:category_id>/disable")
@jwt_required()
def disable_category(category_id: int) -> dict:
    return Result.success(
        master_data_service.set_category_enabled(category_id, False, current_user_id())
    ).to_dict()


@bp.post("/asset-categories/<int:category_id>/enable")
@jwt_required()
def enable_category(category_id: int) -> dict:
    return Result.success(
        master_data_service.set_category_enabled(category_id, True, current_user_id())
    ).to_dict()


__all__ = ["bp"]
