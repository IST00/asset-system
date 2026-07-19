from __future__ import annotations

from app.enums import DataScope
from app.extensions import db
from app.models import Permission, Role, RolePermission, User, UserRole
from app.security.passwords import hash_password


def _organization_admin_headers(client) -> dict[str, str]:
    user = User(username="org-admin", password=hash_password("admin123"), enabled=True)
    role = Role(code="ORG_ADMIN", name="组织管理员", data_scope=DataScope.ALL.value)
    permissions = [
        Permission(code="organization:view", name="查看组织", module="organization"),
        Permission(code="organization:manage", name="管理组织", module="organization"),
    ]
    db.session.add_all([user, role, *permissions])
    db.session.flush()
    db.session.add(UserRole(user_id=user.id, role_id=role.id))
    db.session.add_all(
        [RolePermission(role_id=role.id, permission_id=item.id) for item in permissions]
    )
    db.session.flush()
    token = client.post(
        "/api/v1/auth/login", json={"username": "org-admin", "password": "admin123"}
    ).get_json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


def test_organization_tree_preserves_codes_and_resolves_top_level(client) -> None:
    headers = _organization_admin_headers(client)
    root = client.post(
        "/api/v1/organizations",
        headers=headers,
        json={"code": "001", "name": "集团"},
    ).get_json()["data"]
    child = client.post(
        "/api/v1/organizations",
        headers=headers,
        json={"code": "00101", "name": "事业部", "parent_id": root["id"]},
    ).get_json()["data"]

    tree = client.get("/api/v1/organizations/tree", headers=headers).get_json()["data"]
    assert tree[0]["code"] == "001"
    assert tree[0]["children"][0]["code"] == "00101"

    detail = client.get(
        f"/api/v1/organizations/{child['id']}", headers=headers
    ).get_json()["data"]
    assert detail["top_level_id"] == root["id"]
    assert detail["top_level_code"] == "001"


def test_organization_code_is_immutable_and_parent_cycle_is_rejected(client) -> None:
    headers = _organization_admin_headers(client)
    root = client.post(
        "/api/v1/organizations", headers=headers, json={"code": "A", "name": "根"}
    ).get_json()["data"]
    child = client.post(
        "/api/v1/organizations",
        headers=headers,
        json={"code": "B", "name": "子", "parent_id": root["id"]},
    ).get_json()["data"]

    immutable = client.post(
        f"/api/v1/organizations/{root['id']}/update",
        headers=headers,
        json={"code": "CHANGED", "name": "根"},
    )
    assert immutable.status_code == 400

    cycle = client.post(
        f"/api/v1/organizations/{root['id']}/update",
        headers=headers,
        json={"name": "根", "parent_id": child["id"], "version": root["version"]},
    )
    assert cycle.get_json()["code"] == 1000
    assert "下级" in cycle.get_json()["message"]


def test_organization_version_and_status_actions(client) -> None:
    headers = _organization_admin_headers(client)
    organization = client.post(
        "/api/v1/organizations",
        headers=headers,
        json={"code": "STATUS", "name": "状态公司"},
    ).get_json()["data"]

    disabled = client.post(
        f"/api/v1/organizations/{organization['id']}/disable", headers=headers
    ).get_json()["data"]
    assert disabled["status"] == "DISABLED"

    stale = client.post(
        f"/api/v1/organizations/{organization['id']}/update",
        headers=headers,
        json={"name": "新名称", "version": organization["version"]},
    )
    assert stale.get_json()["code"] == 1000

    enabled = client.post(
        f"/api/v1/organizations/{organization['id']}/enable", headers=headers
    ).get_json()["data"]
    assert enabled["status"] == "ENABLED"
