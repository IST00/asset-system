"""complete asset change, business attachment and scrap detail models

Revision ID: 029
Revises: 028
Create Date: 2026-09-04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("assets") as batch_op:
        batch_op.add_column(
            sa.Column("warranty_supplier_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("warranty_contact", sa.String(length=128), nullable=True)
        )
        batch_op.add_column(
            sa.Column("warranty_phone", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(sa.Column("warranty_expiry_date", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("warranty_description", sa.Text(), nullable=True))
        batch_op.create_foreign_key(
            "fk_assets_warranty_supplier_id_suppliers",
            "suppliers",
            ["warranty_supplier_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index(
            "ix_assets_warranty_supplier_id", ["warranty_supplier_id"]
        )

    op.create_table(
        "asset_information_change_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("operation_request_id", sa.Integer(), nullable=False),
        sa.Column("change_type", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["operation_request_id"], ["operation_requests.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "operation_request_id", name="uq_asset_information_change_operation"
        ),
    )
    op.create_index(
        "ix_asset_information_change_requests_operation_request_id",
        "asset_information_change_requests",
        ["operation_request_id"],
    )
    op.create_index(
        "ix_asset_information_change_requests_change_type",
        "asset_information_change_requests",
        ["change_type"],
    )

    with op.batch_alter_table("asset_attachments") as batch_op:
        batch_op.add_column(sa.Column("business_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "document_type",
                sa.String(length=32),
                nullable=False,
                server_default="OTHER",
            )
        )
        batch_op.create_index("ix_asset_attachments_business_id", ["business_id"])
        batch_op.create_index("ix_asset_attachments_document_type", ["document_type"])

    with op.batch_alter_table("asset_scrap_records") as batch_op:
        batch_op.add_column(sa.Column("disposition_remark", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("disposal_date", sa.Date(), nullable=True))
    op.execute(
        "UPDATE asset_scrap_records SET disposal_date = scrap_date WHERE disposal_date IS NULL"
    )


def downgrade() -> None:
    with op.batch_alter_table("asset_scrap_records") as batch_op:
        batch_op.drop_column("disposal_date")
        batch_op.drop_column("disposition_remark")

    with op.batch_alter_table("asset_attachments") as batch_op:
        batch_op.drop_index("ix_asset_attachments_document_type")
        batch_op.drop_index("ix_asset_attachments_business_id")
        batch_op.drop_column("document_type")
        batch_op.drop_column("business_id")

    op.drop_index(
        "ix_asset_information_change_requests_change_type",
        table_name="asset_information_change_requests",
    )
    op.drop_index(
        "ix_asset_information_change_requests_operation_request_id",
        table_name="asset_information_change_requests",
    )
    op.drop_table("asset_information_change_requests")

    with op.batch_alter_table("assets") as batch_op:
        batch_op.drop_index("ix_assets_warranty_supplier_id")
        batch_op.drop_constraint(
            "fk_assets_warranty_supplier_id_suppliers", type_="foreignkey"
        )
        batch_op.drop_column("warranty_description")
        batch_op.drop_column("warranty_expiry_date")
        batch_op.drop_column("warranty_phone")
        batch_op.drop_column("warranty_contact")
        batch_op.drop_column("warranty_supplier_id")
