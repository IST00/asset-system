"""Add optional holder to stock-in items.

Revision ID: 042
Revises: 041
Create Date: 2026-10-12
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "042"
down_revision = "041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("stock_in_items") as batch_op:
        batch_op.add_column(sa.Column("holder_user_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_stock_in_items_holder_user_id", ["holder_user_id"])
        batch_op.create_foreign_key(
            "fk_stock_in_items_holder_user_id_users",
            "users",
            ["holder_user_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    with op.batch_alter_table("stock_in_items") as batch_op:
        batch_op.drop_constraint(
            "fk_stock_in_items_holder_user_id_users", type_="foreignkey"
        )
        batch_op.drop_index("ix_stock_in_items_holder_user_id")
        batch_op.drop_column("holder_user_id")
