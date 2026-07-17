"""Functional permission and organization-scope rules."""

from __future__ import annotations

from sqlalchemy import select

from app.common import BusinessException, ResultCode
from app.enums import DataScope
from app.extensions import db
from app.models import Organization
from app.repositories.rbac_repository import rbac_repository


def _require_enabled_user(user_id: int):
    user = rbac_repository.find_user(user_id)
    if user is None or not user.enabled:
        raise BusinessException(
            "用户不存在或已停用", result_code=ResultCode.UNAUTHORIZED
        )
    return user


def get_user_permissions(user_id: int) -> set[str]:
    _require_enabled_user(user_id)
    return rbac_repository.permission_codes_for_user(user_id)


def has_permission(user_id: int, permission_code: str) -> bool:
    try:
        return permission_code in get_user_permissions(user_id)
    except BusinessException:
        return False


def require_permission(user_id: int, permission_code: str) -> None:
    if not has_permission(user_id, permission_code):
        raise BusinessException("无操作权限", result_code=ResultCode.FORBIDDEN)


def _descendant_ids(organization_id: int) -> set[int]:
    result = {organization_id}
    frontier = {organization_id}
    while frontier:
        stmt = select(Organization.id).where(Organization.parent_id.in_(frontier))
        children = set(db.session.scalars(stmt).all()) - result
        if not children:
            break
        result.update(children)
        frontier = children
    return result


def accessible_organization_ids(user_id: int) -> set[int] | None:
    user = _require_enabled_user(user_id)
    role_scopes = rbac_repository.data_scopes_for_user(user_id)
    scopes = {scope for _, scope in role_scopes}
    if DataScope.ALL.value in scopes:
        return None

    result: set[int] = set()
    if user.organization_id is not None:
        if DataScope.DEPARTMENT.value in scopes:
            result.add(user.organization_id)
        if DataScope.DEPARTMENT_TREE.value in scopes:
            result.update(_descendant_ids(user.organization_id))

    custom_role_ids = [
        role_id for role_id, scope in role_scopes if scope == DataScope.CUSTOM.value
    ]
    result.update(rbac_repository.custom_organization_ids(custom_role_ids))
    return result


def get_data_scopes(user_id: int) -> set[str]:
    _require_enabled_user(user_id)
    return {scope for _, scope in rbac_repository.data_scopes_for_user(user_id)}


def require_organization_scope(user_id: int, organization_id: int) -> None:
    organization_ids = accessible_organization_ids(user_id)
    if organization_ids is not None and organization_id not in organization_ids:
        raise BusinessException("无该组织的数据权限", result_code=ResultCode.FORBIDDEN)


def find_approval_candidates(permission_code: str, organization_id: int) -> list[int]:
    candidates: list[int] = []
    for user_id in rbac_repository.enabled_user_ids_with_permission(permission_code):
        organization_ids = accessible_organization_ids(user_id)
        if organization_ids is None or organization_id in organization_ids:
            candidates.append(user_id)
    return candidates


__all__ = [
    "accessible_organization_ids",
    "find_approval_candidates",
    "get_data_scopes",
    "get_user_permissions",
    "has_permission",
    "require_organization_scope",
    "require_permission",
]
