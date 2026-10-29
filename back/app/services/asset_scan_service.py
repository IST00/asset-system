"""Safe asset-code/RFID lookup used by scan-to-use and scanner entry points."""

from __future__ import annotations

from typing import Any

from app.common import BusinessException, ResultCode
from sqlalchemy import select

from app.enums import AssetStatus, InventoryItemStatus, InventoryTaskStatus
from app.extensions import db
from app.models import (
    AssetCategory,
    AssetLocation,
    InventoryItem,
    InventoryTask,
    InventoryTaskAdmin,
    Organization,
    PublicUsageObject,
)
from app.repositories.asset_repository import asset_repository
from app.repositories.operation_repository import asset_business_lock_repository
from app.services import asset_access_service, asset_service, permission_service


def lookup(
    actor_id: int, *, asset_code: str | None = None, rfid_tag: str | None = None
) -> dict[str, Any]:
    normalized_code = asset_code.strip() if asset_code else None
    normalized_rfid = rfid_tag.strip() if rfid_tag else None
    if (normalized_code is None) == (normalized_rfid is None):
        raise BusinessException(
            "请提供资产编码或 RFID 标签之一", result_code=ResultCode.BAD_REQUEST
        )
    asset = (
        asset_repository.find_by_code(normalized_code)
        if normalized_code is not None
        else asset_repository.find_by_rfid_tag(normalized_rfid or "")
    )
    if asset is None:
        raise BusinessException("未找到对应资产", result_code=ResultCode.NOT_FOUND)
    asset_access_service.get_accessible(asset.id, actor_id)
    return asset_service.get(asset.id, actor_id)


def usage_candidate(
    actor_id: int, *, asset_code: str | None = None, rfid_tag: str | None = None
) -> dict[str, Any]:
    """Return a visible idle asset that can seed a personal usage request."""
    normalized_code = asset_code.strip() if asset_code else None
    normalized_rfid = rfid_tag.strip() if rfid_tag else None
    if (normalized_code is None) == (normalized_rfid is None):
        raise BusinessException(
            "请提供资产编码或 RFID 标签之一", result_code=ResultCode.BAD_REQUEST
        )
    asset = (
        asset_repository.find_by_code(normalized_code)
        if normalized_code is not None
        else asset_repository.find_by_rfid_tag(normalized_rfid or "")
    )
    if asset is None:
        raise BusinessException("未找到对应资产", result_code=ResultCode.NOT_FOUND)
    asset_access_service.get_accessible(asset.id, actor_id)
    if asset.status != AssetStatus.IDLE.value:
        raise BusinessException("只有空闲资产可以发起领用")
    if asset.parent_asset_id is not None:
        raise BusinessException("附属资产不能单独发起领用")
    locks = asset_business_lock_repository.find_by_assets([asset.id])
    if locks:
        raise BusinessException("资产正在处理其它申请")
    category = db.session.get(AssetCategory, asset.category_id)
    location = (
        db.session.get(AssetLocation, asset.location_id)
        if asset.location_id is not None
        else None
    )
    organization = db.session.get(Organization, asset.organization_id)
    return {
        "id": asset.id,
        "asset_code": asset.asset_code,
        "asset_name": asset.asset_name,
        "status": asset.status,
        "category_id": asset.category_id,
        "category_name": category.name if category else "",
        "organization_id": asset.organization_id,
        "organization_name": organization.name if organization else "",
        "location_id": asset.location_id,
        "location_name": location.name if location else "",
    }


def scan_intent(
    actor_id: int, *, asset_code: str | None = None, rfid_tag: str | None = None
) -> dict[str, Any]:
    """Resolve one scanned asset into the workflow scenarios it can enter."""
    normalized_code = asset_code.strip() if asset_code else None
    normalized_rfid = rfid_tag.strip() if rfid_tag else None
    if (normalized_code is None) == (normalized_rfid is None):
        raise BusinessException(
            "请提供资产编码或 RFID 标签之一", result_code=ResultCode.BAD_REQUEST
        )
    asset = (
        asset_repository.find_by_code(normalized_code)
        if normalized_code is not None
        else asset_repository.find_by_rfid_tag(normalized_rfid or "")
    )
    if asset is None:
        raise BusinessException("未找到对应资产", result_code=ResultCode.NOT_FOUND)
    asset_access_service.get_accessible(asset.id, actor_id)
    can_manage_usage = permission_service.has_permission(actor_id, "asset:usage:manage")
    can_self_usage = permission_service.has_permission(actor_id, "asset:usage:self")
    scenarios: list[str] = []
    if asset.status == AssetStatus.IDLE.value:
        if (
            asset.parent_asset_id is None
            and not asset_business_lock_repository.find_by_assets([asset.id])
        ):
            scenarios.extend(["PERSONAL_USE", "PERSONAL_BORROW"])
            if can_manage_usage or can_self_usage:
                scenarios.extend(["PUBLIC_USE", "PUBLIC_BORROW"])
    elif asset.status == AssetStatus.IN_USE.value:
        if asset.usage_type == "PERSONAL" and asset.holder_user_id == actor_id:
            scenarios.append("PERSONAL_RETURN")
        if asset.usage_type == "PUBLIC" and can_manage_usage:
            scenarios.append("PUBLIC_RETURN")

    category = db.session.get(AssetCategory, asset.category_id)
    location = (
        db.session.get(AssetLocation, asset.location_id)
        if asset.location_id is not None
        else None
    )
    organization = db.session.get(Organization, asset.organization_id)
    public_object = (
        db.session.get(PublicUsageObject, asset.public_object_id)
        if asset.public_object_id is not None
        else None
    )

    inventory_task: dict[str, Any] | None = None
    row = db.session.execute(
        select(InventoryTask, InventoryItem.status)
        .join(InventoryItem, InventoryItem.task_id == InventoryTask.id)
        .where(
            InventoryTask.status == InventoryTaskStatus.IN_PROGRESS.value,
            InventoryItem.asset_id == asset.id,
            (InventoryItem.responsible_user_id == actor_id)
            | (
                select(InventoryTaskAdmin.id)
                .where(
                    InventoryTaskAdmin.task_id == InventoryTask.id,
                    InventoryTaskAdmin.user_id == actor_id,
                )
                .exists()
            ),
        )
        .order_by(InventoryTask.id.desc())
        .limit(1)
    ).first()
    if row is not None:
        task, item_status = row
        inventory_task = {
            "task_id": task.id,
            "task_no": task.task_no,
            "task_name": task.name,
            "item_status": item_status,
            "pending": item_status == InventoryItemStatus.PENDING.value,
        }

    return {
        "id": asset.id,
        "asset_code": asset.asset_code,
        "asset_name": asset.asset_name,
        "status": asset.status,
        "usage_type": asset.usage_type,
        "holder_user_id": asset.holder_user_id,
        "public_object_id": asset.public_object_id,
        "public_object_name": public_object.name if public_object else "",
        "category_id": asset.category_id,
        "category_name": category.name if category else "",
        "organization_id": asset.organization_id,
        "organization_name": organization.name if organization else "",
        "location_id": asset.location_id,
        "location_name": location.name if location else "",
        "scenarios": scenarios,
        "inventory_task": inventory_task,
    }
