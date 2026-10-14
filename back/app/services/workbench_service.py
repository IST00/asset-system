"""Server-side employee task-center queries and request timelines."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import and_, exists, false, func, or_, select

from app.common import BusinessException, ResultCode
from app.enums import (
    ApprovalStatus,
    AssetStatus,
    ExecutionStatus,
    FulfillmentStatus,
    OperationType,
    RuntimeTaskStatus,
    UsageMode,
    UsageType,
)
from app.extensions import db
from app.models.asset import Asset
from app.models.attachment import AssetAttachment
from app.models.asset_borrow_extension import AssetBorrowExtensionRequest
from app.models.asset_usage_return import AssetReturnRequest, AssetUsageRequest
from app.models.operation import OperationRequestAsset
from app.models.workflow import (
    ApprovalRecord,
    ApprovalStep,
    ApprovalTask,
    OperationRequest,
)
from app.repositories.rbac_repository import rbac_repository
from app.services import permission_service

_DUE_SOON_DAYS = 7
_LOCAL_ZONE = ZoneInfo("Asia/Shanghai")
_TERMINAL_EXECUTION = {
    ExecutionStatus.SUCCESS.value,
    ExecutionStatus.FAILED.value,
    ExecutionStatus.TERMINATED.value,
}
_TERMINAL_APPROVAL = {
    ApprovalStatus.REJECTED.value,
    ApprovalStatus.WITHDRAWN.value,
}


def _require_workbench(actor_id: int) -> None:
    if not any(
        permission_service.has_permission(actor_id, code)
        for code in ("asset:usage:self", "asset:return:self", "asset:usage:manage")
    ):
        raise BusinessException("无操作权限", result_code=ResultCode.FORBIDDEN)


def _normalize(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    normalized = _normalize(value)
    return normalized.isoformat() if normalized is not None else None


def _user(user_id: int | None) -> dict[str, Any] | None:
    if user_id is None:
        return None
    row = rbac_repository.find_user(user_id)
    return {
        "id": user_id,
        "name": (row.nickname or row.username) if row is not None else None,
    }


def _page_payload(
    items: list[dict[str, Any]],
    *,
    total: int,
    page: int,
    size: int,
    pending_count: int,
) -> dict[str, Any]:
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pending_count": pending_count,
    }


def _request_status(
    operation: OperationRequest,
    usage: AssetUsageRequest | None,
    return_detail: AssetReturnRequest | None = None,
) -> str:
    if operation.approval_status == ApprovalStatus.REJECTED.value:
        return "REJECTED"
    if operation.approval_status == ApprovalStatus.WITHDRAWN.value:
        return "WITHDRAWN"
    if operation.execution_status == ExecutionStatus.FAILED.value:
        return "FAILED"
    if operation.execution_status == ExecutionStatus.TERMINATED.value:
        return "TERMINATED"
    if usage is not None:
        if usage.fulfillment_status == FulfillmentStatus.PENDING_ISSUE.value:
            return "PENDING_ISSUE"
        if usage.fulfillment_status == FulfillmentStatus.PENDING_SIGN.value:
            return "PENDING_SIGN"
        if usage.fulfillment_status == FulfillmentStatus.SIGN_REFUSED.value:
            return "SIGN_REFUSED"
    if operation.approval_status == ApprovalStatus.PENDING.value:
        if (
            usage is not None
            and usage.fulfillment_status == FulfillmentStatus.PENDING_ISSUE.value
        ):
            return "PENDING_ISSUE"
        return "PENDING_APPROVAL"
    if (
        operation.operation_type == OperationType.PERSONAL_RETURN.value
        and operation.approval_status == ApprovalStatus.APPROVED.value
        and operation.execution_status == ExecutionStatus.NOT_STARTED.value
    ):
        return "PENDING_INSPECTION"
    if operation.execution_status == ExecutionStatus.PROCESSING.value:
        return "PROCESSING"
    if operation.execution_status == ExecutionStatus.SUCCESS.value:
        return "COMPLETED"
    return operation.execution_status


def _request_pending(
    operation: OperationRequest,
    usage: AssetUsageRequest | None,
    return_detail: AssetReturnRequest | None = None,
) -> bool:
    return _request_status(operation, usage, return_detail) in {
        "PENDING_APPROVAL",
        "PENDING_ISSUE",
        "PENDING_SIGN",
        "SIGN_REFUSED",
        "PENDING_HANDOVER",
        "PENDING_INSPECTION",
        "PROCESSING",
    }


def _operation_assets(operation_id: int) -> list[OperationRequestAsset]:
    return list(
        db.session.scalars(
            select(OperationRequestAsset)
            .where(OperationRequestAsset.operation_request_id == operation_id)
            .order_by(OperationRequestAsset.id.asc())
        ).all()
    )


def _usage_detail(operation_id: int) -> AssetUsageRequest | None:
    return db.session.scalar(
        select(AssetUsageRequest).where(
            AssetUsageRequest.operation_request_id == operation_id
        )
    )


def _return_detail(operation_id: int) -> AssetReturnRequest | None:
    return db.session.scalar(
        select(AssetReturnRequest).where(
            AssetReturnRequest.operation_request_id == operation_id
        )
    )


def _request_item(operation: OperationRequest, actor_id: int) -> dict[str, Any]:
    usage = _usage_detail(operation.id)
    return_detail = _return_detail(operation.id)
    snapshots = _operation_assets(operation.id)
    hide_codes = bool(
        usage is not None
        and usage.requested_category_id is not None
        and operation.applicant_id == actor_id
        and not permission_service.has_permission(actor_id, "asset:usage:manage")
        and usage.issued_at is None
    )
    return {
        "id": operation.id,
        "request_no": operation.request_no,
        "operation_type": operation.operation_type,
        "applicant_id": operation.applicant_id,
        "applicant": _user(operation.applicant_id),
        "target_user_id": usage.target_user_id if usage is not None else None,
        "target_user": _user(usage.target_user_id) if usage is not None else None,
        "approval_status": operation.approval_status,
        "execution_status": operation.execution_status,
        "display_status": _request_status(operation, usage, return_detail),
        "pending": _request_pending(operation, usage, return_detail),
        "created_at": _iso(operation.created_at),
        "submitted_at": _iso(operation.submitted_at),
        "approved_at": _iso(operation.approved_at),
        "executed_at": _iso(operation.executed_at),
        "usage_mode": usage.usage_mode if usage is not None else None,
        "expected_return_at": _iso(usage.expected_return_at)
        if usage is not None
        else None,
        "fulfillment_status": usage.fulfillment_status if usage is not None else None,
        "requested_category": (
            usage.requested_category_snapshot if usage is not None else None
        ),
        "requested_quantity": usage.requested_quantity if usage is not None else None,
        "reason": usage.reason if usage is not None else None,
        "assets": [
            {
                "asset_id": snapshot.asset_id,
                "asset_code": None if hide_codes else snapshot.asset_code_snapshot,
                "asset_name": snapshot.asset_name_snapshot,
            }
            for snapshot in snapshots
        ],
    }


def _usage_status_condition(status: str) -> Any:
    return exists(
        select(1)
        .where(
            AssetUsageRequest.operation_request_id == OperationRequest.id,
            AssetUsageRequest.fulfillment_status == status,
        )
        .correlate_except(AssetUsageRequest)
    )


def _operation_status_condition(status: str) -> Any:
    normalized = status.upper()
    pending_issue = _usage_status_condition(FulfillmentStatus.PENDING_ISSUE.value)
    pending_sign = _usage_status_condition(FulfillmentStatus.PENDING_SIGN.value)
    sign_refused = _usage_status_condition(FulfillmentStatus.SIGN_REFUSED.value)
    stable_approval = OperationRequest.approval_status == ApprovalStatus.APPROVED.value
    stable_execution = OperationRequest.execution_status.not_in(
        {ExecutionStatus.FAILED.value, ExecutionStatus.TERMINATED.value}
    )
    mapping = {
        "PENDING_APPROVAL": OperationRequest.approval_status
        == ApprovalStatus.PENDING.value,
        "REJECTED": OperationRequest.approval_status == ApprovalStatus.REJECTED.value,
        "WITHDRAWN": OperationRequest.approval_status == ApprovalStatus.WITHDRAWN.value,
        "FAILED": and_(
            OperationRequest.approval_status == ApprovalStatus.APPROVED.value,
            OperationRequest.execution_status == ExecutionStatus.FAILED.value,
        ),
        "TERMINATED": and_(
            OperationRequest.approval_status == ApprovalStatus.APPROVED.value,
            OperationRequest.execution_status == ExecutionStatus.TERMINATED.value,
        ),
        "PENDING_ISSUE": and_(
            OperationRequest.approval_status.in_(
                {ApprovalStatus.PENDING.value, ApprovalStatus.APPROVED.value}
            ),
            stable_execution,
            pending_issue,
        ),
        "PENDING_SIGN": and_(stable_approval, stable_execution, pending_sign),
        "SIGN_REFUSED": and_(stable_approval, stable_execution, sign_refused),
        # Keep PENDING_HANDOVER as an alias for older clients. New personal-return
        # requests no longer require an employee handover confirmation.
        "PENDING_HANDOVER": false(),
        "PENDING_INSPECTION": and_(
            stable_approval,
            OperationRequest.operation_type == OperationType.PERSONAL_RETURN.value,
            OperationRequest.execution_status == ExecutionStatus.NOT_STARTED.value,
        ),
        "PROCESSING": and_(
            stable_approval,
            OperationRequest.execution_status == ExecutionStatus.PROCESSING.value,
            ~pending_issue,
            ~pending_sign,
            ~sign_refused,
        ),
        "COMPLETED": and_(
            stable_approval,
            OperationRequest.execution_status == ExecutionStatus.SUCCESS.value,
        ),
    }
    return mapping.get(normalized, false())


def _operation_pending_condition() -> Any:
    return or_(
        *(
            _operation_status_condition(status)
            for status in (
                "PENDING_APPROVAL",
                "PENDING_ISSUE",
                "PENDING_SIGN",
                "SIGN_REFUSED",
                "PENDING_HANDOVER",
                "PENDING_INSPECTION",
                "PROCESSING",
            )
        )
    )


def _operation_query(view: str, actor_id: int) -> Any:
    statement = select(OperationRequest.id)
    if view == "my-requests":
        return statement.where(OperationRequest.applicant_id == actor_id)
    if view in {"assigned-to-me", "pending-sign"}:
        statement = statement.join(
            AssetUsageRequest,
            AssetUsageRequest.operation_request_id == OperationRequest.id,
        ).where(
            OperationRequest.operation_type == OperationType.PERSONAL_USE.value,
            AssetUsageRequest.target_user_id == actor_id,
        )
        if view == "pending-sign":
            statement = statement.where(
                AssetUsageRequest.fulfillment_status
                == FulfillmentStatus.PENDING_SIGN.value
            )
        return statement
    if view == "received-handovers":
        target_match = (
            OperationRequestAsset.target_data["holder_user_id"].as_integer() == actor_id
        )
        return statement.join(
            OperationRequestAsset,
            OperationRequestAsset.operation_request_id == OperationRequest.id,
        ).where(
            OperationRequest.operation_type == OperationType.TRANSFER.value,
            target_match,
        )
    raise BusinessException("未知工作台视图", result_code=ResultCode.BAD_REQUEST)


def _apply_operation_filters(statement: Any, query: dict[str, Any]) -> Any:
    keyword = query.get("keyword")
    if keyword:
        pattern = f"%{keyword}%"
        asset_match = exists(
            select(1).where(
                OperationRequestAsset.operation_request_id == OperationRequest.id,
                or_(
                    OperationRequestAsset.asset_code_snapshot.ilike(pattern),
                    OperationRequestAsset.asset_name_snapshot.ilike(pattern),
                ),
            )
        )
        statement = statement.where(
            or_(
                OperationRequest.request_no.ilike(pattern),
                OperationRequest.operation_type.ilike(pattern),
                asset_match,
            )
        )
    start = query.get("start_date")
    end = query.get("end_date")
    if start is not None:
        statement = statement.where(OperationRequest.created_at >= start)
    if end is not None:
        statement = statement.where(OperationRequest.created_at <= end)
    status = query.get("status")
    if status:
        statement = statement.where(_operation_status_condition(status))
    return statement.distinct()


def _count_ids(statement: Any) -> int:
    return int(
        db.session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    )


def _operation_page(view: str, actor_id: int, query: dict[str, Any]) -> dict[str, Any]:
    _require_workbench(actor_id)
    filtered = _apply_operation_filters(_operation_query(view, actor_id), query)
    pending_condition = _operation_pending_condition()
    pending_count = _count_ids(filtered.where(pending_condition))
    if query.get("pending_only"):
        filtered = filtered.where(pending_condition)
    total = _count_ids(filtered)
    page = query["page"]
    size = query["size"]
    paged_ids = (
        filtered.order_by(
            OperationRequest.created_at.desc(), OperationRequest.id.desc()
        )
        .offset(page * size)
        .limit(size)
    )
    rows = list(
        db.session.scalars(
            select(OperationRequest)
            .where(OperationRequest.id.in_(paged_ids))
            .order_by(OperationRequest.created_at.desc(), OperationRequest.id.desc())
        ).all()
    )
    return _page_payload(
        [_request_item(row, actor_id) for row in rows],
        total=total,
        page=page,
        size=size,
        pending_count=pending_count,
    )


def my_requests(actor_id: int, query: dict[str, Any]) -> dict[str, Any]:
    return _operation_page("my-requests", actor_id, query)


def assigned_to_me(actor_id: int, query: dict[str, Any]) -> dict[str, Any]:
    return _operation_page("assigned-to-me", actor_id, query)


def pending_sign(actor_id: int, query: dict[str, Any]) -> dict[str, Any]:
    return _operation_page("pending-sign", actor_id, query)


def received_handovers(actor_id: int, query: dict[str, Any]) -> dict[str, Any]:
    return _operation_page("received-handovers", actor_id, query)


def _latest_usage_operation_id(actor_id: int) -> Any:
    return (
        select(func.max(OperationRequest.id))
        .select_from(OperationRequestAsset)
        .join(
            AssetUsageRequest,
            AssetUsageRequest.operation_request_id
            == OperationRequestAsset.operation_request_id,
        )
        .join(
            OperationRequest,
            OperationRequest.id == OperationRequestAsset.operation_request_id,
        )
        .where(
            OperationRequestAsset.asset_id == Asset.id,
            OperationRequest.operation_type == OperationType.PERSONAL_USE.value,
            OperationRequest.execution_status == ExecutionStatus.SUCCESS.value,
            AssetUsageRequest.target_user_id == actor_id,
        )
        .correlate(Asset)
        .scalar_subquery()
    )


def _latest_usage_condition(actor_id: int, *conditions: Any) -> Any:
    return exists(
        select(1).where(
            AssetUsageRequest.operation_request_id
            == _latest_usage_operation_id(actor_id),
            *conditions,
        )
    )


def _active_return_condition(actor_id: int) -> Any:
    conditions: list[Any] = [
        OperationRequestAsset.asset_id == Asset.id,
        OperationRequest.operation_type == OperationType.PERSONAL_RETURN.value,
        OperationRequest.applicant_id == actor_id,
        OperationRequest.approval_status.not_in(_TERMINAL_APPROVAL),
        OperationRequest.execution_status.not_in(_TERMINAL_EXECUTION),
    ]
    return exists(
        select(1)
        .select_from(OperationRequestAsset)
        .join(
            OperationRequest,
            OperationRequest.id == OperationRequestAsset.operation_request_id,
        )
        .join(
            AssetReturnRequest,
            AssetReturnRequest.operation_request_id == OperationRequest.id,
        )
        .where(*conditions)
        .correlate(Asset)
    )


def _borrow_condition(actor_id: int) -> Any:
    return _latest_usage_condition(
        actor_id, AssetUsageRequest.usage_mode == UsageMode.BORROW.value
    )


def _asset_status_conditions(actor_id: int, now: datetime) -> dict[str, Any]:
    active_return = _active_return_condition(actor_id)
    pending_inspection = _active_return_condition(actor_id)
    borrow = _borrow_condition(actor_id)
    manager_requested = _latest_usage_condition(
        actor_id,
        AssetUsageRequest.usage_mode == UsageMode.BORROW.value,
        AssetUsageRequest.return_requested_at.is_not(None),
    )
    return_not_requested = _latest_usage_condition(
        actor_id,
        AssetUsageRequest.usage_mode == UsageMode.BORROW.value,
        AssetUsageRequest.return_requested_at.is_(None),
    )
    local_now = now.astimezone(_LOCAL_ZONE)
    local_day_start = datetime.combine(
        local_now.date(), datetime.min.time(), tzinfo=_LOCAL_ZONE
    ).astimezone(timezone.utc)
    local_next_day = local_day_start + timedelta(days=1)

    def due_exists(*conditions: Any) -> Any:
        return _latest_usage_condition(
            actor_id,
            AssetUsageRequest.usage_mode == UsageMode.BORROW.value,
            AssetUsageRequest.return_requested_at.is_(None),
            AssetUsageRequest.expected_return_at.is_not(None),
            *conditions,
        )

    due_soon_cutoff = now + timedelta(days=_DUE_SOON_DAYS)
    return {
        "NOT_BORROWED": and_(~active_return, ~borrow),
        "NORMAL": and_(
            ~active_return,
            return_not_requested,
            or_(
                _latest_usage_condition(
                    actor_id,
                    AssetUsageRequest.usage_mode == UsageMode.BORROW.value,
                    AssetUsageRequest.return_requested_at.is_(None),
                    AssetUsageRequest.expected_return_at.is_(None),
                ),
                due_exists(AssetUsageRequest.expected_return_at > due_soon_cutoff),
            ),
        ),
        "DUE_SOON": and_(
            ~active_return,
            due_exists(
                AssetUsageRequest.expected_return_at >= local_next_day,
                AssetUsageRequest.expected_return_at <= due_soon_cutoff,
            ),
        ),
        "DUE_TODAY": and_(
            ~active_return,
            due_exists(
                AssetUsageRequest.expected_return_at >= local_day_start,
                AssetUsageRequest.expected_return_at < local_next_day,
            ),
        ),
        "OVERDUE": and_(
            ~active_return,
            due_exists(AssetUsageRequest.expected_return_at < local_day_start),
        ),
        "MANAGER_REQUESTED": and_(~active_return, manager_requested),
        "RETURN_PROCESSING": and_(active_return, ~pending_inspection),
        "PENDING_INSPECTION": pending_inspection,
    }


def _latest_usage_by_asset(
    actor_id: int, asset_ids: list[int]
) -> dict[int, AssetUsageRequest]:
    if not asset_ids:
        return {}
    rows = db.session.execute(
        select(OperationRequestAsset.asset_id, AssetUsageRequest, OperationRequest.id)
        .join(
            AssetUsageRequest,
            AssetUsageRequest.operation_request_id
            == OperationRequestAsset.operation_request_id,
        )
        .join(
            OperationRequest,
            OperationRequest.id == OperationRequestAsset.operation_request_id,
        )
        .where(
            OperationRequestAsset.asset_id.in_(asset_ids),
            OperationRequest.operation_type == OperationType.PERSONAL_USE.value,
            OperationRequest.execution_status == ExecutionStatus.SUCCESS.value,
            AssetUsageRequest.target_user_id == actor_id,
        )
        .order_by(OperationRequest.id.desc())
    ).all()
    result: dict[int, AssetUsageRequest] = {}
    for asset_id, usage, _operation_id in rows:
        result.setdefault(asset_id, usage)
    return result


def _active_returns_by_asset(
    actor_id: int, asset_ids: list[int]
) -> dict[int, tuple[OperationRequest, AssetReturnRequest]]:
    if not asset_ids:
        return {}
    rows = db.session.execute(
        select(OperationRequestAsset.asset_id, OperationRequest, AssetReturnRequest)
        .join(
            OperationRequest,
            OperationRequest.id == OperationRequestAsset.operation_request_id,
        )
        .join(
            AssetReturnRequest,
            AssetReturnRequest.operation_request_id == OperationRequest.id,
        )
        .where(
            OperationRequestAsset.asset_id.in_(asset_ids),
            OperationRequest.operation_type == OperationType.PERSONAL_RETURN.value,
            OperationRequest.applicant_id == actor_id,
            OperationRequest.approval_status.not_in(_TERMINAL_APPROVAL),
            OperationRequest.execution_status.not_in(_TERMINAL_EXECUTION),
        )
        .order_by(OperationRequest.id.desc())
    ).all()
    result: dict[int, tuple[OperationRequest, AssetReturnRequest]] = {}
    for asset_id, operation, return_detail in rows:
        result.setdefault(asset_id, (operation, return_detail))
    return result


def _due_state(usage: AssetUsageRequest | None, now: datetime) -> str:
    if usage is None or usage.usage_mode != UsageMode.BORROW.value:
        return "NOT_BORROWED"
    if usage.return_requested_at is not None:
        return "MANAGER_REQUESTED"
    due = _normalize(usage.expected_return_at)
    if due is None:
        return "NORMAL"
    local_due = due.astimezone(_LOCAL_ZONE)
    local_now = now.astimezone(_LOCAL_ZONE)
    if local_due.date() < local_now.date():
        return "OVERDUE"
    if local_due.date() == local_now.date():
        return "DUE_TODAY"
    if due <= now + timedelta(days=_DUE_SOON_DAYS):
        return "DUE_SOON"
    return "NORMAL"


def _asset_state(
    usage: AssetUsageRequest | None,
    active_return: tuple[OperationRequest, AssetReturnRequest] | None,
    now: datetime,
) -> str:
    if active_return is not None:
        operation, return_detail = active_return
        if (
            operation.approval_status == ApprovalStatus.APPROVED.value
            and operation.execution_status == ExecutionStatus.NOT_STARTED.value
            and return_detail.handed_over_at is not None
        ):
            return "PENDING_INSPECTION"
        return "RETURN_PROCESSING"
    return _due_state(usage, now)


def _asset_item(
    asset: Asset,
    usage: AssetUsageRequest | None,
    active_return: tuple[OperationRequest, AssetReturnRequest] | None,
    now: datetime,
) -> dict[str, Any]:
    state = _asset_state(usage, active_return, now)
    return_operation = active_return[0] if active_return is not None else None
    return_detail = active_return[1] if active_return is not None else None
    usage_mode = usage.usage_mode if usage is not None else UsageMode.USE.value
    return {
        "id": asset.id,
        "asset_code": asset.asset_code,
        "asset_name": asset.asset_name,
        "status": asset.status,
        "display_status": "BORROWED"
        if usage_mode == UsageMode.BORROW.value
        else "IN_USE",
        "location_id": asset.location_id,
        "usage_mode": usage_mode,
        "usage_request_id": usage.operation_request_id if usage is not None else None,
        "expected_return_at": _iso(usage.expected_return_at)
        if usage is not None
        else None,
        "return_state": state,
        "return_request_id": (
            return_operation.id if return_operation is not None else None
        ),
        "return_request_no": (
            return_operation.request_no if return_operation is not None else None
        ),
        "return_handed_over_at": (
            _iso(return_detail.handed_over_at) if return_detail is not None else None
        ),
        "return_requested_at": _iso(usage.return_requested_at)
        if usage is not None
        else None,
        "return_request_reason": usage.return_request_reason
        if usage is not None
        else None,
    }


def _asset_query(actor_id: int, query: dict[str, Any], view: str, now: datetime) -> Any:
    statement = select(Asset.id).where(
        Asset.status == AssetStatus.IN_USE.value,
        Asset.usage_type == UsageType.PERSONAL.value,
        Asset.holder_user_id == actor_id,
        Asset.parent_asset_id.is_(None),
    )
    borrow = _borrow_condition(actor_id)
    if view == "my-assets":
        statement = statement.where(~borrow)
    elif view in {"my-borrowed", "pending-return"}:
        statement = statement.where(borrow)
    else:
        raise BusinessException(
            "未知资产工作台视图", result_code=ResultCode.BAD_REQUEST
        )
    states = _asset_status_conditions(actor_id, now)
    if view == "pending-return":
        statement = statement.where(
            or_(
                states["DUE_SOON"],
                states["DUE_TODAY"],
                states["OVERDUE"],
                states["MANAGER_REQUESTED"],
            )
        )
    keyword = query.get("keyword")
    if keyword:
        pattern = f"%{keyword}%"
        return_match = exists(
            select(1)
            .select_from(OperationRequestAsset)
            .join(
                OperationRequest,
                OperationRequest.id == OperationRequestAsset.operation_request_id,
            )
            .where(
                OperationRequestAsset.asset_id == Asset.id,
                OperationRequest.operation_type == OperationType.PERSONAL_RETURN.value,
                OperationRequest.request_no.ilike(pattern),
            )
            .correlate(Asset)
        )
        statement = statement.where(
            or_(
                Asset.asset_code.ilike(pattern),
                Asset.asset_name.ilike(pattern),
                return_match,
            )
        )
    status = query.get("status")
    if status:
        statement = statement.where(states.get(status.upper(), false()))
    start = _normalize(query.get("start_date"))
    end = _normalize(query.get("end_date"))
    if start is not None or end is not None:
        date_conditions: list[Any] = [AssetUsageRequest.expected_return_at.is_not(None)]
        if start is not None:
            date_conditions.append(AssetUsageRequest.expected_return_at >= start)
        if end is not None:
            date_conditions.append(AssetUsageRequest.expected_return_at <= end)
        statement = statement.where(_latest_usage_condition(actor_id, *date_conditions))
    return statement.distinct()


def _asset_page(actor_id: int, query: dict[str, Any], view: str) -> dict[str, Any]:
    _require_workbench(actor_id)
    now = datetime.now(timezone.utc)
    filtered = _asset_query(actor_id, query, view, now)
    states = _asset_status_conditions(actor_id, now)
    pending_states = (
        states["DUE_SOON"],
        states["DUE_TODAY"],
        states["OVERDUE"],
        states["MANAGER_REQUESTED"],
        states["RETURN_PROCESSING"],
        states["PENDING_INSPECTION"],
    )
    pending_statement = filtered.where(or_(*pending_states))
    pending_count = _count_ids(pending_statement)
    if query.get("pending_only"):
        filtered = pending_statement
    total = _count_ids(filtered)
    page = query["page"]
    size = query["size"]
    paged_ids = (
        filtered.order_by(Asset.asset_code.asc(), Asset.id.asc())
        .offset(page * size)
        .limit(size)
    )
    assets = list(
        db.session.scalars(
            select(Asset)
            .where(Asset.id.in_(paged_ids))
            .order_by(Asset.asset_code.asc(), Asset.id.asc())
        ).all()
    )
    asset_ids = [asset.id for asset in assets]
    usages = _latest_usage_by_asset(actor_id, asset_ids)
    returns = _active_returns_by_asset(actor_id, asset_ids)
    items = [
        _asset_item(asset, usages.get(asset.id), returns.get(asset.id), now)
        for asset in assets
    ]
    return _page_payload(
        items,
        total=total,
        page=page,
        size=size,
        pending_count=pending_count,
    )


def my_assets(actor_id: int, query: dict[str, Any]) -> dict[str, Any]:
    return _asset_page(actor_id, query, "my-assets")


def my_borrowed(actor_id: int, query: dict[str, Any]) -> dict[str, Any]:
    return _asset_page(actor_id, query, "my-borrowed")


def pending_return(actor_id: int, query: dict[str, Any]) -> dict[str, Any]:
    return _asset_page(actor_id, query, "pending-return")


def _scalar_count(statement: Any) -> int:
    return int(db.session.scalar(statement) or 0)


def summary(actor_id: int) -> dict[str, int]:
    _require_workbench(actor_id)
    now = datetime.now(timezone.utc)
    states = _asset_status_conditions(actor_id, now)
    asset_base = select(func.count(Asset.id)).where(
        Asset.status == AssetStatus.IN_USE.value,
        Asset.usage_type == UsageType.PERSONAL.value,
        Asset.holder_user_id == actor_id,
        Asset.parent_asset_id.is_(None),
    )
    borrowed = _borrow_condition(actor_id)
    can_manage = permission_service.has_permission(actor_id, "asset:usage:manage")
    pending_issue = 0
    pending_inspection = _scalar_count(asset_base.where(states["PENDING_INSPECTION"]))
    if can_manage:
        pending_issue = _scalar_count(
            select(func.count(AssetUsageRequest.id))
            .join(
                OperationRequest,
                OperationRequest.id == AssetUsageRequest.operation_request_id,
            )
            .where(
                AssetUsageRequest.fulfillment_status
                == FulfillmentStatus.PENDING_ISSUE.value,
                OperationRequest.approval_status.in_(
                    {ApprovalStatus.PENDING.value, ApprovalStatus.APPROVED.value}
                ),
                OperationRequest.execution_status == ExecutionStatus.NOT_STARTED.value,
            )
        )
        pending_inspection = _scalar_count(
            select(func.count(AssetReturnRequest.id))
            .join(
                OperationRequest,
                OperationRequest.id == AssetReturnRequest.operation_request_id,
            )
            .where(
                AssetReturnRequest.confirmed_at.is_(None),
                OperationRequest.approval_status == ApprovalStatus.APPROVED.value,
                OperationRequest.execution_status == ExecutionStatus.NOT_STARTED.value,
            )
        )
    pending_sign_count = _scalar_count(
        select(func.count(AssetUsageRequest.id))
        .join(
            OperationRequest,
            OperationRequest.id == AssetUsageRequest.operation_request_id,
        )
        .where(
            AssetUsageRequest.target_user_id == actor_id,
            AssetUsageRequest.fulfillment_status
            == FulfillmentStatus.PENDING_SIGN.value,
            OperationRequest.approval_status == ApprovalStatus.APPROVED.value,
            OperationRequest.execution_status == ExecutionStatus.NOT_STARTED.value,
        )
    )
    pending_approval = _scalar_count(
        select(func.count(ApprovalTask.id)).where(
            ApprovalTask.approver_id == actor_id,
            ApprovalTask.status == RuntimeTaskStatus.PENDING.value,
        )
    )
    pending_handover = 0
    return {
        "pending_approval": pending_approval,
        "pending_issue": pending_issue,
        "pending_sign": pending_sign_count,
        "pending_handover": pending_handover,
        "due_soon": _scalar_count(asset_base.where(states["DUE_SOON"])),
        "due_today": _scalar_count(asset_base.where(states["DUE_TODAY"])),
        "overdue": _scalar_count(asset_base.where(states["OVERDUE"])),
        "manager_requested_return": _scalar_count(
            asset_base.where(states["MANAGER_REQUESTED"])
        ),
        "return_processing": _scalar_count(
            asset_base.where(states["RETURN_PROCESSING"])
        ),
        "pending_return_inspection": pending_inspection,
        "my_in_use": _scalar_count(asset_base.where(~borrowed)),
        "my_borrowed": _scalar_count(asset_base.where(borrowed)),
    }


def _approval_events(operation_id: int) -> list[dict[str, Any]]:
    rows = db.session.scalars(
        select(ApprovalRecord)
        .where(ApprovalRecord.operation_request_id == operation_id)
        .order_by(ApprovalRecord.created_at.asc(), ApprovalRecord.id.asc())
    ).all()
    return [
        {
            "key": f"APPROVAL-{row.id}",
            "title": "审批通过" if row.action == "APPROVE" else "审批拒绝",
            "actor": _user(row.actor_id),
            "occurred_at": _iso(row.created_at),
            "remark": row.opinion,
            "status": "COMPLETED" if row.action == "APPROVE" else "REJECTED",
            "approval_result": row.action,
            "rejection_reason": row.opinion if row.action == "REJECT" else None,
            "asset_codes": [],
        }
        for row in rows
    ]


def _pending_approvers(operation_id: int) -> list[dict[str, Any]]:
    ids = db.session.scalars(
        select(ApprovalTask.approver_id)
        .join(ApprovalStep, ApprovalStep.id == ApprovalTask.approval_step_id)
        .where(
            ApprovalStep.operation_request_id == operation_id,
            ApprovalTask.status == RuntimeTaskStatus.PENDING.value,
        )
        .order_by(ApprovalStep.level_no.asc(), ApprovalTask.id.asc())
    ).all()
    return [entry for entry in (_user(user_id) for user_id in ids) if entry is not None]


def _timeline_attachments(
    operation_id: int, asset_ids: list[int]
) -> list[dict[str, Any]]:
    if not asset_ids:
        return []
    rows = db.session.scalars(
        select(AssetAttachment).where(
            AssetAttachment.business_id == operation_id,
            AssetAttachment.business_type.in_(
                ("USAGE_SIGN", "RETURN_HANDOVER", "RETURN_INSPECTION")
            ),
            AssetAttachment.asset_id.in_(asset_ids),
            AssetAttachment.status == "ACTIVE",
        )
    ).all()
    return [
        {
            "id": row.id,
            "asset_id": row.asset_id,
            "business_type": row.business_type,
            "document_type": row.document_type,
            "original_name": row.original_name,
            "size_bytes": row.size_bytes,
            "uploaded_by": _user(row.uploaded_by),
            "created_at": _iso(row.created_at),
        }
        for row in rows
    ]


def request_detail(operation_id: int, actor_id: int) -> dict[str, Any]:
    _require_workbench(actor_id)
    from app.services.operation_service import get_request

    base = get_request(operation_id, actor_id)
    operation = db.session.get(OperationRequest, operation_id)
    if operation is None:
        raise BusinessException("申请不存在", result_code=ResultCode.NOT_FOUND)
    usage = _usage_detail(operation_id)
    return_detail = _return_detail(operation_id)
    extension_rows = list(
        db.session.scalars(
            select(AssetBorrowExtensionRequest)
            .where(AssetBorrowExtensionRequest.operation_request_id == operation_id)
            .order_by(
                AssetBorrowExtensionRequest.created_at.asc(),
                AssetBorrowExtensionRequest.id.asc(),
            )
        ).all()
    )
    asset_codes = [
        item.get("asset_code")
        for item in base.get("assets", [])
        if item.get("asset_code")
    ]
    timeline: list[dict[str, Any]] = [
        {
            "key": "SUBMITTED",
            "title": "提交申请",
            "actor": _user(operation.applicant_id),
            "occurred_at": _iso(operation.submitted_at or operation.created_at),
            "remark": usage.reason if usage is not None else None,
            "status": "COMPLETED",
            "approval_result": None,
            "rejection_reason": None,
            "asset_codes": asset_codes,
        }
    ]
    timeline.extend(_approval_events(operation_id))
    for extension in extension_rows:
        extension_title = {
            "PENDING": "提交借用延期申请",
            "APPROVED": "借用延期审批通过",
            "REJECTED": "借用延期审批拒绝",
        }.get(extension.status, "借用延期申请")
        timeline.append(
            {
                "key": f"BORROW_EXTENSION-{extension.id}",
                "title": extension_title,
                "actor": _user(extension.reviewed_by or extension.applicant_id),
                "occurred_at": _iso(extension.reviewed_at or extension.created_at),
                "remark": extension.review_opinion or extension.reason,
                "status": "CURRENT"
                if extension.status == "PENDING"
                else ("REJECTED" if extension.status == "REJECTED" else "COMPLETED"),
                "approval_result": extension.status,
                "rejection_reason": extension.review_opinion
                if extension.status == "REJECTED"
                else None,
                "asset_codes": asset_codes,
            }
        )
    if usage is not None and usage.issued_at is not None:
        timeline.append(
            {
                "key": "ISSUED",
                "title": "管理员发放资产",
                "actor": _user(usage.issued_by),
                "occurred_at": _iso(usage.issued_at),
                "remark": usage.issue_remark,
                "status": "COMPLETED",
                "approval_result": None,
                "rejection_reason": None,
                "asset_codes": asset_codes,
            }
        )
        timeline.append(
            {
                "key": "PENDING_SIGN",
                "title": "资产进入领用待确认",
                "actor": _user(usage.issued_by),
                "occurred_at": _iso(usage.issued_at),
                "remark": None,
                "status": "COMPLETED",
                "approval_result": None,
                "rejection_reason": None,
                "asset_codes": asset_codes,
            }
        )
    if usage is not None and usage.signed_at is not None:
        timeline.append(
            {
                "key": "SIGNED",
                "title": "员工签收，资产变为在用",
                "actor": _user(usage.signed_by),
                "occurred_at": _iso(usage.signed_at),
                "remark": usage.sign_remark,
                "status": "COMPLETED",
                "approval_result": None,
                "rejection_reason": None,
                "asset_codes": asset_codes,
            }
        )
    if (
        return_detail is not None
        and operation.approval_status == ApprovalStatus.APPROVED.value
        and return_detail.confirmed_at is None
        and operation.execution_status == ExecutionStatus.NOT_STARTED.value
    ):
        timeline.append(
            {
                "key": "RETURN_INSPECTION_WAITING",
                "title": "等待管理员验收退库",
                "actor": None,
                "occurred_at": None,
                "remark": "管理员验收资产并选择退库后公司、使用公司、区域和存放地点",
                "status": "CURRENT",
                "approval_result": None,
                "rejection_reason": None,
                "asset_codes": asset_codes,
            }
        )
    if return_detail is not None and return_detail.handed_over_at is not None:
        timeline.append(
            {
                "key": "RETURN_HANDOVER",
                "title": "员工交还资产（历史流程记录）",
                "actor": _user(return_detail.handed_over_by),
                "occurred_at": _iso(return_detail.handed_over_at),
                "remark": return_detail.handover_remark,
                "status": "COMPLETED",
                "approval_result": None,
                "rejection_reason": None,
                "asset_codes": asset_codes,
            }
        )
    if return_detail is not None and return_detail.confirmed_at is not None:
        timeline.append(
            {
                "key": "RETURN_CONFIRMED",
                "title": "管理员验收，退库完成",
                "actor": _user(return_detail.confirmed_by),
                "occurred_at": _iso(return_detail.confirmed_at),
                "remark": None,
                "status": "COMPLETED",
                "approval_result": None,
                "rejection_reason": None,
                "asset_codes": asset_codes,
            }
        )
    if operation.withdrawn_at is not None:
        timeline.append(
            {
                "key": "WITHDRAWN",
                "title": "申请已撤回",
                "actor": _user(operation.withdrawn_by),
                "occurred_at": _iso(operation.withdrawn_at),
                "remark": operation.withdrawal_reason,
                "status": "WITHDRAWN",
                "approval_result": None,
                "rejection_reason": None,
                "asset_codes": asset_codes,
            }
        )
    evidence = _timeline_attachments(
        operation_id,
        [item["asset_id"] for item in base.get("assets", []) if item.get("asset_id")],
    )
    for event in timeline:
        event["attachments"] = [
            item
            for item in evidence
            if item["business_type"]
            == {
                "SIGNED": "USAGE_SIGN",
                "RETURN_HANDOVER": "RETURN_HANDOVER",
                "RETURN_CONFIRMED": "RETURN_INSPECTION",
            }.get(event["key"], "")
        ]

    stage_order = {
        "SUBMITTED": 10,
        "ISSUED": 30,
        "PENDING_SIGN": 40,
        "SIGNED": 50,
        "RETURN_INSPECTION_WAITING": 60,
        "RETURN_HANDOVER": 65,
        "RETURN_CONFIRMED": 70,
        "WITHDRAWN": 90,
    }

    def timeline_order(item: dict[str, Any]) -> tuple[int, str]:
        key = item["key"]
        sequence = 20 if key.startswith("APPROVAL-") else stage_order.get(key, 80)
        return sequence, item["occurred_at"] or "9999"

    timeline.sort(key=timeline_order)

    current_handler: dict[str, Any] | None = None
    next_step = "流程已结束"
    actions: list[str] = []
    display_status = _request_status(operation, usage, return_detail)
    if display_status == "PENDING_APPROVAL":
        approvers = _pending_approvers(operation_id)
        current_handler = {"role": "APPROVER", "users": approvers}
        next_step = "等待审批人处理"
    elif display_status in {"PENDING_ISSUE", "SIGN_REFUSED"}:
        current_handler = {"role": "ADMIN", "users": []}
        next_step = "管理员选择具体资产并发放"
        if permission_service.has_permission(actor_id, "asset:usage:manage"):
            actions = ["ISSUE"]
    elif display_status == "PENDING_SIGN" and usage is not None:
        current_handler = {"role": "EMPLOYEE", "users": [_user(usage.target_user_id)]}
        next_step = "目标员工签收或拒收"
        if usage.target_user_id == actor_id:
            actions = ["SIGN", "REFUSE_SIGN"]
    elif (
        usage is not None
        and usage.usage_mode == UsageMode.BORROW.value
        and any(extension.status == "PENDING" for extension in extension_rows)
    ):
        current_handler = {"role": "ADMIN", "users": []}
        next_step = "等待管理员审批借用延期"
    elif display_status == "PENDING_INSPECTION":
        current_handler = {"role": "ADMIN", "users": []}
        next_step = "管理员验收资产并确认退库"
        if permission_service.has_permission(actor_id, "asset:usage:manage"):
            actions = ["CONFIRM_RETURN"]
    result = dict(base)
    result.update(
        {
            "display_status": display_status,
            "current_handler": current_handler,
            "next_step": next_step,
            "available_actions": actions,
            "timeline": timeline,
        }
    )
    return result


__all__ = [
    "assigned_to_me",
    "my_assets",
    "my_borrowed",
    "my_requests",
    "pending_return",
    "pending_sign",
    "received_handovers",
    "request_detail",
    "summary",
]
