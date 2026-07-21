"""Common operation-request creation and immutable asset snapshots."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from sqlalchemy import false, func, inspect, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import InstanceState

from app.common import BusinessException, ResultCode
from app.enums import (
    ApprovalChannel,
    ApprovalExecutionMode,
    ApprovalStatus,
    ExecutionStatus,
)
from app.extensions import db
from app.models import (
    Asset,
    AssetLocation,
    ApprovalStep,
    ApprovalTask,
    OperationActionIdempotency,
    OperationExecutionAttempt,
    OperationRequest,
    OperationRequestAsset,
    PublicUsageObject,
    StockInRequest,
)
from app.models.mixins import utc_now
from app.repositories import (
    operation_action_idempotency_repository,
    operation_request_asset_repository,
)
from app.repositories.rbac_repository import rbac_repository
from app.repositories.workflow_repository import (
    approval_step_repository,
    approval_task_repository,
    operation_request_repository,
)
from app.services import asset_lock_service, permission_service


@dataclass(frozen=True)
class CreateOperationResult:
    operation: OperationRequest
    created: bool


def _request_no() -> str:
    return f"OPR{utc_now():%Y%m%d%H%M%S}{uuid4().hex[:12].upper()}"


def _is_operation_idempotency_conflict(error: IntegrityError) -> bool:
    message = str(error.orig).lower()
    return (
        "uq_operation_request_idempotency" in message
        or "operation_requests.applicant_id, "
        "operation_requests.operation_type, "
        "operation_requests.idempotency_key"
        in message
    )


def _holder_snapshot(asset: Asset) -> dict[str, Any] | None:
    if asset.holder_user_id is None:
        return None
    user = rbac_repository.find_user(asset.holder_user_id)
    if user is None:
        return {"id": asset.holder_user_id, "name": None}
    return {"id": user.id, "name": user.nickname or user.username}


def _location_snapshot(asset: Asset) -> dict[str, Any] | None:
    location = db.session.get(AssetLocation, asset.location_id)
    if location is None:
        return {"id": asset.location_id, "code": None, "name": None}
    return {"id": location.id, "code": location.code, "name": location.name}


def _before_data(asset: Asset) -> dict[str, Any]:
    public_object = (
        db.session.get(PublicUsageObject, asset.public_object_id)
        if asset.public_object_id is not None
        else None
    )
    return {
        "status": asset.status,
        "organization_id": asset.organization_id,
        "usage_type": asset.usage_type,
        "holder_user_id": asset.holder_user_id,
        "public_object_id": asset.public_object_id,
        "public_object_name": public_object.name if public_object is not None else None,
        "usage_department_id": asset.usage_department_id,
        "location_id": asset.location_id,
        "manager_id": asset.manager_id,
        "parent_asset_id": asset.parent_asset_id,
        "version": asset.version,
    }


def get_by_idempotency_key(
    actor_id: int, operation_type: str, key: str
) -> OperationRequest | None:
    normalized_key = key.strip()
    if not normalized_key:
        return None
    return operation_request_repository.find_by_idempotency_key(
        actor_id, operation_type.strip().upper(), normalized_key
    )


def _validate_assets_and_targets(
    assets: list[Asset],
    target_data_by_asset_id: Mapping[int, Mapping[str, Any]],
) -> list[Asset]:
    if not assets:
        raise BusinessException("申请至少包含一项资产")
    current_session = db.session()
    for asset in assets:
        state: InstanceState[Asset] = inspect(asset)
        if not state.persistent or state.session is not current_session:
            raise BusinessException("申请资产必须是当前事务中的持久化资产")
    ordered = sorted(assets, key=lambda asset: asset.id)
    asset_ids = [asset.id for asset in ordered]
    if any(asset_id is None for asset_id in asset_ids) or len(set(asset_ids)) != len(
        asset_ids
    ):
        raise BusinessException("申请包含重复或未保存的资产")
    if set(target_data_by_asset_id) != set(asset_ids):
        raise BusinessException("申请资产与目标快照不一致")
    for target in target_data_by_asset_id.values():
        try:
            json.dumps(dict(target), allow_nan=False)
        except (TypeError, ValueError) as error:
            raise BusinessException("资产目标快照不是有效 JSON") from error
    return ordered


def create_request(
    *,
    operation_type: str,
    applicant_id: int,
    approval_channel: str,
    approval_execution_mode: str,
    assets: list[Asset],
    target_data_by_asset_id: Mapping[int, Mapping[str, Any]],
    idempotency_key: str | None,
    parent_request_id: int | None = None,
) -> CreateOperationResult:
    normalized_type = operation_type.strip().upper()
    if approval_channel not in {item.value for item in ApprovalChannel}:
        raise BusinessException("审批通道无效", result_code=ResultCode.BAD_REQUEST)
    if approval_execution_mode not in {item.value for item in ApprovalExecutionMode}:
        raise BusinessException(
            "审批后执行模式无效", result_code=ResultCode.BAD_REQUEST
        )
    if (
        approval_channel == ApprovalChannel.DIRECT.value
        and approval_execution_mode == ApprovalExecutionMode.MANUAL_CONFIRM.value
    ):
        raise BusinessException(
            "直接确认申请不能等待人工验收", result_code=ResultCode.BAD_REQUEST
        )
    applicant = rbac_repository.find_user(applicant_id)
    if applicant is None or not applicant.enabled:
        raise BusinessException("申请人不存在或已停用")
    ordered_assets = _validate_assets_and_targets(assets, target_data_by_asset_id)
    normalized_key = idempotency_key.strip() if idempotency_key else None
    if normalized_key:
        existing = get_by_idempotency_key(applicant_id, normalized_type, normalized_key)
        if existing is not None:
            return CreateOperationResult(operation=existing, created=False)
    if (
        parent_request_id is not None
        and operation_request_repository.get(parent_request_id) is None
    ):
        raise BusinessException("原申请不存在", result_code=ResultCode.NOT_FOUND)

    try:
        operation = operation_request_repository.add(
            OperationRequest(
                request_no=_request_no(),
                operation_type=normalized_type,
                applicant_id=applicant_id,
                parent_request_id=parent_request_id,
                approval_channel=approval_channel,
                approval_execution_mode=approval_execution_mode,
                idempotency_key=normalized_key,
                approval_status=ApprovalStatus.PENDING.value,
                execution_status=ExecutionStatus.NOT_STARTED.value,
                submitted_at=utc_now(),
            )
        )
    except IntegrityError as error:
        if normalized_key is None or not _is_operation_idempotency_conflict(error):
            raise
        db.session.rollback()
        existing = get_by_idempotency_key(applicant_id, normalized_type, normalized_key)
        if existing is None:
            raise
        return CreateOperationResult(operation=existing, created=False)
    for asset in ordered_assets:
        operation_request_asset_repository.add(
            OperationRequestAsset(
                operation_request_id=operation.id,
                asset_id=asset.id,
                asset_code_snapshot=asset.asset_code,
                asset_name_snapshot=asset.asset_name,
                asset_status_snapshot=asset.status,
                asset_version_snapshot=asset.version,
                organization_id_snapshot=asset.organization_id,
                holder_snapshot=_holder_snapshot(asset),
                location_snapshot=_location_snapshot(asset),
                before_data=_before_data(asset),
                target_data=dict(target_data_by_asset_id[asset.id]),
            )
        )
    asset_lock_service.acquire(operation, ordered_assets)
    return CreateOperationResult(operation=operation, created=True)


def release_locks(operation_request_id: int) -> None:
    asset_lock_service.release(operation_request_id)


_AMOUNT_KEYS = {
    "original_amount",
    "amount",
    "repair_cost",
    "scrap_amount",
}


def _protect_amounts(value: Any, can_view_amount: bool) -> Any:
    if can_view_amount:
        return value
    if isinstance(value, dict):
        return {
            key: _protect_amounts(item, can_view_amount)
            for key, item in value.items()
            if key not in _AMOUNT_KEYS
        }
    if isinstance(value, list):
        return [_protect_amounts(item, can_view_amount) for item in value]
    return value


def _serialize(operation: OperationRequest, actor_id: int) -> dict[str, Any]:
    can_view_amount = permission_service.has_permission(actor_id, "asset:amount:view")
    assets = operation_request_asset_repository.find_by_request(operation.id)
    steps = approval_step_repository.find_by_operation_ordered(operation.id)
    attempts = list(
        db.session.scalars(
            select(OperationExecutionAttempt)
            .where(OperationExecutionAttempt.operation_request_id == operation.id)
            .order_by(OperationExecutionAttempt.attempt_no.asc())
        ).all()
    )
    return {
        "id": operation.id,
        "request_no": operation.request_no,
        "operation_type": operation.operation_type,
        "applicant_id": operation.applicant_id,
        "approval_channel": operation.approval_channel,
        "approval_execution_mode": operation.approval_execution_mode,
        "approval_status": operation.approval_status,
        "execution_status": operation.execution_status,
        "execution_error": operation.execution_error,
        "assets": [
            {
                "asset_id": item.asset_id,
                "asset_code": item.asset_code_snapshot,
                "asset_name": item.asset_name_snapshot,
                "asset_status": item.asset_status_snapshot,
                "asset_version": item.asset_version_snapshot,
                "organization_id": item.organization_id_snapshot,
                "holder_snapshot": _protect_amounts(
                    item.holder_snapshot, can_view_amount
                ),
                "location_snapshot": _protect_amounts(
                    item.location_snapshot, can_view_amount
                ),
                "before_data": _protect_amounts(item.before_data, can_view_amount),
                "target_data": _protect_amounts(item.target_data, can_view_amount),
            }
            for item in assets
        ],
        "approval_timeline": [
            {
                "id": step.id,
                "level_no": step.level_no,
                "sign_mode": step.sign_mode,
                "status": step.status,
                "tasks": [
                    {
                        "id": task.id,
                        "approver_id": task.approver_id,
                        "status": task.status,
                        "opinion": task.opinion,
                    }
                    for task in approval_task_repository.find_by_step(step.id)
                ],
            }
            for step in steps
        ],
        "execution_attempts": [
            {
                "attempt_no": attempt.attempt_no,
                "trigger_type": attempt.trigger_type,
                "status": attempt.status,
                "error_code": attempt.error_code,
                "safe_error_message": attempt.safe_error_message,
            }
            for attempt in attempts
        ],
        "termination_reason": operation.termination_reason,
        "terminated_by": operation.terminated_by,
    }


def _access_filter(actor_id: int):
    organization_ids = permission_service.accessible_organization_ids(actor_id)
    if organization_ids is None:
        return OperationRequest.id.is_not(None)
    scope_filters = [OperationRequest.applicant_id == actor_id]
    if organization_ids:
        scope_filters.append(
            OperationRequestAsset.organization_id_snapshot.in_(organization_ids)
        )
    return or_(*scope_filters) if scope_filters else false()


def list_requests(actor_id: int, page: int = 0, size: int = 50) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "operation:request:view")
    access_filter = _access_filter(actor_id)
    base = (
        select(OperationRequest)
        .outerjoin(
            OperationRequestAsset,
            OperationRequestAsset.operation_request_id == OperationRequest.id,
        )
        .where(access_filter)
        .distinct()
    )
    all_ids = list(
        db.session.scalars(base.with_only_columns(OperationRequest.id)).all()
    )
    operations = list(
        db.session.scalars(
            base.order_by(OperationRequest.id.desc()).limit(size).offset(page * size)
        ).all()
    )
    return {
        "items": [_serialize(operation, actor_id) for operation in operations],
        "total": len(all_ids),
        "page": page,
        "size": size,
    }


def get_request(operation_request_id: int, actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "operation:request:view")
    statement = (
        select(OperationRequest)
        .outerjoin(
            OperationRequestAsset,
            OperationRequestAsset.operation_request_id == OperationRequest.id,
        )
        .where(
            OperationRequest.id == operation_request_id,
            _access_filter(actor_id),
        )
        .distinct()
    )
    operation = db.session.scalar(statement)
    if operation is None:
        raise BusinessException(
            "申请不存在或无权查看", result_code=ResultCode.NOT_FOUND
        )
    return _serialize(operation, actor_id)


def my_tasks(actor_id: int) -> list[dict[str, Any]]:
    permission_service.require_permission(actor_id, "approval:task:view")
    statement = (
        select(ApprovalTask, ApprovalStep, OperationRequest)
        .join(ApprovalStep, ApprovalStep.id == ApprovalTask.approval_step_id)
        .join(
            OperationRequest,
            OperationRequest.id == ApprovalStep.operation_request_id,
        )
        .where(ApprovalTask.approver_id == actor_id)
        .order_by(ApprovalTask.id.desc())
    )
    return [
        {
            "id": task.id,
            "operation_request_id": operation.id,
            "request_no": operation.request_no,
            "operation_type": operation.operation_type,
            "level_no": step.level_no,
            "status": task.status,
        }
        for task, step, operation in db.session.execute(statement).tuples().all()
    ]


def _task_operation(
    task_id: int, actor_id: int, *, require_current: bool = True
) -> OperationRequest:
    statement = (
        select(ApprovalTask, ApprovalStep, OperationRequest)
        .join(ApprovalStep, ApprovalStep.id == ApprovalTask.approval_step_id)
        .join(
            OperationRequest,
            OperationRequest.id == ApprovalStep.operation_request_id,
        )
        .where(ApprovalTask.id == task_id)
    )
    row = db.session.execute(statement).tuples().one_or_none()
    if row is None:
        raise BusinessException("审批任务不存在", result_code=ResultCode.NOT_FOUND)
    task, _step, operation = row
    if task.approver_id != actor_id:
        raise BusinessException("不是该任务审批人", result_code=ResultCode.FORBIDDEN)
    if require_current:
        current_step = approval_step_repository.find_current_for_update(operation.id)
        if (
            current_step is None
            or current_step.id != task.approval_step_id
            or task.status != "PENDING"
        ):
            raise BusinessException("该任务不是当前待审批任务")
    return operation


def _claim_action(
    operation_request_id: int,
    actor_id: int,
    action: str,
    idempotency_key: str | None,
) -> tuple[OperationActionIdempotency | None, bool]:
    normalized_key = idempotency_key.strip() if idempotency_key else None
    if not normalized_key:
        return None, False
    record = OperationActionIdempotency(
        operation_request_id=operation_request_id,
        actor_id=actor_id,
        action=action,
        idempotency_key=normalized_key,
        status="PROCESSING",
    )
    try:
        operation_action_idempotency_repository.add(record)
        return record, False
    except IntegrityError as error:
        message = str(error.orig).lower()
        is_conflict = (
            "uq_operation_action_idempotency" in message
            or "operation_action_idempotencies.operation_request_id, "
            "operation_action_idempotencies.actor_id, "
            "operation_action_idempotencies.action, "
            "operation_action_idempotencies.idempotency_key"
            in message
        )
        if not is_conflict:
            raise
        db.session.rollback()
        existing = operation_action_idempotency_repository.find_by_key(
            operation_request_id, actor_id, action, normalized_key
        )
        if existing is None:
            raise
        return existing, True


def _serialize_replayed_action(
    record: OperationActionIdempotency, actor_id: int
) -> dict[str, Any]:
    if record.status == "PROCESSING":
        raise BusinessException("请求正在处理中，请稍后重试")
    operation = operation_request_repository.get(record.operation_request_id)
    if operation is None:
        raise BusinessException("申请不存在", result_code=ResultCode.NOT_FOUND)
    return _serialize(operation, actor_id)


def _require_action_scope(operation_request_id: int, actor_id: int) -> None:
    organization_ids = permission_service.accessible_organization_ids(actor_id)
    if organization_ids is None:
        return
    snapshot_count = int(
        db.session.scalar(
            select(func.count(OperationRequestAsset.id)).where(
                OperationRequestAsset.operation_request_id == operation_request_id
            )
        )
        or 0
    )
    if snapshot_count:
        if not organization_ids:
            raise BusinessException(
                "无该申请的数据权限", result_code=ResultCode.FORBIDDEN
            )
        outside_count = int(
            db.session.scalar(
                select(func.count(OperationRequestAsset.id)).where(
                    OperationRequestAsset.operation_request_id == operation_request_id,
                    OperationRequestAsset.organization_id_snapshot.not_in(
                        organization_ids
                    ),
                )
            )
            or 0
        )
        if outside_count:
            raise BusinessException(
                "无该申请的数据权限", result_code=ResultCode.FORBIDDEN
            )
        return
    stock_in_organization_id = db.session.scalar(
        select(StockInRequest.organization_id).where(
            StockInRequest.operation_request_id == operation_request_id
        )
    )
    if (
        stock_in_organization_id is None
        or stock_in_organization_id not in organization_ids
    ):
        raise BusinessException("无该申请的数据权限", result_code=ResultCode.FORBIDDEN)


def approve_task(
    task_id: int,
    actor_id: int,
    opinion: str | None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "approval:task:approve")
    operation = _task_operation(task_id, actor_id, require_current=False)
    action_record, replayed = _claim_action(
        operation.id, actor_id, "APPROVE", idempotency_key
    )
    if replayed:
        assert action_record is not None
        return _serialize_replayed_action(action_record, actor_id)
    operation = _task_operation(task_id, actor_id)
    from app.services import approval_engine, operation_executor

    outcome = approval_engine.approve(operation.id, actor_id, opinion)
    db.session.commit()
    if outcome.request_approved:
        operation = operation_executor.execute_after_approval(operation.id, actor_id)
    if action_record is not None:
        action_record.status = "COMPLETED"
        db.session.commit()
    return _serialize(operation, actor_id)


def reject_task(
    task_id: int,
    actor_id: int,
    opinion: str,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "approval:task:approve")
    operation = _task_operation(task_id, actor_id, require_current=False)
    action_record, replayed = _claim_action(
        operation.id, actor_id, "REJECT", idempotency_key
    )
    if replayed:
        assert action_record is not None
        return _serialize_replayed_action(action_record, actor_id)
    operation = _task_operation(task_id, actor_id)
    from app.services import approval_engine

    approval_engine.reject(operation.id, actor_id, opinion)
    release_locks(operation.id)
    if action_record is not None:
        action_record.status = "COMPLETED"
    db.session.commit()
    return _serialize(operation, actor_id)


def withdraw_request(
    operation_request_id: int,
    actor_id: int,
    reason: str | None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    operation = operation_request_repository.get(operation_request_id)
    if operation is None:
        raise BusinessException("申请不存在", result_code=ResultCode.NOT_FOUND)
    if operation.applicant_id != actor_id:
        raise BusinessException("只有申请人可以撤回", result_code=ResultCode.FORBIDDEN)
    action_record, replayed = _claim_action(
        operation_request_id, actor_id, "WITHDRAW", idempotency_key
    )
    if replayed:
        assert action_record is not None
        return _serialize_replayed_action(action_record, actor_id)
    from app.services import approval_engine

    approval_engine.withdraw(operation_request_id, actor_id, reason)
    release_locks(operation_request_id)
    if action_record is not None:
        action_record.status = "COMPLETED"
    db.session.commit()
    operation = operation_request_repository.get(operation_request_id)
    if operation is None:
        raise BusinessException("申请不存在", result_code=ResultCode.NOT_FOUND)
    return _serialize(operation, actor_id)


def retry_request(
    operation_request_id: int,
    actor_id: int,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "approval:execution:retry")
    _require_action_scope(operation_request_id, actor_id)
    operation = operation_request_repository.get(operation_request_id)
    if operation is None:
        raise BusinessException("申请不存在", result_code=ResultCode.NOT_FOUND)
    action_record, replayed = _claim_action(
        operation_request_id, actor_id, "RETRY", idempotency_key
    )
    if replayed:
        assert action_record is not None
        return _serialize_replayed_action(action_record, actor_id)
    if operation.approval_status != ApprovalStatus.APPROVED.value:
        raise BusinessException("只有审批通过的申请可以执行")
    if operation.execution_status != ExecutionStatus.FAILED.value:
        raise BusinessException("只有执行失败的申请可以重试")
    if action_record is not None:
        db.session.commit()
    from app.services import operation_executor

    operation = operation_executor.retry(operation_request_id, actor_id)
    if action_record is not None:
        persisted_record = operation_action_idempotency_repository.find_by_key(
            operation_request_id,
            actor_id,
            "RETRY",
            action_record.idempotency_key,
        )
        if persisted_record is None:
            raise RuntimeError("durable retry idempotency claim missing")
        persisted_record.status = "COMPLETED"
        db.session.commit()
    return _serialize(operation, actor_id)


def terminate_request(
    operation_request_id: int,
    actor_id: int,
    reason: str,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "approval:execution:terminate")
    _require_action_scope(operation_request_id, actor_id)
    action_record, replayed = _claim_action(
        operation_request_id, actor_id, "TERMINATE", idempotency_key
    )
    if replayed:
        assert action_record is not None
        return _serialize_replayed_action(action_record, actor_id)
    from app.services import operation_executor

    operation = operation_executor.terminate(operation_request_id, actor_id, reason)
    if action_record is not None:
        action_record.status = "COMPLETED"
        db.session.commit()
    return _serialize(operation, actor_id)


__all__ = [
    "CreateOperationResult",
    "approve_task",
    "create_request",
    "get_by_idempotency_key",
    "get_request",
    "list_requests",
    "my_tasks",
    "reject_task",
    "release_locks",
    "retry_request",
    "terminate_request",
    "withdraw_request",
]
