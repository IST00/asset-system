"""reserve RFID tags during stock-in approval

Revision ID: 010
Revises: 009
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("stock_in_items") as batch:
        batch.add_column(sa.Column("rfid_tag", sa.String(length=191), nullable=True))
        batch.add_column(
            sa.Column("rfid_reservation_key", sa.String(length=191), nullable=True)
        )
        batch.create_index("ix_stock_in_items_rfid_tag", ["rfid_tag"], unique=False)
        batch.create_index(
            "ix_stock_in_items_rfid_reservation_key",
            ["rfid_reservation_key"],
            unique=False,
        )
        batch.create_unique_constraint(
            "uq_stock_in_items_rfid_reservation_key", ["rfid_reservation_key"]
        )


def downgrade() -> None:
    with op.batch_alter_table("stock_in_items") as batch:
        batch.drop_constraint("uq_stock_in_items_rfid_reservation_key", type_="unique")
        batch.drop_index("ix_stock_in_items_rfid_reservation_key")
        batch.drop_index("ix_stock_in_items_rfid_tag")
        batch.drop_column("rfid_reservation_key")
        batch.drop_column("rfid_tag")
