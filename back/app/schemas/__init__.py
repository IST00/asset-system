"""Marshmallow schemas (DTO boundary)."""

from app.schemas.asset import (
    AssetVersionTargetSchema,
    BatchCompleteAssetDataRequestSchema,
    CompleteAssetDataRequestSchema,
)
from app.schemas.supplier import (
    CreateSupplierRequestSchema,
    DeleteSupplierRequestSchema,
    SupplierVersionRequestSchema,
    UpdateSupplierRequestSchema,
)
from app.schemas.user import (
    ChangePasswordRequestSchema,
    LoginRequestSchema,
    LoginResponseSchema,
    UserPageQuerySchema,
    RegisterRequestSchema,
    UserResponseSchema,
)

__all__ = [
    "AssetVersionTargetSchema",
    "BatchCompleteAssetDataRequestSchema",
    "CompleteAssetDataRequestSchema",
    "CreateSupplierRequestSchema",
    "DeleteSupplierRequestSchema",
    "ChangePasswordRequestSchema",
    "LoginRequestSchema",
    "LoginResponseSchema",
    "UserPageQuerySchema",
    "RegisterRequestSchema",
    "SupplierVersionRequestSchema",
    "UpdateSupplierRequestSchema",
    "UserResponseSchema",
]
