"""Transactional execution, retry, and termination of approved operations."""

from __future__ import annotations

import logging

from app.common import BusinessException, ResultCode
from app.enums import (
    ApprovalExecutionMode,
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
    operation = operation_request_repository.get(operation_request_id)
    if operation is None:
        raise BusinessException("申请不存在", result_code=ResultCode.NOT_FOUND)
    return operation


def _require_operation_for_update(operation_request_id: int) -> OperationRequest:
    operation = operation_request_repository.find_for_update(operation_request_id)
    if operation is None:
        raise BusinessException("申请不存在", result_code=ResultCode.NOT_FOUND)
    return operation


def _validate_trigger(operation: OperationRequest, trigger_type: str) -> None:
    if trigger_type == ExecutionTriggerType.APPROVAL.value and (
        operation.approval_execution_mode
        != ApprovalExecutionMode.AUTO_ON_APPROVAL.value
    ):
        raise BusinessException(
            "当前申请需要人工确认后执行", result_code=ResultCode.BAD_REQUEST
        )
    if trigger_type == ExecutionTriggerType.CONFIRMATION.value and (
        operation.approval_execution_mode != ApprovalExecutionMode.MANUAL_CONFIRM.value
    ):
        raise BusinessException(
            "当前申请不能由人工确认触发", result_code=ResultCode.BAD_REQUEST
        )


def _expected_execution_status(trigger_type: str) -> str:
    if trigger_type == ExecutionTriggerType.RETRY.value:
        return ExecutionStatus.FAILED.value
    return ExecutionStatus.NOT_STARTED.value


def _reload_claim_winner(operation_request_id: int) -> OperationRequest:
    db.session.rollback()
    db.session.remove()
    operation = operation_request_repository.get(operation_request_id)
    if operation is None:
        raise BusinessException("申请不存在", result_code=ResultCode.NOT_FOUND)
    if operation.execution_status in {
        ExecutionStatus.SUCCESS.value,
        ExecutionStatus.FAILED.value,
    }:
        return operation
    if operation.execution_status == ExecutionStatus.PROCESSING.value:
        raise BusinessException("执行请求正在处理中，请稍后重试")
    raise BusinessException("当前执行状态不能开始执行")


def _persist_commit_failure(
    operation_request_id: int,
    actor_id: int,
    trigger_type: str,
    expected_status: str,
    expected_version: int,
    safe_error_message: str,
) -> OperationRequest:
    db.session.rollback()
    db.session.remove()
    if not operation_request_repository.claim_execution(
        operation_request_id,
        expected_status,
        expected_version,
    ):
        return _reload_claim_winner(operation_request_id)
    operation = operation_request_repository.get(operation_request_id)
    if operation is None:
        raise BusinessException("申请不存在", result_code=ResultCode.NOT_FOUND)
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
    try:
        db.session.commit()
    except Exception:
        log.exception(
            "operation commit-failure recovery failed for request_id=%s",
            operation_request_id,
        )
        db.session.rollback()
        db.session.remove()
        persisted = operation_request_repository.get(operation_request_id)
        if (
            persisted is not None
            and persisted.version > expected_version
            and persisted.execution_status
            in {
                ExecutionStatus.SUCCESS.value,
                ExecutionStatus.FAILED.value,
            }
        ):
            return persisted
        raise BusinessException(safe_error_message) from None
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
    _validate_trigger(operation, trigger_type)
    expected_status = _expected_execution_status(trigger_type)
    if trigger_type != ExecutionTriggerType.RETRY.value and (
        operation.execution_status != expected_status
    ):
        raise BusinessException("当前执行状态不能开始执行")
    if trigger_type == ExecutionTriggerType.RETRY.value and (
        operation.execution_status != expected_status
    ):
        raise BusinessException("只有执行失败的申请可以重试")

    handler = operation_handler_registry.get(operation.operation_type)
    expected_version = operation.version
    if not operation_request_repository.claim_execution(
        operation.id,
        expected_status,
        expected_version,
    ):
        return _reload_claim_winner(operation.id)
    db.session.refresh(operation)
    attempt = OperationExecutionAttempt(
        operation_request_id=operation.id,
        attempt_no=execution_attempt_repository.next_attempt_no(operation.id),
        trigger_type=trigger_type,
        triggered_by=actor_id,
        status=ExecutionAttemptStatus.PROCESSING.value,
    )
    execution_attempt_repository.add(attempt)
    safe_error_message = str(
        getattr(handler, "safe_error_message", _SAFE_EXECUTION_ERROR)
    )
    try:
        with db.session.begin_nested():
            handler.revalidate_for_execution(operation.id)
            handler.execute(operation.id, actor_id)
            attempt.status = ExecutionAttemptStatus.SUCCESS.value
            attempt.finished_at = utc_now()
            operation.execution_status = ExecutionStatus.SUCCESS.value
            operation.executed_at = utc_now()
            operation.version += 1
            operation_service.release_locks(operation.id)
    except Exception:
        log.exception("operation execution failed for request_id=%s", operation.id)
        db.session.refresh(operation)
        db.session.refresh(attempt)
        attempt.status = ExecutionAttemptStatus.FAILED.value
        attempt.error_code = "EXECUTION_FAILED"
        attempt.safe_error_message = safe_error_message
        attempt.finished_at = utc_now()
        operation.execution_status = ExecutionStatus.FAILED.value
        operation.execution_error = safe_error_message
    try:
        db.session.commit()
    except Exception:
        log.exception("operation commit failed for request_id=%s", operation.id)
        return _persist_commit_failure(
            operation.id,
            actor_id,
            trigger_type,
            expected_status,
            expected_version,
            safe_error_message,
        )
    return operation


def execute_after_approval(
    operation_request_id: int, actor_id: int
) -> OperationRequest:
    operation = _require_operation(operation_request_id)
    if operation.approval_execution_mode == ApprovalExecutionMode.MANUAL_CONFIRM.value:
        return operation
    return execute(
        operation_request_id,
        actor_id,
        ExecutionTriggerType.APPROVAL.value,
    )


def confirm(operation_request_id: int, actor_id: int) -> OperationRequest:
    return execute(
        operation_request_id,
        actor_id,
        ExecutionTriggerType.CONFIRMATION.value,
    )


def retry(operation_request_id: int, actor_id: int) -> OperationRequest:
    return execute(operation_request_id, actor_id, ExecutionTriggerType.RETRY.value)


def terminate(
    operation_request_id: int, actor_id: int, reason: str
) -> OperationRequest:
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise BusinessException("终止执行必须填写原因")
    operation = _require_operation_for_update(operation_request_id)
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


__all__ = ["confirm", "execute", "execute_after_approval", "retry", "terminate"]
