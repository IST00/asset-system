"""Shared validation and serialization for asset usage and return services."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, TypeAlias

from app.common import BusinessException, ResultCode
from app.enums import AssetStatus, RecordStatus, UsageType
from app.extensions import db
from app.models import (
    Asset,
    AssetLocation,
    OperationRequest,
    OperationRequestAsset,
    Organization,
    PublicUsageObject,
    User,
)
from app.repositories.operation_repository import operation_request_asset_repository
from app.services import (
    asset_relation_service,
    master_data_service,
    organization_service,
    permission_service,
)


def expand_assets(asset_ids: Sequence[int]) -> list[Asset]:
    requested_ids = list(asset_ids)
    if not requested_ids:
        raise BusinessException("申请至少包含一项资产")
    requested_set = set(requested_ids)
    assets = asset_relation_service.expand_with_direct_children(requested_ids)
    for asset in assets:
        if (
            asset.id in requested_set
            and asset.parent_asset_id is not None
            and asset.parent_asset_id not in requested_set
        ):
            raise BusinessException("附属资产需先解除主附关系后再单独操作")
    return assets


def require_assets_in_scope(actor_id: int, assets: Sequence[Asset]) -> None:
    organization_ids = permission_service.accessible_organization_ids(actor_id)
    if organization_ids is None:
        return
    if any(asset.organization_id not in organization_ids for asset in assets):
        raise BusinessException(
            "无该组织的数据权限",
            result_code=ResultCode.FORBIDDEN,
        )


def require_idle_assets(assets: Sequence[Asset]) -> None:
    if any(asset.status != AssetStatus.IDLE.value for asset in assets):
        raise BusinessException("仅空闲资产可发起领用")


def require_personal_assets(assets: Sequence[Asset], holder_user_id: int) -> None:
    if any(
        asset.status != AssetStatus.IN_USE.value
        or asset.usage_type != UsageType.PERSONAL.value
        or asset.holder_user_id != holder_user_id
        or asset.public_object_id is not None
        for asset in assets
    ):
        raise BusinessException("资产不是当前用户持有的个人领用资产")


def require_public_assets(assets: Sequence[Asset]) -> None:
    if any(
        asset.status != AssetStatus.IN_USE.value
        or asset.usage_type != UsageType.PUBLIC.value
        or asset.public_object_id is None
        or asset.holder_user_id is not None
        for asset in assets
    ):
        raise BusinessException("资产不是有效的公共领用资产")


def require_personal_target(user_id: int) -> User:
    user = db.session.get(User, user_id)
    if user is None or not user.enabled or user.organization_id is None:
        raise BusinessException("领用人不存在、已停用或未归属部门")
    organization_service.require_enabled(user.organization_id)
    return user


def require_public_target(public_object_id: int) -> PublicUsageObject:
    public_object = db.session.get(PublicUsageObject, public_object_id)
    if public_object is None or public_object.status != RecordStatus.ENABLED.value:
        raise BusinessException("公共领用对象不存在或已停用")
    return public_object


def require_location(location_id: int) -> AssetLocation:
    return master_data_service.require_selectable_location(location_id)


def build_user_snapshot(user: User) -> dict[str, str | int]:
    return {
        "id": user.id,
        "username": user.username,
        "name": user.nickname or user.username,
    }


def build_named_snapshot(
    value: Organization | PublicUsageObject | AssetLocation,
) -> dict[str, str | int]:
    return {"id": value.id, "code": value.code, "name": value.name}


def validate_user_snapshot(
    value: object,
    expected_id: int | None,
    label: str,
) -> dict[str, str | int] | None:
    if expected_id is None:
        if value is not None:
            raise BusinessException(f"{label}快照与关联标识不匹配")
        return None
    if (
        not isinstance(value, dict)
        or set(value) != {"id", "username", "name"}
        or type(value["id"]) is not int
        or value["id"] != expected_id
        or not isinstance(value["username"], str)
        or not isinstance(value["name"], str)
    ):
        raise BusinessException(f"{label}快照与关联标识不匹配")
    return {
        "id": value["id"],
        "username": value["username"],
        "name": value["name"],
    }


def validate_named_snapshot(
    value: object,
    expected_id: int | None,
    label: str,
) -> dict[str, str | int] | None:
    if expected_id is None:
        if value is not None:
            raise BusinessException(f"{label}快照与关联标识不匹配")
        return None
    if (
        not isinstance(value, dict)
        or set(value) != {"id", "code", "name"}
        or type(value["id"]) is not int
        or value["id"] != expected_id
        or not isinstance(value["code"], str)
        or not isinstance(value["name"], str)
    ):
        raise BusinessException(f"{label}快照与关联标识不匹配")
    return {
        "id": value["id"],
        "code": value["code"],
        "name": value["name"],
    }


def operation_assets(operation_request_id: int) -> list[OperationRequestAsset]:
    return operation_request_asset_repository.find_by_request(operation_request_id)


_AMOUNT_KEYS = {
    "amount",
    "original_amount",
    "repair_cost",
    "scrap_amount",
}

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | dict[str, "JsonValue"] | list["JsonValue"]


def _normalize_json(
    value: object,
    can_view_amount: bool,
    *,
    path: str = "$",
) -> JsonValue:
    """Deep-copy a JSON DTO, rejecting tuples and arbitrary object leaves."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        result: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(
                    f"unsupported JSON object key at {path}: {type(key).__name__}"
                )
            if not can_view_amount and key in _AMOUNT_KEYS:
                continue
            result[key] = _normalize_json(
                item,
                can_view_amount,
                path=f"{path}.{key}",
            )
        return result
    if isinstance(value, list):
        return [
            _normalize_json(
                item,
                can_view_amount,
                path=f"{path}[{index}]",
            )
            for index, item in enumerate(value)
        ]
    raise TypeError(f"unsupported JSON value at {path}: {type(value).__name__}")


def serialize_operation(
    operation: OperationRequest,
    actor_id: int,
    *,
    feature_data: Mapping[str, JsonValue] | None = None,
    allowed_actions: Sequence[str] = (),
    assets: Sequence[OperationRequestAsset] | None = None,
    can_view_amount: bool | None = None,
) -> dict[str, Any]:
    """Build an authorized DTO; JSON arrays must be lists, never tuples."""
    include_amount = (
        permission_service.has_permission(actor_id, "asset:amount:view")
        if can_view_amount is None
        else can_view_amount
    )
    snapshot_rows = operation_assets(operation.id) if assets is None else assets
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
        "external_instance_id": operation.external_instance_id,
        "submitted_at": operation.submitted_at,
        "approved_at": operation.approved_at,
        "executed_at": operation.executed_at,
        "terminated_at": operation.terminated_at,
        "terminated_by": operation.terminated_by,
        "termination_reason": operation.termination_reason,
        "created_at": operation.created_at,
        "updated_at": operation.updated_at,
        "assets": [
            {
                "asset_id": item.asset_id,
                "asset_code": item.asset_code_snapshot,
                "asset_name": item.asset_name_snapshot,
                "asset_status": item.asset_status_snapshot,
                "asset_version": item.asset_version_snapshot,
                "organization_id": item.organization_id_snapshot,
                "holder_snapshot": _normalize_json(
                    item.holder_snapshot,
                    include_amount,
                ),
                "location_snapshot": _normalize_json(
                    item.location_snapshot,
                    include_amount,
                ),
                "before_data": _normalize_json(
                    item.before_data,
                    include_amount,
                ),
                "target_data": _normalize_json(
                    item.target_data,
                    include_amount,
                ),
            }
            for item in snapshot_rows
        ],
        "feature": _normalize_json(feature_data or {}, include_amount),
        "allowed_actions": list(allowed_actions),
    }


__all__ = [
    "build_named_snapshot",
    "build_user_snapshot",
    "expand_assets",
    "operation_assets",
    "require_assets_in_scope",
    "require_idle_assets",
    "require_location",
    "require_personal_assets",
    "require_personal_target",
    "require_public_assets",
    "require_public_target",
    "serialize_operation",
    "validate_named_snapshot",
    "validate_user_snapshot",
]
