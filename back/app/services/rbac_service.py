"""Administrative RBAC use cases."""

from __future__ import annotations

from typing import Any

from app.common import BusinessException, ResultCode
from app.enums import DataScope
from app.extensions import db
from app.models import Permission, Role
from app.repositories import rbac_repository
from app.services import permission_service, user_service


def _role_to_dict(role: Role) -> dict[str, Any]:
    return {
        "id": role.id,
        "code": role.code,
        "name": role.name,
        "data_scope": role.data_scope,
        "built_in": role.built_in,
        "enabled": role.enabled,
        "version": role.version,
        "permissions": rbac_repository.permission_codes_for_role(role.id),
        "organization_ids": rbac_repository.custom_organization_ids_for_role(role.id),
    }


def _permission_to_dict(permission: Permission) -> dict[str, Any]:
    return {
        "id": permission.id,
        "code": permission.code,
        "name": permission.name,
        "module": permission.module,
        "enabled": permission.enabled,
    }


def list_roles(actor_id: int) -> list[dict[str, Any]]:
    permission_service.require_permission(actor_id, "system:role:view")
    return [_role_to_dict(role) for role in rbac_repository.list_roles()]


def list_permissions(actor_id: int) -> list[dict[str, Any]]:
    permission_service.require_permission(actor_id, "system:role:view")
    return [_permission_to_dict(item) for item in rbac_repository.list_permissions()]


def create_role(payload: dict[str, Any], actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "system:role:manage")
    code = str(payload["code"]).strip().upper()
    if rbac_repository.find_role_by_code(code) is not None:
        raise BusinessException("角色编码已存在")
    data_scope = str(payload["data_scope"])
    if data_scope not in {item.value for item in DataScope}:
        raise BusinessException("数据范围无效", result_code=ResultCode.BAD_REQUEST)
    role = Role(
        code=code,
        name=str(payload["name"]).strip(),
        data_scope=data_scope,
        built_in=False,
        enabled=True,
    )
    db.session.add(role)
    db.session.commit()
    return _role_to_dict(role)


def update_role_permissions(
    role_id: int, permission_ids: list[int], actor_id: int
) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "system:role:manage")
    role = rbac_repository.get_role(role_id)
    if role is None:
        raise BusinessException("角色不存在", result_code=ResultCode.NOT_FOUND)
    unique_ids = sorted(set(permission_ids))
    if len(rbac_repository.get_permissions(unique_ids)) != len(unique_ids):
        raise BusinessException("包含不存在的权限", result_code=ResultCode.BAD_REQUEST)
    rbac_repository.replace_role_permissions(role_id, unique_ids)
    db.session.commit()
    return _role_to_dict(role)


def update_role(role_id: int, payload: dict[str, Any], actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "system:role:manage")
    role = rbac_repository.get_role(role_id)
    if role is None:
        raise BusinessException("角色不存在", result_code=ResultCode.NOT_FOUND)
    if role.version != payload["version"]:
        raise BusinessException("角色已被其他人修改，请刷新后重试")
    data_scope = str(payload["data_scope"])
    if data_scope not in {item.value for item in DataScope}:
        raise BusinessException("数据范围无效", result_code=ResultCode.BAD_REQUEST)
    organization_ids = sorted(set(payload.get("organization_ids", [])))
    if data_scope == DataScope.CUSTOM.value:
        if not organization_ids:
            raise BusinessException("自定义数据范围至少选择一个组织")
        from app.models import Organization

        organizations = [
            db.session.get(Organization, item) for item in organization_ids
        ]
        if any(item is None for item in organizations):
            raise BusinessException(
                "包含不存在的组织", result_code=ResultCode.BAD_REQUEST
            )
    else:
        organization_ids = []
    role.name = str(payload["name"]).strip()
    role.data_scope = data_scope
    role.enabled = bool(payload["enabled"])
    role.version += 1
    rbac_repository.replace_role_scope_organizations(role.id, organization_ids)
    db.session.commit()
    return _role_to_dict(role)


def update_user_roles(
    user_id: int, role_ids: list[int], actor_id: int
) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "system:role:manage")
    user = rbac_repository.find_user(user_id)
    if user is None:
        raise BusinessException("用户不存在", result_code=ResultCode.NOT_FOUND)
    unique_ids = sorted(set(role_ids))
    if len(rbac_repository.get_roles(unique_ids)) != len(unique_ids):
        raise BusinessException("包含不存在的角色", result_code=ResultCode.BAD_REQUEST)
    rbac_repository.replace_user_roles(user_id, unique_ids)
    db.session.commit()
    return user_service.get_current(user_id)


__all__ = [
    "create_role",
    "list_permissions",
    "list_roles",
    "update_role_permissions",
    "update_role",
    "update_user_roles",
]
