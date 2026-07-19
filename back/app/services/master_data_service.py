"""Asset category, unit, source, and location use cases."""

from __future__ import annotations

from typing import Any

from app.common import BusinessException
from app.enums import RecordStatus
from app.extensions import db
from app.models import AssetCategory, AssetLocation, AssetSource, Unit
from app.repositories.master_data_repository import (
    asset_category_repository,
    asset_location_repository,
    asset_source_repository,
    unit_repository,
)
from app.services import permission_service


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


def create_location(payload: dict[str, Any], actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "location:manage")
    code = str(payload["code"]).strip()
    name = str(payload["name"]).strip()
    parent_id = payload.get("parent_id")
    if asset_location_repository.find_by_code(code) is not None:
        raise BusinessException("地点编码已存在")
    if parent_id is not None:
        _require_location(parent_id, enabled=True)
    if asset_location_repository.find_sibling(parent_id, name) is not None:
        raise BusinessException("同一上级地点下名称不能重复")
    location = AssetLocation(
        code=code,
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
