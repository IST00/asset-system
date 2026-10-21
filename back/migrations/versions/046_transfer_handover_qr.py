"""Add open-receiver QR handovers.

Revision ID: 046
Revises: 045
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "046"
down_revision = "045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("asset_transfer_handovers") as batch_op:
        batch_op.add_column(
            sa.Column("handover_token", sa.String(length=64), nullable=True)
        )
        batch_op.alter_column(
            "receiver_user_id", existing_type=sa.Integer(), nullable=True
        )
    op.create_index(
        "uq_asset_transfer_handovers_handover_token",
        "asset_transfer_handovers",
        ["handover_token"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_asset_transfer_handovers_handover_token",
        table_name="asset_transfer_handovers",
    )
    # Open QR handovers cannot survive the non-null receiver constraint.
    op.get_bind().execute(
        sa.text(
            "DELETE FROM asset_transfer_handovers "
            "WHERE receiver_user_id IS NULL AND status = 'PENDING_RECEIPT'"
        )
    )
    with op.batch_alter_table("asset_transfer_handovers") as batch_op:
        batch_op.drop_column("handover_token")
        batch_op.alter_column(
            "receiver_user_id", existing_type=sa.Integer(), nullable=False
        )
