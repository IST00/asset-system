from __future__ import annotations

from app.enums import DataScope
from app.extensions import db
from app.models import Permission, Role, RolePermission, User, UserRole
from app.security.passwords import hash_password


MASTER_PERMISSIONS = [
    "unit:view",
    "unit:manage",
    "asset-source:view",
    "asset-source:manage",
    "location:view",
    "location:manage",
    "asset-category:view",
    "asset-category:manage",
]


def _master_admin_headers(client) -> dict[str, str]:
    user = User(
        username="master-admin", password=hash_password("admin123"), enabled=True
    )
    role = Role(
        code="MASTER_ADMIN", name="基础资料管理员", data_scope=DataScope.ALL.value
    )
    permissions = [
        Permission(code=code, name=code, module=code.split(":")[0])
        for code in MASTER_PERMISSIONS
    ]
    db.session.add_all([user, role, *permissions])
    db.session.flush()
    db.session.add(UserRole(user_id=user.id, role_id=role.id))
    db.session.add_all(
        [RolePermission(role_id=role.id, permission_id=item.id) for item in permissions]
    )
    db.session.commit()
    token = client.post(
        "/api/v1/auth/login", json={"username": "master-admin", "password": "admin123"}
    ).get_json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


def test_units_sources_and_categories_have_stable_codes(client) -> None:
    headers = _master_admin_headers(client)
    unit = client.post(
        "/api/v1/units", headers=headers, json={"code": "UNIT", "name": "台"}
    ).get_json()["data"]
    source = client.post(
        "/api/v1/asset-sources",
        headers=headers,
        json={"code": "PURCHASE", "name": "采购"},
    ).get_json()["data"]
    parent = client.post(
        "/api/v1/asset-categories",
        headers=headers,
        json={
            "code": "1",
            "name": "电子设备",
            "service_life_months": 36,
            "default_unit_id": unit["id"],
        },
    ).get_json()["data"]
    child = client.post(
        "/api/v1/asset-categories",
        headers=headers,
        json={
            "code": "00101",
            "name": "笔记本电脑",
            "parent_id": parent["id"],
            "service_life_months": 36,
            "default_unit_id": unit["id"],
        },
    ).get_json()["data"]

    assert unit["code"] == "UNIT"
    assert source["code"] == "PURCHASE"
    assert child["code"] == "00101"
    tree = client.get("/api/v1/asset-categories/tree", headers=headers).get_json()[
        "data"
    ]
    assert tree[0]["children"][0]["default_unit_name"] == "台"


def test_location_sibling_names_are_unique_and_only_selectable_nodes_can_be_used(
    client,
) -> None:
    headers = _master_admin_headers(client)
    office = client.post(
        "/api/v1/locations",
        headers=headers,
        json={"code": "LOC000001", "name": "上海办公室", "is_selectable": False},
    ).get_json()["data"]
    room = client.post(
        "/api/v1/locations",
        headers=headers,
        json={
            "code": "LOC000002",
            "name": "A会议室",
            "parent_id": office["id"],
            "is_selectable": True,
        },
    ).get_json()["data"]

    duplicate = client.post(
        "/api/v1/locations",
        headers=headers,
        json={
            "code": "LOC000003",
            "name": "A会议室",
            "parent_id": office["id"],
            "is_selectable": True,
        },
    )
    assert duplicate.get_json()["code"] == 1000
    assert room["is_selectable"] is True

    tree = client.get("/api/v1/locations/tree", headers=headers).get_json()["data"]
    assert tree[0]["children"][0]["full_path"] == "上海办公室/A会议室"


def test_disabled_unit_cannot_be_selected_for_new_category(client) -> None:
    headers = _master_admin_headers(client)
    unit = client.post(
        "/api/v1/units", headers=headers, json={"code": "OLD", "name": "旧单位"}
    ).get_json()["data"]
    client.post(f"/api/v1/units/{unit['id']}/disable", headers=headers)

    response = client.post(
        "/api/v1/asset-categories",
        headers=headers,
        json={
            "code": "OLD-CATEGORY",
            "name": "旧分类",
            "service_life_months": 12,
            "default_unit_id": unit["id"],
        },
    )
    assert response.get_json()["code"] == 1000
    assert "计量单位" in response.get_json()["message"]


def test_master_data_can_be_updated_without_changing_stable_codes(client) -> None:
    headers = _master_admin_headers(client)
    unit = client.post(
        "/api/v1/units", headers=headers, json={"code": "UPDATE_UNIT", "name": "台"}
    ).get_json()["data"]
    updated_unit = client.post(
        f"/api/v1/units/{unit['id']}/update",
        headers=headers,
        json={"name": "设备台", "version": unit["version"]},
    ).get_json()["data"]
    assert updated_unit["code"] == "UPDATE_UNIT"
    assert updated_unit["name"] == "设备台"

    source = client.post(
        "/api/v1/asset-sources",
        headers=headers,
        json={"code": "UPDATE_SOURCE", "name": "采购"},
    ).get_json()["data"]
    updated_source = client.post(
        f"/api/v1/asset-sources/{source['id']}/update",
        headers=headers,
        json={"name": "集中采购", "version": source["version"]},
    ).get_json()["data"]
    assert updated_source["code"] == "UPDATE_SOURCE"

    root = client.post(
        "/api/v1/locations",
        headers=headers,
        json={"code": "UPDATE_LOC", "name": "办公室", "is_selectable": False},
    ).get_json()["data"]
    updated_location = client.post(
        f"/api/v1/locations/{root['id']}/update",
        headers=headers,
        json={"name": "上海办公室", "is_selectable": True, "version": root["version"]},
    ).get_json()["data"]
    assert updated_location["code"] == "UPDATE_LOC"
    assert updated_location["is_selectable"] is True
    disabled_location = client.post(
        f"/api/v1/locations/{root['id']}/disable", headers=headers
    ).get_json()["data"]
    assert disabled_location["status"] == "DISABLED"
    enabled_location = client.post(
        f"/api/v1/locations/{root['id']}/enable", headers=headers
    ).get_json()["data"]
    assert enabled_location["status"] == "ENABLED"

    category = client.post(
        "/api/v1/asset-categories",
        headers=headers,
        json={
            "code": "UPDATE_CATEGORY",
            "name": "电脑",
            "service_life_months": 36,
            "default_unit_id": unit["id"],
        },
    ).get_json()["data"]
    disabled = client.post(
        f"/api/v1/asset-categories/{category['id']}/disable", headers=headers
    ).get_json()["data"]
    assert disabled["status"] == "DISABLED"
    enabled = client.post(
        f"/api/v1/asset-categories/{category['id']}/enable", headers=headers
    ).get_json()["data"]
    updated_category = client.post(
        f"/api/v1/asset-categories/{category['id']}/update",
        headers=headers,
        json={
            "name": "笔记本电脑",
            "service_life_months": 48,
            "default_unit_id": unit["id"],
            "version": enabled["version"],
        },
    ).get_json()["data"]
    assert updated_category["service_life_months"] == 48

    immutable = client.post(
        f"/api/v1/asset-categories/{category['id']}/update",
        headers=headers,
        json={
            "code": "CHANGED",
            "name": "电脑",
            "service_life_months": 48,
            "default_unit_id": unit["id"],
            "version": updated_category["version"],
        },
    )
    assert immutable.status_code == 400
