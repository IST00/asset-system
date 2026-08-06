"""inventory enhancements: versions, reminders, surplus decisions and asset suites

Revision ID: 008
Revises: 007
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("inventory_items") as batch:
        batch.add_column(sa.Column("parent_asset_id", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column("parent_asset_code", sa.String(length=191), nullable=True)
        )
        batch.create_index(
            "ix_inventory_items_parent_asset_id", ["parent_asset_id"], unique=False
        )
    with op.batch_alter_table("inventory_scan_events") as batch:
        batch.add_column(sa.Column("resolution", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("resolution_reason", sa.Text(), nullable=True))
        batch.add_column(sa.Column("resolved_by", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.create_index(
            "ix_inventory_scan_events_resolution", ["resolution"], unique=False
        )
        batch.create_index(
            "ix_inventory_scan_events_resolved_by", ["resolved_by"], unique=False
        )
        batch.create_foreign_key(
            "fk_inventory_scan_events_resolved_by_users",
            "users",
            ["resolved_by"],
            ["id"],
            ondelete="RESTRICT",
        )

    op.create_table(
        "inventory_result_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("changed_by", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"], ["inventory_tasks.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["item_id"], ["inventory_items.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["changed_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "item_id", "version_no", name="uq_inventory_result_version"
        ),
    )
    for column in ("task_id", "item_id", "action", "changed_by"):
        op.create_index(
            f"ix_inventory_result_versions_{column}",
            "inventory_result_versions",
            [column],
            unique=False,
        )

    op.create_table(
        "inventory_reminders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("recipient_user_id", sa.Integer(), nullable=False),
        sa.Column("sent_by", sa.Integer(), nullable=False),
        sa.Column("batch_no", sa.String(length=64), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"], ["inventory_tasks.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["recipient_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["sent_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("task_id", "recipient_user_id", "sent_by", "batch_no"):
        op.create_index(
            f"ix_inventory_reminders_{column}",
            "inventory_reminders",
            [column],
            unique=False,
        )


def downgrade() -> None:
    op.drop_table("inventory_reminders")
    op.drop_table("inventory_result_versions")
    with op.batch_alter_table("inventory_scan_events") as batch:
        batch.drop_constraint(
            "fk_inventory_scan_events_resolved_by_users", type_="foreignkey"
        )
        batch.drop_index("ix_inventory_scan_events_resolved_by")
        batch.drop_index("ix_inventory_scan_events_resolution")
        batch.drop_column("resolved_at")
        batch.drop_column("resolved_by")
        batch.drop_column("resolution_reason")
        batch.drop_column("resolution")
    with op.batch_alter_table("inventory_items") as batch:
        batch.drop_index("ix_inventory_items_parent_asset_id")
        batch.drop_column("parent_asset_code")
        batch.drop_column("parent_asset_id")
