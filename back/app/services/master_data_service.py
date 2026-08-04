"""Asset category, unit, source, and location use cases."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, NoReturn

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.common import BusinessException, ResultCode
from app.enums import RecordStatus
from app.extensions import db
from app.models import (
    Asset,
    AssetCategory,
    AssetCodeSequence,
    AssetLifecycleRecord,
    AssetLocation,
    AssetReturnRequest,
    AssetSource,
    AssetUsageRequest,
    InventoryItem,
    InventoryTask,
    OperationLog,
    StockInItem,
    Unit,
)
from app.repositories.master_data_repository import (
    asset_category_repository,
    asset_location_repository,
    location_code_sequence_repository,
    asset_source_repository,
    unit_repository,
)
from app.repositories.rbac_repository import rbac_repository
from app.services import audit_service, permission_service


def _reference_dict(item: Unit | AssetSource) -> dict[str, Any]:
    return {
        "id": item.id,
        "code": item.code,
        "name": item.name,
        "status": item.status,
        "version": item.version,
    }


def _require_unit(unit_id: int, enabled: bool = False) -> Unit:
    unit = unit_repository.get(unit_id)
    if unit is None or (enabled and unit.status != RecordStatus.ENABLED.value):
        raise BusinessException("计量单位不存在或已停用")
    return unit


def _require_source(source_id: int, enabled: bool = False) -> AssetSource:
    source = asset_source_repository.get(source_id)
    if source is None or (enabled and source.status != RecordStatus.ENABLED.value):
        raise BusinessException("资产来源不存在或已停用")
    return source


def _require_location(
    location_id: int, selectable: bool = False, enabled: bool = False
) -> AssetLocation:
    location = asset_location_repository.get(location_id)
    if location is None or (
        (enabled or selectable) and location.status != RecordStatus.ENABLED.value
    ):
        raise BusinessException("存放地点不存在或已停用")
    if selectable and not location.is_selectable:
        raise BusinessException("该地点不允许存放资产")
    return location


def _require_category(category_id: int, enabled: bool = False) -> AssetCategory:
    category = asset_category_repository.get(category_id)
    if category is None or (enabled and category.status != RecordStatus.ENABLED.value):
        raise BusinessException("资产分类不存在或已停用")
    return category


def require_enabled_unit(unit_id: int) -> Unit:
    return _require_unit(unit_id, enabled=True)


def require_enabled_source(source_id: int) -> AssetSource:
    return _require_source(source_id, enabled=True)


def require_selectable_location(location_id: int) -> AssetLocation:
    return _require_location(location_id, selectable=True)


def require_enabled_category(category_id: int) -> AssetCategory:
    return _require_category(category_id, enabled=True)


def create_unit(payload: dict[str, Any], actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "unit:manage")
    code = str(payload["code"]).strip()
    if unit_repository.find_by_code(code) is not None:
        raise BusinessException("计量单位编码已存在")
    unit = Unit(code=code, name=str(payload["name"]).strip())
    unit_repository.add(unit)
    db.session.commit()
    return _reference_dict(unit)


def list_units(actor_id: int) -> list[dict[str, Any]]:
    permission_service.require_permission(actor_id, "unit:view")
    return [_reference_dict(item) for item in unit_repository.list_all()]


def set_unit_enabled(unit_id: int, enabled: bool, actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "unit:manage")
    unit = _require_unit(unit_id)
    unit.status = RecordStatus.ENABLED.value if enabled else RecordStatus.DISABLED.value
    unit.version += 1
    db.session.commit()
    return _reference_dict(unit)


def update_unit(unit_id: int, payload: dict[str, Any], actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "unit:manage")
    unit = _require_unit(unit_id)
    if unit.version != payload["version"]:
        raise BusinessException("计量单位已被其他人修改，请刷新后重试")
    unit.name = str(payload["name"]).strip()
    unit.version += 1
    db.session.commit()
    return _reference_dict(unit)


def create_source(payload: dict[str, Any], actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "asset-source:manage")
    code = str(payload["code"]).strip()
    if asset_source_repository.find_by_code(code) is not None:
        raise BusinessException("资产来源编码已存在")
    source = AssetSource(code=code, name=str(payload["name"]).strip())
    asset_source_repository.add(source)
    db.session.commit()
    return _reference_dict(source)


def list_sources(actor_id: int) -> list[dict[str, Any]]:
    permission_service.require_permission(actor_id, "asset-source:view")
    return [_reference_dict(item) for item in asset_source_repository.list_all()]


def set_source_enabled(source_id: int, enabled: bool, actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "asset-source:manage")
    source = _require_source(source_id)
    source.status = (
        RecordStatus.ENABLED.value if enabled else RecordStatus.DISABLED.value
    )
    source.version += 1
    db.session.commit()
    return _reference_dict(source)


def update_source(
    source_id: int, payload: dict[str, Any], actor_id: int
) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "asset-source:manage")
    source = _require_source(source_id)
    if source.version != payload["version"]:
        raise BusinessException("资产来源已被其他人修改，请刷新后重试")
    source.name = str(payload["name"]).strip()
    source.version += 1
    db.session.commit()
    return _reference_dict(source)


def _location_path(location: AssetLocation) -> str:
    names = [location.name]
    visited = {location.id}
    current = location
    while current.parent_id is not None:
        current = _require_location(current.parent_id)
        if current.id in visited:
            raise BusinessException("地点层级存在循环")
        visited.add(current.id)
        names.append(current.name)
    return "/".join(reversed(names))


def _location_dict(location: AssetLocation) -> dict[str, Any]:
    return {
        "id": location.id,
        "code": location.code,
        "name": location.name,
        "parent_id": location.parent_id,
        "status": location.status,
        "is_selectable": location.is_selectable,
        "full_path": _location_path(location),
        "version": location.version,
    }


def _allocate_location_code() -> str:
    location_code_sequence_repository.ensure_exists()
    sequence = location_code_sequence_repository.find_for_update()
    if sequence is None:
        raise RuntimeError("location code sequence initialization failed")
    sequence.current_value += 1
    return f"{sequence.prefix}{sequence.current_value:06d}"


def create_location(payload: dict[str, Any], actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "location:manage")
    name = str(payload["name"]).strip()
    parent_id = payload.get("parent_id")
    if parent_id is not None:
        _require_location(parent_id, enabled=True)
    if asset_location_repository.find_sibling(parent_id, name) is not None:
        raise BusinessException("同一上级地点下名称不能重复")
    location = AssetLocation(
        code=_allocate_location_code(),
        name=name,
        parent_id=parent_id,
        is_selectable=bool(payload.get("is_selectable", True)),
    )
    asset_location_repository.add(location)
    db.session.commit()
    return _location_dict(location)


def _location_descendant_ids(location_id: int) -> set[int]:
    items = asset_location_repository.list_all()
    by_parent: dict[int | None, list[int]] = {}
    for item in items:
        by_parent.setdefault(item.parent_id, []).append(item.id)
    result = {location_id}
    frontier = [location_id]
    while frontier:
        current = frontier.pop()
        for child_id in by_parent.get(current, []):
            if child_id not in result:
                result.add(child_id)
                frontier.append(child_id)
    return result


def update_location(
    location_id: int, payload: dict[str, Any], actor_id: int
) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "location:manage")
    location = _require_location(location_id)
    if location.version != payload["version"]:
        raise BusinessException("地点已被其他人修改，请刷新后重试")
    parent_id = payload.get("parent_id", location.parent_id)
    if parent_id == location.id or (
        parent_id is not None and parent_id in _location_descendant_ids(location.id)
    ):
        raise BusinessException("不能把地点移动到自己或自己的下级")
    if parent_id is not None:
        _require_location(parent_id)
    name = str(payload["name"]).strip()
    sibling = asset_location_repository.find_sibling(parent_id, name)
    if sibling is not None and sibling.id != location.id:
        raise BusinessException("同一上级地点下名称不能重复")
    location.name = name
    location.parent_id = parent_id
    location.is_selectable = payload["is_selectable"]
    location.version += 1
    db.session.commit()
    return _location_dict(location)


def set_location_enabled(
    location_id: int, enabled: bool, actor_id: int
) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "location:manage")
    location = _require_location(location_id)
    location.status = (
        RecordStatus.ENABLED.value if enabled else RecordStatus.DISABLED.value
    )
    location.version += 1
    db.session.commit()
    return _location_dict(location)


def location_tree(actor_id: int) -> list[dict[str, Any]]:
    permission_service.require_permission(actor_id, "location:view")
    items = asset_location_repository.list_all()
    by_parent: dict[int | None, list[AssetLocation]] = {}
    for item in items:
        by_parent.setdefault(item.parent_id, []).append(item)

    def build(item: AssetLocation) -> dict[str, Any]:
        node = _location_dict(item)
        node["children"] = [build(child) for child in by_parent.get(item.id, [])]
        return node

    return [build(item) for item in by_parent.get(None, [])]


def _category_dict(category: AssetCategory) -> dict[str, Any]:
    unit = _require_unit(category.default_unit_id)
    return {
        "id": category.id,
        "code": category.code,
        "name": category.name,
        "parent_id": category.parent_id,
        "service_life_months": category.service_life_months,
        "default_unit_id": category.default_unit_id,
        "default_unit_name": unit.name,
        "status": category.status,
        "version": category.version,
    }


def create_category(payload: dict[str, Any], actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "asset-category:manage")
    code = str(payload["code"]).strip()
    if asset_category_repository.find_by_code(code) is not None:
        raise BusinessException("资产分类编码已存在")
    parent_id = payload.get("parent_id")
    if parent_id is not None:
        _require_category(parent_id, enabled=True)
    _require_unit(payload["default_unit_id"], enabled=True)
    category = AssetCategory(
        code=code,
        name=str(payload["name"]).strip(),
        parent_id=parent_id,
        service_life_months=payload["service_life_months"],
        default_unit_id=payload["default_unit_id"],
    )
    asset_category_repository.add(category)
    db.session.commit()
    return _category_dict(category)


def _category_descendant_ids(category_id: int) -> set[int]:
    items = asset_category_repository.list_all()
    by_parent: dict[int | None, list[int]] = {}
    for item in items:
        by_parent.setdefault(item.parent_id, []).append(item.id)
    result = {category_id}
    frontier = [category_id]
    while frontier:
        current = frontier.pop()
        for child_id in by_parent.get(current, []):
            if child_id not in result:
                result.add(child_id)
                frontier.append(child_id)
    return result


def update_category(
    category_id: int, payload: dict[str, Any], actor_id: int
) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "asset-category:manage")
    category = _require_category(category_id)
    if category.version != payload["version"]:
        raise BusinessException("资产分类已被其他人修改，请刷新后重试")
    parent_id = payload.get("parent_id", category.parent_id)
    if parent_id == category.id or (
        parent_id is not None and parent_id in _category_descendant_ids(category.id)
    ):
        raise BusinessException("不能把分类移动到自己或自己的下级")
    if parent_id is not None:
        _require_category(parent_id, enabled=True)
    _require_unit(payload["default_unit_id"], enabled=True)
    category.name = str(payload["name"]).strip()
    category.parent_id = parent_id
    category.service_life_months = payload["service_life_months"]
    category.default_unit_id = payload["default_unit_id"]
    category.version += 1
    db.session.commit()
    return _category_dict(category)


def set_category_enabled(
    category_id: int, enabled: bool, actor_id: int
) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "asset-category:manage")
    category = _require_category(category_id)
    category.status = (
        RecordStatus.ENABLED.value if enabled else RecordStatus.DISABLED.value
    )
    category.version += 1
    db.session.commit()
    return _category_dict(category)


def _require_super_admin(actor_id: int) -> None:
    if "SUPER_ADMIN" not in rbac_repository.role_codes_for_user(actor_id):
        raise BusinessException(
            "仅超级管理员可以执行删除操作", result_code=ResultCode.FORBIDDEN
        )


def _count_rows(model: type[Any], *conditions: Any) -> int:
    return int(
        db.session.scalar(select(func.count()).select_from(model).where(*conditions))
        or 0
    )


def _json_contains_identifier(value: object, keys: set[str], target_id: int) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in keys:
                if isinstance(child, list) and target_id in child:
                    return True
                if child == target_id:
                    return True
            if _json_contains_identifier(child, keys, target_id):
                return True
        return False
    if isinstance(value, list):
        return any(_json_contains_identifier(item, keys, target_id) for item in value)
    return False


def _count_json_references(
    rows: Iterable[tuple[object | None, ...]], keys: set[str], target_id: int
) -> int:
    return sum(
        1
        for row in rows
        if any(_json_contains_identifier(value, keys, target_id) for value in row)
    )


def _json_reference_counts(keys: set[str], target_id: int) -> tuple[int, int, int]:
    inventory_tasks = _count_json_references(
        db.session.execute(select(InventoryTask.scope_filters)).tuples(),
        keys,
        target_id,
    )
    operation_logs = _count_json_references(
        db.session.execute(
            select(OperationLog.before_data, OperationLog.after_data)
        ).tuples(),
        keys,
        target_id,
    )
    lifecycle_records = _count_json_references(
        db.session.execute(
            select(AssetLifecycleRecord.before_data, AssetLifecycleRecord.after_data)
        ).tuples(),
        keys,
        target_id,
    )
    return inventory_tasks, operation_logs, lifecycle_records


def _reference_item(key: str, label: str, count: int) -> dict[str, Any]:
    return {"key": key, "label": label, "count": count}


def location_delete_impact(location_id: int, actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "location:delete")
    _require_super_admin(actor_id)
    location = _require_location(location_id)
    child_count = _count_rows(AssetLocation, AssetLocation.parent_id == location.id)
    asset_count = _count_rows(Asset, Asset.location_id == location.id)
    stock_in_count = _count_rows(StockInItem, StockInItem.location_id == location.id)
    usage_request_count = _count_rows(
        AssetUsageRequest, AssetUsageRequest.target_location_id == location.id
    )
    return_request_count = _count_rows(
        AssetReturnRequest, AssetReturnRequest.return_location_id == location.id
    )
    inventory_item_count = _count_rows(
        InventoryItem,
        or_(
            InventoryItem.ledger_location_id == location.id,
            InventoryItem.actual_location_id == location.id,
        ),
    )
    inventory_task_count, operation_log_count, lifecycle_count = _json_reference_counts(
        {
            "location_id",
            "location_ids",
            "target_location_id",
            "return_location_id",
            "ledger_location_id",
            "actual_location_id",
        },
        location.id,
    )
    references = [
        _reference_item("children", "下级地点", child_count),
        _reference_item("assets", "当前资产", asset_count),
        _reference_item("stock_in_items", "入库明细", stock_in_count),
        _reference_item("usage_requests", "领用申请", usage_request_count),
        _reference_item("return_requests", "退还申请", return_request_count),
        _reference_item("inventory_items", "盘点明细", inventory_item_count),
        _reference_item("inventory_tasks", "盘点任务范围", inventory_task_count),
        _reference_item("operation_logs", "操作审计记录", operation_log_count),
        _reference_item("lifecycle_records", "资产履历", lifecycle_count),
    ]
    blockers = [
        f"仍有 {item['count']} 条{item['label']}引用该地点"
        for item in references
        if item["count"]
    ]
    return {
        "entity_id": location.id,
        "code": location.code,
        "name": location.name,
        "version": location.version,
        "can_delete": not blockers,
        "blockers": blockers,
        "references": references,
    }


def category_delete_impact(category_id: int, actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "asset-category:delete")
    _require_super_admin(actor_id)
    category = _require_category(category_id)
    child_count = _count_rows(AssetCategory, AssetCategory.parent_id == category.id)
    asset_count = _count_rows(Asset, Asset.category_id == category.id)
    stock_in_count = _count_rows(StockInItem, StockInItem.category_id == category.id)
    inventory_item_count = _count_rows(
        InventoryItem, InventoryItem.category_id == category.id
    )
    code_sequence_count = _count_rows(
        AssetCodeSequence, AssetCodeSequence.category_id == category.id
    )
    inventory_task_count, operation_log_count, lifecycle_count = _json_reference_counts(
        {"category_id", "category_ids"}, category.id
    )
    references = [
        _reference_item("children", "下级分类", child_count),
        _reference_item("assets", "当前资产", asset_count),
        _reference_item("stock_in_items", "入库明细", stock_in_count),
        _reference_item("inventory_items", "盘点明细", inventory_item_count),
        _reference_item("asset_code_sequences", "资产编码流水", code_sequence_count),
        _reference_item("inventory_tasks", "盘点任务范围", inventory_task_count),
        _reference_item("operation_logs", "操作审计记录", operation_log_count),
        _reference_item("lifecycle_records", "资产履历", lifecycle_count),
    ]
    blockers = [
        f"仍有 {item['count']} 条{item['label']}引用该分类"
        for item in references
        if item["count"]
    ]
    return {
        "entity_id": category.id,
        "code": category.code,
        "name": category.name,
        "version": category.version,
        "can_delete": not blockers,
        "blockers": blockers,
        "references": references,
    }


def _raise_delete_integrity(entity_name: str, error: IntegrityError) -> NoReturn:
    db.session.rollback()
    context = f"{error.statement or ''} {error.orig}".lower()
    if (
        "foreign key constraint failed" in context
        or "cannot delete or update" in context
    ):
        raise BusinessException(f"{entity_name}已被使用，不能删除") from None
    raise BusinessException(
        f"{entity_name}删除失败，请稍后重试", result_code=ResultCode.INTERNAL_ERROR
    ) from None


def delete_location(
    location_id: int, payload: dict[str, Any], actor_id: int
) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "location:delete")
    _require_super_admin(actor_id)
    location = _require_location(location_id)
    if location.version != payload["version"]:
        raise BusinessException("地点已被其他人修改，请刷新后重试")
    impact = location_delete_impact(location_id, actor_id)
    if not impact["can_delete"]:
        raise BusinessException("；".join(impact["blockers"]))
    before_data = _location_dict(location)
    try:
        db.session.delete(location)
        audit_service.record_resource_change(
            action="LOCATION_DELETE",
            resource_type="asset_location",
            resource_id=location.id,
            actor_id=actor_id,
            before_data=before_data,
            after_data={"deleted": True, "impact": impact},
            reason=str(payload["reason"]).strip(),
        )
        db.session.commit()
    except IntegrityError as error:
        _raise_delete_integrity("地点", error)
    return {"id": location_id, "deleted": True}


def delete_category(
    category_id: int, payload: dict[str, Any], actor_id: int
) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "asset-category:delete")
    _require_super_admin(actor_id)
    category = _require_category(category_id)
    if category.version != payload["version"]:
        raise BusinessException("资产分类已被其他人修改，请刷新后重试")
    impact = category_delete_impact(category_id, actor_id)
    if not impact["can_delete"]:
        raise BusinessException("；".join(impact["blockers"]))
    before_data = _category_dict(category)
    try:
        db.session.delete(category)
        audit_service.record_resource_change(
            action="ASSET_CATEGORY_DELETE",
            resource_type="asset_category",
            resource_id=category.id,
            actor_id=actor_id,
            before_data=before_data,
            after_data={"deleted": True, "impact": impact},
            reason=str(payload["reason"]).strip(),
        )
        db.session.commit()
    except IntegrityError as error:
        _raise_delete_integrity("资产分类", error)
    return {"id": category_id, "deleted": True}


def category_tree(actor_id: int) -> list[dict[str, Any]]:
    permission_service.require_permission(actor_id, "asset-category:view")
    items = asset_category_repository.list_all()
    by_parent: dict[int | None, list[AssetCategory]] = {}
    for item in items:
        by_parent.setdefault(item.parent_id, []).append(item)

    def build(item: AssetCategory) -> dict[str, Any]:
        node = _category_dict(item)
        node["children"] = [build(child) for child in by_parent.get(item.id, [])]
        return node

    return [build(item) for item in by_parent.get(None, [])]


__all__ = [
    "location_delete_impact",
    "delete_location",
    "delete_category",
    "category_delete_impact",
    "category_tree",
    "create_category",
    "create_location",
    "create_source",
    "create_unit",
    "list_sources",
    "list_units",
    "location_tree",
    "require_enabled_category",
    "require_enabled_source",
    "require_enabled_unit",
    "require_selectable_location",
    "set_source_enabled",
    "set_unit_enabled",
    "set_category_enabled",
    "set_location_enabled",
    "update_category",
    "update_location",
    "update_source",
    "update_unit",
]
