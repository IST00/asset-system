"""User service — queries for the current user and admin-scoped paging."""

from __future__ import annotations

from typing import Any

from app.common import BusinessException, PageResult, ResultCode
from app.extensions import db
from app.models import User
from app.repositories import QuerySpec, rbac_repository, user_repository
from app.security.passwords import verify_password
from app.services import audit_service, permission_service, security_service


def _user_to_dict(u: User) -> dict[str, Any]:
    return {
        "id": u.id,
        "username": u.username,
        "nickname": u.nickname,
        "organization_id": u.organization_id,
        "roles": rbac_repository.role_codes_for_user(u.id),
        "permissions": sorted(permission_service.get_user_permissions(u.id)),
        "enabled": u.enabled,
        "must_change_password": u.must_change_password,
        "password_changed_at": u.password_changed_at,
        "last_login_at": u.last_login_at,
        "created_at": u.created_at,
        "updated_at": u.updated_at,
    }


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


def page(page_index: int, size: int) -> PageResult:
    # page_index is 0-based (matches the Java side's controller contract)
    spec = QuerySpec(
        order_by=[User.id.asc()],
        page=page_index if page_index >= 0 else 0,
        size=size if size > 0 else 10,
    )
    result = user_repository.page(spec)
    return PageResult(
        items=[_user_to_dict(u) for u in result.items],
        total=result.total,
        page=result.page,
        size=result.size,
    )
