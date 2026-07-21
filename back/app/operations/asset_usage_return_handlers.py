"""Execution handlers for personal and public asset usage."""

from __future__ import annotations

from dataclasses import dataclass

from app.common import BusinessException, ResultCode
from app.enums import AssetStatus, OperationType, UsageType
from app.models import Asset, OperationRequest, OperationRequestAsset
from app.models.asset_usage_return import AssetUsageRequest
from app.repositories.asset_repository import asset_repository
from app.repositories.asset_usage_return_repository import (
    asset_usage_request_repository,
)
from app.repositories.operation_repository import operation_request_asset_repository
from app.repositories.workflow_repository import operation_request_repository
from app.services import audit_service
from app.services.asset_usage_return_support import (
    require_location,
    require_personal_target,
    require_public_target,
)

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


@dataclass(frozen=True)
class _ExecutionContext:
    operation: OperationRequest
    detail: AssetUsageRequest
    snapshots: list[OperationRequestAsset]
    assets: list[Asset]


def _require_operation(operation_request_id: int) -> OperationRequest:
    operation = operation_request_repository.get(operation_request_id)
    if operation is None:
        raise BusinessException(
            "领用申请不存在",
            result_code=ResultCode.NOT_FOUND,
        )
    return operation


def _require_detail(operation_request_id: int) -> AssetUsageRequest:
    detail = asset_usage_request_repository.find_by_operation(operation_request_id)
    if detail is None:
        raise BusinessException("领用申请详情不存在")
    return detail


def _personal_target(
    detail: AssetUsageRequest,
    snapshot: OperationRequestAsset,
) -> dict[str, object]:
    if (
        detail.target_user_id is None
        or detail.target_public_object_id is not None
        or detail.usage_department_id is None
    ):
        raise BusinessException("个人领用申请详情不匹配")
    location_id = detail.target_location_id
    if location_id is None:
        if not isinstance(snapshot.before_data, dict):
            raise BusinessException("个人领用资产留用地点快照不匹配")
        location_id = snapshot.before_data.get("location_id")
        if type(location_id) is not int:
            raise BusinessException("个人领用资产留用地点快照不匹配")
    return {
        "status": AssetStatus.IN_USE.value,
        "usage_type": UsageType.PERSONAL.value,
        "holder_user_id": detail.target_user_id,
        "public_object_id": None,
        "usage_department_id": detail.usage_department_id,
        "location_id": location_id,
    }


def _public_target(detail: AssetUsageRequest) -> dict[str, object]:
    if (
        detail.target_user_id is not None
        or detail.target_public_object_id is None
        or detail.usage_department_id is not None
        or detail.target_location_id is None
    ):
        raise BusinessException("公共领用申请详情不匹配")
    return {
        "status": AssetStatus.IN_USE.value,
        "usage_type": UsageType.PUBLIC.value,
        "holder_user_id": None,
        "public_object_id": detail.target_public_object_id,
        "usage_department_id": None,
        "location_id": detail.target_location_id,
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


def _validate_target(
    operation_type: str,
    detail: AssetUsageRequest,
    snapshot: OperationRequestAsset,
) -> dict[str, object]:
    target = snapshot.target_data
    if not isinstance(target, dict) or set(target) != _TARGET_FIELDS:
        raise BusinessException("领用资产目标快照字段不匹配")
    expected = (
        _personal_target(detail, snapshot)
        if operation_type == OperationType.PERSONAL_USE.value
        else _public_target(detail)
    )
    if not _target_matches(target, expected):
        raise BusinessException("领用资产目标快照与申请详情不匹配")
    return expected


def _canonical_before_data(asset: Asset) -> dict[str, object]:
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


def _validate_asset_snapshot(
    asset: Asset,
    snapshot: OperationRequestAsset,
) -> dict[str, object]:
    if not _same_scalar(snapshot.asset_status_snapshot, asset.status):
        raise BusinessException("领用资产状态快照与当前数据不匹配")
    if not _same_scalar(snapshot.organization_id_snapshot, asset.organization_id):
        raise BusinessException("领用资产组织快照与当前数据不匹配")
    if not _same_scalar(snapshot.asset_version_snapshot, asset.version):
        raise BusinessException("领用资产版本已变化")

    canonical = _canonical_before_data(asset)
    before_data = snapshot.before_data
    if not isinstance(before_data, dict) or any(
        key not in before_data or not _same_scalar(before_data[key], value)
        for key, value in canonical.items()
    ):
        raise BusinessException("领用资产操作前快照与当前数据不匹配")

    holder_snapshot = snapshot.holder_snapshot
    if holder_snapshot is None:
        if asset.holder_user_id is not None:
            raise BusinessException("领用资产持有人快照与当前数据不匹配")
    elif (
        not isinstance(holder_snapshot, dict)
        or asset.holder_user_id is None
        or not _same_scalar(holder_snapshot.get("id"), asset.holder_user_id)
    ):
        raise BusinessException("领用资产持有人快照与当前数据不匹配")

    location_snapshot = snapshot.location_snapshot
    if location_snapshot is not None and (
        not isinstance(location_snapshot, dict)
        or not _same_scalar(location_snapshot.get("id"), asset.location_id)
    ):
        raise BusinessException("领用资产地点快照与当前数据不匹配")
    return canonical


def _validate_current_feature_target(
    operation_type: str,
    detail: AssetUsageRequest,
    targets: list[dict[str, object]],
) -> None:
    if operation_type == OperationType.PERSONAL_USE.value:
        if detail.target_user_id is None:
            raise BusinessException("个人领用申请详情不匹配")
        target_user = require_personal_target(detail.target_user_id)
        if target_user.organization_id != detail.usage_department_id:
            raise BusinessException("领用人当前部门与申请快照不匹配")
    else:
        if detail.target_public_object_id is None or detail.target_location_id is None:
            raise BusinessException("公共领用申请详情不匹配")
        require_public_target(detail.target_public_object_id)
        require_location(detail.target_location_id)

    for target in targets:
        location_id = target["location_id"]
        if type(location_id) is not int:
            raise BusinessException("领用资产目标地点快照不匹配")
        require_location(location_id)


def _load_context(
    operation_request_id: int,
    operation_type: str,
) -> _ExecutionContext:
    operation = _require_operation(operation_request_id)
    detail = _require_detail(operation.id)
    if operation.operation_type != operation_type:
        raise BusinessException("领用申请类型与处理器不匹配")

    snapshots = operation_request_asset_repository.find_by_request(operation.id)
    if not snapshots:
        raise BusinessException("领用申请未包含资产快照")
    snapshot_ids = [snapshot.asset_id for snapshot in snapshots]
    if snapshot_ids != sorted(set(snapshot_ids)):
        raise BusinessException("领用申请资产快照不完整")
    assets = asset_repository.find_many_for_update(snapshot_ids)
    if [asset.id for asset in assets] != snapshot_ids:
        raise BusinessException("领用申请资产与快照不一致")

    targets: list[dict[str, object]] = []
    for asset, snapshot in zip(assets, snapshots, strict=True):
        if asset.status != AssetStatus.IDLE.value:
            raise BusinessException("领用资产当前状态不是空闲")
        _validate_asset_snapshot(asset, snapshot)
        targets.append(_validate_target(operation_type, detail, snapshot))
    _validate_current_feature_target(operation_type, detail, targets)
    return _ExecutionContext(
        operation=operation,
        detail=detail,
        snapshots=snapshots,
        assets=assets,
    )


def _execute(operation_request_id: int, actor_id: int, operation_type: str) -> None:
    context = _load_context(operation_request_id, operation_type)
    asset_ids: list[int] = []
    for asset, snapshot in zip(context.assets, context.snapshots, strict=True):
        before_data = _canonical_before_data(asset)
        if not asset_repository.cas_update(
            snapshot.asset_id,
            snapshot.asset_version_snapshot,
            snapshot.target_data,
        ):
            raise BusinessException("资产版本冲突")
        after_data = {
            **before_data,
            **snapshot.target_data,
            "version": snapshot.asset_version_snapshot + 1,
        }
        audit_service.record_asset_lifecycle(
            asset_id=snapshot.asset_id,
            operation_type=operation_type,
            request_no=context.operation.request_no,
            actor_id=actor_id,
            before_data=before_data,
            after_data=after_data,
        )
        asset_ids.append(snapshot.asset_id)

    audit_service.record_operation(
        operation_request_id=context.operation.id,
        operation_type=operation_type,
        actor_id=actor_id,
        before_data={
            "asset_ids": asset_ids,
            "asset_count": len(asset_ids),
        },
        after_data={"result": "SUCCESS"},
    )


class PersonalUsageHandler:
    operation_type = OperationType.PERSONAL_USE.value
    safe_error_message = "个人领用执行失败，请联系管理员或稍后重试"

    def revalidate_for_execution(self, operation_request_id: int) -> None:
        _load_context(operation_request_id, self.operation_type)

    def execute(self, operation_request_id: int, actor_id: int) -> None:
        _execute(operation_request_id, actor_id, self.operation_type)


class PublicUsageHandler:
    operation_type = OperationType.PUBLIC_USE.value
    safe_error_message = "公共资产投入执行失败，请联系管理员或稍后重试"

    def revalidate_for_execution(self, operation_request_id: int) -> None:
        _load_context(operation_request_id, self.operation_type)

    def execute(self, operation_request_id: int, actor_id: int) -> None:
        _execute(operation_request_id, actor_id, self.operation_type)


__all__ = ["PersonalUsageHandler", "PublicUsageHandler"]
