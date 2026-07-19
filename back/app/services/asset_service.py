"""Formal asset creation and query use cases."""

from __future__ import annotations

from typing import Any

from sqlalchemy import ColumnElement, false, or_

from app.common import BusinessException, PageResult, ResultCode
from app.enums import DataScope
from app.enums import ApprovalStatus, AssetCodeStatus, AssetStatus, ExecutionStatus
from app.models import Asset
from app.repositories import (
    QuerySpec,
    asset_code_reservation_repository,
    asset_lifecycle_repository,
    asset_repository,
    operation_log_repository,
)
from app.repositories.workflow_repository import (
    operation_request_repository,
    stock_in_item_repository,
    stock_in_request_repository,
)
from app.services import asset_code_service, audit_service, permission_service


def stock_in_request(operation_request_id: int, actor_id: int) -> None:
    operation = operation_request_repository.get(operation_request_id)
    if operation is None:
        raise BusinessException("入库申请不存在", result_code=ResultCode.NOT_FOUND)
    if operation.approval_status != ApprovalStatus.APPROVED.value:
        raise BusinessException("申请尚未审批通过")
    if operation.execution_status == ExecutionStatus.SUCCESS.value:
        return
    stock_in = stock_in_request_repository.find_by_operation(operation.id)
    if stock_in is None:
        raise BusinessException("入库申请明细不存在")
    items = stock_in_item_repository.find_by_request(stock_in.id)
    reservations = {
        item.stock_in_item_id: item
        for item in asset_code_reservation_repository.find_by_request(operation.id)
    }
    if len(items) != len(reservations):
        raise BusinessException("资产编码占用记录不完整")

    for item in items:
        reservation = reservations[item.id]
        if reservation.status == AssetCodeStatus.ACTIVE.value:
            continue
        if reservation.status != AssetCodeStatus.PENDING_STOCK_IN.value:
            raise BusinessException("资产编码状态不允许入库")
        if asset_repository.find_by_code(item.asset_code) is not None:
            raise BusinessException("资产编码已存在")
        if item.normalized_serial and asset_repository.find_by_normalized_serial(
            item.normalized_serial
        ):
            raise BusinessException("设备序列号已存在")
        asset = Asset(
            asset_code=item.asset_code,
            asset_name=item.asset_name,
            status=AssetStatus.IDLE.value,
            organization_id=stock_in.organization_id,
            category_id=item.category_id,
            unit_id=item.unit_id,
            original_amount=item.original_amount,
            zero_amount_reason=item.zero_amount_reason,
            purchase_date=item.purchase_date,
            manager_id=item.manager_id,
            source_id=item.source_id,
            location_id=item.location_id,
            specification_model=item.specification_model,
            serial_number=item.serial_number,
            normalized_serial=item.normalized_serial,
            receipt_no=item.receipt_no,
            remark=item.remark,
            created_from_request_id=operation.id,
        )
        asset_repository.add(asset)
        asset_code_service.activate(reservation.id, asset.id)
        audit_service.record_asset_stock_in(
            asset_id=asset.id,
            request_no=operation.request_no,
            actor_id=actor_id,
            after_data={
                "asset_code": asset.asset_code,
                "asset_name": asset.asset_name,
                "status": asset.status,
                "organization_id": asset.organization_id,
            },
        )
    stock_in_item_repository.release_serial_reservations(stock_in.id)


def _access_filter(actor_id: int):
    organization_ids = permission_service.accessible_organization_ids(actor_id)
    if organization_ids is None:
        return Asset.id.is_not(None)
    conditions: list[ColumnElement[bool]] = []
    if organization_ids:
        conditions.append(Asset.organization_id.in_(organization_ids))
    if DataScope.SELF.value in permission_service.get_data_scopes(actor_id):
        conditions.append(Asset.manager_id == actor_id)
    return or_(*conditions) if conditions else false()


def _serialize(asset: Asset, include_amount: bool) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": asset.id,
        "asset_code": asset.asset_code,
        "asset_name": asset.asset_name,
        "status": asset.status,
        "organization_id": asset.organization_id,
        "category_id": asset.category_id,
        "unit_id": asset.unit_id,
        "purchase_date": asset.purchase_date.isoformat(),
        "manager_id": asset.manager_id,
        "source_id": asset.source_id,
        "location_id": asset.location_id,
        "specification_model": asset.specification_model,
        "serial_number": asset.serial_number,
        "receipt_no": asset.receipt_no,
        "remark": asset.remark,
        "created_at": asset.created_at,
        "updated_at": asset.updated_at,
    }
    if include_amount:
        result["original_amount"] = f"{asset.original_amount:.2f}"
        result["zero_amount_reason"] = asset.zero_amount_reason
    return result


def page(
    *,
    actor_id: int,
    page_index: int,
    size: int,
    asset_code: str | None = None,
    asset_name: str | None = None,
    serial_number: str | None = None,
) -> PageResult:
    permission_service.require_permission(actor_id, "asset:view")
    filters = [_access_filter(actor_id)]
    if asset_code:
        filters.append(Asset.asset_code == asset_code.strip())
    if asset_name:
        filters.append(Asset.asset_name.contains(asset_name.strip(), autoescape=True))
    if serial_number and serial_number.strip():
        filters.append(Asset.normalized_serial == serial_number.strip().lower())
    result = asset_repository.page(
        QuerySpec(
            filters=filters,
            order_by=[Asset.id.asc()],
            page=page_index,
            size=size,
        )
    )
    include_amount = permission_service.has_permission(actor_id, "asset:amount:view")
    return PageResult(
        items=[_serialize(item, include_amount) for item in result.items],
        total=result.total,
        page=result.page,
        size=result.size,
    )


def get(asset_id: int, actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "asset:view")
    asset = asset_repository.find_accessible(asset_id, _access_filter(actor_id))
    if asset is None:
        raise BusinessException("资产不存在", result_code=ResultCode.NOT_FOUND)
    return _serialize(
        asset, permission_service.has_permission(actor_id, "asset:amount:view")
    )


def lifecycle(asset_id: int, actor_id: int) -> list[dict[str, Any]]:
    get(asset_id, actor_id)
    return [
        {
            "id": item.id,
            "operation_type": item.operation_type,
            "operation_no": item.operation_no,
            "operator_id": item.operator_id,
            "before_data": item.before_data,
            "after_data": item.after_data,
            "remark": item.remark,
            "created_at": item.created_at,
        }
        for item in asset_lifecycle_repository.find_by_asset(asset_id)
    ]


def audit_logs(actor_id: int) -> list[dict[str, Any]]:
    permission_service.require_permission(actor_id, "audit:view")
    if permission_service.accessible_organization_ids(actor_id) is not None:
        raise BusinessException(
            "审计日志第一阶段仅支持全量数据权限", result_code=ResultCode.FORBIDDEN
        )
    return [
        {
            "id": item.id,
            "action": item.action,
            "resource_type": item.resource_type,
            "resource_id": item.resource_id,
            "operator_id": item.operator_id,
            "before_data": item.before_data,
            "after_data": item.after_data,
            "reason": item.reason,
            "created_at": item.created_at,
        }
        for item in operation_log_repository.list_recent()
    ]


__all__ = ["audit_logs", "get", "lifecycle", "page", "stock_in_request"]
