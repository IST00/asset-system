"""SQLAlchemy models imported for metadata registration."""

from app.models.asset import (
    Asset,
    AssetCodeReservation,
    AssetCodeSequence,
    PublicUsageObject,
)
from app.models.attachment import AssetAttachment
from app.models.asset_lifecycle_request import (
    AssetScrapRequest,
    AssetScrapRequestItem,
    AssetTransferRequest,
)
from app.models.asset_usage_return import (
    AssetReturnItem,
    AssetReturnRequest,
    AssetUsageRequest,
)
from app.models.approval_governance import ApprovalTaskEvent
from app.models.approval_flow import (
    ApprovalFlowAssigneeRule,
    ApprovalFlowDefinition,
    ApprovalFlowLayer,
    ApprovalFlowVersion,
)
from app.models.audit import AssetLifecycleRecord, OperationLog
from app.models.export import ExportJob
from app.models.import_job import ImportJob
from app.models.inventory import (
    InventoryItem,
    InventoryPhoto,
    InventoryReminder,
    InventoryResultVersion,
    InventoryScanEvent,
    InventoryTask,
    InventoryTaskAdmin,
)
from app.models.master_data import (
    AssetCategory,
    AssetLocation,
    AssetSource,
    LocationCodeSequence,
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
from app.models.security import (
    PasswordHistory,
    RateLimitBucket,
    SecurityEventLog,
    UserSession,
)
from app.models.rbac import (
    Permission,
    Role,
    RoleDataScopeOrganization,
    RolePermission,
    UserRole,
)
from app.models.supplier import Supplier, SupplierCodeSequence
from app.models.user import User
from app.models.user_preference import UserPreference
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
    "ApprovalTaskEvent",
    "Asset",
    "AssetAttachment",
    "AssetBusinessLock",
    "AssetCodeReservation",
    "AssetCodeSequence",
    "AssetLifecycleRecord",
    "AssetScrapRequest",
    "AssetScrapRequestItem",
    "AssetTransferRequest",
    "AssetReturnItem",
    "AssetReturnRequest",
    "AssetUsageRequest",
    "AssetCategory",
    "AssetLocation",
    "LocationCodeSequence",
    "AssetSource",
    "ExportJob",
    "ExternalApprovalEvent",
    "InventoryTaskAdmin",
    "InventoryTask",
    "InventoryScanEvent",
    "InventoryPhoto",
    "InventoryReminder",
    "InventoryResultVersion",
    "ImportJob",
    "InventoryItem",
    "Permission",
    "PublicUsageObject",
    "UserSession",
    "SecurityEventLog",
    "RateLimitBucket",
    "PasswordHistory",
    "OperationLog",
    "OperationExecutionAttempt",
    "OperationActionIdempotency",
    "OperationRequest",
    "OperationRequestAsset",
    "Role",
    "RoleDataScopeOrganization",
    "RolePermission",
    "User",
    "UserPreference",
    "UserRole",
    "Unit",
    "StockInItem",
    "StockInRequest",
    "Supplier",
    "SupplierCodeSequence",
]
