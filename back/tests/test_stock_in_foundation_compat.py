from __future__ import annotations

from datetime import date

from app.enums import AssetDataCompleteness, DataScope
from app.extensions import db
from app.models import (
    Asset,
    AssetCategory,
    AssetCodeReservation,
    AssetLifecycleRecord,
    AssetLocation,
    AssetSource,
    OperationLog,
    OperationExecutionAttempt,
    OperationRequest,
    ApprovalStep,
    ApprovalTask,
    Organization,
    Permission,
    Role,
    RolePermission,
    StockInItem,
    Unit,
    User,
    UserRole,
)
from app.security.passwords import hash_password


def _seed_context(client) -> dict:
    organization = Organization(code="COMPAT", name="兼容性公司")
    unit = Unit(code="COMPAT-UNIT", name="台")
    source = AssetSource(code="COMPAT-SOURCE", name="采购")
    location = AssetLocation(code="COMPAT-LOC", name="兼容性仓库", is_selectable=True)
    applicant = User(
        username="compat-applicant",
        password=hash_password("admin123"),
        enabled=True,
    )
    approver = User(
        username="compat-approver",
        password=hash_password("admin123"),
        enabled=True,
    )
    creator_role = Role(
        code="COMPAT_CREATOR",
        name="兼容性申请人",
        data_scope=DataScope.ALL.value,
    )
    approver_role = Role(
        code="COMPAT_APPROVER",
        name="兼容性审批人",
        data_scope=DataScope.ALL.value,
    )
    create_permission = Permission(
        code="stock-in:create", name="创建入库", module="stock-in"
    )
    view_permission = Permission(
        code="stock-in:view", name="查看入库", module="stock-in"
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
            approver,
            creator_role,
            approver_role,
            create_permission,
            view_permission,
            approve_permission,
        ]
    )
    db.session.flush()
    category = AssetCategory(
        code="COMPAT-CATEGORY",
        name="兼容性分类",
        service_life_months=36,
        default_unit_id=unit.id,
    )
    db.session.add(category)
    db.session.flush()
    db.session.add_all(
        [
            UserRole(user_id=applicant.id, role_id=creator_role.id),
            UserRole(user_id=approver.id, role_id=approver_role.id),
            RolePermission(role_id=creator_role.id, permission_id=create_permission.id),
            RolePermission(role_id=creator_role.id, permission_id=view_permission.id),
            RolePermission(
                role_id=approver_role.id, permission_id=approve_permission.id
            ),
        ]
    )
    db.session.commit()

    def login(username: str) -> dict[str, str]:
        body = client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": "admin123"},
        ).get_json()
        return {"Authorization": f"Bearer {body['data']['token']}"}

    return {
        "organization": organization,
        "unit": unit,
        "source": source,
        "location": location,
        "applicant": applicant,
        "category": category,
        "applicant_headers": login(applicant.username),
        "approver_headers": login(approver.username),
    }


def test_stock_in_http_contract_survives_operation_foundation(client) -> None:
    context = _seed_context(client)
    submitted_response = client.post(
        "/api/v1/stock-in-requests",
        headers=context["applicant_headers"],
        json={
            "organization_id": context["organization"].id,
            "remark": "底座兼容性测试",
            "items": [
                {
                    "usage_company_id": context["organization"].id,
                    "asset_name": "兼容性资产",
                    "category_id": context["category"].id,
                    "unit_id": context["unit"].id,
                    "original_amount": "100.00",
                    "purchase_date": date(2026, 7, 17).isoformat(),
                    "manager_id": context["applicant"].id,
                    "source_id": context["source"].id,
                    "location_id": context["location"].id,
                    "serial_number": "COMPAT-SN-001",
                }
            ],
        },
    )
    submitted_body = submitted_response.get_json()
    assert submitted_response.status_code == 200
    assert submitted_body["code"] == 200
    submitted = submitted_body["data"]
    assert submitted["approval_status"] == "PENDING"
    assert submitted["execution_status"] == "NOT_STARTED"
    assert submitted["items"][0]["asset_code"] == "COMPAT-COMPAT-CATEGORY-0001"
    stock_item = db.session.query(StockInItem).one()
    assert stock_item.service_life_months == 36
    assert stock_item.expected_expiry_date == date(2029, 7, 17)
    assert stock_item.custom_attributes == {}
    operation = db.session.get(OperationRequest, submitted["id"])
    assert operation is not None
    assert operation.approval_flow_version_id is not None
    step = (
        db.session.query(ApprovalStep)
        .filter_by(operation_request_id=operation.id)
        .one()
    )
    assert step.flow_layer_id is not None
    assert (
        db.session.query(ApprovalTask).filter_by(approval_step_id=step.id).count() == 1
    )

    listed = client.get(
        "/api/v1/stock-in-requests", headers=context["applicant_headers"]
    ).get_json()["data"]
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == submitted["id"]

    context["category"].service_life_months = 120
    db.session.commit()
    approved_response = client.post(
        f"/api/v1/stock-in-requests/{submitted['id']}/approve",
        headers=context["approver_headers"],
        json={"opinion": "兼容性通过"},
    )
    approved_body = approved_response.get_json()
    assert approved_response.status_code == 200
    assert approved_body["code"] == 200
    assert approved_body["data"]["approval_status"] == "APPROVED"
    assert approved_body["data"]["execution_status"] == "SUCCESS"
    asset = db.session.query(Asset).one()
    assert asset.service_life_months == 36
    assert asset.expected_expiry_date == date(2029, 7, 17)
    assert asset.custom_attributes == {}
    assert asset.data_completeness == AssetDataCompleteness.COMPLETE.value
    assert db.session.query(AssetCodeReservation).one().status == "ACTIVE"
    assert db.session.query(AssetLifecycleRecord).count() == 1
    assert db.session.query(OperationLog).count() == 1
    attempt = db.session.query(OperationExecutionAttempt).one()
    assert attempt.trigger_type == "APPROVAL"
    assert attempt.status == "SUCCESS"


def test_stock_in_route_methods_remain_get_and_post_only(app) -> None:
    routes: dict[str, set[str]] = {}
    for rule in app.url_map.iter_rules():
        if rule.rule.startswith("/api/v1/stock-in-requests"):
            routes.setdefault(rule.rule, set()).update(
                set(rule.methods) - {"HEAD", "OPTIONS"}
            )
    assert routes == {
        "/api/v1/stock-in-requests": {"GET", "POST"},
        "/api/v1/stock-in-requests/<int:operation_request_id>": {"GET"},
        "/api/v1/stock-in-requests/<int:operation_request_id>/approve": {"POST"},
        "/api/v1/stock-in-requests/<int:operation_request_id>/reject": {"POST"},
        "/api/v1/stock-in-requests/<int:operation_request_id>/resubmit": {"POST"},
        "/api/v1/stock-in-requests/<int:operation_request_id>/retry": {"POST"},
        "/api/v1/stock-in-requests/<int:operation_request_id>/withdraw": {"POST"},
    }
