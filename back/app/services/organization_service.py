"""Organization hierarchy use cases."""

from __future__ import annotations

from typing import Any

from app.common import BusinessException, ResultCode
from app.enums import RecordStatus
from app.extensions import db
from app.models import Organization
from app.repositories.master_data_repository import organization_repository
from app.services import permission_service


def _require(organization_id: int) -> Organization:
    organization = organization_repository.get(organization_id)
    if organization is None:
        raise BusinessException("组织不存在", result_code=ResultCode.NOT_FOUND)
    return organization


def get_descendant_ids(organization_id: int) -> set[int]:
    result = {organization_id}
    frontier = {organization_id}
    while frontier:
        children: set[int] = set()
        for parent_id in frontier:
            children.update(
                item.id for item in organization_repository.find_children(parent_id)
            )
        children -= result
        if not children:
            break
        result.update(children)
        frontier = children
    return result


def get_top_level(organization_id: int) -> Organization:
    current = _require(organization_id)
    visited: set[int] = set()
    while current.parent_id is not None:
        if current.id in visited:
            raise BusinessException("组织层级存在循环")
        visited.add(current.id)
        current = _require(current.parent_id)
    return current


def require_enabled(organization_id: int) -> Organization:
    organization = _require(organization_id)
    if organization.status != RecordStatus.ENABLED.value:
        raise BusinessException("所属组织已停用")
    return organization


def _to_dict(organization: Organization, include_top: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": organization.id,
        "code": organization.code,
        "name": organization.name,
        "parent_id": organization.parent_id,
        "status": organization.status,
        "version": organization.version,
        "created_at": organization.created_at,
        "updated_at": organization.updated_at,
    }
    if include_top:
        top = get_top_level(organization.id)
        result["top_level_id"] = top.id
        result["top_level_code"] = top.code
    return result


def create(payload: dict[str, Any], actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "organization:manage")
    code = str(payload["code"]).strip()
    if organization_repository.find_by_code(code) is not None:
        raise BusinessException("组织编码已存在")
    parent_id = payload.get("parent_id")
    if parent_id is not None:
        _require(parent_id)
        permission_service.require_organization_scope(actor_id, parent_id)
    elif permission_service.accessible_organization_ids(actor_id) is not None:
        raise BusinessException(
            "只有全量数据权限可以创建顶级组织", result_code=ResultCode.FORBIDDEN
        )
    organization = Organization(
        code=code, name=str(payload["name"]).strip(), parent_id=parent_id
    )
    organization_repository.add(organization)
    db.session.commit()
    return _to_dict(organization)


def update(
    organization_id: int, payload: dict[str, Any], actor_id: int
) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "organization:manage")
    permission_service.require_organization_scope(actor_id, organization_id)
    organization = _require(organization_id)
    if organization.version != payload["version"]:
        raise BusinessException("组织数据已被其他人修改，请刷新后重试")
    if "parent_id" in payload:
        parent_id = payload["parent_id"]
        if parent_id == organization.id:
            raise BusinessException("组织不能选择自己作为上级")
        if parent_id is not None:
            _require(parent_id)
            if parent_id in get_descendant_ids(organization.id):
                raise BusinessException("不能把组织移动到自己的下级组织")
            permission_service.require_organization_scope(actor_id, parent_id)
        organization.parent_id = parent_id
    organization.name = str(payload["name"]).strip()
    organization.version += 1
    db.session.commit()
    return _to_dict(organization)


def set_enabled(organization_id: int, enabled: bool, actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "organization:manage")
    permission_service.require_organization_scope(actor_id, organization_id)
    organization = _require(organization_id)
    organization.status = (
        RecordStatus.ENABLED.value if enabled else RecordStatus.DISABLED.value
    )
    organization.version += 1
    db.session.commit()
    return _to_dict(organization)


def get(organization_id: int, actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "organization:view")
    permission_service.require_organization_scope(actor_id, organization_id)
    return _to_dict(_require(organization_id), include_top=True)


def tree(actor_id: int) -> list[dict[str, Any]]:
    permission_service.require_permission(actor_id, "organization:view")
    allowed = permission_service.accessible_organization_ids(actor_id)
    organizations = organization_repository.list_all()
    if allowed is not None:
        organizations = [item for item in organizations if item.id in allowed]
    by_parent: dict[int | None, list[Organization]] = {}
    visible_ids = {item.id for item in organizations}
    for item in organizations:
        parent_key = item.parent_id if item.parent_id in visible_ids else None
        by_parent.setdefault(parent_key, []).append(item)

    def build(item: Organization) -> dict[str, Any]:
        node = _to_dict(item)
        node["children"] = [build(child) for child in by_parent.get(item.id, [])]
        return node

    return [build(item) for item in by_parent.get(None, [])]


__all__ = [
    "create",
    "get",
    "get_descendant_ids",
    "get_top_level",
    "require_enabled",
    "set_enabled",
    "tree",
    "update",
]
