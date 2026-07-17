from __future__ import annotations

from app.enums import DataScope
from app.extensions import db
from app.models import Organization, Permission, Role, RolePermission, User, UserRole
from app.security.passwords import hash_password


def _authorized_client(client):
    actor = User(
        username="rbac-admin", password=hash_password("admin123"), enabled=True
    )
    role = Role(code="RBAC_ADMIN", name="权限管理员", data_scope=DataScope.ALL.value)
    permissions = [
        Permission(code="system:role:view", name="查看角色", module="system"),
        Permission(code="system:role:manage", name="管理角色", module="system"),
        Permission(code="system:user:view", name="查看用户", module="system"),
    ]
    db.session.add_all([actor, role, *permissions])
    db.session.flush()
    db.session.add(UserRole(user_id=actor.id, role_id=role.id))
    db.session.add_all(
        [RolePermission(role_id=role.id, permission_id=item.id) for item in permissions]
    )
    db.session.flush()
    response = client.post(
        "/api/v1/auth/login", json={"username": "rbac-admin", "password": "admin123"}
    )
    return {"Authorization": f"Bearer {response.get_json()['data']['token']}"}


def test_role_permissions_and_user_roles_can_be_managed(client) -> None:
    headers = _authorized_client(client)
    target = User(username="role-target", password="x", enabled=True)
    asset_view = Permission(code="asset:view", name="查看资产", module="asset")
    db.session.add_all([target, asset_view])
    db.session.flush()

    created = client.post(
        "/api/v1/roles",
        headers=headers,
        json={"code": "ASSET_VIEWER", "name": "资产查看", "data_scope": "SELF"},
    )
    assert created.status_code == 200
    role_id = created.get_json()["data"]["id"]

    assigned_permissions = client.post(
        f"/api/v1/roles/{role_id}/permissions/update",
        headers=headers,
        json={"permission_ids": [asset_view.id]},
    )
    assert assigned_permissions.get_json()["data"]["permissions"] == ["asset:view"]

    assigned_roles = client.post(
        f"/api/v1/users/{target.id}/roles/update",
        headers=headers,
        json={"role_ids": [role_id]},
    )
    assert assigned_roles.get_json()["data"]["roles"] == ["ASSET_VIEWER"]

    permission_list = client.get("/api/v1/permissions", headers=headers)
    assert {item["code"] for item in permission_list.get_json()["data"]} >= {
        "asset:view",
        "system:role:manage",
    }


def test_role_management_requires_permission(client) -> None:
    user = User(username="plain-user", password=hash_password("admin123"), enabled=True)
    db.session.add(user)
    db.session.flush()
    token = client.post(
        "/api/v1/auth/login", json={"username": "plain-user", "password": "admin123"}
    ).get_json()["data"]["token"]

    response = client.post(
        "/api/v1/roles",
        headers={"Authorization": f"Bearer {token}"},
        json={"code": "DENIED", "name": "无权限", "data_scope": "SELF"},
    )
    assert response.get_json()["code"] == 403


def test_role_can_update_name_scope_and_custom_organizations(client) -> None:
    headers = _authorized_client(client)
    organization = Organization(code="RBAC-CUSTOM", name="自定义组织")
    db.session.add(organization)
    db.session.commit()
    created = client.post(
        "/api/v1/roles",
        headers=headers,
        json={"code": "CUSTOM_ROLE", "name": "旧名称", "data_scope": "SELF"},
    ).get_json()["data"]

    updated = client.post(
        f"/api/v1/roles/{created['id']}/update",
        headers=headers,
        json={
            "name": "自定义组织管理员",
            "data_scope": "CUSTOM",
            "enabled": True,
            "organization_ids": [organization.id],
            "version": created["version"],
        },
    ).get_json()["data"]
    assert updated["code"] == "CUSTOM_ROLE"
    assert updated["data_scope"] == "CUSTOM"
    assert updated["organization_ids"] == [organization.id]

    immutable = client.post(
        f"/api/v1/roles/{created['id']}/update",
        headers=headers,
        json={
            "code": "CHANGED",
            "name": "非法修改",
            "data_scope": "SELF",
            "enabled": True,
            "organization_ids": [],
            "version": updated["version"],
        },
    )
    assert immutable.status_code == 400
