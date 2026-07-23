"""Stock-in request orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from flask import current_app
from sqlalchemy.exc import IntegrityError

from app.common import BusinessException, PageResult, ResultCode
from app.enums import (
    ApprovalChannel,
    ApprovalStatus,
    AssigneeType,
    DataScope,
    ExecutionStatus,
    FlowStatus,
    OperationType,
    SignMode,
)
from app.extensions import db
from app.models import (
    ApprovalFlowAssigneeRule,
    ApprovalFlowDefinition,
    ApprovalFlowLayer,
    ApprovalFlowVersion,
    OperationRequest,
    StockInItem,
    StockInRequest,
)
from app.models.mixins import utc_now
from app.repositories import approval_flow_repository, asset_repository, rbac_repository
from app.repositories.workflow_repository import (
    operation_request_repository,
    stock_in_item_repository,
    stock_in_request_repository,
)
from app.services import (
    approval_engine,
    asset_code_service,
    asset_data_service,
    master_data_service,
    operation_executor,
    organization_service,
    permission_service,
)


def _request_no() -> str:
    day = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
    return f"STI{day}{uuid4().hex[:10].upper()}"


def _normalize_serial(value: str | None) -> tuple[str | None, str | None]:
    if value is None or not value.strip():
        return None, None
    original = value.strip()
    return original, original.lower()


def _serialize_item(item: StockInItem, include_amount: bool) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": item.id,
        "asset_code": item.asset_code,
        "asset_name": item.asset_name,
        "category_id": item.category_id,
        "unit_id": item.unit_id,
        "purchase_date": item.purchase_date.isoformat(),
        "manager_id": item.manager_id,
        "source_id": item.source_id,
        "location_id": item.location_id,
        "serial_number": item.serial_number,
    }
    if include_amount:
        result["original_amount"] = f"{item.original_amount:.2f}"
        result["zero_amount_reason"] = item.zero_amount_reason
    return result


def _serialize(operation: OperationRequest, actor_id: int) -> dict[str, Any]:
    stock_in = stock_in_request_repository.find_by_operation(operation.id)
    if stock_in is None:
        raise RuntimeError("stock-in request details missing")
    include_amount = permission_service.has_permission(actor_id, "asset:amount:view")
    return {
        "id": operation.id,
        "request_no": operation.request_no,
        "organization_id": stock_in.organization_id,
        "applicant_id": operation.applicant_id,
        "approval_status": operation.approval_status,
        "execution_status": operation.execution_status,
        "execution_error": operation.execution_error,
        "created_at": operation.created_at,
        "items": [
            _serialize_item(item, include_amount)
            for item in stock_in_item_repository.find_by_request(stock_in.id)
        ],
    }


def _serialize_summary(
    operation: OperationRequest, stock_in: StockInRequest
) -> dict[str, Any]:
    return {
        "id": operation.id,
        "request_no": operation.request_no,
        "organization_id": stock_in.organization_id,
        "applicant_id": operation.applicant_id,
        "approval_status": operation.approval_status,
        "execution_status": operation.execution_status,
        "created_at": operation.created_at,
    }


def _validate_item(item: dict[str, Any], seen_serials: set[str]) -> dict[str, Any]:
    category = master_data_service.require_enabled_category(item["category_id"])
    master_data_service.require_enabled_unit(item["unit_id"])
    master_data_service.require_enabled_source(item["source_id"])
    master_data_service.require_selectable_location(item["location_id"])
    manager = rbac_repository.find_user(item["manager_id"])
    if manager is None or not manager.enabled:
        raise BusinessException("资产责任管理员不存在或已停用")
    amount = Decimal(item["original_amount"])
    if amount < Decimal("0.00"):
        raise BusinessException(
            "采购金额不能为负数", result_code=ResultCode.BAD_REQUEST
        )
    if (
        amount == Decimal("0.00")
        and not str(item.get("zero_amount_reason") or "").strip()
    ):
        raise BusinessException(
            "零金额资产必须填写原因", result_code=ResultCode.BAD_REQUEST
        )
    serial, normalized_serial = _normalize_serial(item.get("serial_number"))
    if normalized_serial is not None:
        if normalized_serial in seen_serials:
            raise BusinessException("同一申请中的设备序列号不能重复")
        if stock_in_item_repository.normalized_serial_in_open_request(
            normalized_serial
        ):
            raise BusinessException("设备序列号已存在于待审批入库申请")
        if asset_repository.find_by_normalized_serial(normalized_serial) is not None:
            raise BusinessException("设备序列号已存在于正式资产")
        seen_serials.add(normalized_serial)
    normalized = dict(item)
    normalized["category"] = category
    normalized["original_amount"] = amount
    normalized["serial_number"] = serial
    normalized["normalized_serial"] = normalized_serial
    normalized["service_life_months"] = category.service_life_months
    normalized["expected_expiry_date"] = asset_data_service.calculate_expected_expiry(
        item["purchase_date"], category.service_life_months
    )
    normalized["custom_attributes"] = {}
    return normalized


def _stock_in_flow(candidates: list[int]) -> ApprovalFlowVersion:
    published = approval_flow_repository.find_published(OperationType.STOCK_IN.value)
    if published is not None:
        return published
    if (
        approval_flow_repository.find_definition(OperationType.STOCK_IN.value)
        is not None
    ):
        raise BusinessException("入库审批流尚未发布")
    if not current_app.testing:
        raise BusinessException("入库审批流尚未发布")

    definition = approval_flow_repository.add_definition(
        ApprovalFlowDefinition(
            operation_type=OperationType.STOCK_IN.value,
            name="入库审批",
            status=FlowStatus.PUBLISHED.value,
        )
    )
    version = approval_flow_repository.add_version(
        ApprovalFlowVersion(
            flow_definition_id=definition.id,
            version_no=1,
            status=FlowStatus.PUBLISHED.value,
            published_at=utc_now(),
        )
    )
    layer = ApprovalFlowLayer(
        flow_version_id=version.id,
        level_no=1,
        sign_mode=SignMode.OR_SIGN.value,
        allow_self_approval=True,
    )
    db.session.add(layer)
    db.session.flush()
    db.session.add_all(
        [
            ApprovalFlowAssigneeRule(
                layer_id=layer.id,
                assignee_type=AssigneeType.USER.value,
                assignee_id=candidate_id,
            )
            for candidate_id in candidates
        ]
    )
    db.session.flush()
    return approval_flow_repository.load_version_graph(version.id) or version


def submit(payload: dict[str, Any], actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "stock-in:create")
    organization_id = payload["organization_id"]
    permission_service.require_organization_scope(actor_id, organization_id)
    idempotency_key = (
        payload["idempotency_key"].strip() if payload.get("idempotency_key") else None
    )
    if idempotency_key:
        existing = operation_request_repository.find_by_idempotency_key(
            actor_id, OperationType.STOCK_IN.value, idempotency_key
        )
        if existing is not None:
            return _serialize(existing, actor_id)
    organization = organization_service.require_enabled(organization_id)
    top_organization = organization_service.get_top_level(organization.id)
    candidates = permission_service.find_approval_candidates(
        "stock-in:approve", organization_id
    )
    if not candidates:
        raise BusinessException("未找到符合条件的入库审批人")
    flow_version = _stock_in_flow(candidates)

    seen_serials: set[str] = set()
    try:
        validated_items = [
            _validate_item(item, seen_serials) for item in payload["items"]
        ]
    except BusinessException:
        if idempotency_key is None:
            raise
        db.session.rollback()
        existing = operation_request_repository.find_by_idempotency_key(
            actor_id, OperationType.STOCK_IN.value, idempotency_key
        )
        if existing is None:
            raise
        return _serialize(existing, actor_id)

    operation = OperationRequest(
        request_no=_request_no(),
        operation_type=OperationType.STOCK_IN.value,
        applicant_id=actor_id,
        approval_channel=ApprovalChannel.INTERNAL.value,
        approval_flow_version_id=flow_version.id,
        idempotency_key=idempotency_key,
        approval_status=ApprovalStatus.PENDING.value,
        execution_status=ExecutionStatus.NOT_STARTED.value,
        flow_version=1,
        submitted_at=utc_now(),
    )
    try:
        operation_request_repository.add(operation)
    except IntegrityError as exc:
        message = str(exc.orig).lower()
        is_idempotency_conflict = idempotency_key is not None and (
            "uq_operation_request_idempotency" in message
            or "operation_requests.applicant_id, "
            "operation_requests.operation_type, "
            "operation_requests.idempotency_key"
            in message
        )
        if not is_idempotency_conflict:
            raise
        db.session.rollback()
        existing = operation_request_repository.find_by_idempotency_key(
            actor_id, OperationType.STOCK_IN.value, idempotency_key
        )
        if existing is None:
            raise
        return _serialize(existing, actor_id)
    stock_in = StockInRequest(
        operation_request_id=operation.id,
        organization_id=organization_id,
        remark=payload.get("remark"),
    )
    stock_in_request_repository.add(stock_in)

    try:
        for item in validated_items:
            category = item.pop("category")
            allocated = asset_code_service.allocate(top_organization, category)
            stock_item = StockInItem(
                stock_in_request_id=stock_in.id,
                asset_code=allocated.asset_code,
                asset_name=item["asset_name"].strip(),
                category_id=category.id,
                unit_id=item["unit_id"],
                original_amount=item["original_amount"],
                zero_amount_reason=(item.get("zero_amount_reason") or None),
                purchase_date=item["purchase_date"],
                service_life_months=item["service_life_months"],
                expected_expiry_date=item["expected_expiry_date"],
                manager_id=item["manager_id"],
                source_id=item["source_id"],
                location_id=item["location_id"],
                specification_model=item.get("specification_model"),
                serial_number=item["serial_number"],
                normalized_serial=item["normalized_serial"],
                serial_reservation_key=item["normalized_serial"],
                receipt_no=item.get("receipt_no"),
                remark=item.get("remark"),
                custom_attributes=item["custom_attributes"],
            )
            stock_in_item_repository.add(stock_item)
            asset_code_service.reserve(operation.id, stock_item.id, allocated)
    except IntegrityError as exc:
        db.session.rollback()
        if "serial_reservation_key" in str(exc.orig).lower():
            raise BusinessException("设备序列号已被其他申请占用") from None
        raise

    approval_engine.initialize(operation, flow_version.id, organization_id)
    db.session.commit()
    return _serialize(operation, actor_id)


def get(operation_request_id: int, actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "stock-in:view")
    operation = _accessible_operation(operation_request_id, actor_id)
    return _serialize(operation, actor_id)


def _scope_parameters(actor_id: int) -> tuple[set[int] | None, int | None]:
    organization_ids = permission_service.accessible_organization_ids(actor_id)
    include_applicant_id = (
        actor_id
        if DataScope.SELF.value in permission_service.get_data_scopes(actor_id)
        else None
    )
    return organization_ids, include_applicant_id


def _accessible_operation(operation_request_id: int, actor_id: int) -> OperationRequest:
    organization_ids, include_applicant_id = _scope_parameters(actor_id)
    accessible = operation_request_repository.find_accessible_stock_in(
        operation_request_id,
        organization_ids,
        include_applicant_id,
    )
    if accessible is None:
        raise BusinessException("入库申请不存在", result_code=ResultCode.NOT_FOUND)
    operation, _stock_in = accessible
    return operation


def page(
    *,
    actor_id: int,
    page_index: int,
    size: int,
    request_no: str | None = None,
    approval_status: str | None = None,
    execution_status: str | None = None,
) -> PageResult:
    permission_service.require_permission(actor_id, "stock-in:view")
    organization_ids, include_applicant_id = _scope_parameters(actor_id)
    result = operation_request_repository.page_stock_in(
        organization_ids=organization_ids,
        include_applicant_id=include_applicant_id,
        page=page_index,
        size=size,
        request_no=request_no,
        approval_status=approval_status,
        execution_status=execution_status,
    )
    return PageResult(
        items=[
            _serialize_summary(operation, stock_in)
            for operation, stock_in in result.items
        ],
        total=result.total,
        page=result.page,
        size=result.size,
    )


def _operation_with_scope(operation_request_id: int, actor_id: int) -> OperationRequest:
    return _accessible_operation(operation_request_id, actor_id)


def approve(
    operation_request_id: int, opinion: str | None, actor_id: int
) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "stock-in:approve")
    operation = _operation_with_scope(operation_request_id, actor_id)
    if operation.approval_status == ApprovalStatus.APPROVED.value:
        if operation.execution_status == ExecutionStatus.SUCCESS.value:
            return _serialize(operation, actor_id)
        if operation.execution_status == ExecutionStatus.FAILED.value:
            raise BusinessException("执行失败，请使用重新执行功能")
    outcome = approval_engine.approve(operation.id, actor_id, opinion)
    db.session.commit()
    if outcome.request_approved:
        operation = operation_executor.execute_after_approval(operation.id, actor_id)
    return _serialize(operation, actor_id)


def reject(operation_request_id: int, opinion: str, actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "stock-in:approve")
    operation = _operation_with_scope(operation_request_id, actor_id)
    approval_engine.reject(operation.id, actor_id, opinion)
    asset_code_service.void_for_request(operation.id)
    stock_in = stock_in_request_repository.find_by_operation(operation.id)
    if stock_in is not None:
        stock_in_item_repository.release_serial_reservations(stock_in.id)
    db.session.commit()
    return _serialize(operation, actor_id)


def withdraw(operation_request_id: int, actor_id: int) -> dict[str, Any]:
    operation = _operation_with_scope(operation_request_id, actor_id)
    if operation.applicant_id != actor_id:
        raise BusinessException("只有申请人可以撤回", result_code=ResultCode.FORBIDDEN)
    approval_engine.withdraw(operation.id, actor_id, None)
    asset_code_service.void_for_request(operation.id)
    stock_in = stock_in_request_repository.find_by_operation(operation.id)
    if stock_in is not None:
        stock_in_item_repository.release_serial_reservations(stock_in.id)
    db.session.commit()
    return _serialize(operation, actor_id)


def retry(operation_request_id: int, actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "approval:execution:retry")
    operation = _operation_with_scope(operation_request_id, actor_id)
    if operation.approval_status != ApprovalStatus.APPROVED.value:
        raise BusinessException("只有审批通过的申请可以重新执行")
    if operation.execution_status == ExecutionStatus.SUCCESS.value:
        return _serialize(operation, actor_id)
    if operation.execution_status != ExecutionStatus.FAILED.value:
        raise BusinessException("当前执行状态不能重新执行")
    operation = operation_executor.retry(operation.id, actor_id)
    return _serialize(operation, actor_id)


__all__ = ["approve", "get", "page", "reject", "retry", "submit", "withdraw"]
