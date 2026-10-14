from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    Permission,
    Organization,
    Role,
    RoleDataScopeOrganization,
    RolePermission,
    User,
    UserRole,
)


def test_user_role_is_a_single_authorization_row(app) -> None:
    with app.app_context():
        user = User(username="rbac-user", password="x", enabled=True)
        admin = Role(code="SUPER_ADMIN", name="超级管理员", data_scope="ALL")
        db.session.add_all([user, admin])
        db.session.flush()
        db.session.add(UserRole(user_id=user.id, role_id=admin.id))
        db.session.flush()

        rows = db.session.query(UserRole).filter_by(user_id=user.id).all()
        assert [row.role_id for row in rows] == [admin.id]


def test_role_permission_and_custom_scope_are_explicit_rows(app) -> None:
    with app.app_context():
        role = Role(code="CUSTOM_MANAGER", name="自定义管理员", data_scope="CUSTOM")
        permission = Permission(code="asset:view", name="查看资产", module="asset")
        organization = Organization(code="001", name="测试公司")
        db.session.add_all([role, permission, organization])
        db.session.flush()
        db.session.add(RolePermission(role_id=role.id, permission_id=permission.id))
        db.session.add(
            RoleDataScopeOrganization(role_id=role.id, organization_id=organization.id)
        )
        db.session.flush()

        assert (
            db.session.query(RolePermission)
            .filter_by(role_id=role.id)
            .one()
            .permission_id
            == permission.id
        )
        assert (
            db.session.query(RoleDataScopeOrganization)
            .filter_by(role_id=role.id)
            .one()
            .organization_id
            == organization.id
        )


def test_role_code_is_unique(app) -> None:
    with app.app_context():
        db.session.add_all(
            [
                Role(code="UNIQUE_ROLE", name="角色一", data_scope="SELF"),
                Role(code="UNIQUE_ROLE", name="角色二", data_scope="SELF"),
            ]
        )
        with pytest.raises(IntegrityError):
            db.session.flush()


def test_builtin_role_permissions_are_hierarchical(app) -> None:
    with app.app_context():
        employee = Role(code="USER", name="普通员工", data_scope="SELF")
        administrator = Role(code="ASSET_ADMIN", name="资产管理员", data_scope="ALL")
        super_admin = Role(code="SUPER_ADMIN", name="超级管理员", data_scope="ALL")
        employee_permission = Permission(
            code="asset:view", name="查看资产", module="asset"
        )
        admin_permission = Permission(
            code="inventory:manage", name="管理盘点", module="inventory"
        )
        db.session.add_all(
            [
                employee,
                administrator,
                super_admin,
                employee_permission,
                admin_permission,
            ]
        )
        db.session.flush()
        db.session.add(
            RolePermission(role_id=employee.id, permission_id=employee_permission.id)
        )
        db.session.add(
            RolePermission(role_id=administrator.id, permission_id=admin_permission.id)
        )
        db.session.flush()

        from app.services import rbac_service

        rbac_service._synchronize_builtin_role_hierarchy()

        employee_ids = {
            item.id
            for item in db.session.query(Permission)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .filter(RolePermission.role_id == employee.id)
            .all()
        }
        administrator_ids = {
            item.id
            for item in db.session.query(Permission)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .filter(RolePermission.role_id == administrator.id)
            .all()
        }
        super_admin_ids = {
            item.id
            for item in db.session.query(Permission)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .filter(RolePermission.role_id == super_admin.id)
            .all()
        }

        assert employee_ids <= administrator_ids
        assert administrator_ids <= super_admin_ids
