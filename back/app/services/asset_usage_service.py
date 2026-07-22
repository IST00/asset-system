"""Personal and public asset-usage request orchestration."""

from __future__ import annotations

from typing import Any

from app.common import BusinessException, PageResult, ResultCode
from app.enums import (
    ApprovalChannel,
    ApprovalExecutionMode,
    AssetStatus,
    OperationType,
    UsageType,
)
from app.models import OperationRequest, OperationRequestAsset
from app.models.asset_usage_return import AssetUsageRequest
from app.repositories.asset_usage_return_repository import (
    asset_usage_request_repository,
    find_operation_assets,
)
from app.services import (
    approval_provider_service,
    operation_service,
    permission_service,
)
from app.services.asset_usage_return_support import (
    expand_assets,
    operation_assets,
    require_assets_in_scope,
    require_idle_assets,
    require_location,
    require_personal_target,
    require_public_target,
    serialize_operation,
)

_USAGE_PERMISSION = "asset:usage:manage"
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


def _feature_data(detail: AssetUsageRequest) -> dict[str, int | None]:
    return {
        "target_user_id": detail.target_user_id,
        "target_public_object_id": detail.target_public_object_id,
        "usage_department_id": detail.usage_department_id,
        "target_location_id": detail.target_location_id,
    }


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
    return serialize_operation(
        operation,
        actor_id,
        feature_data=_feature_data(detail_row),
        assets=snapshot_rows,
        can_view_amount=can_view_amount,
    )


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
    return _serialize(operation, actor_id, operation_type)


def get(operation_request_id: int, actor_id: int) -> dict[str, Any]:
    can_manage = permission_service.has_permission(actor_id, _USAGE_PERMISSION)
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
    can_manage = permission_service.has_permission(actor_id, _USAGE_PERMISSION)
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


def submit_personal(payload: dict[str, Any], actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, _USAGE_PERMISSION)
    idempotency_key = _idempotency_key(payload)
    replayed = _replay(
        actor_id,
        OperationType.PERSONAL_USE.value,
        idempotency_key,
    )
    if replayed is not None:
        return replayed

    assets = expand_assets(payload["asset_ids"])
    require_assets_in_scope(actor_id, assets)
    require_idle_assets(assets)
    target_user = require_personal_target(payload["target_user_id"])
    assert target_user.organization_id is not None
    target_location_id = payload.get("location_id")
    if target_location_id is not None:
        require_location(target_location_id)

    target_data_by_asset_id = {
        asset.id: {
            "status": AssetStatus.IN_USE.value,
            "usage_type": UsageType.PERSONAL.value,
            "holder_user_id": target_user.id,
            "public_object_id": None,
            "usage_department_id": target_user.organization_id,
            "location_id": target_location_id or asset.location_id,
        }
        for asset in assets
    }
    created = operation_service.create_request(
        operation_type=OperationType.PERSONAL_USE.value,
        applicant_id=actor_id,
        approval_channel=ApprovalChannel.FEISHU.value,
        approval_execution_mode=ApprovalExecutionMode.AUTO_ON_APPROVAL.value,
        assets=assets,
        target_data_by_asset_id=target_data_by_asset_id,
        idempotency_key=idempotency_key,
    )
    if not created.created:
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
            usage_department_id=target_user.organization_id,
            target_location_id=target_location_id,
        )
    )
    operation = approval_provider_service.submit(created.operation.id, actor_id)
    return _serialize(operation, actor_id, OperationType.PERSONAL_USE.value)


def submit_public(payload: dict[str, Any], actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, _USAGE_PERMISSION)
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
    require_location(location_id)

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
        approval_channel=ApprovalChannel.DIRECT.value,
        approval_execution_mode=ApprovalExecutionMode.AUTO_ON_APPROVAL.value,
        assets=assets,
        target_data_by_asset_id=target_data_by_asset_id,
        idempotency_key=idempotency_key,
    )
    if not created.created:
        return _serialize(
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
        )
    )
    operation = approval_provider_service.confirm_direct(created.operation.id, actor_id)
    return _serialize(operation, actor_id, OperationType.PUBLIC_USE.value)


__all__ = ["get", "page", "submit_personal", "submit_public"]
