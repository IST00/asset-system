"""Approval state persistence independent of asset execution."""

from __future__ import annotations

from app.common import BusinessException, ResultCode
from app.enums import ApprovalAction, ApprovalStatus
from app.extensions import db
from app.models import ApprovalRecord, ApprovalStep, ApprovalTask, OperationRequest
from app.models.mixins import utc_now
from app.repositories.workflow_repository import (
    approval_record_repository,
    approval_step_repository,
    approval_task_repository,
    operation_request_repository,
)


def create_initial_step(
    operation_request_id: int, approver_ids: list[int]
) -> ApprovalStep:
    step = ApprovalStep(
        operation_request_id=operation_request_id,
        level_no=1,
        status=ApprovalStatus.PENDING.value,
    )
    approval_step_repository.add(step)
    for approver_id in approver_ids:
        approval_task_repository.add(
            ApprovalTask(
                approval_step_id=step.id,
                approver_id=approver_id,
                status=ApprovalStatus.PENDING.value,
            )
        )
    return step


def _pending_task(
    operation: OperationRequest, actor_id: int
) -> tuple[ApprovalStep, ApprovalTask]:
    step = approval_step_repository.find_by_operation(operation.id)
    if step is None:
        raise BusinessException("审批步骤不存在")
    task = approval_task_repository.find_for_approver(step.id, actor_id)
    if task is None:
        raise BusinessException("不是本申请的审批人", result_code=ResultCode.FORBIDDEN)
    if operation.approval_status != ApprovalStatus.PENDING.value:
        raise BusinessException("申请已完成审批，不能重复处理")
    if task.status != ApprovalStatus.PENDING.value:
        raise BusinessException("审批任务已处理")
    return step, task


def _claim_pending(operation: OperationRequest, target_status: str) -> None:
    if not operation_request_repository.transition_pending(
        operation.id, operation.version, target_status
    ):
        db.session.expire(operation)
        raise BusinessException("申请已完成审批，不能重复处理")
    db.session.expire(operation, ["approval_status", "version"])


def approve(operation: OperationRequest, actor_id: int, opinion: str | None) -> None:
    step, task = _pending_task(operation, actor_id)
    _claim_pending(operation, ApprovalStatus.APPROVED.value)
    task.status = ApprovalStatus.APPROVED.value
    task.opinion = opinion
    task.decided_at = utc_now()
    step.status = ApprovalStatus.APPROVED.value
    for other in approval_task_repository.find_by_step(step.id):
        if other.id != task.id and other.status == ApprovalStatus.PENDING.value:
            other.status = ApprovalStatus.WITHDRAWN.value
    approval_record_repository.add(
        ApprovalRecord(
            operation_request_id=operation.id,
            approval_step_id=step.id,
            approval_task_id=task.id,
            actor_id=actor_id,
            action=ApprovalAction.APPROVE.value,
            opinion=opinion,
        )
    )


def reject(operation: OperationRequest, actor_id: int, opinion: str) -> None:
    if not opinion.strip():
        raise BusinessException(
            "拒绝时必须填写原因", result_code=ResultCode.BAD_REQUEST
        )
    step, task = _pending_task(operation, actor_id)
    _claim_pending(operation, ApprovalStatus.REJECTED.value)
    task.status = ApprovalStatus.REJECTED.value
    task.opinion = opinion.strip()
    task.decided_at = utc_now()
    step.status = ApprovalStatus.REJECTED.value
    for other in approval_task_repository.find_by_step(step.id):
        if other.id != task.id and other.status == ApprovalStatus.PENDING.value:
            other.status = ApprovalStatus.WITHDRAWN.value
    approval_record_repository.add(
        ApprovalRecord(
            operation_request_id=operation.id,
            approval_step_id=step.id,
            approval_task_id=task.id,
            actor_id=actor_id,
            action=ApprovalAction.REJECT.value,
            opinion=opinion.strip(),
        )
    )


def withdraw(operation: OperationRequest) -> None:
    if operation.approval_status != ApprovalStatus.PENDING.value:
        raise BusinessException("当前申请不能撤回")
    step = approval_step_repository.find_by_operation(operation.id)
    if step is None:
        raise BusinessException("审批步骤不存在")
    _claim_pending(operation, ApprovalStatus.WITHDRAWN.value)
    step.status = ApprovalStatus.WITHDRAWN.value
    for task in approval_task_repository.find_by_step(step.id):
        if task.status == ApprovalStatus.PENDING.value:
            task.status = ApprovalStatus.WITHDRAWN.value


__all__ = ["approve", "create_initial_step", "reject", "withdraw"]
