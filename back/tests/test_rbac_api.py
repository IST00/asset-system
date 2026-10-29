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


def test_user_roles_reject_multiple_roles_and_preserve_hierarchy(client) -> None:
    from app.models import RolePermission

    headers = _authorized_client(client)
    target = User(username="single-role-target", password="x", enabled=True)
    asset_view = Permission(code="asset:view", name="查看资产", module="asset")
    asset_manage = Permission(code="asset:manage", name="管理资产", module="asset")
    employee = Role(code="USER", name="普通员工", data_scope="SELF")
    administrator = Role(
        code="ASSET_ADMIN", name="资产管理员", data_scope=DataScope.ALL.value
    )
    super_admin = Role(
        code="SUPER_ADMIN", name="超级管理员", data_scope=DataScope.ALL.value
    )
    db.session.add_all(
        [target, asset_view, asset_manage, employee, administrator, super_admin]
    )
    db.session.flush()
    db.session.add(RolePermission(role_id=employee.id, permission_id=asset_view.id))
    db.session.add(
        RolePermission(role_id=administrator.id, permission_id=asset_manage.id)
    )
    db.session.commit()

    invalid = client.post(
        f"/api/v1/users/{target.id}/roles/update",
        headers=headers,
        json={"role_ids": [employee.id, administrator.id], "reason": "测试多角色"},
    )
    assert invalid.status_code == 200
    assert invalid.get_json()["code"] == 400
    assert "每个账号只能分配一个角色" in invalid.get_json()["message"]

    assigned = client.post(
        f"/api/v1/users/{target.id}/roles/update",
        headers=headers,
        json={"role_ids": [administrator.id], "reason": "测试单角色"},
    )
    assert assigned.status_code == 200
    assert assigned.get_json()["data"]["roles"] == ["ASSET_ADMIN"]

    blocked_permissions = client.post(
        f"/api/v1/roles/{administrator.id}/permissions/update",
        headers=headers,
        json={"permission_ids": [asset_manage.id], "reason": "测试角色层级"},
    )
    assert blocked_permissions.get_json()["code"] == 400
    assert "普通员工" in blocked_permissions.get_json()["message"]

    assigned_permissions = client.post(
        f"/api/v1/roles/{administrator.id}/permissions/update",
        headers=headers,
        json={
            "permission_ids": [asset_view.id, asset_manage.id],
            "reason": "测试角色层级",
        },
    )
    assert assigned_permissions.get_json()["data"]["code"] == "ASSET_ADMIN"

    def permission_codes(role_id: int) -> set[str]:
        rows = (
            db.session.query(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .filter(RolePermission.role_id == role_id)
            .all()
        )
        return {row[0] for row in rows}

    assert permission_codes(employee.id) <= permission_codes(administrator.id)
    assert permission_codes(administrator.id) <= permission_codes(super_admin.id)


def test_asset_admin_can_promote_employee_but_not_super_admin(client) -> None:
    actor = User(
        username="asset-admin-actor", password=hash_password("admin123"), enabled=True
    )
    target = User(username="promotion-target", password="x", enabled=True)
    super_admin_user = User(username="existing-super-admin", password="x", enabled=True)
    employee = Role(code="USER", name="普通员工", data_scope="SELF")
    administrator = Role(
        code="ASSET_ADMIN", name="资产管理员", data_scope=DataScope.ALL.value
    )
    super_admin = Role(
        code="SUPER_ADMIN", name="超级管理员", data_scope=DataScope.ALL.value
    )
    permissions = [
        Permission(code="system:role:view", name="查看角色", module="system"),
        Permission(code="system:role:manage", name="管理角色", module="system"),
        Permission(code="system:user:view", name="查看用户", module="system"),
    ]
    db.session.add_all(
        [
            actor,
            target,
            super_admin_user,
            employee,
            administrator,
            super_admin,
            *permissions,
        ]
    )
    db.session.flush()
    db.session.add(UserRole(user_id=actor.id, role_id=administrator.id))
    db.session.add(UserRole(user_id=target.id, role_id=employee.id))
    db.session.add(UserRole(user_id=super_admin_user.id, role_id=super_admin.id))
    db.session.add_all(
        [
            RolePermission(role_id=administrator.id, permission_id=item.id)
            for item in permissions
        ]
    )
    db.session.commit()
    token = client.post(
        "/api/v1/auth/login",
        json={"username": "asset-admin-actor", "password": "admin123"},
    ).get_json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}

    listed_users = client.get("/api/v1/users", headers=headers)
    assert listed_users.get_json()["code"] == 200
    listed_super_admin = next(
        item
        for item in listed_users.get_json()["data"]["items"]
        if item["id"] == super_admin_user.id
    )
    assert listed_super_admin["roles"] == ["SUPER_ADMIN"]

    denied = client.post(
        f"/api/v1/users/{target.id}/roles/update",
        headers=headers,
        json={"role_ids": [super_admin.id], "reason": "越权提升"},
    )
    assert denied.get_json()["code"] == 403
    assert "只有超级管理员可以授权超级管理员" in denied.get_json()["message"]

    denied_super_admin_user_update = client.post(
        f"/api/v1/users/{super_admin_user.id}/roles/update",
        headers=headers,
        json={"role_ids": [administrator.id], "reason": "越权降级超级管理员"},
    )
    assert denied_super_admin_user_update.get_json()["code"] == 403
    assert (
        "只有超级管理员可以修改超级管理员账号角色"
        in denied_super_admin_user_update.get_json()["message"]
    )

    denied_basic_update = client.post(
        f"/api/v1/roles/{super_admin.id}/update",
        headers=headers,
        json={
            "name": "越权修改超级管理员",
            "data_scope": DataScope.ALL.value,
            "enabled": True,
            "version": super_admin.version,
            "reason": "越权修改角色配置",
        },
    )
    assert denied_basic_update.get_json()["code"] == 403
    assert (
        "只有超级管理员可以修改超级管理员角色配置"
        in denied_basic_update.get_json()["message"]
    )

    denied_permission_update = client.post(
        f"/api/v1/roles/{super_admin.id}/permissions/update",
        headers=headers,
        json={"permission_ids": [], "reason": "越权修改权限点"},
    )
    assert denied_permission_update.get_json()["code"] == 403
    assert (
        "只有超级管理员可以修改超级管理员角色配置"
        in denied_permission_update.get_json()["message"]
    )

    allowed = client.post(
        f"/api/v1/users/{target.id}/roles/update",
        headers=headers,
        json={"role_ids": [administrator.id], "reason": "提升资产管理员"},
    )
    assert allowed.get_json()["data"]["roles"] == ["ASSET_ADMIN"]


def test_users_page_can_display_disabled_users(client) -> None:
    headers = _authorized_client(client)
    disabled = User(username="disabled-list-user", password="x", enabled=False)
    db.session.add(disabled)
    db.session.commit()

    response = client.get("/api/v1/users?page=0&size=100", headers=headers)

    assert response.status_code == 200
    assert response.get_json()["code"] == 200
    listed = next(
        item
        for item in response.get_json()["data"]["items"]
        if item["id"] == disabled.id
    )
    assert listed["enabled"] is False


def test_users_page_searches_username_and_nickname_on_server(client) -> None:
    headers = _authorized_client(client)
    root = Organization(code="REMOTE-ORG-ROOT", name="远端集团")
    db.session.add(root)
    db.session.flush()
    department = Organization(code="REMOTE-ORG-DEPT", name="技术部", parent_id=root.id)
    db.session.add(department)
    db.session.flush()
    target = User(
        username="remote-target-user",
        password="x",
        nickname="远端搜索员工",
        enabled=True,
        organization_id=department.id,
    )
    other = User(username="remote-other-user", password="x", nickname="其他员工")
    db.session.add_all([target, other])
    db.session.flush()
    target.organization_id = department.id
    db.session.commit()

    by_nickname = client.get(
        "/api/v1/users?page=0&size=20&keyword=远端搜索",
        headers=headers,
    )
    by_username = client.get(
        "/api/v1/users?page=0&size=20&keyword=remote-target",
        headers=headers,
    )

    assert by_nickname.status_code == 200
    assert [item["id"] for item in by_nickname.get_json()["data"]["items"]] == [
        target.id
    ]
    assert by_username.status_code == 200
    assert [item["id"] for item in by_username.get_json()["data"]["items"]] == [
        target.id
    ]
    assert by_username.get_json()["data"]["items"][0]["organization_path"] == (
        "远端集团/技术部"
    )


def test_users_page_orders_builtin_roles_before_users(client) -> None:
    headers = _authorized_client(client)
    plain = User(
        username="plain-employee", password="x", nickname="普通员工", enabled=True
    )
    asset_admin = User(
        username="asset-admin-user", password="x", nickname="资产管理员", enabled=True
    )
    super_admin = User(
        username="super-admin-user", password="x", nickname="超级管理员", enabled=True
    )
    employee_role = Role(code="USER", name="普通员工", data_scope=DataScope.SELF.value)
    administrator_role = Role(
        code="ASSET_ADMIN", name="资产管理员", data_scope=DataScope.ALL.value
    )
    super_role = Role(
        code="SUPER_ADMIN", name="超级管理员", data_scope=DataScope.ALL.value
    )
    db.session.add_all(
        [plain, asset_admin, super_admin, employee_role, administrator_role, super_role]
    )
    db.session.flush()
    db.session.add(UserRole(user_id=plain.id, role_id=employee_role.id))
    db.session.add(UserRole(user_id=asset_admin.id, role_id=administrator_role.id))
    db.session.add(UserRole(user_id=super_admin.id, role_id=super_role.id))
    db.session.commit()

    response = client.get("/api/v1/users?page=0&size=3", headers=headers)

    assert response.status_code == 200
    items = response.get_json()["data"]["items"]
    assert [item["roles"] for item in items] == [
        ["SUPER_ADMIN"],
        ["ASSET_ADMIN"],
        ["USER"],
    ]
