"""Personal and public asset-return request orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from app.common import BusinessException, ResultCode
from app.enums import (
    ApprovalChannel,
    ApprovalExecutionMode,
    ApprovalStatus,
    AssetStatus,
    ExecutionStatus,
    OperationType,
    UsageType,
)
from app.extensions import db
from app.models import (
    OperationActionIdempotency,
    OperationRequest,
    OperationRequestAsset,
)
from app.models.asset_usage_return import AssetReturnItem, AssetReturnRequest
from app.models.mixins import utc_now
from app.repositories.asset_usage_return_repository import (
    asset_return_item_repository,
    asset_return_request_repository,
)
from app.repositories.operation_repository import (
    operation_action_idempotency_repository,
)
from app.repositories.workflow_repository import operation_request_repository
from app.services import (
    approval_provider_service,
    operation_executor,
    operation_service,
    permission_service,
)
from app.services.asset_usage_return_support import (
    expand_assets,
    operation_assets,
    require_assets_in_scope,
    require_location,
    require_personal_assets,
    require_public_assets,
    serialize_operation,
)

_SELF_RETURN_PERMISSION = "asset:return:self"
_MANAGE_PERMISSION = "asset:usage:manage"
_RETURN_CONFIRM_ACTION = "RETURN_CONFIRM"
_PERSONAL_TARGET_FIELDS = frozenset(
    {
        "status",
        "usage_type",
        "holder_user_id",
        "public_object_id",
        "usage_department_id",
    }
)
_PUBLIC_TARGET_FIELDS = frozenset({*_PERSONAL_TARGET_FIELDS, "location_id"})


@dataclass(frozen=True)
class _ReturnAggregate:
    operation: OperationRequest
    detail: AssetReturnRequest
    snapshots: list[OperationRequestAsset]
    items_by_request_asset_id: dict[int, AssetReturnItem]


@dataclass(frozen=True)
class _Inspection:
    asset_id: int
    condition: str
    condition_description: str | None


def _require_clean_entry_unit_of_work() -> None:
    """Top-level commit owners cannot safely compose with pending ORM writes."""
    session = db.session()
    if session.new or session.dirty or session.deleted:
        raise RuntimeError(
            "asset return transaction boundary rejected pending business writes"
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


def _asset_ids(payload: dict[str, Any]) -> list[int]:
    values = payload.get("asset_ids")
    if not isinstance(values, list) or not values:
        raise BusinessException(
            "申请至少包含一项资产",
            result_code=ResultCode.BAD_REQUEST,
        )
    if any(type(value) is not int for value in values):
        raise BusinessException(
            "资产 ID 格式无效",
            result_code=ResultCode.BAD_REQUEST,
        )
    if len(values) != len(set(values)):
        raise BusinessException(
            "资产 ID 不能重复",
            result_code=ResultCode.BAD_REQUEST,
        )
    return values


def _return_location(payload: dict[str, Any]) -> int:
    value = payload.get("return_location_id")
    if type(value) is not int:
        raise BusinessException(
            "退回地点格式无效",
            result_code=ResultCode.BAD_REQUEST,
        )
    require_location(value)
    return value


def _inspections(payload: dict[str, Any], asset_ids: list[int]) -> list[_Inspection]:
    raw_items = payload.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise BusinessException(
            "必须逐项填写资产验收结果",
            result_code=ResultCode.BAD_REQUEST,
        )
    normalized: list[_Inspection] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            raise BusinessException(
                "资产验收结果格式无效",
                result_code=ResultCode.BAD_REQUEST,
            )
        asset_id = raw_item.get("asset_id")
        condition = raw_item.get("condition")
        description = raw_item.get("condition_description")
        if type(asset_id) is not int:
            raise BusinessException(
                "验收资产 ID 格式无效",
                result_code=ResultCode.BAD_REQUEST,
            )
        if type(condition) is not str or condition not in {"NORMAL", "DAMAGED"}:
            raise BusinessException(
                "资产验收状况无效",
                result_code=ResultCode.BAD_REQUEST,
            )
        if description is not None and not isinstance(description, str):
            raise BusinessException(
                "资产验收说明格式无效",
                result_code=ResultCode.BAD_REQUEST,
            )
        normalized_description = (
            description.strip() if description is not None else None
        )
        if condition == "DAMAGED" and not normalized_description:
            raise BusinessException(
                "损坏资产必须填写情况说明",
                result_code=ResultCode.BAD_REQUEST,
            )
        if condition == "NORMAL":
            normalized_description = None
        normalized.append(
            _Inspection(
                asset_id=asset_id,
                condition=condition,
                condition_description=normalized_description,
            )
        )

    inspection_ids = [item.asset_id for item in normalized]
    if len(inspection_ids) != len(set(inspection_ids)):
        raise BusinessException(
            "验收资产 ID 不能重复",
            result_code=ResultCode.BAD_REQUEST,
        )
    if set(inspection_ids) != set(asset_ids):
        raise BusinessException(
            "验收资产必须与申请资产完全一致",
            result_code=ResultCode.BAD_REQUEST,
        )
    by_asset_id = {item.asset_id: item for item in normalized}
    return [by_asset_id[asset_id] for asset_id in asset_ids]


def _same_scalar(actual: object, expected: object) -> bool:
    return type(actual) is type(expected) and actual == expected


def _target_matches(
    target: object,
    expected: dict[str, object],
    fields: frozenset[str],
) -> bool:
    return (
        isinstance(target, dict)
        and set(target) == fields
        and all(_same_scalar(target[key], value) for key, value in expected.items())
    )


def _expected_target(
    operation_type: str,
    detail: AssetReturnRequest,
) -> tuple[dict[str, object], frozenset[str]]:
    target: dict[str, object] = {
        "status": AssetStatus.IDLE.value,
        "usage_type": None,
        "holder_user_id": None,
        "public_object_id": None,
        "usage_department_id": None,
    }
    if operation_type == OperationType.PERSONAL_RETURN.value:
        return target, _PERSONAL_TARGET_FIELDS
    if type(detail.return_location_id) is not int:
        raise BusinessException("公共退回申请详情与目标快照不匹配")
    return (
        {**target, "location_id": detail.return_location_id},
        _PUBLIC_TARGET_FIELDS,
    )


def _validate_persisted_item(item: AssetReturnItem) -> None:
    if item.condition not in {"NORMAL", "DAMAGED"}:
        raise BusinessException("退回资产验收结果无效")
    if item.condition == "NORMAL":
        if item.condition_description is not None:
            raise BusinessException("正常资产不能保留损坏说明")
        return
    description = item.condition_description
    if not isinstance(description, str) or not description.strip():
        raise BusinessException("损坏资产必须填写情况说明")


def _validate_feature_integrity(
    operation_type: str,
    detail: AssetReturnRequest,
    items: list[AssetReturnItem],
) -> None:
    confirmation_values = (
        detail.return_location_id,
        detail.confirmed_by,
        detail.confirmed_at,
    )
    is_empty = all(value is None for value in confirmation_values)
    is_confirmed = (
        type(detail.return_location_id) is int
        and type(detail.confirmed_by) is int
        and isinstance(detail.confirmed_at, datetime)
    )
    if not is_empty and not is_confirmed:
        raise BusinessException("退回申请验收详情不完整")
    if operation_type == OperationType.PUBLIC_RETURN.value and not is_confirmed:
        raise BusinessException("公共退回申请验收详情不完整")
    if is_empty:
        if any(
            item.condition is not None or item.condition_description is not None
            for item in items
        ):
            raise BusinessException("退回申请验收详情与资产明细不匹配")
        return
    for item in items:
        _validate_persisted_item(item)


def _is_optional_int(value: object) -> bool:
    return value is None or type(value) is int


def _validate_snapshot_integrity(
    operation: OperationRequest,
    snapshot: OperationRequestAsset,
    operation_type: str,
) -> None:
    before_data = snapshot.before_data
    before_fields = {
        "status",
        "organization_id",
        "usage_type",
        "holder_user_id",
        "public_object_id",
        "public_object_name",
        "usage_department_id",
        "location_id",
        "manager_id",
        "parent_asset_id",
        "version",
    }
    if not isinstance(before_data, dict) or set(before_data) != before_fields:
        raise BusinessException("退回申请资产操作前快照不完整")
    if (
        type(snapshot.asset_id) is not int
        or not isinstance(snapshot.asset_code_snapshot, str)
        or not isinstance(snapshot.asset_name_snapshot, str)
        or type(before_data["organization_id"]) is not int
        or type(before_data["location_id"]) is not int
        or type(before_data["manager_id"]) is not int
        or type(before_data["version"]) is not int
        or not _is_optional_int(before_data["usage_department_id"])
        or not _is_optional_int(before_data["parent_asset_id"])
    ):
        raise BusinessException("退回申请资产操作前快照类型无效")
    if (
        not _same_scalar(
            snapshot.asset_status_snapshot,
            before_data["status"],
        )
        or not _same_scalar(
            snapshot.organization_id_snapshot,
            before_data["organization_id"],
        )
        or not _same_scalar(
            snapshot.asset_version_snapshot,
            before_data["version"],
        )
    ):
        raise BusinessException("退回申请资产快照与操作前数据不匹配")

    if operation_type == OperationType.PERSONAL_RETURN.value:
        valid_feature_state = (
            _same_scalar(before_data["status"], AssetStatus.IN_USE.value)
            and _same_scalar(before_data["usage_type"], UsageType.PERSONAL.value)
            and _same_scalar(before_data["holder_user_id"], operation.applicant_id)
            and before_data["public_object_id"] is None
            and before_data["public_object_name"] is None
        )
    else:
        valid_feature_state = (
            _same_scalar(before_data["status"], AssetStatus.IN_USE.value)
            and _same_scalar(before_data["usage_type"], UsageType.PUBLIC.value)
            and before_data["holder_user_id"] is None
            and type(before_data["public_object_id"]) is int
            and isinstance(before_data["public_object_name"], str)
        )
    if not valid_feature_state:
        raise BusinessException("退回申请资产领用快照与申请类型不匹配")

    holder_snapshot = snapshot.holder_snapshot
    holder_user_id = before_data["holder_user_id"]
    if holder_user_id is None:
        if holder_snapshot is not None:
            raise BusinessException("退回申请资产持有人快照不匹配")
    elif (
        not isinstance(holder_snapshot, dict)
        or set(holder_snapshot) != {"id", "name"}
        or not _same_scalar(holder_snapshot["id"], holder_user_id)
        or (
            holder_snapshot["name"] is not None
            and not isinstance(holder_snapshot["name"], str)
        )
    ):
        raise BusinessException("退回申请资产持有人快照不匹配")

    location_snapshot = snapshot.location_snapshot
    if (
        not isinstance(location_snapshot, dict)
        or set(location_snapshot) != {"id", "code", "name"}
        or not _same_scalar(location_snapshot["id"], before_data["location_id"])
        or any(
            location_snapshot[key] is not None
            and not isinstance(location_snapshot[key], str)
            for key in ("code", "name")
        )
    ):
        raise BusinessException("退回申请资产地点快照不匹配")


def _load_aggregate(
    operation: OperationRequest,
    operation_type: str,
    *,
    validate_targets: bool,
    snapshots: list[OperationRequestAsset] | None = None,
) -> _ReturnAggregate:
    if operation.operation_type != operation_type:
        raise BusinessException("退回申请类型不匹配")
    if operation_type == OperationType.PERSONAL_RETURN.value:
        valid_operation_contract = (
            operation.approval_channel == ApprovalChannel.FEISHU.value
            and operation.approval_execution_mode
            == ApprovalExecutionMode.MANUAL_CONFIRM.value
        )
    else:
        valid_operation_contract = (
            operation.approval_channel == ApprovalChannel.DIRECT.value
            and operation.approval_execution_mode
            == ApprovalExecutionMode.AUTO_ON_APPROVAL.value
        )
    if not valid_operation_contract:
        raise BusinessException("退回申请审批执行方式与类型不匹配")
    detail = asset_return_request_repository.find_by_operation(operation.id)
    if detail is None:
        raise BusinessException("退回申请详情不存在")
    snapshot_rows = (
        snapshots if snapshots is not None else operation_assets(operation.id)
    )
    if not snapshot_rows:
        raise BusinessException("退回申请未包含资产快照")
    snapshot_ids = [snapshot.asset_id for snapshot in snapshot_rows]
    if any(
        type(asset_id) is not int for asset_id in snapshot_ids
    ) or snapshot_ids != sorted(set(snapshot_ids)):
        raise BusinessException("退回申请资产快照不完整")
    request_asset_ids = [snapshot.id for snapshot in snapshot_rows]
    if any(type(request_asset_id) is not int for request_asset_id in request_asset_ids):
        raise BusinessException("退回申请资产快照不完整")
    items = asset_return_item_repository.find_by_operation(operation.id)
    item_request_asset_ids = [item.operation_request_asset_id for item in items]
    if (
        len(items) != len(snapshot_rows)
        or len(set(item_request_asset_ids)) != len(item_request_asset_ids)
        or set(item_request_asset_ids) != set(request_asset_ids)
    ):
        raise BusinessException("退回申请资产验收明细不完整")
    _validate_feature_integrity(operation_type, detail, items)
    if validate_targets:
        expected, fields = _expected_target(operation_type, detail)
        for snapshot in snapshot_rows:
            _validate_snapshot_integrity(operation, snapshot, operation_type)
            if not _target_matches(snapshot.target_data, expected, fields):
                raise BusinessException("退回申请详情与资产目标快照不匹配")
    return _ReturnAggregate(
        operation=operation,
        detail=detail,
        snapshots=snapshot_rows,
        items_by_request_asset_id={
            item.operation_request_asset_id: item for item in items
        },
    )


def _feature_data(aggregate: _ReturnAggregate) -> dict[str, Any]:
    confirmed_at = aggregate.detail.confirmed_at
    return {
        "return_location_id": aggregate.detail.return_location_id,
        "confirmed_by": aggregate.detail.confirmed_by,
        "confirmed_at": confirmed_at.isoformat() if confirmed_at is not None else None,
        "items": [
            {
                "asset_id": snapshot.asset_id,
                "condition": aggregate.items_by_request_asset_id[snapshot.id].condition,
                "condition_description": aggregate.items_by_request_asset_id[
                    snapshot.id
                ].condition_description,
            }
            for snapshot in aggregate.snapshots
        ],
    }


def _serialize(
    operation: OperationRequest,
    actor_id: int,
    operation_type: str,
    *,
    validate_targets: bool = True,
) -> dict[str, Any]:
    aggregate = _load_aggregate(
        operation,
        operation_type,
        validate_targets=validate_targets,
    )
    return serialize_operation(
        operation,
        actor_id,
        feature_data=_feature_data(aggregate),
    )


def _replay_submission(
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
    if operation_type == OperationType.PUBLIC_RETURN.value:
        return _serialize_or_recover_public_return(operation, actor_id)
    return _serialize(operation, actor_id, operation_type)


def _add_empty_return_rows(operation: OperationRequest) -> None:
    asset_return_request_repository.add(
        AssetReturnRequest(
            operation_request_id=operation.id,
            return_location_id=None,
            confirmed_by=None,
            confirmed_at=None,
        )
    )
    for snapshot in operation_assets(operation.id):
        asset_return_item_repository.add(
            AssetReturnItem(
                operation_request_asset_id=snapshot.id,
                condition=None,
                condition_description=None,
            )
        )


def submit_personal(payload: dict[str, Any], actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, _SELF_RETURN_PERMISSION)
    idempotency_key = _idempotency_key(payload)
    replayed = _replay_submission(
        actor_id,
        OperationType.PERSONAL_RETURN.value,
        idempotency_key,
    )
    if replayed is not None:
        return replayed

    assets = expand_assets(_asset_ids(payload))
    require_personal_assets(assets, actor_id)
    target = {
        "status": AssetStatus.IDLE.value,
        "usage_type": None,
        "holder_user_id": None,
        "public_object_id": None,
        "usage_department_id": None,
    }
    created = operation_service.create_request(
        operation_type=OperationType.PERSONAL_RETURN.value,
        applicant_id=actor_id,
        approval_channel=ApprovalChannel.FEISHU.value,
        approval_execution_mode=ApprovalExecutionMode.MANUAL_CONFIRM.value,
        assets=assets,
        target_data_by_asset_id={asset.id: target for asset in assets},
        idempotency_key=idempotency_key,
    )
    if not created.created:
        return _serialize(
            created.operation,
            actor_id,
            OperationType.PERSONAL_RETURN.value,
        )

    _add_empty_return_rows(created.operation)
    operation = approval_provider_service.submit(created.operation.id, actor_id)
    return _serialize(operation, actor_id, OperationType.PERSONAL_RETURN.value)


def _scope_snapshots(
    actor_id: int,
    snapshots: list[OperationRequestAsset],
) -> None:
    organization_ids = permission_service.accessible_organization_ids(actor_id)
    if organization_ids is None:
        return
    if any(
        snapshot.organization_id_snapshot not in organization_ids
        for snapshot in snapshots
    ):
        raise BusinessException(
            "无该申请的数据权限",
            result_code=ResultCode.FORBIDDEN,
        )


def _is_action_idempotency_conflict(error: IntegrityError) -> bool:
    message = str(error.orig).lower()
    return (
        "uq_operation_action_idempotency" in message
        or "operation_action_idempotencies.operation_request_id, "
        "operation_action_idempotencies.actor_id, "
        "operation_action_idempotencies.action, "
        "operation_action_idempotencies.idempotency_key"
        in message
    )


def _restart_read_transaction_and_lock_return(
    operation_request_id: int,
    operation_type: str,
) -> tuple[OperationRequest, _ReturnAggregate]:
    session = db.session()
    if session.new or session.dirty or session.deleted:
        raise RuntimeError("return recovery cannot discard pending business writes")
    db.session.rollback()
    db.session.remove()
    operation = operation_request_repository.find_for_update(operation_request_id)
    if operation is None:
        raise BusinessException("退回申请不存在", result_code=ResultCode.NOT_FOUND)
    aggregate = _load_aggregate(
        operation,
        operation_type,
        validate_targets=True,
    )
    return operation, aggregate


def _serialize_or_recover_public_return(
    operation: OperationRequest,
    actor_id: int,
) -> dict[str, Any]:
    _serialize(operation, actor_id, OperationType.PUBLIC_RETURN.value)
    operation, _aggregate = _restart_read_transaction_and_lock_return(
        operation.id,
        OperationType.PUBLIC_RETURN.value,
    )
    serialized = _serialize(
        operation,
        actor_id,
        OperationType.PUBLIC_RETURN.value,
    )
    if (
        operation.approval_status == ApprovalStatus.APPROVED.value
        and operation.execution_status == ExecutionStatus.NOT_STARTED.value
    ):
        operation = operation_executor.execute_after_approval(operation.id, actor_id)
        return _serialize(operation, actor_id, OperationType.PUBLIC_RETURN.value)
    db.session.rollback()
    db.session.remove()
    return serialized


def _replay_confirmation_action(
    record: OperationActionIdempotency,
    actor_id: int,
) -> dict[str, Any]:
    operation = operation_request_repository.get(record.operation_request_id)
    if operation is None:
        raise BusinessException("退回申请不存在", result_code=ResultCode.NOT_FOUND)
    if record.status == "COMPLETED":
        return _serialize(
            operation,
            actor_id,
            OperationType.PERSONAL_RETURN.value,
        )
    if record.status != "PROCESSING":
        raise BusinessException("退库确认幂等记录状态无效")
    aggregate = _load_aggregate(
        operation,
        OperationType.PERSONAL_RETURN.value,
        validate_targets=True,
    )
    operation_id = operation.id
    action_key = record.idempotency_key
    if aggregate.detail.return_location_id is None:
        raise BusinessException("退库确认请求正在处理中，请稍后重试")
    operation, aggregate = _restart_read_transaction_and_lock_return(
        operation_id,
        OperationType.PERSONAL_RETURN.value,
    )
    if operation.execution_status in {
        ExecutionStatus.SUCCESS.value,
        ExecutionStatus.FAILED.value,
    }:
        _complete_confirmation_action(operation_id, actor_id, action_key)
        return _serialize(
            operation,
            actor_id,
            OperationType.PERSONAL_RETURN.value,
        )
    if operation.execution_status != ExecutionStatus.NOT_STARTED.value or (
        aggregate.detail.return_location_id is None
    ):
        db.session.rollback()
        db.session.remove()
        raise BusinessException("退库确认请求正在处理中，请稍后重试")
    operation = operation_executor.confirm(operation_id, actor_id)
    _complete_confirmation_action(operation_id, actor_id, action_key)
    return _serialize(
        operation,
        actor_id,
        OperationType.PERSONAL_RETURN.value,
    )


def _complete_confirmation_action(
    operation_request_id: int,
    actor_id: int,
    idempotency_key: str,
) -> None:
    persisted_record = operation_action_idempotency_repository.find_by_key(
        operation_request_id,
        actor_id,
        _RETURN_CONFIRM_ACTION,
        idempotency_key,
    )
    if persisted_record is None:
        raise RuntimeError("durable return confirmation idempotency claim missing")
    persisted_record.status = "COMPLETED"
    db.session.commit()


def _claim_confirmation_action(
    operation_request_id: int,
    actor_id: int,
    idempotency_key: str | None,
) -> tuple[OperationActionIdempotency | None, dict[str, Any] | None]:
    if idempotency_key is None:
        return None, None
    existing = operation_action_idempotency_repository.find_by_key(
        operation_request_id,
        actor_id,
        _RETURN_CONFIRM_ACTION,
        idempotency_key,
    )
    if existing is not None:
        return None, _replay_confirmation_action(existing, actor_id)
    record = OperationActionIdempotency(
        operation_request_id=operation_request_id,
        actor_id=actor_id,
        action=_RETURN_CONFIRM_ACTION,
        idempotency_key=idempotency_key,
        status="PROCESSING",
    )
    try:
        operation_action_idempotency_repository.add(record)
        return record, None
    except IntegrityError as error:
        if not _is_action_idempotency_conflict(error):
            raise
        db.session.rollback()
        duplicate = operation_action_idempotency_repository.find_by_key(
            operation_request_id,
            actor_id,
            _RETURN_CONFIRM_ACTION,
            idempotency_key,
        )
        if duplicate is None:
            raise BusinessException("退库确认请求正在处理中，请稍后重试") from None
        return None, _replay_confirmation_action(duplicate, actor_id)


def _claim_and_apply_inspection(
    aggregate: _ReturnAggregate,
    inspections: list[_Inspection],
    return_location_id: int,
    actor_id: int,
) -> bool:
    confirmed_at = utc_now()
    result = db.session.execute(
        update(AssetReturnRequest)
        .where(
            AssetReturnRequest.id == aggregate.detail.id,
            AssetReturnRequest.return_location_id.is_(None),
            AssetReturnRequest.confirmed_by.is_(None),
            AssetReturnRequest.confirmed_at.is_(None),
        )
        .values(
            return_location_id=return_location_id,
            confirmed_by=actor_id,
            confirmed_at=confirmed_at,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        return False
    aggregate.detail.return_location_id = return_location_id
    aggregate.detail.confirmed_by = actor_id
    aggregate.detail.confirmed_at = confirmed_at
    by_asset_id = {item.asset_id: item for item in inspections}
    for snapshot in aggregate.snapshots:
        inspection = by_asset_id[snapshot.asset_id]
        item = aggregate.items_by_request_asset_id[snapshot.id]
        item.condition = inspection.condition
        item.condition_description = inspection.condition_description
    return True


def _inspection_matches_winner(
    aggregate: _ReturnAggregate,
    inspections: list[_Inspection],
    return_location_id: int,
    actor_id: int,
) -> bool:
    if not _same_scalar(
        aggregate.detail.return_location_id, return_location_id
    ) or not _same_scalar(aggregate.detail.confirmed_by, actor_id):
        return False
    inspections_by_asset_id = {item.asset_id: item for item in inspections}
    for snapshot in aggregate.snapshots:
        inspection = inspections_by_asset_id[snapshot.asset_id]
        persisted = aggregate.items_by_request_asset_id[snapshot.id]
        if not _same_scalar(
            persisted.condition, inspection.condition
        ) or not _same_scalar(
            persisted.condition_description,
            inspection.condition_description,
        ):
            return False
    return True


def _recover_no_key_personal_confirmation(
    operation_request_id: int,
    actor_id: int,
    return_location_id: int,
    inspections: list[_Inspection],
) -> dict[str, Any]:
    operation, aggregate = _restart_read_transaction_and_lock_return(
        operation_request_id,
        OperationType.PERSONAL_RETURN.value,
    )
    if not _inspection_matches_winner(
        aggregate,
        inspections,
        return_location_id,
        actor_id,
    ):
        db.session.rollback()
        db.session.remove()
        raise BusinessException("退库申请已由其他验收请求确认")
    if operation.execution_status in {
        ExecutionStatus.SUCCESS.value,
        ExecutionStatus.FAILED.value,
    }:
        serialized = _serialize(
            operation,
            actor_id,
            OperationType.PERSONAL_RETURN.value,
        )
        db.session.rollback()
        db.session.remove()
        return serialized
    if operation.execution_status != ExecutionStatus.NOT_STARTED.value:
        db.session.rollback()
        db.session.remove()
        raise BusinessException("退库确认请求正在处理中，请稍后重试")
    operation = operation_executor.confirm(operation.id, actor_id)
    return _serialize(
        operation,
        actor_id,
        OperationType.PERSONAL_RETURN.value,
    )


def confirm(
    operation_request_id: int,
    payload: dict[str, Any],
    actor_id: int,
) -> dict[str, Any]:
    _require_clean_entry_unit_of_work()
    permission_service.require_permission(actor_id, _MANAGE_PERMISSION)
    idempotency_key = _idempotency_key(payload)
    operation = operation_request_repository.get(operation_request_id)
    if operation is None:
        raise BusinessException("退回申请不存在", result_code=ResultCode.NOT_FOUND)
    snapshots = operation_assets(operation.id)
    _scope_snapshots(actor_id, snapshots)
    aggregate = _load_aggregate(
        operation,
        OperationType.PERSONAL_RETURN.value,
        validate_targets=True,
        snapshots=snapshots,
    )
    if operation.approval_status != ApprovalStatus.APPROVED.value:
        raise BusinessException("只有审批通过的个人退库申请可以验收")
    if operation.approval_execution_mode != ApprovalExecutionMode.MANUAL_CONFIRM.value:
        raise BusinessException("当前退回申请不支持人工验收")
    if idempotency_key is not None:
        existing_action = operation_action_idempotency_repository.find_by_key(
            operation.id,
            actor_id,
            _RETURN_CONFIRM_ACTION,
            idempotency_key,
        )
        if existing_action is not None:
            return _replay_confirmation_action(existing_action, actor_id)

    if operation.execution_status == ExecutionStatus.SUCCESS.value:
        return _serialize(
            operation,
            actor_id,
            OperationType.PERSONAL_RETURN.value,
        )
    if (
        operation.execution_status == ExecutionStatus.FAILED.value
        and idempotency_key is None
    ):
        return _serialize(
            operation,
            actor_id,
            OperationType.PERSONAL_RETURN.value,
        )

    if operation.execution_status != ExecutionStatus.NOT_STARTED.value:
        raise BusinessException("当前执行状态不能开始退库验收")

    snapshot_asset_ids = [snapshot.asset_id for snapshot in snapshots]
    return_location_id = _return_location(payload)
    inspections = _inspections(payload, snapshot_asset_ids)
    if aggregate.detail.return_location_id is not None:
        if idempotency_key is not None:
            raise BusinessException("退库申请已由其他验收请求确认")
        return _recover_no_key_personal_confirmation(
            operation.id,
            actor_id,
            return_location_id,
            inspections,
        )
    if not _claim_and_apply_inspection(
        aggregate,
        inspections,
        return_location_id,
        actor_id,
    ):
        if idempotency_key is not None:
            db.session.rollback()
            raise BusinessException("退库申请已由其他验收请求确认")
        return _recover_no_key_personal_confirmation(
            operation.id,
            actor_id,
            return_location_id,
            inspections,
        )
    action_record, replayed = _claim_confirmation_action(
        operation.id,
        actor_id,
        idempotency_key,
    )
    if replayed is not None:
        return replayed

    db.session.commit()
    operation = operation_executor.confirm(operation.id, actor_id)
    if action_record is not None:
        _complete_confirmation_action(
            operation.id,
            actor_id,
            action_record.idempotency_key,
        )
    return _serialize(
        operation,
        actor_id,
        OperationType.PERSONAL_RETURN.value,
    )


def _add_confirmed_return_rows(
    operation: OperationRequest,
    inspections: list[_Inspection],
    return_location_id: int,
    actor_id: int,
) -> None:
    asset_return_request_repository.add(
        AssetReturnRequest(
            operation_request_id=operation.id,
            return_location_id=return_location_id,
            confirmed_by=actor_id,
            confirmed_at=utc_now(),
        )
    )
    inspections_by_asset_id = {item.asset_id: item for item in inspections}
    for snapshot in operation_assets(operation.id):
        inspection = inspections_by_asset_id[snapshot.asset_id]
        asset_return_item_repository.add(
            AssetReturnItem(
                operation_request_asset_id=snapshot.id,
                condition=inspection.condition,
                condition_description=inspection.condition_description,
            )
        )


def submit_public(payload: dict[str, Any], actor_id: int) -> dict[str, Any]:
    _require_clean_entry_unit_of_work()
    permission_service.require_permission(actor_id, _MANAGE_PERMISSION)
    idempotency_key = _idempotency_key(payload)
    replayed = _replay_submission(
        actor_id,
        OperationType.PUBLIC_RETURN.value,
        idempotency_key,
    )
    if replayed is not None:
        return replayed

    assets = expand_assets(_asset_ids(payload))
    require_assets_in_scope(actor_id, assets)
    require_public_assets(assets)
    asset_ids = [asset.id for asset in assets]
    inspections = _inspections(payload, asset_ids)
    return_location_id = _return_location(payload)
    target = {
        "status": AssetStatus.IDLE.value,
        "usage_type": None,
        "holder_user_id": None,
        "public_object_id": None,
        "usage_department_id": None,
        "location_id": return_location_id,
    }
    created = operation_service.create_request(
        operation_type=OperationType.PUBLIC_RETURN.value,
        applicant_id=actor_id,
        approval_channel=ApprovalChannel.DIRECT.value,
        approval_execution_mode=ApprovalExecutionMode.AUTO_ON_APPROVAL.value,
        assets=assets,
        target_data_by_asset_id={asset.id: target for asset in assets},
        idempotency_key=idempotency_key,
    )
    if not created.created:
        return _serialize_or_recover_public_return(created.operation, actor_id)

    _add_confirmed_return_rows(
        created.operation,
        inspections,
        return_location_id,
        actor_id,
    )
    operation = approval_provider_service.confirm_direct(created.operation.id, actor_id)
    return _serialize(operation, actor_id, OperationType.PUBLIC_RETURN.value)


__all__ = ["confirm", "submit_personal", "submit_public"]
