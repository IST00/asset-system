"""add structured asset repair records

Revision ID: 025
Revises: 024
Create Date: 2026-09-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "asset_repair_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("repair_no", sa.String(length=64), nullable=False),
        sa.Column("before_status", sa.String(length=32), nullable=False),
        sa.Column("fault_description", sa.Text(), nullable=False),
        sa.Column("repair_supplier_id", sa.Integer(), nullable=True),
        sa.Column("repair_supplier_name", sa.String(length=255), nullable=True),
        sa.Column("repair_cost", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("repair_result", sa.Text(), nullable=True),
        sa.Column("confirmed_by", sa.Integer(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["repair_supplier_id"], ["suppliers.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["confirmed_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_asset_repair_records_asset_id", "asset_repair_records", ["asset_id"]
    )
    op.create_index(
        "ix_asset_repair_records_repair_no",
        "asset_repair_records",
        ["repair_no"],
    )
    op.create_index(
        "ix_asset_repair_records_repair_supplier_id",
        "asset_repair_records",
        ["repair_supplier_id"],
    )
    op.create_index(
        "ix_asset_repair_records_confirmed_by",
        "asset_repair_records",
        ["confirmed_by"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_asset_repair_records_confirmed_by", table_name="asset_repair_records"
    )
    op.drop_index(
        "ix_asset_repair_records_repair_supplier_id",
        table_name="asset_repair_records",
    )
    op.drop_index(
        "ix_asset_repair_records_repair_no", table_name="asset_repair_records"
    )
    op.drop_index("ix_asset_repair_records_asset_id", table_name="asset_repair_records")
    op.drop_table("asset_repair_records")
