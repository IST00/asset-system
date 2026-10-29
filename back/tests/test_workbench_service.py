"""Employee task-center queries and timeline contracts."""

from __future__ import annotations

from datetime import timedelta

from app.enums import (
    ApprovalChannel,
    ApprovalExecutionMode,
    ApprovalStatus,
    AssetStatus,
    ExecutionStatus,
    FulfillmentStatus,
    OperationType,
    RuntimeTaskStatus,
    UsageMode,
    UsageType,
)
from app.extensions import db
from app.models import (
    ApprovalRecord,
    ApprovalStep,
    ApprovalTask,
    AssetUsageRequest,
    OperationRequest,
    OperationRequestAsset,
)
from app.models.mixins import utc_now
from app.security.passwords import hash_password
from app.services import asset_usage_fulfillment_service, workbench_service
from app.services.asset_usage_return_support import (
    build_named_snapshot,
    build_user_snapshot,
)
from asset_usage_return_fixtures import grant_permissions, seed_usage_return_context


def _operation(
    *,
    request_no: str,
    applicant_id: int,
    operation_type: str = OperationType.PERSONAL_USE.value,
    approval_status: str = ApprovalStatus.APPROVED.value,
    execution_status: str = ExecutionStatus.SUCCESS.value,
) -> OperationRequest:
    now = utc_now()
    row = OperationRequest(
        request_no=request_no,
        operation_type=operation_type,
        applicant_id=applicant_id,
        approval_channel=ApprovalChannel.INTERNAL.value,
        approval_execution_mode=ApprovalExecutionMode.MANUAL_CONFIRM.value,
        approval_status=approval_status,
        execution_status=execution_status,
        submitted_at=now,
        approved_at=now if approval_status == ApprovalStatus.APPROVED.value else None,
        executed_at=now if execution_status == ExecutionStatus.SUCCESS.value else None,
    )
    db.session.add(row)
    db.session.flush()
    return row


def test_my_requests_uses_real_server_side_pagination_beyond_fifty(app) -> None:
    context = seed_usage_return_context()
    grant_permissions(context.employee, "asset:usage:self")
    for index in range(55):
        _operation(
            request_no=f"WB-PAGE-{index:03d}",
            applicant_id=context.employee.id,
            approval_status=ApprovalStatus.PENDING.value,
            execution_status=ExecutionStatus.NOT_STARTED.value,
        )
    db.session.commit()

    result = workbench_service.my_requests(
        context.employee.id,
        {
            "page": 2,
            "size": 20,
            "keyword": "WB-PAGE",
            "status": "PENDING_APPROVAL",
            "pending_only": True,
            "start_date": None,
            "end_date": None,
        },
    )

    assert result["total"] == 55
    assert result["pending_count"] == 55
    assert len(result["items"]) == 15
    assert all(item["display_status"] == "PENDING_APPROVAL" for item in result["items"])


def test_pending_return_excludes_normal_borrow_and_includes_manager_request(
    app,
) -> None:
    context = seed_usage_return_context()
    grant_permissions(context.employee, "asset:usage:self", "asset:return:self")
    grant_permissions(context.manager, "asset:usage:manage")
    operation = _operation(request_no="WB-BORROW-001", applicant_id=context.manager.id)
    detail = AssetUsageRequest(
        operation_request_id=operation.id,
        target_user_id=context.employee.id,
        usage_department_id=context.organization.id,
        target_location_id=context.location.id,
        usage_mode=UsageMode.BORROW.value,
        expected_return_at=utc_now() + timedelta(days=30),
        fulfillment_status=FulfillmentStatus.COMPLETED.value,
        signed_by=context.employee.id,
        signed_at=utc_now(),
        target_user_snapshot=build_user_snapshot(context.employee),
        usage_department_snapshot=build_named_snapshot(context.organization),
        target_location_snapshot=build_named_snapshot(context.location),
    )
    db.session.add(detail)
    db.session.add(
        OperationRequestAsset(
            operation_request_id=operation.id,
            asset_id=context.main_asset.id,
            asset_code_snapshot=context.main_asset.asset_code,
            asset_name_snapshot=context.main_asset.asset_name,
            asset_status_snapshot=AssetStatus.IDLE.value,
            asset_version_snapshot=context.main_asset.version,
            organization_id_snapshot=context.organization.id,
            target_data={
                "status": AssetStatus.IN_USE.value,
                "usage_type": UsageType.PERSONAL.value,
                "holder_user_id": context.employee.id,
                "public_object_id": None,
                "usage_department_id": context.organization.id,
                "location_id": context.location.id,
            },
        )
    )
    context.main_asset.status = AssetStatus.IN_USE.value
    context.main_asset.usage_type = UsageType.PERSONAL.value
    context.main_asset.holder_user_id = context.employee.id
    db.session.commit()

    before = workbench_service.pending_return(
        context.employee.id,
        {"page": 0, "size": 20},
    )
    assert before["total"] == 0

    assert (
        workbench_service.my_assets(context.employee.id, {"page": 0, "size": 20})[
            "total"
        ]
        == 0
    )
    borrowed = workbench_service.my_borrowed(
        context.employee.id, {"page": 0, "size": 20}
    )
    assert borrowed["total"] == 1
    assert borrowed["items"][0]["display_status"] == "BORROWED"

    asset_usage_fulfillment_service.request_return(
        operation.id,
        context.manager.id,
        "项目结束，请于本周归还",
    )
    after = workbench_service.pending_return(
        context.employee.id,
        {"page": 0, "size": 20},
    )
    assert after["total"] == 1
    assert after["items"][0]["return_state"] == "MANAGER_REQUESTED"
    assert after["items"][0]["return_request_reason"] == "项目结束，请于本周归还"


def test_request_timeline_contains_submit_approval_issue_and_sign(app) -> None:
    context = seed_usage_return_context()
    grant_permissions(context.employee, "asset:usage:self")
    operation = _operation(
        request_no="WB-TIMELINE-001", applicant_id=context.employee.id
    )
    detail = AssetUsageRequest(
        operation_request_id=operation.id,
        target_user_id=context.employee.id,
        usage_department_id=context.organization.id,
        target_location_id=context.location.id,
        usage_mode=UsageMode.USE.value,
        fulfillment_status=FulfillmentStatus.COMPLETED.value,
        issued_by=context.manager.id,
        issued_at=utc_now(),
        issue_remark="已发放主机",
        signed_by=context.employee.id,
        signed_at=utc_now(),
        sign_remark="已收到",
    )
    db.session.add(detail)
    db.session.add(
        OperationRequestAsset(
            operation_request_id=operation.id,
            asset_id=context.main_asset.id,
            asset_code_snapshot=context.main_asset.asset_code,
            asset_name_snapshot=context.main_asset.asset_name,
            asset_status_snapshot=AssetStatus.IDLE.value,
            asset_version_snapshot=context.main_asset.version,
            organization_id_snapshot=context.organization.id,
            target_data={"holder_user_id": context.employee.id},
        )
    )
    step = ApprovalStep(
        operation_request_id=operation.id,
        level_no=1,
        sign_mode="OR_SIGN",
        status=RuntimeTaskStatus.APPROVED.value,
    )
    db.session.add(step)
    db.session.flush()
    task = ApprovalTask(
        approval_step_id=step.id,
        approver_id=context.manager.id,
        status=RuntimeTaskStatus.APPROVED.value,
        opinion="同意",
        decided_at=utc_now(),
    )
    db.session.add(task)
    db.session.flush()
    db.session.add(
        ApprovalRecord(
            operation_request_id=operation.id,
            approval_step_id=step.id,
            approval_task_id=task.id,
            actor_id=context.manager.id,
            action="APPROVE",
            opinion="同意",
        )
    )
    db.session.commit()

    detail_result = workbench_service.request_detail(operation.id, context.employee.id)
    titles = [item["title"] for item in detail_result["timeline"]]
    assert titles == [
        "提交申请",
        "审批通过",
        "管理员发放资产",
        "资产进入领用待确认",
        "员工签收，资产变为在用",
    ]
    assert detail_result["next_step"] == "流程已结束"


def test_pending_sign_page_counts_pending_requests_without_correlated_join(app) -> None:
    context = seed_usage_return_context()
    grant_permissions(context.employee, "asset:usage:self")
    operation = _operation(
        request_no="WB-PENDING-SIGN-001",
        applicant_id=context.manager.id,
        approval_status=ApprovalStatus.APPROVED.value,
        execution_status=ExecutionStatus.PROCESSING.value,
    )
    db.session.add(
        AssetUsageRequest(
            operation_request_id=operation.id,
            target_user_id=context.employee.id,
            usage_department_id=context.organization.id,
            target_location_id=context.location.id,
            usage_mode=UsageMode.USE.value,
            fulfillment_status=FulfillmentStatus.PENDING_SIGN.value,
            target_user_snapshot=build_user_snapshot(context.employee),
            usage_department_snapshot=build_named_snapshot(context.organization),
            target_location_snapshot=build_named_snapshot(context.location),
        )
    )
    db.session.commit()

    result = workbench_service.pending_sign(
        context.employee.id, {"page": 0, "size": 20}
    )

    assert result["total"] == 1
    assert result["pending_count"] == 1
    assert result["items"][0]["display_status"] == "PENDING_SIGN"


def test_workbench_summary_api_is_registered_and_identity_scoped(app, client) -> None:
    context = seed_usage_return_context()
    grant_permissions(context.employee, "asset:usage:self")
    context.employee.password = hash_password("workbench-password", rounds=4)
    db.session.commit()
    login = client.post(
        "/api/v1/auth/login",
        json={
            "username": context.employee.username,
            "password": "workbench-password",
        },
    )
    assert login.status_code == 200
    token = login.get_json()["data"]["token"]

    response = client.get(
        "/api/v1/workbench/summary",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["pending_sign"] == 0
