"""Employee self-service request contracts."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.common import BusinessException, ResultCode
from app.enums import (
    ApprovalChannel,
    ApprovalStatus,
    AssetStatus,
    ExecutionStatus,
    FulfillmentStatus,
)
from app.extensions import db
from app.models import (
    Asset,
    AssetBusinessLock,
    AssetUsageRequest,
    OperationRequest,
    OperationRequestAsset,
    Organization,
)
from app.services import (
    asset_return_service,
    asset_usage_fulfillment_service,
    asset_usage_service,
    local_feishu_service,
)
from asset_usage_return_fixtures import (
    grant_permissions,
    register_usage_return_handlers,
    seed_usage_return_context,
)


def test_employee_can_request_available_category_quantity(app) -> None:
    context = seed_usage_return_context()
    grant_permissions(context.employee, "asset:usage:self")
    grant_permissions(context.manager, "asset:usage:manage")

    result = asset_usage_service.submit_personal_self(
        {
            "category_id": context.main_asset.category_id,
            "requested_quantity": 1,
            "location_id": context.location.id,
            "reason": "项目开发需要",
        },
        context.employee.id,
    )

    operation = db.session.get(OperationRequest, result["id"])
    detail = db.session.scalar(
        select(AssetUsageRequest).where(
            AssetUsageRequest.operation_request_id == result["id"]
        )
    )
    assert operation is not None
    assert detail is not None
    assert operation.applicant_id == context.employee.id
    assert operation.approval_status == ApprovalStatus.PENDING.value
    assert operation.execution_status == ExecutionStatus.NOT_STARTED.value
    assert detail.target_user_id == context.employee.id
    assert detail.requested_category_id == context.main_asset.category_id
    assert detail.requested_quantity == 1
    assert detail.reason == "项目开发需要"
    assert result["feature"]["requested_quantity"] == 1
    assert result["feature"]["reason"] == "项目开发需要"


def test_self_service_references_include_stock_count(app) -> None:
    context = seed_usage_return_context()
    grant_permissions(context.employee, "asset:usage:self")

    references = asset_usage_service.self_service_references(context.employee.id)

    category = next(
        item
        for item in references["categories"]
        if item["id"] == context.main_asset.category_id
    )
    assert category["available_quantity"] == 1
    assert any(item["id"] == context.location.id for item in references["locations"])


def test_employee_can_request_idle_asset_from_parent_organization(app) -> None:
    context = seed_usage_return_context()
    parent = Organization(
        code="UR-PARENT-ORG",
        name="UR Parent Organization",
        status="ENABLED",
    )
    db.session.add(parent)
    db.session.flush()
    context.organization.parent_id = parent.id
    context.main_asset.organization_id = parent.id
    db.session.flush()
    grant_permissions(context.employee, "asset:usage:self")
    grant_permissions(context.manager, "asset:usage:manage")

    references = asset_usage_service.self_service_references(context.employee.id)
    category = next(
        item
        for item in references["categories"]
        if item["id"] == context.main_asset.category_id
    )
    assert category["available_quantity"] == 1

    result = asset_usage_service.submit_personal_self(
        {
            "category_id": context.main_asset.category_id,
            "requested_quantity": 1,
            "location_id": context.location.id,
        },
        context.employee.id,
    )
    assert result["approval_status"] == "PENDING"


def test_self_usage_requires_issue_before_employee_receipt(app) -> None:
    context = seed_usage_return_context()
    grant_permissions(context.employee, "asset:usage:self")
    grant_permissions(context.manager, "asset:usage:manage")

    submitted = asset_usage_service.submit_personal_self(
        {
            "category_id": context.main_asset.category_id,
            "requested_quantity": 1,
            "location_id": context.location.id,
            "reason": "项目开发需要",
        },
        context.employee.id,
    )
    operation = db.session.get(OperationRequest, submitted["id"])
    detail = db.session.scalar(
        select(AssetUsageRequest).where(
            AssetUsageRequest.operation_request_id == submitted["id"]
        )
    )
    assert operation is not None
    assert detail is not None
    assert detail.fulfillment_status == FulfillmentStatus.PENDING_ISSUE.value
    assert context.main_asset.status == AssetStatus.IDLE.value
    initial_asset_version = context.main_asset.version

    register_usage_return_handlers()
    operation.approval_channel = ApprovalChannel.FEISHU.value
    operation.external_instance_id = f"LOCAL-FEISHU-{operation.id}"
    db.session.commit()
    with pytest.raises(BusinessException) as raised:
        local_feishu_service.act(
            operation.id,
            {
                "action": "APPROVE",
                "external_event_id": "self-usage-employee-cannot-approve",
            },
            context.employee.id,
        )
    assert raised.value.code == ResultCode.FORBIDDEN.code

    issued = asset_usage_fulfillment_service.issue(
        operation.id,
        context.manager.id,
        [context.main_asset.id],
        context.location.id,
        context.location.id,
    )
    assert issued["approval_status"] == ApprovalStatus.APPROVED.value
    assert issued["execution_status"] == ExecutionStatus.NOT_STARTED.value
    assert issued["fulfillment_status"] == FulfillmentStatus.PENDING_SIGN.value
    db.session.refresh(context.main_asset)
    assert context.main_asset.status == AssetStatus.PENDING_RECEIPT.value
    assert context.main_asset.version == initial_asset_version + 1

    issued_again = asset_usage_fulfillment_service.issue(
        operation.id,
        context.manager.id,
        [context.main_asset.id],
        context.location.id,
        context.location.id,
    )
    assert issued_again["fulfillment_status"] == FulfillmentStatus.PENDING_SIGN.value
    db.session.refresh(context.main_asset)
    assert context.main_asset.status == AssetStatus.PENDING_RECEIPT.value
    assert context.main_asset.version == initial_asset_version + 1

    signed = asset_usage_fulfillment_service.sign(operation.id, context.employee.id)
    assert signed["fulfillment_status"] == FulfillmentStatus.COMPLETED.value
    assert signed["execution_status"] == ExecutionStatus.SUCCESS.value
    db.session.refresh(context.main_asset)
    assert context.main_asset.status == AssetStatus.IN_USE.value
    assert context.main_asset.version == initial_asset_version + 2


def test_manager_selects_concrete_asset_when_issuing(app) -> None:
    context = seed_usage_return_context()
    grant_permissions(context.employee, "asset:usage:self")
    grant_permissions(context.manager, "asset:usage:manage")
    alternate = Asset(
        asset_code="UR-ASSET-ALTERNATE",
        asset_name="UR Alternate Asset",
        status=AssetStatus.IDLE.value,
        organization_id=context.organization.id,
        category_id=context.main_asset.category_id,
        unit_id=context.main_asset.unit_id,
        original_amount=context.main_asset.original_amount,
        purchase_date=context.main_asset.purchase_date,
        service_life_months=context.main_asset.service_life_months,
        expected_expiry_date=context.main_asset.expected_expiry_date,
        manager_id=context.manager.id,
        source_id=context.main_asset.source_id,
        location_id=context.location.id,
        custom_attributes={},
        data_completeness=context.main_asset.data_completeness,
    )
    db.session.add(alternate)
    db.session.flush()
    submitted = asset_usage_service.submit_personal_self(
        {
            "category_id": context.main_asset.category_id,
            "requested_quantity": 1,
            "location_id": context.location.id,
        },
        context.employee.id,
    )
    operation = db.session.get(OperationRequest, submitted["id"])
    assert operation is not None
    candidates = asset_usage_fulfillment_service.issue_candidates(
        operation.id, context.manager.id
    )
    assert candidates["requested_quantity"] == 1
    assert {item["id"] for item in candidates["items"]} == {
        context.main_asset.id,
        alternate.id,
    }

    asset_usage_fulfillment_service.issue(
        operation.id,
        context.manager.id,
        [alternate.id],
        context.location.id,
        context.location.id,
    )
    db.session.refresh(context.main_asset)
    db.session.refresh(context.child_asset)
    db.session.refresh(alternate)
    assert context.main_asset.status == AssetStatus.IDLE.value
    assert context.child_asset.status == AssetStatus.IDLE.value
    assert alternate.status == AssetStatus.PENDING_RECEIPT.value
    snapshot_ids = set(
        db.session.scalars(
            select(OperationRequestAsset.asset_id).where(
                OperationRequestAsset.operation_request_id == operation.id
            )
        ).all()
    )
    lock_ids = set(
        db.session.scalars(
            select(AssetBusinessLock.asset_id).where(
                AssetBusinessLock.operation_request_id == operation.id
            )
        ).all()
    )
    assert snapshot_ids == {alternate.id}
    assert lock_ids == {alternate.id}

    asset_usage_fulfillment_service.sign(operation.id, context.employee.id)
    db.session.refresh(alternate)
    assert alternate.status == AssetStatus.IN_USE.value


def test_manager_must_select_requested_quantity_and_category(app) -> None:
    context = seed_usage_return_context()
    grant_permissions(context.employee, "asset:usage:self")
    grant_permissions(context.manager, "asset:usage:manage")
    submitted = asset_usage_service.submit_personal_self(
        {
            "category_id": context.main_asset.category_id,
            "requested_quantity": 1,
            "location_id": context.location.id,
        },
        context.employee.id,
    )
    operation = db.session.get(OperationRequest, submitted["id"])
    assert operation is not None
    with pytest.raises(BusinessException, match="必须选择 1 件资产"):
        asset_usage_fulfillment_service.issue(
            operation.id,
            context.manager.id,
            [],
            context.location.id,
            context.location.id,
        )


def test_refused_receipt_returns_asset_to_idle_before_reissue(app) -> None:
    context = seed_usage_return_context()
    grant_permissions(context.employee, "asset:usage:self")
    grant_permissions(context.manager, "asset:usage:manage")

    submitted = asset_usage_service.submit_personal_self(
        {
            "category_id": context.main_asset.category_id,
            "requested_quantity": 1,
            "location_id": context.location.id,
        },
        context.employee.id,
    )
    operation = db.session.get(OperationRequest, submitted["id"])
    assert operation is not None
    initial_asset_version = context.main_asset.version

    asset_usage_fulfillment_service.issue(
        operation.id,
        context.manager.id,
        [context.main_asset.id],
        context.location.id,
        context.location.id,
    )
    db.session.refresh(context.main_asset)
    assert context.main_asset.status == AssetStatus.PENDING_RECEIPT.value
    assert context.main_asset.version == initial_asset_version + 1

    refused = asset_usage_fulfillment_service.refuse_sign(
        operation.id,
        context.employee.id,
        "设备外观与约定不符",
    )
    assert refused["fulfillment_status"] == FulfillmentStatus.SIGN_REFUSED.value
    db.session.refresh(context.main_asset)
    assert context.main_asset.status == AssetStatus.IDLE.value
    assert context.main_asset.version == initial_asset_version + 2

    refused_again = asset_usage_fulfillment_service.refuse_sign(
        operation.id,
        context.employee.id,
        "设备外观与约定不符",
    )
    assert refused_again["fulfillment_status"] == FulfillmentStatus.SIGN_REFUSED.value
    db.session.refresh(context.main_asset)
    assert context.main_asset.status == AssetStatus.IDLE.value
    assert context.main_asset.version == initial_asset_version + 2

    asset_usage_fulfillment_service.issue(
        operation.id,
        context.manager.id,
        [context.main_asset.id],
        context.location.id,
        context.location.id,
    )
    db.session.refresh(context.main_asset)
    assert context.main_asset.status == AssetStatus.PENDING_RECEIPT.value
    assert context.main_asset.version == initial_asset_version + 3

    signed = asset_usage_fulfillment_service.sign(operation.id, context.employee.id)
    assert signed["fulfillment_status"] == FulfillmentStatus.COMPLETED.value
    db.session.refresh(context.main_asset)
    assert context.main_asset.status == AssetStatus.IN_USE.value
    assert context.main_asset.version == initial_asset_version + 4


def test_admin_proxy_usage_requires_issue_and_target_employee_sign(app) -> None:
    context = seed_usage_return_context()
    grant_permissions(context.manager, "asset:usage:manage")
    grant_permissions(context.employee, "asset:usage:self")

    submitted = asset_usage_service.submit_personal(
        {
            "asset_ids": [context.main_asset.id],
            "target_user_id": context.employee.id,
            "location_id": context.location.id,
            "reason": "管理员代员工提交",
        },
        context.manager.id,
    )
    operation = db.session.get(OperationRequest, submitted["id"])
    assert operation is not None
    assert operation.applicant_id == context.manager.id
    assert submitted["feature"]["target_user_id"] == context.employee.id
    assert submitted["fulfillment_status"] == FulfillmentStatus.PENDING_ISSUE.value
    assert submitted["execution_status"] == ExecutionStatus.NOT_STARTED.value
    assert context.main_asset.status == AssetStatus.IDLE.value

    issued = asset_usage_fulfillment_service.issue(
        operation.id,
        context.manager.id,
        [context.main_asset.id],
        context.location.id,
        context.location.id,
    )
    assert issued["fulfillment_status"] == FulfillmentStatus.PENDING_SIGN.value
    db.session.refresh(context.main_asset)
    assert context.main_asset.status == AssetStatus.PENDING_RECEIPT.value

    with pytest.raises(BusinessException) as raised:
        asset_usage_fulfillment_service.sign(operation.id, context.manager.id)
    assert raised.value.code == ResultCode.FORBIDDEN.code

    signed = asset_usage_fulfillment_service.sign(operation.id, context.employee.id)
    assert signed["fulfillment_status"] == FulfillmentStatus.COMPLETED.value
    assert signed["execution_status"] == ExecutionStatus.SUCCESS.value
    db.session.refresh(context.main_asset)
    assert context.main_asset.status == AssetStatus.IN_USE.value
    assert context.main_asset.holder_user_id == context.employee.id


def test_admin_direct_usage_changes_asset_owner_immediately(app) -> None:
    context = seed_usage_return_context()
    grant_permissions(context.manager, "asset:usage:manage")
    register_usage_return_handlers()

    result = asset_usage_service.submit_personal_direct(
        {
            "asset_ids": [context.main_asset.id],
            "target_user_id": context.employee.id,
            "location_id": context.return_location.id,
            "idempotency_key": "admin-direct-personal-usage",
        },
        context.manager.id,
    )

    assert result["approval_status"] == ApprovalStatus.APPROVED.value
    assert result["execution_status"] == ExecutionStatus.SUCCESS.value
    assert result["fulfillment_status"] == FulfillmentStatus.COMPLETED.value
    db.session.refresh(context.main_asset)
    assert context.main_asset.status == AssetStatus.IN_USE.value
    assert context.main_asset.holder_user_id == context.employee.id
    assert context.main_asset.location_id == context.return_location.id

    replayed = asset_usage_service.submit_personal_direct(
        {
            "asset_ids": [context.main_asset.id],
            "target_user_id": context.employee.id,
            "location_id": context.return_location.id,
            "idempotency_key": "admin-direct-personal-usage",
        },
        context.manager.id,
    )
    assert replayed["id"] == result["id"]


def test_admin_direct_personal_return_changes_asset_to_idle(app) -> None:
    context = seed_usage_return_context()
    grant_permissions(context.manager, "asset:usage:manage")
    register_usage_return_handlers()
    asset_usage_service.submit_personal_direct(
        {
            "asset_ids": [context.main_asset.id],
            "target_user_id": context.employee.id,
            "location_id": context.location.id,
        },
        context.manager.id,
    )
    db.session.refresh(context.main_asset)
    assert context.main_asset.status == AssetStatus.IN_USE.value

    result = asset_return_service.submit_personal_direct(
        {
            "asset_ids": [context.main_asset.id],
            "return_company_id": context.organization.id,
            "return_usage_company_id": context.organization.id,
            "return_region_id": context.return_location.id,
            "return_location_id": context.return_location.id,
            "items": [
                {
                    "asset_id": context.main_asset.id,
                    "condition": "NORMAL",
                },
                {
                    "asset_id": context.child_asset.id,
                    "condition": "NORMAL",
                },
            ],
            "idempotency_key": "admin-direct-personal-return",
        },
        context.manager.id,
    )

    assert result["approval_status"] == ApprovalStatus.APPROVED.value
    assert result["execution_status"] == ExecutionStatus.SUCCESS.value
    db.session.refresh(context.main_asset)
    assert context.main_asset.status == AssetStatus.IDLE.value
    assert context.main_asset.holder_user_id is None
    assert context.main_asset.usage_type is None
    assert context.main_asset.location_id == context.return_location.id
