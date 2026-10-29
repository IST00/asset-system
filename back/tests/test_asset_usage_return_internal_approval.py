"""Internal approval contracts for employee usage and return requests."""

from __future__ import annotations

import pytest

from app.common import BusinessException
from app.enums import ApprovalChannel, ApprovalStatus, ExecutionStatus, OperationType
from app.extensions import db
from app.models import ApprovalTask, AssetBusinessLock, OperationRequest
from app.services import (
    asset_return_service,
    asset_usage_service,
    operation_service,
)
from asset_usage_return_fixtures import (
    grant_permissions,
    register_usage_return_handlers,
    seed_usage_return_context,
)


@pytest.fixture()
def internal_approval_app(app):
    register_usage_return_handlers()
    yield app


def _usage_setup(internal_approval_app):
    context = seed_usage_return_context()
    grant_permissions(context.employee, "asset:usage:self")
    grant_permissions(
        context.manager,
        "asset:usage:manage",
        "approval:task:view",
        "approval:task:approve",
    )
    return context


def _return_setup(internal_approval_app):
    context = seed_usage_return_context()
    for asset in (context.main_asset, context.child_asset):
        asset.status = "IN_USE"
        asset.usage_type = "PERSONAL"
        asset.holder_user_id = context.employee.id
        asset.public_object_id = None
        asset.usage_department_id = context.organization.id
    db.session.flush()
    grant_permissions(context.employee, "asset:return:self")
    grant_permissions(
        context.manager,
        "asset:usage:manage",
        "approval:task:view",
        "approval:task:approve",
    )
    return context


def test_employee_usage_submits_to_internal_approval(internal_approval_app) -> None:
    context = _usage_setup(internal_approval_app)

    result = asset_usage_service.submit_personal_self(
        {
            "asset_ids": [context.main_asset.id],
            "target_user_id": context.employee.id,
        },
        context.employee.id,
    )

    assert result["approval_channel"] == ApprovalChannel.INTERNAL.value
    assert result["approval_status"] == ApprovalStatus.PENDING.value
    assert result["execution_status"] == ExecutionStatus.NOT_STARTED.value
    assert result["external_instance_id"] is None
    assert (
        db.session.scalar(
            db.select(ApprovalTask).where(
                ApprovalTask.approver_id == context.manager.id,
                ApprovalTask.status == "PENDING",
            )
        )
        is not None
    )


def test_employee_return_submits_to_internal_approval(internal_approval_app) -> None:
    context = _return_setup(internal_approval_app)

    result = asset_return_service.submit_personal(
        {"asset_ids": [context.main_asset.id]},
        context.employee.id,
    )

    assert result["approval_channel"] == ApprovalChannel.INTERNAL.value
    assert result["approval_status"] == ApprovalStatus.PENDING.value
    assert result["execution_status"] == ExecutionStatus.NOT_STARTED.value
    assert result["external_instance_id"] is None
    task = db.session.scalar(
        db.select(ApprovalTask).where(
            ApprovalTask.approver_id == context.manager.id,
            ApprovalTask.status == "PENDING",
        )
    )
    assert task is not None

    operation_service.approve_task(task.id, context.manager.id, "同意退库")
    db.session.expire_all()
    operation = db.session.get(OperationRequest, result["id"])
    assert operation is not None
    assert operation.approval_status == ApprovalStatus.APPROVED.value
    assert asset_return_service.get(operation.id, context.manager.id)[
        "allowed_actions"
    ] == ["CONFIRM_RETURN"]


def test_employee_can_withdraw_internal_return_and_release_asset_lock(
    internal_approval_app,
) -> None:
    context = _return_setup(internal_approval_app)

    result = asset_return_service.submit_personal(
        {"asset_ids": [context.main_asset.id]},
        context.employee.id,
    )

    assert (
        db.session.query(AssetBusinessLock)
        .filter_by(operation_request_id=result["id"])
        .first()
        is not None
    )

    withdrawn = operation_service.withdraw_request(
        result["id"],
        context.employee.id,
        "重复提交，撤回后重新申请",
    )

    assert withdrawn["approval_status"] == ApprovalStatus.WITHDRAWN.value
    assert (
        db.session.query(AssetBusinessLock)
        .filter_by(operation_request_id=result["id"])
        .count()
        == 0
    )


def test_internal_usage_requires_an_available_manager(internal_approval_app) -> None:
    context = _usage_setup(internal_approval_app)
    context.manager.enabled = False
    db.session.commit()

    with pytest.raises(BusinessException, match="未找到符合条件的资产领退审批人"):
        asset_usage_service.submit_personal_self(
            {
                "asset_ids": [context.main_asset.id],
                "target_user_id": context.employee.id,
            },
            context.employee.id,
        )

    db.session.rollback()
    assert (
        db.session.query(OperationRequest)
        .filter_by(operation_type=OperationType.PERSONAL_USE.value)
        .count()
        == 0
    )
