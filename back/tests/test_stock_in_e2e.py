from __future__ import annotations

from datetime import date

from app.enums import DataScope, RecordStatus
from app.extensions import db
from app.models import (
    AssetCategory,
    Permission,
    Role,
    RolePermission,
    Supplier,
    User,
    UserRole,
)
from app.security.passwords import hash_password


def _data(response):
    body = response.get_json()
    assert response.status_code == 200, body
    assert body["code"] == 200, body
    return body["data"]


def _login(client, username: str) -> dict[str, str]:
    data = _data(
        client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": "admin123"},
        )
    )
    return {"Authorization": f"Bearer {data['token']}"}


def _seed_http_actors() -> tuple[User, User, User]:
    admin = User(username="e2e-admin", password=hash_password("admin123"), enabled=True)
    applicant = User(
        username="e2e-applicant", password=hash_password("admin123"), enabled=True
    )
    approver = User(
        username="e2e-approver", password=hash_password("admin123"), enabled=True
    )
    admin_role = Role(
        code="E2E_BOOTSTRAP_ADMIN",
        name="E2E bootstrap admin",
        data_scope=DataScope.ALL.value,
    )
    permission_codes = {
        "asset-category:manage",
        "asset-source:manage",
        "asset:amount:view",
        "asset:service-life:update",
        "asset:view",
        "audit:view",
        "location:manage",
        "organization:manage",
        "stock-in:approve",
        "stock-in:create",
        "stock-in:view",
        "system:role:manage",
        "system:role:view",
        "unit:manage",
    }
    permissions = [
        Permission(code=code, name=code, module=code.split(":")[0])
        for code in sorted(permission_codes)
    ]
    db.session.add_all([admin, applicant, approver, admin_role, *permissions])
    db.session.flush()
    db.session.add(UserRole(user_id=admin.id, role_id=admin_role.id))
    db.session.add_all(
        [
            RolePermission(role_id=admin_role.id, permission_id=permission.id)
            for permission in permissions
        ]
    )
    db.session.commit()
    return admin, applicant, approver


def test_complete_stock_in_workflow_through_http(client) -> None:
    _admin, applicant, approver = _seed_http_actors()
    admin_headers = _login(client, "e2e-admin")

    permission_ids = {
        item["code"]: item["id"]
        for item in _data(client.get("/api/v1/permissions", headers=admin_headers))
    }

    applicant_role = _data(
        client.post(
            "/api/v1/roles",
            headers=admin_headers,
            json={
                "code": "E2E_APPLICANT",
                "name": "入库申请人",
                "data_scope": "ALL",
            },
        )
    )
    _data(
        client.post(
            f"/api/v1/roles/{applicant_role['id']}/permissions/update",
            headers=admin_headers,
            json={
                "permission_ids": [
                    permission_ids["asset:service-life:update"],
                    permission_ids["stock-in:create"],
                    permission_ids["stock-in:view"],
                ]
            },
        )
    )
    _data(
        client.post(
            f"/api/v1/users/{applicant.id}/roles/update",
            headers=admin_headers,
            json={"role_ids": [applicant_role["id"]]},
        )
    )

    approver_role = _data(
        client.post(
            "/api/v1/roles",
            headers=admin_headers,
            json={
                "code": "E2E_APPROVER",
                "name": "入库审批人",
                "data_scope": "ALL",
            },
        )
    )
    _data(
        client.post(
            f"/api/v1/roles/{approver_role['id']}/permissions/update",
            headers=admin_headers,
            json={"permission_ids": [permission_ids["stock-in:approve"]]},
        )
    )
    _data(
        client.post(
            f"/api/v1/users/{approver.id}/roles/update",
            headers=admin_headers,
            json={"role_ids": [approver_role["id"]]},
        )
    )

    organization = _data(
        client.post(
            "/api/v1/organizations",
            headers=admin_headers,
            json={"code": "358466", "name": "E2E 公司"},
        )
    )
    unit = _data(
        client.post(
            "/api/v1/units",
            headers=admin_headers,
            json={"code": "E2E-UNIT", "name": "台"},
        )
    )
    source = _data(
        client.post(
            "/api/v1/asset-sources",
            headers=admin_headers,
            json={"code": "E2E-PURCHASE", "name": "采购"},
        )
    )
    location = _data(
        client.post(
            "/api/v1/locations",
            headers=admin_headers,
            json={"code": "E2E-LOC", "name": "E2E 仓库", "is_selectable": True},
        )
    )
    category = _data(
        client.post(
            "/api/v1/asset-categories",
            headers=admin_headers,
            json={
                "code": "10100",
                "name": "笔记本电脑",
                "service_life_months": 36,
                "default_unit_id": unit["id"],
            },
        )
    )
    supplier = Supplier(
        code="E2E-SUPPLIER",
        name="E2E 原供应商",
        status=RecordStatus.ENABLED.value,
    )
    db.session.add(supplier)
    db.session.commit()
    supplier_id = supplier.id

    applicant_headers = _login(client, applicant.username)
    submitted = _data(
        client.post(
            "/api/v1/stock-in-requests",
            headers=applicant_headers,
            json={
                "organization_id": organization["id"],
                "remark": "HTTP E2E",
                "items": [
                    {
                        "asset_name": "E2E MacBook Air",
                        "category_id": category["id"],
                        "unit_id": unit["id"],
                        "original_amount": "7999.00",
                        "purchase_date": date(2026, 7, 17).isoformat(),
                        "supplier_id": supplier_id,
                        "service_life_months": 48,
                        "manager_id": applicant.id,
                        "source_id": source["id"],
                        "location_id": location["id"],
                        "serial_number": "E2E-SN-001",
                        "custom_attributes": {
                            "warranty": {"years": 3, "onsite": True},
                            "tags": ["laptop", None, 2026],
                        },
                    }
                ],
            },
        )
    )
    submitted_item = submitted["items"][0]
    assert submitted_item["supplier_id"] == supplier_id
    assert submitted_item["supplier_snapshot"] == {
        "id": supplier_id,
        "code": "E2E-SUPPLIER",
        "name": "E2E 原供应商",
    }
    assert submitted_item["service_life_months"] == 48
    assert submitted_item["expected_expiry_date"] == "2030-07-17"
    assert submitted_item["custom_attributes"] == {
        "warranty": {"years": 3, "onsite": True},
        "tags": ["laptop", None, 2026],
    }
    listed = _data(client.get("/api/v1/stock-in-requests", headers=applicant_headers))
    assert listed["items"][0]["id"] == submitted["id"]

    category_model = db.session.get(AssetCategory, category["id"])
    assert category_model is not None
    category_model.service_life_months = 120
    supplier.name = "E2E 已修改供应商"
    supplier.status = RecordStatus.DISABLED.value
    db.session.commit()

    detail = _data(
        client.get(
            f"/api/v1/stock-in-requests/{submitted['id']}",
            headers=applicant_headers,
        )
    )
    assert detail["items"][0]["supplier_snapshot"] == {
        "id": supplier_id,
        "code": "E2E-SUPPLIER",
        "name": "E2E 原供应商",
    }

    approver_headers = _login(client, approver.username)
    approved = _data(
        client.post(
            f"/api/v1/stock-in-requests/{submitted['id']}/approve",
            headers=approver_headers,
            json={"opinion": "HTTP E2E 通过"},
        )
    )
    assert approved["approval_status"] == "APPROVED"
    assert approved["execution_status"] == "SUCCESS"

    assets = _data(
        client.get(
            "/api/v1/assets",
            headers=admin_headers,
            query_string={"asset_code": submitted["items"][0]["asset_code"]},
        )
    )
    assert assets["total"] == 1
    asset = assets["items"][0]
    assert asset["original_amount"] == "7999.00"
    assert asset["supplier_id"] == supplier_id
    assert asset["service_life_months"] == 48
    assert asset["expected_expiry_date"] == "2030-07-17"
    assert asset["custom_attributes"] == {
        "warranty": {"years": 3, "onsite": True},
        "tags": ["laptop", None, 2026],
    }
    assert asset["data_completeness"] == "COMPLETE"
    lifecycle = _data(
        client.get(f"/api/v1/assets/{asset['id']}/lifecycle", headers=admin_headers)
    )
    assert lifecycle[0]["operation_no"] == submitted["request_no"]
    audit_logs = _data(client.get("/api/v1/audit-logs", headers=admin_headers))
    assert audit_logs[0]["resource_id"] == str(asset["id"])
