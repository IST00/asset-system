"""Local FEISHU event simulation contracts for usage and return requests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Lock

import pytest

from app import create_app
from app.api import asset_returns, asset_usage, local_feishu
from app.common import BusinessException, ResultCode
from app.enums import ApprovalChannel, ApprovalStatus, ExecutionStatus, OperationType
from app.extensions import db
from app.models import (
    AssetLifecycleRecord,
    ExternalApprovalEvent,
    OperationExecutionAttempt,
    OperationLog,
    OperationRequest,
    Organization,
    User,
)
from app.repositories.operation_repository import ExternalApprovalEventRepository
from app.services import (
    asset_return_service,
    asset_usage_service,
    local_feishu_service,
)
from asset_usage_return_fixtures import (
    UsageReturnContext,
    grant_permissions,
    grant_scoped_manager_permission,
    register_usage_return_handlers,
    seed_http_context,
    seed_usage_return_context,
)
from config import TestConfig


@pytest.fixture()
def feature_app():
    app = create_app(config=TestConfig)
    app.register_blueprint(asset_usage.bp)
    app.register_blueprint(asset_returns.bp)
    app.register_blueprint(local_feishu.bp)
    register_usage_return_handlers()
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def feature_client(feature_app):
    return feature_app.test_client()


class _PostCallbackBarrierRepository:
    def __init__(
        self,
        delegate: ExternalApprovalEventRepository,
        barrier: Barrier,
    ) -> None:
        self._delegate = delegate
        self._barrier = barrier
        self._remaining_waits = 2
        self._lock = Lock()

    def find_by_event(
        self,
        provider: str,
        external_event_id: str,
    ) -> ExternalApprovalEvent | None:
        event = self._delegate.find_by_event(provider, external_event_id)
        with self._lock:
            should_wait = self._remaining_waits > 0
            if should_wait:
                self._remaining_waits -= 1
        if should_wait:
            assert event is not None
            assert "reason" not in (event.payload or {})
            self._barrier.wait(timeout=5)
        return event


def seed_pending_personal_usage() -> tuple[UsageReturnContext, OperationRequest]:
    context = seed_usage_return_context()
    grant_permissions(context.manager, "asset:usage:manage")
    submitted = asset_usage_service.submit_personal(
        {
            "asset_ids": [context.main_asset.id],
            "target_user_id": context.employee.id,
        },
        context.manager.id,
    )
    operation = db.session.get(OperationRequest, submitted["id"])
    assert operation is not None
    return context, operation


def _set_personal_assets_in_use(context: UsageReturnContext) -> None:
    for asset in (context.main_asset, context.child_asset):
        asset.status = "IN_USE"
        asset.usage_type = "PERSONAL"
        asset.holder_user_id = context.employee.id
        asset.public_object_id = None
        asset.usage_department_id = context.organization.id
    db.session.flush()


def seed_pending_personal_return() -> tuple[UsageReturnContext, OperationRequest]:
    context = seed_usage_return_context()
    _set_personal_assets_in_use(context)
    grant_permissions(context.employee, "asset:return:self")
    submitted = asset_return_service.submit_personal(
        {"asset_ids": [context.main_asset.id]},
        context.employee.id,
    )
    operation = db.session.get(OperationRequest, submitted["id"])
    assert operation is not None
    return context, operation


def _outsider(context: UsageReturnContext) -> User:
    user = User(
        username="UR-mock-outsider",
        password="x",
        nickname="UR Mock Outsider",
        organization_id=context.organization.id,
        enabled=True,
    )
    db.session.add(user)
    db.session.flush()
    return user


def test_usage_target_employee_can_mock_approve_once(app) -> None:
    context, operation = seed_pending_personal_usage()
    register_usage_return_handlers()
    payload = {"action": "APPROVE", "external_event_id": "usage-approved-1"}
    result = local_feishu_service.act(operation.id, payload, context.employee.id)
    replay = local_feishu_service.act(operation.id, payload, context.employee.id)
    assert result["execution_status"] == ExecutionStatus.SUCCESS.value
    assert replay["id"] == result["id"]
    assert db.session.query(ExternalApprovalEvent).count() == 1
    assert db.session.query(OperationExecutionAttempt).count() == 1
    assert db.session.query(AssetLifecycleRecord).count() == 2
    assert db.session.query(OperationLog).count() == 1


def test_mock_reject_persists_reason_in_external_event_payload(app) -> None:
    context, operation = seed_pending_personal_usage()
    local_feishu_service.act(
        operation.id,
        {
            "action": "REJECT",
            "external_event_id": "usage-rejected-1",
            "reason": "device not received",
        },
        context.employee.id,
    )
    assert db.session.query(ExternalApprovalEvent).one().payload["reason"] == (
        "device not received"
    )


@pytest.mark.parametrize(
    "conflicting_payload",
    [
        {
            "action": "REJECT",
            "external_event_id": "usage-rejected-immutable",
            "reason": "second reason",
        },
        {
            "action": "APPROVE",
            "external_event_id": "usage-rejected-immutable",
        },
    ],
    ids=["different-reason", "different-action"],
)
def test_mock_duplicate_event_rejects_conflicting_payload_without_mutation(
    app,
    conflicting_payload: dict[str, str],
) -> None:
    context, operation = seed_pending_personal_usage()
    original_payload = {
        "action": "REJECT",
        "external_event_id": "usage-rejected-immutable",
        "reason": "first reason",
    }
    first = local_feishu_service.act(
        operation.id,
        original_payload,
        context.employee.id,
    )
    expected_event_payload = {
        "status": ApprovalStatus.REJECTED.value,
        "reason": "first reason",
    }
    assert db.session.query(ExternalApprovalEvent).one().payload == (
        expected_event_payload
    )

    exact_replay = local_feishu_service.act(
        operation.id,
        original_payload,
        context.employee.id,
    )

    assert exact_replay["id"] == first["id"]
    assert exact_replay["approval_status"] == ApprovalStatus.REJECTED.value
    assert db.session.query(ExternalApprovalEvent).count() == 1
    assert db.session.query(OperationExecutionAttempt).count() == 0
    assert db.session.query(AssetLifecycleRecord).count() == 0

    conflict: BusinessException | None = None
    try:
        local_feishu_service.act(
            operation.id,
            conflicting_payload,
            context.employee.id,
        )
    except BusinessException as error:
        conflict = error

    db.session.expire_all()
    assert db.session.query(ExternalApprovalEvent).one().payload == (
        expected_event_payload
    )
    assert conflict is not None
    assert conflict.code == ResultCode.BAD_REQUEST.code
    assert db.session.query(ExternalApprovalEvent).count() == 1
    assert db.session.query(OperationExecutionAttempt).count() == 0
    assert db.session.query(AssetLifecycleRecord).count() == 0


def test_mock_concurrent_duplicate_event_binds_only_one_reason(
    tmp_path,
    monkeypatch,
) -> None:
    database = tmp_path / "local-feishu-reason-cas.db"

    class ConcurrentConfig(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{database}"

    concurrent_app = create_app(config=ConcurrentConfig)
    with concurrent_app.app_context():
        db.create_all()
        context, operation = seed_pending_personal_usage()
        operation_id = operation.id
        actor_id = context.employee.id

    original_repository = local_feishu_service.external_approval_event_repository
    monkeypatch.setattr(
        local_feishu_service,
        "external_approval_event_repository",
        _PostCallbackBarrierRepository(original_repository, Barrier(2)),
    )

    def reject(reason: str) -> tuple[str, int, str]:
        with concurrent_app.app_context():
            try:
                result = local_feishu_service.act(
                    operation_id,
                    {
                        "action": "REJECT",
                        "external_event_id": "usage-rejected-concurrent-reason",
                        "reason": reason,
                    },
                    actor_id,
                )
                return "success", int(result["id"]), reason
            except BusinessException as error:
                return "error", error.code, reason

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(reject, ("first reason", "second reason")))

    successes = [result for result in results if result[0] == "success"]
    errors = [result for result in results if result[0] == "error"]
    assert len(successes) == 1
    assert successes[0][1] == operation_id
    assert len(errors) == 1
    assert errors[0][1] == ResultCode.BAD_REQUEST.code

    with concurrent_app.app_context():
        event = db.session.query(ExternalApprovalEvent).one()
        operation = db.session.get(OperationRequest, operation_id)
        assert operation is not None
        assert event.payload == {
            "status": ApprovalStatus.REJECTED.value,
            "reason": successes[0][2],
        }
        assert operation.approval_status == ApprovalStatus.REJECTED.value
        assert db.session.query(ExternalApprovalEvent).count() == 1
        assert db.session.query(OperationExecutionAttempt).count() == 0
        assert db.session.query(AssetLifecycleRecord).count() == 0
        db.drop_all()


def test_mock_reason_enrichment_recovers_after_commit_failure(
    app,
    monkeypatch,
) -> None:
    context, operation = seed_pending_personal_usage()
    payload = {
        "action": "REJECT",
        "external_event_id": "usage-rejected-recover-reason",
        "reason": "device not received",
    }
    original_commit = db.session.commit
    commit_calls = 0

    def fail_reason_commit() -> None:
        nonlocal commit_calls
        commit_calls += 1
        if commit_calls == 2:
            raise RuntimeError("injected reason commit failure")
        original_commit()

    with monkeypatch.context() as commit_patch:
        commit_patch.setattr(db.session, "commit", fail_reason_commit)
        with pytest.raises(RuntimeError, match="injected reason commit failure"):
            local_feishu_service.act(operation.id, payload, context.employee.id)

    assert commit_calls == 2
    db.session.rollback()
    persisted = db.session.get(OperationRequest, operation.id)
    event = db.session.query(ExternalApprovalEvent).one()
    assert persisted is not None
    assert persisted.approval_status == ApprovalStatus.REJECTED.value
    assert event.payload == {"status": ApprovalStatus.REJECTED.value}

    recovered = local_feishu_service.act(
        operation.id,
        payload,
        context.employee.id,
    )

    assert recovered["approval_status"] == ApprovalStatus.REJECTED.value
    assert db.session.query(ExternalApprovalEvent).one().payload == {
        "status": ApprovalStatus.REJECTED.value,
        "reason": "device not received",
    }
    assert db.session.query(ExternalApprovalEvent).count() == 1
    assert db.session.query(OperationExecutionAttempt).count() == 0
    assert db.session.query(AssetLifecycleRecord).count() == 0


@pytest.mark.parametrize("action", ["APPROVE", "REJECT"])
@pytest.mark.parametrize("actor_kind", ["applicant", "outsider"])
def test_mock_usage_decision_rejects_non_target_actor(
    app,
    action: str,
    actor_kind: str,
) -> None:
    context, operation = seed_pending_personal_usage()
    outsider = _outsider(context)
    actor_id = context.manager.id if actor_kind == "applicant" else outsider.id
    payload = {
        "action": action,
        "external_event_id": f"usage-{action.lower()}-{actor_kind}",
        "reason": "not received" if action == "REJECT" else None,
    }

    with pytest.raises(BusinessException) as raised:
        local_feishu_service.act(operation.id, payload, actor_id)

    assert raised.value.code == ResultCode.FORBIDDEN.code
    assert db.session.get(OperationRequest, operation.id).approval_status == (
        ApprovalStatus.PENDING.value
    )
    assert db.session.query(ExternalApprovalEvent).count() == 0
    assert db.session.query(OperationExecutionAttempt).count() == 0


@pytest.mark.parametrize(
    ("action", "expected_status"),
    [
        ("APPROVE", ApprovalStatus.APPROVED.value),
        ("REJECT", ApprovalStatus.REJECTED.value),
    ],
)
def test_mock_return_manager_with_full_scope_can_decide(
    app,
    action: str,
    expected_status: str,
) -> None:
    context, operation = seed_pending_personal_return()
    grant_permissions(context.manager, "asset:usage:manage")
    payload = {
        "action": action,
        "external_event_id": f"return-{action.lower()}-full-scope",
        "reason": "not accepted" if action == "REJECT" else None,
    }

    result = local_feishu_service.act(operation.id, payload, context.manager.id)

    assert result["id"] == operation.id
    assert result["approval_status"] == expected_status
    assert result["execution_status"] == ExecutionStatus.NOT_STARTED.value
    assert db.session.query(ExternalApprovalEvent).count() == 1
    assert db.session.query(OperationExecutionAttempt).count() == 0


@pytest.mark.parametrize("action", ["APPROVE", "REJECT"])
def test_mock_return_decision_requires_manage_permission(app, action: str) -> None:
    context, operation = seed_pending_personal_return()
    payload = {
        "action": action,
        "external_event_id": f"return-{action.lower()}-no-permission",
        "reason": "not accepted" if action == "REJECT" else None,
    }

    with pytest.raises(BusinessException) as raised:
        local_feishu_service.act(operation.id, payload, context.manager.id)

    assert raised.value.code == ResultCode.FORBIDDEN.code
    assert db.session.get(OperationRequest, operation.id).approval_status == (
        ApprovalStatus.PENDING.value
    )
    assert db.session.query(ExternalApprovalEvent).count() == 0


@pytest.mark.parametrize("action", ["APPROVE", "REJECT"])
def test_mock_return_decision_requires_scope_for_every_asset(
    app,
    action: str,
) -> None:
    context = seed_usage_return_context()
    other_organization = Organization(
        code="UR-MOCK-OTHER-ORG",
        name="UR Mock Other Organization",
        status="ENABLED",
    )
    db.session.add(other_organization)
    db.session.flush()
    context.child_asset.organization_id = other_organization.id
    _set_personal_assets_in_use(context)
    grant_permissions(context.employee, "asset:return:self")
    submitted = asset_return_service.submit_personal(
        {"asset_ids": [context.main_asset.id]},
        context.employee.id,
    )
    grant_scoped_manager_permission(context.manager, context.organization.id)
    payload = {
        "action": action,
        "external_event_id": f"return-{action.lower()}-partial-scope",
        "reason": "not accepted" if action == "REJECT" else None,
    }

    with pytest.raises(BusinessException) as raised:
        local_feishu_service.act(submitted["id"], payload, context.manager.id)

    assert raised.value.code == ResultCode.FORBIDDEN.code
    assert db.session.get(OperationRequest, submitted["id"]).approval_status == (
        ApprovalStatus.PENDING.value
    )
    assert db.session.query(ExternalApprovalEvent).count() == 0


def test_mock_withdraw_requires_applicant_and_returns_strict_detail(app) -> None:
    context, operation = seed_pending_personal_return()

    with pytest.raises(BusinessException) as raised:
        local_feishu_service.act(
            operation.id,
            {
                "action": "WITHDRAW",
                "external_event_id": "return-withdraw-not-applicant",
            },
            context.manager.id,
        )

    assert raised.value.code == ResultCode.FORBIDDEN.code
    assert db.session.query(ExternalApprovalEvent).count() == 0

    result = local_feishu_service.act(
        operation.id,
        {
            "action": "WITHDRAW",
            "external_event_id": "return-withdraw-applicant",
        },
        context.employee.id,
    )

    assert result["id"] == operation.id
    assert result["operation_type"] == OperationType.PERSONAL_RETURN.value
    assert result["approval_status"] == ApprovalStatus.WITHDRAWN.value
    assert result["feature"]["items"]
    assert db.session.query(ExternalApprovalEvent).count() == 1


def test_mock_reject_normalizes_reason_before_persisting(app) -> None:
    context, operation = seed_pending_personal_usage()

    result = local_feishu_service.act(
        operation.id,
        {
            "action": "REJECT",
            "external_event_id": "  usage-rejected-normalized  ",
            "reason": "  device not received  ",
        },
        context.employee.id,
    )

    event = db.session.query(ExternalApprovalEvent).one()
    assert result["approval_status"] == ApprovalStatus.REJECTED.value
    assert event.external_event_id == "usage-rejected-normalized"
    assert event.payload == {
        "status": ApprovalStatus.REJECTED.value,
        "reason": "device not received",
    }


def test_mock_approve_normalizes_blank_reason_to_none(app) -> None:
    context, operation = seed_pending_personal_usage()
    register_usage_return_handlers()

    local_feishu_service.act(
        operation.id,
        {
            "action": "APPROVE",
            "external_event_id": "usage-approved-blank-reason",
            "reason": "   ",
        },
        context.employee.id,
    )

    assert db.session.query(ExternalApprovalEvent).one().payload["reason"] is None


def test_mock_reject_requires_non_blank_reason(app) -> None:
    context, operation = seed_pending_personal_usage()

    with pytest.raises(BusinessException) as raised:
        local_feishu_service.act(
            operation.id,
            {
                "action": "REJECT",
                "external_event_id": "usage-rejected-blank-reason",
                "reason": "   ",
            },
            context.employee.id,
        )

    assert raised.value.code == ResultCode.BAD_REQUEST.code
    assert db.session.query(ExternalApprovalEvent).count() == 0


def test_mock_service_is_hidden_when_local_mode_is_disabled(app) -> None:
    context, operation = seed_pending_personal_usage()
    app.config.update(
        TESTING=False,
        DEBUG=False,
        LOCAL_FEISHU_ENABLED=False,
    )

    with pytest.raises(BusinessException) as raised:
        local_feishu_service.act(
            operation.id,
            {
                "action": "REJECT",
                "external_event_id": "usage-rejected-disabled",
                "reason": "not received",
            },
            context.employee.id,
        )

    assert raised.value.code == ResultCode.NOT_FOUND.code
    assert db.session.get(OperationRequest, operation.id).approval_status == (
        ApprovalStatus.PENDING.value
    )
    assert db.session.query(ExternalApprovalEvent).count() == 0


@pytest.mark.parametrize("enabled_by", ["testing", "debug", "flag"])
def test_mock_service_is_available_in_each_local_mode(app, enabled_by: str) -> None:
    context, operation = seed_pending_personal_usage()
    app.config.update(
        TESTING=False,
        DEBUG=False,
        LOCAL_FEISHU_ENABLED=False,
    )
    if enabled_by == "testing":
        app.config["TESTING"] = True
    elif enabled_by == "debug":
        app.config["DEBUG"] = True
    else:
        app.config["LOCAL_FEISHU_ENABLED"] = True

    result = local_feishu_service.act(
        operation.id,
        {
            "action": "REJECT",
            "external_event_id": f"usage-rejected-{enabled_by}",
            "reason": "not received",
        },
        context.employee.id,
    )

    assert result["approval_status"] == ApprovalStatus.REJECTED.value
    assert db.session.query(ExternalApprovalEvent).count() == 1


def test_mock_service_rejects_non_feishu_operation(app) -> None:
    context, operation = seed_pending_personal_usage()
    operation.approval_channel = ApprovalChannel.DIRECT.value
    db.session.commit()

    with pytest.raises(BusinessException) as raised:
        local_feishu_service.act(
            operation.id,
            {
                "action": "REJECT",
                "external_event_id": "usage-rejected-direct",
                "reason": "not received",
            },
            context.employee.id,
        )

    assert raised.value.code == ResultCode.BAD_REQUEST.code
    assert db.session.query(ExternalApprovalEvent).count() == 0


def test_mock_service_rejects_unsupported_operation_type(app) -> None:
    context, operation = seed_pending_personal_usage()
    operation.operation_type = OperationType.TRANSFER.value
    db.session.commit()

    with pytest.raises(BusinessException) as raised:
        local_feishu_service.act(
            operation.id,
            {
                "action": "REJECT",
                "external_event_id": "usage-rejected-transfer",
                "reason": "not received",
            },
            context.employee.id,
        )

    assert raised.value.code == ResultCode.BAD_REQUEST.code
    assert db.session.query(ExternalApprovalEvent).count() == 0


def _set_public_assets_in_use(context: UsageReturnContext) -> None:
    for asset in (context.main_asset, context.child_asset):
        asset.status = "IN_USE"
        asset.usage_type = "PUBLIC"
        asset.holder_user_id = None
        asset.public_object_id = context.public_object.id
        asset.usage_department_id = None
    db.session.commit()


def _inspection_payload(context: UsageReturnContext) -> dict[str, object]:
    return {
        "return_location_id": context.return_location.id,
        "items": [
            {"asset_id": context.main_asset.id, "condition": "NORMAL"},
            {"asset_id": context.child_asset.id, "condition": "NORMAL"},
        ],
    }


def test_personal_usage_post_returns_common_envelope(feature_client) -> None:
    context, headers = seed_http_context(feature_client)

    response = feature_client.post(
        "/api/v1/asset-usage-requests/personal",
        headers=headers.manager,
        json={
            "asset_ids": [context.main_asset.id],
            "target_user_id": context.employee.id,
        },
    )

    body = response.get_json()
    assert response.status_code == 200
    assert body["code"] == 200
    assert body["data"]["operation_type"] == OperationType.PERSONAL_USE.value


def test_public_usage_post_returns_common_envelope(feature_client) -> None:
    context, headers = seed_http_context(feature_client)

    response = feature_client.post(
        "/api/v1/asset-usage-requests/public",
        headers=headers.manager,
        json={
            "asset_ids": [context.main_asset.id],
            "public_object_id": context.public_object.id,
            "location_id": context.location.id,
        },
    )

    body = response.get_json()
    assert response.status_code == 200
    assert body["code"] == 200
    assert body["data"]["operation_type"] == OperationType.PUBLIC_USE.value


def test_usage_page_and_detail_get_return_common_envelopes(feature_client) -> None:
    context, headers = seed_http_context(feature_client)
    created = feature_client.post(
        "/api/v1/asset-usage-requests/personal",
        headers=headers.manager,
        json={
            "asset_ids": [context.main_asset.id],
            "target_user_id": context.employee.id,
            "location_id": context.return_location.id,
        },
    ).get_json()["data"]
    expected_user = {
        "id": context.employee.id,
        "username": context.employee.username,
        "name": context.employee.nickname,
    }
    expected_department = {
        "id": context.organization.id,
        "code": context.organization.code,
        "name": context.organization.name,
    }
    expected_location = {
        "id": context.return_location.id,
        "code": context.return_location.code,
        "name": context.return_location.name,
    }
    context.employee.nickname = "UR HTTP Employee Renamed"
    context.employee.enabled = False
    context.organization.name = "UR HTTP Organization Renamed"
    context.organization.status = "DISABLED"
    context.return_location.name = "UR HTTP Location Renamed"
    context.return_location.status = "DISABLED"
    db.session.commit()

    page_response = feature_client.get(
        "/api/v1/asset-usage-requests?page=0&size=10",
        headers=headers.manager,
    )
    detail_response = feature_client.get(
        f"/api/v1/asset-usage-requests/{created['id']}",
        headers=headers.manager,
    )

    page_body = page_response.get_json()
    detail_body = detail_response.get_json()
    assert page_response.status_code == 200
    assert page_body["code"] == 200
    assert page_body["data"]["total"] == 1
    assert page_body["data"]["items"][0]["id"] == created["id"]
    assert detail_response.status_code == 200
    assert detail_body["code"] == 200
    assert detail_body["data"]["id"] == created["id"]
    for item in (page_body["data"]["items"][0], detail_body["data"]):
        feature = item["feature"]
        assert feature.get("target_user_snapshot") == expected_user
        assert feature.get("usage_department_snapshot") == expected_department
        assert feature.get("target_public_object_snapshot") is None
        assert feature.get("target_location_snapshot") == expected_location


def test_employee_can_post_self_personal_return(feature_client) -> None:
    context, headers = seed_http_context(feature_client)
    _set_personal_assets_in_use(context)
    db.session.commit()

    response = feature_client.post(
        "/api/v1/asset-return-requests/personal",
        headers=headers.employee,
        json={"asset_ids": [context.main_asset.id]},
    )

    body = response.get_json()
    assert response.status_code == 200
    assert body["code"] == 200
    assert body["data"]["operation_type"] == OperationType.PERSONAL_RETURN.value


def test_manager_can_confirm_mock_approved_personal_return(feature_client) -> None:
    context, headers = seed_http_context(feature_client)
    _set_personal_assets_in_use(context)
    db.session.commit()
    submitted = feature_client.post(
        "/api/v1/asset-return-requests/personal",
        headers=headers.employee,
        json={"asset_ids": [context.main_asset.id]},
    ).get_json()["data"]
    approved = feature_client.post(
        f"/api/v1/asset-return-requests/{submitted['id']}/mock-feishu-action",
        headers=headers.manager,
        json={
            "action": "APPROVE",
            "external_event_id": "http-return-approved-for-confirm",
        },
    )
    assert approved.get_json()["data"]["approval_status"] == (
        ApprovalStatus.APPROVED.value
    )

    response = feature_client.post(
        f"/api/v1/asset-return-requests/{submitted['id']}/confirm",
        headers=headers.manager,
        json=_inspection_payload(context),
    )

    body = response.get_json()
    assert response.status_code == 200
    assert body["code"] == 200
    assert body["data"]["operation_type"] == OperationType.PERSONAL_RETURN.value
    assert body["data"]["execution_status"] == ExecutionStatus.SUCCESS.value


def test_public_return_post_returns_common_envelope(feature_client) -> None:
    context, headers = seed_http_context(feature_client)
    _set_public_assets_in_use(context)

    response = feature_client.post(
        "/api/v1/asset-return-requests/public",
        headers=headers.manager,
        json={
            "asset_ids": [context.main_asset.id],
            **_inspection_payload(context),
        },
    )

    body = response.get_json()
    assert response.status_code == 200
    assert body["code"] == 200
    assert body["data"]["operation_type"] == OperationType.PUBLIC_RETURN.value


def test_usage_mock_feishu_route_uses_authenticated_employee(feature_client) -> None:
    context, headers = seed_http_context(feature_client)
    submitted = feature_client.post(
        "/api/v1/asset-usage-requests/personal",
        headers=headers.manager,
        json={
            "asset_ids": [context.main_asset.id],
            "target_user_id": context.employee.id,
        },
    ).get_json()["data"]

    response = feature_client.post(
        f"/api/v1/asset-usage-requests/{submitted['id']}/mock-feishu-action",
        headers=headers.employee,
        json={
            "action": "APPROVE",
            "external_event_id": "  http-usage-approved  ",
        },
    )

    body = response.get_json()
    assert response.status_code == 200
    assert body["code"] == 200
    assert body["data"]["approval_status"] == ApprovalStatus.APPROVED.value


def test_return_mock_feishu_route_uses_authenticated_manager(feature_client) -> None:
    context, headers = seed_http_context(feature_client)
    _set_personal_assets_in_use(context)
    db.session.commit()
    submitted = feature_client.post(
        "/api/v1/asset-return-requests/personal",
        headers=headers.employee,
        json={"asset_ids": [context.main_asset.id]},
    ).get_json()["data"]

    response = feature_client.post(
        f"/api/v1/asset-return-requests/{submitted['id']}/mock-feishu-action",
        headers=headers.manager,
        json={
            "action": "APPROVE",
            "external_event_id": "  http-return-approved  ",
        },
    )

    body = response.get_json()
    assert response.status_code == 200
    assert body["code"] == 200
    assert body["data"]["approval_status"] == ApprovalStatus.APPROVED.value


def test_mock_feishu_route_is_hidden_when_local_mode_is_disabled(
    feature_app,
    feature_client,
) -> None:
    context, headers = seed_http_context(feature_client)
    submitted = feature_client.post(
        "/api/v1/asset-usage-requests/personal",
        headers=headers.manager,
        json={
            "asset_ids": [context.main_asset.id],
            "target_user_id": context.employee.id,
        },
    ).get_json()["data"]
    feature_app.config.update(
        TESTING=False,
        DEBUG=False,
        LOCAL_FEISHU_ENABLED=False,
    )

    response = feature_client.post(
        f"/api/v1/asset-usage-requests/{submitted['id']}/mock-feishu-action",
        headers=headers.employee,
        json={
            "action": "APPROVE",
            "external_event_id": "http-disabled-mock",
        },
    )

    body = response.get_json()
    assert response.status_code == 200
    assert body["code"] == ResultCode.NOT_FOUND.code
    assert "data" not in body


def test_malformed_usage_schema_returns_http_400_envelope(feature_client) -> None:
    _context, headers = seed_http_context(feature_client)

    response = feature_client.post(
        "/api/v1/asset-usage-requests/personal",
        headers=headers.manager,
        json={"asset_ids": []},
    )

    body = response.get_json()
    assert response.status_code == 400
    assert body["code"] == ResultCode.BAD_REQUEST.code
    assert "data" not in body


def test_blueprints_expose_only_get_and_post(feature_app) -> None:
    methods = {
        method
        for rule in feature_app.url_map.iter_rules()
        if "asset-usage" in rule.rule or "asset-return" in rule.rule
        for method in rule.methods
        if method not in {"HEAD", "OPTIONS"}
    }
    assert methods <= {"GET", "POST"}


def test_feature_blueprint_sources_keep_http_boundary_rules() -> None:
    api_dir = Path(__file__).parents[1] / "app" / "api"
    for filename in ("asset_usage.py", "asset_returns.py", "local_feishu.py"):
        source = (api_dir / filename).read_text(encoding="utf-8")
        assert "app.models" not in source
        assert "app.extensions" not in source
        assert "@bp.put" not in source
        assert "@bp.patch" not in source
        assert "@bp.delete" not in source
        assert 'methods=["PUT"' not in source
        assert 'methods=["PATCH"' not in source
        assert 'methods=["DELETE"' not in source
