from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.enums import (
    ApprovalStatus,
    AssetCodeStatus,
    AssetStatus,
    ExecutionStatus,
    OperationType,
)
from app.extensions import db
from app.models import (
    ApprovalRecord,
    ApprovalStep,
    ApprovalTask,
    Asset,
    AssetCategory,
    AssetCodeReservation,
    AssetCodeSequence,
    AssetLifecycleRecord,
    AssetLocation,
    AssetSource,
    OperationLog,
    OperationRequest,
    Organization,
    StockInItem,
    StockInRequest,
    Unit,
    User,
)
from app.repositories.workflow_repository import operation_request_repository


def test_stock_in_persistence_keeps_workflow_and_asset_data_separate(app) -> None:
    organization = Organization(code="358466", name="上海黄豆网络科技")
    unit = Unit(code="UNIT", name="台")
    source = AssetSource(code="PURCHASE", name="采购")
    location = AssetLocation(code="LOC000001", name="仓库", is_selectable=True)
    applicant = User(username="applicant", password="x", enabled=True)
    approver = User(username="approver", password="x", enabled=True)
    db.session.add_all([organization, unit, source, location, applicant, approver])
    db.session.flush()
    category = AssetCategory(
        code="10100",
        name="笔记本电脑",
        service_life_months=36,
        default_unit_id=unit.id,
    )
    db.session.add(category)
    db.session.flush()

    operation = OperationRequest(
        request_no="STI202607170001",
        operation_type=OperationType.STOCK_IN.value,
        applicant_id=applicant.id,
        approval_status=ApprovalStatus.PENDING.value,
        execution_status=ExecutionStatus.NOT_STARTED.value,
        flow_version=1,
    )
    db.session.add(operation)
    db.session.flush()
    stock_in = StockInRequest(
        operation_request_id=operation.id, organization_id=organization.id
    )
    db.session.add(stock_in)
    db.session.flush()
    item = StockInItem(
        stock_in_request_id=stock_in.id,
        asset_code="358466-10100-0001",
        asset_name="MacBook Air",
        category_id=category.id,
        unit_id=unit.id,
        original_amount=Decimal("7999.00"),
        purchase_date=date(2026, 7, 17),
        manager_id=applicant.id,
        source_id=source.id,
        location_id=location.id,
    )
    sequence = AssetCodeSequence(
        top_organization_id=organization.id,
        category_id=category.id,
        current_value=1,
    )
    db.session.add_all([item, sequence])
    db.session.flush()
    reservation = AssetCodeReservation(
        operation_request_id=operation.id,
        stock_in_item_id=item.id,
        asset_code=item.asset_code,
        sequence_value=1,
        status=AssetCodeStatus.PENDING_STOCK_IN.value,
    )
    step = ApprovalStep(
        operation_request_id=operation.id,
        level_no=1,
        status=ApprovalStatus.PENDING.value,
    )
    db.session.add_all([reservation, step])
    db.session.flush()
    db.session.add(
        ApprovalTask(
            approval_step_id=step.id,
            approver_id=approver.id,
            status=ApprovalStatus.PENDING.value,
        )
    )
    db.session.flush()

    assert operation.execution_status == ExecutionStatus.NOT_STARTED.value
    assert item.asset_code == reservation.asset_code
    assert db.session.query(Asset).count() == 0


def test_formal_asset_has_independent_lifecycle_and_audit_records(app) -> None:
    organization = Organization(code="FORMAL", name="正式公司")
    unit = Unit(code="FORMAL_UNIT", name="件")
    source = AssetSource(code="FORMAL_SOURCE", name="赠送")
    location = AssetLocation(code="FORMAL_LOC", name="库房", is_selectable=True)
    manager = User(username="formal-manager", password="x", enabled=True)
    db.session.add_all([organization, unit, source, location, manager])
    db.session.flush()
    category = AssetCategory(
        code="FORMAL_CATEGORY",
        name="设备",
        service_life_months=12,
        default_unit_id=unit.id,
    )
    db.session.add(category)
    db.session.flush()
    asset = Asset(
        asset_code="FORMAL-FORMAL_CATEGORY-0001",
        asset_name="测试资产",
        status=AssetStatus.IDLE.value,
        organization_id=organization.id,
        category_id=category.id,
        unit_id=unit.id,
        original_amount=Decimal("0.00"),
        zero_amount_reason="赠送",
        purchase_date=date(2026, 7, 17),
        manager_id=manager.id,
        source_id=source.id,
        location_id=location.id,
        serial_number=" SN-001 ",
        normalized_serial="sn-001",
    )
    db.session.add(asset)
    db.session.flush()
    db.session.add_all(
        [
            AssetLifecycleRecord(
                asset_id=asset.id,
                operation_type="STOCK_IN",
                operation_no="STI-001",
                operator_id=manager.id,
                before_data=None,
                after_data={"status": "IDLE"},
            ),
            OperationLog(
                action="STOCK_IN",
                resource_type="asset",
                resource_id=str(asset.id),
                operator_id=manager.id,
                before_data=None,
                after_data={"asset_code": asset.asset_code},
            ),
        ]
    )
    db.session.flush()

    assert (
        db.session.query(AssetLifecycleRecord).filter_by(asset_id=asset.id).count() == 1
    )
    assert (
        db.session.query(OperationLog).filter_by(resource_id=str(asset.id)).count() == 1
    )


def test_approval_terminal_transition_is_compare_and_set(app) -> None:
    applicant = User(username="cas-applicant", password="x", enabled=True)
    db.session.add(applicant)
    db.session.flush()
    operation = OperationRequest(
        request_no="CAS-REQUEST",
        operation_type=OperationType.STOCK_IN.value,
        applicant_id=applicant.id,
        approval_status=ApprovalStatus.PENDING.value,
        execution_status=ExecutionStatus.NOT_STARTED.value,
        flow_version=1,
    )
    db.session.add(operation)
    db.session.flush()
    expected_version = operation.version

    assert operation_request_repository.transition_pending(
        operation.id, expected_version, ApprovalStatus.APPROVED.value
    )
    assert not operation_request_repository.transition_pending(
        operation.id, expected_version, ApprovalStatus.REJECTED.value
    )
    db.session.expire_all()

    persisted = db.session.get(OperationRequest, operation.id)
    assert persisted is not None
    assert persisted.approval_status == ApprovalStatus.APPROVED.value
    assert persisted.version == expected_version + 1


def test_only_one_terminal_approval_record_is_allowed_per_task() -> None:
    constraint_names = {
        constraint.name for constraint in ApprovalRecord.__table__.constraints
    }
    assert "uq_approval_record_task" in constraint_names
    assert "uq_approval_record_step" not in constraint_names


def test_pending_serial_reservation_has_a_unique_database_guard() -> None:
    column = StockInItem.__table__.columns["serial_reservation_key"]
    assert column.unique is True
