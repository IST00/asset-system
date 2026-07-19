"""Repository layer — the thin seam between services and SQLAlchemy.

A Repository owns *how to query/persist* a single aggregate. Services own
*business rules + transaction boundaries*. Keep the seam narrow: a repo
method should map to at most a few SQL statements and never raise
BusinessException.
"""

from app.repositories.base import BaseRepository, Page, QuerySpec
from app.repositories.asset_repository import (
    AssetCodeReservationRepository,
    AssetCodeSequenceRepository,
    AssetRepository,
    asset_code_reservation_repository,
    asset_code_sequence_repository,
    asset_repository,
)
from app.repositories.audit_repository import (
    AssetLifecycleRepository,
    OperationLogRepository,
    asset_lifecycle_repository,
    operation_log_repository,
)
from app.repositories.approval_flow_repository import (
    ApprovalFlowRepository,
    approval_flow_repository,
)
from app.repositories.master_data_repository import (
    OrganizationRepository,
    organization_repository,
)
from app.repositories.operation_repository import (
    AssetBusinessLockRepository,
    ExecutionAttemptRepository,
    ExternalApprovalEventRepository,
    OperationRequestAssetRepository,
    OperationActionIdempotencyRepository,
    asset_business_lock_repository,
    execution_attempt_repository,
    external_approval_event_repository,
    operation_request_asset_repository,
    operation_action_idempotency_repository,
)
from app.repositories.rbac_repository import RbacRepository, rbac_repository
from app.repositories.user_repository import UserRepository, user_repository
from app.repositories.workflow_repository import (
    ApprovalRecordRepository,
    ApprovalStepRepository,
    ApprovalTaskRepository,
    OperationRequestRepository,
    StockInItemRepository,
    StockInRequestRepository,
    approval_record_repository,
    approval_step_repository,
    approval_task_repository,
    operation_request_repository,
    stock_in_item_repository,
    stock_in_request_repository,
)

__all__ = [
    "BaseRepository",
    "AssetCodeReservationRepository",
    "AssetCodeSequenceRepository",
    "AssetRepository",
    "AssetBusinessLockRepository",
    "AssetLifecycleRepository",
    "ApprovalFlowRepository",
    "ExecutionAttemptRepository",
    "ExternalApprovalEventRepository",
    "OperationLogRepository",
    "OperationRequestAssetRepository",
    "OperationActionIdempotencyRepository",
    "Page",
    "QuerySpec",
    "OrganizationRepository",
    "RbacRepository",
    "UserRepository",
    "ApprovalStepRepository",
    "ApprovalTaskRepository",
    "ApprovalRecordRepository",
    "OperationRequestRepository",
    "StockInItemRepository",
    "StockInRequestRepository",
    "rbac_repository",
    "organization_repository",
    "asset_code_reservation_repository",
    "asset_code_sequence_repository",
    "asset_repository",
    "asset_business_lock_repository",
    "asset_lifecycle_repository",
    "operation_log_repository",
    "approval_flow_repository",
    "execution_attempt_repository",
    "external_approval_event_repository",
    "operation_request_asset_repository",
    "operation_action_idempotency_repository",
    "user_repository",
    "approval_step_repository",
    "approval_task_repository",
    "approval_record_repository",
    "operation_request_repository",
    "stock_in_item_repository",
    "stock_in_request_repository",
]
