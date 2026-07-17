"""Queries for role-based access control."""

from __future__ import annotations

from sqlalchemy import delete, select

from app.extensions import db
from app.models import (
    Permission,
    Role,
    RoleDataScopeOrganization,
    RolePermission,
    User,
    UserRole,
)


class RbacRepository:
    def find_user(self, user_id: int) -> User | None:
        return db.session.get(User, user_id)

    def permission_codes_for_user(self, user_id: int) -> set[str]:
        stmt = (
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(Role, Role.id == RolePermission.role_id)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(
                UserRole.user_id == user_id,
                Role.enabled.is_(True),
                Permission.enabled.is_(True),
            )
            .distinct()
        )
        return set(db.session.scalars(stmt).all())

    def role_codes_for_user(self, user_id: int) -> list[str]:
        stmt = (
            select(Role.code)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id, Role.enabled.is_(True))
            .order_by(Role.code.asc())
        )
        return list(db.session.scalars(stmt).all())

    def data_scopes_for_user(self, user_id: int) -> list[tuple[int, str]]:
        stmt = (
            select(Role.id, Role.data_scope)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id, Role.enabled.is_(True))
        )
        return list(db.session.execute(stmt).tuples().all())

    def custom_organization_ids(self, role_ids: list[int]) -> set[int]:
        if not role_ids:
            return set()
        stmt = select(RoleDataScopeOrganization.organization_id).where(
            RoleDataScopeOrganization.role_id.in_(role_ids)
        )
        return set(db.session.scalars(stmt).all())

    def custom_organization_ids_for_role(self, role_id: int) -> list[int]:
        stmt = (
            select(RoleDataScopeOrganization.organization_id)
            .where(RoleDataScopeOrganization.role_id == role_id)
            .order_by(RoleDataScopeOrganization.organization_id.asc())
        )
        return list(db.session.scalars(stmt).all())

    def enabled_user_ids_with_permission(self, permission_code: str) -> list[int]:
        stmt = (
            select(User.id)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .join(RolePermission, RolePermission.role_id == Role.id)
            .join(Permission, Permission.id == RolePermission.permission_id)
            .where(
                User.enabled.is_(True),
                Role.enabled.is_(True),
                Permission.enabled.is_(True),
                Permission.code == permission_code,
            )
            .distinct()
            .order_by(User.id.asc())
        )
        return list(db.session.scalars(stmt).all())

    def list_roles(self) -> list[Role]:
        return list(db.session.scalars(select(Role).order_by(Role.code.asc())).all())

    def list_permissions(self) -> list[Permission]:
        return list(
            db.session.scalars(select(Permission).order_by(Permission.code.asc())).all()
        )

    def get_role(self, role_id: int) -> Role | None:
        return db.session.get(Role, role_id)

    def find_role_by_code(self, code: str) -> Role | None:
        return db.session.scalar(select(Role).where(Role.code == code))

    def get_permissions(self, permission_ids: list[int]) -> list[Permission]:
        if not permission_ids:
            return []
        return list(
            db.session.scalars(
                select(Permission).where(Permission.id.in_(permission_ids))
            ).all()
        )

    def permission_codes_for_role(self, role_id: int) -> list[str]:
        stmt = (
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role_id)
            .order_by(Permission.code.asc())
        )
        return list(db.session.scalars(stmt).all())

    def get_roles(self, role_ids: list[int]) -> list[Role]:
        if not role_ids:
            return []
        return list(db.session.scalars(select(Role).where(Role.id.in_(role_ids))).all())

    def replace_role_permissions(self, role_id: int, permission_ids: list[int]) -> None:
        db.session.execute(
            delete(RolePermission).where(RolePermission.role_id == role_id)
        )
        db.session.add_all(
            [
                RolePermission(role_id=role_id, permission_id=item)
                for item in permission_ids
            ]
        )

    def replace_user_roles(self, user_id: int, role_ids: list[int]) -> None:
        db.session.execute(delete(UserRole).where(UserRole.user_id == user_id))
        db.session.add_all(
            [UserRole(user_id=user_id, role_id=item) for item in role_ids]
        )

    def replace_role_scope_organizations(
        self, role_id: int, organization_ids: list[int]
    ) -> None:
        db.session.execute(
            delete(RoleDataScopeOrganization).where(
                RoleDataScopeOrganization.role_id == role_id
            )
        )
        db.session.add_all(
            [
                RoleDataScopeOrganization(role_id=role_id, organization_id=item)
                for item in organization_ids
            ]
        )


rbac_repository = RbacRepository()

__all__ = ["RbacRepository", "rbac_repository"]
