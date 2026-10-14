"""asset ownership, usage and return target fields

Revision ID: 041
Revises: 040
Create Date: 2026-10-10
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "041"
down_revision = "040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("assets") as batch_op:
        batch_op.add_column(sa.Column("usage_company_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_assets_usage_company_id", ["usage_company_id"])
        batch_op.create_foreign_key(
            "fk_assets_usage_company_id_organizations",
            "organizations",
            ["usage_company_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    with op.batch_alter_table("stock_in_items") as batch_op:
        batch_op.add_column(sa.Column("usage_company_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("usage_department_id", sa.Integer(), nullable=True)
        )
        batch_op.create_index(
            "ix_stock_in_items_usage_company_id", ["usage_company_id"]
        )
        batch_op.create_index(
            "ix_stock_in_items_usage_department_id", ["usage_department_id"]
        )
        batch_op.create_foreign_key(
            "fk_stock_in_items_usage_company_id_organizations",
            "organizations",
            ["usage_company_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            "fk_stock_in_items_usage_department_id_organizations",
            "organizations",
            ["usage_department_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    op.execute(
        "UPDATE assets SET usage_company_id = organization_id "
        "WHERE usage_company_id IS NULL"
    )
    op.execute(
        "UPDATE stock_in_items SET usage_company_id = "
        "(SELECT sir.organization_id FROM stock_in_requests sir "
        "WHERE sir.id = stock_in_items.stock_in_request_id) "
        "WHERE usage_company_id IS NULL"
    )

    with op.batch_alter_table("asset_usage_requests") as batch_op:
        batch_op.add_column(sa.Column("target_region_id", sa.Integer(), nullable=True))
        batch_op.create_index(
            "ix_asset_usage_requests_target_region_id", ["target_region_id"]
        )
        batch_op.create_foreign_key(
            "fk_asset_usage_requests_target_region_id_asset_locations",
            "asset_locations",
            ["target_region_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    with op.batch_alter_table("asset_return_requests") as batch_op:
        batch_op.add_column(sa.Column("return_company_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("return_usage_company_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(sa.Column("return_region_id", sa.Integer(), nullable=True))
        batch_op.create_index(
            "ix_asset_return_requests_return_company_id", ["return_company_id"]
        )
        batch_op.create_index(
            "ix_asset_return_requests_return_usage_company_id",
            ["return_usage_company_id"],
        )
        batch_op.create_index(
            "ix_asset_return_requests_return_region_id", ["return_region_id"]
        )
        batch_op.create_foreign_key(
            "fk_asset_return_requests_return_company_id_organizations",
            "organizations",
            ["return_company_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            "fk_asset_return_requests_return_usage_company_id_organizations",
            "organizations",
            ["return_usage_company_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            "fk_asset_return_requests_return_region_id_asset_locations",
            "asset_locations",
            ["return_region_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    with op.batch_alter_table("asset_return_requests") as batch_op:
        batch_op.drop_constraint(
            "fk_asset_return_requests_return_region_id_asset_locations",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_asset_return_requests_return_usage_company_id_organizations",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_asset_return_requests_return_company_id_organizations",
            type_="foreignkey",
        )
        batch_op.drop_index("ix_asset_return_requests_return_region_id")
        batch_op.drop_index("ix_asset_return_requests_return_usage_company_id")
        batch_op.drop_index("ix_asset_return_requests_return_company_id")
        batch_op.drop_column("return_region_id")
        batch_op.drop_column("return_usage_company_id")
        batch_op.drop_column("return_company_id")

    with op.batch_alter_table("asset_usage_requests") as batch_op:
        batch_op.drop_constraint(
            "fk_asset_usage_requests_target_region_id_asset_locations",
            type_="foreignkey",
        )
        batch_op.drop_index("ix_asset_usage_requests_target_region_id")
        batch_op.drop_column("target_region_id")

    with op.batch_alter_table("stock_in_items") as batch_op:
        batch_op.drop_constraint(
            "fk_stock_in_items_usage_department_id_organizations",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_stock_in_items_usage_company_id_organizations",
            type_="foreignkey",
        )
        batch_op.drop_index("ix_stock_in_items_usage_department_id")
        batch_op.drop_index("ix_stock_in_items_usage_company_id")
        batch_op.drop_column("usage_department_id")
        batch_op.drop_column("usage_company_id")

    with op.batch_alter_table("assets") as batch_op:
        batch_op.drop_constraint(
            "fk_assets_usage_company_id_organizations", type_="foreignkey"
        )
        batch_op.drop_index("ix_assets_usage_company_id")
        batch_op.drop_column("usage_company_id")
