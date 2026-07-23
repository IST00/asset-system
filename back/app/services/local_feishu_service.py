"""Development-only FEISHU approval event simulation."""

from __future__ import annotations

from typing import Any, cast

from flask import current_app
from marshmallow import ValidationError
from sqlalchemy import update

from app.common import BusinessException, ResultCode
from app.enums import ApprovalChannel, ApprovalStatus, OperationType
from app.extensions import db
from app.models import ExternalApprovalEvent, OperationRequest
from app.repositories.asset_usage_return_repository import (
    asset_usage_request_repository,
)
from app.repositories.operation_repository import (
    external_approval_event_repository,
    operation_request_asset_repository,
)
from app.repositories.workflow_repository import operation_request_repository
from app.schemas.asset_usage_return import MockFeishuActionSchema
from app.services import (
    approval_provider_service,
    asset_return_service,
    asset_usage_service,
    permission_service,
)

_MANAGE_PERMISSION = "asset:usage:manage"
_USAGE_TYPES = frozenset(
    {
        OperationType.PERSONAL_USE.value,
        OperationType.PUBLIC_USE.value,
    }
)
_RETURN_TYPES = frozenset(
    {
        OperationType.PERSONAL_RETURN.value,
        OperationType.PUBLIC_RETURN.value,
    }
)
_ACTION_STATUSES = {
    "APPROVE": ApprovalStatus.APPROVED.value,
    "REJECT": ApprovalStatus.REJECTED.value,
    "WITHDRAW": ApprovalStatus.WITHDRAWN.value,
}
_action_schema = MockFeishuActionSchema()


def _require_local_mode() -> None:
    if (
        current_app.testing
        or current_app.debug
        or current_app.config.get("LOCAL_FEISHU_ENABLED") is True
    ):
        return
    raise BusinessException(
        "本地飞书模拟接口不存在",
        result_code=ResultCode.NOT_FOUND,
    )


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        loaded = _action_schema.load(payload)
    except ValidationError as error:
        raise BusinessException(
            str(error),
            result_code=ResultCode.BAD_REQUEST,
        ) from None
    if not isinstance(loaded, dict):
        raise BusinessException(
            "本地飞书事件格式无效",
            result_code=ResultCode.BAD_REQUEST,
        )
    return cast(dict[str, Any], loaded)


def _require_operation(operation_request_id: int) -> OperationRequest:
    operation = operation_request_repository.get(operation_request_id)
    if operation is None:
        raise BusinessException(
            "申请不存在",
            result_code=ResultCode.NOT_FOUND,
        )
    if operation.approval_channel != ApprovalChannel.FEISHU.value:
        raise BusinessException(
            "只有飞书审批申请支持本地模拟",
            result_code=ResultCode.BAD_REQUEST,
        )
    if operation.operation_type not in _USAGE_TYPES | _RETURN_TYPES:
        raise BusinessException(
            "当前申请类型不支持本地飞书模拟",
            result_code=ResultCode.BAD_REQUEST,
        )
    if not operation.external_instance_id:
        raise BusinessException(
            "飞书审批实例不存在",
            result_code=ResultCode.BAD_REQUEST,
        )
    return operation


def _authorize_decision(operation: OperationRequest, actor_id: int) -> None:
    if operation.operation_type in _USAGE_TYPES:
        detail = asset_usage_request_repository.find_by_operation(operation.id)
        if detail is None:
            raise BusinessException(
                "领用申请详情不存在",
                result_code=ResultCode.NOT_FOUND,
            )
        if detail.target_user_id != actor_id:
            raise BusinessException(
                "只有目标员工可以处理领用审批",
                result_code=ResultCode.FORBIDDEN,
            )
        return

    permission_service.require_permission(actor_id, _MANAGE_PERMISSION)
    for snapshot in operation_request_asset_repository.find_by_request(operation.id):
        permission_service.require_organization_scope(
            actor_id,
            snapshot.organization_id_snapshot,
        )


def _authorize_action(
    operation: OperationRequest,
    action: str,
    actor_id: int,
) -> None:
    if action == "WITHDRAW":
        if operation.applicant_id != actor_id:
            raise BusinessException(
                "只有申请人可以撤回申请",
                result_code=ResultCode.FORBIDDEN,
            )
        return
    _authorize_decision(operation, actor_id)


def _detail(operation: OperationRequest, actor_id: int) -> dict[str, Any]:
    if operation.operation_type in _USAGE_TYPES:
        return asset_usage_service.get(operation.id, actor_id)
    if operation.operation_type in _RETURN_TYPES:
        return asset_return_service.get(operation.id, actor_id)
    raise BusinessException(
        "当前申请类型不支持本地飞书模拟",
        result_code=ResultCode.BAD_REQUEST,
    )


def _require_matching_event(
    event: ExternalApprovalEvent | None,
    operation_id: int,
    handled_id: int,
) -> ExternalApprovalEvent:
    if (
        event is None
        or event.operation_request_id != operation_id
        or handled_id != operation_id
    ):
        raise BusinessException(
            "外部审批事件与申请不匹配",
            result_code=ResultCode.BAD_REQUEST,
        )
    return event


def _require_status_payload(
    event: ExternalApprovalEvent,
    expected_status: str,
) -> dict[str, Any]:
    if not isinstance(event.payload, dict):
        raise BusinessException(
            "外部审批事件内容无效",
            result_code=ResultCode.BAD_REQUEST,
        )
    payload = dict(event.payload)
    if payload.get("status") != expected_status:
        raise BusinessException(
            "外部审批事件状态冲突",
            result_code=ResultCode.BAD_REQUEST,
        )
    return payload


def _require_exact_reason(
    payload: dict[str, Any],
    reason: str | None,
) -> bool:
    if "reason" not in payload:
        return False
    if payload["reason"] != reason:
        raise BusinessException(
            "外部审批事件原因冲突",
            result_code=ResultCode.BAD_REQUEST,
        )
    return True


def _bind_reason_once(
    event: ExternalApprovalEvent,
    operation_id: int,
    handled_id: int,
    expected_status: str,
    reason: str | None,
) -> None:
    original_payload = _require_status_payload(event, expected_status)
    if _require_exact_reason(original_payload, reason):
        return

    desired_payload = {**original_payload, "reason": reason}
    result = db.session.execute(
        update(ExternalApprovalEvent)
        .where(
            ExternalApprovalEvent.id == event.id,
            ExternalApprovalEvent.payload == original_payload,
        )
        .values(payload=desired_payload)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount == 1:
        db.session.commit()
        return

    provider = event.provider
    external_event_id = event.external_event_id
    db.session.rollback()
    persisted = _require_matching_event(
        external_approval_event_repository.find_by_event(
            provider,
            external_event_id,
        ),
        operation_id,
        handled_id,
    )
    persisted_payload = _require_status_payload(persisted, expected_status)
    if not _require_exact_reason(persisted_payload, reason):
        raise BusinessException(
            "外部审批事件原因绑定冲突",
            result_code=ResultCode.BAD_REQUEST,
        )


def act(
    operation_request_id: int,
    payload: dict[str, Any],
    actor_id: int,
) -> dict[str, Any]:
    """Simulate one authorized FEISHU callback and return a strict detail DTO."""
    _require_local_mode()
    normalized = _normalize_payload(payload)
    action = cast(str, normalized["action"])
    external_event_id = cast(str, normalized["external_event_id"])
    reason = cast(str | None, normalized.get("reason"))
    operation = _require_operation(operation_request_id)
    _authorize_action(operation, action, actor_id)
    _detail(operation, actor_id)
    expected_status = _ACTION_STATUSES[action]

    handled = approval_provider_service.handle_callback(
        provider=ApprovalChannel.FEISHU.value,
        external_event_id=external_event_id,
        external_instance_id=operation.external_instance_id,
        status=expected_status,
        actor_id=actor_id,
    )
    event = external_approval_event_repository.find_by_event(
        ApprovalChannel.FEISHU.value,
        external_event_id,
    )
    event = _require_matching_event(event, operation.id, handled.id)
    _bind_reason_once(
        event,
        operation.id,
        handled.id,
        expected_status,
        reason,
    )
    return _detail(handled, actor_id)


__all__ = ["act"]
