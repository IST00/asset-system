"""Approval-flow configuration, validation, and publication use cases."""

from __future__ import annotations

from typing import Any

from app.common import BusinessException, ResultCode
from app.enums import AssigneeType, FlowStatus, SignMode
from app.extensions import db
from app.models import (
    ApprovalFlowAssigneeRule,
    ApprovalFlowDefinition,
    ApprovalFlowLayer,
    ApprovalFlowVersion,
    OperationLog,
)
from app.models.mixins import utc_now
from app.repositories import approval_flow_repository, operation_log_repository
from app.repositories.rbac_repository import rbac_repository
from app.services import permission_service


def _assignee_dict(rule: ApprovalFlowAssigneeRule) -> dict[str, Any]:
    return {
        "id": rule.id,
        "assignee_type": rule.assignee_type,
        "assignee_id": rule.assignee_id,
    }


def _layer_dict(layer: ApprovalFlowLayer) -> dict[str, Any]:
    return {
        "id": layer.id,
        "level_no": layer.level_no,
        "sign_mode": layer.sign_mode,
        "allow_self_approval": layer.allow_self_approval,
        "assignees": [_assignee_dict(rule) for rule in layer.assignee_rules],
    }


def _version_dict(version: ApprovalFlowVersion) -> dict[str, Any]:
    return {
        "id": version.id,
        "flow_definition_id": version.flow_definition_id,
        "version_no": version.version_no,
        "status": version.status,
        "published_at": (
            version.published_at.isoformat()
            if version.published_at is not None
            else None
        ),
        "published_by": version.published_by,
        "layers": [_layer_dict(layer) for layer in version.layers],
    }


def _definition_dict(
    definition: ApprovalFlowDefinition, *, include_versions: bool = False
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": definition.id,
        "operation_type": definition.operation_type,
        "name": definition.name,
        "status": definition.status,
        "version": definition.version,
    }
    if include_versions:
        result["versions"] = [
            _version_dict(version)
            for version in approval_flow_repository.list_versions(definition.id)
        ]
    return result


def _require_definition(flow_id: int) -> ApprovalFlowDefinition:
    definition = approval_flow_repository.get_definition(flow_id)
    if definition is None:
        raise BusinessException("审批流不存在", result_code=ResultCode.NOT_FOUND)
    return definition


def _require_version(version_id: int) -> ApprovalFlowVersion:
    version = approval_flow_repository.load_version_graph(version_id)
    if version is None:
        raise BusinessException("审批流版本不存在", result_code=ResultCode.NOT_FOUND)
    return version


def _validate_assignee(assignee_type: str, assignee_id: int) -> None:
    if assignee_type == AssigneeType.USER.value:
        user = rbac_repository.find_user(assignee_id)
        if user is None or not user.enabled:
            raise BusinessException("审批用户不存在或已停用")
        return
    if assignee_type == AssigneeType.ROLE.value:
        role = rbac_repository.get_role(assignee_id)
        if role is None or not role.enabled:
            raise BusinessException("审批角色不存在或已停用")
        return
    raise BusinessException("审批人类型无效", result_code=ResultCode.BAD_REQUEST)


def _build_layers(payload: dict[str, Any]) -> list[ApprovalFlowLayer]:
    layer_payloads = list(payload["layers"])
    levels = [int(item["level_no"]) for item in layer_payloads]
    if levels != list(range(1, len(levels) + 1)):
        raise BusinessException("审批层级必须从 1 开始连续排列")

    layers: list[ApprovalFlowLayer] = []
    for layer_payload in layer_payloads:
        sign_mode = str(layer_payload["sign_mode"])
        if sign_mode not in {item.value for item in SignMode}:
            raise BusinessException("会签模式无效", result_code=ResultCode.BAD_REQUEST)
        assignee_payloads = list(layer_payload["assignees"])
        if not assignee_payloads:
            raise BusinessException("每个审批层至少需要一个审批人")
        keys: set[tuple[str, int]] = set()
        rules: list[ApprovalFlowAssigneeRule] = []
        for assignee in assignee_payloads:
            assignee_type = str(assignee["assignee_type"])
            assignee_id = int(assignee["assignee_id"])
            key = (assignee_type, assignee_id)
            if key in keys:
                raise BusinessException("同一审批层不能重复配置审批人")
            keys.add(key)
            _validate_assignee(assignee_type, assignee_id)
            rules.append(
                ApprovalFlowAssigneeRule(
                    assignee_type=assignee_type,
                    assignee_id=assignee_id,
                )
            )
        layer = ApprovalFlowLayer(
            level_no=int(layer_payload["level_no"]),
            sign_mode=sign_mode,
            allow_self_approval=bool(layer_payload.get("allow_self_approval", False)),
        )
        layer.assignee_rules = rules
        layers.append(layer)
    return layers


def create_definition(operation_type: str, name: str, actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "approval:flow:edit")
    normalized_type = operation_type.strip().upper()
    normalized_name = name.strip()
    if not normalized_type or not normalized_name:
        raise BusinessException("操作类型和审批流名称不能为空")
    if approval_flow_repository.find_definition(normalized_type) is not None:
        raise BusinessException("该操作类型的审批流已存在")
    definition = approval_flow_repository.add_definition(
        ApprovalFlowDefinition(
            operation_type=normalized_type,
            name=normalized_name,
            status=FlowStatus.DRAFT.value,
        )
    )
    db.session.commit()
    return _definition_dict(definition)


def save_draft(flow_id: int, payload: dict[str, Any], actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "approval:flow:edit")
    definition = _require_definition(flow_id)
    layers = _build_layers(payload)
    version = approval_flow_repository.find_draft(flow_id)
    if version is None:
        version = ApprovalFlowVersion(
            flow_definition_id=flow_id,
            version_no=approval_flow_repository.next_version_no(flow_id),
            status=FlowStatus.DRAFT.value,
        )
        version.layers = layers
        approval_flow_repository.add_version(version)
    else:
        version.layers = layers
        db.session.flush()
    if definition.status == FlowStatus.DRAFT.value:
        definition.version += 1
    db.session.commit()
    return _version_dict(version)


def publish(version_id: int, actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "approval:flow:publish")
    version = _require_version(version_id)
    definition = _require_definition(version.flow_definition_id)
    if definition.status == FlowStatus.DISABLED.value:
        raise BusinessException("停用的审批流不能发布")
    if version.status != FlowStatus.DRAFT.value:
        if version.status == FlowStatus.PUBLISHED.value:
            return _version_dict(version)
        raise BusinessException("只有草稿版本可以发布")
    if not version.layers or any(not layer.assignee_rules for layer in version.layers):
        raise BusinessException("审批流版本配置不完整")

    before = _version_dict(version)
    version.status = FlowStatus.PUBLISHED.value
    version.published_at = utc_now()
    version.published_by = actor_id
    definition.status = FlowStatus.PUBLISHED.value
    definition.version += 1
    after = _version_dict(version)
    operation_log_repository.add(
        OperationLog(
            action="APPROVAL_FLOW_PUBLISH",
            resource_type="approval_flow_version",
            resource_id=str(version.id),
            operator_id=actor_id,
            before_data=before,
            after_data=after,
        )
    )
    db.session.commit()
    return after


def set_enabled(flow_id: int, enabled: bool, actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "approval:flow:disable")
    definition = _require_definition(flow_id)
    before = _definition_dict(definition)
    if enabled:
        definition.status = (
            FlowStatus.PUBLISHED.value
            if approval_flow_repository.has_published(flow_id)
            else FlowStatus.DRAFT.value
        )
    else:
        definition.status = FlowStatus.DISABLED.value
    definition.version += 1
    after = _definition_dict(definition)
    operation_log_repository.add(
        OperationLog(
            action="APPROVAL_FLOW_ENABLE" if enabled else "APPROVAL_FLOW_DISABLE",
            resource_type="approval_flow_definition",
            resource_id=str(definition.id),
            operator_id=actor_id,
            before_data=before,
            after_data=after,
        )
    )
    db.session.commit()
    return after


def get_published(operation_type: str) -> ApprovalFlowVersion:
    version = approval_flow_repository.find_published(operation_type.strip().upper())
    if version is None:
        raise BusinessException("该操作类型没有可用的已发布审批流")
    return version


def list_definitions(actor_id: int) -> list[dict[str, Any]]:
    permission_service.require_permission(actor_id, "approval:flow:view")
    return [
        _definition_dict(definition)
        for definition in approval_flow_repository.list_definitions()
    ]


def get_definition(flow_id: int, actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "approval:flow:view")
    return _definition_dict(_require_definition(flow_id), include_versions=True)


__all__ = [
    "create_definition",
    "get_definition",
    "get_published",
    "list_definitions",
    "publish",
    "save_draft",
    "set_enabled",
]
