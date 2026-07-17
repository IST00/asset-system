"""Current JWT identity helpers."""

from __future__ import annotations

from flask_jwt_extended import get_jwt_identity

from app.common import BusinessException, ResultCode


def current_user_id() -> int:
    identity = get_jwt_identity()
    try:
        return int(identity)
    except (TypeError, ValueError) as exc:
        raise BusinessException(
            "登录身份无效", result_code=ResultCode.UNAUTHORIZED
        ) from exc


__all__ = ["current_user_id"]
