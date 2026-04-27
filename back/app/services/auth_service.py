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
from app.extensions import db
from app.models import User
from app.repositories import user_repository
from app.security.passwords import hash_password, verify_password


def _user_to_dict(u: User) -> dict[str, Any]:
    return {
        "id": u.id,
        "username": u.username,
        "nickname": u.nickname,
        "role": u.role,
        "enabled": u.enabled,
        "created_at": u.created_at,
        "updated_at": u.updated_at,
    }


def register(*, username: str, password: str, nickname: str | None = None) -> dict[str, Any]:
    if user_repository.username_exists(username):
        raise BusinessException("username already exists")

    user = User(
        username=username,
        password=hash_password(password),
        nickname=nickname,
        role="USER",
        enabled=True,
    )
    user_repository.add(user)
    db.session.commit()
    return _user_to_dict(user)


def login(*, username: str, password: str) -> dict[str, Any]:
    user = user_repository.find_by_username(username)
    if user is None:
        raise BusinessException("invalid credentials", result_code=ResultCode.UNAUTHORIZED)
    if not verify_password(password, user.password):
        raise BusinessException("invalid credentials", result_code=ResultCode.UNAUTHORIZED)
    if not user.enabled:
        raise BusinessException("user disabled", result_code=ResultCode.FORBIDDEN)

    expires: timedelta = current_app.config["JWT_ACCESS_TOKEN_EXPIRES"]
    token = create_access_token(
        identity=user.username,
        additional_claims={"role": user.role or "USER"},
        expires_delta=expires,
    )
    return {"token": token, "user": _user_to_dict(user)}
