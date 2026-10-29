"""add explicit employee handover to personal asset returns"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "asset_return_requests",
        sa.Column("handed_over_by", sa.Integer(), nullable=True),
    )
    op.add_column(
        "asset_return_requests",
        sa.Column("handed_over_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "asset_return_requests",
        sa.Column("handover_remark", sa.Text(), nullable=True),
    )
    op.add_column(
        "asset_return_requests",
        sa.Column("handed_over_by_snapshot", sa.JSON(), nullable=True),
    )
    op.create_index(
        "ix_asset_return_requests_handed_over_by",
        "asset_return_requests",
        ["handed_over_by"],
    )
    with op.batch_alter_table("asset_return_requests") as batch_op:
        batch_op.create_foreign_key(
            "fk_asset_return_requests_handed_over_by_users",
            "users",
            ["handed_over_by"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    with op.batch_alter_table("asset_return_requests") as batch_op:
        batch_op.drop_constraint(
            "fk_asset_return_requests_handed_over_by_users",
            type_="foreignkey",
        )
    op.drop_index(
        "ix_asset_return_requests_handed_over_by",
        table_name="asset_return_requests",
    )
    op.drop_column("asset_return_requests", "handed_over_by_snapshot")
    op.drop_column("asset_return_requests", "handover_remark")
    op.drop_column("asset_return_requests", "handed_over_at")
    op.drop_column("asset_return_requests", "handed_over_by")
