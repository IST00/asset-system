"""add borrow due-date extension requests"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "asset_borrow_extension_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("operation_request_id", sa.Integer(), nullable=False),
        sa.Column("applicant_id", sa.Integer(), nullable=False),
        sa.Column(
            "original_expected_return_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "requested_expected_return_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default="PENDING", nullable=False
        ),
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_opinion", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["applicant_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["operation_request_id"], ["operation_requests.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_asset_borrow_extension_requests_operation_request_id",
        "asset_borrow_extension_requests",
        ["operation_request_id"],
    )
    op.create_index(
        "ix_asset_borrow_extension_requests_applicant_id",
        "asset_borrow_extension_requests",
        ["applicant_id"],
    )
    op.create_index(
        "ix_asset_borrow_extension_requests_status",
        "asset_borrow_extension_requests",
        ["status"],
    )
    op.create_index(
        "ix_asset_borrow_extension_requests_reviewed_by",
        "asset_borrow_extension_requests",
        ["reviewed_by"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_asset_borrow_extension_requests_reviewed_by",
        table_name="asset_borrow_extension_requests",
    )
    op.drop_index(
        "ix_asset_borrow_extension_requests_status",
        table_name="asset_borrow_extension_requests",
    )
    op.drop_index(
        "ix_asset_borrow_extension_requests_applicant_id",
        table_name="asset_borrow_extension_requests",
    )
    op.drop_index(
        "ix_asset_borrow_extension_requests_operation_request_id",
        table_name="asset_borrow_extension_requests",
    )
    op.drop_table("asset_borrow_extension_requests")
