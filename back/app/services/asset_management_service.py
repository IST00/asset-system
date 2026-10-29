"""Transactional asset maintenance, public object and lifecycle commands."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select

from app.common import BusinessException, ResultCode
from app.enums import AssetStatus, RecordStatus, UsageType
from app.extensions import db
from app.models import (
    Asset,
    AssetBusinessLock,
    AssetRepairRecord,
    AssetScrapRecord,
    PublicUsageObject,
    User,
)
from app.repositories import asset_repository
from app.services import (
    asset_access_service,
    asset_data_service,
    asset_service,
    audit_service,
    master_data_service,
    organization_service,
    permission_service,
    supplier_service,
)

_EDIT_FIELDS = {
    "asset_name",
    "category_id",
    "unit_id",
    "supplier_id",
    "original_amount",
    "zero_amount_reason",
    "purchase_date",
    "service_life_months",
    "manager_id",
    "status",
    "usage_type",
    "holder_user_id",
    "public_object_id",
    "usage_company_id",
    "usage_department_id",
    "source_id",
    "location_id",
    "specification_model",
    "serial_number",
    "receipt_no",
    "rfid_tag",
    "remark",
}
_OPTIONAL_TEXT_FIELDS = {
    "zero_amount_reason",
    "specification_model",
    "serial_number",
    "receipt_no",
    "rfid_tag",
    "remark",
}


def _command_no(prefix: str) -> str:
    return f"{prefix}{datetime.now(tz=timezone.utc):%Y%m%d}{uuid4().hex[:12].upper()}"


def _require_user(user_id: int) -> User:
    user = db.session.get(User, user_id)
    if user is None or not user.enabled:
        raise BusinessException("用户不存在或已停用")
    return user


def _asset_snapshot(asset: Asset) -> dict[str, Any]:
    return {
        "asset_name": asset.asset_name,
        "status": asset.status,
        "organization_id": asset.organization_id,
        "usage_type": asset.usage_type,
        "holder_user_id": asset.holder_user_id,
        "public_object_id": asset.public_object_id,
        "usage_department_id": asset.usage_department_id,
        "parent_asset_id": asset.parent_asset_id,
        "category_id": asset.category_id,
        "unit_id": asset.unit_id,
        "supplier_id": asset.supplier_id,
        "original_amount": str(asset.original_amount),
        "zero_amount_reason": asset.zero_amount_reason,
        "purchase_date": asset.purchase_date.isoformat(),
        "service_life_months": asset.service_life_months,
        "expected_expiry_date": asset.expected_expiry_date.isoformat(),
        "manager_id": asset.manager_id,
        "source_id": asset.source_id,
        "location_id": asset.location_id,
        "specification_model": asset.specification_model,
        "serial_number": asset.serial_number,
        "receipt_no": asset.receipt_no,
        "rfid_tag": asset.rfid_tag,
        "remark": asset.remark,
        "data_completeness": asset.data_completeness,
        "version": asset.version,
    }


def _targets(items: list[dict[str, Any]]) -> dict[int, int]:
    result: dict[int, int] = {}
    for item in items:
        asset_id = int(item["asset_id"])
        if asset_id in result:
            raise BusinessException("资产不能重复选择")
        result[asset_id] = int(item["version"])
    return result


def _load_assets(targets: dict[int, int], actor_id: int) -> list[Asset]:
    asset_ids = sorted(targets)
    assets = asset_repository.find_many_accessible_for_update(
        asset_ids, asset_access_service.access_filter(actor_id)
    )
    if [asset.id for asset in assets] != asset_ids:
        raise BusinessException(
            "资产不存在或无权操作", result_code=ResultCode.NOT_FOUND
        )
    locks = list(
        db.session.scalars(
            select(AssetBusinessLock)
            .where(AssetBusinessLock.asset_id.in_(asset_ids))
            .order_by(AssetBusinessLock.asset_id.asc())
            .with_for_update()
        ).all()
    )
    if locks:
        locked = next(asset for asset in assets if asset.id == locks[0].asset_id)
        raise BusinessException(f"资产 {locked.asset_code} 正在处理其它业务")
    for asset in assets:
        if asset.version != targets[asset.id]:
            raise BusinessException(f"资产 {asset.asset_code} 已被修改，请刷新后重试")
    return assets


def _validate_changes(changes: dict[str, Any], assets: list[Asset]) -> dict[str, Any]:
    invalid = set(changes) - _EDIT_FIELDS
    if invalid or not changes:
        raise BusinessException("资产修改字段无效")
    normalized = dict(changes)
    if "asset_name" in normalized:
        normalized["asset_name"] = str(normalized["asset_name"]).strip()
        if not normalized["asset_name"]:
            raise BusinessException("资产名称不能为空")
    for field in _OPTIONAL_TEXT_FIELDS & normalized.keys():
        value = normalized[field]
        normalized[field] = str(value).strip() or None if value is not None else None
    if "category_id" in normalized:
        master_data_service.require_enabled_category(normalized["category_id"])
    if "unit_id" in normalized and normalized["unit_id"] is not None:
        master_data_service.require_enabled_unit(normalized["unit_id"])
    if "source_id" in normalized and normalized["source_id"] is not None:
        master_data_service.require_enabled_source(normalized["source_id"])
    if "location_id" in normalized and normalized["location_id"] is not None:
        master_data_service.require_selectable_location(normalized["location_id"])
    if "supplier_id" in normalized and normalized["supplier_id"] is not None:
        supplier_service.require_enabled_supplier(normalized["supplier_id"])
    if "manager_id" in normalized:
        _require_user(normalized["manager_id"])
    if "usage_company_id" in normalized:
        organization_service.require_enabled(normalized["usage_company_id"])
    if "usage_department_id" in normalized:
        if normalized["usage_department_id"] is None:
            normalized["usage_department_id"] = None
        else:
            organization_service.require_enabled(normalized["usage_department_id"])
    ownership_fields = {
        "holder_user_id",
        "public_object_id",
        "usage_type",
        "usage_department_id",
    }
    if ownership_fields & normalized.keys() and len(assets) > 1:
        raise BusinessException("资产状态和使用归属仅支持逐件资产直接维护")
    holder = None
    if "holder_user_id" in normalized and normalized["holder_user_id"] is not None:
        holder = _require_user(normalized["holder_user_id"])
        if holder.organization_id is None:
            raise BusinessException("使用人未归属部门，请联系管理员维护")
        normalized["usage_type"] = UsageType.PERSONAL.value
        normalized["public_object_id"] = None
        normalized["usage_department_id"] = holder.organization_id
    if "public_object_id" in normalized and normalized["public_object_id"] is not None:
        public_object = db.session.get(
            PublicUsageObject, normalized["public_object_id"]
        )
        if public_object is None or public_object.status != RecordStatus.ENABLED.value:
            raise BusinessException("公共使用对象不存在或已停用")
        normalized["usage_type"] = UsageType.PUBLIC.value
        normalized["holder_user_id"] = None
        if holder is None:
            normalized["usage_department_id"] = None
    if ownership_fields & normalized.keys():
        asset = assets[0]
        status = normalized.get("status", asset.status)
        if "status" not in normalized and (
            normalized.get("holder_user_id") is not None
            or normalized.get("public_object_id") is not None
            or normalized.get("usage_type") is not None
            or normalized.get("usage_department_id") is not None
        ):
            # Editing an idle asset to a personal/public owner means it is now in
            # use. Pending-receipt assets keep their sign-out state.
            if status != AssetStatus.PENDING_RECEIPT.value:
                status = AssetStatus.IN_USE.value
                normalized["status"] = status
        target_usage_type = normalized.get("usage_type", asset.usage_type)
        target_holder_id = normalized.get("holder_user_id", asset.holder_user_id)
        target_public_object_id = normalized.get(
            "public_object_id", asset.public_object_id
        )
        if (
            "status" not in normalized
            and target_holder_id is None
            and (target_public_object_id is None)
        ):
            # Clearing both individual/public ownership returns the asset to the
            # idle pool. Department-only usage without an owner cannot remain in
            # use, so clearing the holder clears it as well.
            normalized["usage_type"] = None
            normalized["usage_department_id"] = None
            normalized["status"] = AssetStatus.IDLE.value
            target_usage_type = None
            status = AssetStatus.IDLE.value
        if status == AssetStatus.IN_USE.value:
            if target_usage_type == UsageType.PERSONAL.value:
                if target_holder_id is None:
                    raise BusinessException("个人在用资产必须选择使用人")
                if target_public_object_id is not None:
                    raise BusinessException("个人在用资产不能同时选择公共使用对象")
            elif target_usage_type == UsageType.PUBLIC.value:
                if target_public_object_id is None:
                    raise BusinessException("公共在用资产必须选择公共使用对象")
                if target_holder_id is not None:
                    raise BusinessException("公共在用资产不能同时选择使用人")
            # A department-only assignment is also valid: the department keeps
            # the asset in use without naming an individual holder.
        elif status not in {
            AssetStatus.IN_USE.value,
            AssetStatus.PENDING_RECEIPT.value,
        } and any(
            field in normalized
            for field in ("holder_user_id", "public_object_id", "usage_type")
        ):
            normalized["usage_type"] = None
            normalized["holder_user_id"] = None
            normalized["public_object_id"] = None
            normalized["usage_department_id"] = None
        elif target_holder_id is not None or target_public_object_id is not None:
            if status != AssetStatus.PENDING_RECEIPT.value:
                raise BusinessException("只有待签收资产可以保留使用归属")
            if target_usage_type not in {
                UsageType.PERSONAL.value,
                UsageType.PUBLIC.value,
            }:
                raise BusinessException("待签收资产必须选择个人或公共使用归属")
            if (
                target_usage_type == UsageType.PERSONAL.value
                and target_holder_id is None
            ):
                raise BusinessException("个人待签收资产必须选择使用人")
            if (
                target_usage_type == UsageType.PUBLIC.value
                and target_public_object_id is None
            ):
                raise BusinessException("公共待签收资产必须选择公共使用对象")
        elif normalized.get("usage_type") is not None:
            if status not in {
                AssetStatus.PENDING_RECEIPT.value,
                AssetStatus.IN_USE.value,
            }:
                raise BusinessException("当前资产状态不能设置使用方式")
    if "original_amount" in normalized:
        amount = Decimal(normalized["original_amount"])
        if amount < 0:
            raise BusinessException("资产金额不能小于 0")
        normalized["original_amount"] = amount
        if (
            amount == 0
            and not normalized.get("zero_amount_reason")
            and not all(asset.zero_amount_reason for asset in assets)
        ):
            raise BusinessException("金额为 0 时必须填写零金额原因")
    asset_ids = {asset.id for asset in assets}
    serial = normalized.get("serial_number")
    if "serial_number" in normalized:
        normalized_serial = serial.lower() if serial else None
        if normalized_serial and len(assets) > 1:
            raise BusinessException("批量编辑不能为多件资产设置同一设备序列号")
        if normalized_serial:
            existing = asset_repository.find_by_normalized_serial(normalized_serial)
            if existing is not None and existing.id not in asset_ids:
                raise BusinessException("设备序列号已存在")
        normalized["normalized_serial"] = normalized_serial
    rfid_tag = normalized.get("rfid_tag")
    if "rfid_tag" in normalized and rfid_tag:
        if len(assets) > 1:
            raise BusinessException("批量编辑不能为多件资产设置同一 RFID 标签")
        existing = asset_repository.find_by_rfid_tag(rfid_tag)
        if existing is not None and existing.id not in asset_ids:
            raise BusinessException("RFID 标签已存在")
    return normalized


def update_batch(payload: dict[str, Any], actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "asset:edit")
    targets = _targets(payload["items"])
    try:
        assets = _load_assets(targets, actor_id)
        changes = _validate_changes(payload["changes"], assets)
        batch_no = _command_no("AED")
        for asset in assets:
            before = _asset_snapshot(asset)
            for field, value in changes.items():
                setattr(asset, field, value)
            if "purchase_date" in changes or "service_life_months" in changes:
                asset.expected_expiry_date = (
                    asset_data_service.calculate_expected_expiry(
                        asset.purchase_date, asset.service_life_months
                    )
                )
            asset.data_completeness = asset_data_service.calculate_completeness_values(
                asset.unit_id, asset.source_id, asset.location_id
            )
            asset.version += 1
            after = _asset_snapshot(asset)
            audit_service.record_asset_lifecycle(
                asset_id=asset.id,
                operation_type="ASSET_EDIT",
                request_no=batch_no,
                actor_id=actor_id,
                before_data=before,
                after_data=after,
            )
        audit_service.record_resource_change(
            action="ASSET_BATCH_EDIT" if len(assets) > 1 else "ASSET_EDIT",
            resource_type="asset",
            resource_id=batch_no,
            actor_id=actor_id,
            before_data={"asset_ids": sorted(targets)},
            after_data={"fields": sorted(changes), "updated_count": len(assets)},
            reason=str(payload["reason"]).strip(),
        )
        db.session.commit()
        return {
            "batch_no": batch_no,
            "updated_count": len(assets),
            "items": [asset_service.get(asset.id, actor_id) for asset in assets],
        }
    except Exception:
        db.session.rollback()
        raise


def update_one(asset_id: int, payload: dict[str, Any], actor_id: int) -> dict[str, Any]:
    changes = {key: value for key, value in payload.items() if key in _EDIT_FIELDS}
    result = update_batch(
        {
            "items": [{"asset_id": asset_id, "version": payload["version"]}],
            "changes": changes,
            "reason": payload["reason"],
        },
        actor_id,
    )
    return result["items"][0]


def relation_tree(asset_id: int, actor_id: int) -> dict[str, Any]:
    asset = asset_access_service.get_accessible(asset_id, actor_id)
    root = asset
    if asset.parent_asset_id is not None:
        root = asset_access_service.get_accessible(asset.parent_asset_id, actor_id)
    children = asset_repository.find_direct_children([root.id])
    return {
        "main": asset_service.get(root.id, actor_id),
        "attachments": [asset_service.get(item.id, actor_id) for item in children],
    }


def _require_relation_assets_unlocked(assets: list[Asset]) -> None:
    asset_ids = [asset.id for asset in assets]
    locks = list(
        db.session.scalars(
            select(AssetBusinessLock)
            .where(AssetBusinessLock.asset_id.in_(asset_ids))
            .order_by(AssetBusinessLock.asset_id.asc())
            .with_for_update()
        ).all()
    )
    if locks:
        locked = next(asset for asset in assets if asset.id == locks[0].asset_id)
        raise BusinessException(f"资产 {locked.asset_code} 正在处理其它业务")


def _record_relation_lifecycle(
    *,
    asset: Asset,
    operation_type: str,
    command_no: str,
    actor_id: int,
    before: dict[str, Any],
) -> None:
    audit_service.record_asset_lifecycle(
        asset_id=asset.id,
        operation_type=operation_type,
        request_no=command_no,
        actor_id=actor_id,
        before_data=before,
        after_data=_asset_snapshot(asset),
    )


def attach(
    main_asset_id: int, payload: dict[str, Any], actor_id: int
) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "asset:relation:manage")
    child_ids = sorted(set(payload["child_ids"]))
    if main_asset_id in child_ids:
        raise BusinessException("主资产不能挂接自身")
    try:
        asset_ids = sorted([main_asset_id, *child_ids])
        assets = asset_repository.find_many_accessible_for_update(
            asset_ids, asset_access_service.access_filter(actor_id)
        )
        if [asset.id for asset in assets] != asset_ids:
            raise BusinessException(
                "资产不存在或无权操作", result_code=ResultCode.NOT_FOUND
            )
        _require_relation_assets_unlocked(assets)
        main = next(item for item in assets if item.id == main_asset_id)
        children = [item for item in assets if item.id in child_ids]
        if main.parent_asset_id is not None:
            raise BusinessException("附属资产不能作为主资产")
        if asset_repository.find_direct_children(child_ids):
            raise BusinessException("已有附属资产的资产不能再挂接为附属资产")
        existing_parent = next(
            (child for child in children if child.parent_asset_id is not None), None
        )
        if existing_parent is not None:
            raise BusinessException(
                f"资产 {existing_parent.asset_code} 已挂接其它主资产，请先解除原关系"
            )
        if any(item.status == AssetStatus.SCRAPPED.value for item in assets):
            raise BusinessException("已报废资产不能维护主附关系")

        command_no = _command_no("REL")
        main_before = _asset_snapshot(main)
        main.version += 1
        _record_relation_lifecycle(
            asset=main,
            operation_type="ASSET_RELATION_ATTACH",
            command_no=command_no,
            actor_id=actor_id,
            before=main_before,
        )
        for child in children:
            before = _asset_snapshot(child)
            child.parent_asset_id = main.id
            child.usage_type = main.usage_type
            child.holder_user_id = main.holder_user_id
            child.public_object_id = main.public_object_id
            child.usage_department_id = main.usage_department_id
            child.location_id = main.location_id
            child.status = main.status
            child.version += 1
            _record_relation_lifecycle(
                asset=child,
                operation_type="ASSET_RELATION_ATTACH",
                command_no=command_no,
                actor_id=actor_id,
                before=before,
            )
        audit_service.record_resource_change(
            action="ASSET_RELATION_ATTACH",
            resource_type="asset_relation",
            resource_id=main.id,
            actor_id=actor_id,
            before_data={"child_ids": []},
            after_data={"child_ids": child_ids},
            reason=payload["reason"],
        )
        db.session.commit()
        return relation_tree(main.id, actor_id)
    except Exception:
        db.session.rollback()
        raise


def detach(
    main_asset_id: int, payload: dict[str, Any], actor_id: int
) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "asset:relation:manage")
    child_ids = sorted(set(payload["child_ids"]))
    try:
        asset_ids = sorted([main_asset_id, *child_ids])
        assets = asset_repository.find_many_accessible_for_update(
            asset_ids, asset_access_service.access_filter(actor_id)
        )
        if [item.id for item in assets] != asset_ids:
            raise BusinessException(
                "主资产或附属资产不存在", result_code=ResultCode.NOT_FOUND
            )
        _require_relation_assets_unlocked(assets)
        main = next(item for item in assets if item.id == main_asset_id)
        children = [item for item in assets if item.id in child_ids]
        if any(item.parent_asset_id != main_asset_id for item in children):
            raise BusinessException("选择的资产不属于该主资产")

        command_no = _command_no("REL")
        main_before = _asset_snapshot(main)
        main.version += 1
        _record_relation_lifecycle(
            asset=main,
            operation_type="ASSET_RELATION_DETACH",
            command_no=command_no,
            actor_id=actor_id,
            before=main_before,
        )
        for child in children:
            before = _asset_snapshot(child)
            child.parent_asset_id = None
            child.version += 1
            _record_relation_lifecycle(
                asset=child,
                operation_type="ASSET_RELATION_DETACH",
                command_no=command_no,
                actor_id=actor_id,
                before=before,
            )
        audit_service.record_resource_change(
            action="ASSET_RELATION_DETACH",
            resource_type="asset_relation",
            resource_id=main_asset_id,
            actor_id=actor_id,
            before_data={"child_ids": child_ids},
            after_data={"child_ids": []},
            reason=payload["reason"],
        )
        db.session.commit()
        return relation_tree(main_asset_id, actor_id)
    except Exception:
        db.session.rollback()
        raise


def _public_object_dict(item: PublicUsageObject) -> dict[str, Any]:
    usage_count = int(
        db.session.scalar(
            select(func.count(Asset.id)).where(Asset.public_object_id == item.id)
        )
        or 0
    )
    return {
        "id": item.id,
        "code": item.code,
        "name": item.name,
        "status": item.status,
        "usage_count": usage_count,
    }


def list_public_objects(
    actor_id: int, include_disabled: bool = False
) -> list[dict[str, Any]]:
    permission_service.require_permission(actor_id, "asset:view")
    statement = select(PublicUsageObject).order_by(PublicUsageObject.id.asc())
    if not include_disabled:
        statement = statement.where(
            PublicUsageObject.status == RecordStatus.ENABLED.value
        )
    return [_public_object_dict(item) for item in db.session.scalars(statement).all()]


def create_public_object(payload: dict[str, Any], actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "public-object:manage")
    name = str(payload["name"]).strip()
    if not name:
        raise BusinessException("公共使用对象名称不能为空")
    exists = db.session.scalar(
        select(PublicUsageObject.id).where(
            func.lower(PublicUsageObject.name) == name.lower()
        )
    )
    if exists is not None:
        raise BusinessException("公共使用对象名称已存在")
    current = int(db.session.scalar(select(func.max(PublicUsageObject.id))) or 0) + 1
    item = PublicUsageObject(code=f"PUB{current:06d}", name=name)
    db.session.add(item)
    db.session.flush()
    audit_service.record_resource_change(
        action="PUBLIC_OBJECT_CREATE",
        resource_type="public_usage_object",
        resource_id=item.id,
        actor_id=actor_id,
        before_data=None,
        after_data=_public_object_dict(item),
    )
    db.session.commit()
    return _public_object_dict(item)


def update_public_object(
    object_id: int, payload: dict[str, Any], actor_id: int
) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "public-object:manage")
    item = db.session.get(PublicUsageObject, object_id)
    if item is None:
        raise BusinessException("公共使用对象不存在", result_code=ResultCode.NOT_FOUND)
    before = _public_object_dict(item)
    if "name" in payload:
        name = str(payload["name"]).strip()
        if not name:
            raise BusinessException("公共使用对象名称不能为空")
        duplicate = db.session.scalar(
            select(PublicUsageObject.id).where(
                func.lower(PublicUsageObject.name) == name.lower(),
                PublicUsageObject.id != object_id,
            )
        )
        if duplicate is not None:
            raise BusinessException("公共使用对象名称已存在")
        item.name = name
    if "status" in payload:
        item.status = payload["status"]
    audit_service.record_resource_change(
        action="PUBLIC_OBJECT_UPDATE",
        resource_type="public_usage_object",
        resource_id=item.id,
        actor_id=actor_id,
        before_data=before,
        after_data=_public_object_dict(item),
    )
    db.session.commit()
    return _public_object_dict(item)


def _apply_lifecycle(
    *,
    operation_type: str,
    items: list[dict[str, Any]],
    actor_id: int,
    reason: str,
    changes_factory: Callable[[Asset, dict[str, Any]], dict[str, Any]],
    allowed_statuses: set[str] | None = None,
    extra_targets: dict[int, int] | None = None,
    before_apply: Callable[[list[Asset], str], None] | None = None,
) -> dict[str, Any]:
    targets = _targets(items)
    lock_targets = dict(targets)
    if extra_targets:
        for asset_id, version in extra_targets.items():
            lock_targets.setdefault(asset_id, version)
    try:
        loaded_assets = _load_assets(lock_targets, actor_id)
        assets = [asset for asset in loaded_assets if asset.id in targets]
        command_no = _command_no(operation_type[:3])
        if before_apply is not None:
            before_apply(loaded_assets, command_no)
        for asset in assets:
            if allowed_statuses is not None and asset.status not in allowed_statuses:
                raise BusinessException(
                    f"资产 {asset.asset_code} 当前状态不允许执行该操作"
                )
            before = _asset_snapshot(asset)
            changes = changes_factory(asset, before)
            for field, value in changes.items():
                setattr(asset, field, value)
            asset.version += 1
            audit_service.record_asset_lifecycle(
                asset_id=asset.id,
                operation_type=operation_type,
                request_no=command_no,
                actor_id=actor_id,
                before_data=before,
                after_data=_asset_snapshot(asset),
                remark=reason,
            )
        audit_service.record_resource_change(
            action=operation_type,
            resource_type="asset_lifecycle",
            resource_id=command_no,
            actor_id=actor_id,
            before_data={"asset_ids": sorted(targets)},
            after_data={"updated_count": len(assets)},
            reason=reason,
        )
        db.session.commit()
        return {
            "request_no": command_no,
            "updated_count": len(assets),
            "items": [asset_service.get(item.id, actor_id) for item in assets],
        }
    except Exception:
        db.session.rollback()
        raise


def transfer(payload: dict[str, Any], actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "asset:transfer")
    if "organization_id" in payload:
        organization_service.require_enabled(payload["organization_id"])
    if "usage_company_id" in payload:
        organization_service.require_enabled(payload["usage_company_id"])
    if "usage_department_id" in payload and payload["usage_department_id"] is not None:
        organization_service.require_enabled(payload["usage_department_id"])
    if "location_id" in payload:
        master_data_service.require_selectable_location(payload["location_id"])
    if "manager_id" in payload:
        _require_user(payload["manager_id"])

    holder = None
    if payload.get("holder_user_id") is not None:
        holder = _require_user(payload["holder_user_id"])
    public_object = None
    if payload.get("public_object_id") is not None:
        public_object = db.session.get(PublicUsageObject, payload["public_object_id"])
        if public_object is None or public_object.status != RecordStatus.ENABLED.value:
            raise BusinessException("公共使用对象不存在或已停用")

    targets = _targets(payload["items"])
    children = asset_repository.find_direct_children(sorted(targets))
    for child in children:
        targets.setdefault(child.id, child.version)
    items = [
        {"asset_id": asset_id, "version": version}
        for asset_id, version in targets.items()
    ]
    target_fields = {
        key: payload[key]
        for key in (
            "organization_id",
            "usage_company_id",
            "usage_department_id",
            "location_id",
            "manager_id",
        )
        if key in payload
    }
    if holder is not None:
        target_fields.update(
            {
                "status": AssetStatus.IN_USE.value,
                "usage_type": "PERSONAL",
                "holder_user_id": holder.id,
                "public_object_id": None,
                "usage_department_id": holder.organization_id,
            }
        )
    elif public_object is not None:
        target_fields.update(
            {
                "status": AssetStatus.IN_USE.value,
                "usage_type": "PUBLIC",
                "holder_user_id": None,
                "public_object_id": public_object.id,
                "usage_department_id": None,
            }
        )
    return _apply_lifecycle(
        operation_type="TRANSFER",
        items=items,
        actor_id=actor_id,
        reason=payload["reason"],
        changes_factory=lambda _asset, _before: target_fields,
        allowed_statuses={AssetStatus.IDLE.value, AssetStatus.IN_USE.value},
    )


def repair_start(payload: dict[str, Any], actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "asset:repair")
    metadata = {
        "vendor": payload.get("vendor"),
        "estimated_cost": str(payload["estimated_cost"])
        if payload.get("estimated_cost") is not None
        else None,
    }

    def changes(asset: Asset, before: dict[str, Any]) -> dict[str, Any]:
        custom = dict(asset.custom_attributes)
        custom["repair_context"] = {
            **metadata,
            "return_status": before["status"],
            "started_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        return {"status": AssetStatus.REPAIRING.value, "custom_attributes": custom}

    def create_repair_records(assets: list[Asset], command_no: str) -> None:
        sent_at = datetime.now(tz=timezone.utc)
        for asset in assets:
            db.session.add(
                AssetRepairRecord(
                    asset_id=asset.id,
                    repair_no=command_no,
                    before_status=asset.status,
                    fault_description=payload["reason"].strip(),
                    repair_supplier_name=metadata["vendor"],
                    repair_cost=payload.get("estimated_cost"),
                    sent_at=sent_at,
                )
            )

    return _apply_lifecycle(
        operation_type="REPAIR_START",
        items=payload["items"],
        actor_id=actor_id,
        reason=payload["reason"],
        changes_factory=changes,
        allowed_statuses={AssetStatus.IDLE.value, AssetStatus.IN_USE.value},
        before_apply=create_repair_records,
    )


def repair_complete(payload: dict[str, Any], actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "asset:repair")

    def changes(asset: Asset, _before: dict[str, Any]) -> dict[str, Any]:
        custom = dict(asset.custom_attributes)
        context = custom.pop("repair_context", {})
        return_status = (
            context.get("return_status", AssetStatus.IDLE.value)
            if isinstance(context, dict)
            else AssetStatus.IDLE.value
        )
        custom["last_repair"] = {
            "result": payload["result"],
            "actual_cost": str(payload["actual_cost"])
            if payload.get("actual_cost") is not None
            else None,
            "completed_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        return {"status": return_status, "custom_attributes": custom}

    def complete_repair_records(assets: list[Asset], command_no: str) -> None:
        completed_at = datetime.now(tz=timezone.utc)
        for asset in assets:
            record = db.session.scalar(
                select(AssetRepairRecord)
                .where(
                    AssetRepairRecord.asset_id == asset.id,
                    AssetRepairRecord.completed_at.is_(None),
                )
                .order_by(AssetRepairRecord.sent_at.desc(), AssetRepairRecord.id.desc())
            )
            if record is None:
                context = dict(asset.custom_attributes).get("repair_context", {})
                before_status = (
                    context.get("return_status", AssetStatus.IDLE.value)
                    if isinstance(context, dict)
                    else AssetStatus.IDLE.value
                )
                record = AssetRepairRecord(
                    asset_id=asset.id,
                    repair_no=command_no,
                    before_status=str(before_status),
                    fault_description="历史维修记录（完成确认）",
                    sent_at=completed_at,
                )
                db.session.add(record)
            record.completed_at = completed_at
            record.repair_result = payload["result"].strip()
            record.confirmed_by = actor_id
            record.confirmed_at = completed_at
            if payload.get("actual_cost") is not None:
                record.repair_cost = payload["actual_cost"]

    return _apply_lifecycle(
        operation_type="REPAIR_COMPLETE",
        items=payload["items"],
        actor_id=actor_id,
        reason=payload["result"],
        changes_factory=changes,
        allowed_statuses={AssetStatus.REPAIRING.value},
        before_apply=complete_repair_records,
    )


def scrap(payload: dict[str, Any], actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "asset:scrap")
    normalized_items: list[dict[str, Any]] = []
    for raw_item in payload["items"]:
        item = dict(raw_item)
        if "disposal_date" not in item and payload.get("scrap_date") is not None:
            item["disposal_date"] = payload["scrap_date"]
        if "scrap_amount" not in item and payload.get("scrap_amount") is not None:
            item["scrap_amount"] = payload["scrap_amount"]
        if "disposition" not in item and "disposition" in payload:
            item["disposition"] = payload.get("disposition")
        if "disposal_date" not in item or "scrap_amount" not in item:
            raise BusinessException("报废资产明细不完整")
        normalized_items.append(item)
    payload = {**payload, "items": normalized_items}
    targets = _targets(normalized_items)
    details = {item["asset_id"]: item for item in normalized_items}
    children = asset_repository.find_direct_children(sorted(targets))
    if children and payload["child_action"] == "BLOCK":
        raise BusinessException("主资产仍有关联附属资产，请选择一并报废或先解除关系")
    detached_children = (
        children if children and payload["child_action"] == "DETACH" else []
    )
    if children and payload["child_action"] == "SCRAP":
        for child in children:
            if child.id in targets:
                continue
            targets[child.id] = child.version
            parent_detail = details.get(child.parent_asset_id or 0)
            if parent_detail is None:
                parent_detail = next(iter(details.values()))
            details[child.id] = {
                "asset_id": child.id,
                "version": child.version,
                "scrap_amount": Decimal("0.00"),
                "disposition": parent_detail.get("disposition"),
                "disposition_remark": parent_detail.get("disposition_remark"),
                "disposal_date": parent_detail["disposal_date"],
            }
        payload = {
            **payload,
            "items": [details[asset_id] for asset_id in targets],
        }

    def detail_for(asset_id: int) -> dict[str, Any]:
        detail = details.get(asset_id)
        if detail is None:
            raise BusinessException("报废资产明细不完整")
        return detail

    def changes(asset: Asset, _before: dict[str, Any]) -> dict[str, Any]:
        detail = detail_for(asset.id)
        disposal_date = detail["disposal_date"]
        scrap_meta = {
            "scrap_date": disposal_date.isoformat()
            if isinstance(disposal_date, date)
            else str(disposal_date),
            "disposal_date": disposal_date.isoformat()
            if isinstance(disposal_date, date)
            else str(disposal_date),
            "scrap_amount": str(detail["scrap_amount"]),
            "disposition": detail.get("disposition"),
            "disposition_remark": detail.get("disposition_remark"),
        }
        custom = dict(asset.custom_attributes)
        custom["scrap"] = scrap_meta
        return {
            "status": AssetStatus.SCRAPPED.value,
            "usage_type": None,
            "holder_user_id": None,
            "public_object_id": None,
            "usage_department_id": None,
            "custom_attributes": custom,
        }

    def create_scrap_records(loaded_assets: list[Asset], command_no: str) -> None:
        confirmed_at = datetime.now(tz=timezone.utc)
        target_ids = set(targets)
        for asset in loaded_assets:
            if asset.id not in target_ids:
                continue
            detail = detail_for(asset.id)
            disposal_date = detail["disposal_date"]
            db.session.add(
                AssetScrapRecord(
                    asset_id=asset.id,
                    scrap_no=command_no,
                    scrap_date=disposal_date,
                    disposal_date=disposal_date,
                    scrap_amount=detail["scrap_amount"],
                    reason=payload["reason"].strip(),
                    disposition=detail.get("disposition"),
                    disposition_remark=detail.get("disposition_remark"),
                    confirmed_by=actor_id,
                    confirmed_at=confirmed_at,
                )
            )

    def detach_children(loaded_assets: list[Asset], command_no: str) -> None:
        child_ids = {child.id for child in detached_children}
        for child in loaded_assets:
            if child.id not in child_ids:
                continue
            before = _asset_snapshot(child)
            child.parent_asset_id = None
            child.version += 1
            audit_service.record_asset_lifecycle(
                asset_id=child.id,
                operation_type="ASSET_RELATION_DETACH",
                request_no=command_no,
                actor_id=actor_id,
                before_data=before,
                after_data=_asset_snapshot(child),
            )
        if child_ids:
            audit_service.record_resource_change(
                action="ASSET_RELATION_DETACH",
                resource_type="asset_relation",
                resource_id=command_no,
                actor_id=actor_id,
                before_data={"child_ids": sorted(child_ids)},
                after_data=None,
                reason="主资产报废时解除主附关系",
            )

    def before_apply(loaded_assets: list[Asset], command_no: str) -> None:
        create_scrap_records(loaded_assets, command_no)
        if detached_children:
            detach_children(loaded_assets, command_no)

    return _apply_lifecycle(
        operation_type="SCRAP",
        items=payload["items"],
        actor_id=actor_id,
        reason=payload["reason"],
        changes_factory=changes,
        allowed_statuses={
            AssetStatus.IDLE.value,
            AssetStatus.IN_USE.value,
            AssetStatus.REPAIRING.value,
        },
        extra_targets={child.id: child.version for child in detached_children},
        before_apply=before_apply,
    )


__all__ = [
    "attach",
    "create_public_object",
    "detach",
    "list_public_objects",
    "relation_tree",
    "repair_complete",
    "repair_start",
    "scrap",
    "transfer",
    "update_batch",
    "update_one",
    "update_public_object",
]
