"""Local FEISHU provider, callback idempotency, and DIRECT confirmation."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import app.services as services
from app import create_app
from app.enums import ApprovalChannel, ApprovalStatus, ExecutionStatus
from app.extensions import db
from app.models import (
    ExternalApprovalEvent,
    OperationExecutionAttempt,
    OperationRequest,
    User,
)
from app.operations import operation_handler_registry
from config import TestConfig


class NoopHandler:
    operation_type = "PROVIDER_TEST"

    def revalidate_for_execution(self, operation_request_id: int) -> None:
        return None

    def execute(self, operation_request_id: int, actor_id: int) -> None:
        return None


def _provider_service():
    service = getattr(services, "approval_provider_service", None)
    assert service is not None, "missing approval_provider_service"
    return service


def _operation(actor: User, channel: str, request_no: str) -> OperationRequest:
    operation = OperationRequest(
        request_no=request_no,
        operation_type="PROVIDER_TEST",
        applicant_id=actor.id,
        approval_channel=channel,
        approval_status=ApprovalStatus.PENDING.value,
        execution_status=ExecutionStatus.NOT_STARTED.value,
    )
    db.session.add(operation)
    db.session.commit()
    return operation


def test_local_feishu_submit_confirm_duplicate_and_stale_callbacks(app) -> None:
    actor = User(username="provider-actor", password="x", enabled=True)
    db.session.add(actor)
    db.session.commit()
    operation = _operation(actor, ApprovalChannel.FEISHU.value, "PROVIDER-FEISHU")
    operation_handler_registry.clear()
    operation_handler_registry.register(NoopHandler())
    service = _provider_service()

    submitted = service.submit(operation.id, actor.id)
    assert submitted.external_instance_id == f"LOCAL-FEISHU-{operation.id}"
    service.urge(operation.id, actor.id)
    confirmed = service.handle_callback(
        provider="FEISHU",
        external_event_id="event-approved",
        external_instance_id=submitted.external_instance_id,
        status="APPROVED",
        actor_id=actor.id,
    )
    assert confirmed.approval_status == ApprovalStatus.APPROVED.value
    assert confirmed.execution_status == ExecutionStatus.SUCCESS.value
    duplicate = service.handle_callback(
        provider="FEISHU",
        external_event_id="event-approved",
        external_instance_id=submitted.external_instance_id,
        status="APPROVED",
        actor_id=actor.id,
    )
    assert duplicate.id == operation.id
    assert db.session.query(ExternalApprovalEvent).count() == 1

    stale = service.handle_callback(
        provider="FEISHU",
        external_event_id="event-stale-reject",
        external_instance_id=submitted.external_instance_id,
        status="REJECTED",
        actor_id=actor.id,
    )
    assert stale.approval_status == ApprovalStatus.APPROVED.value
    assert (
        db.session.query(ExternalApprovalEvent)
        .filter_by(external_event_id="event-stale-reject")
        .one()
        .processing_status
        == "IGNORED"
    )


def test_local_feishu_rejection_and_withdrawal_are_terminal(app) -> None:
    actor = User(username="provider-terminal", password="x", enabled=True)
    db.session.add(actor)
    db.session.commit()
    service = _provider_service()
    rejected = _operation(actor, ApprovalChannel.FEISHU.value, "PROVIDER-REJECT")
    service.submit(rejected.id, actor.id)
    result = service.handle_callback(
        provider="FEISHU",
        external_event_id="event-rejected",
        external_instance_id=rejected.external_instance_id,
        status="REJECTED",
        actor_id=actor.id,
    )
    assert result.approval_status == ApprovalStatus.REJECTED.value

    withdrawn = _operation(actor, ApprovalChannel.FEISHU.value, "PROVIDER-WITHDRAW")
    service.submit(withdrawn.id, actor.id)
    service.withdraw(withdrawn.id, actor.id)
    assert withdrawn.approval_status == ApprovalStatus.WITHDRAWN.value


def test_direct_confirmation_approves_and_executes_without_tasks(app) -> None:
    actor = User(username="provider-direct", password="x", enabled=True)
    db.session.add(actor)
    db.session.commit()
    operation = _operation(actor, ApprovalChannel.DIRECT.value, "PROVIDER-DIRECT")
    operation_handler_registry.clear()
    operation_handler_registry.register(NoopHandler())

    confirmed = _provider_service().confirm_direct(operation.id, actor.id)
    assert confirmed.approval_status == ApprovalStatus.APPROVED.value
    assert confirmed.execution_status == ExecutionStatus.SUCCESS.value


def test_concurrent_feishu_callbacks_are_idempotent_and_choose_one_terminal_state(
    tmp_path,
) -> None:
    database = tmp_path / "provider-callback-concurrency.db"

    class ConcurrentConfig(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{database}"

    concurrent_app = create_app(config=ConcurrentConfig)
    with concurrent_app.app_context():
        db.create_all()
        actor = User(username="provider-concurrent", password="x", enabled=True)
        db.session.add(actor)
        db.session.commit()
        operation = _operation(
            actor, ApprovalChannel.FEISHU.value, "PROVIDER-CONCURRENT"
        )
        _provider_service().submit(operation.id, actor.id)
        operation_id = operation.id
        actor_id = actor.id
        external_instance_id = operation.external_instance_id
    operation_handler_registry.clear()
    operation_handler_registry.register(NoopHandler())
    barrier = Barrier(2)

    def callback(event_id: str, status: str) -> str:
        with concurrent_app.app_context():
            barrier.wait()
            result = _provider_service().handle_callback(
                provider="FEISHU",
                external_event_id=event_id,
                external_instance_id=external_instance_id,
                status=status,
                actor_id=actor_id,
            )
            return result.approval_status

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(
            executor.map(
                lambda args: callback(*args),
                (("event-approved", "APPROVED"), ("event-rejected", "REJECTED")),
            )
        )
    with concurrent_app.app_context():
        persisted = db.session.get(OperationRequest, operation_id)
        assert persisted is not None
        events = db.session.query(ExternalApprovalEvent).all()
        assert sorted(event.processing_status for event in events) == [
            "IGNORED",
            "PROCESSED",
        ]
        assert persisted.approval_status in {"APPROVED", "REJECTED"}
        assert db.session.query(OperationExecutionAttempt).count() == (
            1 if persisted.approval_status == "APPROVED" else 0
        )
        db.drop_all()


def test_concurrent_duplicate_feishu_event_executes_only_once(tmp_path) -> None:
    database = tmp_path / "provider-duplicate-event-concurrency.db"

    class ConcurrentConfig(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{database}"

    concurrent_app = create_app(config=ConcurrentConfig)
    with concurrent_app.app_context():
        db.create_all()
        actor = User(username="provider-duplicate", password="x", enabled=True)
        db.session.add(actor)
        db.session.commit()
        operation = _operation(
            actor, ApprovalChannel.FEISHU.value, "PROVIDER-DUPLICATE"
        )
        _provider_service().submit(operation.id, actor.id)
        operation_id = operation.id
        actor_id = actor.id
        external_instance_id = operation.external_instance_id
    operation_handler_registry.clear()
    operation_handler_registry.register(NoopHandler())
    barrier = Barrier(2)

    def callback() -> int:
        with concurrent_app.app_context():
            barrier.wait()
            result = _provider_service().handle_callback(
                provider="FEISHU",
                external_event_id="same-approved-event",
                external_instance_id=external_instance_id,
                status="APPROVED",
                actor_id=actor_id,
            )
            return result.id

    with ThreadPoolExecutor(max_workers=2) as executor:
        operation_ids = list(executor.map(lambda _index: callback(), range(2)))

    assert operation_ids == [operation_id, operation_id]
    with concurrent_app.app_context():
        assert db.session.query(ExternalApprovalEvent).count() == 1
        assert db.session.query(OperationExecutionAttempt).count() == 1
        db.drop_all()
