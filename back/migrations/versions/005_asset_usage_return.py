"""integrate asset usage and return

Revision ID: 005
Revises: 004
Create Date: 2026-07-23
"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


_PERMISSIONS = (
    (
        "asset:usage:manage",
        "管理资产领用退库",
        ("SUPER_ADMIN", "ASSET_ADMIN"),
    ),
    (
        "asset:return:self",
        "归还本人资产",
        ("SUPER_ADMIN", "ASSET_ADMIN", "USER"),
    ),
)


def _seed_permissions() -> None:
    bind = op.get_bind()
    now = datetime.now(tz=timezone.utc)
    for code, name, role_codes in _PERMISSIONS:
        permission_id = bind.scalar(
            sa.text("SELECT id FROM permissions WHERE code = :code"),
            {"code": code},
        )
        if permission_id is None:
            bind.execute(
                sa.text(
                    "INSERT INTO permissions "
                    "(code, name, module, enabled, created_at, updated_at) "
                    "VALUES (:code, :name, 'asset', 1, :now, :now)"
                ),
                {"code": code, "name": name, "now": now},
            )
            permission_id = bind.scalar(
                sa.text("SELECT id FROM permissions WHERE code = :code"),
                {"code": code},
            )

        for role_code in role_codes:
            bind.execute(
                sa.text(
                    "INSERT INTO role_permissions (role_id, permission_id) "
                    "SELECT r.id, :permission_id FROM roles r "
                    "WHERE r.code = :role_code AND NOT EXISTS ("
                    "SELECT 1 FROM role_permissions rp "
                    "WHERE rp.role_id = r.id AND rp.permission_id = :permission_id)"
                ),
                {"permission_id": permission_id, "role_code": role_code},
            )


def upgrade() -> None:
    op.create_table(
        "asset_usage_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("operation_request_id", sa.Integer(), nullable=False),
        sa.Column("target_user_id", sa.Integer(), nullable=True),
        sa.Column("target_public_object_id", sa.Integer(), nullable=True),
        sa.Column("usage_department_id", sa.Integer(), nullable=True),
        sa.Column("target_location_id", sa.Integer(), nullable=True),
        sa.Column("target_user_snapshot", sa.JSON(none_as_null=True), nullable=True),
        sa.Column(
            "usage_department_snapshot", sa.JSON(none_as_null=True), nullable=True
        ),
        sa.Column(
            "target_public_object_snapshot",
            sa.JSON(none_as_null=True),
            nullable=True,
        ),
        sa.Column(
            "target_location_snapshot", sa.JSON(none_as_null=True), nullable=True
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["operation_request_id"],
            ["operation_requests.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["target_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["target_public_object_id"],
            ["public_usage_objects.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["usage_department_id"],
            ["organizations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_location_id"],
            ["asset_locations.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_asset_usage_requests_operation_request_id"),
        "asset_usage_requests",
        ["operation_request_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_asset_usage_requests_target_user_id"),
        "asset_usage_requests",
        ["target_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_asset_usage_requests_target_public_object_id"),
        "asset_usage_requests",
        ["target_public_object_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_asset_usage_requests_usage_department_id"),
        "asset_usage_requests",
        ["usage_department_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_asset_usage_requests_target_location_id"),
        "asset_usage_requests",
        ["target_location_id"],
        unique=False,
    )

    op.create_table(
        "asset_return_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("operation_request_id", sa.Integer(), nullable=False),
        sa.Column("return_location_id", sa.Integer(), nullable=True),
        sa.Column("confirmed_by", sa.Integer(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "return_location_snapshot", sa.JSON(none_as_null=True), nullable=True
        ),
        sa.Column("confirmed_by_snapshot", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["operation_request_id"],
            ["operation_requests.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["return_location_id"],
            ["asset_locations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["confirmed_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_asset_return_requests_operation_request_id"),
        "asset_return_requests",
        ["operation_request_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_asset_return_requests_return_location_id"),
        "asset_return_requests",
        ["return_location_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_asset_return_requests_confirmed_by"),
        "asset_return_requests",
        ["confirmed_by"],
        unique=False,
    )

    op.create_table(
        "asset_return_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("operation_request_asset_id", sa.Integer(), nullable=False),
        sa.Column("condition", sa.String(length=16), nullable=True),
        sa.Column("condition_description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["operation_request_asset_id"],
            ["operation_request_assets.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_asset_return_items_operation_request_asset_id"),
        "asset_return_items",
        ["operation_request_asset_id"],
        unique=True,
    )

    _seed_permissions()


def downgrade() -> None:
    op.drop_table("asset_return_items")
    op.drop_table("asset_return_requests")
    op.drop_table("asset_usage_requests")

    bind = op.get_bind()
    permission_codes = tuple(code for code, _name, _roles in _PERMISSIONS)
    bind.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN ("
            "SELECT id FROM permissions WHERE code IN :codes)"
        ).bindparams(sa.bindparam("codes", expanding=True)),
        {"codes": permission_codes},
    )
    bind.execute(
        sa.text("DELETE FROM permissions WHERE code IN :codes").bindparams(
            sa.bindparam("codes", expanding=True)
        ),
        {"codes": permission_codes},
    )
