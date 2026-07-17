"""Role-based access-control persistence models."""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.enums import DataScope
from app.extensions import db
from app.models.mixins import TimestampMixin


class Role(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    data_scope: Mapped[str] = mapped_column(
        String(32), nullable=False, default=DataScope.SELF.value
    )
    built_in: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class Permission(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    module: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, index=True
    )


class UserRole(db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_user_roles_pair"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True
    )


class RolePermission(db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permissions_pair"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    permission_id: Mapped[int] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False, index=True
    )


class RoleDataScopeOrganization(db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "role_data_scope_organizations"
    __table_args__ = (
        UniqueConstraint("role_id", "organization_id", name="uq_role_scope_org_pair"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )


__all__ = [
    "Permission",
    "Role",
    "RoleDataScopeOrganization",
    "RolePermission",
    "UserRole",
]
