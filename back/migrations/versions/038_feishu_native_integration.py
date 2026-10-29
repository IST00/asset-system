"""add Feishu native identity mappings"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "038"
down_revision = "037_asset_transfer_handovers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column("feishu_open_id", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("feishu_user_id", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("feishu_union_id", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("feishu_synced_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "feishu_sync_status",
                sa.String(length=32),
                nullable=False,
                server_default="UNSYNCED",
            )
        )
        batch_op.create_unique_constraint("uq_users_feishu_open_id", ["feishu_open_id"])
        batch_op.create_unique_constraint("uq_users_feishu_user_id", ["feishu_user_id"])
        batch_op.create_unique_constraint(
            "uq_users_feishu_union_id", ["feishu_union_id"]
        )
        batch_op.create_index("ix_users_feishu_open_id", ["feishu_open_id"])
        batch_op.create_index("ix_users_feishu_user_id", ["feishu_user_id"])
        batch_op.create_index("ix_users_feishu_union_id", ["feishu_union_id"])

    with op.batch_alter_table("organizations") as batch_op:
        batch_op.add_column(
            sa.Column("feishu_department_id", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("feishu_synced_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_unique_constraint(
            "uq_organizations_feishu_department_id",
            ["feishu_department_id"],
        )
        batch_op.create_index(
            "ix_organizations_feishu_department_id",
            ["feishu_department_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("organizations") as batch_op:
        batch_op.drop_index("ix_organizations_feishu_department_id")
        batch_op.drop_constraint(
            "uq_organizations_feishu_department_id", type_="unique"
        )
        batch_op.drop_column("feishu_synced_at")
        batch_op.drop_column("feishu_department_id")

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_index("ix_users_feishu_union_id")
        batch_op.drop_index("ix_users_feishu_user_id")
        batch_op.drop_index("ix_users_feishu_open_id")
        batch_op.drop_constraint("uq_users_feishu_union_id", type_="unique")
        batch_op.drop_constraint("uq_users_feishu_user_id", type_="unique")
        batch_op.drop_constraint("uq_users_feishu_open_id", type_="unique")
        batch_op.drop_column("feishu_sync_status")
        batch_op.drop_column("feishu_synced_at")
        batch_op.drop_column("feishu_union_id")
        batch_op.drop_column("feishu_user_id")
        batch_op.drop_column("feishu_open_id")
