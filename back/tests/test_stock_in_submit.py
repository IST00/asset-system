from __future__ import annotations

from datetime import date

from sqlalchemy.exc import IntegrityError

from app.enums import DataScope
from app.extensions import db
from app.models import (
    ApprovalTask,
    AssetCategory,
    AssetCodeReservation,
    AssetCodeSequence,
    AssetLocation,
    AssetSource,
    OperationRequest,
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
from app.services import stock_in_service


def _role_with_permissions(code: str, *permission_codes: str) -> Role:
    role = Role(code=code, name=code, data_scope=DataScope.ALL.value)
    permissions = [
        Permission(code=item, name=item, module=item.split(":")[0])
        for item in permission_codes
    ]
    db.session.add_all([role, *permissions])
    db.session.flush()
    db.session.add_all(
        [RolePermission(role_id=role.id, permission_id=item.id) for item in permissions]
    )
    return role


def _assign(user: User, role: Role) -> None:
    db.session.flush()
    db.session.add(UserRole(user_id=user.id, role_id=role.id))


def _setup(client, with_approver: bool = True):
    organization = Organization(code="358466", name="公司")
    unit = Unit(code="UNIT", name="台")
    source = AssetSource(code="PURCHASE", name="采购")
    location = AssetLocation(code="LOC000001", name="仓库", is_selectable=True)
    applicant = User(
        username="stock-applicant", password=hash_password("admin123"), enabled=True
    )
    manager = User(username="asset-manager", password="x", enabled=True)
    create_role = _role_with_permissions(
        "STOCK_CREATOR", "stock-in:create", "stock-in:view"
    )
    db.session.add_all([organization, unit, source, location, applicant, manager])
    db.session.flush()
    _assign(applicant, create_role)
    category = AssetCategory(
        code="10100", name="笔记本电脑", service_life_months=36, default_unit_id=unit.id
    )
    db.session.add(category)
    approver = None
    if with_approver:
        approver = User(username="stock-approver", password="x", enabled=True)
        approve_role = _role_with_permissions("STOCK_APPROVER", "stock-in:approve")
        db.session.add(approver)
        db.session.flush()
        _assign(approver, approve_role)
    db.session.commit()
    token = client.post(
        "/api/v1/auth/login",
        json={"username": "stock-applicant", "password": "admin123"},
    ).get_json()["data"]["token"]
    return {
        "headers": {"Authorization": f"Bearer {token}"},
        "organization": organization,
        "unit": unit,
        "source": source,
        "location": location,
        "applicant": applicant,
        "manager": manager,
        "category": category,
        "approver": approver,
    }


def _item(context, **overrides):
    item = {
        "asset_name": "MacBook Air",
        "category_id": context["category"].id,
        "unit_id": context["unit"].id,
        "original_amount": "7999.00",
        "purchase_date": date(2026, 7, 17).isoformat(),
        "manager_id": context["manager"].id,
        "source_id": context["source"].id,
        "location_id": context["location"].id,
        "serial_number": " SN-001 ",
    }
    item.update(overrides)
    return item


def test_submit_reserves_codes_and_snapshots_approvers(client) -> None:
    context = _setup(client)
    response = client.post(
        "/api/v1/stock-in-requests",
        headers=context["headers"],
        json={
            "organization_id": context["organization"].id,
            "remark": "首批入库",
            "items": [
                _item(context),
                _item(context, asset_name="MacBook Pro", serial_number="SN-002"),
            ],
        },
    )
    body = response.get_json()

    assert body["code"] == 200
    assert body["data"]["approval_status"] == "PENDING"
    assert body["data"]["execution_status"] == "NOT_STARTED"
    assert [item["asset_code"] for item in body["data"]["items"]] == [
        "358466-10100-0001",
        "358466-10100-0002",
    ]
    assert db.session.query(AssetCodeReservation).count() == 2
    assert db.session.query(ApprovalTask).one().approver_id == context["approver"].id


def test_submit_without_approver_creates_nothing(client) -> None:
    context = _setup(client, with_approver=False)
    response = client.post(
        "/api/v1/stock-in-requests",
        headers=context["headers"],
        json={
            "organization_id": context["organization"].id,
            "items": [_item(context)],
        },
    )

    assert response.get_json()["code"] == 1000
    assert "审批人" in response.get_json()["message"]
    assert db.session.query(OperationRequest).count() == 0
    assert db.session.query(AssetCodeSequence).count() == 0


def test_zero_amount_requires_reason_and_batch_validation_is_atomic(client) -> None:
    context = _setup(client)
    response = client.post(
        "/api/v1/stock-in-requests",
        headers=context["headers"],
        json={
            "organization_id": context["organization"].id,
            "items": [
                _item(context, serial_number="VALID"),
                _item(context, original_amount="0.00", serial_number="ZERO"),
            ],
        },
    )

    assert response.status_code == 400
    assert db.session.query(OperationRequest).count() == 0
    assert db.session.query(StockInItem).count() == 0


def test_pending_serial_number_is_unique_ignoring_case_and_spaces(client) -> None:
    context = _setup(client)
    first = client.post(
        "/api/v1/stock-in-requests",
        headers=context["headers"],
        json={"organization_id": context["organization"].id, "items": [_item(context)]},
    )
    assert first.get_json()["code"] == 200

    duplicate = client.post(
        "/api/v1/stock-in-requests",
        headers=context["headers"],
        json={
            "organization_id": context["organization"].id,
            "items": [_item(context, serial_number="sn-001")],
        },
    )
    assert duplicate.get_json()["code"] == 1000
    assert "序列号" in duplicate.get_json()["message"]


def test_serial_reservation_conflict_is_a_safe_business_error(
    client, monkeypatch
) -> None:
    context = _setup(client)
    from app.repositories.workflow_repository import stock_in_item_repository

    def conflict(_item):
        raise IntegrityError(
            "INSERT INTO stock_in_items (...) VALUES (...) ",
            {},
            Exception(
                "UNIQUE constraint failed: stock_in_items.serial_reservation_key"
            ),
        )

    monkeypatch.setattr(stock_in_item_repository, "add", conflict)
    response = client.post(
        "/api/v1/stock-in-requests",
        headers=context["headers"],
        json={
            "organization_id": context["organization"].id,
            "items": [_item(context)],
        },
    )
    body = response.get_json()

    assert response.status_code == 200
    assert body["code"] == 1000
    assert body["message"] == "设备序列号已被其他申请占用"
    assert "UNIQUE" not in body["message"]


def test_rejected_request_releases_serial_reservation(client) -> None:
    context = _setup(client)
    first = client.post(
        "/api/v1/stock-in-requests",
        headers=context["headers"],
        json={
            "organization_id": context["organization"].id,
            "items": [_item(context)],
        },
    ).get_json()["data"]

    stock_in_service.reject(first["id"], "资料不完整", context["approver"].id)

    replacement = client.post(
        "/api/v1/stock-in-requests",
        headers=context["headers"],
        json={
            "organization_id": context["organization"].id,
            "items": [_item(context)],
        },
    ).get_json()
    assert replacement["code"] == 200
    assert replacement["data"]["items"][0]["asset_code"].endswith("-0002")


def test_stock_in_list_is_paginated_filtered_and_newest_first(client) -> None:
    context = _setup(client)
    submitted = []
    for index in range(2):
        response = client.post(
            "/api/v1/stock-in-requests",
            headers=context["headers"],
            json={
                "organization_id": context["organization"].id,
                "items": [_item(context, serial_number=f"LIST-{index}")],
            },
        )
        submitted.append(response.get_json()["data"])

    response = client.get(
        "/api/v1/stock-in-requests",
        headers=context["headers"],
        query_string={"page": 0, "size": 1, "approval_status": "PENDING"},
    )
    body = response.get_json()

    assert body["code"] == 200
    assert body["data"]["total"] == 2
    assert body["data"]["page"] == 0
    assert body["data"]["size"] == 1
    item = body["data"]["items"][0]
    assert item["id"] == submitted[1]["id"]
    assert item["request_no"] == submitted[1]["request_no"]
    assert item["organization_id"] == context["organization"].id
    assert item["applicant_id"] == context["applicant"].id
    assert item["approval_status"] == "PENDING"
    assert item["execution_status"] == "NOT_STARTED"
    assert item["created_at"]

    filtered = client.get(
        "/api/v1/stock-in-requests",
        headers=context["headers"],
        query_string={"request_no": submitted[0]["request_no"]},
    ).get_json()["data"]
    assert filtered["total"] == 1
    assert filtered["items"][0]["id"] == submitted[0]["id"]


def test_stock_in_list_applies_organization_scope_in_query(client) -> None:
    context = _setup(client)
    submitted = client.post(
        "/api/v1/stock-in-requests",
        headers=context["headers"],
        json={
            "organization_id": context["organization"].id,
            "items": [_item(context, serial_number="SCOPED-LIST")],
        },
    ).get_json()["data"]
    other_organization = Organization(code="OTHER", name="其他组织")
    reader = User(
        username="scoped-stock-reader",
        password=hash_password("admin123"),
        enabled=True,
    )
    role = Role(
        code="SCOPED_STOCK_READER",
        name="SCOPED_STOCK_READER",
        data_scope=DataScope.DEPARTMENT.value,
    )
    db.session.add_all([other_organization, reader])
    db.session.add(role)
    db.session.flush()
    reader.organization_id = other_organization.id
    _assign(reader, role)
    view_permission = db.session.query(Permission).filter_by(code="stock-in:view").one()
    db.session.add(RolePermission(role_id=role.id, permission_id=view_permission.id))
    db.session.commit()
    token = client.post(
        "/api/v1/auth/login",
        json={"username": reader.username, "password": "admin123"},
    ).get_json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}

    hidden = client.get("/api/v1/stock-in-requests", headers=headers).get_json()["data"]
    assert hidden["total"] == 0

    reader.organization_id = context["organization"].id
    db.session.commit()
    visible = client.get("/api/v1/stock-in-requests", headers=headers).get_json()[
        "data"
    ]
    assert visible["total"] == 1
    assert visible["items"][0]["id"] == submitted["id"]


def test_stock_in_detail_hides_amount_without_field_permission(client) -> None:
    context = _setup(client)
    submitted = client.post(
        "/api/v1/stock-in-requests",
        headers=context["headers"],
        json={
            "organization_id": context["organization"].id,
            "items": [_item(context)],
        },
    ).get_json()["data"]

    hidden = client.get(
        f"/api/v1/stock-in-requests/{submitted['id']}",
        headers=context["headers"],
    ).get_json()["data"]["items"][0]
    assert "original_amount" not in hidden
    assert "zero_amount_reason" not in hidden

    amount_permission = Permission(
        code="asset:amount:view", name="查看资产金额", module="asset"
    )
    role_id = (
        db.session.query(UserRole)
        .filter_by(user_id=context["applicant"].id)
        .one()
        .role_id
    )
    db.session.add(amount_permission)
    db.session.flush()
    db.session.add(RolePermission(role_id=role_id, permission_id=amount_permission.id))
    db.session.commit()

    visible = client.get(
        f"/api/v1/stock-in-requests/{submitted['id']}",
        headers=context["headers"],
    ).get_json()["data"]["items"][0]
    assert visible["original_amount"] == "7999.00"
    assert visible["zero_amount_reason"] is None


def test_self_scope_consistently_allows_own_list_detail_and_withdraw(client) -> None:
    context = _setup(client)
    submitted = client.post(
        "/api/v1/stock-in-requests",
        headers=context["headers"],
        json={
            "organization_id": context["organization"].id,
            "items": [_item(context)],
        },
    ).get_json()["data"]
    role_id = (
        db.session.query(UserRole)
        .filter_by(user_id=context["applicant"].id)
        .one()
        .role_id
    )
    role = db.session.get(Role, role_id)
    assert role is not None
    role.data_scope = DataScope.SELF.value
    db.session.commit()

    listed = client.get(
        "/api/v1/stock-in-requests", headers=context["headers"]
    ).get_json()["data"]
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == submitted["id"]

    detail = client.get(
        f"/api/v1/stock-in-requests/{submitted['id']}",
        headers=context["headers"],
    ).get_json()
    assert detail["code"] == 200
    assert detail["data"]["id"] == submitted["id"]

    withdrawn = client.post(
        f"/api/v1/stock-in-requests/{submitted['id']}/withdraw",
        headers=context["headers"],
    ).get_json()
    assert withdrawn["code"] == 200
    assert withdrawn["data"]["approval_status"] == "WITHDRAWN"
