from __future__ import annotations

import pytest

from app.common import BusinessException
from app.enums import DataScope
from app.extensions import db
from app.models import (
    Organization,
    Permission,
    Role,
    RoleDataScopeOrganization,
    RolePermission,
    User,
    UserRole,
)
from app.services import permission_service


def _grant(role: Role, *permissions: Permission) -> None:
    db.session.flush()
    db.session.add_all(
        [
            RolePermission(role_id=role.id, permission_id=permission.id)
            for permission in permissions
        ]
    )


def _assign(user: User, *roles: Role) -> None:
    db.session.flush()
    db.session.add_all([UserRole(user_id=user.id, role_id=role.id) for role in roles])


def test_permissions_and_scopes_are_unioned_across_roles(app) -> None:
    with app.app_context():
        root = Organization(code="ORG-ROOT", name="集团")
        child = Organization(code="ORG-CHILD", name="事业部", parent_id=None)
        custom_org = Organization(code="ORG-CUSTOM", name="自定义组织")
        user = User(username="scope-user", password="x", enabled=True)
        tree_role = Role(
            code="TREE_MANAGER",
            name="组织树管理员",
            data_scope=DataScope.DEPARTMENT_TREE.value,
        )
        custom_role = Role(
            code="CUSTOM_VIEWER", name="自定义查看", data_scope=DataScope.CUSTOM.value
        )
        view = Permission(code="asset:view", name="查看资产", module="asset")
        create = Permission(code="stock-in:create", name="创建入库", module="stock-in")
        db.session.add_all(
            [root, child, custom_org, user, tree_role, custom_role, view, create]
        )
        db.session.flush()
        child.parent_id = root.id
        user.organization_id = child.id
        _grant(tree_role, view)
        _grant(custom_role, create)
        _assign(user, tree_role, custom_role)
        db.session.add(
            RoleDataScopeOrganization(
                role_id=custom_role.id, organization_id=custom_org.id
            )
        )
        db.session.flush()

        assert permission_service.get_user_permissions(user.id) == {
            "asset:view",
            "stock-in:create",
        }
        assert permission_service.accessible_organization_ids(user.id) == {
            child.id,
            custom_org.id,
        }


def test_all_scope_overrides_other_scopes(app) -> None:
    with app.app_context():
        user = User(username="all-user", password="x", enabled=True)
        role = Role(
            code="ALL_MANAGER", name="全量管理员", data_scope=DataScope.ALL.value
        )
        permission = Permission(code="asset:view", name="查看资产", module="asset")
        db.session.add_all([user, role, permission])
        db.session.flush()
        _grant(role, permission)
        _assign(user, role)
        db.session.flush()

        assert permission_service.accessible_organization_ids(user.id) is None
        permission_service.require_organization_scope(user.id, 999999)


def test_disabled_role_does_not_grant_permission(app) -> None:
    with app.app_context():
        user = User(username="disabled-role-user", password="x", enabled=True)
        role = Role(
            code="DISABLED_ROLE",
            name="停用角色",
            data_scope=DataScope.ALL.value,
            enabled=False,
        )
        permission = Permission(code="asset:view", name="查看资产", module="asset")
        db.session.add_all([user, role, permission])
        db.session.flush()
        _grant(role, permission)
        _assign(user, role)
        db.session.flush()

        assert permission_service.has_permission(user.id, "asset:view") is False
        with pytest.raises(BusinessException):
            permission_service.require_permission(user.id, "asset:view")


def test_find_approval_candidates_requires_permission_and_scope(app) -> None:
    with app.app_context():
        organization = Organization(code="APPROVAL-ORG", name="审批公司")
        allowed = User(username="allowed-approver", password="x", enabled=True)
        denied = User(username="denied-approver", password="x", enabled=True)
        disabled = User(username="disabled-approver", password="x", enabled=False)
        role = Role(
            code="STOCK_APPROVER", name="入库审批", data_scope=DataScope.CUSTOM.value
        )
        permission = Permission(
            code="stock-in:approve", name="入库审批", module="stock-in"
        )
        db.session.add_all([organization, allowed, denied, disabled, role, permission])
        db.session.flush()
        _grant(role, permission)
        _assign(allowed, role)
        _assign(disabled, role)
        db.session.add(
            RoleDataScopeOrganization(role_id=role.id, organization_id=organization.id)
        )
        db.session.flush()

        assert permission_service.find_approval_candidates(
            "stock-in:approve", organization.id
        ) == [allowed.id]
        assert denied.id not in permission_service.find_approval_candidates(
            "stock-in:approve", organization.id
        )
