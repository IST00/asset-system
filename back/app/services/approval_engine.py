"""Versioned multi-layer internal approval runtime."""

from __future__ import annotations

from dataclasses import dataclass

from app.common import BusinessException, ResultCode
from app.enums import (
    ApprovalAction,
    ApprovalChannel,
    ApprovalStatus,
    AssigneeType,
    RuntimeTaskStatus,
    SignMode,
)
from app.extensions import db
from app.models import (
    ApprovalFlowLayer,
    ApprovalRecord,
    ApprovalStep,
    ApprovalTask,
    OperationRequest,
)
from app.models.mixins import utc_now
from app.repositories import approval_flow_repository
from app.repositories.rbac_repository import rbac_repository
from app.repositories.workflow_repository import (
    approval_record_repository,
    approval_step_repository,
    approval_task_repository,
    operation_request_repository,
)
from app.services import permission_service


@dataclass(frozen=True)
class ApprovalOutcome:
    request_approved: bool = False
    request_rejected: bool = False
    next_layer_activated: bool = False


def _resolve_layer_approvers(
    layer: ApprovalFlowLayer,
    applicant_id: int,
    organization_id: int,
) -> list[int]:
    approver_ids: set[int] = set()
    for rule in layer.assignee_rules:
        if rule.assignee_type == AssigneeType.USER.value:
            user = rbac_repository.find_user(rule.assignee_id)
            if user is not None and user.enabled:
                approver_ids.add(user.id)
        elif rule.assignee_type == AssigneeType.ROLE.value:
            approver_ids.update(
                permission_service.enabled_role_member_ids(
                    rule.assignee_id, organization_id, applicant_id
                )
            )
    if not layer.allow_self_approval:
        approver_ids.discard(applicant_id)
    return sorted(approver_ids)


def initialize(
    operation: OperationRequest, flow_version_id: int, organization_id: int
) -> None:
    if operation.approval_status != ApprovalStatus.PENDING.value:
        raise BusinessException("只有待审批申请可以初始化审批流")
    if approval_step_repository.find_by_operation_ordered(operation.id):
        return
    version = approval_flow_repository.load_version_graph(flow_version_id)
    if version is None or not version.layers:
        raise BusinessException("审批流版本不存在或配置不完整")

    resolved_layers: list[tuple[ApprovalFlowLayer, list[int]]] = []
    for layer in version.layers:
        approver_ids = _resolve_layer_approvers(
            layer, operation.applicant_id, organization_id
        )
        if not approver_ids:
            raise BusinessException(f"审批第 {layer.level_no} 层没有有效审批人")
        resolved_layers.append((layer, approver_ids))

    for layer, approver_ids in resolved_layers:
        status = (
            RuntimeTaskStatus.PENDING.value
            if layer.level_no == 1
            else RuntimeTaskStatus.WAITING.value
        )
        step = approval_step_repository.add(
            ApprovalStep(
                operation_request_id=operation.id,
                flow_layer_id=layer.id,
                level_no=layer.level_no,
                sign_mode=layer.sign_mode,
                status=status,
            )
        )
        for approver_id in approver_ids:
            approval_task_repository.add(
                ApprovalTask(
                    approval_step_id=step.id,
                    approver_id=approver_id,
                    status=status,
                )
            )
    operation.approval_channel = ApprovalChannel.INTERNAL.value
    operation.approval_flow_version_id = flow_version_id
    operation.submitted_at = utc_now()


def _operation_for_decision(operation_request_id: int) -> OperationRequest:
    operation = operation_request_repository.find_for_update(operation_request_id)
    if operation is None:
        raise BusinessException("申请不存在", result_code=ResultCode.NOT_FOUND)
    if operation.approval_status != ApprovalStatus.PENDING.value:
        raise BusinessException("申请已完成审批，不能重复处理")
    return operation


def _claim_current_task(
    operation: OperationRequest, actor_id: int
) -> tuple[ApprovalStep, ApprovalTask]:
    step = approval_step_repository.find_current_for_update(operation.id)
    if step is None:
        raise BusinessException("当前审批步骤不存在")
    task = approval_task_repository.find_for_update(step.id, actor_id)
    if task is None:
        raise BusinessException("不是当前审批人", result_code=ResultCode.FORBIDDEN)
    if task.status != RuntimeTaskStatus.PENDING.value:
        raise BusinessException("审批任务已处理")
    if step.flow_layer_id is not None:
        layer = db.session.get(ApprovalFlowLayer, step.flow_layer_id)
        if (
            layer is not None
            and not layer.allow_self_approval
            and operation.applicant_id == actor_id
        ):
            raise BusinessException("该审批层不允许申请人自审")
    if not approval_step_repository.claim_pending(step.id, step.version):
        db.session.expire(step)
        raise BusinessException("审批任务已被其他人处理")
    db.session.expire(step, ["version"])
    return step, task


def _record(
    operation: OperationRequest,
    step: ApprovalStep,
    task: ApprovalTask,
    actor_id: int,
    action: str,
    opinion: str | None,
) -> None:
    approval_record_repository.add(
        ApprovalRecord(
            operation_request_id=operation.id,
            approval_step_id=step.id,
            approval_task_id=task.id,
            actor_id=actor_id,
            action=action,
            opinion=opinion,
        )
    )


def _withdraw_open_tasks(step: ApprovalStep, except_task_id: int | None = None) -> None:
    for task in approval_task_repository.find_by_step(step.id):
        if task.id != except_task_id and task.status in {
            RuntimeTaskStatus.PENDING.value,
            RuntimeTaskStatus.WAITING.value,
        }:
            task.status = RuntimeTaskStatus.WITHDRAWN.value
            task.version += 1


def _complete_layer(operation: OperationRequest, step: ApprovalStep) -> ApprovalOutcome:
    steps = approval_step_repository.find_by_operation_ordered(operation.id)
    next_step = next(
        (
            item
            for item in steps
            if item.level_no > step.level_no
            and item.status == RuntimeTaskStatus.WAITING.value
        ),
        None,
    )
    if next_step is not None:
        next_step.status = RuntimeTaskStatus.PENDING.value
        next_step.version += 1
        for task in approval_task_repository.find_by_step(next_step.id):
            if task.status == RuntimeTaskStatus.WAITING.value:
                task.status = RuntimeTaskStatus.PENDING.value
                task.version += 1
        return ApprovalOutcome(next_layer_activated=True)

    if not operation_request_repository.transition_pending(
        operation.id, operation.version, ApprovalStatus.APPROVED.value
    ):
        db.session.expire(operation)
        raise BusinessException("申请已被其他人完成审批")
    db.session.expire(operation, ["approval_status", "version"])
    operation.approved_at = utc_now()
    return ApprovalOutcome(request_approved=True)


def approve(
    operation_request_id: int, actor_id: int, opinion: str | None
) -> ApprovalOutcome:
    operation = _operation_for_decision(operation_request_id)
    step, task = _claim_current_task(operation, actor_id)
    task.status = RuntimeTaskStatus.APPROVED.value
    task.opinion = opinion
    task.decided_at = utc_now()
    task.version += 1
    _record(
        operation,
        step,
        task,
        actor_id,
        ApprovalAction.APPROVE.value,
        opinion,
    )

    if step.sign_mode == SignMode.AND_SIGN.value:
        db.session.flush()
        if any(
            item.status == RuntimeTaskStatus.PENDING.value
            for item in approval_task_repository.find_by_step(step.id)
        ):
            return ApprovalOutcome()
    else:
        _withdraw_open_tasks(step, except_task_id=task.id)

    step.status = RuntimeTaskStatus.APPROVED.value
    return _complete_layer(operation, step)


def reject(operation_request_id: int, actor_id: int, opinion: str) -> ApprovalOutcome:
    normalized_opinion = opinion.strip()
    if not normalized_opinion:
        raise BusinessException(
            "拒绝时必须填写原因", result_code=ResultCode.BAD_REQUEST
        )
    operation = _operation_for_decision(operation_request_id)
    step, task = _claim_current_task(operation, actor_id)
    task.status = RuntimeTaskStatus.REJECTED.value
    task.opinion = normalized_opinion
    task.decided_at = utc_now()
    task.version += 1
    step.status = RuntimeTaskStatus.REJECTED.value
    _withdraw_open_tasks(step, except_task_id=task.id)
    for later_step in approval_step_repository.find_by_operation_ordered(operation.id):
        if later_step.level_no > step.level_no and later_step.status in {
            RuntimeTaskStatus.WAITING.value,
            RuntimeTaskStatus.PENDING.value,
        }:
            later_step.status = RuntimeTaskStatus.WITHDRAWN.value
            later_step.version += 1
            _withdraw_open_tasks(later_step)
    _record(
        operation,
        step,
        task,
        actor_id,
        ApprovalAction.REJECT.value,
        normalized_opinion,
    )
    if not operation_request_repository.transition_pending(
        operation.id, operation.version, ApprovalStatus.REJECTED.value
    ):
        db.session.expire(operation)
        raise BusinessException("申请已被其他人完成审批")
    db.session.expire(operation, ["approval_status", "version"])
    return ApprovalOutcome(request_rejected=True)


def withdraw(operation_request_id: int, actor_id: int, reason: str | None) -> None:
    operation = _operation_for_decision(operation_request_id)
    if operation.applicant_id != actor_id:
        raise BusinessException("只有申请人可以撤回", result_code=ResultCode.FORBIDDEN)
    if not operation_request_repository.transition_pending(
        operation.id, operation.version, ApprovalStatus.WITHDRAWN.value
    ):
        db.session.expire(operation)
        raise BusinessException("申请已被其他人完成审批")
    db.session.expire(operation, ["approval_status", "version"])
    for step in approval_step_repository.find_by_operation_ordered(operation.id):
        if step.status in {
            RuntimeTaskStatus.PENDING.value,
            RuntimeTaskStatus.WAITING.value,
        }:
            step.status = RuntimeTaskStatus.WITHDRAWN.value
            step.version += 1
            _withdraw_open_tasks(step)


__all__ = ["ApprovalOutcome", "approve", "initialize", "reject", "withdraw"]
