"""Common operation request, approval task, and action API contracts."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from threading import Event

from app import create_app
from app.enums import ApprovalStatus, AssetStatus, DataScope, ExecutionStatus
from app.extensions import db
from app.models import (
    ApprovalStep,
    ApprovalTask,
    Asset,
    AssetCategory,
    AssetLocation,
    AssetSource,
    OperationActionIdempotency,
    OperationExecutionAttempt,
    OperationRequest,
    OperationRequestAsset,
    Organization,
    Permission,
    Role,
    RolePermission,
    Unit,
    User,
    UserRole,
)
from app.operations import operation_handler_registry
from app.security.passwords import hash_password
from config import TestConfig


class ApiNoopHandler:
    operation_type = "API_TEST"

    def revalidate_for_execution(self, operation_request_id: int) -> None:
        return None

    def execute(self, operation_request_id: int, actor_id: int) -> None:
        return None


class ApiFailingHandler:
    operation_type = "API_TEST"
    safe_error_message = "API测试执行失败"

    def revalidate_for_execution(self, operation_request_id: int) -> None:
        return None

    def execute(self, operation_request_id: int, actor_id: int) -> None:
        raise RuntimeError("simulated retry failure")


def _seed_api_context(client) -> dict:
    organization = Organization(code="API-ORG", name="API组织")
    unit = Unit(code="API-UNIT", name="API单位")
    source = AssetSource(code="API-SOURCE", name="API来源")
    location = AssetLocation(code="API-LOC", name="API地点", is_selectable=True)
    applicant = User(
        username="api-applicant",
        password=hash_password("admin123"),
        enabled=True,
    )
    approver = User(
        username="api-approver",
        password=hash_password("admin123"),
        enabled=True,
    )
    applicant_role = Role(
        code="API-APPLICANT", name="API申请人", data_scope=DataScope.SELF.value
    )
    approver_role = Role(
        code="API-APPROVER", name="API审批人", data_scope=DataScope.ALL.value
    )
    permission_codes = (
        "operation:request:view",
        "approval:task:view",
        "approval:task:approve",
        "approval:execution:retry",
        "approval:execution:terminate",
    )
    permissions = [
        Permission(code=code, name=code, module="operation")
        for code in permission_codes
    ]
    db.session.add_all(
        [
            organization,
            unit,
            source,
            location,
            applicant,
            approver,
            applicant_role,
            approver_role,
            *permissions,
        ]
    )
    db.session.flush()
    applicant.organization_id = organization.id
    approver.organization_id = organization.id
    category = AssetCategory(
        code="API-CATEGORY",
        name="API分类",
        service_life_months=12,
        default_unit_id=unit.id,
    )
    db.session.add(category)
    db.session.flush()
    db.session.add_all(
        [
            UserRole(user_id=applicant.id, role_id=applicant_role.id),
            UserRole(user_id=approver.id, role_id=approver_role.id),
            *[
                RolePermission(role_id=approver_role.id, permission_id=permission.id)
                for permission in permissions
            ],
            RolePermission(
                role_id=applicant_role.id,
                permission_id=permissions[0].id,
            ),
        ]
    )
    asset = Asset(
        asset_code="API-ASSET",
        asset_name="API资产",
        status=AssetStatus.IDLE.value,
        organization_id=organization.id,
        category_id=category.id,
        unit_id=unit.id,
        original_amount=Decimal("100.00"),
        purchase_date=date(2026, 7, 17),
        manager_id=applicant.id,
        source_id=source.id,
        location_id=location.id,
    )
    db.session.add(asset)
    db.session.flush()
    operation = OperationRequest(
        request_no="API-REQUEST",
        operation_type="API_TEST",
        applicant_id=applicant.id,
        approval_status=ApprovalStatus.PENDING.value,
        execution_status=ExecutionStatus.NOT_STARTED.value,
    )
    db.session.add(operation)
    db.session.flush()
    snapshot = OperationRequestAsset(
        operation_request_id=operation.id,
        asset_id=asset.id,
        asset_code_snapshot=asset.asset_code,
        asset_name_snapshot=asset.asset_name,
        asset_status_snapshot=asset.status,
        asset_version_snapshot=asset.version,
        organization_id_snapshot=organization.id,
        before_data={"original_amount": "100.00", "status": asset.status},
        target_data={},
    )
    step = ApprovalStep(
        operation_request_id=operation.id,
        level_no=1,
        sign_mode="OR_SIGN",
        status="PENDING",
    )
    db.session.add_all([snapshot, step])
    db.session.flush()
    task = ApprovalTask(
        approval_step_id=step.id,
        approver_id=approver.id,
        status="PENDING",
    )
    db.session.add(task)
    db.session.commit()

    def login(username: str) -> dict[str, str]:
        token = client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": "admin123"},
        ).get_json()["data"]["token"]
        return {"Authorization": f"Bearer {token}"}

    return {
        "operation": operation,
        "task": task,
        "applicant_headers": login(applicant.username),
        "approver_headers": login(approver.username),
    }


def test_common_request_and_my_task_queries_protect_amount_and_self_scope(
    client,
) -> None:
    context = _seed_api_context(client)
    operation = context["operation"]
    listed = client.get(
        "/api/v1/operation-requests", headers=context["applicant_headers"]
    ).get_json()["data"]
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == operation.id
    detail = client.get(
        f"/api/v1/operation-requests/{operation.id}",
        headers=context["applicant_headers"],
    ).get_json()["data"]
    assert "original_amount" not in detail["assets"][0]["before_data"]

    tasks = client.get(
        "/api/v1/approval-tasks/my", headers=context["approver_headers"]
    ).get_json()["data"]
    assert [item["id"] for item in tasks] == [context["task"].id]


def test_common_approve_withdraw_retry_and_terminate_actions(client) -> None:
    context = _seed_api_context(client)
    operation_handler_registry.clear()
    operation_handler_registry.register(ApiNoopHandler())
    approved = client.post(
        f"/api/v1/approval-tasks/{context['task'].id}/approve",
        headers=context["approver_headers"],
        json={"opinion": "同意"},
    ).get_json()["data"]
    assert approved["approval_status"] == ApprovalStatus.APPROVED.value
    assert approved["execution_status"] == ExecutionStatus.SUCCESS.value

    failed = OperationRequest(
        request_no="API-FAILED",
        operation_type="API_TEST",
        applicant_id=context["operation"].applicant_id,
        approval_status=ApprovalStatus.APPROVED.value,
        execution_status=ExecutionStatus.FAILED.value,
    )
    pending = OperationRequest(
        request_no="API-WITHDRAW",
        operation_type="API_TEST",
        applicant_id=context["operation"].applicant_id,
        approval_status=ApprovalStatus.PENDING.value,
        execution_status=ExecutionStatus.NOT_STARTED.value,
    )
    db.session.add_all([failed, pending])
    db.session.commit()
    retried = client.post(
        f"/api/v1/operation-requests/{failed.id}/retry",
        headers=context["approver_headers"],
    ).get_json()["data"]
    assert retried["execution_status"] == ExecutionStatus.SUCCESS.value

    failed.execution_status = ExecutionStatus.FAILED.value
    db.session.commit()
    terminated = client.post(
        f"/api/v1/operation-requests/{failed.id}/terminate",
        headers=context["approver_headers"],
        json={"reason": "无法继续", "confirmed": True},
    ).get_json()["data"]
    assert terminated["execution_status"] == ExecutionStatus.TERMINATED.value

    withdrawn = client.post(
        f"/api/v1/operation-requests/{pending.id}/withdraw",
        headers=context["applicant_headers"],
        json={"reason": "不再需要"},
    ).get_json()["data"]
    assert withdrawn["approval_status"] == ApprovalStatus.WITHDRAWN.value


def test_approval_and_retry_actions_replay_by_idempotency_key(client) -> None:
    context = _seed_api_context(client)
    operation_handler_registry.clear()
    operation_handler_registry.register(ApiNoopHandler())

    approval_url = f"/api/v1/approval-tasks/{context['task'].id}/approve"
    approval_payload = {"opinion": "同意", "idempotency_key": "approve-once"}
    first_approval = client.post(
        approval_url,
        headers=context["approver_headers"],
        json=approval_payload,
    ).get_json()
    replayed_approval = client.post(
        approval_url,
        headers=context["approver_headers"],
        json=approval_payload,
    ).get_json()

    assert first_approval["code"] == 200
    assert replayed_approval["code"] == 200
    assert replayed_approval["data"]["id"] == first_approval["data"]["id"]
    assert (
        db.session.query(OperationExecutionAttempt)
        .filter_by(operation_request_id=context["operation"].id)
        .count()
        == 1
    )

    failed = OperationRequest(
        request_no="API-IDEMPOTENT-RETRY",
        operation_type="API_TEST",
        applicant_id=context["operation"].applicant_id,
        approval_status=ApprovalStatus.APPROVED.value,
        execution_status=ExecutionStatus.FAILED.value,
    )
    db.session.add(failed)
    db.session.commit()
    retry_url = f"/api/v1/operation-requests/{failed.id}/retry"
    retry_payload = {"idempotency_key": "retry-once"}
    first_retry = client.post(
        retry_url,
        headers=context["approver_headers"],
        json=retry_payload,
    ).get_json()
    replayed_retry = client.post(
        retry_url,
        headers=context["approver_headers"],
        json=retry_payload,
    ).get_json()

    assert first_retry["code"] == 200
    assert replayed_retry["code"] == 200
    assert replayed_retry["data"]["execution_status"] == ExecutionStatus.SUCCESS.value
    assert (
        db.session.query(OperationExecutionAttempt)
        .filter_by(operation_request_id=failed.id)
        .count()
        == 1
    )
    assert db.session.query(OperationActionIdempotency).count() == 2


def test_failed_retry_replay_keeps_one_attempt_and_durable_action(client) -> None:
    context = _seed_api_context(client)
    failed = OperationRequest(
        request_no="API-IDEMPOTENT-FAILED-RETRY",
        operation_type="API_TEST",
        applicant_id=context["operation"].applicant_id,
        approval_status=ApprovalStatus.APPROVED.value,
        execution_status=ExecutionStatus.FAILED.value,
    )
    db.session.add(failed)
    db.session.commit()
    operation_handler_registry.clear()
    operation_handler_registry.register(ApiFailingHandler())
    url = f"/api/v1/operation-requests/{failed.id}/retry"
    payload = {"idempotency_key": "failed-retry-once"}

    first = client.post(
        url, headers=context["approver_headers"], json=payload
    ).get_json()
    replayed = client.post(
        url, headers=context["approver_headers"], json=payload
    ).get_json()

    assert first["code"] == 200
    assert replayed["code"] == 200
    assert replayed["data"]["id"] == failed.id
    assert replayed["data"]["execution_status"] == ExecutionStatus.FAILED.value
    assert (
        db.session.query(OperationExecutionAttempt)
        .filter_by(operation_request_id=failed.id)
        .count()
        == 1
    )
    action = db.session.query(OperationActionIdempotency).one()
    assert action.operation_request_id == failed.id
    assert action.status == "COMPLETED"


def test_retry_idempotency_key_is_scoped_to_requested_operation(client) -> None:
    context = _seed_api_context(client)
    operations = [
        OperationRequest(
            request_no=f"API-SCOPED-RETRY-{index}",
            operation_type="API_TEST",
            applicant_id=context["operation"].applicant_id,
            approval_status=ApprovalStatus.APPROVED.value,
            execution_status=ExecutionStatus.FAILED.value,
        )
        for index in range(2)
    ]
    db.session.add_all(operations)
    db.session.commit()
    operation_handler_registry.clear()
    operation_handler_registry.register(ApiNoopHandler())
    payload = {"idempotency_key": "same-key-different-request"}

    results = [
        client.post(
            f"/api/v1/operation-requests/{operation.id}/retry",
            headers=context["approver_headers"],
            json=payload,
        ).get_json()
        for operation in operations
    ]

    assert [result["data"]["id"] for result in results] == [
        operation.id for operation in operations
    ]
    assert all(
        result["data"]["execution_status"] == ExecutionStatus.SUCCESS.value
        for result in results
    )
    assert db.session.query(OperationExecutionAttempt).count() == 2
    assert db.session.query(OperationActionIdempotency).count() == 2


def test_processing_retry_replay_returns_explicit_in_progress_error(
    tmp_path, monkeypatch
) -> None:
    database = tmp_path / "retry-processing-replay.db"

    class ConcurrentConfig(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{database}"

    concurrent_app = create_app(config=ConcurrentConfig)
    with concurrent_app.app_context():
        db.create_all()
        context = _seed_api_context(concurrent_app.test_client())
        failed = OperationRequest(
            request_no="API-PROCESSING-RETRY",
            operation_type="API_TEST",
            applicant_id=context["operation"].applicant_id,
            approval_status=ApprovalStatus.APPROVED.value,
            execution_status=ExecutionStatus.FAILED.value,
        )
        db.session.add(failed)
        db.session.commit()
        operation_id = failed.id
        headers = context["approver_headers"]

    operation_handler_registry.clear()
    operation_handler_registry.register(ApiNoopHandler())
    from app.services import operation_executor

    original_retry = operation_executor.retry
    claim_committed = Event()
    release_first = Event()

    def paused_retry(operation_request_id: int, actor_id: int):
        claim_committed.set()
        assert release_first.wait(timeout=5)
        return original_retry(operation_request_id, actor_id)

    monkeypatch.setattr(operation_executor, "retry", paused_retry)
    url = f"/api/v1/operation-requests/{operation_id}/retry"
    payload = {"idempotency_key": "processing-retry"}

    def first_retry() -> dict:
        with concurrent_app.test_client() as request_client:
            response = request_client.post(url, headers=headers, json=payload)
            body: dict = response.get_json()
            return body

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(first_retry)
        assert claim_committed.wait(timeout=5)
        try:
            with concurrent_app.test_client() as duplicate_client:
                duplicate = duplicate_client.post(
                    url, headers=headers, json=payload
                ).get_json()
            assert duplicate["code"] == 1000
            assert "处理中" in duplicate["message"]
        finally:
            release_first.set()
        first = future.result(timeout=5)

    assert first["code"] == 200
    assert first["data"]["execution_status"] == ExecutionStatus.SUCCESS.value
    with concurrent_app.app_context():
        assert db.session.query(OperationExecutionAttempt).count() == 1
        assert db.session.query(OperationActionIdempotency).one().status == "COMPLETED"
        db.drop_all()


def test_waiting_task_id_cannot_process_current_layer(client) -> None:
    context = _seed_api_context(client)
    current_task = context["task"]
    later_step = ApprovalStep(
        operation_request_id=context["operation"].id,
        level_no=2,
        sign_mode="OR_SIGN",
        status="WAITING",
    )
    db.session.add(later_step)
    db.session.flush()
    later_task = ApprovalTask(
        approval_step_id=later_step.id,
        approver_id=current_task.approver_id,
        status="WAITING",
    )
    db.session.add(later_task)
    db.session.commit()

    body = client.post(
        f"/api/v1/approval-tasks/{later_task.id}/approve",
        headers=context["approver_headers"],
        json={"opinion": "错误层级"},
    ).get_json()
    assert body["code"] == 1000
    assert db.session.get(ApprovalTask, current_task.id).status == "PENDING"
    assert db.session.get(ApprovalTask, later_task.id).status == "WAITING"


def test_retry_and_terminate_require_all_asset_organizations_in_scope(client) -> None:
    context = _seed_api_context(client)
    approver_role = db.session.query(Role).filter_by(code="API-APPROVER").one()
    approver_role.data_scope = DataScope.DEPARTMENT.value
    other_organization = Organization(code="API-OTHER-ORG", name="其它API组织")
    db.session.add(other_organization)
    db.session.flush()
    template = db.session.query(Asset).one()
    foreign_asset = Asset(
        asset_code="API-FOREIGN-ASSET",
        asset_name="越权资产",
        status=template.status,
        organization_id=other_organization.id,
        category_id=template.category_id,
        unit_id=template.unit_id,
        original_amount=template.original_amount,
        purchase_date=template.purchase_date,
        manager_id=template.manager_id,
        source_id=template.source_id,
        location_id=template.location_id,
    )
    db.session.add(foreign_asset)
    db.session.flush()
    operation = OperationRequest(
        request_no="API-FOREIGN-FAILED",
        operation_type="API_TEST",
        applicant_id=context["operation"].applicant_id,
        approval_status=ApprovalStatus.APPROVED.value,
        execution_status=ExecutionStatus.FAILED.value,
    )
    db.session.add(operation)
    db.session.flush()
    db.session.add(
        OperationRequestAsset(
            operation_request_id=operation.id,
            asset_id=foreign_asset.id,
            asset_code_snapshot=foreign_asset.asset_code,
            asset_name_snapshot=foreign_asset.asset_name,
            asset_status_snapshot=foreign_asset.status,
            asset_version_snapshot=foreign_asset.version,
            organization_id_snapshot=other_organization.id,
            before_data={},
            target_data={},
        )
    )
    db.session.commit()
    operation_handler_registry.clear()
    operation_handler_registry.register(ApiNoopHandler())

    retry = client.post(
        f"/api/v1/operation-requests/{operation.id}/retry",
        headers=context["approver_headers"],
    ).get_json()
    terminate = client.post(
        f"/api/v1/operation-requests/{operation.id}/terminate",
        headers=context["approver_headers"],
        json={"reason": "越权终止", "confirmed": True},
    ).get_json()
    assert retry["code"] in {403, 404}
    assert terminate["code"] in {403, 404}
    db.session.refresh(operation)
    assert operation.execution_status == ExecutionStatus.FAILED.value


def test_operation_routes_are_get_and_post_only(app) -> None:
    expected_prefixes = ("/api/v1/operation-requests", "/api/v1/approval-tasks")
    routes: dict[str, set[str]] = {}
    for rule in app.url_map.iter_rules():
        if rule.rule.startswith(expected_prefixes):
            routes.setdefault(rule.rule, set()).update(
                set(rule.methods) - {"HEAD", "OPTIONS"}
            )
    assert routes == {
        "/api/v1/operation-requests": {"GET"},
        "/api/v1/operation-requests/<int:operation_request_id>": {"GET"},
        "/api/v1/approval-tasks/my": {"GET"},
        "/api/v1/approval-tasks/<int:task_id>/approve": {"POST"},
        "/api/v1/approval-tasks/<int:task_id>/reject": {"POST"},
        "/api/v1/operation-requests/<int:operation_request_id>/withdraw": {"POST"},
        "/api/v1/operation-requests/<int:operation_request_id>/retry": {"POST"},
        "/api/v1/operation-requests/<int:operation_request_id>/terminate": {"POST"},
    }
