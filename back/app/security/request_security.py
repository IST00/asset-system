"""Application-wide authenticated request security policies."""

from __future__ import annotations

from flask import Flask, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from app.common import BusinessException, ResultCode
from app.services import security_service

_PASSWORD_CHANGE_ALLOWLIST = {
    "/api/v1/users/me",
    "/api/v1/users/me/password/update",
    "/api/v1/auth/logout",
}


def register_request_security(app: Flask) -> None:
    @app.before_request
    def _enforce_authenticated_policies() -> None:
        if request.method == "OPTIONS" or not request.path.startswith("/api/v1/"):
            return
        if request.path == "/api/v1/auth/login":
            return
        verify_jwt_in_request(optional=True)
        identity = get_jwt_identity()
        if identity is None:
            return
        try:
            user_id = int(identity)
        except (TypeError, ValueError) as exc:
            raise BusinessException(
                "登录身份无效", result_code=ResultCode.UNAUTHORIZED
            ) from exc
        security_service.enforce_user_rate_limit(user_id)
        if (
            request.path not in _PASSWORD_CHANGE_ALLOWLIST
            and security_service.user_requires_password_change(user_id)
        ):
            raise BusinessException(
                "首次登录请先修改密码", result_code=ResultCode.FORBIDDEN
            )


__all__ = ["register_request_security"]
