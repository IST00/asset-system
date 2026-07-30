"""Formal asset creation and query use cases."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from app.common import BusinessException, PageResult, ResultCode
from app.enums import (
    ApprovalStatus,
    AssetCodeStatus,
    AssetDataCompleteness,
    AssetStatus,
    ExecutionStatus,
)
from app.extensions import db
from app.models import (
    ApprovalTask,
    Asset,
    AssetCategory,
    AssetLifecycleRecord,
    AssetLocation,
    AssetSource,
    Organization,
    Supplier,
    Unit,
    User,
)
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
from app.services import (
    asset_access_service,
    asset_code_service,
    asset_data_service,
    audit_service,
    permission_service,
)


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
            supplier_id=item.supplier_id,
            service_life_months=item.service_life_months,
            expected_expiry_date=item.expected_expiry_date,
            manager_id=item.manager_id,
            source_id=item.source_id,
            location_id=item.location_id,
            specification_model=item.specification_model,
            serial_number=item.serial_number,
            normalized_serial=item.normalized_serial,
            receipt_no=item.receipt_no,
            remark=item.remark,
            custom_attributes=deepcopy(item.custom_attributes),
            data_completeness=AssetDataCompleteness.COMPLETE.value,
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


def _entity_name(model: type[Any], entity_id: int | None) -> str | None:
    if entity_id is None:
        return None
    entity = db.session.get(model, entity_id)
    if entity is None:
        return None
    if isinstance(entity, User):
        return entity.nickname or entity.username
    return str(entity.name)


def _serialize(asset: Asset, include_amount: bool) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": asset.id,
        "asset_code": asset.asset_code,
        "asset_name": asset.asset_name,
        "status": asset.status,
        "version": asset.version,
        "organization_id": asset.organization_id,
        "company_name": _entity_name(Organization, asset.organization_id),
        "category_id": asset.category_id,
        "category_name": _entity_name(AssetCategory, asset.category_id),
        "unit_id": asset.unit_id,
        "unit_name": _entity_name(Unit, asset.unit_id),
        "supplier_id": asset.supplier_id,
        "supplier_name": _entity_name(Supplier, asset.supplier_id),
        "purchase_date": asset.purchase_date.isoformat(),
        "service_life_months": asset.service_life_months,
        "expected_expiry_date": asset.expected_expiry_date.isoformat(),
        "manager_id": asset.manager_id,
        "manager_name": _entity_name(User, asset.manager_id),
        "holder_user_id": asset.holder_user_id,
        "user_name": _entity_name(User, asset.holder_user_id),
        "usage_department_id": asset.usage_department_id,
        "department_name": _entity_name(Organization, asset.usage_department_id),
        "source_id": asset.source_id,
        "source_name": _entity_name(AssetSource, asset.source_id),
        "location_id": asset.location_id,
        "location_name": _entity_name(AssetLocation, asset.location_id),
        "specification_model": asset.specification_model,
        "model": asset.specification_model,
        "serial_number": asset.serial_number,
        "receipt_no": asset.receipt_no,
        "receipt_number": asset.receipt_no,
        "remark": asset.remark,
        "custom_attributes": dict(asset.custom_attributes),
        "data_completeness": asset.data_completeness,
        "information_complete": asset.data_completeness
        == AssetDataCompleteness.COMPLETE.value,
        "missing_fields": asset_data_service.missing_fields(
            asset.unit_id, asset.source_id, asset.location_id
        ),
        "created_at": asset.created_at,
        "updated_at": asset.updated_at,
    }
    if include_amount:
        result["original_amount"] = f"{asset.original_amount:.2f}"
        result["purchase_amount"] = float(asset.original_amount)
        result["zero_amount_reason"] = asset.zero_amount_reason
    return result


def _month_start(value: datetime, offset: int = 0) -> datetime:
    month_index = value.year * 12 + value.month - 1 + offset
    year, month_zero = divmod(month_index, 12)
    return datetime(year, month_zero + 1, 1, tzinfo=timezone.utc)


def dashboard(actor_id: int) -> dict[str, Any]:
    """Return real-time dashboard aggregates within the actor's data scope."""
    permission_service.require_permission(actor_id, "asset:view")
    access = asset_access_service.access_filter(actor_id)

    status_counts = {
        str(status): int(count)
        for status, count in db.session.execute(
            select(Asset.status, func.count(Asset.id))
            .where(access)
            .group_by(Asset.status)
        ).all()
    }
    total = sum(status_counts.values())

    category_rows = db.session.execute(
        select(AssetCategory.name, func.count(Asset.id))
        .join(Asset, Asset.category_id == AssetCategory.id)
        .where(access)
        .group_by(AssetCategory.id, AssetCategory.name)
        .order_by(func.count(Asset.id).desc(), AssetCategory.id.asc())
    ).all()

    incomplete_assets = int(
        db.session.scalar(
            select(func.count(Asset.id)).where(
                access,
                Asset.data_completeness == AssetDataCompleteness.INCOMPLETE.value,
            )
        )
        or 0
    )
    holder = aliased(User)
    departed_owner_assets = int(
        db.session.scalar(
            select(func.count(Asset.id))
            .outerjoin(holder, holder.id == Asset.holder_user_id)
            .where(access, Asset.holder_user_id.is_not(None), holder.enabled.is_(False))
        )
        or 0
    )
    pending_approvals = 0
    if permission_service.has_permission(actor_id, "approval:task:view"):
        pending_approvals = int(
            db.session.scalar(
                select(func.count(ApprovalTask.id)).where(
                    ApprovalTask.approver_id == actor_id,
                    ApprovalTask.status == "PENDING",
                )
            )
            or 0
        )

    current_month = _month_start(datetime.now(tz=timezone.utc))
    month_starts = [_month_start(current_month, offset) for offset in range(-5, 1)]
    month_keys = [item.strftime("%Y-%m") for item in month_starts]
    intake_counts = dict.fromkeys(month_keys, 0)
    scrapped_counts = dict.fromkeys(month_keys, 0)

    intake_dates = db.session.scalars(
        select(Asset.created_at).where(access, Asset.created_at >= month_starts[0])
    ).all()
    for created_at in intake_dates:
        key = created_at.strftime("%Y-%m")
        if key in intake_counts:
            intake_counts[key] += 1

    lifecycle_rows = db.session.execute(
        select(AssetLifecycleRecord.created_at, AssetLifecycleRecord.after_data)
        .join(Asset, Asset.id == AssetLifecycleRecord.asset_id)
        .where(access, AssetLifecycleRecord.created_at >= month_starts[0])
    ).all()
    for created_at, after_data in lifecycle_rows:
        if not isinstance(after_data, dict):
            continue
        if after_data.get("status") != AssetStatus.SCRAPPED.value:
            continue
        key = created_at.strftime("%Y-%m")
        if key in scrapped_counts:
            scrapped_counts[key] += 1

    return {
        "metrics": {
            "total": total,
            "idle": status_counts.get(AssetStatus.IDLE.value, 0),
            "in_use": status_counts.get(AssetStatus.IN_USE.value, 0),
            "repairing": status_counts.get(AssetStatus.REPAIRING.value, 0),
            "scrapped": status_counts.get(AssetStatus.SCRAPPED.value, 0),
        },
        "issues": {
            "pending_approvals": pending_approvals,
            "inventory_exceptions": 0,
            "incomplete_assets": incomplete_assets,
            "departed_owner_assets": departed_owner_assets,
        },
        "inventory": {
            "task_name": "暂无进行中的盘点任务",
            "checked": 0,
            "total": 0,
            "exceptions": 0,
        },
        "categories": [
            {"name": str(name), "value": int(count)} for name, count in category_rows
        ],
        "statuses": [
            {"status": status.value, "value": status_counts.get(status.value, 0)}
            for status in AssetStatus
        ],
        "monthly_changes": [
            {
                "month": key,
                "intake": intake_counts[key],
                "scrapped": scrapped_counts[key],
            }
            for key in month_keys
        ],
    }


def page(
    *,
    actor_id: int,
    page_index: int,
    size: int,
    asset_code: str | None = None,
    asset_name: str | None = None,
    serial_number: str | None = None,
    data_completeness: str | None = None,
) -> PageResult:
    permission_service.require_permission(actor_id, "asset:view")
    filters = [asset_access_service.access_filter(actor_id)]
    if asset_code:
        filters.append(Asset.asset_code == asset_code.strip())
    if asset_name:
        filters.append(Asset.asset_name.contains(asset_name.strip(), autoescape=True))
    if serial_number and serial_number.strip():
        filters.append(Asset.normalized_serial == serial_number.strip().lower())
    if data_completeness is not None:
        filters.append(Asset.data_completeness == data_completeness)
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
    asset = asset_access_service.get_accessible(asset_id, actor_id)
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
