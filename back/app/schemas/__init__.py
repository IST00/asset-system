"""Marshmallow schemas (DTO boundary)."""

from app.schemas.keke import (
    GenerateStoryRequestSchema,
    GenerateStoryResponseSchema,
    TrackingEventRequestSchema,
)
from app.schemas.user import (
    LoginRequestSchema,
    LoginResponseSchema,
    PageQuerySchema,
    RegisterRequestSchema,
    UserResponseSchema,
)

__all__ = [
    "GenerateStoryRequestSchema",
    "GenerateStoryResponseSchema",
    "LoginRequestSchema",
    "LoginResponseSchema",
    "PageQuerySchema",
    "RegisterRequestSchema",
    "TrackingEventRequestSchema",
    "UserResponseSchema",
]
