"""Transactional execution, retry, and termination of approved operations."""

from __future__ import annotations

import logging

from app.common import BusinessException, ResultCode
from app.enums import (
    ApprovalStatus,
    ExecutionAttemptStatus,
    ExecutionStatus,
    ExecutionTriggerType,
)
from app.extensions import db
from app.models import OperationExecutionAttempt, OperationRequest
from app.models.mixins import utc_now
from app.operations import operation_handler_registry
from app.repositories import execution_attempt_repository
from app.repositories.workflow_repository import operation_request_repository
from app.services import operation_service

log = logging.getLogger(__name__)

_SAFE_EXECUTION_ERROR = "业务执行失败，请联系管理员或稍后重试"


def _require_operation(operation_request_id: int) -> OperationRequest:
    operation = operation_request_repository.find_for_update(operation_request_id)
    if operation is None:
        raise BusinessException("申请不存在", result_code=ResultCode.NOT_FOUND)
    return operation


def _persist_failed_attempt(
    operation_request_id: int,
    actor_id: int,
    trigger_type: str,
    safe_error_message: str,
) -> OperationRequest:
    operation = _require_operation(operation_request_id)
    attempt = OperationExecutionAttempt(
        operation_request_id=operation.id,
        attempt_no=execution_attempt_repository.next_attempt_no(operation.id),
        trigger_type=trigger_type,
        triggered_by=actor_id,
        status=ExecutionAttemptStatus.FAILED.value,
        error_code="EXECUTION_FAILED",
        safe_error_message=safe_error_message,
        finished_at=utc_now(),
    )
    execution_attempt_repository.add(attempt)
    operation.execution_status = ExecutionStatus.FAILED.value
    operation.execution_error = safe_error_message
    operation.version += 1
    db.session.commit()
    return operation


def execute(
    operation_request_id: int, actor_id: int, trigger_type: str
) -> OperationRequest:
    if trigger_type not in {item.value for item in ExecutionTriggerType}:
        raise BusinessException("执行触发类型无效", result_code=ResultCode.BAD_REQUEST)
    operation = _require_operation(operation_request_id)
    if operation.approval_status != ApprovalStatus.APPROVED.value:
        raise BusinessException("只有审批通过的申请可以执行")
    if operation.execution_status == ExecutionStatus.SUCCESS.value:
        return operation
    if trigger_type == ExecutionTriggerType.APPROVAL.value and (
        operation.execution_status != ExecutionStatus.NOT_STARTED.value
    ):
        raise BusinessException("当前执行状态不能由审批触发")
    if trigger_type == ExecutionTriggerType.RETRY.value and (
        operation.execution_status != ExecutionStatus.FAILED.value
    ):
        raise BusinessException("只有执行失败的申请可以重试")

    handler = operation_handler_registry.get(operation.operation_type)
    attempt = OperationExecutionAttempt(
        operation_request_id=operation.id,
        attempt_no=execution_attempt_repository.next_attempt_no(operation.id),
        trigger_type=trigger_type,
        triggered_by=actor_id,
        status=ExecutionAttemptStatus.PROCESSING.value,
    )
    execution_attempt_repository.add(attempt)
    operation.execution_status = ExecutionStatus.PROCESSING.value
    operation.execution_error = None
    operation.version += 1
    try:
        handler.revalidate_for_execution(operation.id)
        handler.execute(operation.id, actor_id)
        attempt.status = ExecutionAttemptStatus.SUCCESS.value
        attempt.finished_at = utc_now()
        operation.execution_status = ExecutionStatus.SUCCESS.value
        operation.executed_at = utc_now()
        operation.version += 1
        operation_service.release_locks(operation.id)
        db.session.commit()
        return operation
    except Exception:
        log.exception("operation execution failed for request_id=%s", operation.id)
        db.session.rollback()
        return _persist_failed_attempt(
            operation_request_id,
            actor_id,
            trigger_type,
            str(getattr(handler, "safe_error_message", _SAFE_EXECUTION_ERROR)),
        )


def retry(operation_request_id: int, actor_id: int) -> OperationRequest:
    return execute(operation_request_id, actor_id, ExecutionTriggerType.RETRY.value)


def terminate(
    operation_request_id: int, actor_id: int, reason: str
) -> OperationRequest:
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise BusinessException("终止执行必须填写原因")
    operation = _require_operation(operation_request_id)
    if operation.execution_status != ExecutionStatus.FAILED.value:
        raise BusinessException("只有执行失败的申请可以终止")
    operation.execution_status = ExecutionStatus.TERMINATED.value
    operation.terminated_at = utc_now()
    operation.terminated_by = actor_id
    operation.termination_reason = normalized_reason
    operation.version += 1
    operation_service.release_locks(operation.id)
    db.session.commit()
    return operation


__all__ = ["execute", "retry", "terminate"]
