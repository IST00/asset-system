"""add inventory task foundation

Revision ID: 007
Revises: 006
Create Date: 2026-07-31
"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


_PERMISSIONS = (
    (
        "inventory:view",
        "查看盘点任务",
        "inventory",
        ("SUPER_ADMIN", "ASSET_ADMIN", "USER"),
    ),
    ("inventory:create", "创建盘点任务", "inventory", ("SUPER_ADMIN", "ASSET_ADMIN")),
    ("inventory:export", "导出盘点报告", "inventory", ("SUPER_ADMIN", "ASSET_ADMIN")),
    ("inventory:urge", "催办盘点任务", "inventory", ("SUPER_ADMIN", "ASSET_ADMIN")),
)


def _create_tables() -> None:
    op.create_table(
        "inventory_tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_no", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("photo_source_mode", sa.String(length=32), nullable=False),
        sa.Column("min_photo_count", sa.Integer(), nullable=False),
        sa.Column("scope_filters", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("collection_ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_inventory_tasks_task_no", "inventory_tasks", ["task_no"], unique=True
    )
    op.create_index(
        "ix_inventory_tasks_name", "inventory_tasks", ["name"], unique=False
    )
    op.create_index(
        "ix_inventory_tasks_status", "inventory_tasks", ["status"], unique=False
    )
    op.create_index(
        "ix_inventory_tasks_deadline_at",
        "inventory_tasks",
        ["deadline_at"],
        unique=False,
    )
    op.create_index(
        "ix_inventory_tasks_created_by", "inventory_tasks", ["created_by"], unique=False
    )

    op.create_table(
        "inventory_task_admins",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"], ["inventory_tasks.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "user_id", name="uq_inventory_task_admin_pair"),
    )
    op.create_index(
        "ix_inventory_task_admins_task_id",
        "inventory_task_admins",
        ["task_id"],
        unique=False,
    )
    op.create_index(
        "ix_inventory_task_admins_user_id",
        "inventory_task_admins",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "inventory_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("responsible_user_id", sa.Integer(), nullable=False),
        sa.Column("asset_code", sa.String(length=191), nullable=False),
        sa.Column("asset_name", sa.String(length=255), nullable=False),
        sa.Column("asset_status_snapshot", sa.String(length=32), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("organization_name", sa.String(length=128), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("category_name", sa.String(length=128), nullable=False),
        sa.Column("holder_user_id", sa.Integer(), nullable=True),
        sa.Column("holder_name", sa.String(length=128), nullable=True),
        sa.Column("ledger_location_id", sa.Integer(), nullable=True),
        sa.Column("ledger_location_name", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("physical_result", sa.String(length=32), nullable=True),
        sa.Column("location_result", sa.String(length=32), nullable=True),
        sa.Column("actual_location_id", sa.Integer(), nullable=True),
        sa.Column("actual_location_text", sa.String(length=500), nullable=True),
        sa.Column("loss_reason", sa.String(length=64), nullable=True),
        sa.Column("loss_description", sa.Text(), nullable=True),
        sa.Column("borrowed_by", sa.String(length=128), nullable=True),
        sa.Column("submission_method", sa.String(length=32), nullable=True),
        sa.Column("submitted_by", sa.Integer(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_late", sa.Boolean(), nullable=False),
        sa.Column("review_status", sa.String(length=32), nullable=False),
        sa.Column("resolution", sa.String(length=64), nullable=True),
        sa.Column("resolution_reason", sa.Text(), nullable=True),
        sa.Column("resolved_by", sa.Integer(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("admin_mark_reason", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"], ["inventory_tasks.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["responsible_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["actual_location_id"], ["asset_locations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["submitted_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "asset_id", name="uq_inventory_task_asset"),
    )
    for column in (
        "task_id",
        "asset_id",
        "responsible_user_id",
        "asset_code",
        "organization_id",
        "category_id",
        "holder_user_id",
        "ledger_location_id",
        "status",
        "physical_result",
        "location_result",
        "actual_location_id",
        "loss_reason",
        "submission_method",
        "submitted_by",
        "review_status",
        "resolution",
    ):
        op.create_index(
            f"ix_inventory_items_{column}", "inventory_items", [column], unique=False
        )

    op.create_table(
        "inventory_photos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("uploaded_by", sa.Integer(), nullable=False),
        sa.Column("storage_name", sa.String(length=255), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"], ["inventory_tasks.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["item_id"], ["inventory_items.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_inventory_photos_task_id", "inventory_photos", ["task_id"], unique=False
    )
    op.create_index(
        "ix_inventory_photos_item_id", "inventory_photos", ["item_id"], unique=False
    )
    op.create_index(
        "ix_inventory_photos_uploaded_by",
        "inventory_photos",
        ["uploaded_by"],
        unique=False,
    )
    op.create_index(
        "ix_inventory_photos_storage_name",
        "inventory_photos",
        ["storage_name"],
        unique=True,
    )

    op.create_table(
        "inventory_scan_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("scanned_by", sa.Integer(), nullable=False),
        sa.Column("scanned_value", sa.String(length=500), nullable=False),
        sa.Column("normalized_asset_code", sa.String(length=191), nullable=True),
        sa.Column("asset_id", sa.Integer(), nullable=True),
        sa.Column("item_id", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"], ["inventory_tasks.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["scanned_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["item_id"], ["inventory_items.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "task_id",
        "scanned_by",
        "normalized_asset_code",
        "asset_id",
        "item_id",
        "outcome",
    ):
        op.create_index(
            f"ix_inventory_scan_events_{column}",
            "inventory_scan_events",
            [column],
            unique=False,
        )


def _seed_permissions() -> None:
    now = datetime.now(tz=timezone.utc)
    table = sa.table(
        "permissions",
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("module", sa.String),
        sa.column("enabled", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        table,
        [
            {
                "code": code,
                "name": name,
                "module": module,
                "enabled": True,
                "created_at": now,
                "updated_at": now,
            }
            for code, name, module, _roles in _PERMISSIONS
        ],
    )
    bind = op.get_bind()
    for code, _name, _module, roles in _PERMISSIONS:
        for role in roles:
            bind.execute(
                sa.text(
                    "INSERT INTO role_permissions (role_id, permission_id) "
                    "SELECT roles.id, permissions.id FROM roles, permissions "
                    "WHERE roles.code = :role AND permissions.code = :permission"
                ),
                {"role": role, "permission": code},
            )


def upgrade() -> None:
    _create_tables()
    _seed_permissions()


def downgrade() -> None:
    bind = op.get_bind()
    codes = [item[0] for item in _PERMISSIONS]
    placeholders = ", ".join(f":code_{index}" for index in range(len(codes)))
    params = {f"code_{index}": code for index, code in enumerate(codes)}
    bind.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN "
            f"(SELECT id FROM permissions WHERE code IN ({placeholders}))"
        ),
        params,
    )
    bind.execute(
        sa.text(f"DELETE FROM permissions WHERE code IN ({placeholders})"),
        params,
    )
    op.drop_table("inventory_scan_events")
    op.drop_table("inventory_photos")
    op.drop_table("inventory_items")
    op.drop_table("inventory_task_admins")
    op.drop_table("inventory_tasks")
