"""Create `events` table for Keke H5 analytics.

Revision ID: 002
Down revision: 001
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("event_name", sa.String(32), nullable=False, index=True),
        sa.Column("device_id", sa.String(64), nullable=False, index=True),
        sa.Column(
            "source",
            sa.String(32),
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
        sa.Column("ua", sa.String(32), nullable=True),
        sa.Column("keyword", sa.String(64), nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("events")
