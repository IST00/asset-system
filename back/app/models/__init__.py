"""SQLAlchemy models imported for metadata registration."""

from app.models.asset import (
    Asset,
    AssetCodeReservation,
    AssetCodeSequence,
    PublicUsageObject,
)
from app.models.approval_flow import (
    ApprovalFlowAssigneeRule,
    ApprovalFlowDefinition,
    ApprovalFlowLayer,
    ApprovalFlowVersion,
)
from app.models.audit import AssetLifecycleRecord, OperationLog
from app.models.master_data import (
    AssetCategory,
    AssetLocation,
    AssetSource,
    Organization,
    Unit,
)
from app.models.operation import (
    AssetBusinessLock,
    ExternalApprovalEvent,
    OperationActionIdempotency,
    OperationExecutionAttempt,
    OperationRequestAsset,
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
    "ApprovalFlowAssigneeRule",
    "ApprovalFlowDefinition",
    "ApprovalFlowLayer",
    "ApprovalFlowVersion",
    "ApprovalRecord",
    "ApprovalStep",
    "ApprovalTask",
    "Asset",
    "AssetBusinessLock",
    "AssetCodeReservation",
    "AssetCodeSequence",
    "AssetLifecycleRecord",
    "AssetCategory",
    "AssetLocation",
    "AssetSource",
    "ExternalApprovalEvent",
    "Permission",
    "PublicUsageObject",
    "OperationLog",
    "OperationExecutionAttempt",
    "OperationActionIdempotency",
    "OperationRequest",
    "OperationRequestAsset",
    "Role",
    "RoleDataScopeOrganization",
    "RolePermission",
    "User",
    "UserRole",
    "Unit",
    "StockInItem",
    "StockInRequest",
]
