"""add structured asset scrap records

Revision ID: 028
Revises: 027
Create Date: 2026-09-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "asset_scrap_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("scrap_no", sa.String(length=64), nullable=False),
        sa.Column("scrap_date", sa.Date(), nullable=False),
        sa.Column("scrap_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("disposition", sa.String(length=255), nullable=True),
        sa.Column("confirmed_by", sa.Integer(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["confirmed_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_asset_scrap_records_asset_id", "asset_scrap_records", ["asset_id"]
    )
    op.create_index(
        "ix_asset_scrap_records_scrap_no", "asset_scrap_records", ["scrap_no"]
    )
    op.create_index(
        "ix_asset_scrap_records_confirmed_by",
        "asset_scrap_records",
        ["confirmed_by"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_asset_scrap_records_confirmed_by", table_name="asset_scrap_records"
    )
    op.drop_index("ix_asset_scrap_records_scrap_no", table_name="asset_scrap_records")
    op.drop_index("ix_asset_scrap_records_asset_id", table_name="asset_scrap_records")
    op.drop_table("asset_scrap_records")
