"""Handler registry and transactional operation executor contracts."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
import importlib

import app.services as services
import pytest
from app.common import BusinessException
from app.enums import (
    ApprovalChannel,
    ApprovalExecutionMode,
    ApprovalStatus,
    AssetDataCompleteness,
    AssetStatus,
    ExecutionStatus,
    ExecutionTriggerType,
)
from app.extensions import db
from app.models import (
    Asset,
    AssetBusinessLock,
    AssetCategory,
    AssetLifecycleRecord,
    AssetLocation,
    AssetSource,
    OperationExecutionAttempt,
    OperationLog,
    OperationRequestAsset,
    Organization,
    Unit,
    User,
)
from app.repositories.asset_repository import asset_repository


class StubHandler:
    operation_type = "TRANSFER"

    def __init__(self) -> None:
        self.fail = False
        self.executions = 0

    def revalidate_for_execution(self, operation_request_id: int) -> None:
        if self.fail:
            raise RuntimeError("mysql://root:secret@internal/execution")

    def execute(self, operation_request_id: int, actor_id: int) -> None:
        asset = db.session.query(Asset).one()
        asset.remark = f"executed-by-{actor_id}"
        self.executions += 1
        if self.fail:
            raise RuntimeError("secret internal table")


class AtomicCasConflictHandler:
    operation_type = "TRANSFER"
    safe_error_message = "资产版本冲突"

    def revalidate_for_execution(self, operation_request_id: int) -> None:
        return None

    def execute(self, operation_request_id: int, actor_id: int) -> None:
        snapshots = (
            db.session.query(OperationRequestAsset)
            .filter_by(operation_request_id=operation_request_id)
            .order_by(OperationRequestAsset.asset_id.asc())
            .all()
        )
        first, second = snapshots
        assert asset_repository.cas_update(
            first.asset_id,
            first.asset_version_snapshot,
            {"status": AssetStatus.IN_USE.value},
        )
        services.audit_service.record_asset_lifecycle(
            asset_id=first.asset_id,
            operation_type=self.operation_type,
            request_no="ATOMIC-CAS",
            actor_id=actor_id,
            before_data=first.before_data,
            after_data={"status": AssetStatus.IN_USE.value},
        )
        services.audit_service.record_operation(
            operation_request_id=operation_request_id,
            operation_type=self.operation_type,
            actor_id=actor_id,
            before_data={"asset_ids": [item.asset_id for item in snapshots]},
            after_data={"result": "SUCCESS"},
        )
        if not asset_repository.cas_update(
            second.asset_id,
            second.asset_version_snapshot + 1,
            {"status": AssetStatus.IN_USE.value},
        ):
            raise BusinessException("资产版本冲突")


def _registry():
    try:
        module = importlib.import_module("app.operations.registry")
    except ModuleNotFoundError as error:
        raise AssertionError("missing operation handler registry") from error
    return module.operation_handler_registry


def _executor():
    executor = getattr(services, "operation_executor", None)
    assert executor is not None, "missing operation_executor"
    return executor


def _seed_approved_operation(
    approval_execution_mode: str = ApprovalExecutionMode.AUTO_ON_APPROVAL.value,
) -> tuple[User, Asset, object]:
    organization = Organization(code="EXEC-ORG", name="执行组织")
    unit = Unit(code="EXEC-UNIT", name="执行单位")
    source = AssetSource(code="EXEC-SOURCE", name="执行来源")
    location = AssetLocation(code="EXEC-LOCATION", name="执行地点", is_selectable=True)
    actor = User(username="executor-actor", password="x", enabled=True)
    db.session.add_all([organization, unit, source, location, actor])
    db.session.flush()
    category = AssetCategory(
        code="EXEC-CATEGORY",
        name="执行分类",
        service_life_months=12,
        default_unit_id=unit.id,
    )
    db.session.add(category)
    db.session.flush()
    asset = Asset(
        asset_code="EXEC-ASSET",
        asset_name="执行资产",
        status=AssetStatus.IDLE.value,
        organization_id=organization.id,
        category_id=category.id,
        unit_id=unit.id,
        original_amount=Decimal("1.00"),
        purchase_date=date(2026, 7, 17),
        service_life_months=36,
        expected_expiry_date=date(2029, 1, 1),
        manager_id=actor.id,
        source_id=source.id,
        location_id=location.id,
        custom_attributes={},
        data_completeness=AssetDataCompleteness.COMPLETE.value,
    )
    db.session.add(asset)
    db.session.flush()
    operation = services.operation_service.create_request(
        operation_type="TRANSFER",
        applicant_id=actor.id,
        approval_channel=ApprovalChannel.INTERNAL.value,
        approval_execution_mode=approval_execution_mode,
        assets=[asset],
        target_data_by_asset_id={asset.id: {"location_id": asset.location_id}},
        idempotency_key="executor-request",
    ).operation
    operation.approval_status = ApprovalStatus.APPROVED.value
    db.session.commit()
    return actor, asset, operation


def test_registry_rejects_duplicates_and_missing_handlers(app) -> None:
    registry = _registry()
    registry.clear()
    handler = StubHandler()
    registry.register(handler)
    assert registry.get("TRANSFER") is handler
    try:
        registry.register(StubHandler())
    except BusinessException as error:
        assert "重复" in error.message
    else:
        raise AssertionError("duplicate handler should fail")
    try:
        registry.get("REPAIR")
    except BusinessException as error:
        assert "未注册" in error.message
    else:
        raise AssertionError("missing handler should fail")


def test_success_is_idempotent_and_releases_locks(app) -> None:
    actor, asset, operation = _seed_approved_operation()
    handler = StubHandler()
    registry = _registry()
    registry.clear()
    registry.register(handler)

    executed = _executor().execute(
        operation.id, actor.id, ExecutionTriggerType.APPROVAL.value
    )
    assert executed.execution_status == ExecutionStatus.SUCCESS.value
    assert db.session.get(Asset, asset.id).remark == f"executed-by-{actor.id}"
    assert db.session.query(OperationExecutionAttempt).one().status == "SUCCESS"
    assert db.session.query(AssetBusinessLock).count() == 0

    repeated = _executor().execute(
        operation.id, actor.id, ExecutionTriggerType.APPROVAL.value
    )
    assert repeated.execution_status == ExecutionStatus.SUCCESS.value
    assert handler.executions == 1
    assert db.session.query(OperationExecutionAttempt).count() == 1


def test_manual_confirmation_waits_then_executes_once(app) -> None:
    actor, _asset, operation = _seed_approved_operation(
        ApprovalExecutionMode.MANUAL_CONFIRM.value
    )
    handler = StubHandler()
    registry = _registry()
    registry.clear()
    registry.register(handler)

    waiting = _executor().execute_after_approval(operation.id, actor.id)
    assert waiting.execution_status == ExecutionStatus.NOT_STARTED.value
    assert db.session.query(OperationExecutionAttempt).count() == 0
    assert db.session.query(AssetBusinessLock).count() == 1

    completed = _executor().confirm(operation.id, actor.id)
    assert completed.execution_status == ExecutionStatus.SUCCESS.value
    assert handler.executions == 1
    assert db.session.query(OperationExecutionAttempt).count() == 1
    assert db.session.query(AssetBusinessLock).count() == 0

    repeated = _executor().confirm(operation.id, actor.id)
    assert repeated.execution_status == ExecutionStatus.SUCCESS.value
    assert handler.executions == 1
    assert db.session.query(OperationExecutionAttempt).count() == 1


@pytest.mark.parametrize(
    ("mode", "trigger"),
    [
        (
            ApprovalExecutionMode.MANUAL_CONFIRM.value,
            ExecutionTriggerType.APPROVAL.value,
        ),
        (
            ApprovalExecutionMode.AUTO_ON_APPROVAL.value,
            ExecutionTriggerType.CONFIRMATION.value,
        ),
    ],
)
def test_illegal_execution_mode_trigger_creates_no_attempt(
    app, mode: str, trigger: str
) -> None:
    actor, _asset, operation = _seed_approved_operation(mode)
    registry = _registry()
    registry.clear()
    registry.register(StubHandler())

    with pytest.raises(BusinessException):
        _executor().execute(operation.id, actor.id, trigger)

    assert db.session.query(OperationExecutionAttempt).count() == 0
    assert db.session.query(AssetBusinessLock).count() == 1


def test_failure_rolls_back_business_data_persists_safe_attempt_and_can_retry(
    app,
) -> None:
    actor, asset, operation = _seed_approved_operation()
    handler = StubHandler()
    handler.fail = True
    registry = _registry()
    registry.clear()
    registry.register(handler)

    failed = _executor().execute(
        operation.id, actor.id, ExecutionTriggerType.APPROVAL.value
    )
    assert failed.execution_status == ExecutionStatus.FAILED.value
    assert db.session.get(Asset, asset.id).remark is None
    attempt = db.session.query(OperationExecutionAttempt).one()
    assert attempt.status == "FAILED"
    assert attempt.error_code == "EXECUTION_FAILED"
    assert "secret" not in (attempt.safe_error_message or "")
    assert db.session.query(AssetBusinessLock).count() == 1

    handler.fail = False
    retried = _executor().retry(operation.id, actor.id)
    assert retried.execution_status == ExecutionStatus.SUCCESS.value
    assert [
        item.attempt_no
        for item in db.session.query(OperationExecutionAttempt).order_by(
            OperationExecutionAttempt.attempt_no
        )
    ] == [1, 2]
    assert db.session.query(AssetBusinessLock).count() == 0


def test_cas_conflict_rolls_back_whole_batch_and_success_audit(app) -> None:
    actor, first, operation = _seed_approved_operation()
    second = Asset(
        asset_code="EXEC-ASSET-SECOND",
        asset_name="执行资产2",
        status=AssetStatus.IDLE.value,
        organization_id=first.organization_id,
        category_id=first.category_id,
        unit_id=first.unit_id,
        original_amount=Decimal("1.00"),
        purchase_date=date(2026, 7, 17),
        service_life_months=36,
        expected_expiry_date=date(2029, 1, 1),
        manager_id=actor.id,
        source_id=first.source_id,
        location_id=first.location_id,
        custom_attributes={},
        data_completeness=AssetDataCompleteness.COMPLETE.value,
    )
    db.session.add(second)
    db.session.flush()
    db.session.add(
        OperationRequestAsset(
            operation_request_id=operation.id,
            asset_id=second.id,
            asset_code_snapshot=second.asset_code,
            asset_name_snapshot=second.asset_name,
            asset_status_snapshot=second.status,
            asset_version_snapshot=second.version,
            organization_id_snapshot=second.organization_id,
            before_data={"status": second.status, "version": second.version},
            target_data={"status": AssetStatus.IN_USE.value},
        )
    )
    db.session.add(
        AssetBusinessLock(
            asset_id=second.id,
            operation_request_id=operation.id,
            operation_type=operation.operation_type,
            applicant_id=operation.applicant_id,
        )
    )
    db.session.commit()
    registry = _registry()
    registry.clear()
    registry.register(AtomicCasConflictHandler())

    failed = _executor().execute(
        operation.id,
        actor.id,
        ExecutionTriggerType.APPROVAL.value,
    )

    assert failed.execution_status == ExecutionStatus.FAILED.value
    db.session.expire_all()
    persisted = [db.session.get(Asset, asset_id) for asset_id in (first.id, second.id)]
    assert all(asset is not None for asset in persisted)
    assert [asset.status for asset in persisted if asset is not None] == [
        AssetStatus.IDLE.value,
        AssetStatus.IDLE.value,
    ]
    assert [asset.version for asset in persisted if asset is not None] == [1, 1]
    assert db.session.query(AssetLifecycleRecord).count() == 0
    assert db.session.query(OperationLog).count() == 0
    attempt = db.session.query(OperationExecutionAttempt).one()
    assert attempt.status == "FAILED"
    assert db.session.query(AssetBusinessLock).count() == 2


def test_only_approved_requests_execute_and_failed_requests_can_terminate(app) -> None:
    actor, _asset, operation = _seed_approved_operation()
    handler = StubHandler()
    registry = _registry()
    registry.clear()
    registry.register(handler)
    operation.approval_status = ApprovalStatus.PENDING.value
    db.session.commit()
    try:
        _executor().execute(operation.id, actor.id, ExecutionTriggerType.APPROVAL.value)
    except BusinessException as error:
        assert "审批通过" in error.message
    else:
        raise AssertionError("pending request should not execute")

    operation.approval_status = ApprovalStatus.APPROVED.value
    operation.execution_status = ExecutionStatus.FAILED.value
    db.session.commit()
    terminated = _executor().terminate(operation.id, actor.id, "无法继续执行")
    assert terminated.execution_status == ExecutionStatus.TERMINATED.value
    assert terminated.termination_reason == "无法继续执行"
    assert terminated.terminated_by == actor.id
    assert db.session.query(AssetBusinessLock).count() == 0
