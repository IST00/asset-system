"""Translate formal Feishu approval callbacks into the operation kernel."""

from __future__ import annotations

from typing import Any

from app.common import BusinessException, ResultCode
from app.services import approval_provider_service


_STATUS_MAP = {
    "APPROVE": "APPROVED",
    "REJECT": "REJECTED",
    "CANCELED": "WITHDRAWN",
}


def handle_event(event_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    instance_code = payload.get("instance_code")
    if not isinstance(instance_code, str) or not instance_code:
        raise BusinessException("飞书审批实例无效", result_code=ResultCode.BAD_REQUEST)
    task_list = payload.get("task_list")
    if not isinstance(task_list, list) or not task_list:
        return {"event_id": event_id, "ignored": "no_task"}
    task = task_list[-1] if isinstance(task_list[-1], dict) else {}
    action = str(task.get("status") or "").upper()
    status = _STATUS_MAP.get(action)
    if status is None:
        return {"event_id": event_id, "ignored": action or "unknown_status"}
    custom_node = task.get("custom_node_data")
    reason = ""
    if isinstance(custom_node, dict):
        reason = str(custom_node.get("task_remark") or "")
    operation = approval_provider_service._require_operation_by_external_instance(
        instance_code
    )
    result = approval_provider_service.handle_callback(
        provider="FEISHU",
        external_event_id=event_id,
        external_instance_id=instance_code,
        status=status,
        actor_id=operation.applicant_id,
    )
    return {
        "event_id": event_id,
        "operation_request_id": result.id,
        "status": status,
        "reason": reason,
    }


__all__ = ["handle_event"]
