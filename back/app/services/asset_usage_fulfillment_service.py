"""Business workflow for issuing and receiving self-service asset requests."""

from __future__ import annotations

from typing import Any

from flask import current_app
from sqlalchemy import or_, select, true

from app.common import BusinessException, ResultCode
from app.enums import (
    ApprovalChannel,
    ApprovalExecutionMode,
    ApprovalStatus,
    AssetDataCompleteness,
    AssetStatus,
    ExecutionStatus,
    FulfillmentStatus,
    OperationType,
    RecordStatus,
    UsageType,
)
from app.extensions import db
from app.models import (
    Asset,
    AssetBusinessLock,
    AssetLocation,
    AssetUsageRequest,
    OperationRequest,
    OperationRequestAsset,
    ExternalApprovalEvent,
    Organization,
)
from app.models.mixins import utc_now

from app.repositories.asset_repository import asset_repository
from app.repositories.asset_usage_return_repository import (
    asset_usage_request_repository,
)
from app.repositories.operation_repository import (
    asset_business_lock_repository,
    external_approval_event_repository,
    operation_request_asset_repository,
)
from app.repositories.workflow_repository import operation_request_repository
from app.services import (
    asset_usage_service,
    audit_service,
    feishu_notification_service,
    operation_executor,
    operation_service,
    permission_service,
)
from app.services.asset_usage_return_support import (
    build_named_snapshot,
    expand_assets,
    require_assets_in_scope,
    require_idle_assets,
    require_location,
)

_MANAGE_PERMISSION = "asset:usage:manage"
_SELF_PERMISSION = "asset:usage:self"
_USAGE_TYPES = {OperationType.PERSONAL_USE.value}


def _require_request(
    operation_request_id: int,
) -> tuple[OperationRequest, AssetUsageRequest]:
    operation = operation_request_repository.get(operation_request_id)
    if operation is None:
        raise BusinessException("申请不存在", result_code=ResultCode.NOT_FOUND)
    detail = asset_usage_request_repository.find_by_operation(operation.id)
    if detail is None:
        raise BusinessException("领用申请详情不存在", result_code=ResultCode.NOT_FOUND)
    if operation.operation_type not in _USAGE_TYPES:
        raise BusinessException("当前申请不支持发放和签收")
    if detail.target_user_id is None:
        raise BusinessException("个人领用申请缺少目标员工")
    if operation.approval_execution_mode != ApprovalExecutionMode.MANUAL_CONFIRM.value:
        raise BusinessException("当前申请不是管理员发放流程")
    return operation, detail


def _serialize(operation: OperationRequest, actor_id: int) -> dict[str, Any]:
    return asset_usage_service.get(operation.id, actor_id)


def _same_scalar(actual: object, expected: object) -> bool:
    return type(actual) is type(expected) and actual == expected


def _canonical_asset_data(asset: Asset) -> dict[str, object]:
    return {
        "status": asset.status,
        "organization_id": asset.organization_id,
        "usage_type": asset.usage_type,
        "holder_user_id": asset.holder_user_id,
        "public_object_id": asset.public_object_id,
        "usage_department_id": asset.usage_department_id,
        "location_id": asset.location_id,
        "manager_id": asset.manager_id,
        "parent_asset_id": asset.parent_asset_id,
        "version": asset.version,
    }


def _validate_fulfillment_asset(
    asset: Asset,
    snapshot: OperationRequestAsset,
    expected_status: str,
    *,
    initial_issue: bool = False,
) -> None:
    if snapshot.asset_status_snapshot != AssetStatus.IDLE.value:
        raise BusinessException("领用资产原始状态不是空闲")
    if asset.status != expected_status:
        raise BusinessException(
            "领用资产当前状态不是空闲"
            if expected_status == AssetStatus.IDLE.value
            else "领用资产当前状态不是领用待确认"
        )
    if not _same_scalar(snapshot.organization_id_snapshot, asset.organization_id):
        raise BusinessException("领用资产组织快照与当前数据不匹配")
    if initial_issue:
        if not _same_scalar(snapshot.asset_version_snapshot, asset.version):
            raise BusinessException("领用资产版本已变化")
    elif asset.version <= snapshot.asset_version_snapshot:
        raise BusinessException("领用资产发放状态未生效")

    before_data = snapshot.before_data
    canonical = _canonical_asset_data(asset)
    comparable = {
        key: value
        for key, value in canonical.items()
        if key not in {"status", "version"}
    }
    if not isinstance(before_data, dict) or any(
        key not in before_data or not _same_scalar(before_data[key], value)
        for key, value in comparable.items()
    ):
        raise BusinessException("领用资产操作前快照与当前数据不匹配")
    if not _same_scalar(
        before_data.get("status"), snapshot.asset_status_snapshot
    ) or not _same_scalar(before_data.get("version"), snapshot.asset_version_snapshot):
        raise BusinessException("领用资产原始快照不匹配")


def _load_fulfillment_assets(
    operation: OperationRequest,
    expected_status: str,
    *,
    initial_issue: bool = False,
) -> list[tuple[Asset, OperationRequestAsset]]:
    snapshots = operation_request_asset_repository.find_by_request(operation.id)
    if not snapshots:
        raise BusinessException("领用申请未包含资产快照")
    snapshot_ids = [snapshot.asset_id for snapshot in snapshots]
    if snapshot_ids != sorted(set(snapshot_ids)):
        raise BusinessException("领用申请资产快照不完整")
    assets = asset_repository.find_many_for_update(snapshot_ids)
    if [asset.id for asset in assets] != snapshot_ids:
        raise BusinessException("领用申请资产与快照不一致")
    pairs = list(zip(assets, snapshots, strict=True))
    for asset, snapshot in pairs:
        _validate_fulfillment_asset(
            asset,
            snapshot,
            expected_status,
            initial_issue=initial_issue,
        )
    return pairs


def _transition_fulfillment_assets(
    operation: OperationRequest,
    actor_id: int,
    from_status: str,
    to_status: str,
    lifecycle_remark: str,
    *,
    initial_issue: bool = False,
) -> None:
    for asset, snapshot in _load_fulfillment_assets(
        operation,
        from_status,
        initial_issue=initial_issue,
    ):
        before_data = _canonical_asset_data(asset)
        if not asset_repository.cas_update(
            asset.id,
            asset.version,
            {"status": to_status},
        ):
            raise BusinessException("资产版本冲突")
        audit_service.record_asset_lifecycle(
            asset_id=asset.id,
            operation_type=operation.operation_type,
            request_no=operation.request_no,
            actor_id=actor_id,
            before_data=before_data,
            after_data={
                **before_data,
                "status": to_status,
                "version": asset.version + 1,
            },
            remark=lifecycle_remark,
        )


def _current_root_asset_ids(operation: OperationRequest) -> list[int]:
    snapshots = operation_request_asset_repository.find_by_request(operation.id)
    return sorted(
        snapshot.asset_id
        for snapshot in snapshots
        if isinstance(snapshot.before_data, dict)
        and snapshot.before_data.get("parent_asset_id") is None
    )


def require_issue_location(region_id: int, location_id: int) -> AssetLocation:
    """Validate an administrator-selected region and selectable storage location."""

    region = db.session.get(AssetLocation, region_id)
    location = require_location(location_id)
    if region is None or region.status != RecordStatus.ENABLED.value:
        raise BusinessException(
            "领用后区域不存在或已停用", result_code=ResultCode.NOT_FOUND
        )
    valid_location = location.parent_id == region.id or (
        location.parent_id is None and location.id == region.id
    )
    if not valid_location:
        raise BusinessException("领用后存放地点不属于所选区域")
    return location


def issue_candidates(operation_request_id: int, actor_id: int) -> dict[str, Any]:
    """List concrete idle assets an administrator may issue for the request."""
    permission_service.require_permission(actor_id, _MANAGE_PERMISSION)
    operation, detail = _require_request(operation_request_id)
    if operation.approval_status not in {
        ApprovalStatus.PENDING.value,
        ApprovalStatus.APPROVED.value,
    }:
        raise BusinessException("只有待审批或审批通过的申请可以选择资产")
    if operation.execution_status != ExecutionStatus.NOT_STARTED.value:
        raise BusinessException("当前申请已经执行或不能发放")
    if detail.fulfillment_status not in {
        FulfillmentStatus.PENDING_ISSUE.value,
        FulfillmentStatus.SIGN_REFUSED.value,
    }:
        raise BusinessException("当前申请状态不能选择发放资产")

    requested_quantity = detail.requested_quantity
    requested_category_id = detail.requested_category_id
    fixed_asset_ids: list[int] | None = None
    if requested_category_id is None or requested_quantity is None:
        fixed_asset_ids = _current_root_asset_ids(operation)
        requested_quantity = len(fixed_asset_ids)
        if requested_quantity == 0:
            raise BusinessException("领用申请未包含可发放资产")

    actor_scope = permission_service.accessible_organization_ids(actor_id)
    organization_condition = (
        Asset.organization_id.in_(actor_scope) if actor_scope is not None else true()
    )
    statement = (
        select(Asset)
        .outerjoin(AssetBusinessLock, AssetBusinessLock.asset_id == Asset.id)
        .where(
            Asset.status == AssetStatus.IDLE.value,
            Asset.parent_asset_id.is_(None),
            organization_condition,
            Asset.data_completeness == AssetDataCompleteness.COMPLETE.value,
            Asset.unit_id.is_not(None),
            Asset.source_id.is_not(None),
            Asset.location_id.is_not(None),
            or_(
                AssetBusinessLock.id.is_(None),
                AssetBusinessLock.operation_request_id == operation.id,
            ),
        )
        .order_by(Asset.asset_code.asc(), Asset.id.asc())
    )
    if requested_category_id is not None:
        statement = statement.where(Asset.category_id == requested_category_id)
    if fixed_asset_ids is not None:
        statement = statement.where(Asset.id.in_(fixed_asset_ids))
    assets = list(db.session.scalars(statement).all())

    organization_names: dict[int, str] = {
        organization_id: organization_name
        for organization_id, organization_name in db.session.execute(
            select(Organization.id, Organization.name).where(
                Organization.id.in_({asset.organization_id for asset in assets})
            )
        ).all()
    }
    location_ids = {
        asset.location_id for asset in assets if asset.location_id is not None
    }
    location_names: dict[int, str] = {
        location_id: location_name
        for location_id, location_name in db.session.execute(
            select(AssetLocation.id, AssetLocation.name).where(
                AssetLocation.id.in_(location_ids)
            )
        ).all()
    }
    return {
        "requested_quantity": requested_quantity,
        "requested_category": detail.requested_category_snapshot,
        "items": [
            {
                "id": asset.id,
                "asset_code": asset.asset_code,
                "asset_name": asset.asset_name,
                "status": asset.status,
                "organization_id": asset.organization_id,
                "organization_name": organization_names.get(asset.organization_id),
                "location_name": (
                    location_names.get(asset.location_id)
                    if asset.location_id is not None
                    else None
                ),
                "specification_model": asset.specification_model,
                "serial_number": asset.serial_number,
            }
            for asset in assets
        ],
    }


def _select_issue_assets(
    operation: OperationRequest,
    detail: AssetUsageRequest,
    actor_id: int,
    asset_ids: list[int],
) -> list[Asset]:
    selected_ids = sorted(set(asset_ids))
    if len(selected_ids) != len(asset_ids):
        raise BusinessException("发放资产不能重复")
    requested_quantity = detail.requested_quantity
    if requested_quantity is not None and len(selected_ids) != requested_quantity:
        raise BusinessException(f"本申请必须选择 {requested_quantity} 件资产")
    if detail.requested_category_id is None:
        fixed_asset_ids = _current_root_asset_ids(operation)
        if selected_ids != fixed_asset_ids:
            raise BusinessException("本申请已指定具体资产，不能更换")
    expanded_assets = expand_assets(selected_ids)
    assets = asset_repository.find_many_for_update(
        [asset.id for asset in expanded_assets]
    )
    if [asset.id for asset in assets] != [asset.id for asset in expanded_assets]:
        raise BusinessException("发放资产不存在", result_code=ResultCode.NOT_FOUND)
    selected_roots = [asset for asset in assets if asset.id in selected_ids]
    if len(selected_roots) != len(selected_ids) or any(
        asset.parent_asset_id is not None for asset in selected_roots
    ):
        raise BusinessException("只能选择主资产进行发放")
    if detail.requested_category_id is not None and any(
        asset.category_id != detail.requested_category_id for asset in selected_roots
    ):
        raise BusinessException("所选资产类别与申请类别不一致")
    require_idle_assets(assets)
    require_assets_in_scope(actor_id, assets)
    locks = asset_business_lock_repository.find_by_assets_for_update(
        [asset.id for asset in assets]
    )
    conflict = next(
        (lock for lock in locks if lock.operation_request_id != operation.id),
        None,
    )
    if conflict is not None:
        conflict_asset = next(
            asset for asset in assets if asset.id == conflict.asset_id
        )
        raise BusinessException(f"资产 {conflict_asset.asset_code} 正在处理其它申请")
    return assets


def _issue_without_reapproval(
    operation: OperationRequest,
    detail: AssetUsageRequest,
    actor_id: int,
    assets: list[Asset],
    target_location: AssetLocation,
    remark: str | None,
) -> dict[str, Any]:
    """Reissue a rejected-receipt request without changing the approval result."""
    detail.target_region_id = target_location.parent_id or target_location.id
    detail.target_location_id = target_location.id
    detail.target_location_snapshot = build_named_snapshot(target_location)
    target_data_by_asset_id = {
        asset.id: {
            "status": AssetStatus.IN_USE.value,
            "usage_type": UsageType.PERSONAL.value,
            "holder_user_id": detail.target_user_id,
            "public_object_id": None,
            "usage_department_id": detail.usage_department_id,
            "location_id": target_location.id,
        }
        for asset in assets
    }
    operation_service.replace_request_assets(
        operation,
        assets,
        target_data_by_asset_id,
    )
    _transition_fulfillment_assets(
        operation,
        actor_id,
        AssetStatus.IDLE.value,
        AssetStatus.PENDING_RECEIPT.value,
        "管理员重新发放资产" if remark is None else f"管理员重新发放资产：{remark}",
        initial_issue=True,
    )
    detail.fulfillment_status = FulfillmentStatus.PENDING_SIGN.value
    detail.issued_by = actor_id
    detail.issued_at = utc_now()
    detail.issue_remark = remark
    detail.signed_by = None
    detail.signed_at = None
    detail.sign_remark = None
    db.session.commit()
    return _serialize(operation, actor_id)


def issue(
    operation_request_id: int,
    actor_id: int,
    asset_ids: list[int],
    region_id: int,
    location_id: int,
    remark: str | None = None,
) -> dict[str, Any]:
    """Approve in the asset system and issue assets for employee receipt.

    The employee's Feishu approval is a to-do reminder. The asset system is
    the decision source and atomically approves the request, selects concrete
    assets, and moves them to ``PENDING_RECEIPT``.
    """
    permission_service.require_permission(actor_id, _MANAGE_PERMISSION)
    operation, detail = _require_request(operation_request_id)
    if operation.approval_status == ApprovalStatus.APPROVED.value:
        if detail.fulfillment_status == FulfillmentStatus.COMPLETED.value:
            return _serialize(operation, actor_id)
        if detail.fulfillment_status == FulfillmentStatus.PENDING_SIGN.value:
            if sorted(set(asset_ids)) != _current_root_asset_ids(operation):
                raise BusinessException("本次申请已发放，不能更换资产")
            _load_fulfillment_assets(operation, AssetStatus.PENDING_RECEIPT.value)
            return _serialize(operation, actor_id)
    if operation.approval_status not in {
        ApprovalStatus.PENDING.value,
        ApprovalStatus.APPROVED.value,
    }:
        raise BusinessException("当前申请状态不能审批发放")
    if operation.execution_status != ExecutionStatus.NOT_STARTED.value:
        raise BusinessException("当前申请已经执行或不能发放")
    if detail.fulfillment_status not in {
        FulfillmentStatus.PENDING_ISSUE.value,
        FulfillmentStatus.SIGN_REFUSED.value,
    }:
        raise BusinessException("当前申请状态不能审批发放")
    before = {
        "approval_status": operation.approval_status,
        "fulfillment_status": detail.fulfillment_status,
        "issued_by": detail.issued_by,
        "issued_at": detail.issued_at.isoformat() if detail.issued_at else None,
    }
    normalized_remark = remark.strip() if remark else None
    target_location = require_issue_location(region_id, location_id)
    assets = _select_issue_assets(operation, detail, actor_id, asset_ids)
    if operation.approval_status == ApprovalStatus.APPROVED.value:
        return _issue_without_reapproval(
            operation, detail, actor_id, assets, target_location, normalized_remark
        )

    if not operation_request_repository.transition_pending(
        operation.id,
        operation.version,
        ApprovalStatus.APPROVED.value,
    ):
        raise BusinessException("审批状态已变化，请刷新后重试")
    db.session.expire(operation, ["approval_status", "version"])
    operation.approved_at = utc_now()

    if operation.approval_channel == ApprovalChannel.FEISHU.value:
        external_approval_event_repository.add(
            ExternalApprovalEvent(
                operation_request_id=operation.id,
                provider=ApprovalChannel.FEISHU.value,
                external_event_id=f"SYSTEM-ISSUE-{operation.id}-{operation.version}",
                external_instance_id=operation.external_instance_id or "",
                event_type="APPROVAL_STATUS_CHANGED",
                payload={"status": ApprovalStatus.APPROVED.value},
                processing_status="PROCESSED",
                processed_at=utc_now(),
            )
        )
        db.session.flush()

    detail.target_region_id = region_id
    detail.target_location_id = location_id
    detail.target_location_snapshot = build_named_snapshot(target_location)
    target_data_by_asset_id = {
        asset.id: {
            "status": AssetStatus.IN_USE.value,
            "usage_type": UsageType.PERSONAL.value,
            "holder_user_id": detail.target_user_id,
            "public_object_id": None,
            "usage_department_id": detail.usage_department_id,
            "location_id": location_id,
        }
        for asset in assets
    }
    operation_service.replace_request_assets(
        operation,
        assets,
        target_data_by_asset_id,
    )
    _transition_fulfillment_assets(
        operation,
        actor_id,
        AssetStatus.IDLE.value,
        AssetStatus.PENDING_RECEIPT.value,
        "管理员审批通过并发放资产"
        if normalized_remark is None
        else f"管理员审批通过并发放资产：{normalized_remark}",
        initial_issue=True,
    )
    detail.fulfillment_status = FulfillmentStatus.PENDING_SIGN.value
    detail.issued_by = actor_id
    detail.issued_at = utc_now()
    detail.issue_remark = normalized_remark
    detail.signed_by = None
    detail.signed_at = None
    detail.sign_remark = None
    audit_service.record_resource_change(
        action="ASSET_USAGE_REVIEW_AND_ISSUE",
        resource_type="asset_usage_request",
        resource_id=operation.id,
        actor_id=actor_id,
        before_data=before,
        after_data={
            "approval_status": operation.approval_status,
            "fulfillment_status": detail.fulfillment_status,
            "issued_by": actor_id,
            "issue_remark": detail.issue_remark,
        },
        reason=detail.issue_remark,
    )
    db.session.commit()

    recipient_ids = [actor_id, operation.applicant_id]
    if detail.target_user_id is not None:
        recipient_ids.append(detail.target_user_id)
    notification_result = feishu_notification_service.notify_users(
        recipient_ids,
        "资产领用审批结果",
        "「资产领用/发放」审批结果: 已通过",
    )
    current_app.logger.info(
        "Feishu approval result notification for request %s: %s",
        operation.id,
        notification_result,
    )
    return _serialize(operation, actor_id)


def sign(
    operation_request_id: int,
    actor_id: int,
    remark: str | None = None,
) -> dict[str, Any]:
    """Receive issued assets and only then execute the asset state change."""
    permission_service.require_permission(actor_id, _SELF_PERMISSION)
    operation, detail = _require_request(operation_request_id)
    if detail.target_user_id != actor_id:
        raise BusinessException(
            "只有目标员工可以签收", result_code=ResultCode.FORBIDDEN
        )
    if detail.fulfillment_status == FulfillmentStatus.COMPLETED.value:
        return _serialize(operation, actor_id)
    if detail.fulfillment_status != FulfillmentStatus.PENDING_SIGN.value:
        raise BusinessException("资产尚未发放，不能签收")
    if operation.approval_status != ApprovalStatus.APPROVED.value:
        raise BusinessException("只有审批通过的申请可以签收")
    executed = operation_executor.confirm(operation.id, actor_id)
    if executed.execution_status != ExecutionStatus.SUCCESS.value:
        raise BusinessException("签收时资产执行失败，请联系管理员")
    refreshed_detail = asset_usage_request_repository.find_by_operation(operation.id)
    if refreshed_detail is None:
        raise BusinessException("领用申请详情不存在", result_code=ResultCode.NOT_FOUND)
    refreshed_detail.fulfillment_status = FulfillmentStatus.COMPLETED.value
    refreshed_detail.signed_by = actor_id
    refreshed_detail.signed_at = utc_now()
    refreshed_detail.sign_remark = remark.strip() if remark else None
    audit_service.record_resource_change(
        action="ASSET_USAGE_SIGN",
        resource_type="asset_usage_request",
        resource_id=operation.id,
        actor_id=actor_id,
        before_data={"fulfillment_status": FulfillmentStatus.PENDING_SIGN.value},
        after_data={
            "fulfillment_status": refreshed_detail.fulfillment_status,
            "signed_by": actor_id,
            "sign_remark": refreshed_detail.sign_remark,
        },
        reason=detail.sign_remark,
    )
    db.session.commit()
    return _serialize(executed, actor_id)


def refuse_sign(
    operation_request_id: int,
    actor_id: int,
    remark: str,
) -> dict[str, Any]:
    permission_service.require_permission(actor_id, _SELF_PERMISSION)
    operation, detail = _require_request(operation_request_id)
    if detail.target_user_id != actor_id:
        raise BusinessException(
            "只有目标员工可以拒绝签收", result_code=ResultCode.FORBIDDEN
        )
    normalized = remark.strip()
    if not normalized:
        raise BusinessException(
            "拒绝签收必须填写原因", result_code=ResultCode.BAD_REQUEST
        )
    if detail.fulfillment_status == FulfillmentStatus.SIGN_REFUSED.value:
        return _serialize(operation, actor_id)
    if detail.fulfillment_status != FulfillmentStatus.PENDING_SIGN.value:
        raise BusinessException("当前申请不在待签收状态")
    _transition_fulfillment_assets(
        operation,
        actor_id,
        AssetStatus.PENDING_RECEIPT.value,
        AssetStatus.IDLE.value,
        f"员工拒绝签收：{normalized}",
    )
    detail.fulfillment_status = FulfillmentStatus.SIGN_REFUSED.value
    detail.signed_by = actor_id
    detail.signed_at = utc_now()
    detail.sign_remark = normalized
    audit_service.record_resource_change(
        action="ASSET_USAGE_SIGN_REFUSED",
        resource_type="asset_usage_request",
        resource_id=operation.id,
        actor_id=actor_id,
        before_data={"fulfillment_status": FulfillmentStatus.PENDING_SIGN.value},
        after_data={
            "fulfillment_status": detail.fulfillment_status,
            "signed_by": actor_id,
            "sign_remark": normalized,
        },
        reason=normalized,
    )
    db.session.commit()
    return _serialize(operation, actor_id)


def request_return(
    operation_request_id: int,
    actor_id: int,
    reason: str,
) -> dict[str, Any]:
    """Ask the employee to return an active borrowed asset."""

    permission_service.require_permission(actor_id, _MANAGE_PERMISSION)
    operation, detail = _require_request(operation_request_id)
    if detail.usage_mode != "BORROW":
        raise BusinessException("只有借用资产可以要求归还")
    if (
        operation.execution_status != ExecutionStatus.SUCCESS.value
        or detail.fulfillment_status != FulfillmentStatus.COMPLETED.value
        or detail.target_user_id is None
    ):
        raise BusinessException("只有已签收且仍在借用的资产可以要求归还")
    snapshots = operation_request_asset_repository.find_by_request(operation.id)
    if not snapshots:
        raise BusinessException("借用申请没有关联资产")
    assets = list(
        db.session.scalars(
            select(Asset).where(Asset.id.in_([item.asset_id for item in snapshots]))
        ).all()
    )
    require_assets_in_scope(actor_id, assets)
    if len(assets) != len(snapshots) or any(
        asset.status != AssetStatus.IN_USE.value
        or asset.usage_type != UsageType.PERSONAL.value
        or asset.holder_user_id != detail.target_user_id
        for asset in assets
    ):
        raise BusinessException("资产已不在目标员工名下，无法要求归还")
    normalized = reason.strip()
    before_data = {
        "return_requested_by": detail.return_requested_by,
        "return_requested_at": (
            detail.return_requested_at.isoformat()
            if detail.return_requested_at is not None
            else None
        ),
        "return_request_reason": detail.return_request_reason,
    }
    detail.return_requested_by = actor_id
    detail.return_requested_at = utc_now()
    detail.return_request_reason = normalized
    audit_service.record_resource_change(
        action="ASSET_BORROW_RETURN_REQUESTED",
        resource_type="asset_usage_request",
        resource_id=operation.id,
        actor_id=actor_id,
        before_data=before_data,
        after_data={
            "return_requested_by": actor_id,
            "return_requested_at": detail.return_requested_at.isoformat(),
            "return_request_reason": normalized,
        },
        reason=normalized,
    )
    db.session.commit()
    return _serialize(operation, actor_id)


__all__ = ["issue", "refuse_sign", "request_return", "sign"]
