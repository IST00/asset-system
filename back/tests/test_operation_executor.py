"""Handler registry and transactional operation executor contracts."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
import importlib

import app.services as services
from app.common import BusinessException
from app.enums import (
    ApprovalChannel,
    ApprovalStatus,
    AssetStatus,
    ExecutionStatus,
    ExecutionTriggerType,
)
from app.extensions import db
from app.models import (
    Asset,
    AssetBusinessLock,
    AssetCategory,
    AssetLocation,
    AssetSource,
    OperationExecutionAttempt,
    Organization,
    Unit,
    User,
)


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


def _seed_approved_operation() -> tuple[User, Asset, object]:
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
        manager_id=actor.id,
        source_id=source.id,
        location_id=location.id,
    )
    db.session.add(asset)
    db.session.flush()
    operation = services.operation_service.create_request(
        operation_type="TRANSFER",
        applicant_id=actor.id,
        approval_channel=ApprovalChannel.INTERNAL.value,
        organization_id=organization.id,
        assets=[asset],
        idempotency_key="executor-request",
    )
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
