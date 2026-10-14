"""add requested quantity to personal asset usage requests

Revision ID: 022
Revises: 021
Create Date: 2026-09-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("asset_usage_requests") as batch_op:
        batch_op.add_column(
            sa.Column("requested_quantity", sa.Integer(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("asset_usage_requests") as batch_op:
        batch_op.drop_column("requested_quantity")
