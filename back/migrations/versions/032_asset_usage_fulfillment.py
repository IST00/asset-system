"""add independent issue and receipt stages to asset usage"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "asset_usage_requests",
        sa.Column(
            "fulfillment_status",
            sa.String(length=32),
            nullable=False,
            server_default="COMPLETED",
        ),
    )
    op.create_index(
        "ix_asset_usage_requests_fulfillment_status",
        "asset_usage_requests",
        ["fulfillment_status"],
    )
    op.add_column(
        "asset_usage_requests", sa.Column("issued_by", sa.Integer(), nullable=True)
    )
    op.add_column(
        "asset_usage_requests",
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "asset_usage_requests", sa.Column("issue_remark", sa.Text(), nullable=True)
    )
    op.add_column(
        "asset_usage_requests", sa.Column("signed_by", sa.Integer(), nullable=True)
    )
    op.add_column(
        "asset_usage_requests",
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "asset_usage_requests", sa.Column("sign_remark", sa.Text(), nullable=True)
    )
    op.create_index(
        "ix_asset_usage_requests_issued_by", "asset_usage_requests", ["issued_by"]
    )
    op.create_index(
        "ix_asset_usage_requests_signed_by", "asset_usage_requests", ["signed_by"]
    )
    with op.batch_alter_table("asset_usage_requests") as batch_op:
        batch_op.create_foreign_key(
            "fk_asset_usage_requests_issued_by_users",
            "users",
            ["issued_by"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            "fk_asset_usage_requests_signed_by_users",
            "users",
            ["signed_by"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    with op.batch_alter_table("asset_usage_requests") as batch_op:
        batch_op.drop_constraint(
            "fk_asset_usage_requests_signed_by_users", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_asset_usage_requests_issued_by_users", type_="foreignkey"
        )
    op.drop_index(
        "ix_asset_usage_requests_signed_by", table_name="asset_usage_requests"
    )
    op.drop_index(
        "ix_asset_usage_requests_issued_by", table_name="asset_usage_requests"
    )
    op.drop_column("asset_usage_requests", "sign_remark")
    op.drop_column("asset_usage_requests", "signed_at")
    op.drop_column("asset_usage_requests", "signed_by")
    op.drop_column("asset_usage_requests", "issue_remark")
    op.drop_column("asset_usage_requests", "issued_at")
    op.drop_column("asset_usage_requests", "issued_by")
    op.drop_index(
        "ix_asset_usage_requests_fulfillment_status", table_name="asset_usage_requests"
    )
    op.drop_column("asset_usage_requests", "fulfillment_status")
