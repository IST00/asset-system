"""Independent physical, financial, and warranty asset change requests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select

from app.common import BusinessException, ResultCode
from app.enums import (
    ApprovalChannel,
    ApprovalExecutionMode,
    AssigneeType,
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
    Asset,
    AssetInformationChangeRequest,
    OperationRequest,
    OperationRequestAsset,
)
from app.models.mixins import utc_now
from app.repositories import approval_flow_repository, rbac_repository
from app.repositories import operation_request_asset_repository
from app.services import (
    approval_engine,
    asset_access_service,
    operation_service,
    permission_service,
)

_CHANGE_OPERATION_TYPES = {
    "PHYSICAL": OperationType.PHYSICAL_INFO_CHANGE.value,
    "FINANCIAL": OperationType.FINANCIAL_INFO_CHANGE.value,
    "WARRANTY": OperationType.WARRANTY_INFO_CHANGE.value,
}
_PHYSICAL_FIELDS = {
    "asset_name",
    "category_id",
    "unit_id",
    "supplier_id",
    "location_id",
    "manager_id",
    "source_id",
    "specification_model",
    "serial_number",
    "receipt_no",
    "rfid_tag",
    "remark",
}
_FINANCIAL_FIELDS = {
    "organization_id",
    "original_amount",
    "zero_amount_reason",
    "purchase_date",
    "service_life_months",
}
_WARRANTY_FIELDS = {
    "warranty_supplier_id",
    "warranty_contact",
    "warranty_phone",
    "warranty_expiry_date",
    "warranty_description",
}
_FIELDS_BY_TYPE = {
    "PHYSICAL": _PHYSICAL_FIELDS,
    "FINANCIAL": _FINANCIAL_FIELDS,
    "WARRANTY": _WARRANTY_FIELDS,
}


def _json_value(value: Any) -> Any:
    if isinstance(value, (date, Decimal)):
        return str(value)
    return value


def _normalize_changes(change_type: str, changes: dict[str, Any]) -> dict[str, Any]:
    allowed = _FIELDS_BY_TYPE[change_type]
    unknown = set(changes) - allowed
    if unknown:
        raise BusinessException(f"变更类型不支持字段：{', '.join(sorted(unknown))}")
    normalized = {key: _json_value(value) for key, value in changes.items()}
    for key in {
        "asset_name",
        "specification_model",
        "serial_number",
        "receipt_no",
        "rfid_tag",
        "remark",
        "zero_amount_reason",
        "warranty_contact",
        "warranty_phone",
        "warranty_description",
    } & normalized.keys():
        value = normalized[key]
        if value is not None:
            value = str(value).strip()
            normalized[key] = value or None
    if "asset_name" in normalized and normalized["asset_name"] is None:
        raise BusinessException("资产名称不能为空")
    if "original_amount" in normalized:
        try:
            amount = Decimal(str(normalized["original_amount"]))
        except InvalidOperation as error:
            raise BusinessException("金额格式无效") from error
        if amount < 0:
            raise BusinessException("金额不能为负数")
        normalized["original_amount"] = f"{amount:.2f}"
    if "service_life_months" in normalized:
        months = normalized["service_life_months"]
        if (
            not isinstance(months, int)
            or isinstance(months, bool)
            or not 1 <= months <= 1200
        ):
            raise BusinessException("使用期限必须为 1 到 1200 个月")
    return normalized


def _before_values(asset: Asset, fields: set[str]) -> dict[str, Any]:
    return {field: _json_value(getattr(asset, field)) for field in sorted(fields)} | {
        "version": asset.version
    }


def _published_flow(operation_type: str) -> ApprovalFlowVersion:
    published = approval_flow_repository.find_published(operation_type)
    if published is not None:
        return published
    definition = approval_flow_repository.find_definition(operation_type)
    if definition is not None:
        raise BusinessException("该信息变更审批流尚未发布")
    roles = [
        role
        for role_code in ("ASSET_ADMIN", "SUPER_ADMIN")
        if (role := rbac_repository.find_role_by_code(role_code)) is not None
    ]
    if not roles:
        raise BusinessException("未找到资产管理员或超级管理员审批角色")
    definition = approval_flow_repository.add_definition(
        ApprovalFlowDefinition(
            operation_type=operation_type,
            name="资产信息变更审批",
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
                assignee_type=AssigneeType.ROLE.value,
                assignee_id=role.id,
            )
            for role in roles
        ]
    )
    db.session.flush()
    return approval_flow_repository.load_version_graph(version.id) or version


def submit(payload: dict[str, Any], actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "asset:edit")
    change_type = payload["change_type"]
    if change_type == "FINANCIAL":
        permission_service.require_permission(actor_id, "asset:amount:view")
    operation_type = _CHANGE_OPERATION_TYPES[change_type]
    items = payload["items"]
    asset_ids = [item["asset_id"] for item in items]
    if len(set(asset_ids)) != len(asset_ids):
        raise BusinessException("同一申请不能重复选择资产")
    assets = [
        asset_access_service.get_accessible(asset_id, actor_id)
        for asset_id in asset_ids
    ]
    by_id = {asset.id: asset for asset in assets}
    target_data: dict[int, dict[str, Any]] = {}
    normalized_by_id: dict[int, dict[str, Any]] = {}
    for item in items:
        asset = by_id[item["asset_id"]]
        if asset.version != item["version"]:
            raise BusinessException("资产已被其他人修改，请刷新后重试")
        normalized = _normalize_changes(change_type, item["changes"])
        normalized_by_id[asset.id] = normalized
        target_data[asset.id] = normalized

    created = operation_service.create_request(
        operation_type=operation_type,
        applicant_id=actor_id,
        approval_channel=ApprovalChannel.INTERNAL.value,
        approval_execution_mode=ApprovalExecutionMode.AUTO_ON_APPROVAL.value,
        assets=assets,
        target_data_by_asset_id=target_data,
        idempotency_key=payload.get("idempotency_key"),
    )
    if not created.created:
        return get(created.operation.id, actor_id)
    db.session.add(
        AssetInformationChangeRequest(
            operation_request_id=created.operation.id,
            change_type=change_type,
            reason=payload["reason"].strip(),
        )
    )
    snapshots = operation_request_asset_repository.find_by_request(created.operation.id)
    for snapshot in snapshots:
        changes = normalized_by_id[snapshot.asset_id]
        snapshot.before_data = _before_values(by_id[snapshot.asset_id], set(changes))
        snapshot.target_data = changes

    organization_ids = {asset.organization_id for asset in assets}
    if len(organization_ids) != 1:
        raise BusinessException("信息变更单必须属于同一组织")
    flow = _published_flow(operation_type)
    approval_engine.initialize(created.operation, flow.id, next(iter(organization_ids)))
    db.session.commit()
    return get(created.operation.id, actor_id)


def _detail(operation_request_id: int) -> AssetInformationChangeRequest:
    detail = db.session.scalar(
        select(AssetInformationChangeRequest).where(
            AssetInformationChangeRequest.operation_request_id == operation_request_id
        )
    )
    if detail is None:
        raise BusinessException(
            "资产信息变更单不存在", result_code=ResultCode.NOT_FOUND
        )
    return detail


def get(operation_request_id: int, actor_id: int) -> dict[str, Any]:
    result = operation_service.get_request(operation_request_id, actor_id)
    detail = _detail(operation_request_id)
    operation = db.session.get(OperationRequest, operation_request_id)
    if operation is None:
        raise BusinessException(
            "资产信息变更单不存在", result_code=ResultCode.NOT_FOUND
        )
    result.update(
        {
            "change_request_id": detail.id,
            "change_type": detail.change_type,
            "reason": detail.reason,
            "requires_feishu_approval": result["approval_channel"] == "FEISHU",
            "external_instance_id": operation.external_instance_id,
            "created_at": operation.created_at,
            "executed_at": operation.executed_at,
        }
    )
    return result


def list_requests(
    actor_id: int, *, page: int = 0, size: int = 50, change_type: str | None = None
) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "operation:request:view")
    statement = (
        select(AssetInformationChangeRequest, OperationRequest)
        .join(
            OperationRequest,
            OperationRequest.id == AssetInformationChangeRequest.operation_request_id,
        )
        .outerjoin(
            OperationRequestAsset,
            OperationRequestAsset.operation_request_id == OperationRequest.id,
        )
        .where(operation_service.request_access_filter(actor_id))
        .distinct()
        .order_by(OperationRequest.id.desc())
    )
    if change_type is not None:
        statement = statement.where(
            AssetInformationChangeRequest.change_type == change_type
        )
    rows = (
        db.session.execute(statement.offset(page * size).limit(size + 1)).tuples().all()
    )
    items = [
        {
            "id": detail.id,
            "operation_request_id": operation.id,
            "request_no": operation.request_no,
            "change_type": detail.change_type,
            "reason": detail.reason,
            "applicant_id": operation.applicant_id,
            "approval_channel": operation.approval_channel,
            "requires_feishu_approval": operation.approval_channel == "FEISHU",
            "approval_status": operation.approval_status,
            "execution_status": operation.execution_status,
            "executed_at": operation.executed_at,
            "created_at": operation.created_at,
        }
        for detail, operation in rows[:size]
    ]
    return {"items": items, "page": page, "size": size, "has_next": len(rows) > size}


__all__ = ["get", "list_requests", "submit"]
