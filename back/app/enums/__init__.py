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


class ExecutionStatus(StringEnum):
    NOT_STARTED = "NOT_STARTED"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TERMINATED = "TERMINATED"


class AssetCodeStatus(StringEnum):
    PENDING_STOCK_IN = "PENDING_STOCK_IN"
    ACTIVE = "ACTIVE"
    VOID = "VOID"


class AssetStatus(StringEnum):
    IDLE = "IDLE"
    IN_USE = "IN_USE"
    REPAIRING = "REPAIRING"
    SCRAPPED = "SCRAPPED"


class OperationType(StringEnum):
    STOCK_IN = "STOCK_IN"


class ApprovalAction(StringEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


__all__ = [
    "ApprovalAction",
    "ApprovalStatus",
    "AssetCodeStatus",
    "AssetStatus",
    "DataScope",
    "ExecutionStatus",
    "OperationType",
    "RecordStatus",
    "StringEnum",
]
