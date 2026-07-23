"""Marshmallow schemas (DTO boundary)."""

from app.schemas.supplier import (
    CreateSupplierRequestSchema,
    DeleteSupplierRequestSchema,
    SupplierVersionRequestSchema,
    UpdateSupplierRequestSchema,
)
from app.schemas.user import (
    LoginRequestSchema,
    LoginResponseSchema,
    PageQuerySchema,
    RegisterRequestSchema,
    UserResponseSchema,
)

__all__ = [
    "CreateSupplierRequestSchema",
    "DeleteSupplierRequestSchema",
    "LoginRequestSchema",
    "LoginResponseSchema",
    "PageQuerySchema",
    "RegisterRequestSchema",
    "SupplierVersionRequestSchema",
    "UpdateSupplierRequestSchema",
    "UserResponseSchema",
]
