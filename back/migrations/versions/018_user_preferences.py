"""user preferences and account workspace settings

Revision ID: 018
Revises: 017
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_preferences",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("asset_list_columns", sa.Text(), nullable=True),
        sa.Column(
            "asset_list_page_size", sa.Integer(), nullable=False, server_default="50"
        ),
        sa.Column(
            "task_notice", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "approval_notice", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "weekly_digest", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("user_preferences")
