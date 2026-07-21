"""freeze shared operation contracts

Revision ID: 004
Revises: 003
Create Date: 2026-07-21
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("operation_requests") as batch_op:
        batch_op.add_column(
            sa.Column(
                "approval_execution_mode",
                sa.String(length=32),
                nullable=False,
                server_default="AUTO_ON_APPROVAL",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("operation_requests") as batch_op:
        batch_op.drop_column("approval_execution_mode")
