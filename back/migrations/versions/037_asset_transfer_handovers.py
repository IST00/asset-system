"""add two-party asset transfer handovers

Revision ID: 037_asset_transfer_handovers
Revises: 036_user_notifications
"""

from alembic import op
import sqlalchemy as sa

revision = "037_asset_transfer_handovers"
down_revision = "036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "asset_transfer_handovers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("handover_no", sa.String(length=64), nullable=False),
        sa.Column("initiated_by", sa.Integer(), nullable=False),
        sa.Column("outgoing_user_id", sa.Integer(), nullable=True),
        sa.Column("receiver_user_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("location_id", sa.Integer(), nullable=True),
        sa.Column("manager_id", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            nullable=False,
            server_default="PENDING_OUTGOING",
        ),
        sa.Column("outgoing_confirmed_by", sa.Integer(), nullable=True),
        sa.Column("outgoing_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_confirmed_by", sa.Integer(), nullable=True),
        sa.Column("received_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_by", sa.Integer(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["initiated_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["outgoing_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["receiver_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["location_id"], ["asset_locations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["manager_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["outgoing_confirmed_by"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["received_confirmed_by"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["rejected_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("handover_no"),
    )
    op.create_index(
        "ix_asset_transfer_handovers_handover_no",
        "asset_transfer_handovers",
        ["handover_no"],
        unique=True,
    )
    op.create_index(
        "ix_asset_transfer_handovers_receiver_user_id",
        "asset_transfer_handovers",
        ["receiver_user_id"],
    )
    op.create_index(
        "ix_asset_transfer_handovers_status", "asset_transfer_handovers", ["status"]
    )


def downgrade() -> None:
    op.drop_table("asset_transfer_handovers")
