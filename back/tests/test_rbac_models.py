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


def test_user_can_have_multiple_roles(app) -> None:
    with app.app_context():
        user = User(username="rbac-user", password="x", enabled=True)
        admin = Role(code="SUPER_ADMIN", name="超级管理员", data_scope="ALL")
        viewer = Role(code="ASSET_VIEWER", name="资产查看", data_scope="SELF")
        db.session.add_all([user, admin, viewer])
        db.session.flush()
        db.session.add_all(
            [
                UserRole(user_id=user.id, role_id=admin.id),
                UserRole(user_id=user.id, role_id=viewer.id),
            ]
        )
        db.session.flush()

        rows = db.session.query(UserRole).filter_by(user_id=user.id).all()
        assert {row.role_id for row in rows} == {admin.id, viewer.id}


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
