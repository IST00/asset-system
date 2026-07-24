"""Supplier master-data endpoints."""

from __future__ import annotations

from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from app.common import Result
from app.schemas import (
    CreateSupplierRequestSchema,
    DeleteSupplierRequestSchema,
    SupplierVersionRequestSchema,
    UpdateSupplierRequestSchema,
)
from app.security import current_user_id
from app.services import supplier_service

bp = Blueprint("suppliers", __name__, url_prefix="/api/v1/suppliers")

_create_schema = CreateSupplierRequestSchema()
_update_schema = UpdateSupplierRequestSchema()
_version_schema = SupplierVersionRequestSchema()
_delete_schema = DeleteSupplierRequestSchema()


@bp.get("")
@jwt_required()
def list_suppliers() -> dict:
    return Result.success(supplier_service.list_suppliers(current_user_id())).to_dict()


@bp.post("")
@jwt_required()
def create_supplier() -> dict:
    payload = _create_schema.load(request.get_json(silent=True) or {})
    payload["name"] = payload["name"].strip()
    return Result.success(
        supplier_service.create_supplier(payload, current_user_id())
    ).to_dict()


@bp.post("/<int:supplier_id>/update")
@jwt_required()
def update_supplier(supplier_id: int) -> dict:
    payload = _update_schema.load(request.get_json(silent=True) or {})
    payload["name"] = payload["name"].strip()
    return Result.success(
        supplier_service.update_supplier(supplier_id, payload, current_user_id())
    ).to_dict()


@bp.post("/<int:supplier_id>/disable")
@jwt_required()
def disable_supplier(supplier_id: int) -> dict:
    payload = _version_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        supplier_service.set_supplier_enabled(
            supplier_id,
            False,
            payload["version"],
            current_user_id(),
        )
    ).to_dict()


@bp.post("/<int:supplier_id>/enable")
@jwt_required()
def enable_supplier(supplier_id: int) -> dict:
    payload = _version_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        supplier_service.set_supplier_enabled(
            supplier_id,
            True,
            payload["version"],
            current_user_id(),
        )
    ).to_dict()


@bp.post("/<int:supplier_id>/delete")
@jwt_required()
def delete_supplier(supplier_id: int) -> dict:
    payload = _delete_schema.load(request.get_json(silent=True) or {})
    payload["reason"] = payload["reason"].strip()
    supplier_service.delete_supplier(
        supplier_id,
        payload["version"],
        current_user_id(),
        payload["reason"],
    )
    return Result.success().to_dict()
