"""Personal and public asset-usage request orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from flask import current_app
from sqlalchemy import func, select

from app.common import BusinessException, PageResult, ResultCode
from app.common.datetime import isoformat_utc, normalize_utc
from app.enums import (
    ApprovalChannel,
    ApprovalExecutionMode,
    ApprovalStatus,
    AssigneeType,
    AssetStatus,
    ExecutionStatus,
    FlowStatus,
    FulfillmentStatus,
    OperationType,
    SignMode,
    UsageMode,
    UsageType,
)
from app.extensions import db
from app.models import (
    ApprovalFlowAssigneeRule,
    ApprovalFlowDefinition,
    ApprovalFlowLayer,
    ApprovalFlowVersion,
    Asset,
    AssetCategory,
    AssetLocation,
    OperationRequest,
    OperationRequestAsset,
)
from app.models.asset_usage_return import AssetUsageRequest
from app.models.mixins import utc_now
from app.repositories import approval_flow_repository
from app.repositories.asset_usage_return_repository import (
    asset_usage_request_repository,
    find_operation_assets,
)
from app.repositories.workflow_repository import operation_request_repository
from app.services import (
    approval_engine,
    approval_provider_service,
    operation_executor,
    operation_service,
    organization_service,
    permission_service,
)
from app.services.asset_usage_return_support import (
    build_named_snapshot,
    build_user_snapshot,
    expand_assets,
    operation_assets,
    require_assets_in_scope,
    require_idle_assets,
    require_location,
    require_personal_target,
    require_public_target,
    serialize_operation,
    validate_named_snapshot,
    validate_user_snapshot,
)

_MANAGE_USAGE_PERMISSION = "asset:usage:manage"
_SELF_USAGE_PERMISSION = "asset:usage:self"
_TARGET_FIELDS = frozenset(
    {
        "status",
        "usage_type",
        "holder_user_id",
        "public_object_id",
        "usage_department_id",
        "location_id",
    }
)


def _require_clean_entry_unit_of_work() -> None:
    """Top-level commit owners cannot safely compose with pending ORM writes."""
    session = db.session()
    if session.new or session.dirty or session.deleted:
        raise RuntimeError(
            "asset usage transaction boundary rejected pending business writes"
        )


def _idempotency_key(payload: dict[str, Any]) -> str | None:
    value = payload.get("idempotency_key")
    if value is None:
        return None
    if not isinstance(value, str):
        raise BusinessException(
            "幂等键格式无效",
            result_code=ResultCode.BAD_REQUEST,
        )
    return value.strip() or None


def _usage_approval_candidates(
    organization_ids: set[int],
) -> list[int]:
    candidates: list[int] = []
    for organization_id in sorted(organization_ids):
        candidates.extend(
            permission_service.find_approval_candidates(
                _MANAGE_USAGE_PERMISSION,
                organization_id,
            )
        )
    return sorted(set(candidates))


def _usage_flow(operation_type: str, candidates: list[int]) -> ApprovalFlowVersion:
    published = approval_flow_repository.find_published(operation_type)
    if published is not None:
        return published
    if approval_flow_repository.find_definition(operation_type) is not None:
        raise BusinessException("资产领退审批流尚未发布")
    if not current_app.testing:
        raise BusinessException("资产领退审批流尚未发布")

    definition = approval_flow_repository.add_definition(
        ApprovalFlowDefinition(
            operation_type=operation_type,
            name="资产领退审批",
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
        ApprovalFlowAssigneeRule(
            layer_id=layer.id,
            assignee_type=AssigneeType.USER.value,
            assignee_id=candidate_id,
        )
        for candidate_id in candidates
    )
    db.session.flush()
    return approval_flow_repository.load_version_graph(version.id) or version


def _initialize_internal_approval(
    operation: OperationRequest,
    assets: list[Asset],
) -> None:
    organization_ids = {asset.organization_id for asset in assets}
    if None in organization_ids:
        raise BusinessException("申请资产缺少所属公司")
    candidates = _usage_approval_candidates(organization_ids)
    if not candidates:
        raise BusinessException("未找到符合条件的资产领退审批人")
    flow = _usage_flow(operation.operation_type, candidates)
    approval_engine.initialize(operation, flow.id, min(organization_ids))
    db.session.commit()


def _usage_mode(detail: AssetUsageRequest) -> str:
    return detail.usage_mode or UsageMode.USE.value


def _feature_data(
    detail: AssetUsageRequest, operation: OperationRequest | None = None
) -> dict[str, Any]:
    feature: dict[str, Any] = {
        "target_user_id": detail.target_user_id,
        "target_public_object_id": detail.target_public_object_id,
        "usage_department_id": detail.usage_department_id,
        "target_location_id": detail.target_location_id,
        "target_user_snapshot": detail.target_user_snapshot,
        "usage_department_snapshot": detail.usage_department_snapshot,
        "target_public_object_snapshot": detail.target_public_object_snapshot,
        "target_location_snapshot": detail.target_location_snapshot,
    }
    if detail.reason:
        feature["reason"] = detail.reason
    if detail.requested_category_id is not None:
        feature["requested_category_id"] = detail.requested_category_id
        feature["requested_category_snapshot"] = detail.requested_category_snapshot
        feature["requested_quantity"] = detail.requested_quantity
    if _usage_mode(detail) == UsageMode.BORROW.value:
        expected_return_at = detail.expected_return_at
        feature["usage_mode"] = UsageMode.BORROW.value
        feature["expected_return_at"] = (
            isoformat_utc(expected_return_at)
            if expected_return_at is not None
            else None
        )
        feature["is_overdue"] = bool(
            expected_return_at is not None
            and normalize_utc(expected_return_at) < datetime.now(timezone.utc)
            and operation is not None
            and operation.execution_status == ExecutionStatus.SUCCESS.value
        )
    return feature


def _same_scalar(actual: object, expected: object) -> bool:
    return type(actual) is type(expected) and actual == expected


def _target_matches(
    target: object,
    expected: dict[str, object],
) -> bool:
    return (
        isinstance(target, dict)
        and set(target) == _TARGET_FIELDS
        and all(_same_scalar(target[key], value) for key, value in expected.items())
    )


def _personal_snapshot_target(
    detail: AssetUsageRequest,
    before_data: object,
) -> dict[str, object]:
    location_id = detail.target_location_id
    if location_id is None:
        if not isinstance(before_data, dict):
            raise BusinessException("领用申请详情与资产目标快照不匹配")
        location_id = before_data.get("location_id")
        if type(location_id) is not int:
            raise BusinessException("领用申请详情与资产目标快照不匹配")
    return {
        "status": AssetStatus.IN_USE.value,
        "usage_type": UsageType.PERSONAL.value,
        "holder_user_id": detail.target_user_id,
        "public_object_id": None,
        "usage_department_id": detail.usage_department_id,
        "location_id": location_id,
    }


def _public_snapshot_target(detail: AssetUsageRequest) -> dict[str, object]:
    return {
        "status": AssetStatus.IN_USE.value,
        "usage_type": UsageType.PUBLIC.value,
        "holder_user_id": None,
        "public_object_id": detail.target_public_object_id,
        "usage_department_id": None,
        "location_id": detail.target_location_id,
    }


def _require_snapshot_consistency(
    operation: OperationRequest,
    detail: AssetUsageRequest,
    operation_type: str,
    snapshots: list[OperationRequestAsset],
) -> None:
    if not snapshots:
        raise BusinessException("领用申请资产目标快照不存在")
    for snapshot in snapshots:
        expected = (
            _personal_snapshot_target(detail, snapshot.before_data)
            if operation_type == OperationType.PERSONAL_USE.value
            else _public_snapshot_target(detail)
        )
        if not _target_matches(snapshot.target_data, expected):
            raise BusinessException("领用申请详情与资产目标快照不匹配")


def _require_usage_detail(
    operation: OperationRequest,
    operation_type: str,
    *,
    detail: AssetUsageRequest | None = None,
    snapshots: list[OperationRequestAsset] | None = None,
) -> tuple[AssetUsageRequest, list[OperationRequestAsset]]:
    detail_row = (
        asset_usage_request_repository.find_by_operation(operation.id)
        if detail is None
        else detail
    )
    if detail_row is None:
        raise BusinessException("领用申请详情不存在")
    if operation.operation_type != operation_type:
        raise BusinessException("领用申请类型与详情不匹配")
    mode = _usage_mode(detail_row)
    if mode not in {UsageMode.USE.value, UsageMode.BORROW.value}:
        raise BusinessException("领用申请使用模式无效")
    if mode == UsageMode.BORROW.value:
        if not isinstance(detail_row.expected_return_at, datetime):
            raise BusinessException("借用申请预计归还时间无效")
    elif detail_row.expected_return_at is not None:
        raise BusinessException("普通领用不能填写预计归还时间")
    if operation_type == OperationType.PERSONAL_USE.value:
        valid = (
            detail_row.target_user_id is not None
            and detail_row.target_public_object_id is None
            and detail_row.usage_department_id is not None
        )
    else:
        valid = (
            detail_row.target_user_id is None
            and detail_row.target_public_object_id is not None
            and detail_row.usage_department_id is None
            and detail_row.target_location_id is not None
        )
    if not valid:
        raise BusinessException("领用申请类型与详情不匹配")
    validate_user_snapshot(
        detail_row.target_user_snapshot,
        detail_row.target_user_id,
        "领用人",
    )
    validate_named_snapshot(
        detail_row.usage_department_snapshot,
        detail_row.usage_department_id,
        "使用部门",
    )
    validate_named_snapshot(
        detail_row.target_public_object_snapshot,
        detail_row.target_public_object_id,
        "公共领用对象",
    )
    validate_named_snapshot(
        detail_row.target_location_snapshot,
        detail_row.target_location_id,
        "统一目标地点",
    )
    validate_named_snapshot(
        detail_row.requested_category_snapshot,
        detail_row.requested_category_id,
        "申请资产类别",
    )
    snapshot_rows = operation_assets(operation.id) if snapshots is None else snapshots
    _require_snapshot_consistency(
        operation,
        detail_row,
        operation_type,
        snapshot_rows,
    )
    return detail_row, snapshot_rows


def _serialize(
    operation: OperationRequest,
    actor_id: int,
    operation_type: str,
    *,
    detail: AssetUsageRequest | None = None,
    snapshots: list[OperationRequestAsset] | None = None,
    can_view_amount: bool | None = None,
) -> dict[str, Any]:
    detail_row, snapshot_rows = _require_usage_detail(
        operation,
        operation_type,
        detail=detail,
        snapshots=snapshots,
    )
    hide_asset_codes = (
        detail_row.requested_category_id is not None
        and operation.applicant_id == actor_id
        and not permission_service.has_permission(actor_id, _MANAGE_USAGE_PERMISSION)
    )
    serialized = serialize_operation(
        operation,
        actor_id,
        feature_data=_feature_data(detail_row, operation),
        assets=snapshot_rows,
        can_view_amount=can_view_amount,
        include_asset_codes=not hide_asset_codes,
    )
    serialized.update(
        {
            "fulfillment_status": detail_row.fulfillment_status,
            "issued_by": detail_row.issued_by,
            "issued_at": (
                isoformat_utc(detail_row.issued_at)
                if detail_row.issued_at is not None
                else None
            ),
            "issue_remark": detail_row.issue_remark,
            "signed_by": detail_row.signed_by,
            "signed_at": (
                isoformat_utc(detail_row.signed_at)
                if detail_row.signed_at is not None
                else None
            ),
            "sign_remark": detail_row.sign_remark,
            "return_requested_by": detail_row.return_requested_by,
            "return_requested_at": (
                isoformat_utc(detail_row.return_requested_at)
                if detail_row.return_requested_at is not None
                else None
            ),
            "return_request_reason": detail_row.return_request_reason,
        }
    )
    return serialized


def _serialize_or_recover_direct_usage(
    operation: OperationRequest,
    actor_id: int,
    operation_type: str,
) -> dict[str, Any]:
    operation_id = operation.id
    _serialize(operation, actor_id, operation_type)
    db.session.rollback()
    db.session.remove()
    reloaded = operation_request_repository.find_for_update(operation_id)
    if reloaded is None:
        raise BusinessException("领用申请不存在", result_code=ResultCode.NOT_FOUND)
    operation = reloaded
    serialized = _serialize(operation, actor_id, operation_type)
    if (
        operation.approval_channel == ApprovalChannel.DIRECT.value
        and operation.approval_execution_mode
        == ApprovalExecutionMode.AUTO_ON_APPROVAL.value
        and operation.approval_status == ApprovalStatus.APPROVED.value
        and operation.execution_status == ExecutionStatus.NOT_STARTED.value
    ):
        operation = operation_executor.execute_after_approval(operation.id, actor_id)
        return _serialize(operation, actor_id, operation_type)
    db.session.rollback()
    db.session.remove()
    return serialized


def _replay(
    actor_id: int,
    operation_type: str,
    idempotency_key: str | None,
) -> dict[str, Any] | None:
    if idempotency_key is None:
        return None
    operation = operation_service.get_by_idempotency_key(
        actor_id,
        operation_type,
        idempotency_key,
    )
    if operation is None:
        return None
    if operation.approval_channel == ApprovalChannel.DIRECT.value:
        return _serialize_or_recover_direct_usage(operation, actor_id, operation_type)
    return _serialize(operation, actor_id, operation_type)


def get(operation_request_id: int, actor_id: int) -> dict[str, Any]:
    can_manage = permission_service.has_permission(actor_id, _MANAGE_USAGE_PERMISSION)
    organization_ids = permission_service.accessible_organization_ids(actor_id)
    can_view_amount = permission_service.has_permission(actor_id, "asset:amount:view")
    visible = asset_usage_request_repository.find_visible_usage(
        operation_request_id=operation_request_id,
        actor_id=actor_id,
        can_manage=can_manage,
        organization_ids=organization_ids,
    )
    if visible is None:
        raise BusinessException(
            "无权查看或领用申请不存在",
            result_code=ResultCode.FORBIDDEN,
        )
    operation, detail = visible
    snapshots = find_operation_assets((operation.id,))
    return _serialize(
        operation,
        actor_id,
        operation.operation_type,
        detail=detail,
        snapshots=snapshots,
        can_view_amount=can_view_amount,
    )


def page(*, actor_id: int, page_index: int, size: int) -> PageResult:
    can_manage = permission_service.has_permission(actor_id, _MANAGE_USAGE_PERMISSION)
    organization_ids = permission_service.accessible_organization_ids(actor_id)
    can_view_amount = permission_service.has_permission(actor_id, "asset:amount:view")
    result = asset_usage_request_repository.page_usage(
        actor_id=actor_id,
        can_manage=can_manage,
        organization_ids=organization_ids,
        page=page_index,
        size=size,
    )
    snapshots_by_operation_id: dict[int, list[OperationRequestAsset]] = {}
    for snapshot in find_operation_assets(
        [operation.id for operation, _detail in result.items]
    ):
        snapshots_by_operation_id.setdefault(
            snapshot.operation_request_id,
            [],
        ).append(snapshot)
    return PageResult(
        items=[
            _serialize(
                operation,
                actor_id,
                operation.operation_type,
                detail=detail,
                snapshots=snapshots_by_operation_id.get(operation.id, []),
                can_view_amount=can_view_amount,
            )
            for operation, detail in result.items
        ],
        total=result.total,
        page=result.page,
        size=result.size,
    )


def self_service_references(actor_id: int) -> dict[str, list[dict[str, Any]]]:
    """Return references that an employee needs to submit a self-service request."""

    permission_service.require_permission(actor_id, _SELF_USAGE_PERMISSION)
    asset_join = (
        (Asset.category_id == AssetCategory.id)
        & (Asset.status == AssetStatus.IDLE.value)
        & Asset.parent_asset_id.is_(None)
    )
    categories = db.session.execute(
        select(
            AssetCategory.id,
            AssetCategory.code,
            AssetCategory.name,
            func.count(Asset.id).label("available_quantity"),
        )
        .outerjoin(
            Asset,
            asset_join,
        )
        .where(AssetCategory.status == "ENABLED")
        .group_by(AssetCategory.id, AssetCategory.code, AssetCategory.name)
        .having(func.count(Asset.id) > 0)
        .order_by(AssetCategory.name.asc(), AssetCategory.id.asc())
    ).all()
    locations = db.session.scalars(
        select(AssetLocation)
        .where(
            AssetLocation.status == "ENABLED",
            AssetLocation.is_selectable.is_(True),
        )
        .order_by(AssetLocation.name.asc(), AssetLocation.id.asc())
    ).all()
    return {
        "categories": [
            {
                "id": row.id,
                "code": row.code,
                "name": row.name,
                "available_quantity": int(row.available_quantity),
            }
            for row in categories
        ],
        "locations": [
            {"id": location.id, "code": location.code, "name": location.name}
            for location in locations
        ],
    }


def my_assets(actor_id: int) -> list[dict[str, Any]]:
    """Return the employee's current personal assets with borrowing metadata."""

    if not (
        permission_service.has_permission(actor_id, _SELF_USAGE_PERMISSION)
        or permission_service.has_permission(actor_id, "asset:return:self")
    ):
        raise BusinessException("无操作权限", result_code=ResultCode.FORBIDDEN)
    assets = list(
        db.session.scalars(
            select(Asset)
            .where(
                Asset.status == AssetStatus.IN_USE.value,
                Asset.usage_type == UsageType.PERSONAL.value,
                Asset.holder_user_id == actor_id,
                Asset.parent_asset_id.is_(None),
            )
            .order_by(Asset.asset_code.asc(), Asset.id.asc())
        ).all()
    )
    asset_ids = [asset.id for asset in assets]
    usage_by_asset_id: dict[int, AssetUsageRequest] = {}
    if asset_ids:
        usage_rows = db.session.execute(
            select(OperationRequestAsset.asset_id, AssetUsageRequest)
            .join(
                OperationRequest,
                OperationRequest.id == OperationRequestAsset.operation_request_id,
            )
            .join(
                AssetUsageRequest,
                AssetUsageRequest.operation_request_id == OperationRequest.id,
            )
            .where(
                OperationRequestAsset.asset_id.in_(asset_ids),
                OperationRequest.operation_type == OperationType.PERSONAL_USE.value,
                OperationRequest.execution_status == ExecutionStatus.SUCCESS.value,
                AssetUsageRequest.target_user_id == actor_id,
            )
            .order_by(OperationRequest.id.desc())
        ).all()
        for asset_id, detail in usage_rows:
            usage_by_asset_id.setdefault(asset_id, detail)
    location_ids = {
        asset.location_id for asset in assets if asset.location_id is not None
    }
    location_names = {
        location.id: location.name
        for location in db.session.scalars(
            select(AssetLocation).where(AssetLocation.id.in_(location_ids))
        ).all()
    }
    result: list[dict[str, Any]] = []
    for asset in assets:
        detail = usage_by_asset_id.get(asset.id)
        expected_return_at = detail.expected_return_at if detail is not None else None
        result.append(
            {
                "id": asset.id,
                "asset_code": asset.asset_code,
                "asset_name": asset.asset_name,
                "status": asset.status,
                "location_id": asset.location_id,
                "location_name": (
                    location_names.get(asset.location_id)
                    if asset.location_id is not None
                    else None
                ),
                "usage_mode": (
                    _usage_mode(detail) if detail is not None else UsageMode.USE.value
                ),
                "expected_return_at": (
                    isoformat_utc(expected_return_at)
                    if expected_return_at is not None
                    else None
                ),
            }
        )
    return result


def _submit_personal(
    payload: dict[str, Any],
    actor_id: int,
    *,
    usage_mode: str,
    self_service: bool = False,
    direct: bool = False,
) -> dict[str, Any]:
    if self_service:
        permission_service.require_permission(actor_id, _SELF_USAGE_PERMISSION)
    else:
        permission_service.require_permission(actor_id, _MANAGE_USAGE_PERMISSION)
    expected_return_at = payload.get("expected_return_at")
    if usage_mode == UsageMode.BORROW.value:
        if not isinstance(expected_return_at, datetime):
            raise BusinessException(
                "借用必须填写预计归还时间", result_code=ResultCode.BAD_REQUEST
            )
        if normalize_utc(expected_return_at) <= datetime.now(timezone.utc):
            raise BusinessException(
                "预计归还时间必须晚于当前时间", result_code=ResultCode.BAD_REQUEST
            )
    elif expected_return_at is not None:
        raise BusinessException(
            "普通领用不能填写预计归还时间", result_code=ResultCode.BAD_REQUEST
        )
    if not self_service:
        if payload.get("asset_ids") is None:
            raise BusinessException(
                "管理员领用必须选择具体资产",
                result_code=ResultCode.BAD_REQUEST,
            )
        if payload.get("category_id") is not None:
            raise BusinessException(
                "管理员领用不能同时选择资产类别",
                result_code=ResultCode.BAD_REQUEST,
            )
        if payload.get("requested_quantity") is not None:
            raise BusinessException(
                "管理员领用不能按类别填写申请数量",
                result_code=ResultCode.BAD_REQUEST,
            )

    idempotency_key = _idempotency_key(payload)
    replayed = _replay(
        actor_id,
        OperationType.PERSONAL_USE.value,
        idempotency_key,
    )
    if replayed is not None:
        return replayed

    target_user_id = payload.get("target_user_id")
    if self_service:
        if target_user_id is not None and target_user_id != actor_id:
            raise BusinessException(
                "员工自助申请只能为本人申请",
                result_code=ResultCode.FORBIDDEN,
            )
        target_user_id = actor_id
    if target_user_id is None:
        raise BusinessException("领用人不能为空", result_code=ResultCode.BAD_REQUEST)
    target_user = require_personal_target(target_user_id)

    requested_category_id = payload.get("category_id")
    requested_category = None
    if requested_category_id is not None:
        requested_category = db.session.get(AssetCategory, requested_category_id)
        if requested_category is None or requested_category.status != "ENABLED":
            raise BusinessException("申请资产类别不存在或已停用")
        requested_quantity = payload.get("requested_quantity")
        if not isinstance(requested_quantity, int) or requested_quantity < 1:
            raise BusinessException(
                "按资产类别申请时必须填写有效数量",
                result_code=ResultCode.BAD_REQUEST,
            )
        asset_rows = list(
            db.session.scalars(
                select(Asset)
                .where(
                    Asset.category_id == requested_category.id,
                    Asset.status == AssetStatus.IDLE.value,
                    Asset.parent_asset_id.is_(None),
                )
                .order_by(Asset.id.asc())
                .limit(requested_quantity)
            ).all()
        )
        if len(asset_rows) != requested_quantity:
            raise BusinessException(
                f"该类别当前仅有 {len(asset_rows)} 件可领用资产，无法满足申请数量",
                result_code=ResultCode.BAD_REQUEST,
            )
        assets = expand_assets([asset.id for asset in asset_rows])
    else:
        asset_ids = payload.get("asset_ids")
        if asset_ids is None:
            raise BusinessException(
                "请选择具体资产或资产类别",
                result_code=ResultCode.BAD_REQUEST,
            )
        assets = expand_assets(asset_ids)
    if not self_service:
        require_assets_in_scope(actor_id, assets)
    require_idle_assets(assets)
    usage_department = (
        organization_service.require_enabled(target_user.organization_id)
        if target_user.organization_id is not None
        else None
    )
    target_location_id = payload.get("location_id")
    target_location = None
    if target_location_id is not None:
        target_location = require_location(target_location_id)
    else:
        retained_location_ids = {asset.location_id for asset in assets}
        if None in retained_location_ids:
            raise BusinessException("存放地点不存在或已停用")
        for retained_location_id in sorted(
            location_id
            for location_id in retained_location_ids
            if location_id is not None
        ):
            require_location(retained_location_id)

    target_data_by_asset_id = {
        asset.id: {
            "status": AssetStatus.IN_USE.value,
            "usage_type": UsageType.PERSONAL.value,
            "holder_user_id": target_user.id,
            "public_object_id": None,
            "usage_department_id": (
                target_user.organization_id if usage_department is not None else None
            ),
            "location_id": target_location_id or asset.location_id,
        }
        for asset in assets
    }
    created = operation_service.create_request(
        operation_type=OperationType.PERSONAL_USE.value,
        applicant_id=actor_id,
        approval_channel=(
            ApprovalChannel.DIRECT.value if direct else ApprovalChannel.INTERNAL.value
        ),
        approval_execution_mode=(
            ApprovalExecutionMode.AUTO_ON_APPROVAL.value
            if direct
            else ApprovalExecutionMode.MANUAL_CONFIRM.value
        ),
        assets=assets,
        target_data_by_asset_id=target_data_by_asset_id,
        idempotency_key=idempotency_key,
    )
    if not created.created:
        if direct:
            return _serialize_or_recover_direct_usage(
                created.operation,
                actor_id,
                OperationType.PERSONAL_USE.value,
            )
        return _serialize(
            created.operation,
            actor_id,
            OperationType.PERSONAL_USE.value,
        )

    asset_usage_request_repository.add(
        AssetUsageRequest(
            operation_request_id=created.operation.id,
            target_user_id=target_user.id,
            target_public_object_id=None,
            usage_department_id=(
                target_user.organization_id if usage_department is not None else None
            ),
            target_location_id=target_location_id,
            usage_mode=usage_mode,
            expected_return_at=expected_return_at,
            target_user_snapshot=build_user_snapshot(target_user),
            usage_department_snapshot=(
                build_named_snapshot(usage_department)
                if usage_department is not None
                else None
            ),
            target_public_object_snapshot=None,
            target_location_snapshot=(
                build_named_snapshot(target_location)
                if target_location is not None
                else None
            ),
            requested_category_id=(
                requested_category.id if requested_category is not None else None
            ),
            requested_quantity=(
                payload.get("requested_quantity")
                if requested_category is not None
                else None
            ),
            requested_category_snapshot=(
                build_named_snapshot(requested_category)
                if requested_category is not None
                else None
            ),
            reason=payload.get("reason"),
            fulfillment_status=(
                FulfillmentStatus.COMPLETED.value
                if direct
                else FulfillmentStatus.PENDING_ISSUE.value
            ),
            issued_by=actor_id if direct else None,
            issued_at=utc_now() if direct else None,
            issue_remark="管理员直接领用" if direct else None,
        )
    )
    if direct:
        operation = approval_provider_service.confirm_direct(
            created.operation.id,
            actor_id,
        )
    else:
        _initialize_internal_approval(created.operation, assets)
        operation = created.operation
    return _serialize(operation, actor_id, OperationType.PERSONAL_USE.value)


def _submit_public(
    payload: dict[str, Any], actor_id: int, *, usage_mode: str
) -> dict[str, Any]:
    """Submit a public usage request.

    Managers keep the existing direct-fulfillment behavior. Employees with
    self-service permission may propose the same workflow, but their request
    must wait for approval before assets are reassigned.
    """
    _require_clean_entry_unit_of_work()
    can_manage_usage = permission_service.has_permission(
        actor_id, _MANAGE_USAGE_PERMISSION
    )
    if can_manage_usage:
        permission_service.require_permission(actor_id, _MANAGE_USAGE_PERMISSION)
    else:
        permission_service.require_permission(actor_id, _SELF_USAGE_PERMISSION)
    expected_return_at = payload.get("expected_return_at")
    if usage_mode == UsageMode.BORROW.value:
        if not isinstance(expected_return_at, datetime):
            raise BusinessException(
                "借用必须填写预计归还时间", result_code=ResultCode.BAD_REQUEST
            )
        if normalize_utc(expected_return_at) <= datetime.now(timezone.utc):
            raise BusinessException(
                "预计归还时间必须晚于当前时间", result_code=ResultCode.BAD_REQUEST
            )
    elif expected_return_at is not None:
        raise BusinessException(
            "普通领用不能填写预计归还时间", result_code=ResultCode.BAD_REQUEST
        )
    idempotency_key = _idempotency_key(payload)
    replayed = _replay(
        actor_id,
        OperationType.PUBLIC_USE.value,
        idempotency_key,
    )
    if replayed is not None:
        return replayed

    assets = expand_assets(payload["asset_ids"])
    require_assets_in_scope(actor_id, assets)
    require_idle_assets(assets)
    public_object = require_public_target(payload["public_object_id"])
    location_id = payload.get("location_id")
    if location_id is None:
        raise BusinessException(
            "公共领用必须选择存放地点",
            result_code=ResultCode.BAD_REQUEST,
        )
    location = require_location(location_id)

    target_data_by_asset_id = {
        asset.id: {
            "status": AssetStatus.IN_USE.value,
            "usage_type": UsageType.PUBLIC.value,
            "holder_user_id": None,
            "public_object_id": public_object.id,
            "usage_department_id": None,
            "location_id": location_id,
        }
        for asset in assets
    }
    created = operation_service.create_request(
        operation_type=OperationType.PUBLIC_USE.value,
        applicant_id=actor_id,
        approval_channel=(
            ApprovalChannel.DIRECT.value
            if can_manage_usage
            else ApprovalChannel.INTERNAL.value
        ),
        approval_execution_mode=(
            ApprovalExecutionMode.AUTO_ON_APPROVAL.value
            if can_manage_usage
            else ApprovalExecutionMode.MANUAL_CONFIRM.value
        ),
        assets=assets,
        target_data_by_asset_id=target_data_by_asset_id,
        idempotency_key=idempotency_key,
    )
    if not created.created:
        return _serialize_or_recover_direct_usage(
            created.operation,
            actor_id,
            OperationType.PUBLIC_USE.value,
        )

    asset_usage_request_repository.add(
        AssetUsageRequest(
            operation_request_id=created.operation.id,
            target_user_id=None,
            target_public_object_id=public_object.id,
            usage_department_id=None,
            target_location_id=location_id,
            usage_mode=usage_mode,
            expected_return_at=expected_return_at,
            target_user_snapshot=None,
            usage_department_snapshot=None,
            target_public_object_snapshot=build_named_snapshot(public_object),
            target_location_snapshot=build_named_snapshot(location),
        )
    )
    if can_manage_usage:
        operation = approval_provider_service.confirm_direct(
            created.operation.id,
            actor_id,
        )
    else:
        _initialize_internal_approval(created.operation, assets)
        operation = created.operation
    return _serialize(operation, actor_id, OperationType.PUBLIC_USE.value)


def submit_personal(payload: dict[str, Any], actor_id: int) -> dict[str, Any]:
    return _submit_personal(payload, actor_id, usage_mode=UsageMode.USE.value)


def submit_personal_direct(payload: dict[str, Any], actor_id: int) -> dict[str, Any]:
    return _submit_personal(
        payload,
        actor_id,
        usage_mode=UsageMode.USE.value,
        direct=True,
    )


def submit_personal_self(payload: dict[str, Any], actor_id: int) -> dict[str, Any]:
    return _submit_personal(
        payload,
        actor_id,
        usage_mode=UsageMode.USE.value,
        self_service=True,
    )


def submit_personal_borrow_self(
    payload: dict[str, Any], actor_id: int
) -> dict[str, Any]:
    return _submit_personal(
        payload,
        actor_id,
        usage_mode=UsageMode.BORROW.value,
        self_service=True,
    )


def submit_public(payload: dict[str, Any], actor_id: int) -> dict[str, Any]:
    return _submit_public(payload, actor_id, usage_mode=UsageMode.USE.value)


def submit_personal_borrow(payload: dict[str, Any], actor_id: int) -> dict[str, Any]:
    return _submit_personal(payload, actor_id, usage_mode=UsageMode.BORROW.value)


def submit_personal_borrow_direct(
    payload: dict[str, Any], actor_id: int
) -> dict[str, Any]:
    return _submit_personal(
        payload,
        actor_id,
        usage_mode=UsageMode.BORROW.value,
        direct=True,
    )


def submit_public_borrow(payload: dict[str, Any], actor_id: int) -> dict[str, Any]:
    return _submit_public(payload, actor_id, usage_mode=UsageMode.BORROW.value)


__all__ = [
    "get",
    "my_assets",
    "page",
    "self_service_references",
    "submit_personal",
    "submit_personal_borrow",
    "submit_personal_borrow_direct",
    "submit_personal_direct",
    "submit_personal_borrow_self",
    "submit_personal_self",
    "submit_public",
    "submit_public_borrow",
]
