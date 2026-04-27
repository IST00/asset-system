"""Marshmallow schemas (DTO boundary)."""

from app.schemas.user import (
    LoginRequestSchema,
    LoginResponseSchema,
    PageQuerySchema,
    RegisterRequestSchema,
    UserResponseSchema,
)

__all__ = [
    "LoginRequestSchema",
    "LoginResponseSchema",
    "PageQuerySchema",
    "RegisterRequestSchema",
    "UserResponseSchema",
]
