"""External approval submission, callbacks, and direct confirmation."""

from __future__ import annotations

from app.common import BusinessException, ResultCode
from app.enums import (
    ApprovalChannel,
    ApprovalExecutionMode,
    ApprovalStatus,
    ExecutionStatus,
)
from app.extensions import db
from app.models import ExternalApprovalEvent, OperationRequest
from app.models.mixins import utc_now
from app.operations.providers import approval_provider_registry
from app.repositories import external_approval_event_repository
from app.repositories.workflow_repository import operation_request_repository
from app.services import operation_executor, operation_service
from sqlalchemy.exc import IntegrityError


def _require_operation(operation_request_id: int) -> OperationRequest:
    operation = operation_request_repository.get(operation_request_id)
    if operation is None:
        raise BusinessException("申请不存在", result_code=ResultCode.NOT_FOUND)
    return operation


def _resume_auto_execution(
    operation: OperationRequest,
    actor_id: int,
) -> OperationRequest:
    if (
        operation.approval_status == ApprovalStatus.APPROVED.value
        and operation.execution_status == ExecutionStatus.NOT_STARTED.value
        and operation.approval_execution_mode
        == ApprovalExecutionMode.AUTO_ON_APPROVAL.value
    ):
        return operation_executor.execute_after_approval(operation.id, actor_id)
    return operation


def _require_matching_callback_event(
    event: ExternalApprovalEvent,
    operation_request_id: int,
    external_instance_id: str,
    normalized_status: str,
) -> None:
    payload = event.payload
    if (
        event.operation_request_id != operation_request_id
        or event.external_instance_id != external_instance_id
        or not isinstance(payload, dict)
        or payload.get("status") != normalized_status
    ):
        raise BusinessException(
            "审批回调与已处理事件不一致",
            result_code=ResultCode.BAD_REQUEST,
        )


def submit(operation_request_id: int, actor_id: int) -> OperationRequest:
    operation = _require_operation(operation_request_id)
    if operation.approval_channel != ApprovalChannel.FEISHU.value:
        raise BusinessException("只有飞书审批申请可以提交 Provider")
    if operation.external_instance_id is not None:
        return operation
    provider = approval_provider_registry.get("FEISHU")
    operation.external_instance_id = provider.submit(operation.id)
    operation.submitted_at = operation.submitted_at or utc_now()
    operation.version += 1
    db.session.commit()
    return operation


def urge(operation_request_id: int, actor_id: int) -> None:
    operation = _require_operation(operation_request_id)
    if operation.approval_status != ApprovalStatus.PENDING.value:
        raise BusinessException("只有待审批申请可以催办")
    approval_provider_registry.get("FEISHU").urge(operation.id, actor_id)


def withdraw(operation_request_id: int, actor_id: int) -> OperationRequest:
    operation = _require_operation(operation_request_id)
    if operation.approval_status != ApprovalStatus.PENDING.value:
        return operation
    approval_provider_registry.get("FEISHU").withdraw(operation.id, actor_id)
    operation.approval_status = ApprovalStatus.WITHDRAWN.value
    operation.version += 1
    operation_service.release_locks(operation.id)
    db.session.commit()
    return operation


def handle_callback(
    *,
    provider: str,
    external_event_id: str,
    external_instance_id: str | None,
    status: str,
    actor_id: int,
) -> OperationRequest:
    normalized_provider = provider.strip().upper()
    if not external_instance_id:
        raise BusinessException("外部审批实例标识不能为空")
    normalized_status = status.strip().upper()
    if normalized_status not in {
        ApprovalStatus.APPROVED.value,
        ApprovalStatus.REJECTED.value,
        ApprovalStatus.WITHDRAWN.value,
    }:
        raise BusinessException("外部审批状态无效")
    operation = operation_request_repository.find_by_external_instance(
        external_instance_id
    )
    if operation is None:
        raise BusinessException("外部审批实例不存在", result_code=ResultCode.NOT_FOUND)
    operation_id = operation.id
    existing_event = external_approval_event_repository.find_by_event(
        normalized_provider, external_event_id
    )
    if existing_event is not None:
        _require_matching_callback_event(
            existing_event,
            operation_id,
            external_instance_id,
            normalized_status,
        )
        return _resume_auto_execution(operation, actor_id)
    try:
        event = external_approval_event_repository.add(
            ExternalApprovalEvent(
                operation_request_id=operation.id,
                provider=normalized_provider,
                external_event_id=external_event_id,
                external_instance_id=external_instance_id,
                event_type="APPROVAL_STATUS_CHANGED",
                payload={"status": normalized_status},
                processing_status="PROCESSING",
            )
        )
    except IntegrityError as error:
        message = str(error.orig).lower()
        if (
            "uq_external_approval_event_provider_event" not in message
            and "external_approval_events.provider" not in message
        ):
            raise
        db.session.rollback()
        duplicate = external_approval_event_repository.find_by_event(
            normalized_provider, external_event_id
        )
        if duplicate is None:
            raise BusinessException("审批回调正在处理中，请稍后重试") from None
        _require_matching_callback_event(
            duplicate,
            operation_id,
            external_instance_id,
            normalized_status,
        )
        return _resume_auto_execution(
            _require_operation(operation_id),
            actor_id,
        )

    expected_version = operation.version
    if not operation_request_repository.transition_pending(
        operation.id, expected_version, normalized_status
    ):
        db.session.expire(operation)
        event.processing_status = "IGNORED"
        event.processed_at = utc_now()
        db.session.commit()
        return _resume_auto_execution(operation, actor_id)

    db.session.expire(operation, ["approval_status", "version"])
    if normalized_status == ApprovalStatus.APPROVED.value:
        operation.approved_at = utc_now()
    else:
        operation_service.release_locks(operation.id)
    event.processing_status = "PROCESSED"
    event.processed_at = utc_now()
    db.session.commit()
    if normalized_status == ApprovalStatus.APPROVED.value:
        return _resume_auto_execution(operation, actor_id)
    return operation


def confirm_direct(operation_request_id: int, actor_id: int) -> OperationRequest:
    operation = _require_operation(operation_request_id)
    if operation.approval_channel != ApprovalChannel.DIRECT.value:
        raise BusinessException("只有直接确认申请可以执行此操作")
    if operation.approval_execution_mode == ApprovalExecutionMode.MANUAL_CONFIRM.value:
        raise BusinessException(
            "直接确认申请不能等待人工确认", result_code=ResultCode.BAD_REQUEST
        )
    if operation.approval_status == ApprovalStatus.PENDING.value:
        operation.approval_status = ApprovalStatus.APPROVED.value
        operation.approved_at = utc_now()
        operation.version += 1
        db.session.commit()
    if operation.approval_status != ApprovalStatus.APPROVED.value:
        raise BusinessException("当前申请不能直接确认")
    return operation_executor.execute_after_approval(operation.id, actor_id)


__all__ = [
    "confirm_direct",
    "handle_callback",
    "submit",
    "urge",
    "withdraw",
]
