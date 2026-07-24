from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier

from app import create_app
from app.enums import AssetCodeStatus, DataScope
from app.extensions import db
from app.models import (
    ApprovalRecord,
    ApprovalTask,
    Asset,
    AssetCategory,
    AssetCodeReservation,
    AssetLifecycleRecord,
    AssetLocation,
    AssetSource,
    OperationLog,
    OperationRequest,
    Organization,
    Permission,
    Role,
    RolePermission,
    StockInItem,
    StockInRequest,
    Unit,
    User,
    UserRole,
)
from app.repositories import asset_repository
from app.security.passwords import hash_password
from config import TestConfig


def _workflow_setup(client, self_approve: bool = False):
    organization = Organization(code="358466", name="公司")
    unit = Unit(code="UNIT", name="台")
    source = AssetSource(code="PURCHASE", name="采购")
    location = AssetLocation(code="LOC", name="仓库", is_selectable=True)
    applicant = User(
        username="workflow-applicant", password=hash_password("admin123"), enabled=True
    )
    approver = (
        applicant
        if self_approve
        else User(
            username="workflow-approver",
            password=hash_password("admin123"),
            enabled=True,
        )
    )
    db.session.add_all([organization, unit, source, location, applicant])
    if approver is not applicant:
        db.session.add(approver)
    db.session.flush()
    category = AssetCategory(
        code="10100", name="笔记本", service_life_months=36, default_unit_id=unit.id
    )
    db.session.add(category)

    permission_codes = ["stock-in:create", "stock-in:view"]
    if self_approve:
        permission_codes.append("stock-in:approve")
    creator_role = Role(
        code="WORKFLOW_CREATOR", name="申请人", data_scope=DataScope.ALL.value
    )
    creator_permissions = [
        Permission(code=code, name=code, module="stock-in") for code in permission_codes
    ]
    db.session.add_all([creator_role, *creator_permissions])
    db.session.flush()
    db.session.add(UserRole(user_id=applicant.id, role_id=creator_role.id))
    db.session.add_all(
        [
            RolePermission(role_id=creator_role.id, permission_id=permission.id)
            for permission in creator_permissions
        ]
    )
    if not self_approve:
        approve_role = Role(
            code="WORKFLOW_APPROVER", name="审批人", data_scope=DataScope.ALL.value
        )
        approve_permission = Permission(
            code="stock-in:approve", name="审批入库", module="stock-in"
        )
        db.session.add_all([approve_role, approve_permission])
        db.session.flush()
        db.session.add_all(
            [
                UserRole(user_id=approver.id, role_id=approve_role.id),
                RolePermission(
                    role_id=approve_role.id, permission_id=approve_permission.id
                ),
            ]
        )
    db.session.commit()

    def login(username: str) -> dict[str, str]:
        token = client.post(
            "/api/v1/auth/login", json={"username": username, "password": "admin123"}
        ).get_json()["data"]["token"]
        return {"Authorization": f"Bearer {token}"}

    payload = {
        "organization_id": organization.id,
        "items": [
            {
                "asset_name": "MacBook Air",
                "category_id": category.id,
                "unit_id": unit.id,
                "original_amount": "7999.00",
                "purchase_date": date(2026, 7, 17).isoformat(),
                "manager_id": applicant.id,
                "source_id": source.id,
                "location_id": location.id,
                "serial_number": "APPROVAL-SN",
            }
        ],
    }
    applicant_headers = login(applicant.username)
    request_data = client.post(
        "/api/v1/stock-in-requests", headers=applicant_headers, json=payload
    ).get_json()["data"]
    return {
        "applicant": applicant,
        "approver": approver,
        "applicant_headers": applicant_headers,
        "approver_headers": login(approver.username),
        "request": request_data,
    }


def test_approval_executes_formal_stock_in_and_is_idempotent(client) -> None:
    context = _workflow_setup(client)
    request_id = context["request"]["id"]
    approved = client.post(
        f"/api/v1/stock-in-requests/{request_id}/approve",
        headers=context["approver_headers"],
        json={"opinion": "同意"},
    ).get_json()["data"]

    assert approved["approval_status"] == "APPROVED"
    assert approved["execution_status"] == "SUCCESS"
    assert db.session.query(Asset).count() == 1
    assert (
        db.session.query(AssetCodeReservation).one().status
        == AssetCodeStatus.ACTIVE.value
    )
    assert db.session.query(AssetLifecycleRecord).count() == 1
    assert db.session.query(OperationLog).count() == 1
    assert db.session.query(ApprovalRecord).count() == 1

    repeated = client.post(
        f"/api/v1/stock-in-requests/{request_id}/approve",
        headers=context["approver_headers"],
        json={"opinion": "重复点击"},
    ).get_json()["data"]
    assert repeated["execution_status"] == "SUCCESS"
    assert db.session.query(Asset).count() == 1
    assert db.session.query(ApprovalRecord).count() == 1


def test_approval_deep_copies_frozen_custom_attributes(
    client,
    monkeypatch,
) -> None:
    context = _workflow_setup(client)
    request_id = context["request"]["id"]
    stock_item = db.session.query(StockInItem).one()
    stock_item.custom_attributes = {"nested": {"value": 1}}
    db.session.commit()
    original_add = asset_repository.add

    def assert_isolated(asset: Asset) -> Asset:
        assert (
            asset.custom_attributes["nested"]
            is not stock_item.custom_attributes["nested"]
        )
        return original_add(asset)

    monkeypatch.setattr(asset_repository, "add", assert_isolated)

    approved = client.post(
        f"/api/v1/stock-in-requests/{request_id}/approve",
        headers=context["approver_headers"],
        json={"opinion": "同意"},
    ).get_json()["data"]

    assert approved["execution_status"] == "SUCCESS"
    assert stock_item.custom_attributes == {"nested": {"value": 1}}


def test_stock_in_self_approval_is_allowed_for_snapshotted_approver(client) -> None:
    context = _workflow_setup(client, self_approve=True)
    response = client.post(
        f"/api/v1/stock-in-requests/{context['request']['id']}/approve",
        headers=context["applicant_headers"],
        json={"opinion": "自审入库"},
    )
    assert response.get_json()["data"]["execution_status"] == "SUCCESS"


def test_reject_voids_codes_without_creating_assets(client) -> None:
    rejected_context = _workflow_setup(client)
    rejected = client.post(
        f"/api/v1/stock-in-requests/{rejected_context['request']['id']}/reject",
        headers=rejected_context["approver_headers"],
        json={"opinion": "资料不完整"},
    ).get_json()["data"]
    assert rejected["approval_status"] == "REJECTED"
    assert (
        db.session.query(AssetCodeReservation).one().status
        == AssetCodeStatus.VOID.value
    )
    assert db.session.query(Asset).count() == 0


def test_applicant_can_withdraw_pending_request_and_void_code(client) -> None:
    context = _workflow_setup(client)
    response = client.post(
        f"/api/v1/stock-in-requests/{context['request']['id']}/withdraw",
        headers=context["applicant_headers"],
    )
    assert response.get_json()["data"]["approval_status"] == "WITHDRAWN"
    assert (
        db.session.query(AssetCodeReservation).one().status
        == AssetCodeStatus.VOID.value
    )
    assert db.session.query(Asset).count() == 0


def test_execution_failure_keeps_approval_and_can_retry(client, monkeypatch) -> None:
    context = _workflow_setup(client)
    request_id = context["request"]["id"]
    from app.services import asset_service

    original = asset_service.stock_in_request

    def fail_execution(*_args, **_kwargs):
        raise RuntimeError("mysql://root:secret@database/internal-table")

    monkeypatch.setattr(asset_service, "stock_in_request", fail_execution)
    failed = client.post(
        f"/api/v1/stock-in-requests/{request_id}/approve",
        headers=context["approver_headers"],
        json={"opinion": "审批通过"},
    ).get_json()["data"]
    assert failed["approval_status"] == "APPROVED"
    assert failed["execution_status"] == "FAILED"
    assert failed["execution_error"] == "资产入库执行失败，请联系管理员或稍后重试"
    assert "secret" not in failed["execution_error"]
    assert (
        "internal-table"
        not in db.session.get(OperationRequest, request_id).execution_error
    )
    assert db.session.query(Asset).count() == 0

    retry_permission = Permission(
        code="approval:execution:retry", name="重试执行", module="approval"
    )
    role = db.session.query(Role).filter_by(code="WORKFLOW_APPROVER").one()
    db.session.add(retry_permission)
    db.session.flush()
    db.session.add(RolePermission(role_id=role.id, permission_id=retry_permission.id))
    db.session.commit()
    monkeypatch.setattr(asset_service, "stock_in_request", original)

    retried = client.post(
        f"/api/v1/stock-in-requests/{request_id}/retry",
        headers=context["approver_headers"],
    ).get_json()["data"]
    assert retried["execution_status"] == "SUCCESS"
    assert db.session.query(Asset).count() == 1


def test_concurrent_approve_and_reject_produce_one_consistent_terminal_state(
    tmp_path,
) -> None:
    database = tmp_path / "approval-concurrency.db"

    class ConcurrentConfig(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{database}"

    concurrent_app = create_app(config=ConcurrentConfig)
    with concurrent_app.app_context():
        db.create_all()
        organization = Organization(code="CONCURRENT", name="并发审批公司")
        unit = Unit(code="CONCURRENT-UNIT", name="并发审批单位")
        source = AssetSource(code="CONCURRENT-SOURCE", name="并发审批来源")
        location = AssetLocation(
            code="CONCURRENT-LOC", name="并发审批仓库", is_selectable=True
        )
        applicant = User(
            username="concurrent-applicant",
            password=hash_password("admin123"),
            enabled=True,
        )
        approvers = [
            User(
                username=f"concurrent-approver-{index}",
                password=hash_password("admin123"),
                enabled=True,
            )
            for index in range(2)
        ]
        creator_role = Role(
            code="CONCURRENT_CREATOR",
            name="并发申请人",
            data_scope=DataScope.ALL.value,
        )
        approver_role = Role(
            code="CONCURRENT_APPROVER",
            name="并发审批人",
            data_scope=DataScope.ALL.value,
        )
        create_permission = Permission(
            code="stock-in:create", name="创建入库", module="stock-in"
        )
        approve_permission = Permission(
            code="stock-in:approve", name="审批入库", module="stock-in"
        )
        db.session.add_all(
            [
                organization,
                unit,
                source,
                location,
                applicant,
                *approvers,
                creator_role,
                approver_role,
                create_permission,
                approve_permission,
            ]
        )
        db.session.flush()
        category = AssetCategory(
            code="CONCURRENT-CATEGORY",
            name="并发审批分类",
            service_life_months=12,
            default_unit_id=unit.id,
        )
        db.session.add(category)
        db.session.flush()
        db.session.add_all(
            [
                UserRole(user_id=applicant.id, role_id=creator_role.id),
                *[
                    UserRole(user_id=approver.id, role_id=approver_role.id)
                    for approver in approvers
                ],
                RolePermission(
                    role_id=creator_role.id, permission_id=create_permission.id
                ),
                RolePermission(
                    role_id=approver_role.id, permission_id=approve_permission.id
                ),
            ]
        )
        db.session.commit()
        organization_id = organization.id
        unit_id = unit.id
        source_id = source.id
        location_id = location.id
        applicant_id = applicant.id
        category_id = category.id
        approver_names = [item.username for item in approvers]

    client = concurrent_app.test_client()

    def token(username: str) -> str:
        return client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": "admin123"},
        ).get_json()["data"]["token"]

    applicant_token = token("concurrent-applicant")
    submitted = client.post(
        "/api/v1/stock-in-requests",
        headers={"Authorization": f"Bearer {applicant_token}"},
        json={
            "organization_id": organization_id,
            "items": [
                {
                    "asset_name": "并发审批资产",
                    "category_id": category_id,
                    "unit_id": unit_id,
                    "original_amount": "1.00",
                    "purchase_date": "2026-07-17",
                    "manager_id": applicant_id,
                    "source_id": source_id,
                    "location_id": location_id,
                    "serial_number": "CONCURRENT-APPROVAL-SN",
                }
            ],
        },
    ).get_json()["data"]
    approver_tokens = [token(username) for username in approver_names]
    barrier = Barrier(2)

    def decide(action: str, auth_token: str) -> dict:
        with concurrent_app.test_client() as thread_client:
            barrier.wait()
            return thread_client.post(
                f"/api/v1/stock-in-requests/{submitted['id']}/{action}",
                headers={"Authorization": f"Bearer {auth_token}"},
                json={"opinion": "并发决策"},
            ).get_json()

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(
                lambda args: decide(*args),
                zip(("approve", "reject"), approver_tokens, strict=True),
            )
        )

    assert sorted(response["code"] for response in responses) == [200, 1000]
    with concurrent_app.app_context():
        operation = db.session.get(OperationRequest, submitted["id"])
        assert operation is not None
        assert db.session.query(ApprovalRecord).count() == 1
        tasks = db.session.query(ApprovalTask).all()
        assert len(tasks) == 2
        assert sum(task.status == "WITHDRAWN" for task in tasks) == 1
        reservation = db.session.query(AssetCodeReservation).one()
        stock_in = db.session.query(StockInRequest).one()
        assert stock_in.operation_request_id == operation.id
        if operation.approval_status == "APPROVED":
            assert operation.execution_status == "SUCCESS"
            assert db.session.query(Asset).count() == 1
            assert reservation.status == AssetCodeStatus.ACTIVE.value
        else:
            assert operation.approval_status == "REJECTED"
            assert db.session.query(Asset).count() == 0
            assert reservation.status == AssetCodeStatus.VOID.value
        db.drop_all()
