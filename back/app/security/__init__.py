"""Security utilities (JWT callbacks, role helpers)."""

from app.security.jwt_callbacks import register_jwt_callbacks, require_role

__all__ = ["register_jwt_callbacks", "require_role"]
