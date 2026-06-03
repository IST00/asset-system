"""Create `devices` table — one row per first-time Keke H5 visitor.

Revision ID: 003
Down revision: 002
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "devices",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("device_id", sa.String(64), nullable=False, index=True),
        sa.Column(
            "source",
            sa.String(32),
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
        sa.Column("ua", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("devices")
