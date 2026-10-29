"""Borrow due-date extension workflow."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.common import BusinessException, ResultCode
from app.enums import ApprovalStatus, ExecutionStatus, FulfillmentStatus, UsageMode
from app.extensions import db
from app.models import AssetBorrowExtensionRequest, AssetUsageRequest, OperationRequest
from app.models.mixins import utc_now
from app.repositories.asset_usage_return_repository import (
    asset_usage_request_repository,
)
from app.repositories.workflow_repository import operation_request_repository
from app.services import audit_service, permission_service

_SELF_PERMISSION = "asset:usage:self"
_MANAGE_PERMISSION = "asset:usage:manage"


def _operation(operation_request_id: int) -> tuple[OperationRequest, AssetUsageRequest]:
    operation = operation_request_repository.get(operation_request_id)
    if operation is None:
        raise BusinessException("借用申请不存在", result_code=ResultCode.NOT_FOUND)
    detail = asset_usage_request_repository.find_by_operation(operation.id)
    if detail is None or detail.usage_mode != UsageMode.BORROW.value:
        raise BusinessException("当前申请不是借用申请")
    if detail.target_user_id is None or detail.expected_return_at is None:
        raise BusinessException("借用申请缺少归还信息")
    if operation.approval_status != ApprovalStatus.APPROVED.value:
        raise BusinessException("只有审批通过的借用申请可以延期")
    if operation.execution_status != ExecutionStatus.SUCCESS.value:
        raise BusinessException("只有已完成领用的借用申请可以延期")
    if detail.fulfillment_status != FulfillmentStatus.COMPLETED.value:
        raise BusinessException("只有已签收的借用资产可以延期")
    return operation, detail


def _serialize(row: AssetBorrowExtensionRequest) -> dict[str, Any]:
    return {
        "id": row.id,
        "operation_request_id": row.operation_request_id,
        "applicant_id": row.applicant_id,
        "original_expected_return_at": row.original_expected_return_at.isoformat(),
        "requested_expected_return_at": row.requested_expected_return_at.isoformat(),
        "reason": row.reason,
        "status": row.status,
        "reviewed_by": row.reviewed_by,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        "review_opinion": row.review_opinion,
        "version": row.version,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def list_for_request(operation_request_id: int, actor_id: int) -> list[dict[str, Any]]:
    operation, detail = _operation(operation_request_id)
    if actor_id != detail.target_user_id:
        permission_service.require_permission(actor_id, _MANAGE_PERMISSION)
    rows = db.session.scalars(
        select(AssetBorrowExtensionRequest)
        .where(AssetBorrowExtensionRequest.operation_request_id == operation.id)
        .order_by(
            AssetBorrowExtensionRequest.created_at.desc(),
            AssetBorrowExtensionRequest.id.desc(),
        )
    ).all()
    return [_serialize(row) for row in rows]


def list_pending(actor_id: int) -> list[dict[str, Any]]:
    permission_service.require_permission(actor_id, _MANAGE_PERMISSION)
    rows = db.session.scalars(
        select(AssetBorrowExtensionRequest)
        .where(AssetBorrowExtensionRequest.status == "PENDING")
        .order_by(
            AssetBorrowExtensionRequest.created_at.asc(),
            AssetBorrowExtensionRequest.id.asc(),
        )
    ).all()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = _serialize(row)
        operation = operation_request_repository.get(row.operation_request_id)
        item["request_no"] = operation.request_no if operation is not None else None
        item["reason"] = row.reason
        result.append(item)
    return result


def create(
    operation_request_id: int,
    actor_id: int,
    requested_expected_return_at: datetime,
    reason: str,
) -> dict[str, Any]:
    permission_service.require_permission(actor_id, _SELF_PERMISSION)
    operation, detail = _operation(operation_request_id)
    if detail.target_user_id != actor_id:
        raise BusinessException(
            "只有借用员工本人可以申请延期", result_code=ResultCode.FORBIDDEN
        )
    if requested_expected_return_at.tzinfo is None:
        requested_expected_return_at = requested_expected_return_at.replace(
            tzinfo=timezone.utc
        )
    now = utc_now()
    current_due = detail.expected_return_at
    assert current_due is not None
    if requested_expected_return_at <= current_due:
        raise BusinessException(
            "延期后的归还时间必须晚于当前归还时间", result_code=ResultCode.BAD_REQUEST
        )
    if requested_expected_return_at <= now:
        raise BusinessException(
            "延期后的归还时间必须晚于当前时间", result_code=ResultCode.BAD_REQUEST
        )
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise BusinessException("延期原因不能为空", result_code=ResultCode.BAD_REQUEST)
    existing = db.session.scalar(
        select(AssetBorrowExtensionRequest).where(
            AssetBorrowExtensionRequest.operation_request_id == operation.id,
            AssetBorrowExtensionRequest.status == "PENDING",
        )
    )
    if existing is not None:
        raise BusinessException("当前借用申请已有延期申请待审批")
    row = AssetBorrowExtensionRequest(
        operation_request_id=operation.id,
        applicant_id=actor_id,
        original_expected_return_at=current_due,
        requested_expected_return_at=requested_expected_return_at,
        reason=normalized_reason,
    )
    db.session.add(row)
    db.session.flush()
    audit_service.record_resource_change(
        action="ASSET_BORROW_EXTENSION_REQUESTED",
        resource_type="asset_borrow_extension_request",
        resource_id=row.id,
        actor_id=actor_id,
        before_data={"expected_return_at": current_due.isoformat()},
        after_data={
            "requested_expected_return_at": requested_expected_return_at.isoformat(),
            "status": row.status,
            "operation_request_id": operation.id,
        },
        reason=normalized_reason,
    )
    db.session.commit()
    return _serialize(row)


def _review(
    extension_id: int,
    actor_id: int,
    opinion: str | None,
    *,
    approved: bool,
) -> dict[str, Any]:
    permission_service.require_permission(actor_id, _MANAGE_PERMISSION)
    row = db.session.get(AssetBorrowExtensionRequest, extension_id)
    if row is None:
        raise BusinessException("延期申请不存在", result_code=ResultCode.NOT_FOUND)
    operation, detail = _operation(row.operation_request_id)
    assert detail.expected_return_at is not None
    if row.status != "PENDING":
        return _serialize(row)
    normalized = opinion.strip() if opinion else None
    if not approved and not normalized:
        raise BusinessException(
            "拒绝延期必须填写原因", result_code=ResultCode.BAD_REQUEST
        )
    before = {
        "status": row.status,
        "expected_return_at": detail.expected_return_at.isoformat(),
    }
    row.status = "APPROVED" if approved else "REJECTED"
    row.reviewed_by = actor_id
    row.reviewed_at = utc_now()
    row.review_opinion = normalized
    row.version += 1
    if approved:
        detail.expected_return_at = row.requested_expected_return_at
    audit_service.record_resource_change(
        action="ASSET_BORROW_EXTENSION_APPROVED"
        if approved
        else "ASSET_BORROW_EXTENSION_REJECTED",
        resource_type="asset_borrow_extension_request",
        resource_id=row.id,
        actor_id=actor_id,
        before_data=before,
        after_data={
            "status": row.status,
            "expected_return_at": detail.expected_return_at.isoformat(),
            "review_opinion": normalized,
        },
        reason=normalized,
    )
    db.session.commit()
    return _serialize(row)


def approve(
    extension_id: int, actor_id: int, opinion: str | None = None
) -> dict[str, Any]:
    return _review(extension_id, actor_id, opinion, approved=True)


def reject(extension_id: int, actor_id: int, opinion: str) -> dict[str, Any]:
    return _review(extension_id, actor_id, opinion, approved=False)


__all__ = ["approve", "create", "list_for_request", "list_pending", "reject"]
