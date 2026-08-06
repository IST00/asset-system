"""Authentication service with lockout, audit events, and server-side sessions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from flask import current_app

from app.common import BusinessException, ResultCode
from app.extensions import db
from app.models import User
from app.repositories import rbac_repository, user_repository
from app.security.passwords import verify_password
from app.services import permission_service, security_service


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


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


def login(
    *,
    username: str,
    password: str,
    ip_address: str,
    user_agent: str | None,
) -> dict[str, Any]:
    security_service.enforce_login_rate_limit(ip_address)
    user = user_repository.find_by_username(username)
    if user is None:
        security_service.record_event(
            "LOGIN_FAILURE",
            username=username,
            ip_address=ip_address,
            detail="unknown_username",
            commit=True,
        )
        raise BusinessException(
            "invalid credentials", result_code=ResultCode.UNAUTHORIZED
        )

    now = _now()
    locked_until = _as_utc(user.locked_until)
    if locked_until is not None and locked_until > now:
        security_service.record_event(
            "LOGIN_BLOCKED",
            user=user,
            ip_address=ip_address,
            detail=f"locked_until={locked_until.isoformat()}",
            commit=True,
        )
        raise BusinessException(
            f"账号已锁定，请在 {locked_until.astimezone().strftime('%H:%M:%S')} 后重试",
            code=423,
        )
    if locked_until is not None:
        user.locked_until = None
        user.failed_login_count = 0
        security_service.record_event(
            "ACCOUNT_UNLOCKED",
            user=user,
            ip_address=ip_address,
            detail="automatic_unlock_after_timeout",
        )

    if not verify_password(password, user.password):
        user.failed_login_count += 1
        threshold = int(current_app.config["LOGIN_LOCK_THRESHOLD"])
        detail = f"failed_count={user.failed_login_count}; threshold={threshold}"
        security_service.record_event(
            "LOGIN_FAILURE", user=user, ip_address=ip_address, detail=detail
        )
        if user.failed_login_count >= threshold:
            lock_minutes = int(current_app.config["LOGIN_LOCK_MINUTES"])
            user.locked_until = now + timedelta(minutes=lock_minutes)
            security_service.record_event(
                "ACCOUNT_LOCKED",
                user=user,
                ip_address=ip_address,
                detail=f"lock_minutes={lock_minutes}",
            )
        db.session.commit()
        raise BusinessException(
            "invalid credentials", result_code=ResultCode.UNAUTHORIZED
        )
    if not user.enabled:
        security_service.record_event(
            "LOGIN_BLOCKED",
            user=user,
            ip_address=ip_address,
            detail="user_disabled",
            commit=True,
        )
        raise BusinessException("user disabled", result_code=ResultCode.FORBIDDEN)

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    session_data = security_service.issue_session(
        user, ip_address=ip_address, user_agent=user_agent
    )
    security_service.record_event(
        "LOGIN_SUCCESS", user=user, ip_address=ip_address, detail="password_login"
    )
    db.session.commit()
    return {**session_data, "user": _user_to_dict(user)}


def logout(*, user_id: int, session_id: str) -> None:
    security_service.revoke_session(session_id, user_id=user_id, reason="user_logout")
