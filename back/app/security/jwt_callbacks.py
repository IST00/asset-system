"""JWT / security helpers.

`flask_jwt_extended` already handles token creation/verification; this module
wires callbacks that translate JWT errors into our Result envelope.

IMPORTANT: no blueprint/service/controller should decode tokens by hand —
use `get_jwt_identity()` / `get_jwt()` from flask_jwt_extended.
"""

from __future__ import annotations

from typing import Any

from flask import Flask, jsonify
from flask_jwt_extended import JWTManager

from app.common.result import Result, ResultCode


def register_jwt_callbacks(app: Flask, jwt_manager: JWTManager) -> None:
    @jwt_manager.unauthorized_loader
    def _missing(reason: str) -> tuple[Any, int]:
        return (
            jsonify(Result.fail(ResultCode.UNAUTHORIZED, reason or "missing token").to_dict()),
            401,
        )

    @jwt_manager.invalid_token_loader
    def _invalid(reason: str) -> tuple[Any, int]:
        return (
            jsonify(Result.fail(ResultCode.UNAUTHORIZED, reason or "invalid token").to_dict()),
            401,
        )

    @jwt_manager.expired_token_loader
    def _expired(_jwt_header: dict, _jwt_payload: dict) -> tuple[Any, int]:
        return (
            jsonify(Result.fail(ResultCode.UNAUTHORIZED, "token expired").to_dict()),
            401,
        )

    @jwt_manager.needs_fresh_token_loader
    def _fresh(_jwt_header: dict, _jwt_payload: dict) -> tuple[Any, int]:
        return (
            jsonify(Result.fail(ResultCode.UNAUTHORIZED, "fresh token required").to_dict()),
            401,
        )

    @jwt_manager.revoked_token_loader
    def _revoked(_jwt_header: dict, _jwt_payload: dict) -> tuple[Any, int]:
        return (
            jsonify(Result.fail(ResultCode.UNAUTHORIZED, "token revoked").to_dict()),
            401,
        )


def require_role(required_role: str, claims: dict[str, Any]) -> bool:
    """Tiny helper for role gate inside a blueprint view.

    Controllers should do::

        from flask_jwt_extended import get_jwt
        if not require_role("ADMIN", get_jwt()):
            raise BusinessException(result_code=ResultCode.FORBIDDEN)
    """
    return claims.get("role") == required_role
