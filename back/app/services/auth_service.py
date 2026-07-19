"""Auth service — register / login logic.

Mirrors com.soybean.quick.service.AuthService on the Java side.
Raises BusinessException; translation into Result is done by the global handler.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from flask import current_app
from flask_jwt_extended import create_access_token

from app.common import BusinessException, ResultCode
from app.models import User
from app.repositories import rbac_repository, user_repository
from app.security.passwords import verify_password
from app.services import permission_service


def _user_to_dict(u: User) -> dict[str, Any]:
    return {
        "id": u.id,
        "username": u.username,
        "nickname": u.nickname,
        "organization_id": u.organization_id,
        "roles": rbac_repository.role_codes_for_user(u.id),
        "permissions": sorted(permission_service.get_user_permissions(u.id)),
        "enabled": u.enabled,
        "created_at": u.created_at,
        "updated_at": u.updated_at,
    }


def login(*, username: str, password: str) -> dict[str, Any]:
    user = user_repository.find_by_username(username)
    if user is None:
        raise BusinessException(
            "invalid credentials", result_code=ResultCode.UNAUTHORIZED
        )
    if not verify_password(password, user.password):
        raise BusinessException(
            "invalid credentials", result_code=ResultCode.UNAUTHORIZED
        )
    if not user.enabled:
        raise BusinessException("user disabled", result_code=ResultCode.FORBIDDEN)

    expires: timedelta = current_app.config["JWT_ACCESS_TOKEN_EXPIRES"]
    token = create_access_token(
        identity=str(user.id),
        expires_delta=expires,
    )
    return {"token": token, "user": _user_to_dict(user)}
