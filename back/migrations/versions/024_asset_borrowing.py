"""add borrowing metadata to asset usage requests

Revision ID: 024
Revises: 023
Create Date: 2026-09-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("asset_usage_requests") as batch_op:
        batch_op.add_column(
            sa.Column("usage_mode", sa.String(length=16), nullable=True)
        )
        batch_op.add_column(
            sa.Column("expected_return_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_index(
            "ix_asset_usage_requests_usage_mode", ["usage_mode"], unique=False
        )
        batch_op.create_index(
            "ix_asset_usage_requests_expected_return_at",
            ["expected_return_at"],
            unique=False,
        )
    op.execute(
        sa.text(
            "UPDATE asset_usage_requests SET usage_mode = 'USE' "
            "WHERE usage_mode IS NULL"
        )
    )
    with op.batch_alter_table("asset_usage_requests") as batch_op:
        batch_op.alter_column(
            "usage_mode",
            existing_type=sa.String(length=16),
            nullable=False,
            server_default="USE",
        )


def downgrade() -> None:
    with op.batch_alter_table("asset_usage_requests") as batch_op:
        batch_op.drop_index("ix_asset_usage_requests_expected_return_at")
        batch_op.drop_index("ix_asset_usage_requests_usage_mode")
        batch_op.drop_column("expected_return_at")
        batch_op.drop_column("usage_mode")
