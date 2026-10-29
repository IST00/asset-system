"""Administrative RBAC use cases."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from app.common import BusinessException, ResultCode
from app.enums import AssigneeType, DataScope
from app.extensions import db
from app.models import ApprovalFlowAssigneeRule, Permission, Role, UserRole
from app.repositories import rbac_repository
from app.services import audit_service, permission_service, user_service


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


def _user_role_snapshot(user_id: int) -> dict[str, Any]:
    user = rbac_repository.find_user(user_id)
    if user is None:
        raise BusinessException("用户不存在", result_code=ResultCode.NOT_FOUND)
    return {
        "id": user.id,
        "username": user.username,
        "role_codes": rbac_repository.role_codes_for_user(user.id),
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
    db.session.flush()
    after_data = _role_to_dict(role)
    audit_service.record_resource_change(
        action="ROLE_CREATE",
        resource_type="role",
        resource_id=role.id,
        actor_id=actor_id,
        before_data=None,
        after_data=after_data,
        reason=payload.get("reason"),
    )
    db.session.commit()
    return after_data


_BUILTIN_ROLE_HIERARCHY = (
    ("USER", "ASSET_ADMIN"),
    ("USER", "SUPER_ADMIN"),
    ("ASSET_ADMIN", "SUPER_ADMIN"),
)


def _synchronize_builtin_role_hierarchy() -> None:
    role_ids = {role.code: role.id for role in rbac_repository.list_roles()}
    for source_code, target_code in _BUILTIN_ROLE_HIERARCHY:
        source_id = role_ids.get(source_code)
        target_id = role_ids.get(target_code)
        if source_id is not None and target_id is not None:
            rbac_repository.inherit_role_permissions(source_id, target_id)


def _validate_builtin_role_permission_subset(
    role: Role, permission_ids: list[int]
) -> None:
    lower_codes = {
        "ASSET_ADMIN": ("USER",),
        "SUPER_ADMIN": ("ASSET_ADMIN", "USER"),
    }.get(role.code, ())
    selected_ids = set(permission_ids)
    for code in lower_codes:
        lower_role = rbac_repository.find_role_by_code(code)
        if lower_role is None:
            continue
        missing_ids = (
            rbac_repository.permission_ids_for_role(lower_role.id) - selected_ids
        )
        if missing_ids:
            raise BusinessException(
                f"{role.name} 的权限必须包含 {lower_role.name} 的全部权限",
                result_code=ResultCode.BAD_REQUEST,
            )


def _require_super_admin_to_manage_super_admin_user(
    actor_id: int, user_role_codes: list[str]
) -> None:
    if "SUPER_ADMIN" not in user_role_codes:
        return
    if "SUPER_ADMIN" not in rbac_repository.role_codes_for_user(actor_id):
        raise BusinessException(
            "只有超级管理员可以修改超级管理员账号角色",
            result_code=ResultCode.FORBIDDEN,
        )


def _require_super_admin_to_configure_super_admin(actor_id: int, role: Role) -> None:
    if role.code != "SUPER_ADMIN":
        return
    if "SUPER_ADMIN" not in rbac_repository.role_codes_for_user(actor_id):
        raise BusinessException(
            "只有超级管理员可以修改超级管理员角色配置",
            result_code=ResultCode.FORBIDDEN,
        )


def update_role_permissions(
    role_id: int,
    permission_ids: list[int],
    actor_id: int,
    reason: str | None = None,
) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "system:role:manage")
    role = rbac_repository.get_role(role_id)
    if role is None:
        raise BusinessException("角色不存在", result_code=ResultCode.NOT_FOUND)
    _require_super_admin_to_configure_super_admin(actor_id, role)
    before_data = _role_to_dict(role)
    unique_ids = sorted(set(permission_ids))
    if len(rbac_repository.get_permissions(unique_ids)) != len(unique_ids):
        raise BusinessException("包含不存在的权限", result_code=ResultCode.BAD_REQUEST)
    _validate_builtin_role_permission_subset(role, unique_ids)
    rbac_repository.replace_role_permissions(role_id, unique_ids)
    _synchronize_builtin_role_hierarchy()
    db.session.flush()
    after_data = _role_to_dict(role)
    audit_service.record_resource_change(
        action="ROLE_PERMISSIONS_UPDATE",
        resource_type="role",
        resource_id=role.id,
        actor_id=actor_id,
        before_data=before_data,
        after_data=after_data,
        reason=reason,
    )
    db.session.commit()
    return after_data


def update_role(role_id: int, payload: dict[str, Any], actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "system:role:manage")
    role = rbac_repository.get_role(role_id)
    if role is None:
        raise BusinessException("角色不存在", result_code=ResultCode.NOT_FOUND)
    _require_super_admin_to_configure_super_admin(actor_id, role)
    before_data = _role_to_dict(role)
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
    db.session.flush()
    after_data = _role_to_dict(role)
    audit_service.record_resource_change(
        action="ROLE_UPDATE",
        resource_type="role",
        resource_id=role.id,
        actor_id=actor_id,
        before_data=before_data,
        after_data=after_data,
        reason=payload.get("reason"),
    )
    db.session.commit()
    return after_data


def role_delete_impact(role_id: int, actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "system:role:manage")
    role = rbac_repository.get_role(role_id)
    if role is None:
        raise BusinessException("角色不存在", result_code=ResultCode.NOT_FOUND)
    user_count = int(
        db.session.scalar(
            select(func.count())
            .select_from(UserRole)
            .where(UserRole.role_id == role.id)
        )
        or 0
    )
    approval_flow_rule_count = int(
        db.session.scalar(
            select(func.count())
            .select_from(ApprovalFlowAssigneeRule)
            .where(
                ApprovalFlowAssigneeRule.assignee_type == AssigneeType.ROLE.value,
                ApprovalFlowAssigneeRule.assignee_id == role.id,
            )
        )
        or 0
    )
    blockers: list[str] = []
    if role.built_in:
        blockers.append("系统内置角色不能删除")
    if user_count:
        blockers.append(f"仍有 {user_count} 名用户使用该角色")
    if approval_flow_rule_count:
        blockers.append(f"仍有 {approval_flow_rule_count} 条审批规则引用该角色")
    return {
        "role_id": role.id,
        "role_code": role.code,
        "role_name": role.name,
        "version": role.version,
        "can_delete": not blockers,
        "blockers": blockers,
        "references": [
            {"key": "users", "label": "已授权用户", "count": user_count},
            {
                "key": "approval_flow_rules",
                "label": "审批流程规则",
                "count": approval_flow_rule_count,
            },
            {
                "key": "permissions",
                "label": "将一并移除的权限点",
                "count": len(rbac_repository.permission_codes_for_role(role.id)),
            },
            {
                "key": "organizations",
                "label": "将一并移除的自定义组织范围",
                "count": len(rbac_repository.custom_organization_ids_for_role(role.id)),
            },
        ],
    }


def delete_role(role_id: int, payload: dict[str, Any], actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "system:role:manage")
    role = rbac_repository.get_role(role_id)
    if role is None:
        raise BusinessException("角色不存在", result_code=ResultCode.NOT_FOUND)
    if role.version != payload["version"]:
        raise BusinessException("角色已被其他人修改，请刷新后重试")
    impact = role_delete_impact(role_id, actor_id)
    if not impact["can_delete"]:
        raise BusinessException("；".join(impact["blockers"]))
    before_data = _role_to_dict(role)
    audit_service.record_resource_change(
        action="ROLE_DELETE",
        resource_type="role",
        resource_id=role.id,
        actor_id=actor_id,
        before_data=before_data,
        after_data={"deleted": True, "impact": impact},
        reason=str(payload["reason"]).strip(),
    )
    db.session.delete(role)
    db.session.commit()
    return {"id": role_id, "deleted": True}


def update_user_roles(
    user_id: int,
    role_ids: list[int],
    actor_id: int,
    reason: str | None = None,
) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "system:role:manage")
    user = rbac_repository.find_user(user_id)
    if user is None:
        raise BusinessException("用户不存在", result_code=ResultCode.NOT_FOUND)
    before_data = _user_role_snapshot(user_id)
    _require_super_admin_to_manage_super_admin_user(actor_id, before_data["role_codes"])
    unique_ids = sorted(set(role_ids))
    if len(unique_ids) != 1:
        raise BusinessException(
            "每个账号只能分配一个角色", result_code=ResultCode.BAD_REQUEST
        )
    selected_roles = rbac_repository.get_roles(unique_ids)
    if len(selected_roles) != len(unique_ids):
        raise BusinessException("包含不存在的角色", result_code=ResultCode.BAD_REQUEST)
    selected_role = selected_roles[0]
    actor_role_codes = rbac_repository.role_codes_for_user(actor_id)
    if selected_role.code == "SUPER_ADMIN" and "SUPER_ADMIN" not in actor_role_codes:
        raise BusinessException(
            "只有超级管理员可以授权超级管理员",
            result_code=ResultCode.FORBIDDEN,
        )
    rbac_repository.replace_user_roles(user_id, unique_ids)
    db.session.flush()
    after_data = _user_role_snapshot(user_id)
    audit_service.record_resource_change(
        action="USER_ROLES_UPDATE",
        resource_type="user",
        resource_id=user_id,
        actor_id=actor_id,
        before_data=before_data,
        after_data=after_data,
        reason=reason,
    )
    db.session.commit()
    return user_service.get_current(user_id)


__all__ = [
    "create_role",
    "delete_role",
    "list_permissions",
    "list_roles",
    "role_delete_impact",
    "update_role_permissions",
    "update_role",
    "update_user_roles",
]
