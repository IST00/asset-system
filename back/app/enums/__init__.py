"""Persisted domain enum values.

Database columns store these values as strings so migrations remain portable
between SQLite tests and MySQL production.
"""

from enum import Enum


class StringEnum(str, Enum):
    """String enum whose value is safe to persist and serialize."""


class RecordStatus(StringEnum):
    ENABLED = "ENABLED"
    DISABLED = "DISABLED"


class DataScope(StringEnum):
    ALL = "ALL"
    DEPARTMENT = "DEPARTMENT"
    DEPARTMENT_TREE = "DEPARTMENT_TREE"
    SELF = "SELF"
    CUSTOM = "CUSTOM"


class ApprovalStatus(StringEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


class ApprovalChannel(StringEnum):
    INTERNAL = "INTERNAL"
    FEISHU = "FEISHU"
    DIRECT = "DIRECT"


class ApprovalExecutionMode(StringEnum):
    AUTO_ON_APPROVAL = "AUTO_ON_APPROVAL"
    MANUAL_CONFIRM = "MANUAL_CONFIRM"


class SignMode(StringEnum):
    OR_SIGN = "OR_SIGN"
    AND_SIGN = "AND_SIGN"


class AssigneeType(StringEnum):
    USER = "USER"
    ROLE = "ROLE"


class FlowStatus(StringEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    DISABLED = "DISABLED"


class RuntimeTaskStatus(StringEnum):
    WAITING = "WAITING"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


class ExecutionStatus(StringEnum):
    NOT_STARTED = "NOT_STARTED"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TERMINATED = "TERMINATED"


class ExecutionAttemptStatus(StringEnum):
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class ExecutionTriggerType(StringEnum):
    APPROVAL = "APPROVAL"
    CONFIRMATION = "CONFIRMATION"
    RETRY = "RETRY"


class AssetCodeStatus(StringEnum):
    PENDING_STOCK_IN = "PENDING_STOCK_IN"
    ACTIVE = "ACTIVE"
    VOID = "VOID"


class AssetStatus(StringEnum):
    IDLE = "IDLE"
    IN_USE = "IN_USE"
    REPAIRING = "REPAIRING"
    SCRAPPED = "SCRAPPED"


class AssetDataCompleteness(StringEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"


class UsageType(StringEnum):
    PERSONAL = "PERSONAL"
    PUBLIC = "PUBLIC"


class InventoryTaskStatus(StringEnum):
    DRAFT = "DRAFT"
    IN_PROGRESS = "IN_PROGRESS"
    REVIEWING = "REVIEWING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class InventoryItemStatus(StringEnum):
    PENDING = "PENDING"
    FOUND = "FOUND"
    LOSS = "LOSS"
    UNSUBMITTED = "UNSUBMITTED"
    EXEMPTED = "EXEMPTED"


class InventoryLocationResult(StringEnum):
    MATCHED = "MATCHED"
    DIFFERENT = "DIFFERENT"
    TEMPORARY = "TEMPORARY"


class InventorySubmissionMethod(StringEnum):
    SCANNED = "SCANNED"
    ADMIN_MARKED = "ADMIN_MARKED"


class InventoryReviewStatus(StringEnum):
    NONE = "NONE"
    AUTO_CONFIRMED = "AUTO_CONFIRMED"
    PENDING = "PENDING"
    RESOLVED = "RESOLVED"
    RETURNED = "RETURNED"


class InventoryPhotoSourceMode(StringEnum):
    CAMERA_ONLY = "CAMERA_ONLY"
    CAMERA_OR_ALBUM = "CAMERA_OR_ALBUM"


class OperationType(StringEnum):
    STOCK_IN = "STOCK_IN"
    PERSONAL_USE = "PERSONAL_USE"
    PUBLIC_USE = "PUBLIC_USE"
    PERSONAL_RETURN = "PERSONAL_RETURN"
    PUBLIC_RETURN = "PUBLIC_RETURN"
    TRANSFER = "TRANSFER"
    REPAIR_START = "REPAIR_START"
    REPAIR_COMPLETE = "REPAIR_COMPLETE"


class ApprovalAction(StringEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


__all__ = [
    "ApprovalAction",
    "ApprovalChannel",
    "ApprovalExecutionMode",
    "ApprovalStatus",
    "AssigneeType",
    "AssetCodeStatus",
    "AssetDataCompleteness",
    "AssetStatus",
    "DataScope",
    "ExecutionAttemptStatus",
    "ExecutionStatus",
    "ExecutionTriggerType",
    "FlowStatus",
    "InventoryItemStatus",
    "InventoryLocationResult",
    "InventoryPhotoSourceMode",
    "InventoryReviewStatus",
    "InventorySubmissionMethod",
    "InventoryTaskStatus",
    "OperationType",
    "RecordStatus",
    "RuntimeTaskStatus",
    "SignMode",
    "StringEnum",
    "UsageType",
]
