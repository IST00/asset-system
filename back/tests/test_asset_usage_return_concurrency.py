"""Concurrency, rollback, and idempotency proofs for usage and return flows."""

from __future__ import annotations

import importlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event, local
from types import ModuleType
from typing import Any

import pytest
from flask import Flask

from app import create_app
from app.common import BusinessException
from app.enums import (
    ApprovalChannel,
    ApprovalExecutionMode,
    ApprovalStatus,
    AssetStatus,
    DataScope,
    ExecutionStatus,
    RecordStatus,
    UsageType,
)
from app.extensions import db
from app.models.asset import Asset
from app.models.master_data import AssetLocation
from app.models.asset_usage_return import (
    AssetReturnItem,
    AssetReturnRequest,
    AssetUsageRequest,
)
from app.models.audit import AssetLifecycleRecord, OperationLog
from app.models.operation import (
    AssetBusinessLock,
    ExternalApprovalEvent,
    OperationActionIdempotency,
    OperationExecutionAttempt,
    OperationRequestAsset,
)
from app.models.workflow import OperationRequest
from app.models.user import User
from app.operations.registry import operation_handler_registry
from app.repositories.asset_repository import asset_repository
from app.services import approval_provider_service
from asset_usage_return_fixtures import (
    UsageReturnContext,
    grant_permissions,
    register_usage_return_handlers,
    seed_usage_return_context,
)
from config import TestConfig


def _usage_service() -> ModuleType:
    return importlib.import_module("app.services.asset_usage_service")


def _return_service() -> ModuleType:
    return importlib.import_module("app.services.asset_return_service")


def _concurrent_app(tmp_path: Path, database_name: str) -> Flask:
    database = tmp_path / database_name

    class ConcurrentConfig(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{database}"

    return create_app(config=ConcurrentConfig)


def _grant_usage_manage(context: UsageReturnContext) -> None:
    grant_permissions(context.manager, "asset:usage:manage")


def _grant_personal_return(context: UsageReturnContext) -> None:
    role = grant_permissions(context.employee, "asset:return:self")
    role.data_scope = DataScope.SELF.value
    grant_permissions(context.manager, "asset:usage:manage")


def _set_personal_in_use(context: UsageReturnContext) -> None:
    for asset in (context.main_asset, context.child_asset):
        asset.status = AssetStatus.IN_USE.value
        asset.usage_type = UsageType.PERSONAL.value
        asset.holder_user_id = context.employee.id
        asset.public_object_id = None
        asset.usage_department_id = context.organization.id
    db.session.flush()


def _personal_usage_payload(
    main_asset_id: int,
    target_user_id: int,
    idempotency_key: str,
) -> dict[str, Any]:
    return {
        "asset_ids": [main_asset_id],
        "target_user_id": target_user_id,
        "idempotency_key": idempotency_key,
    }


def _personal_return_payload(
    main_asset_id: int,
    idempotency_key: str,
) -> dict[str, Any]:
    return {
        "asset_ids": [main_asset_id],
        "idempotency_key": idempotency_key,
    }


def _inspection_payload(
    main_asset_id: int,
    child_asset_id: int,
    return_location_id: int,
    idempotency_key: str,
) -> dict[str, Any]:
    return {
        "return_location_id": return_location_id,
        "idempotency_key": idempotency_key,
        "items": [
            {"asset_id": main_asset_id, "condition": "NORMAL"},
            {
                "asset_id": child_asset_id,
                "condition": "DAMAGED",
                "condition_description": "  外壳划痕  ",
            },
        ],
    }


def _asset_state(asset: Asset) -> dict[str, object]:
    return {
        "status": asset.status,
        "organization_id": asset.organization_id,
        "usage_type": asset.usage_type,
        "holder_user_id": asset.holder_user_id,
        "public_object_id": asset.public_object_id,
        "usage_department_id": asset.usage_department_id,
        "location_id": asset.location_id,
        "manager_id": asset.manager_id,
        "parent_asset_id": asset.parent_asset_id,
        "version": asset.version,
    }


def _asset_states(asset_ids: list[int]) -> dict[int, dict[str, object]]:
    db.session.expire_all()
    rows = [db.session.get(Asset, asset_id) for asset_id in asset_ids]
    assert all(row is not None for row in rows)
    return {row.id: _asset_state(row) for row in rows if row is not None}


def _register_handlers() -> None:
    operation_handler_registry.clear()
    register_usage_return_handlers()


def _assert_safe_failed_usage_attempt() -> None:
    attempt = db.session.query(OperationExecutionAttempt).one()
    handler_module = importlib.import_module(
        "app.operations.asset_usage_return_handlers"
    )
    assert attempt.status == "FAILED"
    assert attempt.error_code == "EXECUTION_FAILED"
    assert attempt.safe_error_message == (
        handler_module.PersonalUsageHandler.safe_error_message
    )


class _ManualConfirmNoopHandler:
    operation_type = "TASK8_EXECUTOR_PROOF"

    def revalidate_for_execution(self, operation_request_id: int) -> None:
        return None

    def execute(self, operation_request_id: int, actor_id: int) -> None:
        return None


class _CommitFailureHandler:
    operation_type = "TASK8_COMMIT_FAILURE"
    safe_error_message = "执行提交失败，请联系管理员或稍后重试"

    def __init__(self, asset_id: int) -> None:
        self.asset_id = asset_id

    def revalidate_for_execution(self, operation_request_id: int) -> None:
        return None

    def execute(self, operation_request_id: int, actor_id: int) -> None:
        asset = db.session.get(Asset, self.asset_id)
        assert asset is not None
        asset.remark = "must-roll-back-after-commit-failure"


def test_concurrent_personal_usage_submission_replays_one_aggregate(
    tmp_path: Path,
) -> None:
    concurrent_app = _concurrent_app(tmp_path, "usage-submit.db")
    with concurrent_app.app_context():
        db.create_all()
        context = seed_usage_return_context()
        _grant_usage_manage(context)
        db.session.commit()
        manager_id = context.manager.id
        employee_id = context.employee.id
        main_asset_id = context.main_asset.id

    barrier = Barrier(2)

    def submit() -> int:
        with concurrent_app.app_context():
            barrier.wait()
            result = _usage_service().submit_personal(
                _personal_usage_payload(
                    main_asset_id,
                    employee_id,
                    "concurrent-personal-usage",
                ),
                manager_id,
            )
            return result["id"]

    with ThreadPoolExecutor(max_workers=2) as executor:
        operation_ids = list(executor.map(lambda _index: submit(), range(2)))

    assert operation_ids[0] == operation_ids[1]
    with concurrent_app.app_context():
        operation = db.session.get(OperationRequest, operation_ids[0])
        assert operation is not None
        assert operation.approval_status == ApprovalStatus.PENDING.value
        assert operation.execution_status == ExecutionStatus.NOT_STARTED.value
        assert db.session.query(OperationRequest).count() == 1
        assert db.session.query(AssetUsageRequest).count() == 1
        assert db.session.query(OperationRequestAsset).count() == 2
        assert db.session.query(AssetBusinessLock).count() == 2
        assert db.session.query(OperationExecutionAttempt).count() == 0
        assert db.session.query(AssetLifecycleRecord).count() == 0
        assert db.session.query(OperationLog).count() == 0
        db.drop_all()


def test_concurrent_duplicate_feishu_approval_executes_once(tmp_path: Path) -> None:
    concurrent_app = _concurrent_app(tmp_path, "duplicate-approval.db")
    with concurrent_app.app_context():
        db.create_all()
        context = seed_usage_return_context()
        _grant_usage_manage(context)
        _register_handlers()
        submitted = _usage_service().submit_personal(
            _personal_usage_payload(
                context.main_asset.id,
                context.employee.id,
                "duplicate-approval-usage",
            ),
            context.manager.id,
        )
        operation_id = submitted["id"]
        manager_id = context.manager.id
        employee_id = context.employee.id
        organization_id = context.organization.id
        asset_ids = [context.main_asset.id, context.child_asset.id]
        asset_locations = {
            context.main_asset.id: context.main_asset.location_id,
            context.child_asset.id: context.child_asset.location_id,
        }
        external_instance_id = submitted["external_instance_id"]

    barrier = Barrier(2)

    def approve() -> int:
        with concurrent_app.app_context():
            barrier.wait()
            result = approval_provider_service.handle_callback(
                provider="FEISHU",
                external_event_id="same-personal-usage-approved-event",
                external_instance_id=external_instance_id,
                status=ApprovalStatus.APPROVED.value,
                actor_id=manager_id,
            )
            return result.id

    with ThreadPoolExecutor(max_workers=2) as executor:
        operation_ids = list(executor.map(lambda _index: approve(), range(2)))

    assert operation_ids[0] == operation_ids[1] == operation_id
    with concurrent_app.app_context():
        operation = db.session.get(OperationRequest, operation_id)
        assert operation is not None
        assert operation.approval_status == ApprovalStatus.APPROVED.value
        assert operation.execution_status == ExecutionStatus.SUCCESS.value
        event = db.session.query(ExternalApprovalEvent).one()
        assert event.processing_status == "PROCESSED"
        assert db.session.query(OperationExecutionAttempt).count() == 1
        assert db.session.query(OperationExecutionAttempt).one().status == "SUCCESS"
        assert db.session.query(AssetLifecycleRecord).count() == 2
        assert db.session.query(OperationLog).count() == 1
        assert db.session.query(AssetBusinessLock).count() == 0
        assets = [db.session.get(Asset, asset_id) for asset_id in asset_ids]
        assert all(asset is not None for asset in assets)
        for asset in assets:
            assert asset is not None
            assert asset.status == AssetStatus.IN_USE.value
            assert asset.usage_type == UsageType.PERSONAL.value
            assert asset.holder_user_id == employee_id
            assert asset.public_object_id is None
            assert asset.usage_department_id == organization_id
            assert asset.location_id == asset_locations[asset.id]
            assert asset.version == 2
        db.drop_all()


def test_concurrent_duplicate_personal_return_confirmation_replays_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    concurrent_app = _concurrent_app(tmp_path, "duplicate-return-confirm.db")
    with concurrent_app.app_context():
        db.create_all()
        context = seed_usage_return_context()
        _set_personal_in_use(context)
        _grant_personal_return(context)
        _register_handlers()
        db.session.commit()
        service = _return_service()
        submitted = service.submit_personal(
            _personal_return_payload(
                context.main_asset.id,
                "concurrent-return-submission",
            ),
            context.employee.id,
        )
        approved = approval_provider_service.handle_callback(
            provider="FEISHU",
            external_event_id="concurrent-return-approved",
            external_instance_id=submitted["external_instance_id"],
            status=ApprovalStatus.APPROVED.value,
            actor_id=context.manager.id,
        )
        assert approved.execution_status == ExecutionStatus.NOT_STARTED.value
        assert db.session.query(AssetBusinessLock).count() == 2
        operation_id = submitted["id"]
        manager_id = context.manager.id
        main_asset_id = context.main_asset.id
        child_asset_id = context.child_asset.id
        return_location_id = context.return_location.id

    service = _return_service()
    original_claim = service._claim_and_apply_inspection
    claim_barrier = Barrier(2)

    def synchronized_claim(*args: Any, **kwargs: Any) -> bool:
        claim_barrier.wait()
        return original_claim(*args, **kwargs)

    monkeypatch.setattr(service, "_claim_and_apply_inspection", synchronized_claim)

    def confirm() -> int:
        with concurrent_app.app_context():
            result = service.confirm(
                operation_id,
                _inspection_payload(
                    main_asset_id,
                    child_asset_id,
                    return_location_id,
                    "concurrent-return-confirmation",
                ),
                manager_id,
            )
            return result["id"]

    with ThreadPoolExecutor(max_workers=2) as executor:
        operation_ids = list(executor.map(lambda _index: confirm(), range(2)))

    assert operation_ids[0] == operation_ids[1] == operation_id
    with concurrent_app.app_context():
        operation = db.session.get(OperationRequest, operation_id)
        assert operation is not None
        assert operation.execution_status == ExecutionStatus.SUCCESS.value
        claim = db.session.query(OperationActionIdempotency).one()
        assert claim.status == "COMPLETED"
        assert db.session.query(OperationExecutionAttempt).count() == 1
        assert db.session.query(OperationExecutionAttempt).one().status == "SUCCESS"
        assert db.session.query(AssetLifecycleRecord).count() == 2
        assert db.session.query(OperationLog).count() == 1
        assert db.session.query(AssetBusinessLock).count() == 0
        detail = db.session.query(AssetReturnRequest).one()
        assert detail.confirmed_by == manager_id
        assert detail.return_location_id == return_location_id
        assert getattr(detail, "return_location_snapshot", None) == {
            "id": return_location_id,
            "code": "UR-RETURN-LOCATION",
            "name": "UR Return Location",
        }
        assert getattr(detail, "confirmed_by_snapshot", None) == {
            "id": manager_id,
            "username": "UR-manager",
            "name": "UR Manager",
        }
        items = db.session.query(AssetReturnItem).order_by(AssetReturnItem.id).all()
        assert [item.condition for item in items] == ["NORMAL", "DAMAGED"]
        assert [item.condition_description for item in items] == [None, "外壳划痕"]
        states = _asset_states([main_asset_id, child_asset_id])
        for state in states.values():
            assert state["status"] == AssetStatus.IDLE.value
            assert state["usage_type"] is None
            assert state["holder_user_id"] is None
            assert state["public_object_id"] is None
            assert state["usage_department_id"] is None
            assert state["location_id"] == return_location_id
            assert state["version"] == 2
        db.drop_all()


def test_concurrent_conflicting_return_confirmations_persist_one_winner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    concurrent_app = _concurrent_app(tmp_path, "conflicting-return-confirm.db")
    with concurrent_app.app_context():
        db.create_all()
        context = seed_usage_return_context()
        _set_personal_in_use(context)
        _grant_personal_return(context)
        second_manager = User(
            username="UR-second-manager",
            password="x",
            nickname="UR Second Manager",
            organization_id=context.organization.id,
            enabled=True,
        )
        second_location = AssetLocation(
            code="UR-SECOND-RETURN-LOCATION",
            name="UR Second Return Location",
            status=RecordStatus.ENABLED.value,
            is_selectable=True,
        )
        db.session.add_all([second_manager, second_location])
        db.session.flush()
        grant_permissions(second_manager, "asset:usage:manage")
        _register_handlers()
        db.session.commit()
        service = _return_service()
        submitted = service.submit_personal(
            _personal_return_payload(
                context.main_asset.id,
                "conflicting-return-submission",
            ),
            context.employee.id,
        )
        approved = approval_provider_service.handle_callback(
            provider="FEISHU",
            external_event_id="conflicting-return-approved",
            external_instance_id=submitted["external_instance_id"],
            status=ApprovalStatus.APPROVED.value,
            actor_id=context.manager.id,
        )
        assert approved.execution_status == ExecutionStatus.NOT_STARTED.value
        operation_id = submitted["id"]
        main_asset_id = context.main_asset.id
        child_asset_id = context.child_asset.id
        competitors: dict[str, dict[str, Any]] = {
            "primary": {
                "actor_id": context.manager.id,
                "idempotency_key": "conflicting-confirm-primary",
                "return_location_id": context.return_location.id,
                "return_location_snapshot": {
                    "id": context.return_location.id,
                    "code": context.return_location.code,
                    "name": context.return_location.name,
                },
                "confirmed_by_snapshot": {
                    "id": context.manager.id,
                    "username": context.manager.username,
                    "name": context.manager.nickname,
                },
                "items": [
                    {"asset_id": main_asset_id, "condition": "NORMAL"},
                    {
                        "asset_id": child_asset_id,
                        "condition": "DAMAGED",
                        "condition_description": "外壳划痕",
                    },
                ],
            },
            "secondary": {
                "actor_id": second_manager.id,
                "idempotency_key": "conflicting-confirm-secondary",
                "return_location_id": second_location.id,
                "return_location_snapshot": {
                    "id": second_location.id,
                    "code": second_location.code,
                    "name": second_location.name,
                },
                "confirmed_by_snapshot": {
                    "id": second_manager.id,
                    "username": second_manager.username,
                    "name": second_manager.nickname,
                },
                "items": [
                    {
                        "asset_id": main_asset_id,
                        "condition": "DAMAGED",
                        "condition_description": "机身裂纹",
                    },
                    {"asset_id": child_asset_id, "condition": "NORMAL"},
                ],
            },
        }

    service = _return_service()
    original_claim = service._claim_and_apply_inspection
    claim_barrier = Barrier(2)

    def synchronized_claim(*args: Any, **kwargs: Any) -> bool:
        claim_barrier.wait()
        return original_claim(*args, **kwargs)

    monkeypatch.setattr(service, "_claim_and_apply_inspection", synchronized_claim)

    def confirm(label: str) -> tuple[str, str, str]:
        competitor = competitors[label]
        with concurrent_app.app_context():
            try:
                result = service.confirm(
                    operation_id,
                    {
                        "return_location_id": competitor["return_location_id"],
                        "idempotency_key": competitor["idempotency_key"],
                        "items": competitor["items"],
                    },
                    competitor["actor_id"],
                )
            except BusinessException as error:
                return label, "conflict", error.message
            return label, "success", str(result["execution_status"])

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(confirm, competitors))

    successes = [label for label, status, _result in results if status == "success"]
    conflicts = [
        (label, result) for label, status, result in results if status == "conflict"
    ]
    assert len(successes) == 1
    assert len(conflicts) == 1
    assert conflicts[0][1] == "退库申请已由其他验收请求确认"
    winner = competitors[successes[0]]
    assert (
        next(result for label, status, result in results if label == successes[0])
        == ExecutionStatus.SUCCESS.value
    )

    with concurrent_app.app_context():
        detail = db.session.query(AssetReturnRequest).one()
        assert detail.return_location_id == winner["return_location_id"]
        assert detail.return_location_snapshot == winner["return_location_snapshot"]
        assert detail.confirmed_by == winner["actor_id"]
        assert detail.confirmed_by_snapshot == winner["confirmed_by_snapshot"]
        assert detail.confirmed_at is not None

        snapshots = db.session.query(OperationRequestAsset).all()
        asset_id_by_snapshot_id = {row.id: row.asset_id for row in snapshots}
        persisted_items = {
            asset_id_by_snapshot_id[item.operation_request_asset_id]: {
                "asset_id": asset_id_by_snapshot_id[item.operation_request_asset_id],
                "condition": item.condition,
                "condition_description": item.condition_description,
            }
            for item in db.session.query(AssetReturnItem).all()
        }
        assert persisted_items == {
            item["asset_id"]: {
                "asset_id": item["asset_id"],
                "condition": item["condition"],
                "condition_description": item.get("condition_description"),
            }
            for item in winner["items"]
        }

        action = db.session.query(OperationActionIdempotency).one()
        assert action.actor_id == winner["actor_id"]
        assert action.idempotency_key == winner["idempotency_key"]
        assert action.status == "COMPLETED"
        attempt = db.session.query(OperationExecutionAttempt).one()
        assert attempt.triggered_by == winner["actor_id"]
        lifecycle_rows = db.session.query(AssetLifecycleRecord).all()
        assert len(lifecycle_rows) == 2
        assert all(row.operator_id == winner["actor_id"] for row in lifecycle_rows)
        operation_log = db.session.query(OperationLog).one()
        assert operation_log.operator_id == winner["actor_id"]
        assert db.session.query(AssetBusinessLock).count() == 0

        states = _asset_states([main_asset_id, child_asset_id])
        for state in states.values():
            assert state["status"] == AssetStatus.IDLE.value
            assert state["location_id"] == winner["return_location_id"]
            assert state["version"] == 2
        db.drop_all()


def test_confirmation_creator_converges_when_replay_wins_execution_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    concurrent_app = _concurrent_app(tmp_path, "return-replay-wins-execution.db")
    with concurrent_app.app_context():
        db.create_all()
        context = seed_usage_return_context()
        _set_personal_in_use(context)
        _grant_personal_return(context)
        _register_handlers()
        db.session.commit()
        service = _return_service()
        submitted = service.submit_personal(
            _personal_return_payload(
                context.main_asset.id,
                "return-replay-wins-submission",
            ),
            context.employee.id,
        )
        approved = approval_provider_service.handle_callback(
            provider="FEISHU",
            external_event_id="return-replay-wins-approved",
            external_instance_id=submitted["external_instance_id"],
            status=ApprovalStatus.APPROVED.value,
            actor_id=context.manager.id,
        )
        assert approved.execution_status == ExecutionStatus.NOT_STARTED.value
        operation_id = submitted["id"]
        manager_id = context.manager.id
        main_asset_id = context.main_asset.id
        child_asset_id = context.child_asset.id
        return_location_id = context.return_location.id

    service = _return_service()
    from app.services import operation_executor

    original_inspection_claim = service._claim_and_apply_inspection
    original_executor_confirm = operation_executor.confirm
    roles = local()
    creator_claimed_inspection = Event()
    creator_entered_executor = Event()
    replay_finished_executor = Event()

    def scheduled_inspection_claim(*args: Any, **kwargs: Any) -> bool:
        if roles.value == "creator":
            claimed = original_inspection_claim(*args, **kwargs)
            assert claimed
            creator_claimed_inspection.set()
            return claimed
        assert creator_claimed_inspection.wait(timeout=5)
        claimed = original_inspection_claim(*args, **kwargs)
        assert not claimed
        return claimed

    def scheduled_executor_confirm(
        operation_request_id: int,
        actor_id: int,
    ) -> OperationRequest:
        if roles.value == "creator":
            creator_entered_executor.set()
            assert replay_finished_executor.wait(timeout=5)
            return original_executor_confirm(operation_request_id, actor_id)
        assert creator_entered_executor.wait(timeout=5)
        try:
            return original_executor_confirm(operation_request_id, actor_id)
        finally:
            replay_finished_executor.set()

    monkeypatch.setattr(
        service,
        "_claim_and_apply_inspection",
        scheduled_inspection_claim,
    )
    monkeypatch.setattr(
        operation_executor,
        "confirm",
        scheduled_executor_confirm,
    )

    start = Barrier(2)

    def confirm(role: str) -> str:
        roles.value = role
        with concurrent_app.app_context():
            start.wait()
            result = service.confirm(
                operation_id,
                _inspection_payload(
                    main_asset_id,
                    child_asset_id,
                    return_location_id,
                    "return-replay-wins-confirmation",
                ),
                manager_id,
            )
            return str(result["execution_status"])

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(confirm, ["creator", "replay"]))

    assert statuses == [ExecutionStatus.SUCCESS.value] * 2
    with concurrent_app.app_context():
        operation = db.session.get(OperationRequest, operation_id)
        assert operation is not None
        assert operation.execution_status == ExecutionStatus.SUCCESS.value
        assert db.session.query(OperationExecutionAttempt).count() == 1
        assert db.session.query(AssetLifecycleRecord).count() == 2
        assert db.session.query(OperationLog).count() == 1
        assert db.session.query(AssetBusinessLock).count() == 0
        claim = db.session.query(OperationActionIdempotency).one()
        assert claim.status == "COMPLETED"
        db.drop_all()


def test_second_asset_cas_failure_rolls_back_entire_usage_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    concurrent_app = _concurrent_app(tmp_path, "usage-cas-rollback.db")
    with concurrent_app.app_context():
        db.create_all()
        context = seed_usage_return_context()
        _grant_usage_manage(context)
        _register_handlers()
        submitted = _usage_service().submit_personal(
            _personal_usage_payload(
                context.main_asset.id,
                context.employee.id,
                "usage-second-cas-failure",
            ),
            context.manager.id,
        )
        operation_id = submitted["id"]
        manager_id = context.manager.id
        external_instance_id = submitted["external_instance_id"]
        asset_ids = [context.main_asset.id, context.child_asset.id]
        original_states = _asset_states(asset_ids)

        original_cas_update = asset_repository.cas_update
        call_count = 0

        def fail_second_cas(
            asset_id: int,
            expected_version: int,
            changes: dict[str, object],
        ) -> bool:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                return False
            return original_cas_update(asset_id, expected_version, changes)

        monkeypatch.setattr(asset_repository, "cas_update", fail_second_cas)
        result = approval_provider_service.handle_callback(
            provider="FEISHU",
            external_event_id="usage-second-cas-failure-approved",
            external_instance_id=external_instance_id,
            status=ApprovalStatus.APPROVED.value,
            actor_id=manager_id,
        )

        assert call_count == 2
        assert result.id == operation_id
        assert result.approval_status == ApprovalStatus.APPROVED.value
        assert result.execution_status == ExecutionStatus.FAILED.value
        assert _asset_states(asset_ids) == original_states
        assert db.session.query(AssetLifecycleRecord).count() == 0
        assert db.session.query(OperationLog).count() == 0
        _assert_safe_failed_usage_attempt()
        assert db.session.query(AssetBusinessLock).count() == 2
        db.drop_all()


def test_version_change_before_approval_fails_safely_and_keeps_locks(
    tmp_path: Path,
) -> None:
    concurrent_app = _concurrent_app(tmp_path, "usage-version-change.db")
    with concurrent_app.app_context():
        db.create_all()
        context = seed_usage_return_context()
        _grant_usage_manage(context)
        _register_handlers()
        submitted = _usage_service().submit_personal(
            _personal_usage_payload(
                context.main_asset.id,
                context.employee.id,
                "usage-version-change",
            ),
            context.manager.id,
        )
        operation_id = submitted["id"]
        manager_id = context.manager.id
        external_instance_id = submitted["external_instance_id"]
        main_asset_id = context.main_asset.id
        child_asset_id = context.child_asset.id
        original_states = _asset_states([main_asset_id, child_asset_id])
        child = db.session.get(Asset, child_asset_id)
        assert child is not None
        child.version += 1
        db.session.commit()
        externally_changed_states = _asset_states([main_asset_id, child_asset_id])

        result = approval_provider_service.handle_callback(
            provider="FEISHU",
            external_event_id="usage-version-change-approved",
            external_instance_id=external_instance_id,
            status=ApprovalStatus.APPROVED.value,
            actor_id=manager_id,
        )

        assert result.id == operation_id
        assert result.approval_status == ApprovalStatus.APPROVED.value
        assert result.execution_status == ExecutionStatus.FAILED.value
        persisted_states = _asset_states([main_asset_id, child_asset_id])
        assert persisted_states[main_asset_id] == original_states[main_asset_id]
        assert (
            persisted_states[child_asset_id]
            == externally_changed_states[child_asset_id]
        )
        assert persisted_states[child_asset_id]["version"] == (
            original_states[child_asset_id]["version"] + 1
        )
        assert db.session.query(AssetLifecycleRecord).count() == 0
        assert db.session.query(OperationLog).count() == 0
        _assert_safe_failed_usage_attempt()
        assert db.session.query(AssetBusinessLock).count() == 2
        db.drop_all()


@pytest.mark.parametrize("terminal_status", ["REJECTED", "WITHDRAWN"])
def test_rejected_and_withdrawn_personal_returns_have_no_asset_side_effects(
    tmp_path: Path,
    terminal_status: str,
) -> None:
    concurrent_app = _concurrent_app(
        tmp_path,
        f"return-{terminal_status.lower()}.db",
    )
    with concurrent_app.app_context():
        db.create_all()
        context = seed_usage_return_context()
        _set_personal_in_use(context)
        _grant_personal_return(context)
        db.session.commit()
        submitted = _return_service().submit_personal(
            _personal_return_payload(
                context.main_asset.id,
                f"return-{terminal_status.lower()}",
            ),
            context.employee.id,
        )
        operation_id = submitted["id"]
        asset_ids = [context.main_asset.id, context.child_asset.id]
        original_states = _asset_states(asset_ids)

        if terminal_status == ApprovalStatus.REJECTED.value:
            result = approval_provider_service.handle_callback(
                provider="FEISHU",
                external_event_id="personal-return-rejected",
                external_instance_id=submitted["external_instance_id"],
                status=ApprovalStatus.REJECTED.value,
                actor_id=context.manager.id,
            )
        else:
            result = approval_provider_service.withdraw(
                operation_id,
                context.employee.id,
            )

        assert result.id == operation_id
        assert result.approval_status == terminal_status
        assert result.execution_status == ExecutionStatus.NOT_STARTED.value
        assert _asset_states(asset_ids) == original_states
        assert db.session.query(AssetBusinessLock).count() == 0
        assert db.session.query(OperationExecutionAttempt).count() == 0
        assert db.session.query(AssetLifecycleRecord).count() == 0
        assert db.session.query(OperationLog).count() == 0
        db.drop_all()


def test_common_executor_concurrent_manual_confirmation_executes_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    concurrent_app = _concurrent_app(tmp_path, "common-executor-proof.db")
    with concurrent_app.app_context():
        db.create_all()
        actor = User(username="task8-executor-proof", password="x", enabled=True)
        db.session.add(actor)
        db.session.flush()
        operation = OperationRequest(
            request_no="TASK8-EXECUTOR-PROOF",
            operation_type=_ManualConfirmNoopHandler.operation_type,
            applicant_id=actor.id,
            approval_channel=ApprovalChannel.FEISHU.value,
            approval_execution_mode=ApprovalExecutionMode.MANUAL_CONFIRM.value,
            approval_status=ApprovalStatus.APPROVED.value,
            execution_status=ExecutionStatus.NOT_STARTED.value,
        )
        db.session.add(operation)
        db.session.commit()
        operation_id = operation.id
        actor_id = actor.id
        operation_handler_registry.clear()
        operation_handler_registry.register(_ManualConfirmNoopHandler())

    from app.services import operation_executor

    original_require_operation = operation_executor._require_operation
    read_barrier = Barrier(2)

    def synchronized_require_operation(operation_request_id: int) -> OperationRequest:
        operation = original_require_operation(operation_request_id)
        read_barrier.wait()
        return operation

    monkeypatch.setattr(
        operation_executor,
        "_require_operation",
        synchronized_require_operation,
    )

    def confirm() -> int:
        with concurrent_app.app_context():
            return operation_executor.confirm(operation_id, actor_id).id

    with ThreadPoolExecutor(max_workers=2) as executor:
        operation_ids = list(executor.map(lambda _index: confirm(), range(2)))

    assert operation_ids == [operation_id, operation_id]
    with concurrent_app.app_context():
        persisted = db.session.get(OperationRequest, operation_id)
        assert persisted is not None
        assert persisted.execution_status == ExecutionStatus.SUCCESS.value
        assert db.session.query(OperationExecutionAttempt).count() == 1
        db.drop_all()


def test_executor_commit_failure_persists_one_safe_failed_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    concurrent_app = _concurrent_app(tmp_path, "executor-commit-failure.db")
    with concurrent_app.app_context():
        db.create_all()
        context = seed_usage_return_context()
        operation = OperationRequest(
            request_no="TASK8-COMMIT-FAILURE",
            operation_type=_CommitFailureHandler.operation_type,
            applicant_id=context.manager.id,
            approval_channel=ApprovalChannel.FEISHU.value,
            approval_execution_mode=ApprovalExecutionMode.MANUAL_CONFIRM.value,
            approval_status=ApprovalStatus.APPROVED.value,
            execution_status=ExecutionStatus.NOT_STARTED.value,
        )
        db.session.add(operation)
        db.session.flush()
        db.session.add(
            AssetBusinessLock(
                asset_id=context.main_asset.id,
                operation_request_id=operation.id,
                operation_type=operation.operation_type,
                applicant_id=context.manager.id,
            )
        )
        db.session.commit()
        operation_id = operation.id
        actor_id = context.manager.id
        asset_id = context.main_asset.id
        operation_handler_registry.clear()
        operation_handler_registry.register(_CommitFailureHandler(asset_id))

        from app.services import operation_executor

        original_commit = db.session.commit
        commit_calls = 0

        def fail_first_commit_before_write() -> None:
            nonlocal commit_calls
            commit_calls += 1
            if commit_calls == 1:
                raise RuntimeError("raw outer commit failure")
            original_commit()

        monkeypatch.setattr(db.session, "commit", fail_first_commit_before_write)

        result = operation_executor.confirm(operation_id, actor_id)

        assert result.execution_status == ExecutionStatus.FAILED.value
        assert commit_calls == 2
        db.session.expire_all()
        persisted = db.session.get(OperationRequest, operation_id)
        asset = db.session.get(Asset, asset_id)
        assert persisted is not None
        assert asset is not None
        assert persisted.execution_status == ExecutionStatus.FAILED.value
        assert asset.remark is None
        attempt = db.session.query(OperationExecutionAttempt).one()
        assert attempt.status == "FAILED"
        assert attempt.error_code == "EXECUTION_FAILED"
        assert attempt.safe_error_message == _CommitFailureHandler.safe_error_message
        assert "raw outer commit failure" not in (attempt.safe_error_message or "")
        assert db.session.query(AssetBusinessLock).count() == 1
        assert db.session.query(AssetLifecycleRecord).count() == 0
        assert db.session.query(OperationLog).count() == 0
        db.drop_all()


def test_executor_outer_commit_after_write_reloads_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    concurrent_app = _concurrent_app(tmp_path, "outer-commit-after-write.db")
    with concurrent_app.app_context():
        db.create_all()
        context = seed_usage_return_context()
        operation = OperationRequest(
            request_no="TASK8-OUTER-COMMIT-AFTER-WRITE",
            operation_type=_CommitFailureHandler.operation_type,
            applicant_id=context.manager.id,
            approval_channel=ApprovalChannel.FEISHU.value,
            approval_execution_mode=ApprovalExecutionMode.MANUAL_CONFIRM.value,
            approval_status=ApprovalStatus.APPROVED.value,
            execution_status=ExecutionStatus.NOT_STARTED.value,
        )
        db.session.add(operation)
        db.session.flush()
        db.session.add(
            AssetBusinessLock(
                asset_id=context.main_asset.id,
                operation_request_id=operation.id,
                operation_type=operation.operation_type,
                applicant_id=context.manager.id,
            )
        )
        db.session.commit()
        operation_id = operation.id
        actor_id = context.manager.id
        asset_id = context.main_asset.id
        handler = _CommitFailureHandler(asset_id)
        execute_calls = 0
        original_execute = handler.execute

        def counted_execute(operation_request_id: int, triggered_by: int) -> None:
            nonlocal execute_calls
            execute_calls += 1
            original_execute(operation_request_id, triggered_by)

        monkeypatch.setattr(handler, "execute", counted_execute)
        operation_handler_registry.clear()
        operation_handler_registry.register(handler)

        from app.services import operation_executor

        original_commit = db.session.commit
        commit_calls = 0

        def commit_then_raise() -> None:
            nonlocal commit_calls
            commit_calls += 1
            original_commit()
            if commit_calls == 1:
                raise RuntimeError("outer commit result unknown")

        monkeypatch.setattr(db.session, "commit", commit_then_raise)

        result = operation_executor.confirm(operation_id, actor_id)

        assert result.execution_status == ExecutionStatus.SUCCESS.value
        assert result.version == 3
        assert execute_calls == 1
        assert commit_calls == 1
        db.session.expire_all()
        persisted = db.session.get(OperationRequest, operation_id)
        asset = db.session.get(Asset, asset_id)
        assert persisted is not None
        assert asset is not None
        assert persisted.execution_status == ExecutionStatus.SUCCESS.value
        assert persisted.version == 3
        assert asset.remark == "must-roll-back-after-commit-failure"
        attempt = db.session.query(OperationExecutionAttempt).one()
        assert attempt.status == "SUCCESS"
        assert db.session.query(AssetBusinessLock).count() == 0
        db.drop_all()


def test_executor_recovery_commit_after_write_reloads_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    concurrent_app = _concurrent_app(tmp_path, "recovery-commit-after-write.db")
    with concurrent_app.app_context():
        db.create_all()
        context = seed_usage_return_context()
        operation = OperationRequest(
            request_no="TASK8-RECOVERY-COMMIT-AFTER-WRITE",
            operation_type=_CommitFailureHandler.operation_type,
            applicant_id=context.manager.id,
            approval_channel=ApprovalChannel.FEISHU.value,
            approval_execution_mode=ApprovalExecutionMode.MANUAL_CONFIRM.value,
            approval_status=ApprovalStatus.APPROVED.value,
            execution_status=ExecutionStatus.NOT_STARTED.value,
        )
        db.session.add(operation)
        db.session.flush()
        db.session.add(
            AssetBusinessLock(
                asset_id=context.main_asset.id,
                operation_request_id=operation.id,
                operation_type=operation.operation_type,
                applicant_id=context.manager.id,
            )
        )
        db.session.commit()
        operation_id = operation.id
        actor_id = context.manager.id
        asset_id = context.main_asset.id
        handler = _CommitFailureHandler(asset_id)
        execute_calls = 0
        original_execute = handler.execute

        def counted_execute(operation_request_id: int, triggered_by: int) -> None:
            nonlocal execute_calls
            execute_calls += 1
            original_execute(operation_request_id, triggered_by)

        monkeypatch.setattr(handler, "execute", counted_execute)
        operation_handler_registry.clear()
        operation_handler_registry.register(handler)

        from app.services import operation_executor

        original_commit = db.session.commit
        commit_calls = 0

        def fail_then_commit_and_raise() -> None:
            nonlocal commit_calls
            commit_calls += 1
            if commit_calls == 1:
                raise RuntimeError("outer commit failed before write")
            original_commit()
            if commit_calls == 2:
                raise RuntimeError("recovery commit result unknown")

        monkeypatch.setattr(db.session, "commit", fail_then_commit_and_raise)

        result = operation_executor.confirm(operation_id, actor_id)

        assert result.execution_status == ExecutionStatus.FAILED.value
        assert result.version == 2
        assert execute_calls == 1
        assert commit_calls == 2
        db.session.expire_all()
        persisted = db.session.get(OperationRequest, operation_id)
        asset = db.session.get(Asset, asset_id)
        assert persisted is not None
        assert asset is not None
        assert persisted.execution_status == ExecutionStatus.FAILED.value
        assert persisted.version == 2
        assert asset.remark is None
        attempt = db.session.query(OperationExecutionAttempt).one()
        assert attempt.status == "FAILED"
        assert attempt.error_code == "EXECUTION_FAILED"
        assert attempt.safe_error_message == _CommitFailureHandler.safe_error_message
        assert db.session.query(AssetBusinessLock).count() == 1
        assert db.session.query(AssetLifecycleRecord).count() == 0
        assert db.session.query(OperationLog).count() == 0
        db.drop_all()


def test_retry_double_commit_failure_rejects_stale_failed_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    concurrent_app = _concurrent_app(tmp_path, "retry-double-commit-failure.db")
    with concurrent_app.app_context():
        db.create_all()
        context = seed_usage_return_context()
        operation = OperationRequest(
            request_no="TASK8-RETRY-COMMIT-FAILURE",
            operation_type=_CommitFailureHandler.operation_type,
            applicant_id=context.manager.id,
            approval_channel=ApprovalChannel.FEISHU.value,
            approval_execution_mode=ApprovalExecutionMode.MANUAL_CONFIRM.value,
            approval_status=ApprovalStatus.APPROVED.value,
            execution_status=ExecutionStatus.FAILED.value,
            execution_error="prior safe failure",
            version=2,
        )
        db.session.add(operation)
        db.session.flush()
        db.session.add_all(
            [
                OperationExecutionAttempt(
                    operation_request_id=operation.id,
                    attempt_no=1,
                    trigger_type="CONFIRMATION",
                    triggered_by=context.manager.id,
                    status="FAILED",
                    error_code="EXECUTION_FAILED",
                    safe_error_message="prior safe failure",
                ),
                AssetBusinessLock(
                    asset_id=context.main_asset.id,
                    operation_request_id=operation.id,
                    operation_type=operation.operation_type,
                    applicant_id=context.manager.id,
                ),
            ]
        )
        db.session.commit()
        operation_id = operation.id
        actor_id = context.manager.id
        asset_id = context.main_asset.id
        operation_handler_registry.clear()
        operation_handler_registry.register(_CommitFailureHandler(asset_id))

        from app.services import operation_executor

        original_commit = db.session.commit
        commit_calls = 0

        def fail_two_commits_before_write() -> None:
            nonlocal commit_calls
            commit_calls += 1
            if commit_calls <= 2:
                raise RuntimeError("raw retry commit failure")
            original_commit()

        monkeypatch.setattr(db.session, "commit", fail_two_commits_before_write)

        with pytest.raises(
            BusinessException,
            match=_CommitFailureHandler.safe_error_message,
        ) as raised:
            operation_executor.retry(operation_id, actor_id)

        assert "raw retry commit failure" not in raised.value.message
        assert commit_calls == 2
        db.session.expire_all()
        persisted = db.session.get(OperationRequest, operation_id)
        asset = db.session.get(Asset, asset_id)
        assert persisted is not None
        assert asset is not None
        assert persisted.execution_status == ExecutionStatus.FAILED.value
        assert persisted.version == 2
        assert asset.remark is None
        attempts = db.session.query(OperationExecutionAttempt).all()
        assert len(attempts) == 1
        assert attempts[0].attempt_no == 1
        assert attempts[0].safe_error_message == "prior safe failure"
        assert db.session.query(AssetBusinessLock).count() == 1
        db.drop_all()
