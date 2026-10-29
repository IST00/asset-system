"""add persistent in-product notifications"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_notifications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("notification_type", sa.String(length=48), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("related_operation_id", sa.Integer(), nullable=True),
        sa.Column("related_asset_id", sa.Integer(), nullable=True),
        sa.Column("deduplication_key", sa.String(length=191), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["related_operation_id"], ["operation_requests.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["related_asset_id"], ["assets.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "deduplication_key", name="uq_user_notification_dedup"
        ),
    )
    op.create_index("ix_user_notifications_user_id", "user_notifications", ["user_id"])
    op.create_index(
        "ix_user_notifications_notification_type",
        "user_notifications",
        ["notification_type"],
    )
    op.create_index(
        "ix_user_notifications_related_operation_id",
        "user_notifications",
        ["related_operation_id"],
    )
    op.create_index(
        "ix_user_notifications_related_asset_id",
        "user_notifications",
        ["related_asset_id"],
    )
    op.create_index("ix_user_notifications_read_at", "user_notifications", ["read_at"])


def downgrade() -> None:
    op.drop_index("ix_user_notifications_read_at", table_name="user_notifications")
    op.drop_index(
        "ix_user_notifications_related_asset_id", table_name="user_notifications"
    )
    op.drop_index(
        "ix_user_notifications_related_operation_id", table_name="user_notifications"
    )
    op.drop_index(
        "ix_user_notifications_notification_type", table_name="user_notifications"
    )
    op.drop_index("ix_user_notifications_user_id", table_name="user_notifications")
    op.drop_table("user_notifications")
