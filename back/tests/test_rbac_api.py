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


def test_custom_role_delete_has_impact_confirmation_and_audit(client) -> None:
    from app.models import OperationLog

    headers = _authorized_client(client)
    created = client.post(
        "/api/v1/roles",
        headers=headers,
        json={
            "code": "TEMP_ROLE",
            "name": "临时角色",
            "data_scope": "SELF",
            "reason": "测试",
        },
    ).get_json()["data"]
    impact = client.get(
        f"/api/v1/roles/{created['id']}/delete-impact", headers=headers
    ).get_json()["data"]
    assert impact["can_delete"] is True

    invalid = client.post(
        f"/api/v1/roles/{created['id']}/delete",
        headers=headers,
        json={
            "version": created["version"],
            "reason": "删除临时角色",
            "confirmed": False,
        },
    )
    assert invalid.status_code == 400

    deleted = client.post(
        f"/api/v1/roles/{created['id']}/delete",
        headers=headers,
        json={
            "version": created["version"],
            "reason": "删除临时角色",
            "confirmed": True,
        },
    ).get_json()["data"]
    assert deleted["deleted"] is True
    audit = db.session.query(OperationLog).filter_by(action="ROLE_DELETE").one()
    assert audit.reason == "删除临时角色"
    assert audit.before_data is not None
    assert audit.before_data["code"] == "TEMP_ROLE"


def test_role_delete_is_blocked_for_built_in_user_and_approval_references(
    client,
) -> None:
    from app.enums import AssigneeType
    from app.models import (
        ApprovalFlowAssigneeRule,
        ApprovalFlowDefinition,
        ApprovalFlowLayer,
        ApprovalFlowVersion,
    )

    headers = _authorized_client(client)
    built_in = Role(
        code="BUILT_IN_TEST",
        name="内置测试",
        data_scope=DataScope.ALL.value,
        built_in=True,
    )
    assigned = Role(code="ASSIGNED_TEST", name="已授权", data_scope=DataScope.ALL.value)
    approval = Role(
        code="APPROVAL_TEST", name="审批角色", data_scope=DataScope.ALL.value
    )
    target = User(username="role-delete-target", password="x", enabled=True)
    db.session.add_all([built_in, assigned, approval, target])
    db.session.flush()
    db.session.add(UserRole(user_id=target.id, role_id=assigned.id))
    definition = ApprovalFlowDefinition(
        operation_type="DELETE_ROLE_TEST", name="删除角色测试"
    )
    db.session.add(definition)
    db.session.flush()
    version = ApprovalFlowVersion(flow_definition_id=definition.id, version_no=1)
    db.session.add(version)
    db.session.flush()
    layer = ApprovalFlowLayer(flow_version_id=version.id, level_no=1, sign_mode="ANY")
    db.session.add(layer)
    db.session.flush()
    db.session.add(
        ApprovalFlowAssigneeRule(
            layer_id=layer.id,
            assignee_type=AssigneeType.ROLE.value,
            assignee_id=approval.id,
        )
    )
    db.session.commit()

    built_in_impact = client.get(
        f"/api/v1/roles/{built_in.id}/delete-impact", headers=headers
    ).get_json()["data"]
    assigned_impact = client.get(
        f"/api/v1/roles/{assigned.id}/delete-impact", headers=headers
    ).get_json()["data"]
    approval_impact = client.get(
        f"/api/v1/roles/{approval.id}/delete-impact", headers=headers
    ).get_json()["data"]
    assert built_in_impact["can_delete"] is False
    assert assigned_impact["can_delete"] is False
    assert approval_impact["can_delete"] is False
    assert "内置角色" in built_in_impact["blockers"][0]
    assert "用户" in assigned_impact["blockers"][0]
    assert "审批规则" in approval_impact["blockers"][0]
