"""Persistent notification inbox backed by actionable asset tasks."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select

from app.common import BusinessException, PageResult, ResultCode
from app.enums import (
    ApprovalStatus,
    ExecutionStatus,
    FulfillmentStatus,
    RuntimeTaskStatus,
    UsageMode,
)
from flask import current_app

from app.extensions import db
from app.models import (
    AssetReturnRequest,
    AssetTransferHandover,
    AssetUsageRequest,
    ApprovalTask,
    OperationRequest,
    UserNotification,
)
from app.models.mixins import utc_now
from app.services import permission_service


def _serialize(row: UserNotification) -> dict[str, Any]:
    return {
        "id": row.id,
        "notification_type": row.notification_type,
        "title": row.title,
        "content": row.content,
        "related_operation_id": row.related_operation_id,
        "related_asset_id": row.related_asset_id,
        "read_at": row.read_at.isoformat() if row.read_at else None,
        "created_at": row.created_at.isoformat(),
    }


def _add(
    user_id: int,
    notification_type: str,
    title: str,
    content: str,
    deduplication_key: str,
    *,
    operation_id: int | None = None,
    asset_id: int | None = None,
) -> None:
    existing = db.session.scalar(
        select(UserNotification).where(
            UserNotification.user_id == user_id,
            UserNotification.deduplication_key == deduplication_key,
        )
    )
    if existing is not None:
        return
    db.session.add(
        UserNotification(
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            content=content,
            related_operation_id=operation_id,
            related_asset_id=asset_id,
            deduplication_key=deduplication_key,
        )
    )


def sync_for_user(user_id: int) -> None:
    """Materialize currently actionable tasks and fan out Feishu messages."""
    pending_approval = db.session.scalars(
        select(ApprovalTask).where(
            ApprovalTask.approver_id == user_id,
            ApprovalTask.status == RuntimeTaskStatus.PENDING.value,
        )
    ).all()
    for task in pending_approval:
        _add(
            user_id,
            "APPROVAL",
            "有新的审批待处理",
            f"申请 #{task.operation_request_id} 等待你审批",
            f"APPROVAL:{task.id}:{task.version}",
            operation_id=task.operation_request_id,
        )

    pending_issue = db.session.scalars(
        select(AssetUsageRequest)
        .join(
            OperationRequest,
            OperationRequest.id == AssetUsageRequest.operation_request_id,
        )
        .where(
            AssetUsageRequest.fulfillment_status
            == FulfillmentStatus.PENDING_ISSUE.value,
            OperationRequest.approval_status == ApprovalStatus.APPROVED.value,
            OperationRequest.execution_status == ExecutionStatus.NOT_STARTED.value,
        )
    ).all()
    if permission_service.has_permission(user_id, "asset:usage:manage"):
        for row in pending_issue:
            _add(
                user_id,
                "ASSET_ISSUE",
                "待管理员发放资产",
                f"领用申请 #{row.operation_request_id} 已审批通过，请选择具体资产发放",
                f"ASSET_ISSUE:{row.operation_request_id}",
                operation_id=row.operation_request_id,
            )

    pending_sign = db.session.scalars(
        select(AssetUsageRequest)
        .join(
            OperationRequest,
            OperationRequest.id == AssetUsageRequest.operation_request_id,
        )
        .where(
            AssetUsageRequest.target_user_id == user_id,
            AssetUsageRequest.fulfillment_status
            == FulfillmentStatus.PENDING_SIGN.value,
            OperationRequest.approval_status == ApprovalStatus.APPROVED.value,
            OperationRequest.execution_status == ExecutionStatus.NOT_STARTED.value,
        )
    ).all()
    for row in pending_sign:
        _add(
            user_id,
            "ASSET_SIGN",
            "有资产待你签收",
            f"领用申请 #{row.operation_request_id} 已发放，请确认签收",
            f"ASSET_SIGN:{row.operation_request_id}",
            operation_id=row.operation_request_id,
        )

    if permission_service.has_permission(user_id, "asset:usage:manage"):
        pending_inspection = db.session.scalars(
            select(AssetReturnRequest)
            .join(
                OperationRequest,
                OperationRequest.id == AssetReturnRequest.operation_request_id,
            )
            .where(
                OperationRequest.approval_status == ApprovalStatus.APPROVED.value,
                OperationRequest.execution_status == ExecutionStatus.NOT_STARTED.value,
                AssetReturnRequest.confirmed_at.is_(None),
            )
        ).all()
        for row in pending_inspection:
            _add(
                user_id,
                "ASSET_RETURN_INSPECTION",
                "待管理员验收退库资产",
                f"退库申请 #{row.operation_request_id} 已交还，请完成验收",
                f"ASSET_RETURN_INSPECTION:{row.operation_request_id}",
                operation_id=row.operation_request_id,
            )

    pending_handovers = db.session.scalars(
        select(AssetTransferHandover).where(
            AssetTransferHandover.receiver_user_id == user_id,
            AssetTransferHandover.status == "PENDING_RECEIPT",
        )
    ).all()
    for row in pending_handovers:
        _add(
            user_id,
            "ASSET_TRANSFER_RECEIPT",
            "有资产交接待你签收",
            f"交接单 {row.handover_no} 等待你确认接收",
            f"ASSET_TRANSFER_RECEIPT:{row.id}:{row.version}",
        )

    if permission_service.has_permission(user_id, "asset:usage:manage"):
        pending_outgoing = db.session.scalars(
            select(AssetTransferHandover).where(
                AssetTransferHandover.status == "PENDING_OUTGOING"
            )
        ).all()
        for row in pending_outgoing:
            _add(
                user_id,
                "ASSET_TRANSFER_OUTGOING",
                "待管理员确认资产转出",
                f"交接单 {row.handover_no} 等待确认转出",
                f"ASSET_TRANSFER_OUTGOING:{row.id}:{row.version}",
            )

    now = datetime.now(timezone.utc)
    due_soon = now + timedelta(days=7)
    borrowed = db.session.scalars(
        select(AssetUsageRequest).where(
            AssetUsageRequest.target_user_id == user_id,
            AssetUsageRequest.usage_mode == UsageMode.BORROW.value,
            AssetUsageRequest.fulfillment_status == FulfillmentStatus.COMPLETED.value,
            AssetUsageRequest.expected_return_at.is_not(None),
        )
    ).all()
    for row in borrowed:
        due = row.expected_return_at
        if due is None:
            continue
        normalized_due = due if due.tzinfo else due.replace(tzinfo=timezone.utc)
        if normalized_due <= now:
            title, kind = "借用资产已逾期", "BORROW_OVERDUE"
        elif normalized_due <= due_soon:
            title, kind = "借用资产即将到期", "BORROW_DUE_SOON"
        else:
            continue
        _add(
            user_id,
            kind,
            title,
            f"借用申请 #{row.operation_request_id} 的预计归还时间为 {normalized_due.isoformat()}",
            f"{kind}:{row.operation_request_id}:{normalized_due.isoformat()}",
            operation_id=row.operation_request_id,
        )
    new_rows = [row for row in db.session.new if isinstance(row, UserNotification)]
    db.session.commit()
    _notify_new_rows(user_id, new_rows)


def _notify_new_rows(user_id: int, rows: list[UserNotification]) -> None:
    from app.services import feishu_notification_service

    if not feishu_notification_service.feishu_service.notifications_enabled():
        return
    for row in rows:
        try:
            feishu_notification_service.send_to_user(user_id, row.title, row.content)
        except Exception:
            db.session.rollback()
            current_app.logger.warning(
                "Feishu notification delivery failed for user %s notification %s",
                user_id,
                row.id,
                exc_info=True,
            )


def page(user_id: int, page: int, size: int, unread_only: bool = False) -> PageResult:
    sync_for_user(user_id)
    statement = select(UserNotification).where(UserNotification.user_id == user_id)
    if unread_only:
        statement = statement.where(UserNotification.read_at.is_(None))
    total = int(
        db.session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    )
    rows = db.session.scalars(
        statement.order_by(
            UserNotification.created_at.desc(), UserNotification.id.desc()
        )
        .offset(page * size)
        .limit(size)
    ).all()
    return PageResult([_serialize(row) for row in rows], total, page, size)


def unread_count(user_id: int) -> int:
    sync_for_user(user_id)
    return int(
        db.session.scalar(
            select(func.count(UserNotification.id)).where(
                UserNotification.user_id == user_id,
                UserNotification.read_at.is_(None),
            )
        )
        or 0
    )


def mark_read(notification_id: int, user_id: int) -> dict[str, Any]:
    row = db.session.get(UserNotification, notification_id)
    if row is None or row.user_id != user_id:
        raise BusinessException("通知不存在", result_code=ResultCode.NOT_FOUND)
    if row.read_at is None:
        row.read_at = utc_now()
        db.session.commit()
    return _serialize(row)


def mark_all_read(user_id: int) -> int:
    rows = db.session.scalars(
        select(UserNotification).where(
            UserNotification.user_id == user_id,
            UserNotification.read_at.is_(None),
        )
    ).all()
    now = utc_now()
    for row in rows:
        row.read_at = now
    db.session.commit()
    return len(rows)


__all__ = ["mark_all_read", "mark_read", "page", "sync_for_user", "unread_count"]
