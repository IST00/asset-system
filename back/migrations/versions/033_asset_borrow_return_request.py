"""track administrator requests to return borrowed assets"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "asset_usage_requests",
        sa.Column("return_requested_by", sa.Integer(), nullable=True),
    )
    op.add_column(
        "asset_usage_requests",
        sa.Column("return_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "asset_usage_requests",
        sa.Column("return_request_reason", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_asset_usage_requests_return_requested_by",
        "asset_usage_requests",
        ["return_requested_by"],
    )
    with op.batch_alter_table("asset_usage_requests") as batch_op:
        batch_op.create_foreign_key(
            "fk_asset_usage_requests_return_requested_by_users",
            "users",
            ["return_requested_by"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    with op.batch_alter_table("asset_usage_requests") as batch_op:
        batch_op.drop_constraint(
            "fk_asset_usage_requests_return_requested_by_users",
            type_="foreignkey",
        )
    op.drop_index(
        "ix_asset_usage_requests_return_requested_by",
        table_name="asset_usage_requests",
    )
    op.drop_column("asset_usage_requests", "return_request_reason")
    op.drop_column("asset_usage_requests", "return_requested_at")
    op.drop_column("asset_usage_requests", "return_requested_by")
