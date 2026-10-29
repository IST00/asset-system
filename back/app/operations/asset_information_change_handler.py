"""Execution handler for approved asset information change requests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from app.common import BusinessException
from app.enums import OperationType
from app.extensions import db
from app.models import (
    Asset,
    AssetInformationChangeRequest,
    OperationRequest,
    OperationRequestAsset,
    User,
)
from app.services import (
    asset_data_service,
    audit_service,
    master_data_service,
    organization_service,
    supplier_service,
)

_OPERATION_TYPES = {
    OperationType.PHYSICAL_INFO_CHANGE.value,
    OperationType.FINANCIAL_INFO_CHANGE.value,
    OperationType.WARRANTY_INFO_CHANGE.value,
}


def _same(left: Any, right: Any) -> bool:
    if isinstance(left, (date, Decimal)):
        left = str(left)
    if isinstance(right, (date, Decimal)):
        right = str(right)
    return left == right


def _context(
    operation_request_id: int,
) -> tuple[
    OperationRequest, AssetInformationChangeRequest, list[OperationRequestAsset]
]:
    operation = db.session.get(OperationRequest, operation_request_id)
    detail = db.session.scalar(
        select(AssetInformationChangeRequest).where(
            AssetInformationChangeRequest.operation_request_id == operation_request_id
        )
    )
    snapshots = list(
        db.session.scalars(
            select(OperationRequestAsset)
            .where(OperationRequestAsset.operation_request_id == operation_request_id)
            .order_by(OperationRequestAsset.id.asc())
        ).all()
    )
    if operation is None or detail is None or not snapshots:
        raise BusinessException("资产信息变更单数据不完整")
    return operation, detail, snapshots


def _validate_reference(field: str, value: Any) -> None:
    if field == "category_id":
        master_data_service.require_enabled_category(int(value))
    elif field == "unit_id" and value is not None:
        master_data_service.require_enabled_unit(int(value))
    elif field == "source_id" and value is not None:
        master_data_service.require_enabled_source(int(value))
    elif field == "location_id" and value is not None:
        master_data_service.require_selectable_location(int(value))
    elif field in {"supplier_id", "warranty_supplier_id"} and value is not None:
        supplier_service.require_enabled_supplier(int(value))
    elif field == "organization_id":
        organization_service.require_enabled(int(value))
    elif field == "manager_id":
        user = db.session.get(User, int(value))
        if user is None or not user.enabled:
            raise BusinessException("资产责任管理员不存在或已停用")


def _coerce(field: str, value: Any) -> Any:
    if field in {"purchase_date", "warranty_expiry_date"}:
        return date.fromisoformat(str(value)) if value is not None else None
    if field == "original_amount":
        return Decimal(str(value))
    return value


def _validate_unique_identifier(asset: Asset, field: str, value: Any) -> None:
    if value is None or field not in {"serial_number", "rfid_tag"}:
        return
    normalized = str(value).strip()
    if not normalized:
        return
    column = Asset.normalized_serial if field == "serial_number" else Asset.rfid_tag
    compare_value = normalized.lower() if field == "serial_number" else normalized
    existing = db.session.scalar(
        select(Asset).where(column == compare_value, Asset.id != asset.id)
    )
    if existing is not None:
        raise BusinessException(
            "设备序列号已存在" if field == "serial_number" else "RFID 标签已存在"
        )


def _validate_snapshot(asset: Asset, snapshot: OperationRequestAsset) -> None:
    if asset.version != snapshot.asset_version_snapshot:
        raise BusinessException("资产版本已变化，不能执行信息变更")
    before = snapshot.before_data
    if not isinstance(before, dict) or before.get("version") != asset.version:
        raise BusinessException("资产变更前快照不完整")
    for field, old_value in before.items():
        if field == "version":
            continue
        if not hasattr(asset, field) or not _same(getattr(asset, field), old_value):
            raise BusinessException("资产信息已变化，不能执行原变更单")


def _apply(
    operation: OperationRequest,
    detail: AssetInformationChangeRequest,
    snapshot: OperationRequestAsset,
) -> None:
    asset = db.session.scalar(
        select(Asset).where(Asset.id == snapshot.asset_id).with_for_update()
    )
    if asset is None:
        raise BusinessException("资产不存在")
    _validate_snapshot(asset, snapshot)
    changes = snapshot.target_data
    if not isinstance(changes, dict) or not changes:
        raise BusinessException("资产变更后快照不完整")
    before = {field: getattr(asset, field) for field in changes}
    for field, raw_value in changes.items():
        _validate_reference(field, raw_value)
        value = _coerce(field, raw_value)
        _validate_unique_identifier(asset, field, value)
        setattr(asset, field, value)
        if field == "serial_number":
            asset.normalized_serial = str(value).strip().lower() if value else None
    amount = asset.original_amount
    if amount == Decimal("0.00") and not str(asset.zero_amount_reason or "").strip():
        raise BusinessException("零金额资产必须填写原因")
    if "purchase_date" in changes or "service_life_months" in changes:
        asset.expected_expiry_date = asset_data_service.calculate_expected_expiry(
            asset.purchase_date, asset.service_life_months
        )
    asset.version += 1
    after = {field: getattr(asset, field) for field in changes} | {
        "version": asset.version
    }
    audit_service.record_resource_change(
        action=operation.operation_type,
        resource_type="asset",
        resource_id=asset.id,
        actor_id=operation.applicant_id,
        before_data={
            key: str(value) if isinstance(value, (date, Decimal)) else value
            for key, value in before.items()
        },
        after_data={
            key: str(value) if isinstance(value, (date, Decimal)) else value
            for key, value in after.items()
        },
        reason=detail.reason,
    )
    audit_service.record_asset_lifecycle(
        asset_id=asset.id,
        operation_type=operation.operation_type,
        request_no=operation.request_no,
        actor_id=operation.applicant_id,
        before_data=snapshot.before_data,
        after_data={
            key: str(value) if isinstance(value, (date, Decimal)) else value
            for key, value in after.items()
        },
        remark=detail.reason,
    )


class AssetInformationChangeHandler:
    def __init__(self, operation_type: str) -> None:
        if operation_type not in _OPERATION_TYPES:
            raise ValueError("unsupported information change operation type")
        self.operation_type = operation_type

    def revalidate_for_execution(self, operation_request_id: int) -> None:
        operation, _detail, snapshots = _context(operation_request_id)
        if operation.operation_type != self.operation_type:
            raise BusinessException("资产信息变更类型不匹配")
        for snapshot in snapshots:
            asset = db.session.get(Asset, snapshot.asset_id)
            if asset is None:
                raise BusinessException("资产不存在")
            _validate_snapshot(asset, snapshot)

    def execute(self, operation_request_id: int, actor_id: int) -> None:
        operation, detail, snapshots = _context(operation_request_id)
        for snapshot in snapshots:
            _apply(operation, detail, snapshot)


__all__ = ["AssetInformationChangeHandler"]
