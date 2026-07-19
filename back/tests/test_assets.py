from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.enums import AssetStatus, DataScope
from app.extensions import db
from app.models import (
    Asset,
    AssetCategory,
    AssetLifecycleRecord,
    AssetLocation,
    AssetSource,
    OperationLog,
    Organization,
    Permission,
    Role,
    RolePermission,
    Unit,
    User,
    UserRole,
)
from app.security.passwords import hash_password


def _reader(
    client, username: str, scope: str, permission_codes: list[str], organization=None
):
    user = User(
        username=username,
        password=hash_password("admin123"),
        enabled=True,
        organization_id=organization.id if organization else None,
    )
    role = Role(code=f"{username.upper()}_ROLE", name=username, data_scope=scope)
    permissions = []
    for code in permission_codes:
        permission = db.session.query(Permission).filter_by(code=code).one_or_none()
        if permission is None:
            permission = Permission(code=code, name=code, module=code.split(":")[0])
            db.session.add(permission)
        permissions.append(permission)
    db.session.add_all([user, role])
    db.session.flush()
    db.session.add(UserRole(user_id=user.id, role_id=role.id))
    db.session.add_all(
        [RolePermission(role_id=role.id, permission_id=item.id) for item in permissions]
    )
    db.session.commit()
    token = client.post(
        "/api/v1/auth/login", json={"username": username, "password": "admin123"}
    ).get_json()["data"]["token"]
    return user, {"Authorization": f"Bearer {token}"}


def _asset_fixture():
    organization = Organization(code="ASSET-ORG", name="资产公司")
    other_organization = Organization(code="OTHER-ORG", name="其他公司")
    unit = Unit(code="ASSET-UNIT", name="台")
    source = AssetSource(code="ASSET-SOURCE", name="采购")
    location = AssetLocation(code="ASSET-LOC", name="仓库", is_selectable=True)
    manager = User(username="asset-owner", password="x", enabled=True)
    db.session.add_all(
        [organization, other_organization, unit, source, location, manager]
    )
    db.session.flush()
    manager.organization_id = organization.id
    category = AssetCategory(
        code="ASSET-CATEGORY",
        name="电脑",
        service_life_months=36,
        default_unit_id=unit.id,
    )
    db.session.add(category)
    db.session.flush()
    asset = Asset(
        asset_code="ASSET-ORG-ASSET-CATEGORY-0001",
        asset_name="MacBook Air",
        status=AssetStatus.IDLE.value,
        organization_id=organization.id,
        category_id=category.id,
        unit_id=unit.id,
        original_amount=Decimal("8999.00"),
        purchase_date=date(2026, 7, 17),
        manager_id=manager.id,
        source_id=source.id,
        location_id=location.id,
        normalized_serial="asset-sn",
        serial_number="ASSET-SN",
    )
    db.session.add(asset)
    db.session.flush()
    db.session.add_all(
        [
            AssetLifecycleRecord(
                asset_id=asset.id,
                operation_type="STOCK_IN",
                operation_no="STI-ASSET",
                operator_id=manager.id,
                before_data=None,
                after_data={"status": "IDLE"},
            ),
            OperationLog(
                action="STOCK_IN",
                resource_type="asset",
                resource_id=str(asset.id),
                operator_id=manager.id,
                before_data=None,
                after_data={"asset_code": asset.asset_code},
            ),
        ]
    )
    db.session.commit()
    return organization, other_organization, manager, asset


def test_asset_list_applies_scope_and_amount_field_permission(client) -> None:
    organization, _other, manager, asset = _asset_fixture()
    all_user, all_headers = _reader(
        client,
        "all-reader",
        DataScope.ALL.value,
        ["asset:view", "asset:amount:view"],
    )
    self_user, self_headers = _reader(
        client,
        "self-reader",
        DataScope.SELF.value,
        ["asset:view"],
        organization,
    )
    asset.manager_id = self_user.id
    db.session.commit()

    all_result = client.get("/api/v1/assets", headers=all_headers).get_json()["data"]
    assert all_result["total"] == 1
    assert all_result["items"][0]["original_amount"] == "8999.00"

    self_result = client.get("/api/v1/assets", headers=self_headers).get_json()["data"]
    assert self_result["total"] == 1
    assert "original_amount" not in self_result["items"][0]
    assert self_result["items"][0]["asset_code"] == asset.asset_code


def test_asset_detail_lifecycle_and_audit_require_permissions(client) -> None:
    _organization, _other, _manager, asset = _asset_fixture()
    _user, headers = _reader(
        client,
        "audit-reader",
        DataScope.ALL.value,
        ["asset:view", "audit:view"],
    )

    detail = client.get(f"/api/v1/assets/{asset.id}", headers=headers).get_json()[
        "data"
    ]
    assert detail["asset_name"] == "MacBook Air"
    lifecycle = client.get(
        f"/api/v1/assets/{asset.id}/lifecycle", headers=headers
    ).get_json()["data"]
    assert lifecycle[0]["operation_no"] == "STI-ASSET"
    audit = client.get("/api/v1/audit-logs", headers=headers).get_json()["data"]
    assert audit[0]["action"] == "STOCK_IN"


def test_asset_list_filters_by_name_and_normalized_serial(client) -> None:
    _organization, _other, _manager, asset = _asset_fixture()
    _user, headers = _reader(
        client,
        "filter-reader",
        DataScope.ALL.value,
        ["asset:view"],
    )

    by_name = client.get(
        "/api/v1/assets",
        headers=headers,
        query_string={"asset_name": "MacBook"},
    ).get_json()["data"]
    assert by_name["total"] == 1
    assert by_name["items"][0]["id"] == asset.id

    by_serial = client.get(
        "/api/v1/assets",
        headers=headers,
        query_string={"serial_number": " asset-SN "},
    ).get_json()["data"]
    assert by_serial["total"] == 1
    assert by_serial["items"][0]["id"] == asset.id

    missing = client.get(
        "/api/v1/assets",
        headers=headers,
        query_string={"asset_name": "不存在"},
    ).get_json()["data"]
    assert missing["total"] == 0
