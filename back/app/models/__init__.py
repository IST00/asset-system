"""SQLAlchemy models imported for metadata registration."""

from app.models.asset import Asset, AssetCodeReservation, AssetCodeSequence
from app.models.audit import AssetLifecycleRecord, OperationLog
from app.models.master_data import (
    AssetCategory,
    AssetLocation,
    AssetSource,
    Organization,
    Unit,
)
from app.models.rbac import (
    Permission,
    Role,
    RoleDataScopeOrganization,
    RolePermission,
    UserRole,
)
from app.models.user import User
from app.models.workflow import (
    ApprovalRecord,
    ApprovalStep,
    ApprovalTask,
    OperationRequest,
    StockInItem,
    StockInRequest,
)

__all__ = [
    "Organization",
    "ApprovalRecord",
    "ApprovalStep",
    "ApprovalTask",
    "Asset",
    "AssetCodeReservation",
    "AssetCodeSequence",
    "AssetLifecycleRecord",
    "AssetCategory",
    "AssetLocation",
    "AssetSource",
    "Permission",
    "OperationLog",
    "OperationRequest",
    "Role",
    "RoleDataScopeOrganization",
    "RolePermission",
    "User",
    "UserRole",
    "Unit",
    "StockInItem",
    "StockInRequest",
]
