"""User service — queries for the current user and admin-scoped paging."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import case, func, or_, select

from app.common import BusinessException, PageResult, ResultCode
from app.extensions import db
from app.models import Role, User, UserRole
from app.repositories import QuerySpec, rbac_repository, user_repository
from app.security.passwords import verify_password
from app.services import (
    audit_service,
    organization_service,
    permission_service,
    security_service,
)


def _user_to_dict(
    u: User, organization_paths: Mapping[int, str] | None = None
) -> dict[str, Any]:
    paths = organization_paths or {}
    return {
        "id": u.id,
        "username": u.username,
        "nickname": u.nickname,
        "organization_id": u.organization_id,
        "organization_path": (
            paths.get(u.organization_id) if u.organization_id is not None else None
        ),
        "roles": rbac_repository.role_codes_for_user(u.id),
        "permissions": sorted(permission_service.effective_permissions(u.id)),
        "enabled": u.enabled,
        "must_change_password": u.must_change_password,
        "password_changed_at": u.password_changed_at,
        "last_login_at": u.last_login_at,
        "created_at": u.created_at,
        "updated_at": u.updated_at,
    }


_USER_ROLE_DISPLAY_PRIORITY = {
    "SUPER_ADMIN": 0,
    "ASSET_ADMIN": 1,
    "USER": 2,
}


def _user_role_display_order():
    fallback_priority = len(_USER_ROLE_DISPLAY_PRIORITY)
    priority = case(
        (Role.code == "SUPER_ADMIN", _USER_ROLE_DISPLAY_PRIORITY["SUPER_ADMIN"]),
        (Role.code == "ASSET_ADMIN", _USER_ROLE_DISPLAY_PRIORITY["ASSET_ADMIN"]),
        (Role.code == "USER", _USER_ROLE_DISPLAY_PRIORITY["USER"]),
        else_=fallback_priority,
    )
    return (
        select(func.coalesce(func.min(priority), fallback_priority))
        .where(UserRole.user_id == User.id, UserRole.role_id == Role.id)
        .scalar_subquery()
    )


def get_current(user_id: int) -> dict[str, Any]:
    user = user_repository.get(user_id)
    if user is None:
        raise BusinessException("user not found")
    return _user_to_dict(user)


def change_password(
    user_id: int,
    current_password: str,
    new_password: str,
    *,
    ip_address: str | None,
    user_agent: str | None,
) -> dict[str, Any]:
    user = user_repository.get(user_id)
    if user is None:
        raise BusinessException("用户不存在", result_code=ResultCode.NOT_FOUND)
    if not verify_password(current_password, user.password):
        raise BusinessException("当前密码不正确", result_code=ResultCode.BAD_REQUEST)

    security_service.apply_new_password(user, new_password, must_change=False)
    revoked = security_service.revoke_all_sessions(user.id, reason="password_changed")
    session_data = security_service.issue_session(
        user, ip_address=ip_address, user_agent=user_agent
    )
    security_service.record_event(
        "PASSWORD_CHANGED",
        user=user,
        ip_address=ip_address,
        detail=f"revoked_sessions={revoked}",
    )
    audit_service.record_resource_change(
        action="PASSWORD_UPDATE",
        resource_type="user",
        resource_id=user.id,
        actor_id=user.id,
        before_data={"password_changed": False},
        after_data={"password_changed": True},
        reason="用户主动修改密码",
    )
    db.session.commit()
    return {**session_data, "user": _user_to_dict(user)}


def page(page_index: int, size: int, keyword: str = "") -> PageResult:
    normalized_keyword = keyword.strip()
    filters = []
    if normalized_keyword:
        pattern = f"%{normalized_keyword}%"
        filters.append(
            or_(
                User.username.ilike(pattern),
                User.nickname.ilike(pattern),
            )
        )
    # page_index is 0-based (matches the Java side's controller contract)
    spec = QuerySpec(
        filters=filters,
        order_by=[_user_role_display_order().asc(), User.id.asc()],
        page=page_index if page_index >= 0 else 0,
        size=size if size > 0 else 10,
    )
    result = user_repository.page(spec)
    organization_paths = organization_service.full_paths()
    return PageResult(
        items=[_user_to_dict(u, organization_paths) for u in result.items],
        total=result.total,
        page=result.page,
        size=result.size,
    )
