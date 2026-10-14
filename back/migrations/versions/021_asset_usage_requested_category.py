"""add requested category to personal asset usage

Revision ID: 021
Revises: 020
Create Date: 2026-09-02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("asset_usage_requests") as batch_op:
        batch_op.add_column(
            sa.Column("requested_category_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("requested_category_snapshot", sa.JSON(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_asset_usage_requests_requested_category_id",
            "asset_categories",
            ["requested_category_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index(
            "ix_asset_usage_requests_requested_category_id",
            ["requested_category_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("asset_usage_requests") as batch_op:
        batch_op.drop_index("ix_asset_usage_requests_requested_category_id")
        batch_op.drop_constraint(
            "fk_asset_usage_requests_requested_category_id",
            type_="foreignkey",
        )
        batch_op.drop_column("requested_category_snapshot")
        batch_op.drop_column("requested_category_id")
